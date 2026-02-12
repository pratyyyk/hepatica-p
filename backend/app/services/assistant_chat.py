from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    ClinicalAssessment,
    FibrosisPrediction,
    KnowledgeChunk,
    Patient,
    RiskAlert,
    Stage3Assessment,
)
from app.schemas.assistant import AssistantCitation, AssistantPatientSummary


@dataclass
class PatientSnapshot:
    patient: Patient
    clinical: ClinicalAssessment | None
    fibrosis: FibrosisPrediction | None
    stage3: Stage3Assessment | None
    open_alerts: int


def _pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _hash_embedding(text: str, dim: int = 256) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    dim = min(a.shape[0], b.shape[0])
    if dim == 0:
        return 0.0
    a = a[:dim]
    b = b[:dim]
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _keyword_overlap(query: str, text: str) -> float:
    q = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not q:
        return 0.0
    t = set(re.findall(r"[a-z0-9]+", text.lower()))
    return len(q.intersection(t)) / max(len(q), 1)


def _retrieve_citations(db: Session, *, query: str, top_k: int = 3) -> list[AssistantCitation]:
    rows = db.scalars(select(KnowledgeChunk)).all()
    if not rows:
        return []

    q_emb = _hash_embedding(query)
    scored: list[tuple[KnowledgeChunk, float]] = []
    for row in rows:
        emb = np.array(row.embedding or [], dtype=np.float32)
        semantic = _cosine_similarity(q_emb, emb) if emb.size else 0.0
        lexical = _keyword_overlap(query, row.text)
        score = semantic + (0.25 * lexical)
        if score <= 0:
            continue
        scored.append((row, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    citations: list[AssistantCitation] = []
    for row, _ in scored[:top_k]:
        snippet = " ".join((row.text or "").split())[:220]
        citations.append(
            AssistantCitation(
                source_doc=row.source_doc,
                page_number=row.page_number,
                snippet=snippet,
            )
        )
    return citations


def build_snapshot(db: Session, *, patient_id: str) -> PatientSnapshot | None:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None

    clinical = db.scalar(
        select(ClinicalAssessment)
        .where(ClinicalAssessment.patient_id == patient_id)
        .order_by(desc(ClinicalAssessment.created_at))
    )
    fibrosis = db.scalar(
        select(FibrosisPrediction)
        .where(FibrosisPrediction.patient_id == patient_id)
        .order_by(desc(FibrosisPrediction.created_at))
    )
    stage3 = db.scalar(
        select(Stage3Assessment)
        .where(Stage3Assessment.patient_id == patient_id)
        .order_by(desc(Stage3Assessment.created_at))
    )
    open_alerts = len(
        db.scalars(
            select(RiskAlert.id).where(
                RiskAlert.patient_id == patient_id,
                RiskAlert.status == "open",
            )
        ).all()
    )

    return PatientSnapshot(
        patient=patient,
        clinical=clinical,
        fibrosis=fibrosis,
        stage3=stage3,
        open_alerts=open_alerts,
    )


def _build_summary(snapshot: PatientSnapshot) -> AssistantPatientSummary:
    return AssistantPatientSummary(
        external_id=snapshot.patient.external_id,
        stage1_risk_tier=snapshot.clinical.risk_tier if snapshot.clinical else None,
        stage1_probability=snapshot.clinical.probability if snapshot.clinical else None,
        stage2_top_stage=snapshot.fibrosis.top1_stage if snapshot.fibrosis else None,
        stage2_top_probability=snapshot.fibrosis.top1_probability if snapshot.fibrosis else None,
        stage3_risk_tier=snapshot.stage3.risk_tier if snapshot.stage3 else None,
        stage3_composite_risk=snapshot.stage3.composite_risk_score if snapshot.stage3 else None,
        open_alerts=snapshot.open_alerts,
    )


def _default_suggestions(snapshot: PatientSnapshot | None, stage3_enabled: bool) -> list[str]:
    if snapshot is None:
        return [
            "Set an active patient and ask: summarize current risk.",
            "Ask: what should I do next for this patient?",
            "Ask: explain Stage 1, Stage 2, and Stage 3 together.",
        ]

    suggestions: list[str] = []
    if snapshot.clinical is None:
        suggestions.append("Run Stage 1 clinical assessment to establish baseline risk.")
    if snapshot.fibrosis is None:
        suggestions.append("Upload scan and run Stage 2 to get fibrosis stage probabilities.")
    if stage3_enabled and snapshot.stage3 is None:
        suggestions.append("Save stiffness and run Stage 3 for integrated 12-month risk.")
    if snapshot.open_alerts > 0:
        suggestions.append("Review and acknowledge open Stage 3 alerts on the monitoring panel.")

    suggestions.append("Correlate AI output with exam, labs, and local protocol before action.")
    return suggestions[:4]


def _message_specific_note(message: str, snapshot: PatientSnapshot | None) -> str | None:
    lower = message.lower()

    if "0.82" in lower or ("fixed" in lower and "prob" in lower):
        return (
            "If Stage 1 probability repeats near 0.82, that is expected for HIGH tier in the "
            "rule engine (base mapping). Stage 2 and Stage 3 should provide additional variability."
        )

    if any(token in lower for token in ["f2", "f3", "f4", "same", "similar"]):
        if snapshot and snapshot.fibrosis:
            return (
                "Close F2/F3/F4 probabilities indicate model uncertainty in mid-to-advanced classes. "
                "Use quality metrics, confidence flags, and longitudinal context before escalation."
            )
    return None


def generate_assistant_reply(
    *,
    db: Session,
    message: str,
    patient_id: str | None,
    stage3_enabled: bool,
) -> tuple[str, list[str], list[AssistantCitation], AssistantPatientSummary | None]:
    snapshot = build_snapshot(db, patient_id=patient_id) if patient_id else None

    lines: list[str] = []
    if snapshot is None:
        lines.append(
            "I can help with risk interpretation, next-step recommendations, and report-ready summaries."
        )
        lines.append(
            "For patient-specific guidance, select a patient and ask me to summarize Stage 1/2/3 status."
        )
    else:
        lines.append(f"Patient {snapshot.patient.external_id} summary:")
        if snapshot.clinical:
            lines.append(
                f"- Stage 1: {snapshot.clinical.risk_tier} risk "
                f"({_pct(snapshot.clinical.probability)}; FIB-4 {snapshot.clinical.fib4:.2f}, "
                f"APRI {snapshot.clinical.apri:.2f})."
            )
        else:
            lines.append("- Stage 1: no assessment yet.")

        if snapshot.fibrosis:
            lines.append(
                f"- Stage 2: top class {snapshot.fibrosis.top1_stage} "
                f"({_pct(snapshot.fibrosis.top1_probability)}), "
                f"confidence {snapshot.fibrosis.confidence_flag}."
            )
        else:
            lines.append("- Stage 2: no scan inference yet.")

        if not stage3_enabled:
            lines.append("- Stage 3: disabled in backend config.")
        elif snapshot.stage3:
            lines.append(
                f"- Stage 3: {snapshot.stage3.risk_tier} tier "
                f"(composite {_pct(snapshot.stage3.composite_risk_score)}, "
                f"progression {_pct(snapshot.stage3.progression_risk_12m)}, "
                f"decompensation {_pct(snapshot.stage3.decomp_risk_12m)})."
            )
        else:
            lines.append("- Stage 3: no multimodal assessment yet.")

        lines.append(f"- Open alerts: {snapshot.open_alerts}.")

    note = _message_specific_note(message, snapshot)
    if note:
        lines.append("")
        lines.append(note)

    suggestions = _default_suggestions(snapshot, stage3_enabled)

    citation_query = message
    if snapshot:
        citation_query = (
            f"{message} liver fibrosis {snapshot.clinical.risk_tier if snapshot.clinical else ''} "
            f"{snapshot.fibrosis.top1_stage if snapshot.fibrosis else ''} "
            f"{snapshot.stage3.risk_tier if snapshot.stage3 else ''}"
        )
    citations = _retrieve_citations(db, query=citation_query, top_k=3)

    summary = _build_summary(snapshot) if snapshot else None
    return "\n".join(lines), suggestions, citations, summary
