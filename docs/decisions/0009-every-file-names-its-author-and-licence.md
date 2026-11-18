# 0009. Every file states its author and licence, checked in CI

- **Status:** Accepted
- **Decided:** 2026-11-18, commit `25f077d`
- **Written:** 2026-11-18

## Context

The repository had an MIT licence, but no file said who wrote it or under what terms,
and nothing stopped a file landing without either. Some files were not written by the
owner at all: the shadcn/ui components, Alembic's templates, lock files and generated
snapshots.

## Decision

- Every file the owner wrote opens with `SPDX-FileCopyrightText` and
  `SPDX-License-Identifier` lines, the [REUSE](https://reuse.software) convention.
- Files that came from elsewhere keep their real authors, with the owner added only
  where he changed them. Output of tools, such as lock files and Jest snapshots, names no
  one and is marked CC0.
- Markdown and JSON take no header. [`REUSE.toml`](../../REUSE.toml) covers them, because
  an HTML comment would hide the notice on the rendered page, and nothing here is hidden.
- `reuse lint` runs in CI on every push to `main` and working branches and on every pull
  request.

## Alternatives

None is recorded in the commit.

## Consequences

- A new file without its two lines, or a `REUSE.toml` entry, fails CI.
- Work written with an AI coding agent carries the owner's name in its headers, and the
  agent is named in the commit's `Co-Authored-By` trailer.
