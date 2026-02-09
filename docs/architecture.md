# Hepatica MVP Architecture

## Flow

1. Doctor authenticates via Firebase Auth (or dev login mode).
2. Doctor creates/selects de-identified patient.
3. Stage 1 endpoint computes FIB-4/APRI risk tier and persists output.
4. Scan upload URL is issued; file is uploaded to object storage (Firebase Storage/GCS or local fallback).
5. Stage 2 endpoint loads scan, runs antivirus hook + quality checks, infers fibrosis stage.
6. Knowledge endpoint retrieves journal chunks and synthesizes cited guidance blocks.
7. Report endpoint generates PDF and persists report metadata.
8. Timeline endpoint returns ordered patient events.

## Monorepo Layout

- `/Users/praty/hepatica-p/backend`: FastAPI + DB + services + tests.
- `/Users/praty/hepatica-p/frontend`: Next.js doctor dashboard.
- `/Users/praty/hepatica-p/ml`: training/evaluation artifacts and scripts.
- `/Users/praty/hepatica-p/infra`: legacy Terraform AWS baseline (optional).
- `/Users/praty/hepatica-p/docs`: API and implementation docs.

## Data Stores

- PostgreSQL: transactional entities + knowledge chunk metadata.
- pgvector-compatible embedding column for chunk vectors.
- Scan object storage: uploaded scan assets.
- Report object storage: rendered PDF reports.
- Model artifact storage: model artifacts.

## Security Controls (MVP)

- `DOCTOR` role enforcement middleware.
- audit log writes for login, prediction, report generation.
- de-identified patient profile schema.
- upload MIME and size validation.
- antivirus hook integration point.

## Operational Baseline

- CloudWatch dashboard and alarm.
- model metrics artifacts with acceptance thresholds.
- weekly drift-monitor script in ML package for scheduled run.
