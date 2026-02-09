from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from app.schemas.assessment import ClinicalAssessmentCreate
from app.services.stage1 import run_stage1
from scripts.generate_synthetic_clinical_dataset import (
    COLUMN_ORDER,
    PARAMETER_BOUNDS,
    SCHEMA_VERSION_DEFAULT,
    _compute_dataset_hash,
    generate_dataset_arrays,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("HEPATICA_SYNTH_DATA_DIR", str(REPO_ROOT / "data" / "synthetic")))
BASE = SCHEMA_VERSION_DEFAULT
FULL = DATA_DIR / f"{BASE}.parquet"
TRAIN = DATA_DIR / f"{BASE}_train.parquet"
VAL = DATA_DIR / f"{BASE}_val.parquet"
TEST = DATA_DIR / f"{BASE}_test.parquet"
SAMPLE_CSV = DATA_DIR / f"{BASE}_sample_5000.csv"
SCHEMA_JSON = DATA_DIR / f"{BASE}_schema.json"
PROFILE_JSON = DATA_DIR / f"{BASE}_profile.json"
PROFILE_MD = DATA_DIR / f"{BASE}_profile.md"


@pytest.fixture(scope="session")
def dataset_table():
    assert FULL.exists(), f"Missing dataset artifact: {FULL}"
    return pq.read_table(FULL)


@pytest.fixture(scope="session")
def dataset_arrays(dataset_table):
    arrays: dict[str, np.ndarray] = {}
    for col in COLUMN_ORDER:
        chunked = dataset_table.column(col).combine_chunks()
        try:
            arrays[col] = chunked.to_numpy(zero_copy_only=False)
        except (NotImplementedError, TypeError):
            arrays[col] = np.array(chunked.to_pylist(), dtype=object)
    return arrays


def test_schema_and_row_count(dataset_table):
    assert TRAIN.exists(), f"Missing split artifact: {TRAIN}"
    assert VAL.exists(), f"Missing split artifact: {VAL}"
    assert TEST.exists(), f"Missing split artifact: {TEST}"
    assert SAMPLE_CSV.exists(), f"Missing sample CSV artifact: {SAMPLE_CSV}"
    assert SCHEMA_JSON.exists(), f"Missing schema artifact: {SCHEMA_JSON}"
    assert PROFILE_JSON.exists(), f"Missing profile artifact: {PROFILE_JSON}"
    assert PROFILE_MD.exists(), f"Missing profile markdown artifact: {PROFILE_MD}"

    assert dataset_table.num_rows == 200_000
    assert dataset_table.num_columns == len(COLUMN_ORDER)
    assert dataset_table.column_names == COLUMN_ORDER

    assert pq.ParquetFile(TRAIN).metadata.num_rows == 140_000
    assert pq.ParquetFile(VAL).metadata.num_rows == 30_000
    assert pq.ParquetFile(TEST).metadata.num_rows == 30_000


def test_parameter_bounds_and_non_null(dataset_arrays):
    for name, (low, high) in PARAMETER_BOUNDS.items():
        values = dataset_arrays[name].astype(float)
        assert not np.isnan(values).any(), f"Column {name} contains NaN"
        assert (values >= low).all(), f"Column {name} has values < {low}"
        assert (values <= high).all(), f"Column {name} has values > {high}"


def test_rule_parity_matches_stage1_runtime(dataset_arrays):
    n = dataset_arrays["age_years"].shape[0]
    for i in range(n):
        result = run_stage1(
            age=int(dataset_arrays["age_years"][i]),
            ast=float(dataset_arrays["ast_u_l"][i]),
            alt=float(dataset_arrays["alt_u_l"][i]),
            platelets=float(dataset_arrays["platelets_10e9_l"][i]),
            ast_uln=float(dataset_arrays["ast_uln_u_l"][i]),
            bmi=float(dataset_arrays["bmi"][i]),
            type2dm=bool(dataset_arrays["type2dm"][i]),
        )
        if abs(float(dataset_arrays["fib4"][i]) - result.fib4) > 1e-12:
            pytest.fail(f"FIB-4 mismatch at row {i}")
        if abs(float(dataset_arrays["apri"][i]) - result.apri) > 1e-12:
            pytest.fail(f"APRI mismatch at row {i}")
        if str(dataset_arrays["risk_tier_rule"][i]) != result.risk_tier.value:
            pytest.fail(f"risk_tier_rule mismatch at row {i}")
        if abs(float(dataset_arrays["probability_rule"][i]) - result.probability) > 1e-12:
            pytest.fail(f"probability_rule mismatch at row {i}")


def test_split_stratified_and_reproducible(dataset_arrays):
    split_values, split_counts = np.unique(dataset_arrays["split"], return_counts=True)
    split_map = {str(k): int(v) for k, v in zip(split_values, split_counts)}
    assert split_map == {"train": 140_000, "val": 30_000, "test": 30_000}

    combined = np.char.add(
        np.char.add(dataset_arrays["latent_stage"].astype(str), "|"),
        dataset_arrays["risk_tier_rule"].astype(str),
    )
    labels, counts = np.unique(combined, return_counts=True)
    global_dist = {k: float(v / combined.shape[0]) for k, v in zip(labels, counts)}

    for split_name in ["train", "val", "test"]:
        mask = dataset_arrays["split"] == split_name
        split_combined = combined[mask]
        split_labels, split_counts = np.unique(split_combined, return_counts=True)
        split_dist = {k: float(v / split_combined.shape[0]) for k, v in zip(split_labels, split_counts)}
        for label, p in global_dist.items():
            assert abs(split_dist.get(label, 0.0) - p) < 0.03

    data_a = generate_dataset_arrays(rows=5_000, seed=123, schema_version=SCHEMA_VERSION_DEFAULT)
    data_b = generate_dataset_arrays(rows=5_000, seed=123, schema_version=SCHEMA_VERSION_DEFAULT)
    data_c = generate_dataset_arrays(rows=5_000, seed=124, schema_version=SCHEMA_VERSION_DEFAULT)
    assert _compute_dataset_hash(data_a) == _compute_dataset_hash(data_b)
    assert _compute_dataset_hash(data_a) != _compute_dataset_hash(data_c)


def test_distribution_and_correlation_sanity(dataset_arrays):
    risk_values, risk_counts = np.unique(dataset_arrays["risk_tier_rule"], return_counts=True)
    risk_dist = {str(k): float(v / dataset_arrays["risk_tier_rule"].shape[0]) for k, v in zip(risk_values, risk_counts)}

    assert 0.55 <= risk_dist.get("LOW", 0.0) <= 0.70
    assert 0.18 <= risk_dist.get("MODERATE", 0.0) <= 0.28
    assert 0.10 <= risk_dist.get("HIGH", 0.0) <= 0.20

    type2dm_prev = float(np.mean(dataset_arrays["type2dm"]))
    obesity_prev = float(np.mean(dataset_arrays["bmi"].astype(float) >= 30.0))
    enrichment_prev = float(np.mean(dataset_arrays["cohort_source"] == "enrichment"))

    assert 0.05 <= type2dm_prev <= 0.20
    assert 0.20 <= obesity_prev <= 0.50
    assert abs(enrichment_prev - 0.25) <= 0.02

    fib4 = dataset_arrays["fib4"].astype(float)
    latent = dataset_arrays["latent_fibrosis_score"].astype(float)

    corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    assert corr(fib4, dataset_arrays["age_years"].astype(float)) > 0
    assert corr(fib4, dataset_arrays["ast_u_l"].astype(float)) > 0
    assert corr(fib4, dataset_arrays["platelets_10e9_l"].astype(float)) < 0

    assert corr(latent, dataset_arrays["total_bilirubin_mg_dl"].astype(float)) > 0
    assert corr(latent, dataset_arrays["inr"].astype(float)) > 0
    assert corr(latent, dataset_arrays["albumin_g_dl"].astype(float)) < 0
    assert corr(latent, dataset_arrays["platelets_10e9_l"].astype(float)) < 0


def test_usability_smoke_matches_clinical_payload_constraints(dataset_arrays):
    for i in range(1_000):
        payload = ClinicalAssessmentCreate(
            patient_id="synthetic-patient",
            ast=float(dataset_arrays["ast_u_l"][i]),
            alt=float(dataset_arrays["alt_u_l"][i]),
            platelets=float(dataset_arrays["platelets_10e9_l"][i]),
            ast_uln=float(dataset_arrays["ast_uln_u_l"][i]),
            age=int(dataset_arrays["age_years"][i]),
            bmi=float(dataset_arrays["bmi"][i]),
            type2dm=bool(dataset_arrays["type2dm"][i]),
        )
        assert payload.patient_id == "synthetic-patient"


def test_profile_files_consistent_with_dataset(dataset_arrays):
    profile = json.loads(PROFILE_JSON.read_text())
    assert profile["schema_version"] == SCHEMA_VERSION_DEFAULT
    assert profile["rows"] == 200_000

    computed_hash = _compute_dataset_hash(dataset_arrays)
    assert profile["dataset_hash_sha256"] == computed_hash

    assert profile["checks"]["risk_tier_window_pass"] is True
    assert profile["checks"]["split_70_15_15_exact"] is True
    assert profile["checks"]["correlation_sanity_pass"] is True
