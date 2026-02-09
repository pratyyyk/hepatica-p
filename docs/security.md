# Security Model (Prototype)

This prototype includes production-minded guardrails even when running locally.

## Cookies + CSRF (Why)

- Backend issues an HTTP-only session cookie for authentication.
- Mutating requests require a CSRF token (cookie + header match).

Reason: cookie-based auth is vulnerable to CSRF by default. The explicit CSRF header requirement makes state-changing
requests harder to forge cross-site.

## Rate Limiting (Why)

SlowAPI provides per-route limits (auth, read, mutating).

Reason: prevents trivial abuse and gives a clear place to tune limits for staging/production.

## Upload Safety (Why)

Stage 2 pipeline enforces:
- allowlisted content types
- byte size limits
- antivirus hook point
- DICOM conversion with strict error handling
- image quality checks

Reason: image uploads are a common attack surface and also a source of low-quality clinical inputs.

## Local Upload Path Guard (Why)

The local upload endpoint refuses to write outside `backend/artifacts/uploads`.

Reason: prevents path traversal and accidental overwrites if a DB row is tampered with.

## Non-dev Guardrails

In non-development environments, model artifacts can be required (fail startup or inference if missing).

Reason: "silent fallbacks" are dangerous in production clinical systems; the prototype is strict by default.

