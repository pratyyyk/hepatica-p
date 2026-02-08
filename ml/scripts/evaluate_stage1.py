#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stage1_data import CLASS_ORDER, load_stage1_dataset, normalize_stage1_config_paths
from src.stage1_modeling import evaluate_stage1_models, load_stage1_models


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def _write_markdown(path: Path, report: dict) -> None:
    val = report["val"]
    test = report["test"]
    lines = [
        "# Stage 1 ML Evaluation",
        "",
        f"- Model name: `{report['model_name']}`",
        f"- Model version: `{report['model_version']}`",
        f"- Evaluated rows: `{report['rows']}`",
        "",
        "## Classification",
        f"- Val macro-F1: `{val['classification']['macro_f1']:.6f}`",
        f"- Test macro-F1: `{test['classification']['macro_f1']:.6f}`",
        f"- Val ECE: `{val['classification']['ece']:.6f}`",
        f"- Test ECE: `{test['classification']['ece']:.6f}`",
        "",
        "## Regression (MAE)",
        f"- Val probability_rule MAE: `{val['regression']['probability_rule']['mae']:.6f}`",
        f"- Val latent_fibrosis_score MAE: `{val['regression']['latent_fibrosis_score']['mae']:.6f}`",
        f"- Test probability_rule MAE: `{test['regression']['probability_rule']['mae']:.6f}`",
        f"- Test latent_fibrosis_score MAE: `{test['regression']['latent_fibrosis_score']['mae']:.6f}`",
    ]
    path.write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Stage 1 tabular ML models")
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

    dataset = load_stage1_dataset(config, max_rows=args.max_rows)
    artifact_dir = Path(config["artifact_dir"])
    models = load_stage1_models(artifact_dir)

    val_eval = evaluate_stage1_models(models=models, df=dataset.val_df, split_name="val", class_order=CLASS_ORDER)
    test_eval = evaluate_stage1_models(models=models, df=dataset.test_df, split_name="test", class_order=CLASS_ORDER)

    run_metadata_path = artifact_dir / "stage1_run_metadata.json"
    model_version = "unknown"
    if run_metadata_path.exists():
        model_version = json.loads(run_metadata_path.read_text()).get("model_version", "unknown")

    confusion_payload = {
        "val": val_eval.metrics["confusion_matrix"],
        "test": test_eval.metrics["confusion_matrix"],
    }
    calibration_payload = {
        "val": val_eval.metrics["calibration"],
        "test": test_eval.metrics["calibration"],
    }

    report = {
        "model_name": config["model_name"],
        "model_version": model_version,
        "rows": {
            "total": int(len(dataset.full_df)),
            "val": int(len(dataset.val_df)),
            "test": int(len(dataset.test_df)),
        },
        "val": val_eval.metrics,
        "test": test_eval.metrics,
    }

    _write_json(artifact_dir / "stage1_metrics_val.json", val_eval.metrics)
    _write_json(artifact_dir / "stage1_metrics_test.json", test_eval.metrics)
    _write_json(artifact_dir / "stage1_confusion_matrix.json", confusion_payload)
    _write_json(artifact_dir / "stage1_calibration.json", calibration_payload)
    _write_json(artifact_dir / "stage1_evaluation_report.json", report)
    _write_markdown(artifact_dir / "stage1_evaluation_report.md", report)

    print(
        json.dumps(
            {
                "model_name": config["model_name"],
                "model_version": model_version,
                "val_macro_f1": val_eval.metrics["classification"]["macro_f1"],
                "test_macro_f1": test_eval.metrics["classification"]["macro_f1"],
                "val_probability_mae": val_eval.metrics["regression"]["probability_rule"]["mae"],
                "val_latent_mae": val_eval.metrics["regression"]["latent_fibrosis_score"]["mae"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
