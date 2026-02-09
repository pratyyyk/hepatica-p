# Hepatica Prototype

Hepatica is a local-first clinical workflow prototype for advanced fibrosis/cirrhosis risk triage and fibrosis staging.
It is designed to be demoable end-to-end on a laptop (no AWS/Firebase required) while still supporting cloud-backed
deployments when configured.

## What This Prototype Demonstrates

- Doctor authentication (local dev "demo doctors" login; Firebase/Cognito optional)
- Patient create + list + detail + timeline
- Stage 1: clinical risk triage (rule engine, optional ML artifacts)
- Stage 2: scan upload + fibrosis inference (local upload mode for demos)
- Knowledge blocks (retrieval + synthesis; local fallback embeddings)
- Report PDF generation and in-browser viewing

## Quickstart (Local Demo)

### 1) Backend

```bash
cd backend
cp .env.example .env
# ensure ENVIRONMENT=development and ENABLE_DEV_AUTH=true in .env
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Why: in `development`, the backend defaults `UPLOAD_MODE=auto` -> local uploads, so scan uploads and report PDFs work
without AWS credentials.

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

## One-command Preflight

Runs backend tests, backend smoke flow, frontend lint/audit/build, and infra validation:

```bash
make preflight
```

## Design Principles (Reasons)

- Local-first demo: local upload + PDF serving avoids "blocked by missing cloud credentials" during a demo.
- Strict in non-dev: the backend has guardrails to fail fast in production if required ML artifacts are missing.
- BFF-style auth: backend owns session cookies and CSRF; frontend stays simple and avoids storing tokens.
- Defensive file handling: content-type allowlist, size limits, AV hook, DICOM conversion, and quality gating.

