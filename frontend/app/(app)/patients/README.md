# frontend/app/(app)/patients

Patient management.

Routes:
- `/patients`: list + create + set active patient (stored in localStorage).
- `/patients/[id]`: patient details + timeline viewer.

Why "active patient":
- It reduces repetitive copy/paste across the workflow (assessments, reports).

