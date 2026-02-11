from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import Stage3RiskTier
from app.db.models import (
    ClinicalAssessment,
    FibrosisPrediction,
    RiskAlert,
    Stage3Assessment,
    Stage3Explanation,
    StiffnessMeasurement,
)
from app.services.model_registry import format_model_version, get_active_model, resolve_local_artifact_path
from app.services.stiffness_proxy import estimate_stiffness_proxy


class Stage3Error(RuntimeError):
    pass


@dataclass
class Stage3Computation:
    composite_risk_score: float
    progression_risk_12m: float
    decomp_risk_12m: float
    risk_tier: Stage3RiskTier
    model_version: str
    feature_snapshot: dict[str, Any]
    local_feature_contrib_json: dict[str, Any]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sigmoid(value: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-value))


def _nfs_proxy(*, age: int, bmi: float, type2dm: bool, ast: float, alt: float, platelets: float, albumin: float) -> float:
    ast_alt = ast / max(alt, 1e-4)
    diabetes = 1 if type2dm else 0
    return (
        -1.675
        + 0.037 * age
        + 0.094 * bmi
        + 1.13 * diabetes
        + 0.99 * ast_alt
        - 0.013 * platelets
        - 0.66 * albumin
    )


def _bard_score(*, bmi: float, ast: float, alt: float, type2dm: bool) -> int:
    score = 0
    if bmi >= 28:
        score += 1
    if ast / max(alt, 1e-4) >= 0.8:
        score += 2
    if type2dm:
        score += 1
    return score


def _stage_numeric(top_stage: str | None) -> float:
    order = {"F0": 0.0, "F1": 1.0, "F2": 2.0, "F3": 3.0, "F4": 4.0}
    return order.get(str(top_stage or "").upper(), 1.5)


def _risk_tier_from_score(score: float) -> Stage3RiskTier:
    if score >= 0.82:
        return Stage3RiskTier.CRITICAL
    if score >= 0.62:
        return Stage3RiskTier.HIGH
    if score >= 0.35:
        return Stage3RiskTier.MODERATE
    return Stage3RiskTier.LOW


@lru_cache(maxsize=4)
def _load_stage3_model(artifact_dir_raw: str):
    artifact_dir = Path(artifact_dir_raw)
    model_path = artifact_dir / "stage3_risk_model.joblib"
    if not model_path.exists():
        return None

    try:
        import joblib

        model = joblib.load(model_path)
    except Exception:
        return None

    manifest_path = artifact_dir / "stage3_feature_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            columns = [str(c) for c in manifest.get("feature_columns", [])]
        except Exception:
            columns = []
    else:
        columns = []

    metadata_path = artifact_dir / "stage3_run_metadata.json"
    model_version = "multimodal-stage3-risk:v1"
    if metadata_path.exists():
        try:
            payload = json.loads(metadata_path.read_text())
            model_version = f"{payload.get('model_name', 'multimodal-stage3-risk')}:{payload.get('model_version', 'v1')}"
        except Exception:
            pass

    return model, columns, model_version


def _predict_artifact_scores(*, feature_payload: dict[str, Any], artifact_dir: Path) -> tuple[float, float, float, str] | None:
    loaded = _load_stage3_model(str(artifact_dir.resolve()))
    if loaded is None:
        return None
    model, columns, model_version = loaded

    try:
        import pandas as pd
    except Exception:
        return None

    frame = pd.DataFrame([feature_payload])
    if columns:
        for col in columns:
            if col not in frame:
                frame[col] = 0.0
        frame = frame[columns]

    try:
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(frame)
            if probs.shape[1] == 2:
                p = float(probs[0, 1])
            else:
                p = float(probs[0].max())
        else:
            p = float(model.predict(frame)[0])
            p = _clamp(p, 0.0, 1.0)
    except Exception:
        return None

    progression = _clamp(0.92 * p + 0.03, 0.0, 0.99)
    decomp = _clamp(0.72 * p + 0.05, 0.0, 0.99)
    return round(p, 6), round(progression, 6), round(decomp, 6), model_version


def _alert_threshold_for_ppv_target(ppv_target: float) -> float:
    if ppv_target >= 0.9:
        return 0.78
    if ppv_target >= 0.85:
        return 0.7
    return 0.62


def _build_trend_points(db: Session, patient_id: str, limit: int = 12) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(Stage3Assessment)
            .where(Stage3Assessment.patient_id == patient_id)
            .order_by(Stage3Assessment.created_at.desc())
            .limit(limit)
        ).all()
    )
    rows = list(reversed(rows))
    if not rows:
        return []

    open_alerts = {
        alert.stage3_assessment_id
        for alert in db.scalars(
            select(RiskAlert).where(
                RiskAlert.patient_id == patient_id,
                RiskAlert.status == "open",
            )
        ).all()
    }
    points: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        points.append(
            {
                "visit_index": idx,
                "assessment_id": row.id,
                "score": round(float(row.composite_risk_score), 6),
                "risk_tier": row.risk_tier,
                "alert_state": "open" if row.id in open_alerts else "none",
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return points


def _compute_stage3(
    *,
    cfg: Settings,
    clinical: ClinicalAssessment | None,
    fibrosis: FibrosisPrediction | None,
    stiffness_kpa: float,
    stiffness_source: str,
    previous_assessment: Stage3Assessment | None,
    artifact_dir: Path,
    model_version_default: str,
) -> Stage3Computation:
    age = int(clinical.age) if clinical else 50
    bmi = float(clinical.bmi) if clinical else 28.0
    fib4 = float(clinical.fib4) if clinical else 1.4
    apri = float(clinical.apri) if clinical else 0.6
    ast = float(clinical.ast) if clinical else 45.0
    alt = float(clinical.alt) if clinical else 40.0
    platelets = float(clinical.platelets) if clinical else 190.0
    type2dm = bool(clinical.type2dm) if clinical else False
    albumin_proxy = _clamp(4.3 - 0.0025 * max(ast - 35.0, 0.0), 2.0, 5.5)

    stage_num = _stage_numeric(fibrosis.top1_stage if fibrosis else None)
    stage_prob = float(fibrosis.top1_probability) if fibrosis else 0.56
    quality_valid = bool((fibrosis.quality_metrics or {}).get("is_valid", True)) if fibrosis else True

    nfs_score = _nfs_proxy(
        age=age,
        bmi=bmi,
        type2dm=type2dm,
        ast=ast,
        alt=alt,
        platelets=platelets,
        albumin=albumin_proxy,
    )
    bard = _bard_score(bmi=bmi, ast=ast, alt=alt, type2dm=type2dm)

    previous_score = float(previous_assessment.composite_risk_score) if previous_assessment else 0.0

    fib4_component = _clamp((fib4 - 1.1) / 3.5, 0.0, 1.0)
    apri_component = _clamp((apri - 0.35) / 1.6, 0.0, 1.0)
    stage_component = _clamp((stage_num / 4.0) * 0.7 + stage_prob * 0.3, 0.0, 1.0)
    stiffness_component = _clamp((stiffness_kpa - 3.0) / 22.0, 0.0, 1.0)
    nfs_component = _clamp(_sigmoid(nfs_score / 2.5), 0.0, 1.0)
    bard_component = _clamp(bard / 4.0, 0.0, 1.0)
    delta_component = _clamp(max(previous_score, 0.0), 0.0, 1.0)
    quality_penalty = 0.08 if not quality_valid else 0.0

    heuristic_score = _clamp(
        0.22 * fib4_component
        + 0.14 * apri_component
        + 0.22 * stage_component
        + 0.23 * stiffness_component
        + 0.10 * nfs_component
        + 0.05 * bard_component
        + 0.04 * delta_component
        - quality_penalty,
        0.0,
        0.99,
    )
    artifact = _predict_artifact_scores(feature_payload={
        "age": age,
        "bmi": bmi,
        "fib4": fib4,
        "apri": apri,
        "stage_numeric": stage_num,
        "stage_probability": stage_prob,
        "stiffness_kpa": stiffness_kpa,
        "nfs_score": nfs_score,
        "bard_score": bard,
        "previous_score": previous_score,
        "quality_valid": 1.0 if quality_valid else 0.0,
    }, artifact_dir=artifact_dir)

    if artifact is None:
        composite_risk = round(float(heuristic_score), 6)
        progression_risk_12m = round(_clamp(0.90 * composite_risk + 0.05, 0.0, 0.99), 6)
        decomp_risk_12m = round(_clamp(0.74 * composite_risk + (0.06 if stage_num >= 3 else 0.0), 0.0, 0.99), 6)
        model_version = f"{model_version_default}::heuristic"
    else:
        composite_risk, progression_risk_12m, decomp_risk_12m, model_version = artifact

    risk_tier = _risk_tier_from_score(composite_risk)

    local_components = {
        "fib4_component": round(0.22 * fib4_component, 6),
        "apri_component": round(0.14 * apri_component, 6),
        "stage_component": round(0.22 * stage_component, 6),
        "stiffness_component": round(0.23 * stiffness_component, 6),
        "nfs_component": round(0.10 * nfs_component, 6),
        "bard_component": round(0.05 * bard_component, 6),
        "history_component": round(0.04 * delta_component, 6),
        "quality_penalty": round(-quality_penalty, 6),
    }
    sorted_items = sorted(local_components.items(), key=lambda item: item[1], reverse=True)
    positive = [{"feature": k, "contribution": v} for k, v in sorted_items[:5]]
    negative = [{"feature": k, "contribution": v} for k, v in sorted(local_components.items(), key=lambda item: item[1])[:3]]

    feature_snapshot = {
        "fib4": round(fib4, 6),
        "apri": round(apri, 6),
        "nfs_score": round(float(nfs_score), 6),
        "bard_score": int(bard),
        "stage_numeric": round(stage_num, 6),
        "stage_probability": round(stage_prob, 6),
        "stiffness_kpa": round(stiffness_kpa, 6),
        "stiffness_source": stiffness_source,
        "quality_valid": quality_valid,
        "previous_composite_score": round(previous_score, 6),
        "alert_score_threshold": _alert_threshold_for_ppv_target(cfg.stage3_alert_ppv_target),
        "alert_ppv_target": cfg.stage3_alert_ppv_target,
        "alert_recall_floor": cfg.stage3_alert_recall_floor,
    }

    return Stage3Computation(
        composite_risk_score=composite_risk,
        progression_risk_12m=progression_risk_12m,
        decomp_risk_12m=decomp_risk_12m,
        risk_tier=risk_tier,
        model_version=model_version,
        feature_snapshot=feature_snapshot,
        local_feature_contrib_json={
            "positive": positive,
            "negative": negative,
            "raw_components": local_components,
        },
    )


def _resolve_selected_or_latest(db: Session, model_cls, patient_id: str, selected_id: str | None):
    if selected_id:
        row = db.get(model_cls, selected_id)
        if row is None or row.patient_id != patient_id:
            return None
        return row
    return db.scalar(
        select(model_cls)
        .where(model_cls.patient_id == patient_id)
        .order_by(model_cls.created_at.desc())
    )


def run_stage3_assessment(
    *,
    db: Session,
    cfg: Settings,
    patient_id: str,
    performed_by: str | None,
    clinical_assessment_id: str | None = None,
    fibrosis_prediction_id: str | None = None,
    stiffness_measurement_id: str | None = None,
) -> tuple[Stage3Assessment, Stage3Explanation, list[RiskAlert]]:
    if not cfg.stage3_enabled:
        raise Stage3Error("Stage 3 is disabled")

    clinical = _resolve_selected_or_latest(
        db,
        ClinicalAssessment,
        patient_id=patient_id,
        selected_id=clinical_assessment_id,
    )
    fibrosis = _resolve_selected_or_latest(
        db,
        FibrosisPrediction,
        patient_id=patient_id,
        selected_id=fibrosis_prediction_id,
    )
    if clinical is None and fibrosis is None:
        raise Stage3Error("Stage 3 requires at least one prior Stage 1 or Stage 2 assessment")

    stiffness_row = _resolve_selected_or_latest(
        db,
        StiffnessMeasurement,
        patient_id=patient_id,
        selected_id=stiffness_measurement_id,
    )
    if stiffness_row is None:
        if not cfg.stage3_stiffness_proxy_enabled:
            raise Stage3Error("No stiffness measurement found and proxy fallback is disabled")
        proxy = estimate_stiffness_proxy(clinical=clinical, fibrosis=fibrosis)
        stiffness_row = StiffnessMeasurement(
            patient_id=patient_id,
            entered_by=performed_by,
            measured_kpa=proxy.estimated_kpa,
            cap_dbm=None,
            source=proxy.source,
            measured_at=datetime.now(timezone.utc),
        )
        db.add(stiffness_row)
        db.flush()

    previous_assessment = db.scalar(
        select(Stage3Assessment)
        .where(Stage3Assessment.patient_id == patient_id)
        .order_by(Stage3Assessment.created_at.desc())
    )

    active_stage3_model = get_active_model(db, cfg.stage3_registry_model_name)
    stage3_model_version = format_model_version(
        active_stage3_model,
        default_name=cfg.stage3_registry_model_name,
        default_version="v1",
    )
    stage3_artifact_dir = resolve_local_artifact_path(active_stage3_model, cfg.stage3_model_artifact_dir)

    computed = _compute_stage3(
        cfg=cfg,
        clinical=clinical,
        fibrosis=fibrosis,
        stiffness_kpa=float(stiffness_row.measured_kpa),
        stiffness_source=stiffness_row.source,
        previous_assessment=previous_assessment,
        artifact_dir=stage3_artifact_dir,
        model_version_default=stage3_model_version,
    )

    assessment = Stage3Assessment(
        patient_id=patient_id,
        clinical_assessment_id=clinical.id if clinical else None,
        fibrosis_prediction_id=fibrosis.id if fibrosis else None,
        stiffness_measurement_id=stiffness_row.id,
        performed_by=performed_by,
        composite_risk_score=computed.composite_risk_score,
        progression_risk_12m=computed.progression_risk_12m,
        decomp_risk_12m=computed.decomp_risk_12m,
        risk_tier=computed.risk_tier.value,
        model_version=computed.model_version,
        feature_snapshot_json=computed.feature_snapshot,
    )
    db.add(assessment)
    db.flush()

    explanation = Stage3Explanation(
        stage3_assessment_id=assessment.id,
        local_feature_contrib_json=computed.local_feature_contrib_json,
        global_reference_version=computed.model_version,
        trend_points_json=[],
    )
    db.add(explanation)
    db.flush()

    explanation.trend_points_json = _build_trend_points(db, patient_id=patient_id)
    db.flush()

    alerts = upsert_stage3_alerts(
        db=db,
        cfg=cfg,
        assessment=assessment,
        created_by=performed_by,
    )
    return assessment, explanation, alerts


def upsert_stage3_alerts(
    *,
    db: Session,
    cfg: Settings,
    assessment: Stage3Assessment,
    created_by: str | None,
) -> list[RiskAlert]:
    threshold = _alert_threshold_for_ppv_target(cfg.stage3_alert_ppv_target)
    candidates: list[tuple[str, str, float]] = []

    if assessment.composite_risk_score >= threshold and assessment.risk_tier in {"HIGH", "CRITICAL"}:
        severity = "critical" if assessment.risk_tier == "CRITICAL" else "high"
        candidates.append(("ADVANCED_FIBROSIS_RISK", severity, float(assessment.composite_risk_score)))

    if assessment.decomp_risk_12m >= threshold + 0.05:
        severity = "critical" if assessment.decomp_risk_12m >= 0.8 else "high"
        candidates.append(("DECOMPENSATION_RISK", severity, float(assessment.decomp_risk_12m)))

    created: list[RiskAlert] = []
    for alert_type, severity, score in candidates:
        existing = db.scalar(
            select(RiskAlert).where(
                RiskAlert.patient_id == assessment.patient_id,
                RiskAlert.alert_type == alert_type,
                RiskAlert.status == "open",
            )
        )
        if existing:
            existing.score = round(score, 6)
            existing.threshold = threshold
            existing.stage3_assessment_id = assessment.id
            existing.severity = severity
            continue

        row = RiskAlert(
            patient_id=assessment.patient_id,
            stage3_assessment_id=assessment.id,
            created_by=created_by,
            alert_type=alert_type,
            severity=severity,
            threshold=threshold,
            score=round(score, 6),
            status="open",
        )
        db.add(row)
        db.flush()
        created.append(row)

    return created
