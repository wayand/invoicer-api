# Invoicer API

Flask + PostgreSQL backend for invoicer.wayand.dk (users, organizations, contacts, invoices, products, tax rates). JWT auth with 2FA, per-organization data isolation. The Vue frontend lives in the separate `invoicer-vue` repo.

## Commands

Always run Python through `uv`, never `pip` or bare `python`.

```bash
uv sync                      # install (CI uses `uv sync --frozen`)
uv run ruff check .          # lint
uv run ruff format .         # format (CI runs `--check`)
uv run pytest                # tests (CI runs `-vs`; needs Postgres via TEST_DATABASE_URL)
uv run flask db upgrade      # apply migrations
uv run flask run             # dev server
```

## Layout

- `app/` application package: `models/` (SQLAlchemy models + marshmallow schemas), `routes/` (blueprints, `authz.py` org scoping), `seed/`, `templates/` (emails), `cli.py`, `email.py`, `ratelimit.py`
- `config.py` env-driven config classes; `run.py` entry point; `boot.sh` + `Dockerfile` for the container
- `migrations/` Alembic (excluded from ruff)
- `tests/unit/`, `tests/functional/` (HTTP tests against a real Postgres), `tests/conftest.py`
- `ruff.toml` (lint/format), `pytest.ini`, `.env.sample` (documents every env var)

## Working rules

- Run `/check` before saying a task is done, and report what failed.
- Code changes come with tests. Bug fixes get a regression test.
- Every tenant-scoped route must enforce organization isolation (see `app/routes/authz.py`).
- Keep changes focused. No drive-by refactors or unrelated upgrades.
- Don't touch shared config (`ruff.toml`, `pytest.ini`, `pyproject.toml`, `.github/`, `Dockerfile`, `.claude/`) unless asked.
- New env vars go in `config.py` and `.env.sample`.
- Never read `.env`. Use `.env.sample`.
- Branches come off an up-to-date `master`. Ask before committing or pushing; see `.claude/rules/git-and-security.md`.

## Personal overrides

`CLAUDE.local.md` and `.claude/settings.local.json` are git-ignored.
