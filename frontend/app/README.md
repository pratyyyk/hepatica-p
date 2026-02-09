# frontend/app

Next.js App Router pages and layouts.

Folders:
- `(auth)/`: authentication screens (login)
- `(app)/`: authenticated application shell (sidebar + pages)
- `layout.tsx`: root layout (wraps the app with providers)
- `providers.tsx`: client providers (session context)

Reason: route groups keep the login experience separate from the authenticated shell, which simplifies guard logic.

