# backend/tests

Test suite for backend APIs and services.

Categories:
- API contract tests: happy path + auth/ownership + CSRF
- Local upload + PDF tests: ensures the prototype demo works with no cloud dependencies
- Model registry tests: activate/deactivate semantics
- Synthetic dataset tests: validates schema, bounds, and reproducibility

Run:

```bash
cd backend
pytest
```

