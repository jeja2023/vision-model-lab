from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from vision_model_lab import __version__
from vision_model_lab.adapters.registry import list_adapters
from vision_model_lab.contracts import validate_models_fragment, validate_release_decision
from vision_model_lab.datasets.manifest import validate_manifest
from vision_model_lab.object_store import object_store_from_settings
from vision_model_lab.packaging.model_package import validate_model_package
from vision_model_lab.naming import parse_artifact_name
from vision_model_lab.pipeline import collect_pipeline_artifacts, create_package_from_experiment, load_error_cases, run_experiment_pipeline
from vision_model_lab.settings import load_settings
from vision_model_lab.storage import metadata_store_from_uri
from vision_model_lab.utils import read_yaml


SETTINGS = load_settings()
WORKSPACE_ROOT = SETTINGS.workspace_root
STORE = metadata_store_from_uri(SETTINGS.metadata_db)
EXECUTOR = ThreadPoolExecutor(max_workers=SETTINGS.pipeline_workers, thread_name_prefix="vmlab-pipeline")

app = FastAPI(
    title="Vision Model Lab",
    version=__version__,
    description="Management API for vision model research artifacts, dataset manifests, experiments, and delivery packages.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if SETTINGS.serve_frontend and SETTINGS.frontend_dist.exists():
    assets_dir = SETTINGS.frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


class ApiModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), populate_by_name=True)


def workspace_path(value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    resolved = candidate.resolve()
    if resolved != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved.parents:
        raise HTTPException(status_code=400, detail=f"Path escapes workspace: {value}")
    return resolved


def workspace_relative(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path)


def _storage_uri() -> str:
    if SETTINGS.storage_backend == "local":
        return str(workspace_path(SETTINGS.storage_uri))
    return SETTINGS.storage_uri


def _safe_frontend_file(path: str) -> Path | None:
    frontend_root = SETTINGS.frontend_dist.resolve()
    requested = (frontend_root / path).resolve()
    if requested != frontend_root and frontend_root not in requested.parents:
        return None
    if requested.exists() and requested.is_file():
        return requested
    return None


class PackageValidationRequest(ApiModel):
    package_dir: str = Field(default="shared-models")
    model_id: str | None = None
    strict_hash: bool = False
    strict_sidecars: bool = True
    strict_examples: bool = True
    strict_onnx: bool = False
    persist: bool = True


class ManifestValidationRequest(ApiModel):
    path: str
    min_split_counts: dict[str, int] = Field(default_factory=dict)
    allowed_labels: list[str] = Field(default_factory=list)


class ContractValidationRequest(ApiModel):
    kind: str = Field(pattern="^(models-fragment|release-decision)$")
    path: str


class ExperimentRecord(ApiModel):
    id: str
    task: str
    dataset: str
    model: str
    status: str = "planned"
    package: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class PipelineRunRequest(ApiModel):
    config_path: str
    package: bool = False
    output_root: str = "shared-models"
    persist: bool = True
    async_run: bool = Field(default=False, alias="async")


class PackageCreateRequest(ApiModel):
    config_path: str
    onnx_path: str | None = None
    output_root: str = "shared-models"
    project_name: str | None = None
    overwrite: bool = True


class ErrorAnalysisRequest(ApiModel):
    path: str


class DatasetVersionRegisterRequest(ApiModel):
    name: str
    version: str
    task: str
    manifest_path: str
    dataset_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    allowed_labels: list[str] = Field(default_factory=list)
    min_split_counts: dict[str, int] = Field(default_factory=dict)
    status: str = "registered"


class ModelRegistryRegisterRequest(ApiModel):
    package_dir: str
    model_id: str | None = None
    stage: str = "candidate"
    metrics: dict[str, float] = Field(default_factory=dict)


class ReleaseApprovalRequest(ApiModel):
    path: str
    status: str = "pending"


class DeploymentRolloutRequest(ApiModel):
    model_id: str
    environment: str = "production"
    strategy: str = "gray"
    status: str = "planned"
    traffic_percent: int = Field(default=0, ge=0, le=100)
    rollback_target: str | None = None


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not SETTINGS.auth_token:
        return
    expected = f"Bearer {SETTINGS.auth_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _pipeline_payload(config_path: Path, output_root: Path, request: PipelineRunRequest) -> dict[str, Any]:
    return {
        "config_path": str(config_path),
        "package": request.package,
        "output_root": str(output_root),
        "persist": request.persist,
    }


def _record_pipeline_artifacts(report: dict[str, Any], *, job_id: int | None = None, run_id: int | None = None) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for artifact in collect_pipeline_artifacts(report):
        indexed.append(
            STORE.record_pipeline_artifact(
                job_id=job_id,
                run_id=run_id,
                name=str(artifact["name"]),
                kind=str(artifact["kind"]),
                path=str(artifact.get("path")) if artifact.get("path") else None,
                uri=str(artifact.get("uri")) if artifact.get("uri") else None,
                size=int(artifact["size"]) if artifact.get("size") is not None else None,
            )
        )
    return indexed


def _pipeline_job_detail(job_id: int) -> dict[str, Any]:
    job = STORE.get_pipeline_job(job_id)
    job["logs"] = STORE.list_pipeline_job_logs(job_id)
    job["artifacts"] = STORE.list_pipeline_artifacts(job_id=job_id)
    return job


def _run_pipeline_job(job_id: int, payload: dict[str, Any]) -> None:
    def event_sink(stage: str, message: str, detail: dict[str, Any]) -> None:
        STORE.record_pipeline_job_log(job_id, stage, message, detail)

    try:
        job = STORE.mark_pipeline_job_running(job_id)
        if job["status"] == "cancelled":
            STORE.record_pipeline_job_log(job_id, "job", "cancelled before start")
            return
        STORE.record_pipeline_job_log(job_id, "job", "started", {"config_path": payload["config_path"]})
        report = run_experiment_pipeline(
            payload["config_path"],
            package=bool(payload.get("package")),
            output_root=payload.get("output_root", "shared-models"),
            event_sink=event_sink,
        )
        run_record = STORE.record_pipeline_run(payload["config_path"], report) if payload.get("persist", True) else None
        _record_pipeline_artifacts(report, job_id=job_id, run_id=int(run_record["id"]) if run_record else None)
        STORE.record_audit_event(
            actor="api",
            action="pipeline.job.completed",
            target=str(job_id),
            detail={"config_path": payload["config_path"], "package": bool(payload.get("package"))},
        )
        current = STORE.get_pipeline_job(job_id)
        if report.get("status") == "failed":
            STORE.fail_pipeline_job(job_id, "Pipeline stage failed", report)
            return
        final_status = "cancelled" if current["status"] == "cancellation_requested" else "completed"
        STORE.complete_pipeline_job(job_id, report, status=final_status)
    except Exception as exc:  # noqa: BLE001
        STORE.record_pipeline_job_log(job_id, "job", "failed", {"error": str(exc)})
        STORE.fail_pipeline_job(job_id, str(exc))
        STORE.record_audit_event(actor="api", action="pipeline.job.failed", target=str(job_id), detail={"error": str(exc)})


def _queue_pipeline_job(payload: dict[str, Any]) -> dict[str, Any]:
    job = STORE.create_pipeline_job(payload["config_path"], payload)
    EXECUTOR.submit(_run_pipeline_job, int(job["id"]), payload)
    STORE.record_audit_event(
        actor="api",
        action="pipeline.job.queued",
        target=str(job["id"]),
        detail={"config_path": payload["config_path"], "package": bool(payload.get("package"))},
    )
    return job


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "workspace": str(WORKSPACE_ROOT),
        "metadata_db": SETTINGS.metadata_db,
        "serve_frontend": SETTINGS.serve_frontend and SETTINGS.frontend_dist.exists(),
        "storage_backend": SETTINGS.storage_backend,
        "storage_uri": SETTINGS.storage_uri,
        "auth_required": bool(SETTINGS.auth_token),
        "pipeline_workers": SETTINGS.pipeline_workers,
        "external_shell_commands_allowed": SETTINGS.allow_shell_commands,
    }


@app.post("/api/packages/validate", dependencies=[Depends(require_auth)])
def validate_package_endpoint(request: PackageValidationRequest) -> dict[str, Any]:
    package_dir = workspace_path(request.package_dir)
    result = validate_model_package(
        package_dir,
        model_id=request.model_id,
        strict_hash=request.strict_hash,
        strict_sidecars=request.strict_sidecars,
        strict_examples=request.strict_examples,
        strict_onnx=request.strict_onnx,
    )
    report = result.to_dict()
    if request.persist:
        validation = STORE.record_package_validation(report)
        STORE.record_audit_event(actor="api", action="package.validate", target=str(package_dir), detail={"ok": report["ok"]})
        return {"validation": validation}
    return {"validation": report}


@app.get("/api/packages/scan")
def scan_packages(
    root: str = Query(default="shared-models"),
    strict_hash: bool = Query(default=False),
    strict_examples: bool = Query(default=True),
) -> dict[str, Any]:
    resolved_root = workspace_path(root)
    if not resolved_root.exists():
        return {"root": str(resolved_root), "packages": []}
    packages: list[dict[str, Any]] = []
    model_files = sorted(resolved_root.rglob("*.onnx"))
    if len(model_files) > SETTINGS.max_package_scan_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many ONNX files under {root}; limit is {SETTINGS.max_package_scan_files}",
        )
    for model_file in model_files:
        result = validate_model_package(
            model_file.parent,
            model_id=model_file.name,
            strict_hash=strict_hash,
            strict_examples=strict_examples,
        )
        packages.append(result.to_dict())
    return {"root": str(resolved_root), "packages": packages}


@app.get("/api/package-validations")
def list_package_validations(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"validations": STORE.list_package_validations(limit)}


@app.post("/api/manifests/validate")
def validate_manifest_endpoint(request: ManifestValidationRequest) -> dict[str, Any]:
    result = validate_manifest(
        workspace_path(request.path),
        min_split_counts=request.min_split_counts or None,
        allowed_labels=request.allowed_labels or None,
    )
    return {"manifest": result.to_dict()}


@app.post("/api/contracts/validate")
def validate_contract_endpoint(request: ContractValidationRequest) -> dict[str, Any]:
    path = workspace_path(request.path)
    if request.kind == "models-fragment":
        result = validate_models_fragment(path)
    else:
        result = validate_release_decision(path)
    return {"contract": result.to_dict()}


@app.get("/api/experiments")
def list_experiments(index_path: str = Query(default="experiments/index.yml")) -> dict[str, Any]:
    records = STORE.list_experiments()
    index_file = workspace_path(index_path)
    index_records: list[dict[str, Any]] = []
    if index_file.exists():
        data = read_yaml(index_file)
        raw_records = data.get("experiments", [])
        if isinstance(raw_records, list):
            index_records = [record for record in raw_records if isinstance(record, dict)]
    return {"experiments": records, "index": index_records}


@app.post("/api/experiments", dependencies=[Depends(require_auth)])
def upsert_experiment(record: ExperimentRecord) -> dict[str, Any]:
    saved = STORE.upsert_experiment(record.model_dump())
    STORE.record_audit_event(actor="api", action="experiment.upsert", target=record.id, detail={"status": record.status})
    return {"experiment": saved}


@app.get("/api/adapters")
def adapters() -> dict[str, Any]:
    return {"adapters": list_adapters()}


@app.post("/api/pipelines/run", dependencies=[Depends(require_auth)])
def run_pipeline_endpoint(request: PipelineRunRequest) -> dict[str, Any]:
    config_path = workspace_path(request.config_path)
    output_root = workspace_path(request.output_root)
    payload = _pipeline_payload(config_path, output_root, request)
    if request.async_run:
        return {"job": _queue_pipeline_job(payload)}
    report = run_experiment_pipeline(config_path, package=request.package, output_root=output_root)
    STORE.record_audit_event(actor="api", action="pipeline.run", target=str(config_path), detail={"package": request.package})
    if request.persist:
        run_record = STORE.record_pipeline_run(str(config_path), report)
        _record_pipeline_artifacts(report, run_id=int(run_record["id"]))
        return {"run": run_record}
    return {"run": report}


@app.get("/api/pipelines/runs")
def list_pipeline_runs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"runs": STORE.list_pipeline_runs(limit)}


@app.get("/api/pipelines/jobs")
def list_pipeline_jobs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"jobs": STORE.list_pipeline_jobs(limit)}


@app.get("/api/pipelines/jobs/{job_id}")
def get_pipeline_job(job_id: int) -> dict[str, Any]:
    try:
        return {"job": _pipeline_job_detail(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline job not found") from exc


@app.get("/api/pipelines/jobs/{job_id}/logs")
def list_pipeline_job_logs(job_id: int, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    try:
        STORE.get_pipeline_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline job not found") from exc
    return {"logs": STORE.list_pipeline_job_logs(job_id, limit)}


@app.get("/api/pipelines/jobs/{job_id}/artifacts")
def list_pipeline_job_artifacts(job_id: int, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    try:
        STORE.get_pipeline_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline job not found") from exc
    return {"artifacts": STORE.list_pipeline_artifacts(job_id=job_id, limit=limit)}


@app.post("/api/pipelines/jobs/{job_id}/cancel", dependencies=[Depends(require_auth)])
def cancel_pipeline_job(job_id: int) -> dict[str, Any]:
    try:
        job = STORE.request_pipeline_job_cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline job not found") from exc
    STORE.record_audit_event(actor="api", action="pipeline.job.cancel", target=str(job_id), detail={"status": job["status"]})
    return {"job": job}


@app.post("/api/pipelines/jobs/{job_id}/retry", dependencies=[Depends(require_auth)])
def retry_pipeline_job(job_id: int) -> dict[str, Any]:
    try:
        job = STORE.get_pipeline_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline job not found") from exc
    return {"job": _queue_pipeline_job(job["request"])}


@app.post("/api/packages/create", dependencies=[Depends(require_auth)])
def create_package_endpoint(request: PackageCreateRequest) -> dict[str, Any]:
    config_path = workspace_path(request.config_path)
    onnx_path = workspace_path(request.onnx_path) if request.onnx_path else None
    output_root = workspace_path(request.output_root)
    result = create_package_from_experiment(
        config_path,
        onnx_path=onnx_path,
        output_root=output_root,
        project_name=request.project_name,
        overwrite=request.overwrite,
    )
    STORE.record_audit_event(actor="api", action="package.create", target=result["artifact_name"], detail=result["validation"])
    return {"package": result}


@app.post("/api/uploads", dependencies=[Depends(require_auth)])
def upload_file(file: UploadFile, target_dir: str = "artifacts/uploads") -> dict[str, Any]:
    resolved_dir = workspace_path(target_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    destination = resolved_dir / Path(file.filename or "upload.bin").name
    total_bytes = 0
    try:
        with destination.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > SETTINGS.max_upload_bytes:
                    raise HTTPException(status_code=413, detail=f"Upload exceeds {SETTINGS.max_upload_bytes} bytes")
                handle.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    try:
        stored = object_store_from_settings(SETTINGS.storage_backend, _storage_uri()).put_file(destination, destination.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STORE.record_audit_event(actor="api", action="file.upload", target=str(destination), detail=stored.to_dict())
    return {"upload": {"path": str(destination), "stored": stored.to_dict()}}


@app.post("/api/error-analysis")
def error_analysis_endpoint(request: ErrorAnalysisRequest) -> dict[str, Any]:
    return {"analysis": load_error_cases(workspace_path(request.path))}


@app.get("/api/audit-events")
def list_audit_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"events": STORE.list_audit_events(limit)}


@app.get("/api/datasets/versions")
def list_dataset_versions(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"datasets": STORE.list_dataset_versions(limit)}


@app.post("/api/datasets/versions", dependencies=[Depends(require_auth)])
def register_dataset_version(request: DatasetVersionRegisterRequest) -> dict[str, Any]:
    manifest_path = workspace_path(request.manifest_path)
    validation = validate_manifest(
        manifest_path,
        min_split_counts=request.min_split_counts or None,
        allowed_labels=request.allowed_labels or None,
    )
    if not validation.ok:
        raise HTTPException(status_code=400, detail={"manifest": validation.to_dict()})
    dataset_id = request.dataset_id or f"{request.name}_v{request.version}"
    dataset = STORE.upsert_dataset_version(
        {
            "dataset_id": dataset_id,
            "name": request.name,
            "version": request.version,
            "task": request.task,
            "manifest_path": workspace_relative(manifest_path),
            "split_counts": validation.split_counts,
            "labels": request.labels,
            "status": request.status,
        }
    )
    STORE.record_audit_event(actor="api", action="dataset.register", target=dataset_id, detail={"rows": validation.total_rows})
    return {"dataset": dataset, "manifest": validation.to_dict()}


@app.get("/api/models/registry")
def list_model_registry(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"models": STORE.list_model_registry_entries(limit)}


@app.post("/api/models/registry", dependencies=[Depends(require_auth)])
def register_model(request: ModelRegistryRegisterRequest) -> dict[str, Any]:
    package_dir = workspace_path(request.package_dir)
    validation = validate_model_package(package_dir, model_id=request.model_id, strict_hash=True, strict_examples=True, strict_onnx=False)
    if not validation.ok or validation.model_file is None:
        raise HTTPException(status_code=400, detail={"validation": validation.to_dict()})
    artifact = parse_artifact_name(validation.model_file.name)
    task = "model"
    if validation.model_card and validation.model_card.exists():
        card = read_yaml(validation.model_card)
        model_section = card.get("model", {}) if isinstance(card, dict) else {}
        if isinstance(model_section, dict):
            task = str(model_section.get("task") or task)
    model_id = request.model_id or f"{workspace_relative(package_dir)}/{validation.model_file.name}"
    model = STORE.upsert_model_registry_entry(
        {
            "model_id": model_id,
            "package_dir": workspace_relative(package_dir),
            "artifact_name": validation.model_file.name,
            "version": artifact.version,
            "task": task,
            "metrics": request.metrics,
            "stage": request.stage,
        }
    )
    STORE.record_audit_event(actor="api", action="model.register", target=model_id, detail={"stage": request.stage})
    return {"model": model, "validation": validation.to_dict()}


@app.get("/api/releases/approvals")
def list_release_approvals(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"approvals": STORE.list_release_approvals(limit)}


@app.post("/api/releases/approvals", dependencies=[Depends(require_auth)])
def record_release_approval(request: ReleaseApprovalRequest) -> dict[str, Any]:
    decision_path = workspace_path(request.path)
    validation = validate_release_decision(decision_path)
    if not validation.ok:
        raise HTTPException(status_code=400, detail={"contract": validation.to_dict()})
    data = read_yaml(decision_path)
    decision = data.get("decision", {}) if isinstance(data, dict) else {}
    approval = STORE.record_release_approval(
        {
            "model_id": str(decision.get("model")),
            "recommendation": str(decision.get("recommendation")),
            "status": request.status,
            "decision": decision,
        }
    )
    STORE.record_audit_event(actor="api", action="release.approval", target=approval["model_id"], detail={"status": request.status})
    return {"approval": approval, "contract": validation.to_dict()}


@app.get("/api/deployments/rollouts")
def list_deployment_rollouts(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"rollouts": STORE.list_deployment_rollouts(limit)}


@app.post("/api/deployments/rollouts", dependencies=[Depends(require_auth)])
def create_deployment_rollout(request: DeploymentRolloutRequest) -> dict[str, Any]:
    rollout = STORE.upsert_deployment_rollout(request.model_dump())
    STORE.record_audit_event(
        actor="api",
        action="deployment.rollout",
        target=request.model_id,
        detail={"environment": request.environment, "traffic_percent": request.traffic_percent},
    )
    return {"rollout": rollout}


@app.get("/api/templates")
def templates() -> dict[str, Any]:
    return {
        "model_card": "configs/export/model-card.template.yml",
        "dataset": "configs/datasets/example_dataset.yml",
        "experiment": "configs/experiments/detection_yolo_baseline.yml",
        "labeling_guideline": "labeling/guidelines/detection_template.md",
        "quality_rules": "labeling/quality_rules/default_detection.yml",
        "release_decision": "configs/export/release-decision.template.yml",
        "detection_pipeline": "configs/experiments/detection_yolo_baseline.yml",
        "reid_pipeline": "configs/experiments/reid_baseline.yml",
        "classification_pipeline": "configs/experiments/classification_baseline.yml",
        "segmentation_pipeline": "configs/experiments/segmentation_baseline.yml",
    }


@app.get("/{path:path}", include_in_schema=False)
def frontend_fallback(path: str) -> FileResponse:
    if SETTINGS.serve_frontend:
        requested = _safe_frontend_file(path)
        if requested is not None:
            return FileResponse(requested)
        index_file = _safe_frontend_file("index.html")
        if index_file is not None:
            return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build is not available")