# Frontend

Next.js 15 (App Router) in TypeScript, built as a static export. Tailwind with shadcn/ui
primitives and the newer kit in [`components/ui/v2`](./components/ui/v2/); TanStack Query
for server state; Zustand for the in-memory access token; openapi-fetch for API calls;
sonner for toasts; React Hook Form and Zod for forms. Tooling: pnpm, ESLint, Prettier,
Vitest and `tsc --noEmit`.

How the whole studio runs is in the top-level [`README.md`](../README.md). This file covers
the frontend only.

## Routes

Public:

- `/`: landing page
- `/login`, `/register`

Signed in (the `(protected)` route group):

- `/dashboard`: past drafts, with search, a type filter, Markdown download, and soft delete with undo
- `/generate`: draft a blog post, LinkedIn post, email or ad copy, and pair it with an image
- `/improve`: rewrite pasted text for a goal, shown beside the original with what changed
- `/brand-voices`: saved style presets that prefill new drafts
- `/settings`: the account's details, read-only

## Commands

```bash
cd frontend
pnpm install
pnpm dev           # http://localhost:3000
pnpm test          # Vitest
pnpm lint          # ESLint through next lint
pnpm format:check  # Prettier
pnpm typecheck     # tsc --noEmit
NEXT_OUTPUT=export pnpm build   # the static export, written to out/
```

The backend address is read at build time from `NEXT_PUBLIC_API_BASE_URL`, in
`.env.local` or the shell. It defaults to `http://localhost:8000/api/v1`.

## Auth

The access token lives only in memory (a Zustand store); the refresh token is an httpOnly
cookie set by the backend, `SameSite=Lax` unless the backend is configured otherwise. On a
401 the client in [`lib/api.ts`](./lib/api.ts) refreshes once through
`POST /auth/refresh` and replays the request; concurrent 401s in one tab share a single
refresh request. Two tabs refreshing at the same moment look like token reuse to the
backend, which then signs the user out everywhere. Logging out clears every cached query.

## API types

[`types/api.d.ts`](./types/api.d.ts) is written by hand, not generated. It types every
route the frontend calls through the client; the Markdown download uses a plain `fetch`.
`pnpm gen:api` would generate the file from a running backend's OpenAPI spec, but the
committed file did not come from it, and nothing checks that it matches the backend.

## Layout

```
frontend/
├── app/
│   ├── (auth)/            # login, register
│   ├── (protected)/       # dashboard, generate, improve, brand-voices, settings, behind useAuthGuard
│   ├── error.tsx, global-error.tsx, not-found.tsx
│   ├── layout.tsx, page.tsx, globals.css
├── components/
│   ├── features/          # the screens' building blocks
│   ├── ui/                # shadcn/ui primitives (button, input, label, modal)
│   ├── ui/v2/             # the newer kit; see its README for how far adoption has got
│   └── mobile-nav.tsx, sidebar.tsx, nav-links.tsx, mock-mode-banner.tsx, …
├── lib/
│   ├── api.ts             # openapi-fetch client with refresh-and-retry
│   ├── auth-store.ts      # the in-memory access token
│   ├── auth/, content/, brand-voices/, improver/, meta/   # TanStack Query hooks
│   ├── errors/ai-codes.ts # messages for the backend's AI error codes
│   └── validation/        # Zod schemas mirroring the backend's limits
├── types/api.d.ts
├── tests/                 # Vitest and Testing Library
└── next.config.ts         # NEXT_OUTPUT=export switches to the static export
```

## Tests

Component and hook tests in [`tests/`](./tests/) mock the API at the module level. There
are no end-to-end browser tests.
