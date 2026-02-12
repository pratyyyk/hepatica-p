# scripts Folder Guide

## Purpose
Repository-level release and deployment helper scripts.

## Files
| File | What it does |
|---|---|
| `release_dry_run_pack.sh` | Release artifact dry-run pack workflow. |
| `release_preflight.sh` | Cross-stack preflight: tests, smoke, Stage 3 dry-run, frontend build, infra validation. |
| `staging_deploy.sh` | Terraform staging plan/apply orchestrator with health checks. |
