# backend/alembic

Alembic migrations for the backend database schema.

Key files:
- `alembic.ini`: migration configuration (DB URL is supplied via environment).
- `env.py`: Alembic runtime (imports SQLAlchemy metadata).
- `versions/`: generated migration scripts.

Why migrations exist in a prototype:
- Keeping schema changes explicit prevents "works on my machine" drift.
- It enables staging/production-like workflows even while iterating quickly.

Common commands:

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

