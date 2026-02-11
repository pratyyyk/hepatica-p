# backend/app/services

Services hold application logic.

Highlights:
- `stage1.py`: deterministic clinical rule engine (always available)
- `stage1_ml_inference.py`: optional ML artifacts loader + predictor
- `fibrosis_inference.py`: Stage 2 inference runtime + strict artifact checks
- `stiffness_proxy.py`: Stage 3 liver stiffness proxy estimator when measured data is missing
- `stage3.py`: Stage 3 multimodal risk computation + alert creation helper
- `stage3_monitoring.py`: scheduled Stage 3 monitoring batch executor
- `upload.py`: content-type allowlist and (optional) S3 presign helper
- `knowledge.py`: chunking + embedding + retrieval + synthesis (with fallback embedding)
- `report.py`: report JSON + PDF rendering + storage helper

Reason: keeping services small and focused improves unit testability and makes behavior reusable across endpoints.
