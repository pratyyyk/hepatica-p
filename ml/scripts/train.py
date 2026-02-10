from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data import create_dataloaders, save_split_indices, seed_everything, stratified_split
from src.metrics import compute_metrics
from src.modeling import TemperatureScaler, build_model, compute_class_weights


def _predict_logits(model: nn.Module, loader, device: torch.device):
    model.eval()
    all_logits = []
    all_labels = []
    with torch.no_grad():
        for x, y in loader:
            x = x.to(device)
            logits = model(x)
            all_logits.append(logits.cpu())
            all_labels.append(y)
    return torch.cat(all_logits), torch.cat(all_labels)


def _evaluate(model: nn.Module, loader, class_names: list[str], device: torch.device):
    logits, labels = _predict_logits(model, loader, device)
    preds = torch.argmax(logits, dim=1).numpy().tolist()
    return compute_metrics(labels.numpy().tolist(), preds, class_names)


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
    cfg = yaml.safe_load(Path("configs/train.yaml").read_text())

    artifact_dir = Path(cfg["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(cfg["seed"])

    from torchvision import datasets

    raw = datasets.ImageFolder(root=str(cfg["data_root"]))
    split = stratified_split(
        targets=raw.targets,
        train_ratio=cfg["train_ratio"],
        val_ratio=cfg["val_ratio"],
        test_ratio=cfg["test_ratio"],
        seed=cfg["seed"],
    )
    save_split_indices(split, artifact_dir / "split_indices.json")

    classes, targets, train_loader, val_loader, test_loader = create_dataloaders(
        data_root=Path(cfg["data_root"]),
        image_size=cfg["image_size"],
        batch_size=cfg["batch_size"],
        num_workers=cfg["num_workers"],
        split=split,
    )

    (artifact_dir / "classes.json").write_text(json.dumps(classes, indent=2))

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    print(f"device={device.type}")
    model = build_model(num_classes=len(classes), pretrained=True).to(device)

    train_targets = [targets[idx] for idx in split.train_indices]
    class_weights = compute_class_weights(train_targets, num_classes=len(classes), device=device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(cfg["learning_rate"]),
        weight_decay=float(cfg["weight_decay"]),
    )

    best_val_f1 = -1.0
    best_epoch = -1
    bad_epochs = 0
    best_path = artifact_dir / "fibrosis_model.pt"

    for epoch in range(int(cfg["epochs"])):
        model.train()
        running_loss = 0.0
        for x, y in tqdm(train_loader, desc=f"epoch {epoch + 1}/{cfg['epochs']}", leave=False):
            x = x.to(device)
            y = y.to(device)

            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item())

        val_metrics = _evaluate(model, val_loader, classes, device)
        avg_loss = running_loss / max(1, len(train_loader))
        print(
            f"epoch={epoch + 1} train_loss={avg_loss:.4f} val_macro_f1={val_metrics.macro_f1:.4f}"
        )

        if val_metrics.macro_f1 > best_val_f1:
            best_val_f1 = val_metrics.macro_f1
            best_epoch = epoch + 1
            bad_epochs = 0
            torch.save(model.state_dict(), best_path)
        else:
            bad_epochs += 1

        if bad_epochs >= int(cfg["early_stopping_patience"]):
            print("Early stopping triggered")
            break

    model.load_state_dict(torch.load(best_path, map_location=device))

    val_logits, val_labels = _predict_logits(model, val_loader, device)
    temperature = _fit_temperature(val_logits, val_labels, device)
    (artifact_dir / "temperature_scaling.json").write_text(
        json.dumps({"temperature": round(temperature, 6)}, indent=2)
    )

    val_logits_scaled = val_logits.numpy() / temperature
    val_preds = np.argmax(val_logits_scaled, axis=1).tolist()
    val_metrics = compute_metrics(val_labels.numpy().tolist(), val_preds, classes)

    test_logits, test_labels = _predict_logits(model, test_loader, device)
    test_logits_scaled = test_logits.numpy() / temperature
    test_preds = np.argmax(test_logits_scaled, axis=1).tolist()
    test_metrics = compute_metrics(test_labels.numpy().tolist(), test_preds, classes)

    summary = {
        "best_epoch": best_epoch,
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

    recalls = val_metrics.per_class_recall
    meets_thresholds = (
        val_metrics.macro_f1 >= 0.72
        and recalls.get("F2", 0.0) >= 0.65
        and recalls.get("F3", 0.0) >= 0.65
        and recalls.get("F4", 0.0) >= 0.65
    )

    print(json.dumps(summary, indent=2))
    if not meets_thresholds:
        raise SystemExit(
            "Model did not meet acceptance thresholds: val_macro_f1>=0.72 and recall(F2,F3,F4)>=0.65"
        )


if __name__ == "__main__":
    main()
