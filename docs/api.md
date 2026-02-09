# API (Human Reference)

Base prefix: `/api/v1`

## Auth

- `POST /auth/dev-login` (development only; requires `ENABLE_DEV_AUTH=true`)
  - Body: `{ "email": "doctor@example.com" }`
  - Sets cookies: `hp_session`, `hp_csrf`

- `POST /auth/firebase-login` (optional; requires Firebase env configured)
  - Body: `{ "email": "user@example.com", "password": "..." }`

- `GET /auth/session`
  - Returns: `{ authenticated, user_id, email, role, csrf_token, csrf_header_name }`

- `POST /auth/logout`

## Patients

- `GET /patients?limit=20&offset=0`
  - Returns only patients created by the authenticated doctor.
  - Reason: multi-tenant safety and a simple UX for “my patients”.

- `POST /patients`
  - Body: `{ external_id, sex?, age?, bmi?, type2dm?, notes? }`

- `GET /patients/{patient_id}`

- `GET /patients/{patient_id}/timeline`

## Stage 1 (Clinical)

- `POST /assessments/clinical`
  - Body: `{ patient_id, ast, alt, platelets, ast_uln, age, bmi, type2dm }`

## Scan Upload

- `POST /scans/upload-url`
  - Body: `{ patient_id, filename, content_type, byte_size }`
  - Returns:
    - `scan_asset_id`
    - `upload_url` (either presigned S3 URL or backend local upload endpoint)

- `PUT /scans/upload/{scan_asset_id}` (local upload mode)
  - Body: raw bytes
  - Headers: `Content-Type`, `x-csrf-token`

## Stage 2 (Fibrosis)

- `POST /assessments/fibrosis`
  - Body: `{ patient_id, scan_asset_id }`
  - Backend runs:
    - AV hook
    - DICOM conversion (if needed)
    - quality gates
    - ML inference (model artifact or dev fallback)

## Knowledge + Reports

- `POST /knowledge/explain`
  - Body: `{ patient_id, fibrosis_stage?, top_k? }`

- `POST /reports`
  - Body: `{ patient_id, clinical_assessment_id?, fibrosis_prediction_id? }`
  - Returns `pdf_download_url` pointing to `/reports/{report_id}/pdf`

- `GET /reports/{report_id}`
- `GET /reports/{report_id}/pdf`

## Models

- `GET /models/status`
  - Returns registry + artifact health checks for Stage 1 and Stage 2.

