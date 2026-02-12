# backend/app Folder Guide

## Purpose
Backend application entrypoint and modular domain packages.

## Subfolders
| Folder | Role |
|---|---|
| `api` | API dependency helpers and auth-scoped request context. |
| `core` | Core runtime configuration, enums, security, and startup guardrails. |
| `db` | ORM models, DB session wiring, and database initialization. |
| `schemas` | Pydantic request/response contracts for all API payloads. |
| `services` | Business logic for scoring, inference, monitoring, upload, audit, and PDF rendering. |
| `utils` | Nested module grouping related code. |

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `main.py` | Application bootstrap and server lifecycle entrypoint. |
