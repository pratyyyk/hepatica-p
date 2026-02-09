from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.enums import RiskTier
from app.services.stage1 import compute_apri, compute_fib4


class Stage1ModelUnavailableError(RuntimeError):
    pass


@dataclass
class Stage1MLPrediction:
    risk_tier: RiskTier
    probability: float
    model_version: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _coerce_sex(value: str | None) -> str:
    if not value:
        return "F"
    normalized = str(value).strip().upper()
    return "M" if normalized.startswith("M") else "F"


def _default_hypertension(age: int, bmi: float, type2dm: bool) -> int:
    return int(type2dm or bmi >= 30.0 or age >= 60)


def _default_dyslipidemia(bmi: float, type2dm: bool) -> int:
    return int(type2dm or bmi >= 28.0)


def _default_albumin(ast: float) -> float:
    return _clamp(4.3 - 0.0025 * max(ast - 35.0, 0.0), 2.0, 5.5)


def _default_bilirubin(ast: float, alt: float, type2dm: bool) -> float:
    value = 0.65 + 0.002 * max(ast - 30.0, 0.0) + 0.0015 * max(alt - 30.0, 0.0)
    if type2dm:
        value += 0.1
    return _clamp(value, 0.1, 8.0)


def _default_ggt(ast: float, bmi: float, type2dm: bool) -> float:
    value = 22.0 + 0.5 * ast + 1.1 * max(bmi - 25.0, 0.0)
    if type2dm:
        value += 8.0
    return _clamp(value, 10.0, 800.0)


def _default_inr(ast: float) -> float:
    return _clamp(0.96 + 0.0004 * max(ast - 25.0, 0.0), 0.8, 2.5)


def _default_hba1c(type2dm: bool, bmi: float) -> float:
    if type2dm:
        return _clamp(7.1 + 0.02 * max(bmi - 28.0, 0.0), 4.5, 12.0)
    return _clamp(5.3 + 0.015 * max(bmi - 25.0, 0.0), 4.5, 12.0)


def _default_triglycerides(type2dm: bool, bmi: float) -> float:
    value = 118.0 + 2.7 * max(bmi - 25.0, 0.0)
    if type2dm:
        value += 40.0
    return _clamp(value, 50.0, 700.0)


def _build_stage1_feature_payload(
    *,
    patient_sex: str | None,
    age: int,
    bmi: float,
    type2dm: bool,
    ast: float,
    alt: float,
    platelets: float,
    ast_uln: float,
) -> dict[str, Any]:
    sex = _coerce_sex(patient_sex)
    hypertension = _default_hypertension(age=age, bmi=bmi, type2dm=type2dm)
    dyslipidemia = _default_dyslipidemia(bmi=bmi, type2dm=type2dm)

    fib4_input = compute_fib4(age=age, ast=ast, platelets=platelets, alt=alt)
    apri_input = compute_apri(ast=ast, ast_uln=ast_uln, platelets=platelets)
    ast_alt_ratio = ast / alt

    return {
        "age_years": int(age),
        "sex": sex,
        "bmi": float(bmi),
        "type2dm": int(bool(type2dm)),
        "hypertension": hypertension,
        "dyslipidemia": dyslipidemia,
        "ast_u_l": float(ast),
        "alt_u_l": float(alt),
        "platelets_10e9_l": float(platelets),
        "ast_uln_u_l": float(ast_uln),
        "albumin_g_dl": _default_albumin(ast=float(ast)),
        "total_bilirubin_mg_dl": _default_bilirubin(ast=float(ast), alt=float(alt), type2dm=bool(type2dm)),
        "ggt_u_l": _default_ggt(ast=float(ast), bmi=float(bmi), type2dm=bool(type2dm)),
        "inr": _default_inr(ast=float(ast)),
        "hba1c_pct": _default_hba1c(type2dm=bool(type2dm), bmi=float(bmi)),
        "triglycerides_mg_dl": _default_triglycerides(type2dm=bool(type2dm), bmi=float(bmi)),
        "fib4_input": float(fib4_input),
        "apri_input": float(apri_input),
        "ast_alt_ratio": float(ast_alt_ratio),
    }


def _read_model_version_from_metadata(artifact_dir: Path) -> str:
    metadata_path = artifact_dir / "stage1_run_metadata.json"
    if not metadata_path.exists():
        return "clinical-stage1-gbdt:v1"
    try:
        payload = json.loads(metadata_path.read_text())
        name = str(payload.get("model_name", "clinical-stage1-gbdt"))
        version = str(payload.get("model_version", "v1"))
        return f"{name}:{version}"
    except Exception:
        return "clinical-stage1-gbdt:v1"


@lru_cache(maxsize=4)
def _load_stage1_artifacts(artifact_dir_raw: str):
    artifact_dir = Path(artifact_dir_raw)
    required_files = [
        artifact_dir / "stage1_preprocessor.joblib",
        artifact_dir / "stage1_classifier.joblib",
        artifact_dir / "stage1_reg_probability.joblib",
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise Stage1ModelUnavailableError(
            "Stage 1 ML artifacts missing: " + ", ".join(missing)
        )

    try:
        import joblib

        preprocessor = joblib.load(required_files[0])
        classifier = joblib.load(required_files[1])
        reg_probability = joblib.load(required_files[2])
    except Exception as exc:
        raise Stage1ModelUnavailableError(
            f"Failed to load Stage 1 ML artifacts from {artifact_dir}"
        ) from exc

    model_version = _read_model_version_from_metadata(artifact_dir)
    return preprocessor, classifier, reg_probability, model_version


def predict_stage1_ml(
    *,
    patient_sex: str | None,
    age: int,
    bmi: float,
    type2dm: bool,
    ast: float,
    alt: float,
    platelets: float,
    ast_uln: float,
    artifact_dir: Path,
    model_version_override: str | None = None,
) -> Stage1MLPrediction:
    try:
        import pandas as pd
    except Exception as exc:
        raise Stage1ModelUnavailableError("pandas is required for Stage 1 ML inference") from exc

    preprocessor, classifier, reg_probability, default_model_version = _load_stage1_artifacts(
        str(artifact_dir.resolve())
    )

    feature_payload = _build_stage1_feature_payload(
        patient_sex=patient_sex,
        age=age,
        bmi=bmi,
        type2dm=type2dm,
        ast=ast,
        alt=alt,
        platelets=platelets,
        ast_uln=ast_uln,
    )

    frame = pd.DataFrame([feature_payload])
    transformed = preprocessor.transform(frame)

    predicted_tier_raw = str(classifier.predict(transformed)[0]).upper()
    try:
        predicted_tier = RiskTier(predicted_tier_raw)
    except ValueError as exc:
        raise Stage1ModelUnavailableError(
            f"Unexpected Stage 1 classifier output label: {predicted_tier_raw}"
        ) from exc

    predicted_probability = float(reg_probability.predict(transformed)[0])
    probability = round(_clamp(predicted_probability, 0.0, 0.95), 4)

    return Stage1MLPrediction(
        risk_tier=predicted_tier,
        probability=probability,
        model_version=model_version_override or default_model_version,
    )
