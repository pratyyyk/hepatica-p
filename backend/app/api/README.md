# backend/app/api

API layer responsibilities:
- validate request payloads
- enforce auth and ownership checks
- call into services
- write audit + timeline events

Reason: the API layer should be boring; complex behavior belongs in `services/` so it can be tested without HTTP.

