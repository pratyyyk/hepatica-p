from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, f1_score, recall_score


@dataclass
class EvalMetrics:
    accuracy: float
    macro_f1: float
    per_class_recall: dict[str, float]
    report: dict


def compute_metrics(y_true: list[int], y_pred: list[int], class_names: list[str]) -> EvalMetrics:
    accuracy = float(accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro"))
    recalls = recall_score(y_true, y_pred, average=None, labels=list(range(len(class_names))))
    per_class_recall = {cls: float(recalls[idx]) for idx, cls in enumerate(class_names)}
    report = classification_report(
        y_true,
        y_pred,
        target_names=class_names,
        labels=list(range(len(class_names))),
        output_dict=True,
        zero_division=0,
    )
    return EvalMetrics(accuracy=accuracy, macro_f1=macro_f1, per_class_recall=per_class_recall, report=report)


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - np.max(logits, axis=1, keepdims=True)
    exps = np.exp(logits)
    return exps / np.sum(exps, axis=1, keepdims=True)
