# Backend (FastAPI)

## Purpose

The backend is the system-of-record and orchestration layer:
- owns auth sessions (cookies) + CSRF protection
- stores patients, assessments, predictions, reports, and timeline events
- runs Stage 1, Stage 2, and Stage 3 monitoring pipelines (with safety gates)

Reason: keeping the backend in control of state and security allows a thin frontend and a clear audit trail.

## Entry Points

- App: `backend/app/main.py`
- API router: `backend/app/api/v1/api.py`
- Settings: `backend/app/core/config.py` (Pydantic `Settings`)

## Run (Local)

```bash
cd backend
cp .env.example .env
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Auth (BFF)

Endpoints live in `backend/app/api/v1/auth.py`.

Modes:
- Dev login (demo): `POST /api/v1/auth/dev-login` in `ENVIRONMENT=development` (can be disabled via `ENABLE_DEV_AUTH=false`)
- Firebase login (optional): `POST /api/v1/auth/firebase-login`
- Cognito hosted UI (optional legacy): `GET /api/v1/auth/login` and callback

Why cookies + CSRF:
- cookies simplify browser auth but require CSRF protection for mutating methods
- CSRF is enforced by middleware in `backend/app/main.py`

## Uploads (Local-first)

- `UPLOAD_MODE=auto` resolves to local uploads in `development`, S3 otherwise.
- Local upload endpoint: `PUT /api/v1/scans/upload/{scan_asset_id}`
- Storage directory: `LOCAL_STORAGE_DIR` (defaults to `backend/artifacts/`)

Reason: demos should not fail due to missing AWS credentials while still preserving a presigned-upload model.

## Reports

- Report JSON + PDF generation in `backend/app/services/report.py`
- PDF streaming endpoint: `GET /api/v1/reports/{report_id}/pdf`

Reason: browsers cannot open server-local file paths; the backend endpoint makes the PDF reachable in all modes.

## Stage 3 Monitoring

- Stage 3 assessment endpoint: `POST /api/v1/assessments/stage3`
- Stiffness input endpoint: `POST /api/v1/patients/{patient_id}/stiffness`
- Explainability + monitoring endpoints:
  - `GET /api/v1/patients/{patient_id}/stage3/history`
  - `GET /api/v1/patients/{patient_id}/alerts`
  - `GET /api/v1/patients/{patient_id}/stage3/explainability`
- Scheduled batch runner: `python3 scripts/run_stage3_monitoring.py`

## Tests

```bash
cd backend
pytest
make smoke
```

Test setup notes:
- `backend/tests/conftest.py` forces development settings and uses a temporary SQLite DB.
