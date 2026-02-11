from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_stage3_synthetic_distribution_and_temporal_shape():
    mod = _load_module(
        "stage3_synth_generator",
        REPO_ROOT / "ml" / "scripts" / "generate_stage3_synthetic.py",
    )
    arrays = mod.generate_stage3_dataset_arrays(
        patients=800,
        visits=6,
        seed=77,
        schema_version=mod.SCHEMA_VERSION_DEFAULT,
    )

    assert list(arrays.keys()) == mod.COLUMN_ORDER
    assert arrays["patient_id"].shape[0] == 800 * 6
    assert int(np.min(arrays["visit_index"])) == 1
    assert int(np.max(arrays["visit_index"])) == 6

    split_values, split_counts = np.unique(arrays["split"], return_counts=True)
    split_map = {str(k): int(v) for k, v in zip(split_values, split_counts)}
    assert split_map["train"] > split_map["val"] > 0
    assert split_map["test"] > 0

    progression_prev = float(np.mean(arrays["progression_label_12m"]))
    decomp_prev = float(np.mean(arrays["decomp_label_12m"]))
    assert 0.10 <= progression_prev <= 0.90
    assert 0.03 <= decomp_prev <= 0.80

    corr = float(np.corrcoef(arrays["composite_risk_latent"].astype(float), arrays["stiffness_kpa"].astype(float))[0, 1])
    assert corr > 0.45

    a_hash = mod._dataset_hash(arrays)
    b_hash = mod._dataset_hash(
        mod.generate_stage3_dataset_arrays(
            patients=800,
            visits=6,
            seed=77,
            schema_version=mod.SCHEMA_VERSION_DEFAULT,
        )
    )
    c_hash = mod._dataset_hash(
        mod.generate_stage3_dataset_arrays(
            patients=800,
            visits=6,
            seed=78,
            schema_version=mod.SCHEMA_VERSION_DEFAULT,
        )
    )
    assert a_hash == b_hash
    assert a_hash != c_hash


def test_stage3_threshold_gate_enforces_precision_and_recall_floor():
    mod = _load_module(
        "stage3_train_module",
        REPO_ROOT / "ml" / "scripts" / "train_stage3.py",
    )
    probs = np.array([0.95, 0.91, 0.88, 0.84, 0.80, 0.72, 0.65, 0.55, 0.42, 0.30], dtype=np.float64)
    labels = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0, 0], dtype=np.int8)

    out = mod.pick_threshold(
        probs=probs,
        labels=labels,
        ppv_target=0.85,
        recall_floor=0.65,
    )
    assert out["precision"] >= 0.85
    assert out["recall"] >= 0.65
