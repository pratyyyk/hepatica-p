# Frontend (Next.js Doctor Console)

## Purpose

Interactive doctor dashboard for:
- login (demo doctors)
- patient management + timeline
- Stage 1 assessment
- Stage 2 scan upload + inference
- knowledge generation
- report generation + PDF viewing

Reason: the UI is intentionally BFF-backed; it never stores access tokens and relies on backend cookies + CSRF.

## Routes (App Router)

- `/login`: demo doctor sign-in
- `/patients`: list + create, set active patient
- `/patients/[id]`: details + timeline
- `/assessments/stage1`: run Stage 1
- `/assessments/stage2`: upload scan, run Stage 2, generate knowledge/report
- `/reports`: generate report for a patient

## Environment

`frontend/.env.local`:
- `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`)
- `NEXT_PUBLIC_ENABLE_DEV_AUTH=true` (for demo login UI)

## Upload Behavior (Why it works locally)

Stage 2 uploads use the `upload_url` returned by the backend:
- If it points to the backend (local mode), the frontend includes cookies + CSRF header.
- If it is a presigned S3 URL, the frontend uploads without cookies and without CSRF.

## Run

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

