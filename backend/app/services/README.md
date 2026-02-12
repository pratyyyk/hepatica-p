# backend/app/services Folder Guide

## Purpose
Business logic for scoring, inference, monitoring, upload, audit, and PDF rendering.

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `antivirus.py` | Python module implementing domain-specific logic for this folder. |
| `assistant_chat.py` | Patient-aware doctor chatbot response engine and citation retrieval. |
| `audit.py` | Python module implementing domain-specific logic for this folder. |
| `auth_session.py` | Authentication/session handling logic. |
| `dicom.py` | Python module implementing domain-specific logic for this folder. |
| `fibrosis_inference.py` | Stage 2 scan inference/calibration/quality handling. |
| `knowledge.py` | Knowledge retrieval, chunking, and explainability support. |
| `model_registry.py` | Model registry/status or model lifecycle helper. |
| `model_registry_admin.py` | Model registry/status or model lifecycle helper. |
| `quality.py` | Python module implementing domain-specific logic for this folder. |
| `report.py` | Report payload assembly or PDF/report endpoint logic. |
| `session_crypto.py` | Python module implementing domain-specific logic for this folder. |
| `stage1.py` | Stage 1 clinical scoring or model support module. |
| `stage1_ml_inference.py` | Stage 1 clinical scoring or model support module. |
| `stage3.py` | Stage 3 multimodal scoring, API schema, or support logic. |
| `stage3_monitoring.py` | Stage 3 scheduled monitoring logic and alerting workflow. |
| `stiffness_proxy.py` | Python module implementing domain-specific logic for this folder. |
| `timeline.py` | Timeline persistence or rendering contract logic. |
| `upload.py` | Scan upload or file handling endpoint/service logic. |
