# 0007. The frontend ships as a static export, and CI builds what ships

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#156](https://github.com/Eslam93/FigureMatch/pull/156)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

The frontend was deployed in May as a static export (`NEXT_OUTPUT=export`), but CI built
the default server build, so the thing that shipped was never built in CI. Next.js 15.1.3
was in the version range of the React2Shell vulnerability (CVE-2025-66478 and
CVE-2025-55182), which affects anyone running `next start` or server rendering. The
frontend Sentry setup never loaded: the config was never wrapped with
`withSentryConfig`, and its server hooks cannot run in a static export.

## Decision

- CI builds the static export and fails if `out/index.html` or `out/404.html` is missing.
- Next.js and `eslint-config-next` move to 15.5.29, pinned exactly.
- CI runs on Node 22; Node 20 reached end of life in April 2026.
- The frontend Sentry packages and config were removed. The backend keeps Sentry.

The same pull request added mobile navigation, a 404 page and error boundaries, the
typography plugin the Markdown views had always assumed, and a banner in mock mode.

## Alternatives

None is recorded in the pull request.

## Consequences

- Anything that needs a server, such as middleware or server rendering, cannot be used
  without changing how the frontend ships.
- The frontend reports no errors anywhere. Its error pages log to the browser console.
