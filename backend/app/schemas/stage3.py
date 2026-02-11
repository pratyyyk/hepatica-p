from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import Stage3RiskTier


class Stage3AssessmentCreate(BaseModel):
    patient_id: str
    clinical_assessment_id: str | None = None
    fibrosis_prediction_id: str | None = None
    stiffness_measurement_id: str | None = None


class StiffnessMeasurementCreate(BaseModel):
    measured_kpa: float = Field(gt=0, le=120)
    cap_dbm: float | None = Field(default=None, ge=50, le=500)
    source: Literal["MEASURED", "PROXY_MANUAL"] = "MEASURED"
    measured_at: datetime | None = None


class StiffnessMeasurementRead(BaseModel):
    id: str
    patient_id: str
    measured_kpa: float
    cap_dbm: float | None
    source: str
    measured_at: datetime
    created_at: datetime


class Stage3AssessmentRead(BaseModel):
    id: str
    patient_id: str
    clinical_assessment_id: str | None
    fibrosis_prediction_id: str | None
    stiffness_measurement_id: str | None
    composite_risk_score: float
    progression_risk_12m: float
    decomp_risk_12m: float
    risk_tier: Stage3RiskTier
    model_version: str
    feature_snapshot_json: dict
    created_at: datetime


class RiskAlertRead(BaseModel):
    id: str
    patient_id: str
    stage3_assessment_id: str | None
    alert_type: str
    severity: str
    threshold: float
    score: float
    status: str
    resolved_at: datetime | None
    created_at: datetime


class RiskAlertStatusUpdate(BaseModel):
    status: Literal["open", "ack", "closed"]


class Stage3HistoryRead(BaseModel):
    patient_id: str
    assessments: list[Stage3AssessmentRead]


class Stage3AlertListRead(BaseModel):
    patient_id: str
    alerts: list[RiskAlertRead]


class Stage3ExplainabilityRead(BaseModel):
    patient_id: str
    stage3_assessment_id: str
    local_feature_contrib_json: dict
    global_reference_version: str
    trend_points_json: list[dict]
    created_at: datetime
