#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION_DEFAULT = "stage3_synth_v1"

COLUMN_ORDER = [
    "patient_id",
    "visit_index",
    "age_years",
    "sex",
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
    "measured_stiffness_kpa",
    "proxy_stiffness_kpa",
    "stiffness_kpa",
    "composite_risk_latent",
    "progression_label_12m",
    "decomp_label_12m",
    "split",
    "seed",
    "schema_version",
]


@dataclass
class Stage3SyntheticBundle:
    arrays: dict[str, np.ndarray]
    patients: int
    visits: int
    seed: int
    schema_version: str


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _split_by_patient(patients: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = rng.permutation(np.arange(patients))
    n_train = int(patients * 0.70)
    n_val = int(patients * 0.15)
    train = set(order[:n_train].tolist())
    val = set(order[n_train : n_train + n_val].tolist())
    labels = np.empty(patients, dtype=object)
    for idx in range(patients):
        if idx in train:
            labels[idx] = "train"
        elif idx in val:
            labels[idx] = "val"
        else:
            labels[idx] = "test"
    return labels


def _dataset_hash(data: dict[str, np.ndarray]) -> str:
    hasher = hashlib.sha256()
    for col in COLUMN_ORDER:
        hasher.update(col.encode("utf-8"))
        arr = data[col]
        if arr.dtype.kind in {"f", "i", "u", "b"}:
            hasher.update(np.ascontiguousarray(arr).tobytes())
        else:
            hasher.update("\x1f".join(str(x) for x in arr.tolist()).encode("utf-8"))
    return hasher.hexdigest()


def generate_stage3_dataset_arrays(
    *,
    patients: int = 250_000,
    visits: int = 12,
    seed: int = 42,
    schema_version: str = SCHEMA_VERSION_DEFAULT,
) -> dict[str, np.ndarray]:
    if patients <= 0:
        raise ValueError("patients must be > 0")
    if visits < 2:
        raise ValueError("visits must be >= 2")

    rng = np.random.default_rng(seed)
    rows = patients * visits

    patient_idx = np.repeat(np.arange(patients, dtype=np.int64), visits)
    visit_idx = np.tile(np.arange(1, visits + 1, dtype=np.int64), patients)

    sex_per_patient = np.where(rng.random(patients) < 0.52, "M", "F")
    sex = sex_per_patient[patient_idx]

    age_base = np.clip(rng.normal(49.0, 12.0, patients), 18.0, 85.0)
    age = np.clip(age_base[patient_idx] + (visit_idx - 1) / 8.0, 18.0, 90.0).astype(np.float64)

    bmi_base = np.clip(rng.normal(29.0, 5.2, patients), 17.0, 52.0)
    bmi = np.clip(bmi_base[patient_idx] + rng.normal(0.02, 0.22, rows) * (visit_idx - 1), 15.0, 60.0)

    type2dm_p = _sigmoid(-2.6 + 0.04 * (age_base - 45.0) + 0.10 * (bmi_base - 27.0))
    type2dm_patient = (rng.random(patients) < type2dm_p).astype(np.int8)
    type2dm = type2dm_patient[patient_idx]

    htn_p = _sigmoid(-2.2 + 0.05 * (age_base - 45.0) + 0.08 * (bmi_base - 27.0) + 0.55 * type2dm_patient)
    hypertension_patient = (rng.random(patients) < htn_p).astype(np.int8)
    hypertension = hypertension_patient[patient_idx]

    risk_base_patient = _sigmoid(
        -3.2
        + 0.045 * (age_base - 45.0)
        + 0.095 * (bmi_base - 27.0)
        + 0.9 * type2dm_patient
        + 0.45 * hypertension_patient
        + rng.normal(0.0, 0.65, patients)
    )
    risk_base = risk_base_patient[patient_idx]

    temporal_drift = 0.025 * (visit_idx - 1)
    latent = _sigmoid(-1.4 + 3.1 * risk_base + temporal_drift + rng.normal(0.0, 0.55, rows))

    ast = np.clip(24.0 + 105.0 * latent + rng.normal(0.0, 11.0, rows), 10.0, 450.0)
    alt = np.clip(18.0 + 88.0 * latent + rng.normal(0.0, 9.0, rows), 8.0, 420.0)
    platelets = np.clip(300.0 - 182.0 * latent + rng.normal(0.0, 15.0, rows), 45.0, 550.0)
    ast_uln = np.clip(35.0 + rng.normal(0.0, 2.0, rows), 25.0, 55.0)

    fib4 = (age * ast) / (platelets * np.sqrt(np.maximum(alt, 1e-3)))
    apri = ((ast / ast_uln) * 100.0) / platelets

    albumin_proxy = np.clip(4.35 - 0.0028 * np.maximum(ast - 32.0, 0.0), 2.0, 5.5)
    nfs_proxy = (
        -1.675
        + 0.037 * age
        + 0.094 * bmi
        + 1.13 * type2dm
        + 0.99 * (ast / np.maximum(alt, 1e-3))
        - 0.013 * platelets
        - 0.66 * albumin_proxy
    )
    bard_score = (
        (bmi >= 28.0).astype(np.int8)
        + (ast / np.maximum(alt, 1e-3) >= 0.8).astype(np.int8) * 2
        + type2dm.astype(np.int8)
    )

    stage2_stage_numeric = np.clip(np.rint(latent * 4.0 + rng.normal(0.0, 0.5, rows)), 0, 4).astype(np.int8)
    stage2_top_probability = np.clip(0.35 + 0.55 * latent + rng.normal(0.0, 0.07, rows), 0.2, 0.99)

    stiffness_available = (rng.random(rows) < 0.58).astype(np.int8)
    measured_kpa = np.clip(4.6 + 21.0 * latent + rng.normal(0.0, 1.9, rows), 2.0, 75.0)
    proxy_kpa = np.clip(4.8 + 19.0 * latent + rng.normal(0.0, 2.4, rows), 2.0, 75.0)
    stiffness_kpa = np.where(stiffness_available == 1, measured_kpa, proxy_kpa)

    composite_risk_latent = np.clip(
        0.22 * np.clip((fib4 - 1.1) / 3.5, 0.0, 1.0)
        + 0.14 * np.clip((apri - 0.35) / 1.6, 0.0, 1.0)
        + 0.22 * np.clip((stage2_stage_numeric / 4.0) * 0.7 + stage2_top_probability * 0.3, 0.0, 1.0)
        + 0.23 * np.clip((stiffness_kpa - 3.0) / 22.0, 0.0, 1.0)
        + 0.10 * np.clip(_sigmoid(nfs_proxy / 2.5), 0.0, 1.0)
        + 0.05 * np.clip(bard_score / 4.0, 0.0, 1.0),
        0.0,
        0.99,
    )

    progression_probability = np.clip(0.12 + 0.78 * composite_risk_latent + rng.normal(0.0, 0.08, rows), 0.01, 0.99)
    decomp_probability = np.clip(
        0.04 + 0.64 * composite_risk_latent + 0.06 * (stage2_stage_numeric >= 3).astype(float) + rng.normal(0.0, 0.06, rows),
        0.01,
        0.99,
    )
    progression_label = (rng.random(rows) < progression_probability).astype(np.int8)
    decomp_label = (rng.random(rows) < decomp_probability).astype(np.int8)

    split_per_patient = _split_by_patient(patients=patients, seed=seed + 17)
    split = split_per_patient[patient_idx]

    patient_ids = np.array([f"S3P-{idx:06d}" for idx in patient_idx], dtype=object)
    schema_col = np.full(rows, schema_version, dtype=object)
    seed_col = np.full(rows, seed, dtype=np.int64)

    return {
        "patient_id": patient_ids,
        "visit_index": visit_idx.astype(np.int64),
        "age_years": np.round(age, 3),
        "sex": sex.astype(object),
        "bmi": np.round(bmi, 4),
        "type2dm": type2dm.astype(np.int8),
        "hypertension": hypertension.astype(np.int8),
        "fib4": np.round(fib4, 6),
        "apri": np.round(apri, 6),
        "nfs_proxy": np.round(nfs_proxy, 6),
        "bard_score": bard_score.astype(np.int8),
        "stage2_stage_numeric": stage2_stage_numeric.astype(np.int8),
        "stage2_top_probability": np.round(stage2_top_probability, 6),
        "stiffness_available": stiffness_available.astype(np.int8),
        "measured_stiffness_kpa": np.round(measured_kpa, 6),
        "proxy_stiffness_kpa": np.round(proxy_kpa, 6),
        "stiffness_kpa": np.round(stiffness_kpa, 6),
        "composite_risk_latent": np.round(composite_risk_latent, 6),
        "progression_label_12m": progression_label.astype(np.int8),
        "decomp_label_12m": decomp_label.astype(np.int8),
        "split": split.astype(object),
        "seed": seed_col,
        "schema_version": schema_col,
    }


def _arrays_to_table(data: dict[str, np.ndarray]) -> pa.Table:
    return pa.table({col: pa.array(data[col].tolist() if data[col].dtype.kind == "O" else data[col]) for col in COLUMN_ORDER})


def write_stage3_artifacts(
    *,
    data: dict[str, np.ndarray],
    out_dir: Path,
    schema_version: str,
    patients: int,
    visits: int,
    seed: int,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = schema_version
    full_path = out_dir / f"{base}.parquet"
    train_path = out_dir / f"{base}_train.parquet"
    val_path = out_dir / f"{base}_val.parquet"
    test_path = out_dir / f"{base}_test.parquet"
    schema_path = out_dir / f"{base}_schema.json"
    profile_path = out_dir / f"{base}_profile.json"

    table = _arrays_to_table(data)
    pq.write_table(table, full_path, compression="zstd")

    for split_name, path in [("train", train_path), ("val", val_path), ("test", test_path)]:
        mask = (data["split"] == split_name)
        split_data = {col: values[mask] for col, values in data.items()}
        pq.write_table(_arrays_to_table(split_data), path, compression="zstd")

    schema_payload = {
        "schema_version": schema_version,
        "columns": COLUMN_ORDER,
        "rows": int(table.num_rows),
        "patients": int(patients),
        "visits_per_patient": int(visits),
    }
    schema_path.write_text(json.dumps(schema_payload, indent=2))

    split_counts = {
        key: int((data["split"] == key).sum())
        for key in ["train", "val", "test"]
    }
    profile_payload = {
        "schema_version": schema_version,
        "rows": int(table.num_rows),
        "patients": int(patients),
        "visits_per_patient": int(visits),
        "seed": int(seed),
        "split_counts": split_counts,
        "dataset_hash_sha256": _dataset_hash(data),
        "composite_risk_mean": float(np.mean(data["composite_risk_latent"])),
        "progression_prevalence": float(np.mean(data["progression_label_12m"])),
        "decomp_prevalence": float(np.mean(data["decomp_label_12m"])),
    }
    profile_path.write_text(json.dumps(profile_payload, indent=2))
    return profile_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic Stage 3 longitudinal dataset.")
    parser.add_argument("--patients", type=int, default=250_000)
    parser.add_argument("--visits", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION_DEFAULT)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "synthetic",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = generate_stage3_dataset_arrays(
        patients=args.patients,
        visits=args.visits,
        seed=args.seed,
        schema_version=args.schema_version,
    )
    profile = write_stage3_artifacts(
        data=data,
        out_dir=args.out_dir,
        schema_version=args.schema_version,
        patients=args.patients,
        visits=args.visits,
        seed=args.seed,
    )
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
