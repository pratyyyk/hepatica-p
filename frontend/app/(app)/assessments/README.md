# frontend/app/(app)/assessments

Assessment workflows (doctor-facing).

Routes:
- `stage1/`: clinical risk triage form + result viewer.
- `stage2/`: upload scan + run fibrosis inference + generate knowledge/report.

Why split Stage 1 and Stage 2:
- Stage 1 is fast and tabular; Stage 2 is file-based and has safety/quality gating.
- Separating pages keeps interactions focused and improves demo clarity.

