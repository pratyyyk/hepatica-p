# frontend/app Folder Guide

## Purpose
App Router structure, global layout, and cross-page providers/styles.

## Subfolders
| Folder | Role |
|---|---|
| `(app)` | Authenticated clinician workspace shell and routed pages. |
| `(auth)` | Authentication route group. |

## Files
| File | What it does |
|---|---|
| `globals.css` | Global/style definitions for frontend visual system. |
| `layout.tsx` | Next.js layout wrapper for nested routes. |
| `page.tsx` | Next.js route page component for this folder path. |
| `providers.tsx` | React context/provider composition for app-wide state. |
