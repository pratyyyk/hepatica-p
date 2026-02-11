from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConfidenceFlag, EscalationFlag, FibrosisStage, RiskTier, Stage3RiskTier
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EmbeddingVector


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="DOCTOR", nullable=False)

    auth_sessions = relationship("AuthSession", back_populates="user")


class AuthSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    id_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_agent_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    user = relationship("User", back_populates="auth_sessions")

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_session_expires_at", "session_expires_at"),
        Index("ix_auth_sessions_revoked_at", "revoked_at"),
    )


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patients"

    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sex: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bmi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    type2dm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    clinical_assessments = relationship("ClinicalAssessment", back_populates="patient")
    scan_assets = relationship("ScanAsset", back_populates="patient")
    fibrosis_predictions = relationship("FibrosisPrediction", back_populates="patient")
    stiffness_measurements = relationship("StiffnessMeasurement", back_populates="patient")
    stage3_assessments = relationship("Stage3Assessment", back_populates="patient")
    risk_alerts = relationship("RiskAlert", back_populates="patient")
    reports = relationship("Report", back_populates="patient")
    timeline_events = relationship("TimelineEvent", back_populates="patient")


class ClinicalAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clinical_assessments"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    performed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    ast: Mapped[float] = mapped_column(Float, nullable=False)
    alt: Mapped[float] = mapped_column(Float, nullable=False)
    platelets: Mapped[float] = mapped_column(Float, nullable=False)
    ast_uln: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    bmi: Mapped[float] = mapped_column(Float, nullable=False)
    type2dm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    fib4: Mapped[float] = mapped_column(Float, nullable=False)
    apri: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), default=RiskTier.LOW.value, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    patient = relationship("Patient", back_populates="clinical_assessments")


class ScanAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scan_assets"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_UPLOAD", nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    patient = relationship("Patient", back_populates="scan_assets")
    predictions = relationship("FibrosisPrediction", back_populates="scan_asset")


class FibrosisPrediction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "fibrosis_predictions"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    scan_asset_id: Mapped[str] = mapped_column(ForeignKey("scan_assets.id"), nullable=False)
    performed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    softmax_vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    top1_stage: Mapped[str] = mapped_column(String(8), default=FibrosisStage.F0.value, nullable=False)
    top1_probability: Mapped[float] = mapped_column(Float, nullable=False)
    top2: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    confidence_flag: Mapped[str] = mapped_column(
        String(32), default=ConfidenceFlag.NORMAL.value, nullable=False
    )
    escalation_flag: Mapped[str] = mapped_column(
        String(32), default=EscalationFlag.NONE.value, nullable=False
    )
    quality_metrics: Mapped[dict] = mapped_column(JSON, nullable=False)

    patient = relationship("Patient", back_populates="fibrosis_predictions")
    scan_asset = relationship("ScanAsset", back_populates="predictions")
    stage3_assessments = relationship("Stage3Assessment", back_populates="fibrosis_prediction")


class StiffnessMeasurement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stiffness_measurements"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    entered_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    measured_kpa: Mapped[float] = mapped_column(Float, nullable=False)
    cap_dbm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="MEASURED", nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    patient = relationship("Patient", back_populates="stiffness_measurements")
    stage3_assessments = relationship("Stage3Assessment", back_populates="stiffness_measurement")

    __table_args__ = (
        Index("ix_stiffness_measurements_patient_id", "patient_id"),
        Index("ix_stiffness_measurements_patient_created_at", "patient_id", "created_at"),
    )


class Stage3Assessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stage3_assessments"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    clinical_assessment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clinical_assessments.id"), nullable=True
    )
    fibrosis_prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("fibrosis_predictions.id"), nullable=True
    )
    stiffness_measurement_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("stiffness_measurements.id"), nullable=True
    )
    performed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    composite_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    progression_risk_12m: Mapped[float] = mapped_column(Float, nullable=False)
    decomp_risk_12m: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), default=Stage3RiskTier.LOW.value, nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    patient = relationship("Patient", back_populates="stage3_assessments")
    fibrosis_prediction = relationship("FibrosisPrediction", back_populates="stage3_assessments")
    stiffness_measurement = relationship("StiffnessMeasurement", back_populates="stage3_assessments")
    explanation = relationship("Stage3Explanation", back_populates="assessment", uselist=False)
    alerts = relationship("RiskAlert", back_populates="assessment")

    __table_args__ = (
        Index("ix_stage3_assessments_patient_id", "patient_id"),
        Index("ix_stage3_assessments_patient_created_at", "patient_id", "created_at"),
    )


class RiskAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "risk_alerts"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    stage3_assessment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("stage3_assessments.id"), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient", back_populates="risk_alerts")
    assessment = relationship("Stage3Assessment", back_populates="alerts")

    __table_args__ = (
        Index("ix_risk_alerts_patient_id", "patient_id"),
        Index("ix_risk_alerts_patient_status", "patient_id", "status"),
        Index("ix_risk_alerts_patient_created_at", "patient_id", "created_at"),
    )


class Stage3Explanation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stage3_explanations"

    stage3_assessment_id: Mapped[str] = mapped_column(ForeignKey("stage3_assessments.id"), nullable=False)
    local_feature_contrib_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    global_reference_version: Mapped[str] = mapped_column(String(128), nullable=False)
    trend_points_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)

    assessment = relationship("Stage3Assessment", back_populates="explanation")

    __table_args__ = (
        UniqueConstraint("stage3_assessment_id", name="uq_stage3_explanations_assessment_id"),
        Index("ix_stage3_explanations_assessment_id", "stage3_assessment_id"),
    )


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    source_doc: Mapped[str] = mapped_column(String(512), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingVector(1536), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_doc", "page_number", "chunk_index", name="uq_doc_page_chunk"),
    )


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reports"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    clinical_assessment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("clinical_assessments.id"), nullable=True
    )
    fibrosis_prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("fibrosis_predictions.id"), nullable=True
    )

    pdf_object_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)

    patient = relationship("Patient", back_populates="reports")


class TimelineEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "timeline_events"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    patient = relationship("Patient", back_populates="timeline_events")


class ModelRegistry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_registry"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
