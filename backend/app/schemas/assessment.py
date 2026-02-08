from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ConfidenceFlag, EscalationFlag, FibrosisStage, RiskTier


class ClinicalAssessmentCreate(BaseModel):
    patient_id: str
    ast: float = Field(gt=0, le=2000)
    alt: float = Field(gt=0, le=2000)
    platelets: float = Field(gt=0, le=2000)
    ast_uln: float = Field(gt=0, le=500)
    age: int = Field(ge=0, le=120)
    bmi: float = Field(ge=10, le=80)
    type2dm: bool = False


class ClinicalAssessmentRead(BaseModel):
    id: str
    patient_id: str
    fib4: float
    apri: float
    risk_tier: RiskTier
    probability: float
    model_version: str
    created_at: datetime


class UploadUrlRequest(BaseModel):
    patient_id: str
    filename: str = Field(min_length=3, max_length=255)
    content_type: str
    byte_size: int = Field(gt=0)


class UploadUrlResponse(BaseModel):
    scan_asset_id: str
    object_key: str
    upload_url: str
    expires_in_seconds: int


class FibrosisAssessmentCreate(BaseModel):
    patient_id: str
    scan_asset_id: str


class TopPrediction(BaseModel):
    stage: FibrosisStage
    probability: float


class FibrosisAssessmentRead(BaseModel):
    prediction_id: str
    patient_id: str
    scan_asset_id: str
    model_version: str
    softmax_vector: dict[FibrosisStage, float]
    top1: TopPrediction
    top2: list[TopPrediction]
    confidence_flag: ConfidenceFlag
    escalation_flag: EscalationFlag
    quality_metrics: dict
    created_at: datetime
