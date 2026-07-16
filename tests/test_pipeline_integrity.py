from __future__ import annotations

import json
import sys
from pathlib import Path

from vision_model_lab.adapters.registry import run_stage
from vision_model_lab.pipeline import run_experiment_pipeline
from vision_model_lab.utils import sha256_file, write_yaml


def _base_config(workspace_tmp_path: Path, experiment_id: str) -> dict:
    return {
        "experiment": {"id": experiment_id, "task": "classification"},
        "dataset": {"name": "regression_dataset", "version": "1.0.0"},
        "model": {"architecture": "resnet50", "version": "1.0.0"},
        "evaluation": {"adapter": "classification_baseline"},
        "export": {
            "adapter": "classification_baseline",
            "artifact_name": f"{experiment_id}_resnet50_v1.0.0_fp32.onnx",
        },
        "training": {"adapter": "classification_baseline"},
    }


def _make_real_onnx_script(target: Path) -> list[str]:
    """构造一个外部命令：产出与合成桩结构不同的真实 ONNX（含 Add 节点）。"""
    code = (
        "import onnx\n"
        "from onnx import TensorProto, helper\n"
        "node = helper.make_node('Add', ['input', 'input'], ['output'])\n"
        "graph = helper.make_graph([node], 'external_graph',"
        " [helper.make_tensor_value_info('input', TensorProto.FLOAT, [1, 4])],"
        " [helper.make_tensor_value_info('output', TensorProto.FLOAT, [1, 4])])\n"
        "model = helper.make_model(graph, producer_name='external-exporter',"
        " opset_imports=[helper.make_operatorsetid('', 17)])\n"
        "model.ir_version = 8\n"
        f"onnx.save(model, r'{target}')\n"
    )
    return [sys.executable, "-c", code]


def test_external_export_result_is_not_overwritten_by_synthetic_model(workspace_tmp_path: Path) -> None:
    """回归：外部导出命令产出的真实 ONNX 绝不能被合成桩模型覆盖。"""
    produced = workspace_tmp_path / "produced_model.onnx"
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "external_export_keep")
    payload["export"]["command"] = _make_real_onnx_script(produced)
    payload["export"]["produced_onnx"] = str(produced)
    write_yaml(config, payload)

    result = run_stage("export", config)

    assert result.status == "completed"
    output_path = Path(result.payload["onnx"])
    assert output_path.exists()
    # 最终产物必须与外部命令产物逐字节一致（未被桩模型覆盖）。
    assert sha256_file(output_path) == sha256_file(produced)
    report = json.loads(Path(result.payload["report"]).read_text(encoding="utf-8"))
    assert report["onnx_source"] == "external_command"


def test_export_does_not_silently_reuse_stale_onnx(workspace_tmp_path: Path) -> None:
    """回归：默认不复用已存在的 ONNX；显式 reuse_existing=true 时才复用。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "export_no_reuse")
    write_yaml(config, payload)

    first = run_stage("export", config)
    output_path = Path(first.payload["onnx"])
    stale_marker = b"stale"
    original_bytes = output_path.read_bytes()
    # 第二次导出应重新生成而不是保留旧文件内容。
    output_path.write_bytes(original_bytes + stale_marker)
    second = run_stage("export", config)
    assert second.status == "completed"
    assert Path(second.payload["onnx"]).read_bytes() == original_bytes

    # reuse_existing=true 时复用现有可加载产物。
    payload["export"]["reuse_existing"] = True
    write_yaml(config, payload)
    third = run_stage("export", config)
    report = json.loads(Path(third.payload["report"]).read_text(encoding="utf-8"))
    assert report["onnx_source"] == "reused"


def test_training_failure_short_circuits_pipeline_and_blocks_packaging(workspace_tmp_path: Path) -> None:
    """回归：训练失败必须短路，绝不产出模型包。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "training_failure_short_circuit")
    payload["training"]["command"] = [sys.executable, "-c", "import sys; sys.exit(1)"]
    write_yaml(config, payload)
    output_root = workspace_tmp_path / "packages"

    report = run_experiment_pipeline(config, package=True, output_root=output_root)

    assert report["status"] == "failed"
    assert report["failed_stage"] == "training"
    assert "package" not in report or not isinstance(report.get("package"), dict) or "validation" not in report.get("package", {})
    assert not list(output_root.rglob("*.onnx"))
    # 导出/评估阶段不应被执行。
    assert "export" not in report


def test_evaluation_reads_produced_metrics_and_marks_source(workspace_tmp_path: Path) -> None:
    """回归：外部评估命令产出的真实指标必须回读，并标注 metrics_source=measured。"""
    metrics_file = workspace_tmp_path / "metrics.json"
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "eval_produced_metrics")
    payload["evaluation"] = {
        "adapter": "classification_baseline",
        "command": [
            sys.executable,
            "-c",
            f"import json; json.dump({{'accuracy': 0.93, 'f1': 0.91}}, open(r'{metrics_file}', 'w'))",
        ],
        "produced_metrics": str(metrics_file),
        "expected_metrics": {"accuracy": 0.5},
    }
    write_yaml(config, payload)

    run_stage("export", config)
    result = run_stage("evaluation", config)

    assert result.status == "completed"
    assert result.payload["metrics"] == {"accuracy": 0.93, "f1": 0.91}
    assert result.payload["metrics_source"] == "measured"


def test_evaluation_fails_when_produced_metrics_missing(workspace_tmp_path: Path) -> None:
    """回归：声明了 produced_metrics 但文件缺失时评估必须失败，而非静默回落自报值。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "eval_missing_metrics")
    payload["evaluation"] = {
        "adapter": "classification_baseline",
        "command": [sys.executable, "-c", "pass"],
        "produced_metrics": str(workspace_tmp_path / "never_written.json"),
    }
    write_yaml(config, payload)

    run_stage("export", config)
    result = run_stage("evaluation", config)

    assert result.status == "failed"


def test_evaluation_without_external_command_marks_declared_source(workspace_tmp_path: Path) -> None:
    """回归：自报指标必须被明确标注为 declared，供发布链路区分。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "eval_declared_metrics")
    payload["evaluation"] = {
        "adapter": "classification_baseline",
        "expected_metrics": {"accuracy": 0.8},
    }
    write_yaml(config, payload)

    run_stage("export", config)
    result = run_stage("evaluation", config)

    assert result.status == "completed"
    assert result.payload["metrics_source"] == "declared"
    assert result.payload["metrics"]["accuracy"] == 0.8


def test_external_command_with_large_output_does_not_deadlock(workspace_tmp_path: Path) -> None:
    """回归：外部命令输出超过管道缓冲区（64KB）不得死锁。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "large_output_no_deadlock")
    # 输出约 2MB 文本，远超管道缓冲区。
    payload["training"]["command"] = [
        sys.executable,
        "-c",
        "import sys\nfor i in range(20000):\n    print('x' * 100)\nsys.exit(0)",
    ]
    write_yaml(config, payload)

    result = run_stage("training", config)

    assert result.status == "completed"
    assert result.payload["external"]["ok"] is True


def test_external_command_output_decodes_utf8_on_any_locale(workspace_tmp_path: Path) -> None:
    """回归：外部命令输出 UTF-8 中文时不得抛 UnicodeDecodeError。"""
    config = workspace_tmp_path / "config.yml"
    payload = _base_config(workspace_tmp_path, "utf8_output")
    payload["training"]["command"] = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.buffer.write('训练进度：第 1 轮完成\\n'.encode('utf-8'))",
    ]
    write_yaml(config, payload)

    result = run_stage("training", config)

    assert result.status == "completed"
    assert "训练进度" in result.payload["external"]["stdout"]


def test_log_truncation_keeps_tail(workspace_tmp_path: Path) -> None:
    """回归：日志截断必须保留尾部（Traceback 所在位置）。"""
    from vision_model_lab.adapters.local_tasks import _truncate_log

    text = "HEAD_MARKER\n" + ("x" * 50000) + "\nTAIL_TRACEBACK_MARKER"
    truncated = _truncate_log(text, 20000)
    assert "TAIL_TRACEBACK_MARKER" in truncated
    assert "HEAD_MARKER" in truncated
    assert len(truncated) < 21000
