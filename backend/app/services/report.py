from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import Settings

DISCLAIMER = (
    "This report is decision-support only. It does not replace clinician judgment, definitive diagnosis, "
    "or local guideline requirements."
)


def build_report_payload(
    *,
    patient: dict,
    clinical: dict | None,
    fibrosis: dict | None,
    knowledge_blocks: list[dict],
) -> dict:
    return {
        "patient": patient,
        "clinical_assessment": clinical,
        "fibrosis_prediction": fibrosis,
        "knowledge": knowledge_blocks,
        "disclaimer": DISCLAIMER,
        "versioning": {
            "clinical_model": (clinical or {}).get("model_version"),
            "fibrosis_model": (fibrosis or {}).get("model_version"),
        },
    }


def render_pdf(report_payload: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40

    def draw_line(text: str, indent: int = 0):
        nonlocal y
        if y < 70:
            c.showPage()
            y = height - 40
        c.drawString(40 + indent, y, text[:140])
        y -= 16

    draw_line("Hepatica Patient Report")
    draw_line(f"Patient External ID: {report_payload['patient'].get('external_id', 'N/A')}")
    draw_line("")

    clinical = report_payload.get("clinical_assessment")
    if clinical:
        draw_line("Stage 1 - Clinical Risk")
        draw_line(f"Risk Tier: {clinical.get('risk_tier')}", 20)
        draw_line(f"Probability: {clinical.get('probability')}", 20)
        draw_line(f"FIB-4: {clinical.get('fib4')} | APRI: {clinical.get('apri')}", 20)

    fibrosis = report_payload.get("fibrosis_prediction")
    if fibrosis:
        draw_line("")
        draw_line("Stage 2 - Fibrosis Prediction")
        draw_line(f"Top Stage: {fibrosis.get('top1_stage')}", 20)
        draw_line(f"Top Probability: {fibrosis.get('top1_probability')}", 20)
        draw_line(f"Confidence Flag: {fibrosis.get('confidence_flag')}", 20)
        draw_line(f"Escalation Flag: {fibrosis.get('escalation_flag')}", 20)

    draw_line("")
    draw_line("Knowledge Summary")
    for block in report_payload.get("knowledge", []):
        draw_line(f"- {block.get('title')}", 20)
        draw_line(block.get("content", "")[:120], 40)

    draw_line("")
    draw_line("Disclaimer")
    draw_line(report_payload["disclaimer"])
    c.save()
    buffer.seek(0)
    return buffer.read()


def upload_pdf(*, report_id: str, pdf_bytes: bytes, settings: Settings) -> str:
    key = f"reports/{report_id}-{uuid4().hex}.pdf"
    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        s3.put_object(
            Bucket=settings.s3_report_bucket,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        return key
    except (BotoCoreError, ClientError):
        local_path = f"/tmp/{report_id}.pdf"
        with open(local_path, "wb") as f:
            f.write(pdf_bytes)
        return local_path


def build_download_url(*, object_key: str, settings: Settings) -> str:
    if object_key.startswith("/tmp/"):
        return object_key
    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.s3_report_bucket, "Key": object_key},
            ExpiresIn=3600,
        )
    except (BotoCoreError, ClientError):
        return f"s3://{settings.s3_report_bucket}/{object_key}"
