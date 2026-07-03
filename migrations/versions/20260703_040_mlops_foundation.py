from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260703_040"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_job_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("stream", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_pipeline_job_logs_job_id", "pipeline_job_logs", ["job_id"])
    op.create_table(
        "pipeline_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_pipeline_artifacts_job_id", "pipeline_artifacts", ["job_id"])
    op.create_index("idx_pipeline_artifacts_run_id", "pipeline_artifacts", ["run_id"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=False),
        sa.Column("split_counts_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("labels_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="registered"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_id", sa.Text(), nullable=False, unique=True),
        sa.Column("package_dir", sa.Text(), nullable=False),
        sa.Column("artifact_name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("stage", sa.Text(), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_model_registry_stage", "model_registry", ["stage"])
    op.create_table(
        "release_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decision_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_release_approvals_model_id", "release_approvals", ["model_id"])
    op.create_table(
        "deployment_rollouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("traffic_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rollback_target", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_deployment_rollouts_model_id", "deployment_rollouts", ["model_id"])


def downgrade() -> None:
    op.drop_index("idx_deployment_rollouts_model_id", table_name="deployment_rollouts")
    op.drop_table("deployment_rollouts")
    op.drop_index("idx_release_approvals_model_id", table_name="release_approvals")
    op.drop_table("release_approvals")
    op.drop_index("idx_model_registry_stage", table_name="model_registry")
    op.drop_table("model_registry")
    op.drop_table("dataset_versions")
    op.drop_index("idx_pipeline_artifacts_run_id", table_name="pipeline_artifacts")
    op.drop_index("idx_pipeline_artifacts_job_id", table_name="pipeline_artifacts")
    op.drop_table("pipeline_artifacts")
    op.drop_index("idx_pipeline_job_logs_job_id", table_name="pipeline_job_logs")
    op.drop_table("pipeline_job_logs")
