# Frontend — Next.js 15 (App Router)

TypeScript, Tailwind v3, shadcn/ui, TanStack Query for server state, Zustand for the in-memory access token, openapi-fetch for the typed API client, sonner for toasts, React Hook Form + Zod for forms. Tooling: pnpm, ESLint, Prettier, Vitest, `tsc --noEmit`.

> Top-level repo docs (architecture, deployment, API surface): [`../README.md`](../README.md). This file covers frontend-specific commands and conventions only.

## Routes

Public:

- `/` — landing
- `/login`, `/register` — JWT auth pages (httpOnly refresh cookie + in-memory access token)

Protected (gated by the `(protected)` route group):

- `/dashboard` — paginated list of generated content with search, type filter, soft-delete + undo, and a detail dialog
- `/generate` — content generation form (blog post / LinkedIn post / email / ad copy) with staged loader
- `/improve` — analyze → rewrite chain with side-by-side diff and "what changed" rationale
- `/brand-voices` — CRUD for style presets that inject into generation prompts
- `/settings` — read-only account details

## Local commands

```bash
cd frontend
pnpm install
pnpm dev           # next dev → http://localhost:3000
pnpm build         # production build (Next.js)
pnpm test          # vitest run
pnpm lint          # next lint
pnpm format        # prettier --write .
pnpm format:check  # prettier --check . (CI gate)
pnpm typecheck     # tsc --noEmit
```

For static-export builds (used for manual Amplify zip deploys until the GitHub→Amplify OAuth path is wired):

```bash
NEXT_OUTPUT=export \
NEXT_PUBLIC_API_BASE_URL=https://<api-url>/api/v1 \
pnpm build
# Output lands in ./out/ — zip its contents (POSIX paths!) and PUT to Amplify.
```

The repo root [`README.md`](../README.md) §10 has the full deploy recipe.

## Environment

```bash
# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1   # default
```

In production, Amplify environment configuration sets `NEXT_PUBLIC_API_BASE_URL` to the App Runner URL.

## Auth model

In-memory access token (Zustand store) + httpOnly `SameSite=None` refresh cookie set by the backend. The 401 interceptor in [`lib/api.ts`](./lib/api.ts) transparently refreshes via `POST /auth/refresh` and replays the original request once; concurrent 401s share a single inflight refresh promise. On logout, `queryClient.clear()` drops every cached query so a second user on the same browser doesn't see the first user's data.

## Layout

```
frontend/
├── app/
│   ├── (auth)/                # public auth routes
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (protected)/           # routes gated by useAuthGuard
│   │   ├── dashboard/page.tsx
│   │   ├── generate/page.tsx
│   │   ├── improve/page.tsx
│   │   ├── brand-voices/page.tsx
│   │   └── settings/page.tsx
│   ├── layout.tsx             # root layout with <Providers>
│   ├── page.tsx               # landing
│   └── globals.css            # Tailwind base + theme variables
├── components/
│   ├── features/              # business UI (one folder-level deeper would be overkill)
│   ├── ui/                    # shadcn primitives (button, input, label, modal)
│   └── providers.tsx          # TanStack Query + sonner Toaster
├── lib/
│   ├── api.ts                 # openapi-fetch wrapper + auth middleware
│   ├── auth-store.ts          # Zustand: in-memory access token
│   ├── auth/                  # hooks: useLoginMutation, useLogoutMutation, useMe, useAuthGuard
│   ├── content/hooks.ts       # content list / detail / generate / delete / restore mutations
│   ├── brand-voices/hooks.ts  # brand-voice CRUD mutations
│   ├── improve/hooks.ts       # analyze→rewrite mutation
│   ├── validation/            # Zod schemas mirrored from backend
│   └── utils.ts               # cn() helper
├── types/api.d.ts             # OpenAPI-generated types (regenerate via `pnpm gen:api`)
├── tests/                     # Vitest + Testing Library
├── amplify.yml                # Amplify build spec
├── next.config.ts             # NEXT_OUTPUT=export toggle for static deploys
└── tailwind.config.ts
```

## Testing

Unit + component tests live in [`tests/`](./tests). They mock the API hooks at the module level and exercise components in isolation. Run with `pnpm test`; CI runs the same. Playwright E2E is on the backlog ([#86](https://github.com/Eslam93/MagnaCMS/issues/86)) but not wired yet.
