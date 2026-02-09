# backend/scripts

Helper scripts for local workflows.

Common:
- `smoke_flow.py`: executes an end-to-end API flow using TestClient.
- `smoke_evidence.py`: produces smoke evidence artifacts.
- `generate_synthetic_clinical_dataset.py`: generates synthetic Stage 1 data artifacts.
- `export_openapi.py`: exports OpenAPI JSON to `docs/openapi.generated.json` (ignored by git).

Reason: scripts keep one-off operational tasks out of the request path and make repeatable workflows easy.

