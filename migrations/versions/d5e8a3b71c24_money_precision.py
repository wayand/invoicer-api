"""money columns get a fixed precision, and excluding_vat goes

Amounts become NUMERIC(14,2), quantities and unit prices NUMERIC(14,3), the
VAT rate NUMERIC(6,4). The server now computes the invoice totals (see
docs/money-rules.md), so the columns are narrowed to what that rule produces.
Existing values are rounded to the new scale (half up, as the rule does).

invoices.excluding_vat was never used by anything and is dropped.

Revision ID: d5e8a3b71c24
Revises: c4a9f1d27e63
Create Date: 2026-10-25 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e8a3b71c24'
down_revision = 'c4a9f1d27e63'
branch_labels = None
depends_on = None

# table, column, new (precision, scale), old type
COLUMNS = [
    ('invoices', 'amount', (14, 2), sa.Numeric(10, 3)),
    ('invoices', 'vat_amount', (14, 2), sa.Numeric(10, 3)),
    ('invoices', 'gross_amount', (14, 2), sa.Numeric(10, 3)),
    ('invoice_lines', 'amount', (14, 2), sa.Numeric(10, 3)),
    ('invoice_lines', 'quantity', (14, 3), sa.Numeric(10, 3)),
    ('invoice_lines', 'unit_price', (14, 3), sa.Numeric(10, 3)),
    ('products', 'unit_price', (14, 3), sa.Numeric(10, 3)),
    ('invoice_settings', 'default_reminder_fee', (14, 2), sa.Numeric()),
    ('tax_rates', 'rate', (6, 4), sa.Numeric()),
]


def upgrade():
    for table, column, (precision, scale), _old in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Numeric(precision, scale),
            existing_nullable=False,
            postgresql_using=f'{column}::numeric({precision},{scale})',
        )
    op.drop_column('invoices', 'excluding_vat')


def downgrade():
    op.add_column(
        'invoices',
        sa.Column(
            'excluding_vat',
            sa.Boolean(),
            server_default=sa.text('true'),
            nullable=False,
        ),
    )
    for table, column, _new, old in reversed(COLUMNS):
        op.alter_column(
            table,
            column,
            type_=old,
            existing_nullable=False,
        )
