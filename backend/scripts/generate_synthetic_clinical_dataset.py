#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.stage1 import run_stage1

SCHEMA_VERSION_DEFAULT = "stage1_synth_v1"

PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "age_years": (18, 90),
    "bmi": (15, 60),
    "ast_u_l": (10, 500),
    "alt_u_l": (8, 500),
    "platelets_10e9_l": (40, 600),
    "ast_uln_u_l": (25, 55),
    "albumin_g_dl": (2.0, 5.5),
    "total_bilirubin_mg_dl": (0.1, 8.0),
    "ggt_u_l": (10, 800),
    "inr": (0.8, 2.5),
    "hba1c_pct": (4.5, 12.0),
    "triglycerides_mg_dl": (50, 700),
}

COLUMN_ORDER = [
    "age_years",
    "sex",
    "bmi",
    "type2dm",
    "hypertension",
    "dyslipidemia",
    "ast_u_l",
    "alt_u_l",
    "platelets_10e9_l",
    "ast_uln_u_l",
    "albumin_g_dl",
    "total_bilirubin_mg_dl",
    "ggt_u_l",
    "inr",
    "hba1c_pct",
    "triglycerides_mg_dl",
    "fib4",
    "apri",
    "risk_tier_rule",
    "probability_rule",
    "latent_fibrosis_score",
    "latent_stage",
    "split",
    "cohort_source",
    "seed",
    "schema_version",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _clip(arr: np.ndarray, low: float, high: float) -> np.ndarray:
    return np.clip(arr, low, high)


def _stratified_split_indices(
    labels: np.ndarray,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not np.isclose(train_ratio + val_ratio, 0.85):
        raise ValueError("train+val ratio must be 0.85")

    rng = np.random.default_rng(seed)
    n_total = len(labels)
    target = np.array(
        [
            int(n_total * train_ratio),
            int(n_total * val_ratio),
            n_total - int(n_total * train_ratio) - int(n_total * val_ratio),
        ],
        dtype=np.int64,
    )

    unique, inverse = np.unique(labels, return_inverse=True)
    per_group_indices: list[np.ndarray] = []
    allocations = np.zeros((len(unique), 3), dtype=np.int64)

    ratios = np.array([train_ratio, val_ratio, 1.0 - train_ratio - val_ratio], dtype=np.float64)

    for group_idx in range(len(unique)):
        idx = np.where(inverse == group_idx)[0]
        idx = rng.permutation(idx)
        per_group_indices.append(idx)

        raw = len(idx) * ratios
        base = np.floor(raw).astype(np.int64)
        leftover = len(idx) - int(base.sum())
        if leftover > 0:
            order = np.argsort(-(raw - base))
            for i in range(leftover):
                base[order[i % len(order)]] += 1
        allocations[group_idx] = base

    totals = allocations.sum(axis=0)

    def move_one(src_split: int, dst_split: int) -> bool:
        candidates = np.where(allocations[:, src_split] > 0)[0]
        if candidates.size == 0:
            return False
        best = candidates[np.argmax(allocations[candidates, src_split] - allocations[candidates, dst_split])]
        allocations[best, src_split] -= 1
        allocations[best, dst_split] += 1
        return True

    max_iter = n_total * 3
    it = 0
    while not np.array_equal(totals, target) and it < max_iter:
        it += 1
        moved = False
        surplus = np.where(totals > target)[0]
        deficit = np.where(totals < target)[0]
        if surplus.size == 0 or deficit.size == 0:
            break

        for dst in deficit:
            while totals[dst] < target[dst]:
                src_order = surplus[np.argsort(-(totals[surplus] - target[surplus]))]
                shifted = False
                for src in src_order:
                    if totals[src] <= target[src]:
                        continue
                    if move_one(int(src), int(dst)):
                        totals[src] -= 1
                        totals[dst] += 1
                        moved = True
                        shifted = True
                        break
                if not shifted:
                    break

        if not moved:
            break

    if not np.array_equal(totals, target):
        raise RuntimeError(
            f"Unable to satisfy exact split targets; got={totals.tolist()} target={target.tolist()}"
        )

    split_parts: list[list[np.ndarray]] = [[], [], []]
    for group_idx, idx in enumerate(per_group_indices):
        n_train, n_val, n_test = allocations[group_idx]
        split_parts[0].append(idx[:n_train])
        split_parts[1].append(idx[n_train : n_train + n_val])
        split_parts[2].append(idx[n_train + n_val : n_train + n_val + n_test])

    split_indices = [np.concatenate(parts) if parts else np.array([], dtype=np.int64) for parts in split_parts]
    split_indices = [rng.permutation(x) for x in split_indices]

    return split_indices[0], split_indices[1], split_indices[2]


def _latent_stage_from_score(score: np.ndarray) -> np.ndarray:
    bins = np.array([0.18, 0.36, 0.56, 0.75], dtype=np.float64)
    idx = np.digitize(score, bins, right=False)
    mapping = np.array(["F0", "F1", "F2", "F3", "F4"], dtype=object)
    return mapping[idx]


def _risk_tier_distribution(risk_tier_rule: np.ndarray) -> dict[str, float]:
    unique, counts = np.unique(risk_tier_rule, return_counts=True)
    total = float(risk_tier_rule.shape[0])
    return {str(k): float(v / total) for k, v in zip(unique, counts)}


def _validate_bounds(data: dict[str, np.ndarray]) -> None:
    for name, (low, high) in PARAMETER_BOUNDS.items():
        values = data[name]
        if np.isnan(values).any():
            raise ValueError(f"Column {name} contains NaN")
        if (values < low).any() or (values > high).any():
            raise ValueError(f"Column {name} has values outside [{low}, {high}]")


def _compute_dataset_hash(data: dict[str, np.ndarray]) -> str:
    hasher = hashlib.sha256()
    for col in COLUMN_ORDER:
        hasher.update(col.encode("utf-8"))
        values = data[col]
        if values.dtype.kind in {"b", "i", "u", "f"}:
            hasher.update(np.ascontiguousarray(values).tobytes())
        else:
            joined = "\x1f".join(str(x) for x in values.tolist())
            hasher.update(joined.encode("utf-8"))
    return hasher.hexdigest()


def generate_dataset_arrays(
    *,
    rows: int = 200_000,
    seed: int = 42,
    schema_version: str = SCHEMA_VERSION_DEFAULT,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)

    cohort_source = np.where(rng.random(rows) < 0.75, "general_pop", "enrichment")
    enrichment = (cohort_source == "enrichment").astype(np.float64)

    sex = np.where(rng.random(rows) < (0.52 + 0.06 * enrichment), "M", "F")

    age_years = np.where(
        enrichment > 0,
        rng.normal(58.0, 11.0, rows),
        rng.normal(45.0, 14.0, rows),
    )
    age_years = _clip(age_years, *PARAMETER_BOUNDS["age_years"])
    age_years = np.rint(age_years).astype(np.int64)

    bmi = np.where(
        enrichment > 0,
        rng.normal(32.0, 5.8, rows),
        rng.normal(27.2, 4.9, rows),
    )
    bmi = np.round(_clip(bmi, *PARAMETER_BOUNDS["bmi"]), 2)

    p_type2dm = _sigmoid(-3.6 + 0.055 * (age_years - 45) + 0.115 * (bmi - 27) + 0.95 * enrichment)
    type2dm = rng.random(rows) < p_type2dm

    p_hypertension = _sigmoid(
        -2.8 + 0.06 * (age_years - 45) + 0.06 * (bmi - 27) + 0.40 * type2dm + 0.7 * enrichment
    )
    hypertension = rng.random(rows) < p_hypertension

    p_dyslipidemia = _sigmoid(
        -2.7 + 0.04 * (age_years - 45) + 0.08 * (bmi - 27) + 0.65 * type2dm + 0.5 * enrichment
    )
    dyslipidemia = rng.random(rows) < p_dyslipidemia

    latent_fibrosis_score = _sigmoid(
        -5.45
        + 0.052 * (age_years - 45)
        + 0.085 * (bmi - 27)
        + 0.95 * type2dm
        + 0.50 * hypertension
        + 0.42 * dyslipidemia
        + 1.25 * enrichment
        + rng.normal(0.0, 0.85, rows)
    )
    latent_fibrosis_score = np.round(_clip(latent_fibrosis_score, 0.0, 1.0), 6)

    ast_uln_u_l = np.where(
        sex == "M",
        rng.normal(41.5, 3.8, rows),
        rng.normal(36.5, 3.4, rows),
    )
    ast_uln_u_l = np.round(_clip(ast_uln_u_l, *PARAMETER_BOUNDS["ast_uln_u_l"]), 2)

    platelets_10e9_l = 275 - 200 * latent_fibrosis_score - 12 * type2dm + rng.normal(0.0, 30.0, rows)
    platelets_10e9_l = np.round(_clip(platelets_10e9_l, *PARAMETER_BOUNDS["platelets_10e9_l"]), 2)

    ast_u_l = 22 + 165 * latent_fibrosis_score + 12 * type2dm + 8 * enrichment + rng.normal(0.0, 16.0, rows)
    ast_u_l = np.round(_clip(ast_u_l, *PARAMETER_BOUNDS["ast_u_l"]), 2)

    alt_u_l = (
        24
        + 86 * latent_fibrosis_score
        + 0.7 * (bmi - 27)
        + 8 * type2dm
        + rng.normal(0.0, 20.0, rows)
    )
    alt_u_l = np.round(_clip(alt_u_l, *PARAMETER_BOUNDS["alt_u_l"]), 2)

    albumin_g_dl = 4.62 - 1.24 * latent_fibrosis_score - 0.04 * type2dm + rng.normal(0.0, 0.22, rows)
    albumin_g_dl = np.round(_clip(albumin_g_dl, *PARAMETER_BOUNDS["albumin_g_dl"]), 3)

    total_bilirubin_mg_dl = (
        0.45 + 2.55 * latent_fibrosis_score + 0.10 * enrichment + rng.normal(0.0, 0.30, rows)
    )
    total_bilirubin_mg_dl = np.round(
        _clip(total_bilirubin_mg_dl, *PARAMETER_BOUNDS["total_bilirubin_mg_dl"]),
        3,
    )

    ggt_u_l = 26 + 215 * latent_fibrosis_score + 24 * dyslipidemia + 14 * type2dm + rng.normal(0.0, 40.0, rows)
    ggt_u_l = np.round(_clip(ggt_u_l, *PARAMETER_BOUNDS["ggt_u_l"]), 2)

    inr = 0.95 + 0.60 * latent_fibrosis_score + rng.normal(0.0, 0.07, rows)
    inr = np.round(_clip(inr, *PARAMETER_BOUNDS["inr"]), 3)

    hba1c_pct = (
        5.25
        + 1.75 * type2dm
        + 0.32 * latent_fibrosis_score
        + 0.025 * (bmi - 27)
        + rng.normal(0.0, 0.35, rows)
    )
    hba1c_pct = np.round(_clip(hba1c_pct, *PARAMETER_BOUNDS["hba1c_pct"]), 3)

    triglycerides_mg_dl = (
        120 + 120 * dyslipidemia + 55 * type2dm + 4.8 * (bmi - 27) + rng.normal(0.0, 35.0, rows)
    )
    triglycerides_mg_dl = np.round(
        _clip(triglycerides_mg_dl, *PARAMETER_BOUNDS["triglycerides_mg_dl"]),
        2,
    )

    latent_stage = _latent_stage_from_score(latent_fibrosis_score)

    fib4 = np.empty(rows, dtype=np.float64)
    apri = np.empty(rows, dtype=np.float64)
    risk_tier_rule = np.empty(rows, dtype=object)
    probability_rule = np.empty(rows, dtype=np.float64)

    for i in range(rows):
        result = run_stage1(
            age=int(age_years[i]),
            ast=float(ast_u_l[i]),
            alt=float(alt_u_l[i]),
            platelets=float(platelets_10e9_l[i]),
            ast_uln=float(ast_uln_u_l[i]),
            bmi=float(bmi[i]),
            type2dm=bool(type2dm[i]),
        )
        fib4[i] = result.fib4
        apri[i] = result.apri
        risk_tier_rule[i] = result.risk_tier.value
        probability_rule[i] = result.probability

    strata = np.char.add(np.char.add(latent_stage.astype(str), "|"), risk_tier_rule.astype(str))
    train_idx, val_idx, test_idx = _stratified_split_indices(strata, seed=seed + 17)

    split = np.empty(rows, dtype=object)
    split[train_idx] = "train"
    split[val_idx] = "val"
    split[test_idx] = "test"

    data = {
        "age_years": age_years.astype(np.int64),
        "sex": sex.astype(object),
        "bmi": bmi.astype(np.float64),
        "type2dm": type2dm.astype(bool),
        "hypertension": hypertension.astype(bool),
        "dyslipidemia": dyslipidemia.astype(bool),
        "ast_u_l": ast_u_l.astype(np.float64),
        "alt_u_l": alt_u_l.astype(np.float64),
        "platelets_10e9_l": platelets_10e9_l.astype(np.float64),
        "ast_uln_u_l": ast_uln_u_l.astype(np.float64),
        "albumin_g_dl": albumin_g_dl.astype(np.float64),
        "total_bilirubin_mg_dl": total_bilirubin_mg_dl.astype(np.float64),
        "ggt_u_l": ggt_u_l.astype(np.float64),
        "inr": inr.astype(np.float64),
        "hba1c_pct": hba1c_pct.astype(np.float64),
        "triglycerides_mg_dl": triglycerides_mg_dl.astype(np.float64),
        "fib4": fib4.astype(np.float64),
        "apri": apri.astype(np.float64),
        "risk_tier_rule": risk_tier_rule.astype(object),
        "probability_rule": probability_rule.astype(np.float64),
        "latent_fibrosis_score": latent_fibrosis_score.astype(np.float64),
        "latent_stage": latent_stage.astype(object),
        "split": split.astype(object),
        "cohort_source": cohort_source.astype(object),
        "seed": np.full(rows, seed, dtype=np.int64),
        "schema_version": np.full(rows, schema_version, dtype=object),
    }

    _validate_bounds(data)

    return data


def _to_arrow_table(data: dict[str, np.ndarray]) -> pa.Table:
    return pa.table({name: data[name] for name in COLUMN_ORDER})


def _subset_data(data: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, np.ndarray]:
    return {k: v[mask] for k, v in data.items()}


def _write_schema_json(out_dir: Path, schema_version: str) -> None:
    payload = {
        "schema_version": schema_version,
        "description": "Synthetic Stage 1 clinical dataset with 16 base parameters and dual labels.",
        "parameters": [
            {"name": "age_years", "type": "int64", "bounds": [18, 90]},
            {"name": "sex", "type": "string", "allowed": ["F", "M"]},
            {"name": "bmi", "type": "float64", "bounds": [15, 60]},
            {"name": "type2dm", "type": "bool"},
            {"name": "hypertension", "type": "bool"},
            {"name": "dyslipidemia", "type": "bool"},
            {"name": "ast_u_l", "type": "float64", "bounds": [10, 500]},
            {"name": "alt_u_l", "type": "float64", "bounds": [8, 500]},
            {"name": "platelets_10e9_l", "type": "float64", "bounds": [40, 600]},
            {"name": "ast_uln_u_l", "type": "float64", "bounds": [25, 55]},
            {"name": "albumin_g_dl", "type": "float64", "bounds": [2.0, 5.5]},
            {
                "name": "total_bilirubin_mg_dl",
                "type": "float64",
                "bounds": [0.1, 8.0],
            },
            {"name": "ggt_u_l", "type": "float64", "bounds": [10, 800]},
            {"name": "inr", "type": "float64", "bounds": [0.8, 2.5]},
            {"name": "hba1c_pct", "type": "float64", "bounds": [4.5, 12.0]},
            {
                "name": "triglycerides_mg_dl",
                "type": "float64",
                "bounds": [50, 700],
            },
        ],
        "derived_fields": [
            "fib4",
            "apri",
            "risk_tier_rule",
            "probability_rule",
            "latent_fibrosis_score",
            "latent_stage",
        ],
        "meta_fields": ["split", "cohort_source", "seed", "schema_version"],
        "column_order": COLUMN_ORDER,
    }
    schema_path = out_dir / f"{schema_version}_schema.json"
    schema_path.write_text(json.dumps(payload, indent=2))


def _compute_profile(data: dict[str, np.ndarray], rows: int, seed: int, schema_version: str) -> dict:
    risk_dist = _risk_tier_distribution(data["risk_tier_rule"])

    split_counts = {
        k: int(v)
        for k, v in zip(
            *np.unique(data["split"], return_counts=True),
        )
    }
    cohort_counts = {
        k: int(v)
        for k, v in zip(
            *np.unique(data["cohort_source"], return_counts=True),
        )
    }
    latent_counts = {
        k: int(v)
        for k, v in zip(
            *np.unique(data["latent_stage"], return_counts=True),
        )
    }

    def _corr(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.corrcoef(a, b)[0, 1])

    correlations = {
        "fib4_age_years": _corr(data["fib4"], data["age_years"]),
        "fib4_ast_u_l": _corr(data["fib4"], data["ast_u_l"]),
        "fib4_platelets_10e9_l": _corr(data["fib4"], data["platelets_10e9_l"]),
        "latent_total_bilirubin_mg_dl": _corr(
            data["latent_fibrosis_score"],
            data["total_bilirubin_mg_dl"],
        ),
        "latent_inr": _corr(data["latent_fibrosis_score"], data["inr"]),
        "latent_albumin_g_dl": _corr(data["latent_fibrosis_score"], data["albumin_g_dl"]),
        "latent_platelets_10e9_l": _corr(
            data["latent_fibrosis_score"],
            data["platelets_10e9_l"],
        ),
    }

    checks = {
        "risk_tier_window_pass": (
            0.55 <= risk_dist.get("LOW", 0.0) <= 0.70
            and 0.18 <= risk_dist.get("MODERATE", 0.0) <= 0.28
            and 0.10 <= risk_dist.get("HIGH", 0.0) <= 0.20
        ),
        "split_70_15_15_exact": split_counts == {"train": int(rows * 0.70), "val": int(rows * 0.15), "test": rows - int(rows * 0.85)},
        "correlation_sanity_pass": (
            correlations["fib4_age_years"] > 0
            and correlations["fib4_ast_u_l"] > 0
            and correlations["fib4_platelets_10e9_l"] < 0
            and correlations["latent_total_bilirubin_mg_dl"] > 0
            and correlations["latent_inr"] > 0
            and correlations["latent_albumin_g_dl"] < 0
            and correlations["latent_platelets_10e9_l"] < 0
        ),
    }

    profile = {
        "schema_version": schema_version,
        "rows": rows,
        "seed": seed,
        "column_count": len(COLUMN_ORDER),
        "risk_tier_distribution": risk_dist,
        "split_counts": split_counts,
        "cohort_counts": cohort_counts,
        "latent_stage_counts": latent_counts,
        "prevalence": {
            "type2dm": float(np.mean(data["type2dm"])),
            "hypertension": float(np.mean(data["hypertension"])),
            "dyslipidemia": float(np.mean(data["dyslipidemia"])),
            "obesity_bmi_ge_30": float(np.mean(data["bmi"] >= 30.0)),
            "enrichment_fraction": float(np.mean(data["cohort_source"] == "enrichment")),
        },
        "correlations": correlations,
        "checks": checks,
        "dataset_hash_sha256": _compute_dataset_hash(data),
    }

    return profile


def _write_profile_markdown(profile: dict, out_path: Path) -> None:
    risk = profile["risk_tier_distribution"]
    prev = profile["prevalence"]
    checks = profile["checks"]
    lines = [
        "# Stage 1 Synthetic Dataset Profile",
        "",
        f"- Schema version: `{profile['schema_version']}`",
        f"- Rows: `{profile['rows']}`",
        f"- Seed: `{profile['seed']}`",
        f"- Dataset hash (sha256): `{profile['dataset_hash_sha256']}`",
        "",
        "## Risk Tier Distribution",
        f"- LOW: `{risk.get('LOW', 0.0):.4f}`",
        f"- MODERATE: `{risk.get('MODERATE', 0.0):.4f}`",
        f"- HIGH: `{risk.get('HIGH', 0.0):.4f}`",
        "",
        "## Prevalence",
        f"- Type2DM: `{prev['type2dm']:.4f}`",
        f"- Hypertension: `{prev['hypertension']:.4f}`",
        f"- Dyslipidemia: `{prev['dyslipidemia']:.4f}`",
        f"- BMI >= 30: `{prev['obesity_bmi_ge_30']:.4f}`",
        f"- Enrichment cohort fraction: `{prev['enrichment_fraction']:.4f}`",
        "",
        "## Quality Checks",
        f"- risk_tier_window_pass: `{checks['risk_tier_window_pass']}`",
        f"- split_70_15_15_exact: `{checks['split_70_15_15_exact']}`",
        f"- correlation_sanity_pass: `{checks['correlation_sanity_pass']}`",
    ]
    out_path.write_text("\n".join(lines) + "\n")


def _write_csv_sample(data: dict[str, np.ndarray], out_path: Path, sample_size: int = 5000) -> None:
    sample_size = min(sample_size, data["age_years"].shape[0])
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMN_ORDER)
        for i in range(sample_size):
            writer.writerow([data[col][i] for col in COLUMN_ORDER])


def write_artifacts(
    *,
    data: dict[str, np.ndarray],
    out_dir: Path,
    schema_version: str,
    seed: int,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    table = _to_arrow_table(data)

    full_path = out_dir / f"{schema_version}.parquet"
    pq.write_table(table, full_path, compression="zstd")

    split_col = data["split"]
    train_data = _subset_data(data, split_col == "train")
    val_data = _subset_data(data, split_col == "val")
    test_data = _subset_data(data, split_col == "test")

    pq.write_table(_to_arrow_table(train_data), out_dir / f"{schema_version}_train.parquet", compression="zstd")
    pq.write_table(_to_arrow_table(val_data), out_dir / f"{schema_version}_val.parquet", compression="zstd")
    pq.write_table(_to_arrow_table(test_data), out_dir / f"{schema_version}_test.parquet", compression="zstd")

    _write_csv_sample(data, out_dir / f"{schema_version}_sample_5000.csv", sample_size=5000)
    _write_schema_json(out_dir, schema_version)

    profile = _compute_profile(data, rows=data["age_years"].shape[0], seed=seed, schema_version=schema_version)
    profile_json = out_dir / f"{schema_version}_profile.json"
    profile_md = out_dir / f"{schema_version}_profile.md"
    profile_json.write_text(json.dumps(profile, indent=2))
    _write_profile_markdown(profile, profile_md)

    return profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic Stage 1 clinical dataset")
    parser.add_argument("--rows", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/Users/praty/hepatica-p/data/synthetic"),
    )
    parser.add_argument("--schema-version", type=str, default=SCHEMA_VERSION_DEFAULT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = generate_dataset_arrays(rows=args.rows, seed=args.seed, schema_version=args.schema_version)
    profile = write_artifacts(data=data, out_dir=args.out_dir, schema_version=args.schema_version, seed=args.seed)

    print(json.dumps(
        {
            "rows": args.rows,
            "seed": args.seed,
            "out_dir": str(args.out_dir),
            "schema_version": args.schema_version,
            "risk_tier_distribution": profile["risk_tier_distribution"],
            "checks": profile["checks"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
