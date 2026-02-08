from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import ScanAsset
from app.db.session import get_db
from app.schemas.assessment import UploadUrlRequest, UploadUrlResponse
from app.services.audit import write_audit_log
from app.services.upload import generate_presigned_upload

router = APIRouter(prefix="/scans", tags=["scans"])
settings = get_settings()


@router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_upload_url(
    request: Request,
    response: Response,
    payload: UploadUrlRequest,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    assert_patient_owned_by_user(db, payload.patient_id, req_user.db_user.id)

    try:
        ticket = generate_presigned_upload(
            patient_id=payload.patient_id,
            filename=payload.filename,
            content_type=payload.content_type,
            byte_size=payload.byte_size,
            settings=cfg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scan = ScanAsset(
        patient_id=payload.patient_id,
        uploaded_by=req_user.db_user.id,
        object_key=ticket.object_key,
        content_type=payload.content_type,
        byte_size=payload.byte_size,
        status="PENDING_UPLOAD",
    )
    db.add(scan)
    db.flush()

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="SCAN_UPLOAD_URL_CREATED",
        resource_type="scan_asset",
        resource_id=scan.id,
        metadata={"object_key": scan.object_key},
    )

    db.commit()

    return UploadUrlResponse(
        scan_asset_id=scan.id,
        object_key=ticket.object_key,
        upload_url=ticket.upload_url,
        expires_in_seconds=ticket.expires_in_seconds,
    )
