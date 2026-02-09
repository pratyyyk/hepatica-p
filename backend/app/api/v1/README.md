# backend/app/api/v1

Versioned API routers.

Files are grouped by domain:
- `auth.py`: login/session/logout
- `patients.py`: patient CRUD + list
- `assessments.py`: Stage 1 + Stage 2 orchestration
- `scans.py`: upload tickets + local upload endpoint
- `reports.py`: report generation + PDF streaming endpoint
- `knowledge.py`: knowledge blocks generation
- `timeline.py`: timeline read endpoint
- `models.py`: model registry + artifact health status

Reason: versioned routing makes it possible to evolve contracts without breaking existing clients.

