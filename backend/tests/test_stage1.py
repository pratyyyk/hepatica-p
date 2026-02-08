import pytest

from app.core.enums import RiskTier
from app.services.stage1 import compute_apri, compute_fib4, run_stage1


def test_compute_fib4_basic():
    fib4 = compute_fib4(age=55, ast=80, platelets=150, alt=60)
    assert round(fib4, 4) == 3.7869


def test_compute_apri_basic():
    apri = compute_apri(ast=80, ast_uln=40, platelets=150)
    assert round(apri, 4) == 1.3333


def test_stage1_high_risk_with_bmi_t2dm_boost():
    result = run_stage1(
        age=55,
        ast=80,
        alt=60,
        platelets=150,
        ast_uln=40,
        bmi=31,
        type2dm=True,
    )
    assert result.risk_tier == RiskTier.HIGH
    assert result.probability == 0.87


@pytest.mark.parametrize(
    "fib4,apri,expected",
    [
        (2.68, 0.2, RiskTier.HIGH),
        (1.5, 0.4, RiskTier.MODERATE),
        (1.2, 0.4, RiskTier.LOW),
        (1.0, 0.6, RiskTier.MODERATE),
    ],
)
def test_risk_tier_boundaries(fib4, apri, expected):
    from app.services.stage1 import map_risk_tier

    assert map_risk_tier(fib4, apri) == expected
