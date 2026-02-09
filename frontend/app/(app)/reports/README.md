# frontend/app/(app)/reports

Report generation UI.

Uses:
- `POST /api/v1/reports` to create a report.
- `pdf_download_url` returned by backend points to `/api/v1/reports/{id}/pdf`, which streams bytes and is always browser-openable.

Why a backend PDF endpoint:
- S3 presigned URLs and local filesystem paths are not interchangeable; the backend hides that complexity.

