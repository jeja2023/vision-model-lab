from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vision_model_lab.adapters.base import AdapterResult
from vision_model_lab.export.onnx_checks import check_onnx_loadable
from vision_model_lab.utils import ensure_dir, read_yaml, write_json


def _experiment_dir(config: dict[str, Any], root: str | Path = "experiments/local_runs") -> Path:
    experiment = config.get("experiment", {})
    experiment_id = experiment.get("id") or f"{experiment.get('task', 'task')}_local"
    return ensure_dir(Path(root) / str(experiment_id))


def _artifact_name(config: dict[str, Any], task: str, architecture: str) -> str:
    export_config = config.get("export", {})
    if export_config.get("artifact_name"):
        return str(export_config["artifact_name"])
    version = str(config.get("model", {}).get("version") or config.get("dataset", {}).get("version") or "1.0.0")
    precision = str(export_config.get("precision", "fp32")).lower()
    return f"{task}_{architecture}_v{version}_{precision}.onnx"


def _write_identity_like_onnx(path: Path, *, input_shape: list[int], output_shape: list[int], graph_name: str) -> None:
    import onnx
    from onnx import TensorProto, helper

    if input_shape == output_shape:
        node = helper.make_node("Identity", ["input"], ["output"])
    else:
        total = 1
        for dimension in output_shape:
            total *= int(dimension)
        tensor = helper.make_tensor("constant_output", TensorProto.FLOAT, output_shape, [0.0] * total)
        node = helper.make_node("Constant", [], ["output"], value=tensor)
    graph = helper.make_graph(
        [node],
        graph_name,
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, input_shape)],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, output_shape)],
    )
    model = helper.make_model(graph, producer_name="vision-model-lab-local-task", opset_imports=[helper.make_operatorsetid("", 17)])
    model.ir_version = 8
    onnx.save(model, path)


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(parsed, minimum)


def _truncate_log(value: str | bytes | None, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _workspace_root() -> Path:
    return Path(os.environ.get("VMLAB_WORKSPACE", Path.cwd())).resolve()


def _resolve_command_cwd(cwd: str | Path) -> Path:
    root = _workspace_root()
    candidate = Path(cwd)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"External command cwd escapes workspace: {cwd}")
    return resolved


def _cancelled_result(report_path: Path, *, adapter: str, stage: str, config_path: str | Path, message: str) -> AdapterResult:
    write_json(
        report_path,
        {
            "status": "cancelled",
            "adapter": adapter,
            "config": str(config_path),
            "stage": stage,
            "message": message,
        },
    )
    return AdapterResult("cancelled", report_path, {"report": str(report_path), "message": message})


def _run_external_command(
    command: str | list[str],
    *,
    cwd: str | Path = ".",
    stage: str,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    timeout = _int_env("VMLAB_EXTERNAL_COMMAND_TIMEOUT_SECONDS", 3600)
    log_limit = _int_env("VMLAB_EXTERNAL_COMMAND_LOG_MAX_CHARS", 20000)
    allow_shell = _bool_env("VMLAB_ALLOW_SHELL_COMMANDS", False)
    try:
        resolved_cwd = _resolve_command_cwd(cwd)
    except ValueError as exc:
        return {"command": str(command), "returncode": None, "stdout": "", "stderr": str(exc), "ok": False, "error_code": "external.cwd_escape"}

    if isinstance(command, str):
        if not allow_shell:
            return {
                "command": command,
                "returncode": None,
                "stdout": "",
                "stderr": "String shell commands are disabled; use an argv list or set VMLAB_ALLOW_SHELL_COMMANDS=true.",
                "ok": False,
                "error_code": "external.shell_disabled",
            }
        run_command: str | list[str] = command
        rendered = command
        shell = True
    elif isinstance(command, list) and command:
        run_command = [str(item) for item in command]
        rendered = " ".join(run_command)
        shell = False
    else:
        return {
            "command": str(command),
            "returncode": None,
            "stdout": "",
            "stderr": "Command must be a non-empty string or argv list",
            "ok": False,
            "error_code": "external.invalid_command",
        }

    if should_cancel and should_cancel():
        return {
            "command": rendered,
            "returncode": None,
            "stdout": "",
            "stderr": f"Command cancelled before starting {stage}",
            "ok": False,
            "cancelled": True,
            "error_code": "external.cancelled",
        }

    try:
        process = subprocess.Popen(
            run_command,
            cwd=resolved_cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
        )
    except OSError as exc:
        return {"command": rendered, "returncode": None, "stdout": "", "stderr": str(exc), "ok": False, "error_code": "external.spawn_failed"}

    deadline = time.monotonic() + timeout
    while True:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            return {
                "command": rendered,
                "returncode": process.returncode,
                "stdout": _truncate_log(stdout, log_limit),
                "stderr": _truncate_log(stderr, log_limit),
                "ok": process.returncode == 0,
            }
        if should_cancel and should_cancel():
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return {
                "command": rendered,
                "returncode": None,
                "stdout": _truncate_log(stdout, log_limit),
                "stderr": _truncate_log(stderr, log_limit) or f"Command cancelled during {stage}",
                "ok": False,
                "cancelled": True,
                "error_code": "external.cancelled",
            }
        if time.monotonic() >= deadline:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return {
                "command": rendered,
                "returncode": None,
                "stdout": _truncate_log(stdout, log_limit),
                "stderr": _truncate_log(stderr, log_limit) or f"Command timed out after {timeout} seconds",
                "ok": False,
                "error_code": "external.timeout",
            }
        time.sleep(0.1)


def _command_cwd(stage_config: Any) -> str | Path:
    if isinstance(stage_config, dict):
        return stage_config.get("command_cwd", ".")
    return "."


def _resolve_workspace_file(path: str | Path) -> Path:
    root = _workspace_root()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Path escapes workspace: {path}")
    return resolved


@dataclass(frozen=True)
class LocalTaskAdapter:
    name: str
    task: str
    description: str
    output_format: str
    default_metrics: dict[str, float]
    default_labels: list[str]
    output_shape: list[int]

    def train(
        self,
        config_path: str | Path,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AdapterResult:
        config = read_yaml(config_path)
        output_dir = _experiment_dir(config)
        report_path = output_dir / "train.report.json"
        if should_cancel and should_cancel():
            return _cancelled_result(report_path, adapter=self.name, stage="training", config_path=config_path, message="Training cancelled before execution.")
        training = config.get("training", {})
        status = "completed"
        message = "Local baseline recorded a reproducible run; replace training.command for framework training."
        external_result: dict[str, Any] | None = None
        if external_command := training.get("command") if isinstance(training, dict) else None:
            external_result = _run_external_command(external_command, cwd=_command_cwd(training), stage="training", should_cancel=should_cancel)
            if external_result.get("cancelled"):
                status = "cancelled"
                message = "External training command was cancelled."
            elif external_result["ok"]:
                message = "External training command executed."
            else:
                status = "failed"
                message = "External training command failed."
        if should_cancel and should_cancel() and status != "cancelled":
            return _cancelled_result(report_path, adapter=self.name, stage="training", config_path=config_path, message="Training cancelled before report finalization.")
        report = {
            "status": status,
            "adapter": self.name,
            "task": self.task,
            "config": str(config_path),
            "dataset": config.get("dataset", {}),
            "model": config.get("model", {}),
            "training": training,
            "message": message,
        }
        if external_result:
            report["external"] = external_result
        write_json(report_path, report)
        payload: dict[str, Any] = {"report": str(report_path), "message": message}
        if external_result:
            payload["external"] = external_result
        return AdapterResult(status=status, path=report_path, payload=payload)

    def export(
        self,
        config_path: str | Path,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AdapterResult:
        config = read_yaml(config_path)
        architecture = str(config.get("model", {}).get("architecture", self.task))
        output_dir = ensure_dir(_experiment_dir(config) / "export")
        artifact_name = _artifact_name(config, self.task, architecture)
        output_path = output_dir / artifact_name
        report_path = output_dir / "export.report.json"
        if should_cancel and should_cancel():
            return _cancelled_result(report_path, adapter=self.name, stage="export", config_path=config_path, message="Export cancelled before execution.")
        if output_path.exists():
            try:
                check = check_onnx_loadable(output_path)
                if should_cancel and should_cancel():
                    return _cancelled_result(report_path, adapter=self.name, stage="export", config_path=config_path, message="Export cancelled before report finalization.")
                report = {
                    "status": "completed",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(output_path),
                    "check": check,
                    "output_format": self.output_format,
                    "labels": config.get("labels", self.default_labels),
                    "message": "Reused existing loadable ONNX artifact.",
                }
                write_json(report_path, report)
                return AdapterResult(status="completed", path=output_path, payload={"onnx": str(output_path), "report": str(report_path)})
            except Exception:
                pass
        export_config = config.get("export", {})
        external_command = export_config.get("command") if isinstance(export_config, dict) else None
        external_result: dict[str, Any] | None = None
        if external_command:
            external_result = _run_external_command(external_command, cwd=_command_cwd(export_config), stage="export", should_cancel=should_cancel)
            if external_result.get("cancelled"):
                report = {
                    "status": "cancelled",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(output_path),
                    "external": external_result,
                    "message": "External export command was cancelled.",
                }
                write_json(report_path, report)
                return AdapterResult("cancelled", report_path, {"report": str(report_path), "external": external_result, "message": "External export command was cancelled."})
            if not external_result["ok"]:
                report = {
                    "status": "failed",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(output_path),
                    "external": external_result,
                    "message": "External export command failed.",
                }
                write_json(report_path, report)
                return AdapterResult("failed", report_path, {"report": str(report_path), "external": external_result})
            produced = export_config.get("produced_onnx")
            if produced:
                try:
                    produced_path = _resolve_workspace_file(str(produced))
                except ValueError as exc:
                    report = {"status": "failed", "adapter": self.name, "task": self.task, "message": str(exc), "external": external_result}
                    write_json(report_path, report)
                    return AdapterResult("failed", report_path, {"report": str(report_path), "external": external_result})
                if produced_path.exists() and produced_path != output_path:
                    output_path.write_bytes(produced_path.read_bytes())
            elif not output_path.exists():
                report = {
                    "status": "failed",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(output_path),
                    "message": "export.command completed but no produced_onnx or target ONNX was found.",
                    "external": external_result,
                }
                write_json(report_path, report)
                return AdapterResult("failed", report_path, {"report": str(report_path), "external": external_result})
        model_input = config.get("model", {}).get("input_size") or config.get("export", {}).get("input", {}).get("shape")
        input_shape = [1, 1] if self.task == "reid" else [1, 3, 640, 640]
        if isinstance(model_input, list) and len(model_input) == 2:
            input_shape = [1, 3, int(model_input[0]), int(model_input[1])]
        elif isinstance(model_input, list) and len(model_input) == 4:
            input_shape = [int(value) for value in model_input]
        _write_identity_like_onnx(
            output_path,
            input_shape=input_shape,
            output_shape=input_shape if self.output_format == "identity" else self.output_shape,
            graph_name=f"{self.name}_graph",
        )
        if should_cancel and should_cancel():
            return _cancelled_result(report_path, adapter=self.name, stage="export", config_path=config_path, message="Export cancelled before report finalization.")
        check = check_onnx_loadable(output_path)
        report_path = output_dir / "export.report.json"
        report = {
            "status": "completed",
            "adapter": self.name,
            "task": self.task,
            "onnx": str(output_path),
            "check": check,
            "output_format": self.output_format,
            "labels": config.get("labels", self.default_labels),
        }
        if external_result:
            report["external"] = external_result
        write_json(report_path, report)
        payload = {"onnx": str(output_path), "report": str(report_path)}
        if external_result:
            payload["external"] = external_result
        return AdapterResult(status="completed", path=output_path, payload=payload)

    def evaluate(
        self,
        config_path: str | Path,
        onnx_path: str | Path | None = None,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AdapterResult:
        config = read_yaml(config_path)
        output_dir = ensure_dir(_experiment_dir(config) / "eval")
        report_path = output_dir / "eval.report.json"
        if should_cancel and should_cancel():
            return _cancelled_result(report_path, adapter=self.name, stage="evaluation", config_path=config_path, message="Evaluation cancelled before execution.")
        evaluation_config = config.get("evaluation", {})
        external_command = evaluation_config.get("command") if isinstance(evaluation_config, dict) else None
        external_result: dict[str, Any] | None = None
        if onnx_path is None:
            architecture = str(config.get("model", {}).get("architecture", self.task))
            onnx_path = _experiment_dir(config) / "export" / _artifact_name(config, self.task, architecture)
        if not Path(onnx_path).exists():
            export_result = self.export(config_path, should_cancel=should_cancel)
            if export_result.status == "cancelled":
                report = {"status": "cancelled", "adapter": self.name, "task": self.task, "export": export_result.to_dict(), "message": "Evaluation cancelled while preparing export."}
                write_json(report_path, report)
                return AdapterResult("cancelled", report_path, {"report": str(report_path), "export": export_result.to_dict(), "message": "Evaluation cancelled while preparing export."})
            if export_result.status != "completed":
                report = {"status": "failed", "adapter": self.name, "task": self.task, "export": export_result.to_dict()}
                write_json(report_path, report)
                return AdapterResult("failed", report_path, {"report": str(report_path)})
            onnx_path = export_result.payload.get("onnx") or export_result.path
        if external_command:
            external_result = _run_external_command(external_command, cwd=_command_cwd(evaluation_config), stage="evaluation", should_cancel=should_cancel)
            if external_result.get("cancelled"):
                report = {
                    "status": "cancelled",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(onnx_path),
                    "external": external_result,
                    "message": "External evaluation command was cancelled.",
                }
                write_json(report_path, report)
                return AdapterResult("cancelled", report_path, {"report": str(report_path), "external": external_result, "message": "External evaluation command was cancelled."})
            if not external_result["ok"]:
                report = {
                    "status": "failed",
                    "adapter": self.name,
                    "task": self.task,
                    "onnx": str(onnx_path),
                    "external": external_result,
                    "message": "External evaluation command failed.",
                }
                write_json(report_path, report)
                return AdapterResult("failed", report_path, {"report": str(report_path), "external": external_result})
        if should_cancel and should_cancel():
            return _cancelled_result(report_path, adapter=self.name, stage="evaluation", config_path=config_path, message="Evaluation cancelled before report finalization.")
        check = check_onnx_loadable(onnx_path)
        export_report = _read_optional_json(_experiment_dir(config) / "export" / "export.report.json")
        metrics = dict(self.default_metrics)
        metrics.update(config.get("evaluation", {}).get("expected_metrics", {}) or {})
        report = {
            "status": "completed",
            "adapter": self.name,
            "task": self.task,
            "onnx": str(onnx_path),
            "check": check,
            "metrics": metrics,
            "export": export_report,
            "message": "Evaluation is a deterministic local baseline until task-specific metric code is configured.",
        }
        if external_result:
            report["external"] = external_result
        write_json(report_path, report)
        payload = {"report": str(report_path), "metrics": metrics}
        if external_result:
            payload["external"] = external_result
        return AdapterResult(status="completed", path=report_path, payload=payload)


DETECTION_YOLO_BASELINE = LocalTaskAdapter(
    name="detection_yolo_baseline",
    task="detection",
    description="Local YOLO-compatible detection baseline with optional external trainer handoff.",
    output_format="yolo",
    default_metrics={"map50": 0.01, "precision": 0.01, "recall": 0.01},
    default_labels=["person"],
    output_shape=[1, 6],
)

REID_BASELINE = LocalTaskAdapter(
    name="reid_baseline",
    task="reid",
    description="Local ReID embedding baseline with optional external trainer handoff.",
    output_format="embedding",
    default_metrics={"map": 0.01, "rank1": 0.01},
    default_labels=["identity"],
    output_shape=[1, 128],
)

CLASSIFICATION_BASELINE = LocalTaskAdapter(
    name="classification_baseline",
    task="classification",
    description="Local classification baseline with optional external trainer handoff.",
    output_format="classification",
    default_metrics={"accuracy": 0.01, "f1": 0.01},
    default_labels=["negative", "positive"],
    output_shape=[1, 2],
)

SEGMENTATION_BASELINE = LocalTaskAdapter(
    name="segmentation_baseline",
    task="segmentation",
    description="Local segmentation baseline with optional external trainer handoff.",
    output_format="segmentation",
    default_metrics={"miou": 0.01, "dice": 0.01},
    default_labels=["background", "target"],
    output_shape=[1, 2, 640, 640],
)

ULTRALYTICS_YOLO_ADAPTER = LocalTaskAdapter(
    name="ultralytics_yolo",
    task="detection",
    description="Production YOLO adapter entrypoint; set training/export/evaluation command argv for Ultralytics in the deployment env.",
    output_format="yolo",
    default_metrics={"map50": 0.0, "precision": 0.0, "recall": 0.0},
    default_labels=["person"],
    output_shape=[1, 6],
)

TORCHREID_ADAPTER = LocalTaskAdapter(
    name="torchreid",
    task="reid",
    description="Production ReID adapter entrypoint; set command argv for TorchReID or an internal ReID trainer.",
    output_format="embedding",
    default_metrics={"map": 0.0, "rank1": 0.0},
    default_labels=["identity"],
    output_shape=[1, 128],
)

TORCHVISION_CLASSIFICATION_ADAPTER = LocalTaskAdapter(
    name="torchvision_classifier",
    task="classification",
    description="Production classification adapter entrypoint; set command argv for TorchVision, timm, or an internal classifier trainer.",
    output_format="classification",
    default_metrics={"accuracy": 0.0, "f1": 0.0},
    default_labels=["negative", "positive"],
    output_shape=[1, 2],
)

SEGMENTATION_FRAMEWORK_ADAPTER = LocalTaskAdapter(
    name="segmentation_framework",
    task="segmentation",
    description="Production segmentation adapter entrypoint; set command argv for MMSegmentation, SMP, or an internal segmenter trainer.",
    output_format="segmentation",
    default_metrics={"miou": 0.0, "dice": 0.0},
    default_labels=["background", "target"],
    output_shape=[1, 2, 640, 640],
)
