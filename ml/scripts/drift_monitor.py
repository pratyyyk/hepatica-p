from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml


def js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = p / np.sum(p)
    q = q / np.sum(q)
    m = 0.5 * (p + q)
    kl_pm = np.sum(np.where(p > 0, p * np.log2(p / m), 0))
    kl_qm = np.sum(np.where(q > 0, q * np.log2(q / m), 0))
    return float(0.5 * (kl_pm + kl_qm))


def main() -> None:
    cfg = yaml.safe_load(Path("configs/train.yaml").read_text())
    artifact_dir = Path(cfg["artifact_dir"])

    baseline_metrics_path = artifact_dir / "metrics.json"
    baseline_classes_path = artifact_dir / "classes.json"
    recent_distribution_path = artifact_dir / "recent_prediction_distribution.json"

    if not baseline_metrics_path.exists() or not baseline_classes_path.exists():
        print("Baseline artifacts missing. Run training first.")
        raise SystemExit(1)

    classes = json.loads(baseline_classes_path.read_text())
    if not recent_distribution_path.exists():
        payload = {
            "status": "NO_RECENT_DISTRIBUTION",
            "message": "Expected recent_prediction_distribution.json with class counts.",
            "classes": classes,
        }
        print(json.dumps(payload, indent=2))
        return

    recent = json.loads(recent_distribution_path.read_text())
    recent_counts = np.array([float(recent.get(c, 0.0)) for c in classes])

    baseline = json.loads(baseline_metrics_path.read_text())
    baseline_recall = baseline.get("val_per_class_recall", {})
    baseline_counts = np.array([max(baseline_recall.get(c, 0.01), 0.01) for c in classes])

    score = js_divergence(baseline_counts, recent_counts)

    payload = {
        "classes": classes,
        "js_divergence": round(score, 6),
        "status": "ALERT" if score > 0.15 else "OK",
        "threshold": 0.15,
    }
    print(json.dumps(payload, indent=2))

    if score > 0.15:
        raise SystemExit("Drift alert threshold exceeded")


if __name__ == "__main__":
    main()
