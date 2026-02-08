from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.model_selection import StratifiedShuffleSplit
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms


@dataclass
class SplitResult:
    train_indices: list[int]
    val_indices: list[int]
    test_indices: list[int]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_transforms(image_size: int) -> tuple[transforms.Compose, transforms.Compose]:
    train_tf = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(degrees=10),
            transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    eval_tf = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    return train_tf, eval_tf


def stratified_split(
    targets: list[int],
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> SplitResult:
    if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0):
        raise ValueError("Split ratios must sum to 1.0")

    indices = np.arange(len(targets))
    y = np.array(targets)

    sss_outer = StratifiedShuffleSplit(n_splits=1, test_size=test_ratio, random_state=seed)
    train_val_idx, test_idx = next(sss_outer.split(indices, y))

    val_fraction_of_trainval = val_ratio / (train_ratio + val_ratio)
    sss_inner = StratifiedShuffleSplit(
        n_splits=1,
        test_size=val_fraction_of_trainval,
        random_state=seed,
    )
    train_idx_rel, val_idx_rel = next(
        sss_inner.split(indices[train_val_idx], y[train_val_idx])
    )

    train_idx = train_val_idx[train_idx_rel]
    val_idx = train_val_idx[val_idx_rel]

    return SplitResult(
        train_indices=train_idx.tolist(),
        val_indices=val_idx.tolist(),
        test_indices=test_idx.tolist(),
    )


def save_split_indices(split: SplitResult, output_path: Path) -> None:
    payload = {
        "train": split.train_indices,
        "val": split.val_indices,
        "test": split.test_indices,
    }
    output_path.write_text(json.dumps(payload, indent=2))


def load_splits(path: Path) -> SplitResult:
    payload = json.loads(path.read_text())
    return SplitResult(
        train_indices=payload["train"],
        val_indices=payload["val"],
        test_indices=payload["test"],
    )


def create_dataloaders(
    *,
    data_root: Path,
    image_size: int,
    batch_size: int,
    num_workers: int,
    split: SplitResult,
):
    train_tf, eval_tf = build_transforms(image_size=image_size)

    base_train = datasets.ImageFolder(root=str(data_root), transform=train_tf)
    base_eval = datasets.ImageFolder(root=str(data_root), transform=eval_tf)

    train_ds = Subset(base_train, split.train_indices)
    val_ds = Subset(base_eval, split.val_indices)
    test_ds = Subset(base_eval, split.test_indices)

    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    return base_eval.classes, base_eval.targets, train_loader, val_loader, test_loader
