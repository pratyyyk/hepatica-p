from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .stage1_data import (
    CLASS_ORDER,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
)


@dataclass
class Stage1Models:
    preprocessor: ColumnTransformer
    classifier: CalibratedClassifierCV
    reg_probability: HistGradientBoostingRegressor
    reg_latent: HistGradientBoostingRegressor
    feature_names: list[str]
    feature_baseline: np.ndarray


@dataclass
class Stage1EvalBundle:
    split_name: str
    X_raw: pd.DataFrame
    X_transformed: np.ndarray
    y_cls: np.ndarray
    y_prob: np.ndarray
    y_latent: np.ndarray
    pred_cls: np.ndarray
    pred_probs: np.ndarray
    pred_prob: np.ndarray
    pred_latent: np.ndarray
    metrics: dict[str, Any]


def _build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        (
            "onehot",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
        ),
    ])

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


def _classifier_from_config(cfg: dict[str, Any]) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=float(cfg["learning_rate"]),
        max_iter=int(cfg["max_iter"]),
        max_depth=int(cfg["max_depth"]),
        min_samples_leaf=int(cfg["min_samples_leaf"]),
        l2_regularization=float(cfg["l2_regularization"]),
        class_weight=str(cfg["class_weight"]),
        random_state=int(cfg["random_state"]),
    )


def _regressor_from_config(cfg: dict[str, Any]) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=float(cfg["learning_rate"]),
        max_iter=int(cfg["max_iter"]),
        max_depth=int(cfg["max_depth"]),
        min_samples_leaf=int(cfg["min_samples_leaf"]),
        l2_regularization=float(cfg["l2_regularization"]),
        random_state=int(cfg["random_state"]),
    )


def _expected_calibration_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    pred_probs: np.ndarray,
    n_bins: int = 10,
) -> tuple[float, list[dict[str, float]]]:
    confidences = np.max(pred_probs, axis=1)
    correctness = (y_true == y_pred).astype(np.float64)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    details: list[dict[str, float]] = []

    total = len(y_true)
    for i in range(n_bins):
        left = bins[i]
        right = bins[i + 1]
        if i == n_bins - 1:
            mask = (confidences >= left) & (confidences <= right)
        else:
            mask = (confidences >= left) & (confidences < right)

        count = int(mask.sum())
        if count == 0:
            details.append(
                {
                    "bin_left": float(left),
                    "bin_right": float(right),
                    "count": 0,
                    "avg_confidence": 0.0,
                    "accuracy": 0.0,
                    "gap": 0.0,
                }
            )
            continue

        avg_conf = float(confidences[mask].mean())
        acc = float(correctness[mask].mean())
        gap = abs(acc - avg_conf)
        ece += (count / total) * gap

        details.append(
            {
                "bin_left": float(left),
                "bin_right": float(right),
                "count": count,
                "avg_confidence": avg_conf,
                "accuracy": acc,
                "gap": float(gap),
            }
        )

    return float(ece), details


def fit_stage1_models(train_df: pd.DataFrame, config: dict[str, Any]) -> Stage1Models:
    pre = _build_preprocessor()

    X_train = train_df[FEATURE_COLUMNS]
    y_cls = train_df["risk_tier_rule"].astype(str).to_numpy()
    y_prob = train_df["probability_rule"].astype(float).to_numpy()
    y_latent = train_df["latent_fibrosis_score"].astype(float).to_numpy()

    X_train_t = pre.fit_transform(X_train)
    X_train_t = np.asarray(X_train_t, dtype=np.float64)

    cls_cfg = config["models"]["classifier"]
    classifier_base = _classifier_from_config(cls_cfg)
    classifier = CalibratedClassifierCV(
        estimator=classifier_base,
        method="isotonic",
        cv=int(config["models"]["classifier_calibration_cv"]),
    )
    classifier.fit(X_train_t, y_cls)

    reg_cfg = config["models"]["regressor"]
    reg_probability = _regressor_from_config(reg_cfg)
    reg_probability.fit(X_train_t, y_prob)

    reg_latent = _regressor_from_config(reg_cfg)
    reg_latent.fit(X_train_t, y_latent)

    feature_names = pre.get_feature_names_out().tolist()
    feature_baseline = np.median(X_train_t, axis=0)

    return Stage1Models(
        preprocessor=pre,
        classifier=classifier,
        reg_probability=reg_probability,
        reg_latent=reg_latent,
        feature_names=feature_names,
        feature_baseline=feature_baseline,
    )


def evaluate_stage1_models(
    models: Stage1Models,
    df: pd.DataFrame,
    split_name: str,
    class_order: list[str] | None = None,
) -> Stage1EvalBundle:
    classes = class_order or CLASS_ORDER

    X_raw = df[FEATURE_COLUMNS].copy()
    y_cls = df["risk_tier_rule"].astype(str).to_numpy()
    y_prob = df["probability_rule"].astype(float).to_numpy()
    y_latent = df["latent_fibrosis_score"].astype(float).to_numpy()

    X_t = models.preprocessor.transform(X_raw)
    X_t = np.asarray(X_t, dtype=np.float64)

    pred_probs = models.classifier.predict_proba(X_t)
    pred_cls = models.classifier.predict(X_t).astype(str)

    pred_prob = models.reg_probability.predict(X_t).astype(np.float64)
    pred_latent = models.reg_latent.predict(X_t).astype(np.float64)

    accuracy = float(accuracy_score(y_cls, pred_cls))
    macro_f1 = float(f1_score(y_cls, pred_cls, labels=classes, average="macro", zero_division=0))
    recalls = recall_score(y_cls, pred_cls, labels=classes, average=None, zero_division=0)
    per_class_recall = {label: float(recalls[idx]) for idx, label in enumerate(classes)}

    ece, ece_bins = _expected_calibration_error(y_true=y_cls, y_pred=pred_cls, pred_probs=pred_probs)

    cls_metrics = {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class_recall": per_class_recall,
        "classes_order": classes,
        "ece": ece,
    }

    reg_metrics = {
        "probability_rule": {
            "mae": float(mean_absolute_error(y_prob, pred_prob)),
            "rmse": float(np.sqrt(mean_squared_error(y_prob, pred_prob))),
            "r2": float(r2_score(y_prob, pred_prob)),
        },
        "latent_fibrosis_score": {
            "mae": float(mean_absolute_error(y_latent, pred_latent)),
            "rmse": float(np.sqrt(mean_squared_error(y_latent, pred_latent))),
            "r2": float(r2_score(y_latent, pred_latent)),
        },
    }

    confusion = confusion_matrix(y_cls, pred_cls, labels=classes)

    metrics = {
        "split": split_name,
        "classification": cls_metrics,
        "regression": reg_metrics,
        "confusion_matrix": {
            "labels": classes,
            "matrix": confusion.astype(int).tolist(),
        },
        "calibration": {
            "ece": ece,
            "bins": ece_bins,
        },
    }

    return Stage1EvalBundle(
        split_name=split_name,
        X_raw=X_raw,
        X_transformed=X_t,
        y_cls=y_cls,
        y_prob=y_prob,
        y_latent=y_latent,
        pred_cls=pred_cls,
        pred_probs=pred_probs,
        pred_prob=pred_prob,
        pred_latent=pred_latent,
        metrics=metrics,
    )


def check_strict_gates(
    val_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    gates: dict[str, Any],
) -> list[str]:
    failures: list[str] = []

    def _assert(metric: float, threshold: float, cmp: str, label: str) -> None:
        ok = metric >= threshold if cmp == ">=" else metric <= threshold
        if not ok:
            failures.append(f"{label}: expected {cmp} {threshold}, got {metric:.6f}")

    _assert(
        val_metrics["classification"]["macro_f1"],
        float(gates["val_macro_f1_min"]),
        ">=",
        "val_macro_f1",
    )
    _assert(
        val_metrics["classification"]["per_class_recall"]["HIGH"],
        float(gates["val_recall_high_min"]),
        ">=",
        "val_recall_high",
    )
    _assert(
        val_metrics["classification"]["per_class_recall"]["MODERATE"],
        float(gates["val_recall_moderate_min"]),
        ">=",
        "val_recall_moderate",
    )
    _assert(
        test_metrics["classification"]["macro_f1"],
        float(gates["test_macro_f1_min"]),
        ">=",
        "test_macro_f1",
    )
    _assert(
        val_metrics["regression"]["probability_rule"]["mae"],
        float(gates["val_probability_mae_max"]),
        "<=",
        "val_probability_mae",
    )
    _assert(
        val_metrics["regression"]["latent_fibrosis_score"]["mae"],
        float(gates["val_latent_mae_max"]),
        "<=",
        "val_latent_mae",
    )
    _assert(
        val_metrics["classification"]["ece"],
        float(gates["val_ece_max"]),
        "<=",
        "val_ece",
    )

    return failures


def save_stage1_models(models: Stage1Models, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(models.preprocessor, artifact_dir / "stage1_preprocessor.joblib")
    joblib.dump(models.classifier, artifact_dir / "stage1_classifier.joblib")
    joblib.dump(models.reg_probability, artifact_dir / "stage1_reg_probability.joblib")
    joblib.dump(models.reg_latent, artifact_dir / "stage1_reg_latent.joblib")


def load_stage1_models(artifact_dir: Path) -> Stage1Models:
    preprocessor = joblib.load(artifact_dir / "stage1_preprocessor.joblib")
    classifier = joblib.load(artifact_dir / "stage1_classifier.joblib")
    reg_probability = joblib.load(artifact_dir / "stage1_reg_probability.joblib")
    reg_latent = joblib.load(artifact_dir / "stage1_reg_latent.joblib")

    feature_names = preprocessor.get_feature_names_out().tolist()

    feature_manifest_path = artifact_dir / "stage1_feature_manifest.json"
    if feature_manifest_path.exists():
        payload = json.loads(feature_manifest_path.read_text())
        baseline = np.asarray(payload["feature_baseline"], dtype=np.float64)
    else:
        baseline = np.zeros(len(feature_names), dtype=np.float64)

    return Stage1Models(
        preprocessor=preprocessor,
        classifier=classifier,
        reg_probability=reg_probability,
        reg_latent=reg_latent,
        feature_names=feature_names,
        feature_baseline=baseline,
    )
