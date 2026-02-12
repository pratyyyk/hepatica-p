# Testing Guide

## Full stack preflight
```bash
cd /Users/praty/hepatica-p
./scripts/release_preflight.sh
```

## Backend tests
```bash
cd /Users/praty/hepatica-p/backend
python3 -m pytest -q
```

## Backend smoke checks
```bash
cd /Users/praty/hepatica-p/backend
python3 scripts/smoke_flow.py
python3 scripts/smoke_evidence.py
STAGE3_ENABLED=true python3 scripts/run_stage3_monitoring.py --dry-run
```

## Frontend quality gates
```bash
cd /Users/praty/hepatica-p/frontend
npm ci
npm run lint
npm run build
```

## Infra validation
```bash
cd /Users/praty/hepatica-p/infra
./scripts/validate.sh
```
