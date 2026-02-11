from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReportCreate(BaseModel):
    patient_id: str
    clinical_assessment_id: str | None = None
    fibrosis_prediction_id: str | None = None
    stage3_assessment_id: str | None = None


class ReportRead(BaseModel):
    report_id: str
    patient_id: str
    pdf_download_url: str | None
    report_json: dict
    created_at: datetime
