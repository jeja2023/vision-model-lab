from __future__ import annotations

from pathlib import Path

from vision_model_lab.adapters.reference_identity import export_onnx, run_evaluation, run_training


def test_reference_identity_pipeline_runs() -> None:
    config = Path("configs/experiments/reference_identity.yml")

    train_report = run_training(config)
    onnx_path = export_onnx(config)
    eval_report = run_evaluation(config, onnx_path)

    assert train_report.exists()
    assert onnx_path.exists()
    assert eval_report.exists()

