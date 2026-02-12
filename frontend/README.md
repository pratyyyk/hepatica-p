# frontend Folder Guide

## Purpose
Next.js frontend for login, patient workflows, assessments, monitoring, and reporting.

## Subfolders
| Folder | Role |
|---|---|
| `app` | App Router structure, global layout, and cross-page providers/styles. |
| `components` | Reusable UI components and shell/navigation primitives. |
| `lib` | Frontend API client, session state, and active patient helpers. |

## Files
| File | What it does |
|---|---|
| `.env.local.example` | Frontend env template for API/auth settings. |
| `.eslintignore` | ESLint exclusion list. |
| `.eslintrc.json` | ESLint rules for frontend TypeScript/React. |
| `next-env.d.ts` | Next.js ambient type declarations. |
| `next.config.mjs` | Next.js runtime configuration. |
| `package-lock.json` | Locked npm dependency graph for reproducible installs. |
| `package.json` | Frontend scripts and dependency manifest. |
| `tsconfig.json` | TypeScript compiler options. |

## Quick Commands
- `npm ci`
- `npm run dev`
- `npm run lint`
- `npm run build`
