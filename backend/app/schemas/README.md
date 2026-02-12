# backend/app/schemas Folder Guide

## Purpose
Pydantic request/response contracts for all API payloads.

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `assessment.py` | Python module implementing domain-specific logic for this folder. |
| `assistant.py` | Request/response models for doctor assistant chat. |
| `auth.py` | Authentication/session handling logic. |
| `knowledge.py` | Knowledge retrieval, chunking, and explainability support. |
| `model_status.py` | Model registry/status or model lifecycle helper. |
| `patient.py` | Patient data API/schema test or helper logic. |
| `report.py` | Report payload assembly or PDF/report endpoint logic. |
| `stage3.py` | Stage 3 multimodal scoring, API schema, or support logic. |
| `timeline.py` | Timeline persistence or rendering contract logic. |
