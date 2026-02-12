# backend/scripts Folder Guide

## Purpose
Operational scripts for API export, synthetic data, smoke runs, and Stage 3 monitoring.

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `export_openapi.py` | Python module implementing domain-specific logic for this folder. |
| `generate_synthetic_clinical_dataset.py` | Synthetic dataset generator script. |
| `ingest_journals.py` | Python module implementing domain-specific logic for this folder. |
| `model_registry.py` | Model registry/status or model lifecycle helper. |
| `run_stage3_monitoring.py` | Stage 3 scheduled monitoring logic and alerting workflow. |
| `smoke_evidence.py` | Python module implementing domain-specific logic for this folder. |
| `smoke_flow.py` | Python module implementing domain-specific logic for this folder. |
| `start.sh` | Entrypoint: migrate DB then start uvicorn. |
