# Hepatica Prototype

Hepatica is a local-first clinical workflow prototype for advanced fibrosis/cirrhosis risk triage and fibrosis staging.
It is designed to be demoable end-to-end on a laptop (no AWS/Firebase required) while still supporting cloud-backed
deployments when configured.

Clinical note: this is decision-support software, not a diagnostic device. Generated outputs must be reviewed by a
qualified clinician and validated against local guidelines.

## What This Prototype Demonstrates

- Doctor authentication (local dev "demo doctors" login; Firebase/Cognito optional)
- Patient create + list + detail + timeline
- Stage 1: clinical risk triage (rule engine, optional ML artifacts)
- Stage 2: scan upload + fibrosis inference (local upload mode for demos)
- Knowledge blocks (retrieval + synthesis; local fallback embeddings)
- Report PDF generation and in-browser viewing

## Model Accuracy (Last Trained)

These numbers are from the most recent local retrain on this machine (seed `42`). Re-run training to reproduce and refresh.

- Stage 1 (tabular, `data/synthetic/stage1_synth_v1.parquet`; model `clinical-stage1-gbdt:v20260210.0219.seed42`)
  - Val: accuracy `0.997167`, macro-F1 `0.995589`
  - Test: accuracy `0.996567`, macro-F1 `0.994597`
- Stage 2 (image, `data/Images/`; model `fibrosis_model.pt`)
  - Val: accuracy `0.975764`, macro-F1 `0.966753`, severe recall (F2/F3/F4) `0.974790/0.899225/1.000000`
  - Test: accuracy `0.959958`, macro-F1 `0.943888`, severe recall (F2/F3/F4) `0.890756/0.922481/0.980392`

## Model Accuracy Test

Fail-fast validation for the currently trained artifacts:

```bash
cd ml
.venv/bin/python scripts/check_model_metrics.py
```

## Tech Stack (Detailed)

### Frontend

- Framework: Next.js `15.5.10` (App Router)
- UI runtime: React `18.3.1`
- Language/tooling: TypeScript `5.7.2`, ESLint `8.57.1`

### Backend

- API framework: FastAPI `0.116.1` + Uvicorn `0.35.0`
- Validation/config: Pydantic `2.11.7`, pydantic-settings `2.10.1`
- Database ORM/migrations: SQLAlchemy `2.0.43`, Alembic `1.16.4`
- Rate limiting: SlowAPI `0.1.9`
- Auth/JWT: python-jose `3.4.0`
- Storage integrations: boto3 `1.40.12` (S3, Bedrock embeddings)
- PDF generation: ReportLab `4.4.3`
- Image + quality tooling: Pillow `11.3.0`, OpenCV-headless `4.12.0.88`, pydicom `3.0.1`

### ML / Data

- Stage 2 image model: PyTorch `2.5.1`, torchvision `0.20.1`
- Stage 1 tabular pipeline: scikit-learn `1.6.1` + joblib `1.4.2`
- Data tooling: pandas, numpy, pyarrow

### Infra (Optional)

- IaC: Terraform (validated against `1.10.5`)

## Architecture (How It Works)

### BFF authentication (cookies + CSRF)

- Backend issues an HTTP-only session cookie (`hp_session`) and a CSRF cookie (`hp_csrf`).
- Frontend never stores tokens; it calls `GET /api/v1/auth/session` and includes CSRF header for mutating calls.

Reason: browser-native cookie session handling keeps the frontend simpler and reduces token-handling pitfalls; CSRF
protection makes cookie auth safe for state-changing requests.

### Local-first uploads and browser-openable PDFs

The demo flow is designed to work without AWS credentials:

- In `ENVIRONMENT=development`, `UPLOAD_MODE=auto` resolves to local upload mode.
- `POST /api/v1/scans/upload-url` returns either a presigned S3 URL (cloud) or a backend local upload endpoint (demo).
- Reports always return `pdf_download_url` as `GET /api/v1/reports/{id}/pdf`, so the browser can open the PDF in all
  modes (S3 or local filesystem).

Reason: demos fail fast when cloud credentials are missing; local mode removes that dependency while preserving the
same overall shape as a production “presigned upload” design.

### Stage 1 vs Stage 2 (two-stage pipeline)

- Stage 1 is deterministic and fast: rules compute FIB-4/APRI and map to risk tiers; ML can optionally override.
- Stage 2 is file-based and safety-gated: AV hook, DICOM conversion, image quality checks, then inference.

Reason: keeps “always works” triage available while treating uploads/inference as higher risk and higher variance.

## Quickstart (Local Demo)

### 1) Backend

```bash
cd backend
cp .env.example .env
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# Optional (recommended): run migrations explicitly. In local dev + SQLite, the API will also auto-create tables
# on first boot so the demo can start without extra steps.
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Why: in `development`, the backend defaults `UPLOAD_MODE=auto` -> local uploads, so scan uploads and report PDFs work
without AWS credentials.

Local storage paths (defaults):
- scan bytes: `backend/artifacts/uploads/`
- report PDFs: `backend/artifacts/reports/`

### 2) Frontend

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000/login` and use a 1-click demo doctor:
- `asha.singh@demo.hepatica`
- `maya.chen@demo.hepatica`
- `alex.rivera@demo.hepatica`

## API Overview (Most Important Endpoints)

Base prefix: `/api/v1`

- Auth:
  - `POST /auth/dev-login` (development only; demo doctors)
  - `POST /auth/firebase-login` (optional; needs Firebase env)
  - `GET /auth/session` (returns CSRF token + header name)
  - `POST /auth/logout`
- Patients:
  - `GET /patients` (scoped to the signed-in doctor)
  - `POST /patients`
  - `GET /patients/{patient_id}`
  - `GET /patients/{patient_id}/timeline`
- Stage 1:
  - `POST /assessments/clinical`
- Stage 2:
  - `POST /scans/upload-url` (returns upload target)
  - `PUT /scans/upload/{scan_asset_id}` (local upload mode)
  - `POST /assessments/fibrosis`
- Knowledge + Reports:
  - `POST /knowledge/explain`
  - `POST /reports`
  - `GET /reports/{report_id}`
  - `GET /reports/{report_id}/pdf`
- Model readiness:
  - `GET /models/status`

Reason: these map directly to the UI workflow and cover the complete demo path.

## Configuration (Important Env Vars)

Backend: `backend/.env` (see `backend/.env.example`)
- `ENVIRONMENT=development|production`
- `AUTH_PROVIDER=firebase|cognito`
- `ENABLE_DEV_AUTH=true|false` (controls `POST /api/v1/auth/dev-login`; defaults to enabled in development)
- `SESSION_ENCRYPTION_KEY=...` (must be strong for non-dev)
- `UPLOAD_MODE=auto|local|s3` (auto=local in development, s3 otherwise)
- `LOCAL_STORAGE_DIR=../backend/artifacts` (where local uploads/PDFs are stored)
- `STAGE1_ML_ENABLED=true` and `STAGE1_MODEL_ARTIFACT_DIR=...` (optional artifacts)
- `MODEL_ARTIFACT_PATH=...` and `TEMPERATURE_ARTIFACT_PATH=...` (Stage 2 artifacts in non-dev)

Frontend: `frontend/.env.local` (see `frontend/.env.local.example`)
- `NEXT_PUBLIC_API_BASE=http://localhost:8000`
- `NEXT_PUBLIC_ENABLE_DEV_AUTH=true` (shows demo doctor login UI)

## Repo Guide (Documentation Map)

Folder docs (each explains the "why" and the boundaries):
- Backend service: `backend/README.md`
- Frontend console: `frontend/README.md`
- ML pipelines: `ml/README.md`
- Infra (Terraform): `infra/README.md`
- Data layout: `data/README.md`
- Release/deploy helper scripts: `scripts/README.md`
- CI / repo automation: `.github/README.md`

Cross-cutting docs:
- Testing: `TESTING.md`
- Architecture + API + security: `docs/README.md`

Recommended reading order (professional onboarding):
1) `docs/architecture.md` (how the system fits)
2) `docs/security.md` (auth/CSRF/uploads guardrails)
3) `docs/api.md` (endpoint shapes and intent)
4) `backend/README.md` and `frontend/README.md` (service-level ownership)
5) `TESTING.md` (repeatable validation)

## One-command Preflight

Runs backend tests, backend smoke flow, frontend lint/audit/build, and infra validation:

```bash
make preflight
```

## Project Layout (Where Things Live)

- `backend/`: FastAPI + SQLAlchemy service (APIs, auth, inference orchestration)
- `frontend/`: Next.js doctor console (multi-page, interactive UI)
- `ml/`: training/evaluation pipelines and artifact contracts
- `data/`: demo/training data layout (images and synthetic tabular artifacts)
- `infra/`: Terraform for optional staging
- `scripts/`: repo-level helpers for preflight/staging/release workflows
- `docs/`: cross-cutting architecture/API/security/ops documentation

## Database Model (What We Store and Why)

The backend stores workflow state in a relational schema (SQLite for local by default; Postgres optional):
- Users + sessions (cookie sessions)
- Patients (doctor-owned)
- Clinical assessments (Stage 1 outputs)
- Scan assets (upload metadata + storage key/path)
- Fibrosis predictions (Stage 2 outputs)
- Knowledge chunks (ingested literature + embeddings)
- Reports (JSON + PDF object key/path)
- Timeline events (patient-centric event log)
- Audit logs (security and action trace)

Reason: patient-centric workflows naturally map to relational entities, and the schema provides an auditable history.

## Design Principles (Reasons)

- Local-first demo: local upload + PDF serving avoids "blocked by missing cloud credentials" during a demo.
- Strict in non-dev: the backend has guardrails to fail fast in production if required ML artifacts are missing.
- BFF-style auth: backend owns session cookies and CSRF; frontend stays simple and avoids storing tokens.
- Defensive file handling: content-type allowlist, size limits, AV hook, DICOM conversion, and quality gating.

## Testing and Quality

Primary commands:
- Full preflight: `make preflight`
- Backend tests: `cd backend && pytest`
- Backend smoke: `cd backend && make smoke`
- Frontend lint/build: `cd frontend && npm run lint && npm run build`

Why these checks:
- Backend tests protect contracts (auth/CSRF/ownership) and inference orchestration.
- Smoke flow confirms the end-to-end workflow stays demoable.
- Frontend lint/build ensures the console ships as a coherent UX.

## Troubleshooting (Common)

- Dev login UI not showing: set `NEXT_PUBLIC_ENABLE_DEV_AUTH=true` in `frontend/.env.local`. If you explicitly disabled
  it server-side, set `ENABLE_DEV_AUTH=true` in `backend/.env`.
- Upload fails in local demo: ensure `ENVIRONMENT=development` and `UPLOAD_MODE=auto` (or `local`) in `backend/.env`.
- PDF “Open” fails: it should use `/api/v1/reports/{id}/pdf`; if not, check `backend/app/api/v1/reports.py`.
- Stage 2 returns 422 quality errors: try a higher-resolution/less-blurry image (quality gates are strict by design).

## Roadmap (Pragmatic Next Steps)

- Production auth UI: add Firebase login UI (passwordless or SSO) and role/tenant management.
- Cloud upload hardening: multipart uploads, checksums, background scan/quality jobs, and status transitions.
- Observability: request ids, structured logs, tracing, error monitoring, and performance metrics.
- ML promotion: registry-backed artifact download, reproducible evaluation reports, drift monitoring integration.
