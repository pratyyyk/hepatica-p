from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.enums import RiskTier
from app.services.fibrosis_inference import FibrosisModelRuntime
from app.services.stage1_ml_inference import predict_stage1_ml


def _sample_image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(128, 96, 72))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_stage1_ml_prediction_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    artifact_dir = repo_root / "ml" / "artifacts" / "stage1"
    required = [
        artifact_dir / "stage1_preprocessor.joblib",
        artifact_dir / "stage1_classifier.joblib",
        artifact_dir / "stage1_reg_probability.joblib",
    ]
    if any(not path.exists() for path in required):
        pytest.skip(
            f"Stage 1 artifacts not present in checkout: {artifact_dir}. "
            "Run ml-stage1 workflow to produce them."
        )

    prediction = predict_stage1_ml(
        patient_sex="F",
        age=49,
        bmi=29.3,
        type2dm=True,
        ast=90.0,
        alt=70.0,
        platelets=130.0,
        ast_uln=40.0,
        artifact_dir=artifact_dir,
    )

    assert isinstance(prediction.risk_tier, RiskTier)
    assert 0.0 <= prediction.probability <= 0.95
    assert prediction.model_version


def test_fibrosis_runtime_requires_model_outside_dev(tmp_path: Path):
    settings = Settings(
        environment="production",
        stage2_require_model_non_dev=True,
        model_artifact_path=tmp_path / "missing-model.pt",
        temperature_artifact_path=tmp_path / "missing-temperature.json",
        local_image_root=tmp_path,
    )

    runtime = FibrosisModelRuntime(settings=settings)
    with pytest.raises(RuntimeError, match="Stage 2 model artifact is missing"):
        runtime.predict(_sample_image_bytes())


def test_fibrosis_runtime_uses_fallback_in_local_dev(tmp_path: Path):
    settings = Settings(
        environment="development",
        stage2_require_model_non_dev=True,
        model_artifact_path=tmp_path / "missing-model.pt",
        temperature_artifact_path=tmp_path / "missing-temperature.json",
        local_image_root=tmp_path,
    )

    runtime = FibrosisModelRuntime(settings=settings)
    result = runtime.predict(_sample_image_bytes())

    assert result.top1[0].value in {"F0", "F1", "F2", "F3", "F4"}
    assert result.model_version
