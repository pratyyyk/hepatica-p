from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    def _s(v) -> str:
        return "—" if v is None or v == "" else str(v)

    def _f(v, digits: int = 3) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):.{digits}f}"
        except (TypeError, ValueError):
            return _s(v)

    def _pct(v) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v) * 100:.1f}%"
        except (TypeError, ValueError):
            return _s(v)

    def _bar(prob: float, *, width: float = 70 * mm, height: float = 4.5 * mm) -> Drawing:
        p = max(0.0, min(1.0, float(prob)))
        d = Drawing(width, height)
        d.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#E5E7EB"), strokeColor=None))
        d.add(Rect(0, 0, width * p, height, fillColor=colors.HexColor("#0E7C7B"), strokeColor=None))
        return d

    patient = report_payload.get("patient") or {}
    clinical = report_payload.get("clinical_assessment") or None
    fibrosis = report_payload.get("fibrosis_prediction") or None
    versioning = report_payload.get("versioning") or {}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="Hepatica Patient Report",
        author="Hepatica",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="HepTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0B1320"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="HepSub",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#6B7280"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#0B1320"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#374151"),
        )
    )

    def on_page(c, d):
        w, h = A4
        c.saveState()
        # Header mark.
        c.setFillColor(colors.HexColor("#0E7C7B"))
        c.roundRect(d.leftMargin, h - d.topMargin + 4, 18, 18, 5, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(d.leftMargin + 9, h - d.topMargin + 9.5, "H")

        c.setFillColor(colors.HexColor("#0B1320"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(d.leftMargin + 26, h - d.topMargin + 12, "Hepatica Patient Report")
        c.setFillColor(colors.HexColor("#6B7280"))
        c.setFont("Helvetica", 9)
        c.drawRightString(w - d.rightMargin, h - d.topMargin + 12, f"Generated {generated_at}")

        # Footer.
        c.setFillColor(colors.HexColor("#9CA3AF"))
        c.setFont("Helvetica", 8)
        c.drawRightString(w - d.rightMargin, d.bottomMargin - 10, f"Page {c.getPageNumber()}")
        c.restoreState()

    story: list[object] = []
    story.append(Spacer(1, 10))
    story.append(Paragraph("Clinical risk triage + fibrosis staging", styles["HepSub"]))
    story.append(Spacer(1, 10))

    patient_rows = [
        ["Patient ID", _s(patient.get("external_id"))],
        ["Sex", _s(patient.get("sex"))],
        ["Age", _s(patient.get("age"))],
    ]
    pt = Table(patient_rows, colWidths=[30 * mm, 130 * mm])
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(pt)
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E5E7EB")))

    # Stage 1.
    story.append(Paragraph("Stage 1 - Clinical Risk", styles["H2"]))
    if clinical:
        tier = _s(clinical.get("risk_tier")).upper()
        tier_color = {
            "LOW": "#065F46",
            "MODERATE": "#92400E",
            "HIGH": "#991B1B",
        }.get(tier, "#111827")

        s1_rows = [
            ["Risk Tier", Paragraph(f'<font color="{tier_color}"><b>{tier}</b></font>', styles["Small"])],
            ["Probability", _pct(clinical.get("probability"))],
            ["FIB-4", _f(clinical.get("fib4"), 3)],
            ["APRI", _f(clinical.get("apri"), 3)],
            ["Model", _s(versioning.get("clinical_model") or clinical.get("model_version"))],
        ]
        t = Table(s1_rows, colWidths=[30 * mm, 130 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(t)
    else:
        story.append(Paragraph("No Stage 1 assessment was attached to this report.", styles["Small"]))

    # Stage 2.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Stage 2 - Fibrosis Prediction", styles["H2"]))
    if fibrosis:
        s2_rows = [
            ["Top Stage", _s(fibrosis.get("top1_stage"))],
            ["Top Probability", _pct(fibrosis.get("top1_probability"))],
            ["Confidence", _s(fibrosis.get("confidence_flag"))],
            ["Escalation", _s(fibrosis.get("escalation_flag"))],
            ["Model", _s(versioning.get("fibrosis_model") or fibrosis.get("model_version"))],
        ]
        t = Table(s2_rows, colWidths=[30 * mm, 130 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(t)

        softmax = fibrosis.get("softmax_vector") or {}
        rows = [["Stage", "Probability", ""]]
        stages = ["F0", "F1", "F2", "F3", "F4"]
        top = _s(fibrosis.get("top1_stage"))
        for s in stages:
            p = float(softmax.get(s, 0.0) or 0.0)
            rows.append([s, _pct(p), _bar(p)])
        bars = Table(rows, colWidths=[14 * mm, 28 * mm, 118 * mm])
        style_cmds = [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#111827")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        if top in stages:
            idx = stages.index(top) + 1
            style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#ECFDFD")))
        bars.setStyle(TableStyle(style_cmds))
        story.append(Spacer(1, 8))
        story.append(Paragraph("Stage probabilities (temperature-scaled):", styles["Small"]))
        story.append(Spacer(1, 4))
        story.append(bars)
    else:
        story.append(Paragraph("No Stage 2 prediction was attached to this report.", styles["Small"]))

    # Knowledge.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Knowledge Summary", styles["H2"]))
    blocks = report_payload.get("knowledge") or []
    if not blocks:
        story.append(Paragraph("No knowledge blocks were generated for this report.", styles["Small"]))
    else:
        for block in blocks[:5]:
            title = _s(block.get("title"))
            content = _s(block.get("content"))
            if len(content) > 900:
                content = content[:900].rstrip() + "..."
            story.append(Paragraph(f"<b>{title}</b>", styles["Small"]))
            story.append(Spacer(1, 2))
            story.append(Paragraph(content.replace("\n", "<br/>"), styles["Small"]))
            story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Disclaimer</b>", styles["Small"]))
    story.append(Paragraph(_s(report_payload.get("disclaimer") or DISCLAIMER), styles["Small"]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
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
        settings.local_report_dir.mkdir(parents=True, exist_ok=True)
        local_path = (settings.local_report_dir / f"{report_id}-{uuid4().hex}.pdf").resolve()
        local_path.write_bytes(pdf_bytes)
        return str(local_path)


def build_download_url(*, object_key: str, settings: Settings) -> str:
    if Path(object_key).is_absolute():
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
