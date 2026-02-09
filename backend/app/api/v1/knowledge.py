from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.session import get_db
from app.schemas.knowledge import KnowledgeExplainRequest, KnowledgeExplainResponse
from app.services.audit import write_audit_log
from app.services.knowledge import retrieve_chunks, synthesize_blocks

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
settings = get_settings()


@router.post("/explain", response_model=KnowledgeExplainResponse)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def explain_prediction(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = KnowledgeExplainRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    query = (
        f"fibrosis stage {parsed_payload.fibrosis_stage.value if parsed_payload.fibrosis_stage else 'unknown'} "
        "patient guidance"
    )
    retrieved = retrieve_chunks(db=db, query=query, settings=cfg, top_k=parsed_payload.top_k)
    blocks = synthesize_blocks(fibrosis_stage=parsed_payload.fibrosis_stage, retrieved=retrieved)

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="KNOWLEDGE_EXPLANATION_GENERATED",
        resource_type="patient",
        resource_id=parsed_payload.patient_id,
        metadata={"chunks": len(retrieved)},
    )
    db.commit()

    return KnowledgeExplainResponse(patient_id=parsed_payload.patient_id, blocks=blocks)
