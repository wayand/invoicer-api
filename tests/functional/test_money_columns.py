"""
Money columns have a fixed precision (docs/money-rules.md). The models are
what the application uses, the migrations are what the database gets: this
checks that the database really has the types the rules call for.
"""

import pytest
from sqlalchemy import inspect

from app.models.base import db

# table, column, precision, scale
MONEY_COLUMNS = [
    ("invoices", "amount", 14, 2),
    ("invoices", "vat_amount", 14, 2),
    ("invoices", "gross_amount", 14, 2),
    ("invoice_lines", "amount", 14, 2),
    ("invoice_lines", "quantity", 14, 3),
    ("invoice_lines", "unit_price", 14, 3),
    ("products", "unit_price", 14, 3),
    ("invoice_settings", "default_reminder_fee", 14, 2),
    ("tax_rates", "rate", 6, 4),
]


def column(table, name):
    columns = inspect(db.engine).get_columns(table)
    return next(item for item in columns if item["name"] == name)


@pytest.mark.parametrize(("table", "name", "precision", "scale"), MONEY_COLUMNS)
def test_money_column_has_a_fixed_precision(app, table, name, precision, scale):
    found = column(table, name)["type"]

    assert (found.precision, found.scale) == (precision, scale)


def test_excluding_vat_is_gone(app):
    names = [
        item["name"] for item in inspect(db.engine).get_columns("invoices")
    ]

    assert "excluding_vat" not in names
