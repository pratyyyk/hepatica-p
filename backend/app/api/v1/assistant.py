from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.session import get_db
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant_chat import generate_assistant_reply
from app.services.audit import write_audit_log

router = APIRouter(prefix="/assistant", tags=["assistant"])
settings = get_settings()


@router.post("/chat", response_model=AssistantChatResponse)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def chat_with_assistant(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = AssistantChatRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    if parsed_payload.patient_id:
        assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    reply, suggestions, citations, summary = generate_assistant_reply(
        db=db,
        message=parsed_payload.message,
        patient_id=parsed_payload.patient_id,
        stage3_enabled=cfg.stage3_enabled,
    )

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="ASSISTANT_CHAT_RESPONSE_GENERATED",
        resource_type="patient" if parsed_payload.patient_id else "assistant",
        resource_id=parsed_payload.patient_id,
        metadata={
            "message_length": len(parsed_payload.message),
            "citations": len(citations),
            "has_patient_context": parsed_payload.patient_id is not None,
        },
    )
    db.commit()

    return AssistantChatResponse(
        patient_id=parsed_payload.patient_id,
        reply=reply,
        suggestions=suggestions,
        citations=citations,
        patient_summary=summary,
    )
