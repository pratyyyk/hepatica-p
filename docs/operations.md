# Operations

## Local Development

Recommended: `ENVIRONMENT=development` and `ENABLE_DEV_AUTH=true`.

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
- frontend lint/audit/build: correctness + supply chain checks
- infra validation: keeps Terraform from silently rotting

## Staging (Optional)

Terraform helpers:

```bash
make staging-plan
make staging-apply
```

Notes:
- Requires AWS credentials and Terraform available.
- `infra/` is considered optional/legacy for this repo; the prototype is designed to run without it.

