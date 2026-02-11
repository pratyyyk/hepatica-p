from enum import Enum


class RiskTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class FibrosisStage(str, Enum):
    F0 = "F0"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"


class ConfidenceFlag(str, Enum):
    NORMAL = "NORMAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class EscalationFlag(str, Enum):
    NONE = "NONE"
    SEVERE_STAGE_REVIEW = "SEVERE_STAGE_REVIEW"


class Stage3RiskTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
