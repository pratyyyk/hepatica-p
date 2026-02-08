from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.core.config import Settings, get_settings
from app.db.models import Patient
from app.db.session import get_db
from app.schemas.knowledge import KnowledgeExplainRequest, KnowledgeExplainResponse
from app.services.audit import write_audit_log
from app.services.knowledge import retrieve_chunks, synthesize_blocks

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/explain", response_model=KnowledgeExplainResponse)
def explain_prediction(
    payload: KnowledgeExplainRequest,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    settings: Settings = Depends(get_settings),
):
    patient = db.get(Patient, payload.patient_id)
    if not patient:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Patient not found")

    query = f"fibrosis stage {payload.fibrosis_stage.value if payload.fibrosis_stage else 'unknown'} patient guidance"
    retrieved = retrieve_chunks(db=db, query=query, settings=settings, top_k=payload.top_k)
    blocks = synthesize_blocks(fibrosis_stage=payload.fibrosis_stage, retrieved=retrieved)

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="KNOWLEDGE_EXPLANATION_GENERATED",
        resource_type="patient",
        resource_id=payload.patient_id,
        metadata={"chunks": len(retrieved)},
    )
    db.commit()

    return KnowledgeExplainResponse(patient_id=payload.patient_id, blocks=blocks)
