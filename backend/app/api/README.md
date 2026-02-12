# backend/app/api Folder Guide

## Purpose
API dependency helpers and auth-scoped request context.

## Subfolders
| Folder | Role |
|---|---|
| `v1` | Versioned REST endpoints for auth, assessments, scans, reports, and Stage 3. |

## Files
| File | What it does |
|---|---|
| `__init__.py` | Package marker and module export surface. |
| `deps.py` | Python module implementing domain-specific logic for this folder. |
