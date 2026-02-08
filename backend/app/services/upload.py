from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/dicom",
    "application/dicom+json",
}


@dataclass
class UploadTicket:
    object_key: str
    upload_url: str
    expires_in_seconds: int


def sanitize_filename(filename: str) -> str:
    safe = "".join(ch for ch in filename if ch.isalnum() or ch in {"-", "_", "."})
    return safe or f"scan-{uuid4().hex}.bin"


def create_object_key(patient_id: str, filename: str) -> str:
    ext = Path(filename).suffix.lower() or ".bin"
    return f"patients/{patient_id}/scans/{uuid4().hex}{ext}"


def generate_presigned_upload(
    *,
    patient_id: str,
    filename: str,
    content_type: str,
    byte_size: int,
    settings: Settings,
) -> UploadTicket:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Unsupported content type")
    if byte_size > settings.max_upload_bytes:
        raise ValueError("File exceeds max upload size")

    key = create_object_key(patient_id=patient_id, filename=sanitize_filename(filename))
    s3 = boto3.client("s3", region_name=settings.aws_region)

    params = {
        "Bucket": settings.s3_upload_bucket,
        "Key": key,
        "ContentType": content_type,
    }

    try:
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params=params,
            ExpiresIn=settings.presigned_expiration_seconds,
            HttpMethod="PUT",
        )
    except (BotoCoreError, ClientError):
        # Local fallback for environments without AWS credentials.
        url = f"https://local-upload.invalid/{settings.s3_upload_bucket}/{key}"

    return UploadTicket(
        object_key=key,
        upload_url=url,
        expires_in_seconds=settings.presigned_expiration_seconds,
    )
