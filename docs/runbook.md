# Runbook

Python runtime: `3.11`.

## Local startup

```bash
cd /Users/praty/hepatica-p/backend
cp .env.example .env
python3.11 -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd /Users/praty/hepatica-p/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Journal ingestion

```bash
cd /Users/praty/hepatica-p/backend
python3.11 scripts/ingest_journals.py
```

## Model training

```bash
cd /Users/praty/hepatica-p/ml
python3.11 -m pip install -r requirements.txt
python3.11 scripts/train.py
python3.11 scripts/evaluate.py
```

## Drift monitoring (weekly)

Run `/Users/praty/hepatica-p/ml/scripts/drift_monitor.py` as a weekly scheduled job.
