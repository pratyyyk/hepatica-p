from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import ScanAsset
from app.db.session import get_db
from app.schemas.assessment import UploadUrlRequest, UploadUrlResponse
from app.services.audit import write_audit_log
from app.services.timeline import append_timeline_event
from app.services.upload import ALLOWED_CONTENT_TYPES, generate_presigned_upload, sanitize_filename

router = APIRouter(prefix="/scans", tags=["scans"])
settings = get_settings()


def _infer_extension(*, filename: str, content_type: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext:
        return ext
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "application/dicom": ".dcm",
        "application/dicom+json": ".dcm",
    }
    return mapping.get(content_type, ".bin")


def _build_absolute_url(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}{path}"


@router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_upload_url(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    try:
        parsed_payload = UploadUrlRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, parsed_payload.patient_id, req_user.db_user.id)

    if parsed_payload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported content type")
    if parsed_payload.byte_size > cfg.max_upload_bytes:
        raise HTTPException(status_code=422, detail="File exceeds max upload size")

    scan = ScanAsset(
        patient_id=parsed_payload.patient_id,
        uploaded_by=req_user.db_user.id,
        object_key="pending",
        content_type=parsed_payload.content_type,
        byte_size=parsed_payload.byte_size,
        status="PENDING_UPLOAD",
    )
    db.add(scan)
    db.flush()

    resolved_mode = cfg.resolved_upload_mode
    upload_url: str
    object_key: str
    expires_in_seconds = cfg.presigned_expiration_seconds

    if resolved_mode == "local":
        safe_name = sanitize_filename(parsed_payload.filename)
        ext = _infer_extension(filename=safe_name, content_type=parsed_payload.content_type)
        cfg.local_upload_dir.mkdir(parents=True, exist_ok=True)
        target = (cfg.local_upload_dir / f"{scan.id}{ext}").resolve()
        object_key = str(target)
        upload_url = _build_absolute_url(request, f"/api/v1/scans/upload/{scan.id}")
    else:
        try:
            ticket = generate_presigned_upload(
                patient_id=parsed_payload.patient_id,
                filename=parsed_payload.filename,
                content_type=parsed_payload.content_type,
                byte_size=parsed_payload.byte_size,
                settings=cfg,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if ticket.upload_url.startswith("https://local-upload.invalid/"):
            safe_name = sanitize_filename(parsed_payload.filename)
            ext = _infer_extension(filename=safe_name, content_type=parsed_payload.content_type)
            cfg.local_upload_dir.mkdir(parents=True, exist_ok=True)
            target = (cfg.local_upload_dir / f"{scan.id}{ext}").resolve()
            object_key = str(target)
            upload_url = _build_absolute_url(request, f"/api/v1/scans/upload/{scan.id}")
            resolved_mode = "local"
        else:
            object_key = ticket.object_key
            upload_url = ticket.upload_url
            expires_in_seconds = ticket.expires_in_seconds

    scan.object_key = object_key

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="SCAN_UPLOAD_URL_CREATED",
        resource_type="scan_asset",
        resource_id=scan.id,
        metadata={"object_key": scan.object_key, "mode": resolved_mode},
    )

    db.commit()

    return UploadUrlResponse(
        scan_asset_id=scan.id,
        object_key=scan.object_key,
        upload_url=upload_url,
        expires_in_seconds=expires_in_seconds,
    )


@router.put("/upload/{scan_asset_id}")
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
async def upload_scan_bytes(
    request: Request,
    response: Response,
    scan_asset_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    scan = db.get(ScanAsset, scan_asset_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan asset not found")

    assert_patient_owned_by_user(db, scan.patient_id, req_user.db_user.id)

    if scan.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported content type")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared > cfg.max_upload_bytes:
            raise HTTPException(status_code=413, detail="File exceeds max upload size")

    raw = await request.body()
    if len(raw) > cfg.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds max upload size")

    target = Path(scan.object_key).expanduser().resolve()
    base = cfg.local_upload_dir.resolve()
    if not target.is_absolute() or not target.is_relative_to(base):
        raise HTTPException(status_code=422, detail="Invalid local upload target")

    base.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

    scan.byte_size = len(raw)
    scan.status = "UPLOADED"

    append_timeline_event(
        db,
        patient_id=scan.patient_id,
        event_type="SCAN_UPLOADED",
        event_payload={"scan_asset_id": scan.id, "content_type": scan.content_type},
        created_by=req_user.db_user.id,
    )
    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="SCAN_UPLOADED",
        resource_type="scan_asset",
        resource_id=scan.id,
        metadata={"object_key": scan.object_key, "byte_size": scan.byte_size},
    )
    db.commit()

    return {"ok": True}
