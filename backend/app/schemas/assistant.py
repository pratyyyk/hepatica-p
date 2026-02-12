from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    patient_id: str | None = None


class AssistantCitation(BaseModel):
    source_doc: str
    page_number: int
    snippet: str


class AssistantPatientSummary(BaseModel):
    external_id: str
    stage1_risk_tier: str | None = None
    stage1_probability: float | None = None
    stage2_top_stage: str | None = None
    stage2_top_probability: float | None = None
    stage3_risk_tier: str | None = None
    stage3_composite_risk: float | None = None
    open_alerts: int = 0


class AssistantChatResponse(BaseModel):
    patient_id: str | None = None
    reply: str
    suggestions: list[str]
    citations: list[AssistantCitation] = Field(default_factory=list)
    patient_summary: AssistantPatientSummary | None = None
