# Testing

This repo is a local-first prototype. The default happy path is:
login (dev) -> patient -> Stage 1 -> upload scan (local) -> Stage 2 -> report PDF -> timeline.

## Quick (recommended)

Runs backend tests + backend smoke flow + frontend lint/audit/build + infra validation:

```bash
cd /Users/praty/hepatica-p
make preflight
```

## Backend

### Setup

Python runtime is pinned to `3.11` via `/Users/praty/hepatica-p/.python-version`. Create a venv and install deps:

```bash
cd /Users/praty/hepatica-p
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

### Run tests

```bash
cd /Users/praty/hepatica-p/backend
pytest
```

Notes:
- Tests set `ENVIRONMENT=development` and `ENABLE_DEV_AUTH=true` in `/Users/praty/hepatica-p/backend/tests/conftest.py`.
- Local upload mode is automatic in dev (`UPLOAD_MODE=auto` -> local). Uploads + PDFs go to `backend/artifacts/` by default.

### Run smoke flow

```bash
cd /Users/praty/hepatica-p/backend
make smoke
```

## Frontend

### Install + lint + build

```bash
cd /Users/praty/hepatica-p/frontend
npm ci
npm run lint
npm run build
```

### Local manual demo

1) Backend:

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

2) Frontend:

```bash
cd /Users/praty/hepatica-p/frontend
cp .env.local.example .env.local
npm run dev
```

Then open `http://localhost:3000/login` and use a 1-click demo doctor:
- `asha.singh@demo.hepatica`
- `maya.chen@demo.hepatica`
- `alex.rivera@demo.hepatica`

