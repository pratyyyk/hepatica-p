# Operations

## Local Development

Recommended: `ENVIRONMENT=development` (dev login is enabled by default; set `ENABLE_DEV_AUTH=true` if you disabled it).

Key local-first behavior:
- `UPLOAD_MODE=auto` resolves to local uploads in development.
- Local uploads and report PDFs are stored under `backend/artifacts/` (ignored by git).

## Preflight

```bash
make preflight
```

What it runs and why:
- backend tests: regression safety
- backend smoke: ensures the happy-path API flow works
- stage3 monitoring dry-run: validates scheduled monitoring pipeline + alert dedupe path
- frontend lint/audit/build: correctness + supply chain checks
- infra validation: keeps Terraform from silently rotting

## Stage 3 Scheduled Monitoring

Stage 3 monitoring is scheduled-only.

Manual run:

```bash
cd backend
STAGE3_ENABLED=true python3 scripts/run_stage3_monitoring.py
```

Dry-run:

```bash
cd backend
STAGE3_ENABLED=true python3 scripts/run_stage3_monitoring.py --dry-run
```

Recommended cadence: every 10 weeks.

## Staging (Optional)

Terraform helpers:

```bash
make staging-plan
make staging-apply
```

Notes:
- Requires AWS credentials and Terraform available.
- `infra/` is considered optional/legacy for this repo; the prototype is designed to run without it.
