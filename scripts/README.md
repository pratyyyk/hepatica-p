# scripts

Repo-level helper scripts used by the root `Makefile`.

- `scripts/release_preflight.sh`: runs tests, smoke, frontend checks, infra validation, and optional Docker build.
- `scripts/staging_deploy.sh`: Terraform plan/apply helper.
- `scripts/release_dry_run_pack.sh`: release dry-run evidence bundling.

Reason: these scripts encode repeatable workflows and avoid hand-run “tribal knowledge” steps.

