#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

FEATURE_COLUMNS = [
    "age_years",
    "bmi",
    "type2dm",
    "hypertension",
    "fib4",
    "apri",
    "nfs_proxy",
    "bard_score",
    "stage2_stage_numeric",
    "stage2_top_probability",
    "stiffness_available",
    "stiffness_kpa",
]


def _binary_stats(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }


def pick_threshold(
    *,
    probs: np.ndarray,
    labels: np.ndarray,
    ppv_target: float,
    recall_floor: float,
) -> dict[str, float]:
    best = {"threshold": 0.5, "precision": 0.0, "recall": 0.0}
    for threshold in np.linspace(0.20, 0.95, 151):
        preds = (probs >= threshold).astype(np.int8)
        stats = _binary_stats(labels, preds)
        precision = stats["precision"]
        recall = stats["recall"]
        if recall < recall_floor:
            continue
        if precision >= ppv_target and precision >= best["precision"]:
            best = {"threshold": float(threshold), "precision": precision, "recall": recall}
    if best["precision"] >= ppv_target:
        return best

    # Fallback: highest precision while still meeting recall floor.
    fallback = {"threshold": 0.5, "precision": 0.0, "recall": 0.0}
    for threshold in np.linspace(0.20, 0.95, 151):
        preds = (probs >= threshold).astype(np.int8)
        stats = _binary_stats(labels, preds)
        precision = stats["precision"]
        recall = stats["recall"]
        if recall < recall_floor:
            continue
        if precision > fallback["precision"]:
            fallback = {"threshold": float(threshold), "precision": precision, "recall": recall}
    return fallback


def _evaluate(
    *,
    probs: np.ndarray,
    labels: np.ndarray,
    threshold: float,
) -> dict[str, float]:
    preds = (probs >= threshold).astype(np.int8)
    stats = _binary_stats(labels, preds)
    return {
        **stats,
        "threshold": float(threshold),
        "roc_auc": float(roc_auc_score(labels, probs)),
        "avg_precision": float(average_precision_score(labels, probs)),
        "positive_rate": float(np.mean(preds)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Stage 3 multimodal risk model.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/Users/praty/hepatica-p/ml/configs/train_stage3.yaml"),
    )
    parser.add_argument("--max-rows", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text())
    data_path = Path(config["data_path"])
    artifact_dir = Path(config["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    df = pd.read_parquet(data_path)
    if args.max_rows and args.max_rows > 0 and len(df) > args.max_rows:
        df = (
            df.groupby("split", group_keys=False)
            .apply(lambda g: g.sample(max(1, int(args.max_rows * (len(g) / len(df)))), random_state=int(config["seed"])))
            .reset_index(drop=True)
        )

    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()
    test_df = df[df["split"] == "test"].copy()
    if train_df.empty or val_df.empty or test_df.empty:
        raise SystemExit("Dataset splits are incomplete. Need train/val/test rows.")

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["progression_label_12m"].astype(int).to_numpy()

    model_cfg = config["model"]
    base = HistGradientBoostingClassifier(
        learning_rate=float(model_cfg["learning_rate"]),
        max_iter=int(model_cfg["max_iter"]),
        max_depth=int(model_cfg["max_depth"]),
        min_samples_leaf=int(model_cfg["min_samples_leaf"]),
        l2_regularization=float(model_cfg["l2_regularization"]),
        random_state=int(config["seed"]),
    )
    model = CalibratedClassifierCV(estimator=base, method="isotonic", cv=3)
    model.fit(X_train, y_train)

    val_probs = model.predict_proba(val_df[FEATURE_COLUMNS])[:, 1]
    test_probs = model.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]
    val_labels = val_df["progression_label_12m"].astype(int).to_numpy()
    test_labels = test_df["progression_label_12m"].astype(int).to_numpy()

    gate_cfg = config["gates"]
    threshold_payload = pick_threshold(
        probs=val_probs,
        labels=val_labels,
        ppv_target=float(gate_cfg["ppv_target"]),
        recall_floor=float(gate_cfg["recall_floor"]),
    )

    val_metrics = _evaluate(probs=val_probs, labels=val_labels, threshold=threshold_payload["threshold"])
    test_metrics = _evaluate(probs=test_probs, labels=test_labels, threshold=threshold_payload["threshold"])

    model_version = datetime.now(timezone.utc).strftime(f"v%Y%m%d.%H%M.seed{int(config['seed'])}")
    joblib.dump(model, artifact_dir / "stage3_risk_model.joblib")

    thresholds = {
        "threshold": threshold_payload["threshold"],
        "val_precision": threshold_payload["precision"],
        "val_recall": threshold_payload["recall"],
        "ppv_target": float(gate_cfg["ppv_target"]),
        "recall_floor": float(gate_cfg["recall_floor"]),
    }
    (artifact_dir / "stage3_thresholds.json").write_text(json.dumps(thresholds, indent=2))

    feature_manifest = {
        "feature_columns": FEATURE_COLUMNS,
        "target": "progression_label_12m",
        "schema_version": config["schema_version"],
    }
    (artifact_dir / "stage3_feature_manifest.json").write_text(json.dumps(feature_manifest, indent=2))
    (artifact_dir / "stage3_metrics_val.json").write_text(json.dumps(val_metrics, indent=2))
    (artifact_dir / "stage3_metrics_test.json").write_text(json.dumps(test_metrics, indent=2))

    metadata = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": int(config["seed"]),
        "schema_version": config["schema_version"],
        "rows_used": {
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
            "max_rows": args.max_rows,
        },
        "gates": gate_cfg,
        "gates_passed": bool(
            threshold_payload["precision"] >= float(gate_cfg["ppv_target"])
            and threshold_payload["recall"] >= float(gate_cfg["recall_floor"])
        ),
    }
    (artifact_dir / "stage3_run_metadata.json").write_text(json.dumps(metadata, indent=2))

    summary = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "threshold": threshold_payload,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
    }
    print(json.dumps(summary, indent=2))

    if not metadata["gates_passed"]:
        raise SystemExit(
            "Stage 3 gates failed: expected "
            f"PPV>={gate_cfg['ppv_target']} and recall>={gate_cfg['recall_floor']} "
            f"got PPV={threshold_payload['precision']:.4f} recall={threshold_payload['recall']:.4f}"
        )


if __name__ == "__main__":
    main()
