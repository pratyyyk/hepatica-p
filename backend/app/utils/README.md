# backend/app/utils

Reserved for small shared helpers that do not naturally belong in `services/` or `core/`.

Why this is separate:
- Avoids turning `services/` into a dumping ground.
- Keeps domain logic and cross-cutting policy separate.

This folder is intentionally light in the prototype; add utilities only when they are reused in multiple places.

