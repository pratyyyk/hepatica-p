from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, assert_patient_owned_by_user, get_request_user
from app.core.config import Settings, get_settings
from app.core.enums import Stage3RiskTier
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.models import RiskAlert, Stage3Assessment, Stage3Explanation, StiffnessMeasurement
from app.db.session import get_db
from app.schemas.stage3 import (
    RiskAlertRead,
    RiskAlertStatusUpdate,
    Stage3AlertListRead,
    Stage3AssessmentCreate,
    Stage3AssessmentRead,
    Stage3ExplainabilityRead,
    Stage3HistoryRead,
    StiffnessMeasurementCreate,
    StiffnessMeasurementRead,
)
from app.services.audit import write_audit_log
from app.services.stage3 import Stage3Error, run_stage3_assessment
from app.services.timeline import append_timeline_event

router = APIRouter(tags=["stage3"])
settings = get_settings()


def _require_stage3_enabled(cfg: Settings) -> None:
    if not cfg.stage3_enabled:
        raise HTTPException(status_code=404, detail="Stage 3 is disabled")


@router.post("/assessments/stage3", response_model=Stage3AssessmentRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def run_stage3(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    try:
        parsed = Stage3AssessmentCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, parsed.patient_id, req_user.db_user.id)

    try:
        assessment, _explanation, created_alerts = run_stage3_assessment(
            db=db,
            cfg=cfg,
            patient_id=parsed.patient_id,
            performed_by=req_user.db_user.id,
            clinical_assessment_id=parsed.clinical_assessment_id,
            fibrosis_prediction_id=parsed.fibrosis_prediction_id,
            stiffness_measurement_id=parsed.stiffness_measurement_id,
        )
    except Stage3Error as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    append_timeline_event(
        db,
        patient_id=parsed.patient_id,
        event_type="STAGE3_ASSESSMENT_COMPLETED",
        event_payload={
            "assessment_id": assessment.id,
            "risk_tier": assessment.risk_tier,
            "composite_risk_score": assessment.composite_risk_score,
            "progression_risk_12m": assessment.progression_risk_12m,
            "decomp_risk_12m": assessment.decomp_risk_12m,
            "model_version": assessment.model_version,
        },
        created_by=req_user.db_user.id,
    )

    for alert in created_alerts:
        append_timeline_event(
            db,
            patient_id=parsed.patient_id,
            event_type="STAGE3_ALERT_CREATED",
            event_payload={
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "status": alert.status,
                "score": alert.score,
                "threshold": alert.threshold,
            },
            created_by=req_user.db_user.id,
        )

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="STAGE3_ASSESSMENT_CREATED",
        resource_type="stage3_assessment",
        resource_id=assessment.id,
        metadata={"risk_tier": assessment.risk_tier, "alerts_created": len(created_alerts)},
    )

    db.commit()
    db.refresh(assessment)
    return Stage3AssessmentRead(
        id=assessment.id,
        patient_id=assessment.patient_id,
        clinical_assessment_id=assessment.clinical_assessment_id,
        fibrosis_prediction_id=assessment.fibrosis_prediction_id,
        stiffness_measurement_id=assessment.stiffness_measurement_id,
        composite_risk_score=assessment.composite_risk_score,
        progression_risk_12m=assessment.progression_risk_12m,
        decomp_risk_12m=assessment.decomp_risk_12m,
        risk_tier=Stage3RiskTier(assessment.risk_tier),
        model_version=assessment.model_version,
        feature_snapshot_json=assessment.feature_snapshot_json,
        created_at=assessment.created_at,
    )


@router.post("/patients/{patient_id}/stiffness", response_model=StiffnessMeasurementRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def create_stiffness_measurement(
    request: Request,
    response: Response,
    patient_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    try:
        parsed = StiffnessMeasurementCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)
    measured_at = parsed.measured_at or datetime.now(timezone.utc)

    row = StiffnessMeasurement(
        patient_id=patient_id,
        entered_by=req_user.db_user.id,
        measured_kpa=round(parsed.measured_kpa, 4),
        cap_dbm=round(parsed.cap_dbm, 4) if parsed.cap_dbm is not None else None,
        source=parsed.source,
        measured_at=measured_at,
    )
    db.add(row)
    db.flush()

    append_timeline_event(
        db,
        patient_id=patient_id,
        event_type="STIFFNESS_MEASUREMENT_RECORDED",
        event_payload={
            "measurement_id": row.id,
            "measured_kpa": row.measured_kpa,
            "cap_dbm": row.cap_dbm,
            "source": row.source,
            "measured_at": measured_at.isoformat(),
        },
        created_by=req_user.db_user.id,
    )

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="STIFFNESS_MEASUREMENT_CREATED",
        resource_type="stiffness_measurement",
        resource_id=row.id,
        metadata={"patient_id": patient_id, "source": row.source},
    )

    db.commit()
    db.refresh(row)
    return StiffnessMeasurementRead(
        id=row.id,
        patient_id=row.patient_id,
        measured_kpa=row.measured_kpa,
        cap_dbm=row.cap_dbm,
        source=row.source,
        measured_at=row.measured_at,
        created_at=row.created_at,
    )


@router.get("/patients/{patient_id}/stage3/history", response_model=Stage3HistoryRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_stage3_history(
    request: Request,
    response: Response,
    patient_id: str,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    rows = list(
        db.scalars(
            select(Stage3Assessment)
            .where(Stage3Assessment.patient_id == patient_id)
            .order_by(Stage3Assessment.created_at.desc())
        ).all()
    )
    return Stage3HistoryRead(
        patient_id=patient_id,
        assessments=[
            Stage3AssessmentRead(
                id=row.id,
                patient_id=row.patient_id,
                clinical_assessment_id=row.clinical_assessment_id,
                fibrosis_prediction_id=row.fibrosis_prediction_id,
                stiffness_measurement_id=row.stiffness_measurement_id,
                composite_risk_score=row.composite_risk_score,
                progression_risk_12m=row.progression_risk_12m,
                decomp_risk_12m=row.decomp_risk_12m,
                risk_tier=Stage3RiskTier(row.risk_tier),
                model_version=row.model_version,
                feature_snapshot_json=row.feature_snapshot_json,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/patients/{patient_id}/alerts", response_model=Stage3AlertListRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_stage3_alerts(
    request: Request,
    response: Response,
    patient_id: str,
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    stmt = select(RiskAlert).where(RiskAlert.patient_id == patient_id).order_by(RiskAlert.created_at.desc())
    if status:
        stmt = stmt.where(RiskAlert.status == status.lower())
    rows = list(db.scalars(stmt).all())
    return Stage3AlertListRead(
        patient_id=patient_id,
        alerts=[
            RiskAlertRead(
                id=row.id,
                patient_id=row.patient_id,
                stage3_assessment_id=row.stage3_assessment_id,
                alert_type=row.alert_type,
                severity=row.severity,
                threshold=row.threshold,
                score=row.score,
                status=row.status,
                resolved_at=row.resolved_at,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.post("/patients/{patient_id}/alerts/{alert_id}/status", response_model=RiskAlertRead)
@limiter.limit(settings.rate_limit_mutating_per_ip, key_func=get_remote_address)
@limiter.limit(settings.rate_limit_mutating_per_user, key_func=user_or_ip_key)
def update_stage3_alert_status(
    request: Request,
    response: Response,
    patient_id: str,
    alert_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    try:
        parsed = RiskAlertStatusUpdate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)
    alert = db.get(RiskAlert, alert_id)
    if alert is None or alert.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = parsed.status
    if parsed.status == "closed":
        alert.resolved_at = datetime.now(timezone.utc)

    append_timeline_event(
        db,
        patient_id=patient_id,
        event_type="STAGE3_ALERT_STATUS_UPDATED",
        event_payload={
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "status": alert.status,
        },
        created_by=req_user.db_user.id,
    )
    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="STAGE3_ALERT_STATUS_UPDATED",
        resource_type="risk_alert",
        resource_id=alert.id,
        metadata={"status": alert.status},
    )
    db.commit()
    db.refresh(alert)
    return RiskAlertRead(
        id=alert.id,
        patient_id=alert.patient_id,
        stage3_assessment_id=alert.stage3_assessment_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        threshold=alert.threshold,
        score=alert.score,
        status=alert.status,
        resolved_at=alert.resolved_at,
        created_at=alert.created_at,
    )


@router.get("/patients/{patient_id}/stage3/explainability", response_model=Stage3ExplainabilityRead)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
def get_stage3_explainability(
    request: Request,
    response: Response,
    patient_id: str,
    stage3_assessment_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    _require_stage3_enabled(cfg)
    assert_patient_owned_by_user(db, patient_id, req_user.db_user.id)

    if stage3_assessment_id:
        assessment = db.get(Stage3Assessment, stage3_assessment_id)
        if assessment is None or assessment.patient_id != patient_id:
            raise HTTPException(status_code=404, detail="Stage 3 assessment not found")
    else:
        assessment = db.scalar(
            select(Stage3Assessment)
            .where(Stage3Assessment.patient_id == patient_id)
            .order_by(Stage3Assessment.created_at.desc())
        )
        if assessment is None:
            raise HTTPException(status_code=404, detail="No Stage 3 assessments found")

    explanation = db.scalar(
        select(Stage3Explanation).where(Stage3Explanation.stage3_assessment_id == assessment.id)
    )
    if explanation is None:
        raise HTTPException(status_code=404, detail="Stage 3 explanation not found")

    return Stage3ExplainabilityRead(
        patient_id=patient_id,
        stage3_assessment_id=assessment.id,
        local_feature_contrib_json=explanation.local_feature_contrib_json,
        global_reference_version=explanation.global_reference_version,
        trend_points_json=explanation.trend_points_json,
        created_at=explanation.created_at,
    )
