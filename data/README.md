# data

Local datasets used for demos and training.

## Images

`data/Images/` is expected to have subfolders by fibrosis stage:
- `F0/`, `F1/`, `F2/`, `F3/`, `F4/`

Why: the Stage 2 pipeline uses an ImageFolder-style layout, and the backend can look up local images by filename.

## Synthetic (Stage 1)

`data/synthetic/` contains synthetic tabular artifacts for Stage 1 experimentation:
- parquet dataset + splits
- schema and profile json

Why: enables deterministic training and evaluation without PHI.

