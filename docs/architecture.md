# Architecture

## Components

- Frontend (`frontend/`): Next.js doctor console (App Router).
- Backend (`backend/`): FastAPI service (BFF-style auth, APIs, inference orchestration).
- ML (`ml/`): training/evaluation pipelines (Stage 1 tabular + Stage 2 images).
- Infra (`infra/`): Terraform for legacy AWS-based staging (optional).

## Data + Control Flow (Why this is structured this way)

### Authentication (BFF session cookies)

1) Frontend calls `POST /api/v1/auth/dev-login` (demo) or `POST /api/v1/auth/firebase-login` (optional).
2) Backend sets:
   - `hp_session` (HTTP-only session id cookie)
   - `hp_csrf` (readable CSRF token cookie)
3) Frontend uses `GET /api/v1/auth/session` to fetch `csrf_header_name` and includes it for mutating requests.

Reason: the browser keeps cookies; the frontend does not store access tokens. This reduces client-side auth complexity
and makes CSRF protection explicit.

### Patient -> Timeline (event log)

Mutating actions append a `timeline_events` row (e.g., patient created, Stage 1 completed, report generated).

Reason: the prototype needs a quick, auditable "what happened" history without building a full audit product.

### Stage 1 (Clinical)

- Always computes FIB-4 and APRI with a rule-based risk tier.
- If `STAGE1_ML_ENABLED=true`, it attempts to use ML artifacts (joblib models) to override tier/probability.

Reason: demos must work even before ML artifacts are produced; ML adds value when available.

### Stage 2 (Scan upload + inference)

Upload is intentionally split:
- `POST /api/v1/scans/upload-url` creates a ScanAsset and returns an upload target.
- Frontend performs `PUT` upload.
- `POST /api/v1/assessments/fibrosis` fetches the uploaded bytes, runs safety/quality checks, then predicts.

Reason: mirrors real systems (presigned uploads) while still supporting a purely local upload for demos.

### Reports

- `POST /api/v1/reports` builds a JSON payload, renders a PDF, stores it (S3 or local), and returns a URL.
- `GET /api/v1/reports/{id}/pdf` streams the PDF via backend so the browser always has a reachable URL.

Reason: in local mode, a file path like `/tmp/...pdf` is not browser-accessible; a backend endpoint is.

