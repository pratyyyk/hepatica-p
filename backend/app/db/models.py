from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConfidenceFlag, EscalationFlag, FibrosisStage, RiskTier
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EmbeddingVector


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="DOCTOR", nullable=False)


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
