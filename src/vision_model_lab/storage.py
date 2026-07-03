from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = "20260703_040_mlops_foundation"


class MetadataStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = path
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._reset_empty_database_files()
        self.initialize()

    def initialize(self) -> None:
        connection = self._shared_connection if str(self.path) == ":memory:" else None
        if connection is not None:
            self._initialize_connection(connection)
            return
        try:
            with self.connect() as connection:
                self._initialize_connection(connection)
        except sqlite3.DatabaseError:
            if not self._reset_empty_database_files():
                raise
            with self.connect() as connection:
                self._initialize_connection(connection)

    def _initialize_connection(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                dataset TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                package TEXT,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS package_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package_dir TEXT NOT NULL,
                model_file TEXT,
                ok INTEGER NOT NULL,
                sha256 TEXT,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                cancelled_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                stream TEXT NOT NULL,
                message TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                run_id INTEGER,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT,
                uri TEXT,
                size INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                task TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                split_counts_json TEXT NOT NULL DEFAULT '{}',
                labels_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'registered',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL UNIQUE,
                package_dir TEXT NOT NULL,
                artifact_name TEXT NOT NULL,
                version TEXT NOT NULL,
                task TEXT NOT NULL,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                stage TEXT NOT NULL DEFAULT 'candidate',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS release_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                status TEXT NOT NULL,
                decision_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS deployment_rollouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                environment TEXT NOT NULL,
                strategy TEXT NOT NULL,
                status TEXT NOT NULL,
                traffic_percent INTEGER NOT NULL DEFAULT 0,
                rollback_target TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON pipeline_jobs(status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_job_logs_job_id ON pipeline_job_logs(job_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_job_id ON pipeline_artifacts(job_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_run_id ON pipeline_artifacts(run_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_model_registry_stage ON model_registry(stage)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_release_approvals_model_id ON release_approvals(model_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_deployment_rollouts_model_id ON deployment_rollouts(model_id)")
        connection.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)", (SCHEMA_VERSION,))

    def _configure_connection(self, connection: sqlite3.Connection, *, in_memory: bool, use_wal: bool = True) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        if in_memory:
            self._configure_journal_mode(connection, ("MEMORY",))
        elif use_wal:
            self._configure_journal_mode(connection, ("MEMORY", "WAL", "DELETE", "OFF"))
        else:
            self._configure_journal_mode(connection, ("MEMORY", "DELETE", "OFF"))
        try:
            connection.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass

    def _configure_journal_mode(self, connection: sqlite3.Connection, modes: tuple[str, ...]) -> None:
        for mode in modes:
            try:
                connection.execute(f"PRAGMA journal_mode={mode}").fetchone()
                return
            except sqlite3.DatabaseError:
                continue

    def _database_family(self, path: Path) -> list[Path]:
        return [Path(str(path) + suffix) for suffix in ("", "-wal", "-shm", "-journal")]

    def _reset_empty_database_files(self) -> bool:
        if str(self.path) == ":memory:" or not isinstance(self.path, Path):
            return False
        try:
            is_empty = self.path.exists() and self.path.stat().st_size == 0
        except OSError:
            return False
        if not is_empty:
            return False
        targets = self._database_family(self.path)
        removed_any = False
        for target in targets:
            if not target.exists():
                continue
            try:
                target.unlink()
                removed_any = True
            except OSError:
                return False
        return removed_any and all(not target.exists() for target in targets)

    @property
    def _shared_connection(self) -> sqlite3.Connection | None:
        if str(self.path) != ":memory:":
            return None
        connection = getattr(self, "_memory_connection", None)
        if connection is None:
            connection = sqlite3.connect(":memory:", check_same_thread=False, timeout=30.0)
            self._configure_connection(connection, in_memory=True)
            self._memory_connection = connection
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            shared = self._shared_connection
            if shared is not None:
                yield shared
                shared.commit()
                return
            connection = sqlite3.connect(self.path, timeout=30.0)
            try:
                self._configure_connection(connection, in_memory=False, use_wal=True)
            except sqlite3.DatabaseError:
                connection.close()
                if not self._reset_empty_database_files():
                    raise
                connection = sqlite3.connect(self.path, timeout=30.0)
                self._configure_connection(connection, in_memory=False, use_wal=False)
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def upsert_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("metrics") or {}
        record = {
            "id": payload["id"],
            "task": payload["task"],
            "dataset": payload["dataset"],
            "model": payload["model"],
            "status": payload.get("status", "planned"),
            "package": payload.get("package"),
            "metrics_json": json.dumps(metrics, ensure_ascii=False),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO experiments (id, task, dataset, model, status, package, metrics_json)
                VALUES (:id, :task, :dataset, :model, :status, :package, :metrics_json)
                ON CONFLICT(id) DO UPDATE SET
                    task=excluded.task,
                    dataset=excluded.dataset,
                    model=excluded.model,
                    status=excluded.status,
                    package=excluded.package,
                    metrics_json=excluded.metrics_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                record,
            )
        return self.get_experiment(payload["id"])

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return self._experiment_row(row)

    def list_experiments(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM experiments ORDER BY created_at DESC").fetchall()
        return [self._experiment_row(row) for row in rows]

    def record_package_validation(self, report: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO package_validations (package_dir, model_file, ok, sha256, report_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.get("package_dir"),
                    report.get("model_file"),
                    1 if report.get("ok") else 0,
                    report.get("sha256"),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            validation_id = int(cursor.lastrowid)
        return self.get_package_validation(validation_id)

    def list_package_validations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM package_validations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._package_validation_row(row) for row in rows]

    def record_pipeline_run(self, config_path: str, report: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs (config_path, status, report_json)
                VALUES (?, ?, ?)
                """,
                (
                    config_path,
                    str(report.get("status", "unknown")),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get_pipeline_run(run_id)

    def list_pipeline_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._pipeline_run_row(row) for row in rows]

    def get_pipeline_run(self, run_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return self._pipeline_run_row(row)

    def create_pipeline_job(self, config_path: str, request: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_jobs (config_path, status, request_json)
                VALUES (?, 'queued', ?)
                """,
                (config_path, json.dumps(request, ensure_ascii=False)),
            )
            job_id = int(cursor.lastrowid)
        return self.get_pipeline_job(job_id)

    def mark_pipeline_job_running(self, job_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_jobs
                SET status='running', started_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (job_id,),
            )
        return self.get_pipeline_job(job_id)

    def complete_pipeline_job(self, job_id: int, result: dict[str, Any], *, status: str = "completed") -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_jobs
                SET status=?, result_json=?, completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, json.dumps(result, ensure_ascii=False), job_id),
            )
        return self.get_pipeline_job(job_id)

    def fail_pipeline_job(self, job_id: int, error: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_jobs
                SET status='failed', error=?, result_json=?, completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error, json.dumps(result, ensure_ascii=False) if result is not None else None, job_id),
            )
        return self.get_pipeline_job(job_id)

    def request_pipeline_job_cancel(self, job_id: int) -> dict[str, Any]:
        job = self.get_pipeline_job(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        next_status = "cancelled" if job["status"] == "queued" else "cancellation_requested"
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_jobs
                SET status=?, cancelled_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (next_status, job_id),
            )
        return self.get_pipeline_job(job_id)

    def list_pipeline_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pipeline_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._pipeline_job_row(row) for row in rows]

    def get_pipeline_job(self, job_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM pipeline_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(str(job_id))
        return self._pipeline_job_row(row)

    def record_pipeline_job_log(
        self,
        job_id: int,
        stream: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_job_logs (job_id, stream, message, detail_json)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, stream, message, json.dumps(detail or {}, ensure_ascii=False)),
            )
            log_id = int(cursor.lastrowid)
        return self.get_pipeline_job_log(log_id)

    def list_pipeline_job_logs(self, job_id: int, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pipeline_job_logs
                WHERE job_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [self._pipeline_job_log_row(row) for row in rows]

    def get_pipeline_job_log(self, log_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM pipeline_job_logs WHERE id = ?", (log_id,)).fetchone()
        if row is None:
            raise KeyError(str(log_id))
        return self._pipeline_job_log_row(row)

    def record_pipeline_artifact(
        self,
        *,
        name: str,
        kind: str,
        job_id: int | None = None,
        run_id: int | None = None,
        path: str | None = None,
        uri: str | None = None,
        size: int | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_artifacts (job_id, run_id, name, kind, path, uri, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, run_id, name, kind, path, uri, size),
            )
            artifact_id = int(cursor.lastrowid)
        return self.get_pipeline_artifact(artifact_id)

    def list_pipeline_artifacts(
        self,
        *,
        job_id: int | None = None,
        run_id: int | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if job_id is None and run_id is None:
            with self.connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM pipeline_artifacts ORDER BY created_at DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._pipeline_artifact_row(row) for row in rows]
        field = "job_id" if job_id is not None else "run_id"
        value = job_id if job_id is not None else run_id
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM pipeline_artifacts WHERE {field} = ? ORDER BY id ASC LIMIT ?",
                (value, limit),
            ).fetchall()
        return [self._pipeline_artifact_row(row) for row in rows]

    def get_pipeline_artifact(self, artifact_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM pipeline_artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise KeyError(str(artifact_id))
        return self._pipeline_artifact_row(row)

    def record_audit_event(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = detail or {}
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_events (actor, action, target, detail_json)
                VALUES (?, ?, ?, ?)
                """,
                (actor, action, target, json.dumps(payload, ensure_ascii=False)),
            )
            event_id = int(cursor.lastrowid)
        return self.get_audit_event(event_id)

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._audit_event_row(row) for row in rows]

    def upsert_dataset_version(self, payload: dict[str, Any]) -> dict[str, Any]:
        labels = payload.get("labels") or []
        split_counts = payload.get("split_counts") or {}
        record = {
            "dataset_id": payload["dataset_id"],
            "name": payload["name"],
            "version": payload["version"],
            "task": payload["task"],
            "manifest_path": payload["manifest_path"],
            "split_counts_json": json.dumps(split_counts, ensure_ascii=False),
            "labels_json": json.dumps(labels, ensure_ascii=False),
            "status": payload.get("status", "registered"),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO dataset_versions
                    (dataset_id, name, version, task, manifest_path, split_counts_json, labels_json, status)
                VALUES
                    (:dataset_id, :name, :version, :task, :manifest_path, :split_counts_json, :labels_json, :status)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    task=excluded.task,
                    manifest_path=excluded.manifest_path,
                    split_counts_json=excluded.split_counts_json,
                    labels_json=excluded.labels_json,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                record,
            )
        return self.get_dataset_version(payload["dataset_id"])

    def get_dataset_version(self, dataset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM dataset_versions WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise KeyError(dataset_id)
        return self._dataset_version_row(row)

    def list_dataset_versions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM dataset_versions ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._dataset_version_row(row) for row in rows]

    def upsert_model_registry_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("metrics") or {}
        record = {
            "model_id": payload["model_id"],
            "package_dir": payload["package_dir"],
            "artifact_name": payload["artifact_name"],
            "version": payload["version"],
            "task": payload["task"],
            "metrics_json": json.dumps(metrics, ensure_ascii=False),
            "stage": payload.get("stage", "candidate"),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO model_registry
                    (model_id, package_dir, artifact_name, version, task, metrics_json, stage)
                VALUES
                    (:model_id, :package_dir, :artifact_name, :version, :task, :metrics_json, :stage)
                ON CONFLICT(model_id) DO UPDATE SET
                    package_dir=excluded.package_dir,
                    artifact_name=excluded.artifact_name,
                    version=excluded.version,
                    task=excluded.task,
                    metrics_json=excluded.metrics_json,
                    stage=excluded.stage,
                    updated_at=CURRENT_TIMESTAMP
                """,
                record,
            )
        return self.get_model_registry_entry(payload["model_id"])

    def get_model_registry_entry(self, model_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM model_registry WHERE model_id = ?", (model_id,)).fetchone()
        if row is None:
            raise KeyError(model_id)
        return self._model_registry_row(row)

    def list_model_registry_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM model_registry ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._model_registry_row(row) for row in rows]

    def record_release_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO release_approvals (model_id, recommendation, status, decision_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    payload["model_id"],
                    payload["recommendation"],
                    payload.get("status", "pending"),
                    json.dumps(payload.get("decision", {}), ensure_ascii=False),
                ),
            )
            approval_id = int(cursor.lastrowid)
        return self.get_release_approval(approval_id)

    def get_release_approval(self, approval_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM release_approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(str(approval_id))
        return self._release_approval_row(row)

    def list_release_approvals(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM release_approvals ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._release_approval_row(row) for row in rows]

    def upsert_deployment_rollout(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO deployment_rollouts
                    (model_id, environment, strategy, status, traffic_percent, rollback_target)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["model_id"],
                    payload.get("environment", "production"),
                    payload.get("strategy", "gray"),
                    payload.get("status", "planned"),
                    int(payload.get("traffic_percent", 0)),
                    payload.get("rollback_target"),
                ),
            )
            rollout_id = int(cursor.lastrowid)
        return self.get_deployment_rollout(rollout_id)

    def get_deployment_rollout(self, rollout_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM deployment_rollouts WHERE id = ?", (rollout_id,)).fetchone()
        if row is None:
            raise KeyError(str(rollout_id))
        return self._deployment_rollout_row(row)

    def list_deployment_rollouts(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM deployment_rollouts ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._deployment_rollout_row(row) for row in rows]

    def get_audit_event(self, event_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(str(event_id))
        return self._audit_event_row(row)

    def get_package_validation(self, validation_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM package_validations WHERE id = ?", (validation_id,)).fetchone()
        if row is None:
            raise KeyError(str(validation_id))
        return self._package_validation_row(row)

    @staticmethod
    def _experiment_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metrics"] = json.loads(record.pop("metrics_json") or "{}")
        return record

    @staticmethod
    def _package_validation_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["ok"] = bool(record["ok"])
        record["report"] = json.loads(record.pop("report_json") or "{}")
        return record

    @staticmethod
    def _pipeline_run_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["report"] = json.loads(record.pop("report_json") or "{}")
        return record

    @staticmethod
    def _pipeline_job_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["request"] = json.loads(record.pop("request_json") or "{}")
        result_json = record.pop("result_json")
        record["result"] = json.loads(result_json) if result_json else None
        return record

    @staticmethod
    def _pipeline_job_log_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["detail"] = json.loads(record.pop("detail_json") or "{}")
        return record

    @staticmethod
    def _pipeline_artifact_row(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _audit_event_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["detail"] = json.loads(record.pop("detail_json") or "{}")
        return record

    @staticmethod
    def _dataset_version_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["split_counts"] = json.loads(record.pop("split_counts_json") or "{}")
        record["labels"] = json.loads(record.pop("labels_json") or "[]")
        return record

    @staticmethod
    def _model_registry_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metrics"] = json.loads(record.pop("metrics_json") or "{}")
        return record

    @staticmethod
    def _release_approval_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["decision"] = json.loads(record.pop("decision_json") or "{}")
        return record

    @staticmethod
    def _deployment_rollout_row(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)


class _PostgresCursorAdapter:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor
        self._lastrowid: int | None = None
        self._lastrowid_loaded = False

    @property
    def lastrowid(self) -> int | None:
        if not self._lastrowid_loaded:
            self._lastrowid_loaded = True
            if self.cursor.description:
                row = self.cursor.fetchone()
                if row:
                    self._lastrowid = int(row["id"] if isinstance(row, dict) else row[0])
        return self._lastrowid

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()


class _PostgresConnectionAdapter:
    _returning_tables = {
        "package_validations",
        "pipeline_runs",
        "pipeline_jobs",
        "audit_events",
        "pipeline_job_logs",
        "pipeline_artifacts",
        "release_approvals",
        "deployment_rollouts",
    }

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, sql: str, params: Any = None) -> _PostgresCursorAdapter:
        prepared = self._prepare_sql(sql, params)
        cursor = self.connection.execute(prepared, params or ())
        return _PostgresCursorAdapter(cursor)

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _prepare_sql(self, sql: str, params: Any) -> str:
        prepared = sql
        if isinstance(params, dict):
            for key in params:
                prepared = prepared.replace(f":{key}", f"%({key})s")
        else:
            prepared = prepared.replace("?", "%s")
        stripped = prepared.strip()
        upper = stripped.upper()
        if upper.startswith("INSERT INTO") and "RETURNING" not in upper and "ON CONFLICT" not in upper:
            parts = stripped.split()
            table = parts[2].strip('"') if len(parts) > 2 else ""
            if table in self._returning_tables:
                prepared = prepared.rstrip().rstrip(";") + " RETURNING id"
        return prepared


class PostgresMetadataStore(MetadataStore):
    def __init__(self, dsn: str) -> None:
        self.path = dsn
        self._lock = threading.RLock()
        self.initialize()

    @property
    def _shared_connection(self) -> None:
        return None

    @contextmanager
    def connect(self) -> Iterator[_PostgresConnectionAdapter]:
        with self._lock:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - optional deployment extra
                raise RuntimeError("psycopg is required for PostgreSQL metadata storage; install vision-model-lab[postgres].") from exc
            connection = psycopg.connect(str(self.path), row_factory=dict_row, connect_timeout=10)
            adapter = _PostgresConnectionAdapter(connection)
            try:
                yield adapter
                adapter.commit()
            finally:
                adapter.close()

    def _initialize_connection(self, connection: Any) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                dataset TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                package TEXT,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for table_sql in (
            """
            CREATE TABLE IF NOT EXISTS package_validations (
                id BIGSERIAL PRIMARY KEY,
                package_dir TEXT NOT NULL,
                model_file TEXT,
                ok INTEGER NOT NULL,
                sha256 TEXT,
                report_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id BIGSERIAL PRIMARY KEY,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                id BIGSERIAL PRIMARY KEY,
                config_path TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                cancelled_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id BIGSERIAL PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pipeline_job_logs (
                id BIGSERIAL PRIMARY KEY,
                job_id BIGINT NOT NULL,
                stream TEXT NOT NULL,
                message TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pipeline_artifacts (
                id BIGSERIAL PRIMARY KEY,
                job_id BIGINT,
                run_id BIGINT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT,
                uri TEXT,
                size BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id BIGSERIAL PRIMARY KEY,
                dataset_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                task TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                split_counts_json TEXT NOT NULL DEFAULT '{}',
                labels_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'registered',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_registry (
                id BIGSERIAL PRIMARY KEY,
                model_id TEXT NOT NULL UNIQUE,
                package_dir TEXT NOT NULL,
                artifact_name TEXT NOT NULL,
                version TEXT NOT NULL,
                task TEXT NOT NULL,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                stage TEXT NOT NULL DEFAULT 'candidate',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS release_approvals (
                id BIGSERIAL PRIMARY KEY,
                model_id TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                status TEXT NOT NULL,
                decision_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS deployment_rollouts (
                id BIGSERIAL PRIMARY KEY,
                model_id TEXT NOT NULL,
                environment TEXT NOT NULL,
                strategy TEXT NOT NULL,
                status TEXT NOT NULL,
                traffic_percent INTEGER NOT NULL DEFAULT 0,
                rollback_target TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ):
            connection.execute(table_sql)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON pipeline_jobs(status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_job_logs_job_id ON pipeline_job_logs(job_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_job_id ON pipeline_artifacts(job_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_run_id ON pipeline_artifacts(run_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_model_registry_stage ON model_registry(stage)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_release_approvals_model_id ON release_approvals(model_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_deployment_rollouts_model_id ON deployment_rollouts(model_id)")
        connection.execute(
            "INSERT INTO schema_migrations (version) VALUES (?) ON CONFLICT(version) DO NOTHING",
            (SCHEMA_VERSION,),
        )


def metadata_store_from_uri(uri: str | Path = ":memory:") -> MetadataStore:
    value = str(uri)
    if value.startswith(("postgresql://", "postgres://")):
        return PostgresMetadataStore(value)
    return MetadataStore(uri)
