from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ML_ROOT = Path("/Users/praty/hepatica-p/ml")
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from src.stage1_data import ENGINEERED_FEATURES, FEATURE_COLUMNS, load_stage1_dataset
from src.stage1_explainability import (
    compute_global_importance,
    compute_local_class_summary,
    compute_local_regression_summary,
)
from src.stage1_modeling import (
    check_strict_gates,
    evaluate_stage1_models,
    fit_stage1_models,
    load_stage1_models,
    save_stage1_models,
)


@pytest.fixture(scope="session")
def stage1_config() -> dict:
    cfg_path = ML_ROOT / "configs" / "train_stage1.yaml"
    return yaml.safe_load(cfg_path.read_text())


@pytest.fixture(scope="session")
def subset_bundle(stage1_config):
    return load_stage1_dataset(stage1_config, max_rows=12000)


@pytest.fixture(scope="session")
def trained_models(stage1_config, subset_bundle):
    return fit_stage1_models(subset_bundle.train_df, stage1_config)


@pytest.fixture(scope="session")
def val_eval(trained_models, subset_bundle):
    return evaluate_stage1_models(trained_models, subset_bundle.val_df, split_name="val")


def test_data_contract_and_feature_engineering(stage1_config, subset_bundle):
    full_df = subset_bundle.full_df
    assert set(ENGINEERED_FEATURES).issubset(full_df.columns)
    assert set(FEATURE_COLUMNS).issubset(full_df.columns)
    assert len(full_df) == 12000
    assert full_df[ENGINEERED_FEATURES].isna().sum().sum() == 0


def test_training_determinism(stage1_config, subset_bundle, val_eval):
    models_2 = fit_stage1_models(subset_bundle.train_df, stage1_config)
    val_eval_2 = evaluate_stage1_models(models_2, subset_bundle.val_df, split_name="val")

    a = val_eval.metrics
    b = val_eval_2.metrics
    assert "accuracy" in a["classification"]
    assert abs(a["classification"]["macro_f1"] - b["classification"]["macro_f1"]) <= 1e-6
    assert (
        abs(
            a["regression"]["probability_rule"]["mae"]
            - b["regression"]["probability_rule"]["mae"]
        )
        <= 1e-6
    )
    assert (
        abs(
            a["regression"]["latent_fibrosis_score"]["mae"]
            - b["regression"]["latent_fibrosis_score"]["mae"]
        )
        <= 1e-6
    )


def test_gate_enforcement_catches_bad_metrics(stage1_config):
    bad_val = {
        "classification": {
            "macro_f1": 0.40,
            "per_class_recall": {"LOW": 0.95, "MODERATE": 0.50, "HIGH": 0.50},
            "ece": 0.30,
        },
        "regression": {
            "probability_rule": {"mae": 0.2},
            "latent_fibrosis_score": {"mae": 0.2},
        },
    }
    bad_test = {
        "classification": {
            "macro_f1": 0.50,
            "per_class_recall": {"LOW": 0.9, "MODERATE": 0.6, "HIGH": 0.6},
            "ece": 0.2,
        },
        "regression": {
            "probability_rule": {"mae": 0.2},
            "latent_fibrosis_score": {"mae": 0.2},
        },
    }

    failures = check_strict_gates(bad_val, bad_test, stage1_config["gates"])
    assert failures
    assert any("val_macro_f1" in f for f in failures)
    assert any("val_probability_mae" in f for f in failures)
    assert any("val_ece" in f for f in failures)


def test_evaluation_consistency_after_reload(tmp_path, trained_models, subset_bundle, val_eval):
    save_stage1_models(trained_models, tmp_path)
    manifest = {
        "feature_baseline": trained_models.feature_baseline.tolist(),
    }
    (tmp_path / "stage1_feature_manifest.json").write_text(json.dumps(manifest))

    loaded = load_stage1_models(tmp_path)
    re_eval = evaluate_stage1_models(loaded, subset_bundle.val_df, split_name="val")

    assert abs(re_eval.metrics["classification"]["macro_f1"] - val_eval.metrics["classification"]["macro_f1"]) <= 1e-10
    assert (
        abs(
            re_eval.metrics["regression"]["probability_rule"]["mae"]
            - val_eval.metrics["regression"]["probability_rule"]["mae"]
        )
        <= 1e-10
    )


def test_explainability_artifacts_shape(stage1_config, trained_models, val_eval):
    global_imp = compute_global_importance(
        models=trained_models,
        eval_bundle=val_eval,
        random_state=int(stage1_config["seed"]),
        n_repeats=2,
        max_samples=2000,
    )
    local_cls = compute_local_class_summary(trained_models, val_eval, top_n=50)
    local_reg = compute_local_regression_summary(trained_models, val_eval, top_n=50)

    assert set(global_imp.keys()) == {"classifier_macro_f1", "reg_probability_mae", "reg_latent_mae"}
    assert global_imp["classifier_macro_f1"]
    assert set(local_cls.keys()) == {"LOW", "MODERATE", "HIGH"}
    assert set(local_reg.keys()) == {"probability_rule", "latent_fibrosis_score"}


def test_end_to_end_smoke_artifacts(tmp_path):
    cfg = yaml.safe_load((ML_ROOT / "configs" / "train_stage1.yaml").read_text())
    cfg["artifact_dir"] = str(tmp_path / "artifacts")
    cfg_path = tmp_path / "train_stage1_smoke.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    subprocess.run(
        [
            sys.executable,
            str(ML_ROOT / "scripts" / "train_stage1.py"),
            "--config",
            str(cfg_path),
            "--max-rows",
            "6000",
        ],
        check=True,
        cwd=str(ML_ROOT),
    )

    subprocess.run(
        [
            sys.executable,
            str(ML_ROOT / "scripts" / "evaluate_stage1.py"),
            "--config",
            str(cfg_path),
            "--max-rows",
            "6000",
        ],
        check=True,
        cwd=str(ML_ROOT),
    )

    artifact_dir = Path(cfg["artifact_dir"])
    required = [
        "stage1_classifier.joblib",
        "stage1_reg_probability.joblib",
        "stage1_reg_latent.joblib",
        "stage1_feature_manifest.json",
        "stage1_metrics_val.json",
        "stage1_metrics_test.json",
        "stage1_confusion_matrix.json",
        "stage1_calibration.json",
        "stage1_run_metadata.json",
    ]
    for file_name in required:
        assert (artifact_dir / file_name).exists(), f"Missing artifact: {file_name}"
