"""initial schema"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_col() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        _uuid_col(),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "patients",
        _uuid_col(),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("sex", sa.String(length=16), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("bmi", sa.Float(), nullable=True),
        sa.Column("type2dm", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_patients_external_id"),
    )

    op.create_table(
        "model_registry",
        _uuid_col(),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("artifact_uri", sa.String(length=512), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_model_name_version"),
    )

    op.create_table(
        "clinical_assessments",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("performed_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ast", sa.Float(), nullable=False),
        sa.Column("alt", sa.Float(), nullable=False),
        sa.Column("platelets", sa.Float(), nullable=False),
        sa.Column("ast_uln", sa.Float(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("bmi", sa.Float(), nullable=False),
        sa.Column("type2dm", sa.Boolean(), nullable=False),
        sa.Column("fib4", sa.Float(), nullable=False),
        sa.Column("apri", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "scan_assets",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    vector_col = sa.JSON()
    if bind.dialect.name == "postgresql":
        try:
            from pgvector.sqlalchemy import Vector

            vector_col = Vector(1536)
        except Exception:
            vector_col = postgresql.ARRAY(postgresql.DOUBLE_PRECISION)

    op.create_table(
        "knowledge_chunks",
        _uuid_col(),
        sa.Column("source_doc", sa.String(length=512), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", vector_col, nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_doc", "page_number", "chunk_index", name="uq_doc_page_chunk"),
    )

    op.create_table(
        "fibrosis_predictions",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("scan_asset_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("scan_assets.id"), nullable=False),
        sa.Column("performed_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("softmax_vector", sa.JSON(), nullable=False),
        sa.Column("top1_stage", sa.String(length=8), nullable=False),
        sa.Column("top1_probability", sa.Float(), nullable=False),
        sa.Column("top2", sa.JSON(), nullable=False),
        sa.Column("confidence_flag", sa.String(length=32), nullable=False),
        sa.Column("escalation_flag", sa.String(length=32), nullable=False),
        sa.Column("quality_metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reports",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "clinical_assessment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("clinical_assessments.id"), nullable=True
        ),
        sa.Column(
            "fibrosis_prediction_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("fibrosis_predictions.id"), nullable=True
        ),
        sa.Column("pdf_object_key", sa.String(length=512), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "timeline_events",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        _uuid_col(),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("timeline_events")
    op.drop_table("reports")
    op.drop_table("fibrosis_predictions")
    op.drop_table("knowledge_chunks")
    op.drop_table("scan_assets")
    op.drop_table("clinical_assessments")
    op.drop_table("model_registry")
    op.drop_table("patients")
    op.drop_table("users")
