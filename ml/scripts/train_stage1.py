#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stage1_data import (
    CLASS_ORDER,
    FEATURE_COLUMNS,
    load_stage1_dataset,
    normalize_stage1_config_paths,
)
from src.stage1_explainability import (
    compute_global_importance,
    compute_local_class_summary,
    compute_local_regression_summary,
)
from src.stage1_modeling import (
    check_strict_gates,
    evaluate_stage1_models,
    fit_stage1_models,
    save_stage1_models,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Stage 1 tabular ML models")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/Users/praty/hepatica-p/ml/configs/train_stage1.yaml"),
    )
    parser.add_argument("--max-rows", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text())
    config = normalize_stage1_config_paths(config, repo_root=ROOT.parent)

    max_rows = args.max_rows
    dataset = load_stage1_dataset(config, max_rows=max_rows)

    models = fit_stage1_models(dataset.train_df, config)

    val_eval = evaluate_stage1_models(models=models, df=dataset.val_df, split_name="val", class_order=CLASS_ORDER)
    test_eval = evaluate_stage1_models(models=models, df=dataset.test_df, split_name="test", class_order=CLASS_ORDER)

    explain_cfg = config["explainability"]
    global_explain = compute_global_importance(
        models=models,
        eval_bundle=val_eval,
        random_state=int(config["seed"]),
        n_repeats=int(explain_cfg["permutation_n_repeats"]),
        max_samples=int(explain_cfg["permutation_max_samples"]),
    )
    local_class_explain = compute_local_class_summary(
        models=models,
        eval_bundle=val_eval,
        top_n=int(explain_cfg["local_top_n"]),
    )
    local_reg_explain = compute_local_regression_summary(
        models=models,
        eval_bundle=val_eval,
        top_n=int(explain_cfg["local_top_n"]),
    )

    gates = config["gates"]
    gate_failures = check_strict_gates(
        val_metrics=val_eval.metrics,
        test_metrics=test_eval.metrics,
        gates=gates,
    )

    artifact_dir = Path(config["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    save_stage1_models(models=models, artifact_dir=artifact_dir)

    model_version = datetime.now(timezone.utc).strftime(f"v%Y%m%d.%H%M.seed{int(config['seed'])}")

    feature_manifest = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "feature_columns_raw": FEATURE_COLUMNS,
        "feature_columns_transformed": models.feature_names,
        "feature_baseline": models.feature_baseline.tolist(),
        "class_order_target": CLASS_ORDER,
        "classifier_classes_internal": models.classifier.classes_.tolist(),
    }

    confusion_payload = {
        "val": val_eval.metrics["confusion_matrix"],
        "test": test_eval.metrics["confusion_matrix"],
    }
    calibration_payload = {
        "val": val_eval.metrics["calibration"],
        "test": test_eval.metrics["calibration"],
    }

    _write_json(artifact_dir / "stage1_feature_manifest.json", feature_manifest)
    _write_json(artifact_dir / "stage1_metrics_val.json", val_eval.metrics)
    _write_json(artifact_dir / "stage1_metrics_test.json", test_eval.metrics)
    _write_json(artifact_dir / "stage1_confusion_matrix.json", confusion_payload)
    _write_json(artifact_dir / "stage1_calibration.json", calibration_payload)
    _write_json(artifact_dir / "stage1_explain_global.json", global_explain)
    _write_json(artifact_dir / "stage1_explain_local_class.json", local_class_explain)
    _write_json(artifact_dir / "stage1_explain_local_regression.json", local_reg_explain)

    run_metadata = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": int(config["seed"]),
        "schema_version": config["schema_version"],
        "data_path": str(config["data_path"]),
        "rows_used": {
            "total": int(len(dataset.full_df)),
            "train": int(len(dataset.train_df)),
            "val": int(len(dataset.val_df)),
            "test": int(len(dataset.test_df)),
            "max_rows": max_rows,
        },
        "strict_gates": gates,
        "gate_failures": gate_failures,
        "gates_passed": len(gate_failures) == 0,
        "artifacts": {
            "classifier": "stage1_classifier.joblib",
            "reg_probability": "stage1_reg_probability.joblib",
            "reg_latent": "stage1_reg_latent.joblib",
            "preprocessor": "stage1_preprocessor.joblib",
            "metrics_val": "stage1_metrics_val.json",
            "metrics_test": "stage1_metrics_test.json",
            "confusion": "stage1_confusion_matrix.json",
            "calibration": "stage1_calibration.json",
            "explain_global": "stage1_explain_global.json",
            "explain_local_class": "stage1_explain_local_class.json",
            "explain_local_regression": "stage1_explain_local_regression.json",
        },
    }
    _write_json(artifact_dir / "stage1_run_metadata.json", run_metadata)

    summary = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "val_macro_f1": val_eval.metrics["classification"]["macro_f1"],
        "test_macro_f1": test_eval.metrics["classification"]["macro_f1"],
        "val_probability_mae": val_eval.metrics["regression"]["probability_rule"]["mae"],
        "val_latent_mae": val_eval.metrics["regression"]["latent_fibrosis_score"]["mae"],
        "val_ece": val_eval.metrics["classification"]["ece"],
        "gate_failures": gate_failures,
    }
    print(json.dumps(summary, indent=2))

    if gate_failures:
        raise SystemExit("Strict gates failed: " + " | ".join(gate_failures))


if __name__ == "__main__":
    main()
