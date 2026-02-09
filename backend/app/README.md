# backend/app

This package contains the FastAPI application.

Structure (what goes where, and why):
- `api/`: HTTP endpoints (thin; validate + delegate to services).
- `core/`: settings, rate limiting, security guardrails (centralized policy).
- `db/`: SQLAlchemy engine/session/models/migrations integration.
- `schemas/`: Pydantic request/response models (contracts).
- `services/`: business logic (inference, uploads, reports, knowledge).
- `utils/`: small shared helpers.

Reason: keeping I/O at the edges (`api/`) and logic in `services/` keeps endpoints testable and reduces coupling.

