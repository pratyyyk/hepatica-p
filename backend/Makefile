.PHONY: install run test lint init-db ingest-journals smoke

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
