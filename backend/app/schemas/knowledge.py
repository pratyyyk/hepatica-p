from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import FibrosisStage


class KnowledgeExplainRequest(BaseModel):
    patient_id: str
    fibrosis_stage: FibrosisStage | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class Citation(BaseModel):
    source_doc: str
    page_number: int


class KnowledgeBlock(BaseModel):
    title: str
    content: str
    citations: list[Citation]


class KnowledgeExplainResponse(BaseModel):
    patient_id: str
    blocks: list[KnowledgeBlock]
