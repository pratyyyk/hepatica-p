from __future__ import annotations

from dataclasses import dataclass

from app.db.models import ClinicalAssessment, FibrosisPrediction


@dataclass
class StiffnessProxyResult:
    estimated_kpa: float
    source: str
    features: dict[str, float]


def _stage_weight(top_stage: str | None) -> float:
    mapping = {"F0": 0.0, "F1": 1.6, "F2": 3.8, "F3": 6.2, "F4": 8.4}
    return mapping.get(str(top_stage or "").upper(), 2.0)


def estimate_stiffness_proxy(
    *,
    clinical: ClinicalAssessment | None,
    fibrosis: FibrosisPrediction | None,
) -> StiffnessProxyResult:
    fib4 = float(clinical.fib4) if clinical else 1.4
    apri = float(clinical.apri) if clinical else 0.6
    stage_weight = _stage_weight(fibrosis.top1_stage if fibrosis else None)
    stage_prob = float(fibrosis.top1_probability) if fibrosis else 0.55
    bmi = float(clinical.bmi) if clinical else 27.5
    type2dm = 1.0 if clinical and clinical.type2dm else 0.0

    raw = (
        4.8
        + 1.9 * max(fib4 - 1.0, 0.0)
        + 2.3 * max(apri - 0.4, 0.0)
        + stage_weight
        + 1.8 * stage_prob
        + 0.06 * max(bmi - 25.0, 0.0)
        + 0.9 * type2dm
    )
    estimated = max(2.0, min(75.0, raw))
    return StiffnessProxyResult(
        estimated_kpa=round(float(estimated), 3),
        source="PROXY",
        features={
            "fib4": round(fib4, 4),
            "apri": round(apri, 4),
            "stage_weight": round(stage_weight, 4),
            "stage_probability": round(stage_prob, 4),
            "bmi": round(bmi, 3),
            "type2dm": type2dm,
        },
    )
