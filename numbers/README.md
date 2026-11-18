# Numbers committed by CI

Each file here is named for the day it was measured, in UTC, and was written and committed
by the [`numbers`](../.github/workflows/numbers.yml) workflow after a push to `main`. No
person types these figures. Each file names the commit it measured and the run that
measured it, so a reader can match the two; the run's log will expire, the file will not.

A later run on the same day replaces that day's file; git history keeps the earlier one.

Why this exists: [decision 0012](../docs/decisions/0012-ci-writes-down-its-own-numbers.md).
