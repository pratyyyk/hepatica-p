# Hepatica

Clinical liver risk platform with three integrated stages:
- Stage 1: non-invasive clinical risk scoring.
- Stage 2: fibrosis imaging inference (F0-F4) with quality gates.
- Stage 3: multimodal monitoring (clinical + imaging + stiffness + longitudinal alerting + explainability).

This repository now uses **folder-level `README.md` documentation** as the primary documentation system.

## 1. Project Overview

Hepatica is a clinician-facing decision-support system for local/demo use.
- Backend: FastAPI + SQLAlchemy + Alembic + PDF generation.
- Frontend: Next.js App Router (TypeScript).
- ML: Stage 1 and Stage 3 tabular models + Stage 2 imaging pipeline tooling.
- Data: local image folders and synthetic datasets.

## 2. Problem Statement and Background

Chronic liver disease monitoring often depends on fragmented signals:
- clinical labs and comorbidities,
- imaging-derived fibrosis probabilities,
- intermittent stiffness measurements.

Without integration, longitudinal risk trends and high-confidence alerts are inconsistent. Hepatica addresses this by unifying these signals in one staged workflow, while preserving non-diagnostic positioning for clinician oversight.

## 3. Proposed Solution / Technology

Hepatica uses a staged architecture:
- **Stage 1 (clinical):** deterministic + ML-assisted non-invasive risk (FIB-4/APRI + model support).
- **Stage 2 (imaging):** image upload + quality checks + fibrosis class probabilities.
- **Stage 3 (multimodal):** composite risk score, progression/decompensation 12-month risks, alert lifecycle, explainability payloads, and scheduled monitoring.

Core technologies:
- FastAPI, SQLAlchemy, Alembic, Pydantic, ReportLab
- Next.js 15, React 18, TypeScript
- scikit-learn, PyTorch tooling, pandas/numpy/pyarrow

## 4. Methodology and Implementation Approach

### 4.1 Architecture
- `backend/`: APIs, domain services, DB models/migrations, scripts/tests.
- `frontend/`: clinician UI for all stages, patient tracking, timeline, and reporting.
- `ml/`: data generation, train/eval/register scripts, model artifacts.
- `data/`: local image classes and synthetic schema/profile files.
- `infra/` + `scripts/`: validation/release/staging automation.

### 4.2 Stage 3 activation model
Stage 3 is **feature flagged** and can be intentionally disabled by default.
Set in `backend/.env`:
- `STAGE3_ENABLED=true`
- `STAGE3_MONITORING_MODE=scheduled_only`
- `STAGE3_MONITOR_INTERVAL_WEEKS=10`
- `STAGE3_ALERT_PPV_TARGET=0.85`
- `STAGE3_ALERT_RECALL_FLOOR=0.65`
- `STAGE3_STIFFNESS_PROXY_ENABLED=true`

Then restart backend.

### 4.3 Local setup

#### Backend
```bash
cd /Users/praty/hepatica-p/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
make init-db
make run
```

#### Frontend
```bash
cd /Users/praty/hepatica-p/frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

#### ML (optional for retraining)
```bash
cd /Users/praty/hepatica-p/ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.4 Synthetic Stage 3 dataset and training
```bash
cd /Users/praty/hepatica-p/ml
python3 scripts/generate_stage3_synthetic.py --patients 250000 --visits 12
python3 scripts/train_stage3.py --config configs/train_stage3.yaml
python3 scripts/register_stage3_model.py --artifact-dir /Users/praty/hepatica-p/ml/artifacts/stage3
```

### 4.5 Running scheduled Stage 3 monitoring
```bash
cd /Users/praty/hepatica-p/backend
STAGE3_ENABLED=true python3 scripts/run_stage3_monitoring.py
```

## 5. Results / Prototype Demonstration

The prototype demonstrates:
- patient create/select/delete flows,
- Stage 1 assessment,
- Stage 2 upload + fibrosis inference + knowledge blocks,
- Stage 3 stiffness capture + multimodal risk + alerts + explainability,
- integrated report generation (including Stage 1/2/3 sections).

Smoke flow:
```bash
cd /Users/praty/hepatica-p/backend
python3 scripts/smoke_flow.py
```

Evidence smoke (JSON + markdown):
```bash
cd /Users/praty/hepatica-p/backend
python3 scripts/smoke_evidence.py
```

## 6. Impact and Future Scope

Expected impact:
- better continuity across clinical, imaging, and monitoring signals,
- higher-quality follow-up prioritization using precision-focused alerts,
- clearer patient-level decision support through explainability and trends.

Future scope:
- production-grade external notification channels,
- multi-site calibration and drift dashboards,
- broader EHR integration and deployment hardening.

## 7. Visual Appeal & Organization

UI is organized into:
- assessment workspace (Stage 1 / Stage 2 / Stage 3),
- patient list + patient detail timeline,
- report center.

Design direction is clinical and clean: restrained palette, straightforward typography, high signal-to-noise data blocks, and explicit status messaging.

## 8. Clarity of Information

Documentation strategy in this repo:
- every key folder has its own `README.md` with file-by-file roles,
- root `README.md` explains architecture, execution, testing, and deployment,
- endpoint contracts and behavior are captured in backend tests and schema modules.

## 9. Scalability & Sustainability

Scalability controls already present:
- feature flags for controlled rollout (`STAGE3_ENABLED` etc.),
- schema migrations via Alembic,
- model registry endpoints and activation controls,
- synthetic data tooling for pipeline continuity,
- release preflight automation.

Sustainability practices:
- local reproducibility through pinned dependency files,
- CI workflows in `.github/workflows/`,
- contract tests for API and model-quality gates.

## 10. References

- FIB-4 and APRI score conventions (clinical hepatology practice)
- FastAPI, SQLAlchemy, Alembic, Next.js official documentation
- scikit-learn and PyTorch documentation

## Tests and Verification

Run full preflight:
```bash
cd /Users/praty/hepatica-p
./scripts/release_preflight.sh
```

Or run targeted checks:
```bash
cd /Users/praty/hepatica-p/backend
python3 -m pytest -q

cd /Users/praty/hepatica-p/frontend
npm run lint
npm run build

cd /Users/praty/hepatica-p/infra
./scripts/validate.sh
```

## Documentation Index

Use these entry points:
- `/Users/praty/hepatica-p/backend/README.md`
- `/Users/praty/hepatica-p/frontend/README.md`
- `/Users/praty/hepatica-p/ml/README.md`
- `/Users/praty/hepatica-p/data/README.md`
- `/Users/praty/hepatica-p/infra/README.md`
- `/Users/praty/hepatica-p/scripts/README.md`
- `/Users/praty/hepatica-p/.github/README.md`
- `/Users/praty/hepatica-p/docs/README.md`
