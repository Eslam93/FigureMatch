# Decision records

One file per decision made since the May 2026 build. The May decisions are summarised in
[`ARCHITECTURE.md`](../../ARCHITECTURE.md).

**Every record here was written after the fact.** The November audit fixes were decided
and merged on 7 November 2026; their records were written on 18 November, from the pull
requests, the commits and the code, by an AI coding agent working in this repository for
its owner. Each record gives both dates. Where a pull request records no alternative that
was weighed, the record says so instead of inventing one.

| # | Decision | Decided | Written |
|---|---|---|---|
| [0001](./0001-one-dated-catalog-for-models-and-prices.md) | Model ids, prices and shutdown dates live in one dated catalog, checked at boot and weekly | 2026-11-07, [#154](https://github.com/Eslam93/FigureMatch/pull/154) | 2026-11-18 |
| [0002](./0002-commit-reuse-revocation-before-the-401.md) | Refresh-token reuse revocation is committed before the 401, and integration tests run the real session handling | 2026-11-07, [#155](https://github.com/Eslam93/FigureMatch/pull/155) | 2026-11-18 |
| [0003](./0003-validation-errors-echo-nothing-submitted.md) | A 422 says which field failed and why, never what was submitted | 2026-11-07, [#155](https://github.com/Eslam93/FigureMatch/pull/155) | 2026-11-18 |
| [0004](./0004-one-typed-family-of-provider-errors.md) | Model-provider failures are one typed family with fixed responses | 2026-11-07, [#155](https://github.com/Eslam93/FigureMatch/pull/155) | 2026-11-18 |
| [0005](./0005-corrective-retry-keeps-the-strict-schema.md) | The corrective retry keeps the strict schema and names the failing field | 2026-11-07, [#155](https://github.com/Eslam93/FigureMatch/pull/155) | 2026-11-18 |
| [0006](./0006-end-the-read-transaction-before-model-calls.md) | No database transaction stays open across a model call | 2026-11-07, [#155](https://github.com/Eslam93/FigureMatch/pull/155) | 2026-11-18 |
| [0007](./0007-the-frontend-ships-as-a-static-export.md) | The frontend ships as a static export, and CI builds what ships | 2026-11-07, [#156](https://github.com/Eslam93/FigureMatch/pull/156) | 2026-11-18 |
| [0008](./0008-the-name-came-before-the-product.md) | The project is named for a figure checker that is not built | 2026-11-07, [#157](https://github.com/Eslam93/FigureMatch/pull/157) | 2026-11-18 |
| [0009](./0009-every-file-names-its-author-and-licence.md) | Every file states its author and licence, checked in CI | 2026-11-18, `25f077d` | 2026-11-18 |
| [0010](./0010-measure-before-building-the-checker.md) | The checker is built only if a measurement fixed in advance says so | 2026-11-18, `f63b393` | 2026-11-18 |
| [0011](./0011-replay-the-audit-against-a-stand-in.md) | The audit is replayed against a stand-in for OpenAI, not the real API | 2026-11-18, `948fdce` | 2026-11-18 |
| [0012](./0012-ci-writes-down-its-own-numbers.md) | CI commits the numbers it measured, because its logs expire | 2026-11-18 | 2026-11-18 |

Also in #155, without a record of their own: unhandled 500s are rendered inside the
middleware stack, so they carry a request id and the security headers; the rendered
prompts are pinned by golden files; three prompts stopped asking the model for figures
the brief never gave; Docker Compose binds its ports to `127.0.0.1`; and `GET /meta`
reports the provider mode, so the frontend shows a banner in mock mode.
