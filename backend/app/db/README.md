# backend/app/db

Database layer (SQLAlchemy).

Key files:
- `models.py`: ORM models for patients, assessments, scans, predictions, knowledge, reports, timeline, audit logs.
- `session.py`: engine/session creation (SQLite by default; Postgres optional).
- `init_db.py`: seeds default model registry rows for convenience.

Reason: the prototype uses a relational model because it matches "patient-centric" workflows and is easy to reason about.

