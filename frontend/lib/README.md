# frontend/lib

Frontend client utilities.

- `api.ts`: backend fetch wrapper + upload helper (handles CSRF/cookies for backend uploads)
- `session.tsx`: session bootstrap + login/logout helpers
- `activePatient.ts`: persistent active patient selection (localStorage)

Reason: centralizing fetch/session logic avoids duplicating security-sensitive behaviors across pages.

