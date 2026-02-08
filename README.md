# Hepatica MVP

Clinical workflow MVP for advanced fibrosis/cirrhosis risk triage and fibrosis staging.

## Stack

- Frontend: Next.js (`/frontend`)
- Backend: FastAPI + SQLAlchemy (`/backend`)
- ML: PyTorch training/evaluation (`/ml`)
- Infra: Terraform on AWS (`/infra`)

## Quick Start

### 1) Backend

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
python3 -m pip install -r requirements.txt
python3 -m app.db.init_db
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
python3 scripts/ingest_journals.py
```

### 4) Optional: Model Training

```bash
cd /Users/praty/hepatica-p/ml
python3 -m pip install -r requirements.txt
python3 scripts/train.py
python3 scripts/evaluate.py
```

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
