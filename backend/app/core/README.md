# backend/app/core

Cross-cutting policies and configuration.

Contents:
- `config.py`: typed Settings (env-driven) with local-first defaults.
- `security.py`: auth verification, session loading, role gating.
- `rate_limit.py`: SlowAPI limiter configuration.
- `startup_guardrails.py`: fail-fast checks for unsafe/misconfigured environments.
- `enums.py`: shared domain enums (risk tiers, stages, flags).

Why this is centralized:
- It avoids duplicating policy in multiple endpoints.
- It makes environment behavior explicit and testable (dev vs non-dev).

