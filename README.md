# Hepatica MVP

Clinical workflow MVP for advanced fibrosis/cirrhosis risk triage and fibrosis staging.

## Stack

- Frontend: Next.js (`/frontend`)
- Backend: FastAPI + SQLAlchemy (`/backend`)
- ML: PyTorch training/evaluation (`/ml`)
- Infra: Terraform on AWS (`/infra`)

## Quick Start

Python runtime: `3.11` (repo pin in `/Users/praty/hepatica-p/.python-version`).

### 1) Backend

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
python3.11 -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend

```bash
cd /Users/praty/hepatica-p/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### 3) Optional: Journal Ingestion

```bash
cd /Users/praty/hepatica-p/backend
python3.11 scripts/ingest_journals.py
```

### 4) Optional: Model Training

```bash
cd /Users/praty/hepatica-p/ml
python3.11 -m pip install -r requirements.txt
python3.11 scripts/train.py
python3.11 scripts/evaluate.py
```

## Release Preflight (One Command)

```bash
cd /Users/praty/hepatica-p
make preflight
```

This runs backend tests, backend smoke flow, frontend lint/audit/build, infra validation, and backend container build (if Docker daemon is available).

## Staging Deploy Helper

```bash
cd /Users/praty/hepatica-p
make staging-plan
make staging-apply
```

Requirements:
- AWS CLI authenticated (`aws sts get-caller-identity`)
- `/Users/praty/hepatica-p/infra/terraform.tfvars` populated
- Terraform `1.10.5` available in PATH (enforced by `infra/scripts/validate.sh`)

## API Contract

OpenAPI spec: `/Users/praty/hepatica-p/docs/openapi.yaml`

## Core Endpoints

- `POST /api/v1/patients`
- `GET /api/v1/patients/{patientId}`
- `POST /api/v1/assessments/clinical`
- `POST /api/v1/scans/upload-url`
- `POST /api/v1/assessments/fibrosis`
- `POST /api/v1/knowledge/explain`
- `POST /api/v1/reports`
- `GET /api/v1/reports/{reportId}`
- `GET /api/v1/patients/{patientId}/timeline`

## Dataset Paths

- Images: `/Users/praty/hepatica-p/data/Images/F0..F4`
- Journals: `/Users/praty/journals`
