# Numbers committed by CI

CI's measurements are kept on the [`numbers`](https://github.com/Eslam93/FigureMatch/tree/numbers)
branch, one file per day it measured, in UTC. After each push to `main` that changes
code, the [`numbers`](../.github/workflows/numbers.yml) workflow runs every check that
produces a number, writes the results, and commits the file to that branch itself, as
`github-actions[bot]`. No person types these figures. Each file names the commit it
measured and the run that measured it; the run's log will expire, the file will not.

They live on a branch of their own because `main` takes changes only through pull
requests, and its protection refuses a push from CI. A later run on the same day replaces
that day's file; the branch's history keeps the earlier one.

Why this exists: [decision 0012](../docs/decisions/0012-ci-writes-down-its-own-numbers.md).
