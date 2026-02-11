from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Patient
from app.services.stage3 import Stage3Error, run_stage3_assessment
from app.services.timeline import append_timeline_event


def run_scheduled_stage3_monitoring(
    *,
    db: Session,
    cfg: Settings,
    performed_by: str | None = None,
) -> dict:
    if not cfg.stage3_enabled:
        return {
            "status": "SKIPPED",
            "reason": "stage3_disabled",
            "processed": 0,
            "alerts_created": 0,
        }

    patients = list(db.scalars(select(Patient).order_by(Patient.created_at.asc())).all())
    processed = 0
    alerts_created = 0
    failures: list[dict[str, str]] = []
    run_started_at = datetime.now(timezone.utc).isoformat()

    for patient in patients:
        try:
            assessment, _explain, created_alerts = run_stage3_assessment(
                db=db,
                cfg=cfg,
                patient_id=patient.id,
                performed_by=performed_by,
            )
            processed += 1
            alerts_created += len(created_alerts)
            append_timeline_event(
                db,
                patient_id=patient.id,
                event_type="STAGE3_MONITORING_BATCH_COMPLETED",
                event_payload={
                    "assessment_id": assessment.id,
                    "risk_tier": assessment.risk_tier,
                    "composite_risk_score": assessment.composite_risk_score,
                    "alerts_created": len(created_alerts),
                    "monitoring_mode": cfg.stage3_monitoring_mode,
                    "interval_weeks": cfg.stage3_monitor_interval_weeks,
                    "run_started_at": run_started_at,
                },
                created_by=performed_by,
            )
        except Stage3Error as exc:
            failures.append({"patient_id": patient.id, "error": str(exc)})

    return {
        "status": "OK",
        "processed": processed,
        "alerts_created": alerts_created,
        "failures": failures,
        "monitoring_mode": cfg.stage3_monitoring_mode,
        "interval_weeks": cfg.stage3_monitor_interval_weeks,
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
    }
