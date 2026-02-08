# ML Pipelines

## Install

```bash
cd /Users/praty/hepatica-p/ml
python3 -m pip install -r requirements.txt
```

## Stage 1 (Tabular, Offline, Dual-Task)

### Commands

```bash
cd /Users/praty/hepatica-p/ml
python3 scripts/train_stage1.py --config configs/train_stage1.yaml
python3 scripts/evaluate_stage1.py --config configs/train_stage1.yaml
```

Optional smoke mode:

```bash
python3 scripts/train_stage1.py --config configs/train_stage1.yaml --max-rows 30000
python3 scripts/evaluate_stage1.py --config configs/train_stage1.yaml --max-rows 30000
```

Optional registry sync (manual only):

```bash
python3 scripts/register_stage1_model.py --database-url "$DATABASE_URL" --artifact-dir artifacts/stage1
```

### Outputs

- `artifacts/stage1/stage1_preprocessor.joblib`
- `artifacts/stage1/stage1_classifier.joblib`
- `artifacts/stage1/stage1_reg_probability.joblib`
- `artifacts/stage1/stage1_reg_latent.joblib`
- `artifacts/stage1/stage1_feature_manifest.json`
- `artifacts/stage1/stage1_metrics_val.json`
- `artifacts/stage1/stage1_metrics_test.json`
- `artifacts/stage1/stage1_confusion_matrix.json`
- `artifacts/stage1/stage1_calibration.json`
- `artifacts/stage1/stage1_explain_global.json`
- `artifacts/stage1/stage1_explain_local_class.json`
- `artifacts/stage1/stage1_explain_local_regression.json`
- `artifacts/stage1/stage1_run_metadata.json`
- `artifacts/stage1/stage1_evaluation_report.json`
- `artifacts/stage1/stage1_evaluation_report.md`

### Strict Gates

Training exits non-zero if any gate fails:

- Val macro-F1 >= `0.93`
- Val recall HIGH >= `0.90`
- Val recall MODERATE >= `0.88`
- Test macro-F1 >= `0.91`
- Val MAE (`probability_rule`) <= `0.025`
- Val MAE (`latent_fibrosis_score`) <= `0.060`
- Val ECE <= `0.05`

## Stage 2 (Image Fibrosis)

### Commands

```bash
cd /Users/praty/hepatica-p/ml
python3 scripts/train.py
python3 scripts/evaluate.py
```

### Outputs

- `artifacts/fibrosis_model.pt`
- `artifacts/temperature_scaling.json`
- `artifacts/metrics.json`
- `artifacts/split_indices.json`
- `artifacts/classes.json`

### Acceptance Gates

Training exits non-zero if these validation thresholds are not met:

- Macro F1 >= `0.72`
- Recall for `F2`, `F3`, `F4` each >= `0.65`
