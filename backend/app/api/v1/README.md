# backend/app/api/v1 Folder Guide

## Purpose
Versioned REST endpoints for auth, assessments, scans, reports, and Stage 3.

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `api.py` | Python module implementing domain-specific logic for this folder. |
| `assessments.py` | Python module implementing domain-specific logic for this folder. |
| `assistant.py` | Doctor assistant chatbot API for patient-aware Q&A. |
| `auth.py` | Authentication/session handling logic. |
| `knowledge.py` | Knowledge retrieval, chunking, and explainability support. |
| `models.py` | Model registry/status or model lifecycle helper. |
| `patients.py` | Patient data API/schema test or helper logic. |
| `reports.py` | Report payload assembly or PDF/report endpoint logic. |
| `scans.py` | Scan upload or file handling endpoint/service logic. |
| `stage3.py` | Stage 3 multimodal scoring, API schema, or support logic. |
| `timeline.py` | Timeline persistence or rendering contract logic. |
