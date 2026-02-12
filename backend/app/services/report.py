from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import Settings

DISCLAIMER = (
    "This report is decision-support only. It does not replace clinician judgment, definitive diagnosis, "
    "or local guideline requirements."
)


def _interpret_stage1(clinical: dict | None) -> str:
    if not clinical:
        return "Stage 1 clinical assessment was not available for this report."
    tier = str(clinical.get("risk_tier", "UNKNOWN")).upper()
    prob = float(clinical.get("probability") or 0.0)
    fib4 = float(clinical.get("fib4") or 0.0)
    apri = float(clinical.get("apri") or 0.0)
    risk_note = {
        "LOW": "low short-term risk; continue protocol-based routine follow-up.",
        "MODERATE": "intermediate risk; consider closer interval reassessment and trend review.",
        "HIGH": "elevated risk; prioritize specialist correlation and management planning.",
    }.get(tier, "risk interpretation requires clinical correlation.")
    return (
        f"Stage 1 non-invasive clinical triage indicates {tier} risk "
        f"(estimated probability {prob * 100:.1f}%). "
        f"FIB-4 is {fib4:.3f} and APRI is {apri:.3f}; this profile is consistent with {risk_note}"
    )


def _interpret_stage2(fibrosis: dict | None) -> str:
    if not fibrosis:
        return "Stage 2 imaging inference was not available for this report."
    top_stage = str(fibrosis.get("top1_stage", "UNKNOWN"))
    top_prob = float(fibrosis.get("top1_probability") or 0.0)
    confidence = str(fibrosis.get("confidence_flag") or "UNKNOWN")
    escalation = str(fibrosis.get("escalation_flag") or "NONE")
    return (
        f"Stage 2 imaging model identifies {top_stage} as the leading fibrosis class "
        f"({top_prob * 100:.1f}%). "
        f"Confidence flag: {confidence}; escalation flag: {escalation}. "
        "Class probabilities across F0-F4 are shown below for transparent interpretation."
    )


def _interpret_stage3(stage3: dict | None) -> str:
    if not stage3:
        return "Stage 3 multimodal monitoring was not available for this report."
    tier = str(stage3.get("risk_tier") or "UNKNOWN")
    comp = float(stage3.get("composite_risk_score") or 0.0)
    prog = float(stage3.get("progression_risk_12m") or 0.0)
    decomp = float(stage3.get("decomp_risk_12m") or 0.0)
    snapshot = stage3.get("feature_snapshot_json") or {}
    stiffness = snapshot.get("stiffness_kpa")
    stiffness_source = snapshot.get("stiffness_source")
    stiffness_part = ""
    if stiffness is not None:
        stiffness_part = f" Liver stiffness input was {stiffness} kPa ({stiffness_source})."
    return (
        f"Stage 3 multimodal monitoring indicates {tier} risk with a composite score of {comp * 100:.1f}%. "
        f"Estimated 12-month progression risk is {prog * 100:.1f}%, and estimated "
        f"12-month decompensation risk is {decomp * 100:.1f}%.{stiffness_part}"
    )


def _build_stage_availability(
    *,
    clinical: dict | None,
    fibrosis: dict | None,
    stage3: dict | None,
    stage3_enabled: bool,
    stage3_failure_reason: str | None,
) -> dict[str, dict[str, str]]:
    stage1 = {
        "status": "AVAILABLE" if clinical else "UNAVAILABLE",
        "reason": "Stage 1 clinical assessment attached."
        if clinical
        else "No Stage 1 clinical assessment linked to this report.",
    }
    stage2 = {
        "status": "AVAILABLE" if fibrosis else "UNAVAILABLE",
        "reason": "Stage 2 fibrosis prediction attached."
        if fibrosis
        else "No Stage 2 fibrosis prediction linked to this report.",
    }

    if stage3:
        stage3_status = {
            "status": "AVAILABLE",
            "reason": "Stage 3 multimodal monitoring assessment attached.",
        }
    elif not stage3_enabled:
        stage3_status = {
            "status": "DISABLED",
            "reason": "Stage 3 feature flag is OFF (set STAGE3_ENABLED=true in backend/.env and restart backend).",
        }
    elif stage3_failure_reason:
        stage3_status = {
            "status": "UNAVAILABLE",
            "reason": stage3_failure_reason,
        }
    else:
        stage3_status = {
            "status": "UNAVAILABLE",
            "reason": "No Stage 3 assessment found for this patient yet.",
        }

    return {"stage1": stage1, "stage2": stage2, "stage3": stage3_status}


def _build_integrated_assessment(
    *,
    clinical: dict | None,
    fibrosis: dict | None,
    stage3: dict | None,
    stage3_alerts: list[dict],
) -> dict:
    stage1_tier = str((clinical or {}).get("risk_tier") or "").upper()
    stage1_prob = float((clinical or {}).get("probability") or 0.0)
    stage2_stage = str((fibrosis or {}).get("top1_stage") or "").upper()
    stage2_prob = float((fibrosis or {}).get("top1_probability") or 0.0)
    stage3_tier = str((stage3 or {}).get("risk_tier") or "").upper()
    stage3_comp = float((stage3 or {}).get("composite_risk_score") or 0.0)
    open_alerts = sum(1 for alert in stage3_alerts if str(alert.get("status") or "").lower() == "open")

    stage1_high = stage1_tier == "HIGH" or stage1_prob >= 0.67
    stage2_advanced = stage2_stage in {"F3", "F4"} and stage2_prob >= 0.45
    stage3_high = stage3_tier in {"HIGH", "CRITICAL"} or stage3_comp >= 0.62
    stage3_critical = stage3_tier == "CRITICAL" or stage3_comp >= 0.82

    key_drivers: list[str] = []
    if stage1_high:
        key_drivers.append(f"Stage 1 high-risk signal ({stage1_tier}, {stage1_prob * 100:.1f}%).")
    if stage2_advanced:
        key_drivers.append(f"Stage 2 advanced fibrosis signal ({stage2_stage}, {stage2_prob * 100:.1f}%).")
    if stage3_high:
        key_drivers.append(f"Stage 3 monitoring signal ({stage3_tier}, {stage3_comp * 100:.1f}%).")
    if open_alerts:
        key_drivers.append(f"{open_alerts} open Stage 3 alert(s).")
    if not key_drivers:
        key_drivers.append("No high-risk triggers detected across available stages.")

    high_signal_count = sum([stage1_high, stage2_advanced, stage3_high])
    if stage3_critical or (stage2_stage == "F4" and stage2_prob >= 0.55):
        overall_posture = "CRITICAL"
    elif high_signal_count >= 2:
        overall_posture = "HIGH"
    elif high_signal_count == 1:
        overall_posture = "ELEVATED"
    else:
        overall_posture = "LOW"

    available_count = sum(1 for stage in (clinical, fibrosis, stage3) if stage is not None)
    if available_count < 2:
        concordance = "Limited cross-stage concordance: fewer than two stages are available."
    elif high_signal_count >= 2:
        concordance = "Cross-stage concordance is strong toward higher risk."
    elif high_signal_count == 0:
        concordance = "Available stage outputs are directionally concordant toward lower risk."
    else:
        concordance = "Mixed cross-stage signals; continue longitudinal monitoring and clinician correlation."

    recommended_actions = [
        "Correlate outputs with clinical exam, history, and local protocol.",
    ]
    if overall_posture in {"HIGH", "CRITICAL"}:
        recommended_actions.append("Prioritize specialist review and short-interval reassessment.")
    elif overall_posture == "ELEVATED":
        recommended_actions.append("Plan closer follow-up and trend review for risk progression.")
    else:
        recommended_actions.append("Continue routine follow-up and monitor for risk drift.")
    if stage3 is not None:
        recommended_actions.append("Maintain scheduled Stage 3 monitoring cadence (every 10 weeks).")
    if open_alerts:
        recommended_actions.append("Review and resolve in-app Stage 3 alerts in the patient timeline.")

    return {
        "overall_posture": overall_posture,
        "concordance_summary": concordance,
        "key_drivers": key_drivers,
        "recommended_actions": recommended_actions,
    }


def build_report_payload(
    *,
    patient: dict,
    clinical: dict | None,
    fibrosis: dict | None,
    stage3: dict | None,
    stage3_explanation: dict | None,
    stage3_alerts: list[dict],
    knowledge_blocks: list[dict],
    scan_preview: dict | None,
    stage3_enabled: bool,
    stage3_failure_reason: str | None = None,
) -> dict:
    stage_availability = _build_stage_availability(
        clinical=clinical,
        fibrosis=fibrosis,
        stage3=stage3,
        stage3_enabled=stage3_enabled,
        stage3_failure_reason=stage3_failure_reason,
    )
    integrated_assessment = _build_integrated_assessment(
        clinical=clinical,
        fibrosis=fibrosis,
        stage3=stage3,
        stage3_alerts=stage3_alerts,
    )
    detailed_analysis = {
        "stage1": _interpret_stage1(clinical),
        "stage2": _interpret_stage2(fibrosis),
        "stage3": _interpret_stage3(stage3),
    }
    executive_summary = {
        "overall_posture": integrated_assessment.get("overall_posture"),
        "stage1_risk_tier": (clinical or {}).get("risk_tier"),
        "stage2_top_stage": (fibrosis or {}).get("top1_stage"),
        "stage3_risk_tier": (stage3 or {}).get("risk_tier"),
        "stage3_composite_risk_score": (stage3 or {}).get("composite_risk_score"),
        "stage3_status": stage_availability["stage3"]["status"],
        "active_alert_count": sum(1 for alert in stage3_alerts if str(alert.get("status") or "").lower() == "open"),
    }
    return {
        "patient": patient,
        "clinical_assessment": clinical,
        "fibrosis_prediction": fibrosis,
        "stage3_assessment": stage3,
        "stage3_explainability": stage3_explanation,
        "stage3_alerts": stage3_alerts,
        "scan_preview": scan_preview or {},
        "stage_availability": stage_availability,
        "executive_summary": executive_summary,
        "integrated_assessment": integrated_assessment,
        "detailed_analysis": detailed_analysis,
        "knowledge": knowledge_blocks,
        "disclaimer": DISCLAIMER,
        "report_meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "monitoring_cadence_weeks": 10,
        },
        "versioning": {
            "clinical_model": (clinical or {}).get("model_version"),
            "fibrosis_model": (fibrosis or {}).get("model_version"),
            "stage3_model": (stage3 or {}).get("model_version"),
        },
    }


def render_pdf(report_payload: dict, *, scan_preview_bytes: bytes | None = None) -> bytes:
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

    def _tier_color(value: str) -> str:
        normalized = value.strip().upper()
        if normalized in {"LOW", "AVAILABLE"}:
            return "#065F46"
        if normalized in {"MODERATE", "ELEVATED"}:
            return "#92400E"
        if normalized in {"HIGH", "UNAVAILABLE", "OPEN"}:
            return "#9A3412"
        if normalized in {"CRITICAL", "DISABLED"}:
            return "#991B1B"
        if normalized in {"ACK"}:
            return "#1D4ED8"
        if normalized in {"CLOSED"}:
            return "#065F46"
        return "#1F2937"

    def _stage_color(value: str) -> str:
        normalized = value.strip().upper()
        if normalized in {"F0", "F1"}:
            return "#065F46"
        if normalized == "F2":
            return "#92400E"
        if normalized in {"F3", "F4"}:
            return "#991B1B"
        return "#1F2937"

    def _pill(value: str, *, color_hex: str) -> Paragraph:
        return Paragraph(f'<font color="{color_hex}"><b>{_s(value)}</b></font>', styles["Small"])

    def _callout(text: str, *, tone: str = "neutral", col_width: float = 165 * mm) -> Table:
        palette = {
            "neutral": ("#F8FAFC", "#D8E1EB"),
            "warn": ("#FFFBEB", "#F3C98B"),
            "danger": ("#FEF2F2", "#F2B8B5"),
            "ok": ("#ECFDF5", "#97E2BF"),
        }
        bg, border = palette.get(tone, palette["neutral"])
        table = Table([[Paragraph(_s(text), styles["Small"])]], colWidths=[col_width])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(border)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    def _scan_image_flowable(image_bytes: bytes) -> tuple[RLImage, str] | None:
        try:
            with PILImage.open(BytesIO(image_bytes)) as pil_image:
                src_w, src_h = pil_image.size
                max_w = 120 * mm
                max_h = 85 * mm
                scale = min(max_w / max(src_w, 1), max_h / max(src_h, 1))
                render_w = max(48 * mm, src_w * scale)
                render_h = max(36 * mm, src_h * scale)

                normalized = pil_image.convert("RGB")
                image_buffer = BytesIO()
                normalized.save(image_buffer, format="JPEG", quality=88, optimize=True)
                image_buffer.seek(0)

            flowable = RLImage(image_buffer, width=render_w, height=render_h)
            flowable.hAlign = "CENTER"
            return flowable, f"{src_w} x {src_h} px"
        except (UnidentifiedImageError, OSError, ValueError):
            return None

    patient = report_payload.get("patient") or {}
    clinical = report_payload.get("clinical_assessment") or None
    fibrosis = report_payload.get("fibrosis_prediction") or None
    stage3 = report_payload.get("stage3_assessment") or None
    stage3_explainability = report_payload.get("stage3_explainability") or None
    stage3_alerts = report_payload.get("stage3_alerts") or []
    scan_preview = report_payload.get("scan_preview") or {}
    stage_availability = report_payload.get("stage_availability") or {}
    executive_summary = report_payload.get("executive_summary") or {}
    integrated_assessment = report_payload.get("integrated_assessment") or {}
    detailed_analysis = report_payload.get("detailed_analysis") or {}
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
            fontSize=19,
            leading=23,
            textColor=colors.HexColor("#0B1320"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="HepSub",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.3,
            leading=14,
            textColor=colors.HexColor("#6B7280"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.8,
            leading=17,
            spaceBefore=11,
            spaceAfter=7,
            textColor=colors.HexColor("#0B1320"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.8,
            textColor=colors.HexColor("#374151"),
        )
    )

    def on_page(c, d):
        w, h = A4
        c.saveState()
        c.setStrokeColor(colors.HexColor("#D5DEE8"))
        c.setLineWidth(0.9)
        c.line(d.leftMargin, h - d.topMargin + 20, w - d.rightMargin, h - d.topMargin + 20)

        c.setFillColor(colors.HexColor("#0B1320"))
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - d.topMargin + 10, "Hepatica Patient Report")
        c.setFillColor(colors.HexColor("#6B7280"))
        c.setFont("Helvetica", 8.6)
        c.drawCentredString(w / 2, h - d.topMargin + 2.5, "Clinical liver risk assessment summary")
        c.drawRightString(w - d.rightMargin, h - d.topMargin + 10, generated_at)

        c.setFillColor(colors.HexColor("#9CA3AF"))
        c.setFont("Helvetica", 8)
        c.drawRightString(w - d.rightMargin, d.bottomMargin - 10, f"Page {c.getPageNumber()}")
        c.restoreState()

    story: list[object] = []
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Structured summary of Stage 1 clinical triage, Stage 2 imaging assessment, and Stage 3 monitoring.",
            styles["HepSub"],
        )
    )
    story.append(Spacer(1, 8))

    patient_rows = [
        ["Patient ID", _s(patient.get("external_id"))],
        ["Sex", _s(patient.get("sex"))],
        ["Age", _s(patient.get("age"))],
    ]
    pt = Table(patient_rows, colWidths=[30 * mm, 130 * mm])
    pt.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
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

    # Executive summary.
    story.append(Paragraph("Executive Summary", styles["H2"]))
    overall_posture = _s(executive_summary.get("overall_posture")).upper()
    stage1_tier = _s(executive_summary.get("stage1_risk_tier")).upper()
    stage2_top_stage = _s(executive_summary.get("stage2_top_stage")).upper()
    stage3_status = _s(executive_summary.get("stage3_status")).upper()
    stage3_tier = _s(executive_summary.get("stage3_risk_tier")).upper()
    summary_rows = [
        ["Overall Posture", _pill(overall_posture, color_hex=_tier_color(overall_posture))],
        ["Stage 1 Risk Tier", _pill(stage1_tier, color_hex=_tier_color(stage1_tier))],
        ["Stage 2 Top Stage", _pill(stage2_top_stage, color_hex=_stage_color(stage2_top_stage))],
        ["Stage 3 Status", _pill(stage3_status, color_hex=_tier_color(stage3_status))],
        ["Stage 3 Risk Tier", _pill(stage3_tier, color_hex=_tier_color(stage3_tier))],
        ["Stage 3 Composite Risk", _pct(executive_summary.get("stage3_composite_risk_score"))],
        ["Open Alerts", _s(executive_summary.get("active_alert_count"))],
    ]
    summary_tbl = Table(summary_rows, colWidths=[45 * mm, 115 * mm])
    summary_tbl.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_tbl)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Integrated Multistage Assessment", styles["H2"]))
    concordance = _s(integrated_assessment.get("concordance_summary"))
    concordance_tone = "warn" if "mixed" in concordance.lower() else "ok"
    story.append(_callout(concordance, tone=concordance_tone))
    story.append(Spacer(1, 5))
    story.append(Paragraph("<b>Primary Drivers</b>", styles["Small"]))
    for driver in integrated_assessment.get("key_drivers") or []:
        story.append(Paragraph(f"- {_s(driver)}", styles["Small"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph("<b>Recommended Next Actions</b>", styles["Small"]))
    for action in integrated_assessment.get("recommended_actions") or []:
        story.append(Paragraph(f"- {_s(action)}", styles["Small"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Stage Availability", styles["H2"]))
    availability_rows = [["Stage", "Status", "Notes"]]
    for key, label in [("stage1", "Stage 1"), ("stage2", "Stage 2"), ("stage3", "Stage 3")]:
        info = stage_availability.get(key) or {}
        status_value = _s(info.get("status")).upper()
        availability_rows.append(
            [label, _pill(status_value, color_hex=_tier_color(status_value)), _s(info.get("reason"))]
        )
    availability_tbl = Table(availability_rows, colWidths=[24 * mm, 28 * mm, 108 * mm])
    availability_tbl.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F7")),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F5F8FC")),
                ("ROWBACKGROUNDS", (2, 1), (2, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(availability_tbl)
    story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E5E7EB")))

    # Stage 1.
    story.append(Paragraph("Stage 1 - Clinical Risk", styles["H2"]))
    if clinical:
        tier = _s(clinical.get("risk_tier")).upper()

        s1_rows = [
            ["Risk Tier", _pill(tier, color_hex=_tier_color(tier))],
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
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                    ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 5))
        analysis_1 = _s(detailed_analysis.get("stage1"))
        story.append(_callout(analysis_1, tone="neutral"))
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
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                    ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
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
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F7")),
            ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#F8FBFF")),
            ("ROWBACKGROUNDS", (2, 1), (2, -1), [colors.white, colors.HexColor("#FCFDFE")]),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
            ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
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
        story.append(Spacer(1, 5))
        analysis_2 = _s(detailed_analysis.get("stage2"))
        story.append(_callout(analysis_2, tone="neutral"))
    else:
        story.append(Paragraph("No Stage 2 prediction was attached to this report.", styles["Small"]))

    # Uploaded scan preview.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Uploaded Scan Preview", styles["H2"]))
    scan_asset_id = _s(scan_preview.get("scan_asset_id"))
    scan_status = _s(scan_preview.get("status")).upper()
    scan_content_type = _s(scan_preview.get("content_type"))
    scan_reason = _s(scan_preview.get("reason"))

    if scan_preview_bytes:
        flow = _scan_image_flowable(scan_preview_bytes)
        if flow is not None:
            scan_image, scan_dims = flow
            story.append(scan_image)
            story.append(Spacer(1, 4))
            scan_meta_rows = [
                ["Scan Asset", scan_asset_id],
                ["Image Type", scan_content_type],
                ["Status", _pill(scan_status, color_hex=_tier_color(scan_status))],
                ["Image Size", scan_dims],
            ]
            scan_meta_tbl = Table(scan_meta_rows, colWidths=[36 * mm, 124 * mm])
            scan_meta_tbl.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                        ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            scan_meta_tbl.hAlign = "CENTER"
            story.append(scan_meta_tbl)
        else:
            story.append(
                _callout(
                    "A scan upload was found, but the image could not be rendered in the PDF preview.",
                    tone="warn",
                )
            )
    else:
        if scan_reason == "—":
            scan_reason = "No compatible uploaded scan was available for report preview."
        story.append(_callout(scan_reason, tone="neutral"))

    # Stage 3.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Stage 3 - Multimodal Monitoring", styles["H2"]))
    if stage3:
        s3_tier = _s(stage3.get("risk_tier")).upper()
        s3_rows = [
            ["Risk Tier", _pill(s3_tier, color_hex=_tier_color(s3_tier))],
            ["Composite Risk Score", _pct(stage3.get("composite_risk_score"))],
            ["Progression Risk (12m)", _pct(stage3.get("progression_risk_12m"))],
            ["Decompensation Risk (12m)", _pct(stage3.get("decomp_risk_12m"))],
            ["Model", _s(versioning.get("stage3_model") or stage3.get("model_version"))],
        ]
        t = Table(s3_rows, colWidths=[45 * mm, 115 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                    ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 5))
        analysis_3 = _s(detailed_analysis.get("stage3"))
        story.append(_callout(analysis_3, tone="neutral"))

        snapshot = stage3.get("feature_snapshot_json") or {}
        if snapshot:
            snapshot_rows = [
                ["Stiffness Source", _s(snapshot.get("stiffness_source"))],
                ["Stiffness (kPa)", _s(snapshot.get("stiffness_kpa"))],
                ["Alert Threshold", _s(snapshot.get("alert_score_threshold"))],
                ["PPV Target", _s(snapshot.get("alert_ppv_target"))],
                ["Recall Floor", _s(snapshot.get("alert_recall_floor"))],
            ]
            snapshot_tbl = Table(snapshot_rows, colWidths=[45 * mm, 115 * mm])
            snapshot_tbl.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8FC")),
                        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                        ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(Spacer(1, 5))
            story.append(snapshot_tbl)

        if stage3_explainability:
            local = stage3_explainability.get("local_feature_contrib_json") or {}
            positive = local.get("positive") or []
            if positive:
                story.append(Spacer(1, 6))
                story.append(Paragraph("Top Explainability Drivers", styles["Small"]))
                explain_rows = [["Feature", "Contribution"]]
                for item in positive[:5]:
                    explain_rows.append([_s(item.get("feature")), _f(item.get("contribution"), 4)])
                explain_tbl = Table(explain_rows, colWidths=[95 * mm, 65 * mm])
                explain_tbl.setStyle(
                    TableStyle(
                        [
                            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F7")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                            ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.append(explain_tbl)
    else:
        stage3_reason = _s((stage_availability.get("stage3") or {}).get("reason"))
        story.append(_callout(f"Stage 3 output unavailable. {stage3_reason}", tone="warn"))

    if stage3_alerts:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Stage 3 Alerts", styles["H2"]))
        alert_rows = [["Type", "Severity", "Status", "Score / Threshold"]]
        for alert in stage3_alerts[:10]:
            sev = _s(alert.get("severity")).upper()
            status = _s(alert.get("status")).upper()
            alert_rows.append(
                [
                    _s(alert.get("alert_type")),
                    _pill(sev, color_hex=_tier_color(sev)),
                    _pill(status, color_hex=_tier_color(status)),
                    f"{_f(alert.get('score'), 3)} / {_f(alert.get('threshold'), 3)}",
                ]
            )
        alert_tbl = Table(alert_rows, colWidths=[58 * mm, 30 * mm, 24 * mm, 48 * mm])
        alert_tbl.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                    ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F7")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FCFDFE")]),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D5DEE8")),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.45, colors.HexColor("#E3EAF2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(alert_tbl)

    # Knowledge.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Knowledge Summary", styles["H2"]))
    blocks = report_payload.get("knowledge") or []
    if not blocks:
        story.append(_callout("No knowledge blocks were generated for this report.", tone="neutral"))
    else:
        for block in blocks[:5]:
            title = _s(block.get("title"))
            content = _s(block.get("content"))
            if len(content) > 900:
                content = content[:900].rstrip() + "..."
            story.append(Paragraph(f"<b>{title}</b>", styles["Small"]))
            story.append(Spacer(1, 3))
            story.append(_callout(content.replace("\n", " "), tone="neutral"))
            story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Disclaimer</b>", styles["Small"]))
    story.append(_callout(_s(report_payload.get("disclaimer") or DISCLAIMER), tone="warn"))

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
