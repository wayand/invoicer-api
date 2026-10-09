---
name: check
description: Run the same steps as the CI pipeline (install, ruff lint, ruff format check, pytest) in order and report pass/fail. Use before saying work is done, before committing, or when asked to verify.
allowed-tools: Bash(uv sync *), Bash(uv run ruff *), Bash(uv run pytest *)
---

# Check

Mirror `.github/workflows/deploy.yml` (jobs `lint` and `test`). Run in this order and keep going after a failure so the report is complete:

1. `uv sync --frozen`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run pytest -vs`

Do not auto-fix with `ruff format .` or `ruff check --fix` unless asked. Report the problem and offer to fix it.

If step 1 fails, stop: the later steps are meaningless.

Tests need Postgres through `TEST_DATABASE_URL` and `TEST_DB_NAME` (from the git-ignored `.env`, never read it). If tests fail on connection, say so rather than guessing.

## Report

One line per step, `PASS` or `FAIL`, then for each failure the first relevant error and the file:line. End with an overall verdict. Don't claim success if a step was skipped or failed.
