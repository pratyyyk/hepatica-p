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

## How Backend Uses ML

- Stage 1: rule engine always runs; ML artifacts can override tier/probability when enabled and available.
- Stage 2: in development, the backend can fall back to a heuristic logits model if artifacts are missing.
  In non-dev, artifacts can be required.

