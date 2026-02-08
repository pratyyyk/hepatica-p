# Fibrosis Model Training

## Commands

```bash
cd /Users/praty/hepatica-p/ml
python3 -m pip install -r requirements.txt
python3 scripts/train.py
python3 scripts/evaluate.py
```

## Outputs

- `artifacts/fibrosis_model.pt`
- `artifacts/temperature_scaling.json`
- `artifacts/metrics.json`
- `artifacts/split_indices.json`
- `artifacts/classes.json`

## Acceptance Gates

Training exits non-zero if these validation thresholds are not met:

- Macro F1 >= `0.72`
- Recall for `F2`, `F3`, `F4` each >= `0.65`
