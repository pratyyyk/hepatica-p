.PHONY: install run test lint init-db ingest-journals smoke smoke-evidence stage3-monitor

install:
	python3 -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

init-db:
	python -m app.db.init_db

ingest-journals:
	python scripts/ingest_journals.py

test:
	pytest

lint:
	ruff check app tests

smoke:
	python3 scripts/smoke_flow.py

smoke-evidence:
	python3 scripts/smoke_evidence.py

stage3-monitor:
	python3 scripts/run_stage3_monitoring.py
