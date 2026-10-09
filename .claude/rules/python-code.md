---
paths:
  - "**/*.py"
---

# Python code

## Do
- Catch specific exceptions and handle or re-raise them.
- Read configuration from environment variables via `config.py`, and document new ones in `.env.sample`.
- Build paths with `pathlib` or from config (e.g. `UPLOAD_FOLDER`).
- Use SQLAlchemy bound parameters and ORM queries.
- Use the `logging` module for diagnostics.
- Keep formatting at ruff's settings (80 columns, double quotes, sorted imports).

## Don't
- Don't write bare `except:` or silent `except Exception: pass`.
- Don't hardcode secrets, tokens, passwords or absolute paths. Test fixtures may use obvious dummy values.
- Don't leave `print()` calls, debug code or commented-out code behind.
- Don't use `eval`, `exec`, `subprocess(..., shell=True)` or `os.system`.
- Don't build SQL with f-strings, `%` or `.format()`, including in raw `text()` queries.
- Don't return data for an organization other than the caller's.
