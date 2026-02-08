import math
from dataclasses import dataclass

from app.core.enums import RiskTier


@dataclass
class Stage1Result:
    fib4: float
    apri: float
    risk_tier: RiskTier
    probability: float
    model_version: str = "clinical-rule-engine:v1"


def compute_fib4(age: int, ast: float, platelets: float, alt: float) -> float:
    if alt <= 0 or platelets <= 0:
        raise ValueError("ALT and platelets must be greater than 0")
    return (age * ast) / (platelets * math.sqrt(alt))


def compute_apri(ast: float, ast_uln: float, platelets: float) -> float:
    if ast_uln <= 0 or platelets <= 0:
        raise ValueError("AST_ULN and platelets must be greater than 0")
    return ((ast / ast_uln) * 100) / platelets


def map_risk_tier(fib4: float, apri: float) -> RiskTier:
    if fib4 > 2.67 or apri >= 1.0:
        return RiskTier.HIGH
    if (1.3 <= fib4 <= 2.67) or (0.5 <= apri < 1.0):
        return RiskTier.MODERATE
    return RiskTier.LOW


def map_probability(risk_tier: RiskTier, bmi: float, type2dm: bool) -> float:
    base = {
        RiskTier.LOW: 0.20,
        RiskTier.MODERATE: 0.55,
        RiskTier.HIGH: 0.82,
    }[risk_tier]
    if bmi >= 30 and type2dm:
        base += 0.05
    return min(base, 0.95)


def run_stage1(
    age: int,
    ast: float,
    alt: float,
    platelets: float,
    ast_uln: float,
    bmi: float,
    type2dm: bool,
) -> Stage1Result:
    fib4 = round(compute_fib4(age=age, ast=ast, platelets=platelets, alt=alt), 4)
    apri = round(compute_apri(ast=ast, ast_uln=ast_uln, platelets=platelets), 4)
    risk_tier = map_risk_tier(fib4=fib4, apri=apri)
    probability = round(map_probability(risk_tier=risk_tier, bmi=bmi, type2dm=type2dm), 4)
    return Stage1Result(fib4=fib4, apri=apri, risk_tier=risk_tier, probability=probability)
