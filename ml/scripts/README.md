# ml/scripts Folder Guide

## Purpose
Executable pipelines for training, evaluation, drift checks, synthetic generation, and registry updates.

## Files
| File | What it does |
|---|---|
| `check_model_metrics.py` | Model registry/status or model lifecycle helper. |
| `drift_monitor.py` | Data/model drift monitoring utilities. |
| `evaluate.py` | Evaluation pipeline for trained model outputs. |
| `evaluate_stage1.py` | Stage 1 clinical scoring or model support module. |
| `finalize_stage2_artifacts.py` | Stage 2 scan inference/calibration/quality handling. |
| `generate_stage3_synthetic.py` | Stage 3 multimodal scoring, API schema, or support logic. |
| `register_stage1_model.py` | Stage 1 clinical scoring or model support module. |
| `register_stage3_model.py` | Stage 3 multimodal scoring, API schema, or support logic. |
| `train.py` | Training pipeline entrypoint for model fitting. |
| `train_stage1.py` | Stage 1 clinical scoring or model support module. |
| `train_stage3.py` | Stage 3 multimodal scoring, API schema, or support logic. |
