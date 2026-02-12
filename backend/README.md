# backend Folder Guide

## Purpose
FastAPI backend for auth, patient management, Stage 1/2/3 APIs, and report generation.

## Subfolders
| Folder | Role |
|---|---|
| `alembic` | Database migration framework setup for SQLAlchemy models. |
| `app` | Backend application entrypoint and modular domain packages. |
| `artifacts` | Nested module grouping related code. |
| `scripts` | Operational scripts for API export, synthetic data, smoke runs, and Stage 3 monitoring. |
| `tests` | Backend integration/unit/contract tests. |

## Files
| File | What it does |
|---|---|
| `.env.example` | Backend environment variable template. |
| `alembic.ini` | Alembic runtime configuration. |
| `Dockerfile` | Backend container build definition. |
| `Makefile` | Developer shortcuts for install/run/test/lint/smoke/stage3 monitor tasks. |
| `pyproject.toml` | Backend project metadata plus pytest/ruff settings. |
| `requirements.txt` | Pinned backend Python dependencies. |

## Quick Commands
- `make install`
- `make init-db`
- `make run`
- `make test`
