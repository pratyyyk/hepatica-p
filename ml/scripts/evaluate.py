from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data import create_dataloaders, load_splits
from src.metrics import compute_metrics
from src.modeling import build_model


def main() -> None:
    cfg = yaml.safe_load(Path("configs/train.yaml").read_text())
    artifact_dir = Path(cfg["artifact_dir"])

    classes = json.loads((artifact_dir / "classes.json").read_text())
    split = load_splits(artifact_dir / "split_indices.json")

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
    state = torch.load(artifact_dir / "fibrosis_model.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    temperature = json.loads((artifact_dir / "temperature_scaling.json").read_text())["temperature"]

    def eval_loader(loader):
        logits_all = []
        labels_all = []
        with torch.no_grad():
            for x, y in loader:
                x = x.to(device)
                logits = model(x).cpu().numpy()
                logits_all.append(logits)
                labels_all.append(y.numpy())

        logits = np.concatenate(logits_all, axis=0) / float(temperature)
        labels = np.concatenate(labels_all, axis=0)
        preds = np.argmax(logits, axis=1)
        return compute_metrics(labels.tolist(), preds.tolist(), classes)

    val = eval_loader(val_loader)
    test = eval_loader(test_loader)

    payload = {
        "val_accuracy": val.accuracy,
        "val_macro_f1": val.macro_f1,
        "val_per_class_recall": val.per_class_recall,
        "test_accuracy": test.accuracy,
        "test_macro_f1": test.macro_f1,
        "test_per_class_recall": test.per_class_recall,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
