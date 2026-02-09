# ml/configs

Training configuration files.

- `train_stage1.yaml`: Stage 1 (tabular) config (data paths, gates, artifact output directory).
- `train.yaml`: Stage 2 (image) config (data root, hyperparameters, artifact output directory).

Why configs:
- Makes runs reproducible and reviewable.
- Keeps scripts thin and avoids hardcoding paths in code.

