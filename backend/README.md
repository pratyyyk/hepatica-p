# Backend

FastAPI service for Stage 1 clinical risk, Stage 2 fibrosis inference, knowledge retrieval, reports, and timeline.

## Run

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
python3 -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
cd /Users/praty/hepatica-p/backend
python3 -m pytest
```

## Migrations

```bash
cd /Users/praty/hepatica-p/backend
alembic upgrade head
```

## Seed default registry rows (optional)

```bash
cd /Users/praty/hepatica-p/backend
python3 -m app.db.init_db
```
