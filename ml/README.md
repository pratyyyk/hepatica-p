# ML

The `ml/` folder contains training/evaluation pipelines. The backend can optionally load produced artifacts.

## Stage 1 (Tabular)

Goal: predict risk tier + probability from clinical features (with strict offline gates).

Outputs are expected under `ml/artifacts/stage1/`:
- `stage1_preprocessor.joblib`
- `stage1_classifier.joblib`
- `stage1_reg_probability.joblib`
- plus metrics and metadata json

Why artifacts are split: preprocessing and models evolve independently, and the backend loads only what it needs.

## Stage 2 (Images)

Goal: classify fibrosis stage (F0..F4) from an image.

Outputs under `ml/artifacts/`:
- `fibrosis_model.pt`
- `temperature_scaling.json`

Why temperature scaling: improves probability calibration while keeping inference runtime simple.

## Stage 3 (Multimodal Longitudinal Risk)

Goal: combine clinical non-invasive scores, Stage 2 image outputs, and liver stiffness signals into longitudinal
risk monitoring with precision-focused alert thresholds.

Synthetic pipeline:
- `ml/scripts/generate_stage3_synthetic.py` (default target: 250k patients x 12 visits)

Training + registration:
- `ml/scripts/train_stage3.py`
- `ml/scripts/register_stage3_model.py`

Outputs under `ml/artifacts/stage3/`:
- `stage3_risk_model.joblib`
- `stage3_thresholds.json`
- `stage3_feature_manifest.json`
- `stage3_run_metadata.json`

## How Backend Uses ML

- Stage 1: rule engine always runs; ML artifacts can override tier/probability when enabled and available.
- Stage 2: in development, the backend can fall back to a heuristic logits model if artifacts are missing.
  In non-dev, artifacts can be required.
