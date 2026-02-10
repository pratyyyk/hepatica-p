#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data import create_dataloaders, load_splits  # noqa: E402
from src.metrics import compute_metrics  # noqa: E402
from src.modeling import TemperatureScaler, build_model  # noqa: E402


def _predict_logits(model: nn.Module, loader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    logits_all: list[np.ndarray] = []
    labels_all: list[np.ndarray] = []
    with torch.no_grad():
        for x, y in loader:
            x = x.to(device)
            logits = model(x).detach().cpu().numpy()
            logits_all.append(logits)
            labels_all.append(y.numpy())
    return np.concatenate(logits_all, axis=0), np.concatenate(labels_all, axis=0)


def _fit_temperature(logits: torch.Tensor, labels: torch.Tensor, device: torch.device) -> float:
    scaler = TemperatureScaler().to(device)
    logits = logits.to(device)
    labels = labels.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.LBFGS([scaler.temperature], lr=0.05, max_iter=60)

    def closure():
        optimizer.zero_grad()
        loss = criterion(scaler(logits), labels)
        loss.backward()
        return loss

    optimizer.step(closure)
    temp = float(torch.clamp(scaler.temperature, min=0.05).detach().cpu().item())
    return temp


def main() -> None:
    cfg = yaml.safe_load((ROOT / "configs" / "train.yaml").read_text())
    artifact_dir = Path(cfg["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    classes_path = artifact_dir / "classes.json"
    split_path = artifact_dir / "split_indices.json"
    model_path = artifact_dir / "fibrosis_model.pt"

    if not classes_path.exists() or not split_path.exists() or not model_path.exists():
        raise SystemExit(
            "Missing Stage 2 prerequisites. Expected: "
            f"{classes_path}, {split_path}, {model_path}. "
            "Run: python scripts/train.py"
        )

    classes = json.loads(classes_path.read_text())
    split = load_splits(split_path)

    _, _, _, val_loader, test_loader = create_dataloaders(
        data_root=Path(cfg["data_root"]),
        image_size=cfg["image_size"],
        batch_size=cfg["batch_size"],
        # Keep evaluation single-process to avoid macOS multiprocessing spawn issues.
        num_workers=0,
        split=split,
    )

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    model = build_model(num_classes=len(classes), pretrained=False).to(device)
    state = torch.load(model_path, map_location=device)
    model.load_state_dict(state)
    model.eval()

    val_logits_np, val_labels_np = _predict_logits(model, val_loader, device)
    temperature = _fit_temperature(
        torch.tensor(val_logits_np, dtype=torch.float32),
        torch.tensor(val_labels_np, dtype=torch.long),
        device=device,
    )

    (artifact_dir / "temperature_scaling.json").write_text(
        json.dumps({"temperature": round(float(temperature), 6)}, indent=2)
    )

    val_preds = np.argmax(val_logits_np / float(temperature), axis=1).tolist()
    val_metrics = compute_metrics(val_labels_np.tolist(), val_preds, classes)

    test_logits_np, test_labels_np = _predict_logits(model, test_loader, device)
    test_preds = np.argmax(test_logits_np / float(temperature), axis=1).tolist()
    test_metrics = compute_metrics(test_labels_np.tolist(), test_preds, classes)

    summary = {
        "val_accuracy": val_metrics.accuracy,
        "val_macro_f1": val_metrics.macro_f1,
        "val_per_class_recall": val_metrics.per_class_recall,
        "test_accuracy": test_metrics.accuracy,
        "test_macro_f1": test_metrics.macro_f1,
        "test_per_class_recall": test_metrics.per_class_recall,
        "thresholds": {
            "required_val_macro_f1": 0.72,
            "required_val_recall_F2_F4": 0.65,
        },
    }
    (artifact_dir / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

