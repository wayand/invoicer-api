"""
The app must be creatable in a fresh interpreter, whatever was imported
before it. Importing `app.models` has to register every model; otherwise
SQLAlchemy cannot resolve relationship targets (e.g. Invoice.lines ->
"InvoiceLine") when the marshmallow schemas are built during create_app.

These run in subprocesses on purpose: inside pytest, other modules have
already imported every model and would hide the problem.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_create_app_works_in_a_fresh_interpreter():
    result = run_python(
        "from app import create_app\n"
        "from config import TestingConfig\n"
        "create_app(TestingConfig)\n"
    )

    assert result.returncode == 0, result.stderr[-2000:]


def test_importing_the_model_package_registers_every_model():
    result = run_python(
        "import importlib, pkgutil\n"
        "import app.models as models\n"
        "from app.models.base import db\n"
        "registered = set(db.metadata.tables)\n"
        "for module in pkgutil.iter_modules(models.__path__):\n"
        "    if not module.name.endswith('_schema'):\n"
        "        importlib.import_module(f'app.models.{module.name}')\n"
        "print(sorted(set(db.metadata.tables) - registered))\n"
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]", (
        "tables only registered by importing their module directly: "
        + result.stdout.strip()
    )
