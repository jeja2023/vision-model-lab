from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from vision_model_lab.storage import MetadataStore


def test_metadata_store_initializes_file_database_without_probe_files(workspace_tmp_path: Path) -> None:
    database = workspace_tmp_path / "store.sqlite3"

    store = MetadataStore(database)
    saved = store.upsert_experiment(
        {
            "id": "storage_file_test",
            "task": "classification",
            "dataset": "dataset_v1.0.0",
            "model": "resnet50",
            "status": "completed",
            "metrics": {"accuracy": 1.0},
        }
    )

    assert saved["id"] == "storage_file_test"
    assert database.exists()
    assert not list(workspace_tmp_path.glob(".vmlab-wal-probe-*"))


def test_metadata_store_pipeline_job_lifecycle() -> None:
    store = MetadataStore(":memory:")

    job = store.create_pipeline_job("configs/experiments/example.yml", {"package": False})
    running = store.mark_pipeline_job_running(int(job["id"]))
    completed = store.complete_pipeline_job(int(job["id"]), {"status": "completed"})

    assert job["status"] == "queued"
    assert running["status"] == "running"
    assert completed["status"] == "completed"
    assert completed["result"] == {"status": "completed"}
    assert store.list_pipeline_jobs()[0]["id"] == job["id"]

def test_metadata_store_job_logs_artifacts_and_mlops_records() -> None:
    store = MetadataStore(":memory:")

    job = store.create_pipeline_job("configs/experiments/example.yml", {"package": True})
    log = store.record_pipeline_job_log(int(job["id"]), "training", "completed", {"status": "completed"})
    artifact = store.record_pipeline_artifact(job_id=int(job["id"]), name="model.onnx", kind="onnx", path="model.onnx", uri="model.onnx", size=12)
    dataset = store.upsert_dataset_version(
        {
            "dataset_id": "people_v1.0.0",
            "name": "people",
            "version": "1.0.0",
            "task": "detection",
            "manifest_path": "data/train.jsonl",
            "split_counts": {"train": 10},
            "labels": ["person"],
        }
    )
    model = store.upsert_model_registry_entry(
        {
            "model_id": "cross_camera_tracking/model.onnx",
            "package_dir": "shared-models/cross_camera_tracking",
            "artifact_name": "model.onnx",
            "version": "1.0.0",
            "task": "detection",
            "metrics": {"map50": 0.5},
            "stage": "candidate",
        }
    )
    approval = store.record_release_approval(
        {"model_id": model["model_id"], "recommendation": "gray_release", "status": "approved", "decision": {"model": model["model_id"]}}
    )
    rollout = store.upsert_deployment_rollout(
        {"model_id": model["model_id"], "environment": "production", "strategy": "gray", "status": "planned", "traffic_percent": 10}
    )

    assert log["detail"] == {"status": "completed"}
    assert artifact["kind"] == "onnx"
    assert store.list_pipeline_job_logs(int(job["id"]))[0]["id"] == log["id"]
    assert store.list_pipeline_artifacts(job_id=int(job["id"]))[0]["id"] == artifact["id"]
    assert dataset["split_counts"] == {"train": 10}
    assert model["metrics"] == {"map50": 0.5}
    assert approval["status"] == "approved"
    assert rollout["traffic_percent"] == 10


def test_alembic_upgrade_supports_plain_sqlite_path_and_creates_base_tables(workspace_tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    database = workspace_tmp_path / "alembic_upgrade.sqlite3"
    env = {**os.environ, "VMLAB_WORKSPACE": str(repo_root), "VMLAB_METADATA_DB": str(database)}

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=repo_root, env=env, check=True, capture_output=True, text=True)

    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}

    assert {
        "experiments",
        "package_validations",
        "pipeline_runs",
        "pipeline_jobs",
        "audit_events",
        "pipeline_job_logs",
        "pipeline_artifacts",
        "dataset_versions",
        "model_registry",
        "release_approvals",
        "deployment_rollouts",
    } <= tables
