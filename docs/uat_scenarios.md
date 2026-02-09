# UAT Scenarios (10)

1. Doctor login with valid Firebase account; dashboard loads.
2. Create new patient with valid de-identified payload.
3. Stage 1 with low-risk inputs returns `LOW` and persists timeline event.
4. Stage 1 with high-risk inputs returns `HIGH` and escalates probability boost when BMI>=30 and T2DM=true.
5. Upload URL request rejects unsupported file MIME.
6. Stage 2 rejects poor-quality scan with explicit reason codes.
7. Stage 2 accepts valid scan, returns `F0-F4` softmax and flags.
8. Knowledge endpoint returns 5 blocks each with citations.
9. Report generation returns downloadable PDF with disclaimer + model versions.
10. Timeline endpoint shows ordered events across patient creation, assessments, and report generation.
