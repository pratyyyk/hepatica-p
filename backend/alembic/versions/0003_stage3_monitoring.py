"""add stage3 monitoring tables"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_stage3_monitoring"
down_revision: Union[str, None] = "0002_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_col() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "stiffness_measurements",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("entered_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("measured_kpa", sa.Float(), nullable=False),
        sa.Column("cap_dbm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stiffness_measurements_patient_id", "stiffness_measurements", ["patient_id"])
    op.create_index(
        "ix_stiffness_measurements_patient_created_at",
        "stiffness_measurements",
        ["patient_id", "created_at"],
    )

    op.create_table(
        "stage3_assessments",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column(
            "clinical_assessment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("clinical_assessments.id"),
            nullable=True,
        ),
        sa.Column(
            "fibrosis_prediction_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("fibrosis_predictions.id"),
            nullable=True,
        ),
        sa.Column(
            "stiffness_measurement_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("stiffness_measurements.id"),
            nullable=True,
        ),
        sa.Column("performed_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("composite_risk_score", sa.Float(), nullable=False),
        sa.Column("progression_risk_12m", sa.Float(), nullable=False),
        sa.Column("decomp_risk_12m", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("feature_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stage3_assessments_patient_id", "stage3_assessments", ["patient_id"])
    op.create_index(
        "ix_stage3_assessments_patient_created_at",
        "stage3_assessments",
        ["patient_id", "created_at"],
    )

    op.create_table(
        "risk_alerts",
        _uuid_col(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column(
            "stage3_assessment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("stage3_assessments.id"),
            nullable=True,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_alerts_patient_id", "risk_alerts", ["patient_id"])
    op.create_index("ix_risk_alerts_patient_status", "risk_alerts", ["patient_id", "status"])
    op.create_index("ix_risk_alerts_patient_created_at", "risk_alerts", ["patient_id", "created_at"])

    op.create_table(
        "stage3_explanations",
        _uuid_col(),
        sa.Column(
            "stage3_assessment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("stage3_assessments.id"),
            nullable=False,
        ),
        sa.Column("local_feature_contrib_json", sa.JSON(), nullable=False),
        sa.Column("global_reference_version", sa.String(length=128), nullable=False),
        sa.Column("trend_points_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stage3_assessment_id", name="uq_stage3_explanations_assessment_id"),
    )
    op.create_index("ix_stage3_explanations_assessment_id", "stage3_explanations", ["stage3_assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_stage3_explanations_assessment_id", table_name="stage3_explanations")
    op.drop_table("stage3_explanations")

    op.drop_index("ix_risk_alerts_patient_created_at", table_name="risk_alerts")
    op.drop_index("ix_risk_alerts_patient_status", table_name="risk_alerts")
    op.drop_index("ix_risk_alerts_patient_id", table_name="risk_alerts")
    op.drop_table("risk_alerts")

    op.drop_index("ix_stage3_assessments_patient_created_at", table_name="stage3_assessments")
    op.drop_index("ix_stage3_assessments_patient_id", table_name="stage3_assessments")
    op.drop_table("stage3_assessments")

    op.drop_index("ix_stiffness_measurements_patient_created_at", table_name="stiffness_measurements")
    op.drop_index("ix_stiffness_measurements_patient_id", table_name="stiffness_measurements")
    op.drop_table("stiffness_measurements")
