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

from src.stage1_data import normalize_stage1_config_paths  # noqa: E402
from src.stage1_modeling import check_strict_gates  # noqa: E402


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _fail(msg: str) -> None:
    raise SystemExit(msg)


def _fmt(v: float) -> str:
    return f"{v:.6f}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fail-fast checks for Stage 1 + Stage 2 trained metrics.")
    p.add_argument(
        "--stage1-config",
        type=Path,
        default=Path("configs/train_stage1.yaml"),
        help="Stage 1 config (contains strict gates).",
    )
    p.add_argument(
        "--stage2-config",
        type=Path,
        default=Path("configs/train.yaml"),
        help="Stage 2 config (points at ml/artifacts/metrics.json).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- Stage 1 (tabular) ---
    stage1_cfg = yaml.safe_load(args.stage1_config.read_text())
    stage1_cfg = normalize_stage1_config_paths(stage1_cfg, repo_root=ROOT.parent)
    stage1_artifacts = Path(stage1_cfg["artifact_dir"])
    stage1_val_path = stage1_artifacts / "stage1_metrics_val.json"
    stage1_test_path = stage1_artifacts / "stage1_metrics_test.json"

    if not stage1_val_path.exists() or not stage1_test_path.exists():
        _fail(
            "Stage 1 metrics missing. Run: python scripts/train_stage1.py --config configs/train_stage1.yaml"
        )

    stage1_val = _read_json(stage1_val_path)
    stage1_test = _read_json(stage1_test_path)
    failures = check_strict_gates(stage1_val, stage1_test, stage1_cfg["gates"])

    # --- Stage 2 (image) ---
    stage2_cfg = yaml.safe_load(args.stage2_config.read_text())
    stage2_artifacts = Path(stage2_cfg["artifact_dir"])
    stage2_metrics_path = stage2_artifacts / "metrics.json"
    if not stage2_metrics_path.exists():
        _fail("Stage 2 metrics missing. Run: python scripts/train.py")

    stage2 = _read_json(stage2_metrics_path)
    thresholds = stage2.get("thresholds", {}) if isinstance(stage2, dict) else {}
    required_f1 = float(thresholds.get("required_val_macro_f1", 0.72))
    required_recall = float(thresholds.get("required_val_recall_F2_F4", 0.65))

    val_f1 = float(stage2.get("val_macro_f1", 0.0))
    val_recalls = stage2.get("val_per_class_recall", {}) or {}
    val_recall_f2 = float(val_recalls.get("F2", 0.0))
    val_recall_f3 = float(val_recalls.get("F3", 0.0))
    val_recall_f4 = float(val_recalls.get("F4", 0.0))

    stage2_failures: list[str] = []
    if val_f1 < required_f1:
        stage2_failures.append(f"val_macro_f1: expected >= {required_f1}, got {_fmt(val_f1)}")
    for label, value in [("F2", val_recall_f2), ("F3", val_recall_f3), ("F4", val_recall_f4)]:
        if value < required_recall:
            stage2_failures.append(
                f"val_recall_{label}: expected >= {required_recall}, got {_fmt(value)}"
            )

    if failures or stage2_failures:
        out = []
        if failures:
            out.append("Stage 1 gates failed:")
            out.extend([f"- {f}" for f in failures])
        if stage2_failures:
            out.append("Stage 2 gates failed:")
            out.extend([f"- {f}" for f in stage2_failures])
        _fail("\n".join(out))

    stage1_val_acc = stage1_val["classification"].get("accuracy")
    stage1_test_acc = stage1_test["classification"].get("accuracy")
    stage2_val_acc = stage2.get("val_accuracy")
    stage2_test_acc = stage2.get("test_accuracy")

    print("OK: model metrics meet gates")
    print(
        json.dumps(
            {
                "stage1": {
                    "val_accuracy": stage1_val_acc,
                    "val_macro_f1": stage1_val["classification"]["macro_f1"],
                    "test_accuracy": stage1_test_acc,
                    "test_macro_f1": stage1_test["classification"]["macro_f1"],
                },
                "stage2": {
                    "val_accuracy": stage2_val_acc,
                    "val_macro_f1": val_f1,
                    "test_accuracy": stage2_test_acc,
                    "test_macro_f1": float(stage2.get("test_macro_f1", 0.0)),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

