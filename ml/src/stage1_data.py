from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_FEATURES = [
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
]

ENGINEERED_FEATURES = ["fib4_input", "apri_input", "ast_alt_ratio"]
FEATURE_COLUMNS = BASE_FEATURES + ENGINEERED_FEATURES
TARGET_COLUMNS = ["risk_tier_rule", "probability_rule", "latent_fibrosis_score"]
META_COLUMNS = ["split", "cohort_source", "seed", "schema_version"]

BOOL_FEATURES = ["type2dm", "hypertension", "dyslipidemia"]
CATEGORICAL_FEATURES = ["sex"]
NUMERIC_FEATURES = [c for c in FEATURE_COLUMNS if c not in CATEGORICAL_FEATURES]
CLASS_ORDER = ["LOW", "MODERATE", "HIGH"]


@dataclass
class Stage1DatasetBundle:
    full_df: pd.DataFrame
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame


class DataContractError(RuntimeError):
    pass


def resolve_repo_path(path_value: str | Path, repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    raw = str(path_value)
    candidate = Path(raw)
    if candidate.exists():
        return candidate

    prefix = "/Users/praty/hepatica-p/"
    if raw.startswith(prefix):
        remapped = root / raw[len(prefix) :]
        return remapped

    if candidate.is_absolute():
        return candidate

    return (root / candidate).resolve()


def normalize_stage1_config_paths(config: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    out = dict(config)
    for key in ["data_path", "schema_path", "artifact_dir"]:
        if key in out:
            out[key] = str(resolve_repo_path(out[key], repo_root=repo_root))
    return out


def _required_columns() -> list[str]:
    return BASE_FEATURES + TARGET_COLUMNS + META_COLUMNS


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["fib4_input"] = (
        out["age_years"].astype(float)
        * out["ast_u_l"].astype(float)
        / (out["platelets_10e9_l"].astype(float) * np.sqrt(out["alt_u_l"].astype(float)))
    )
    out["apri_input"] = (
        (out["ast_u_l"].astype(float) / out["ast_uln_u_l"].astype(float))
        * 100.0
        / out["platelets_10e9_l"].astype(float)
    )
    out["ast_alt_ratio"] = out["ast_u_l"].astype(float) / out["alt_u_l"].astype(float)
    return out


def _validate_schema_file(schema_path: Path, expected_version: str) -> None:
    if not schema_path.exists():
        raise DataContractError(f"Schema file missing: {schema_path}")
    payload = json.loads(schema_path.read_text())
    schema_version = payload.get("schema_version")
    if schema_version != expected_version:
        raise DataContractError(
            f"Schema version mismatch in schema file. expected={expected_version} got={schema_version}"
        )


def validate_data_contract(df: pd.DataFrame, config: dict[str, Any]) -> None:
    missing = sorted(set(_required_columns()) - set(df.columns))
    if missing:
        raise DataContractError(f"Missing required columns: {missing}")

    expected_rows = int(config["expected_rows"])
    if df.shape[0] != expected_rows:
        raise DataContractError(
            f"Row count mismatch. expected={expected_rows} got={df.shape[0]}"
        )

    expected_version = str(config["schema_version"])
    versions = sorted(df["schema_version"].astype(str).unique().tolist())
    if versions != [expected_version]:
        raise DataContractError(
            f"schema_version mismatch in dataset. expected={[expected_version]} got={versions}"
        )

    split_counts = (
        df["split"].astype(str).value_counts().sort_index().to_dict()
    )
    expected_splits = {
        k: int(v)
        for k, v in config["expected_split_counts"].items()
    }
    if split_counts != expected_splits:
        raise DataContractError(
            f"Split counts mismatch. expected={expected_splits} got={split_counts}"
        )

    null_cols = [c for c in _required_columns() if df[c].isna().any()]
    if null_cols:
        raise DataContractError(f"Required columns contain nulls: {null_cols}")


def _downsample_by_split(df: pd.DataFrame, max_rows: int, seed: int) -> pd.DataFrame:
    if max_rows <= 0:
        raise ValueError("max_rows must be > 0")
    if max_rows >= len(df):
        return df

    rng = np.random.default_rng(seed)
    split_counts = df["split"].astype(str).value_counts().to_dict()
    split_names = ["train", "val", "test"]
    split_ratios = np.array([split_counts[name] / len(df) for name in split_names], dtype=np.float64)

    target = np.floor(split_ratios * max_rows).astype(np.int64)
    target[-1] = max_rows - int(target[0] + target[1])

    sampled_parts = []
    for idx, name in enumerate(split_names):
        split_df = df[df["split"] == name]
        n = int(min(target[idx], len(split_df)))
        indices = rng.choice(split_df.index.to_numpy(), size=n, replace=False)
        sampled_parts.append(split_df.loc[np.sort(indices)])

    out = pd.concat(sampled_parts, axis=0).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return out


def cast_feature_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in BOOL_FEATURES:
        out[col] = out[col].astype(np.int8)
    out["sex"] = out["sex"].astype(str)
    return out


def split_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df = df[df["split"] == "val"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)
    return train_df, val_df, test_df


def load_stage1_dataset(config: dict[str, Any], max_rows: int | None = None) -> Stage1DatasetBundle:
    data_path = resolve_repo_path(config["data_path"])
    if not data_path.exists():
        raise DataContractError(f"Dataset parquet missing: {data_path}")

    _validate_schema_file(resolve_repo_path(config["schema_path"]), str(config["schema_version"]))

    df = pd.read_parquet(data_path)
    validate_data_contract(df, config)

    if max_rows is not None:
        df = _downsample_by_split(df, max_rows=max_rows, seed=int(config["seed"]))

    df = add_engineered_features(df)
    df = cast_feature_dtypes(df)

    train_df, val_df, test_df = split_dataset(df)
    return Stage1DatasetBundle(full_df=df, train_df=train_df, val_df=val_df, test_df=test_df)
