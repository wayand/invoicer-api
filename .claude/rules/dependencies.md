---
paths:
  - "pyproject.toml"
  - "uv.lock"
  - ".python-version"
---

# Dependencies

## Do
- Change dependencies only with `uv add`, `uv add --dev`, `uv remove` (these ask for approval).
- Commit `pyproject.toml` and `uv.lock` together.
- Keep each dependency change in its own focused commit.
- Keep the Python version in sync across `.python-version`, `requires-python`, the `Dockerfile` and CI.

## Don't
- Don't use `pip install`, `pip freeze` or `requirements.txt`.
- Don't edit `uv.lock` by hand.
- Don't upgrade packages that the task doesn't need.
- Don't add `[tool.ruff]` to `pyproject.toml`. Ruff config lives in `ruff.toml`.
- Don't add a second test config: pytest config stays in the existing `pytest.ini`, not also in `pyproject.toml`.
