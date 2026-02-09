# Backend

FastAPI service for Stage 1 clinical risk, Stage 2 fibrosis inference, knowledge retrieval, reports, and timeline.

Python runtime: `3.11`.

## Run

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
python3.11 -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
cd /Users/praty/hepatica-p/backend
python3.11 -m pytest
```

## One-command smoke flow

```bash
cd /Users/praty/hepatica-p/backend
make smoke
```

## Smoke evidence artifacts

```bash
cd /Users/praty/hepatica-p/backend
make smoke-evidence
```

Outputs:
- `artifacts/uat/uat_evidence.json`
- `artifacts/uat/uat_evidence.md`

## Migrations

```bash
cd /Users/praty/hepatica-p/backend
alembic upgrade head
```

## Seed default registry rows (optional)

```bash
cd /Users/praty/hepatica-p/backend
python3.11 -m app.db.init_db
```

## Model promotion CLI

```bash
cd /Users/praty/hepatica-p/backend
python3.11 scripts/model_registry.py list --name clinical-stage1-gbdt --json
python3.11 scripts/model_registry.py activate --name clinical-stage1-gbdt --version v20260208.1751.seed42
python3.11 scripts/model_registry.py deactivate --name clinical-stage1-gbdt --version v1 --allow-zero-active
```

Notes:
- `activate` is exclusive by default and deactivates other active versions for the same model name.
- Use `--keep-others-active` to opt out of exclusive activation.
- `deactivate` refuses to deactivate the last active version unless `--allow-zero-active` is set.

## Model status endpoint

Authenticated doctors can query active model versions and artifact health:

```bash
GET /api/v1/models/status
```
