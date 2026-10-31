"""Invoice lines carry a VAT code, and the tax rates are gone

See docs/vat-design.md, section 7.

- invoice_lines.vat_code_id: required. Lines that exist get S01 (25% VAT), the
  rate every invoice was calculated with so far; their amounts are not
  changed, and a line is recalculated only when its invoice is saved again.
- accounts.tax_rate_id and the tax_rates table are removed: the VAT codes
  replace them. The downgrade brings the empty table and column back.

Revision ID: c2e8a4d67b19
Revises: b9d4f6a31c58
Create Date: 2026-11-01 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2e8a4d67b19'
down_revision = 'b9d4f6a31c58'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'invoice_lines', sa.Column('vat_code_id', sa.Integer(), nullable=True)
    )
    op.execute(
        "UPDATE invoice_lines SET vat_code_id = "
        "(SELECT id FROM vat_codes WHERE code = 'S01')"
    )
    op.alter_column('invoice_lines', 'vat_code_id', nullable=False)
    op.create_foreign_key(
        'fk_invoice_lines_vat_code_id',
        'invoice_lines',
        'vat_codes',
        ['vat_code_id'],
        ['id'],
    )

    op.drop_column('accounts', 'tax_rate_id')
    op.drop_table('tax_rates')
    op.execute('DROP SEQUENCE IF EXISTS tax_rates_id_seq')


def downgrade():
    tax_rates_seq = sa.Sequence('tax_rates_id_seq')
    op.execute(sa.schema.CreateSequence(tax_rates_seq))
    op.create_table(
        'tax_rates',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), tax_rates_seq,
                  server_default=tax_rates_seq.next_value(),
                  autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('abbreviation', sa.String(length=10), nullable=False),
        sa.Column('applies_to_purchases', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False),
        sa.Column('applies_to_sales', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False),
        sa.Column('description', sa.String(length=200), server_default='',
                  nullable=True),
        sa.Column('is_active', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False),
        sa.Column('is_predefined', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False),
        sa.Column('net_amount_meta_field_id', sa.Integer(), nullable=True),
        sa.Column('predefined_tag', sa.String(length=100),
                  server_default='', nullable=False),
        sa.Column('rate', sa.Numeric(6, 4), server_default='0',
                  nullable=False),
        sa.Column('tax_rate_group', sa.String(length=100),
                  server_default='danish', nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('organization_id', 'name', 'abbreviation'),
        sa.UniqueConstraint('id'),
    )
    op.add_column(
        'accounts', sa.Column('tax_rate_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'accounts_tax_rate_id_fkey', 'accounts', 'tax_rates',
        ['tax_rate_id'], ['id'],
    )

    op.drop_constraint(
        'fk_invoice_lines_vat_code_id', 'invoice_lines', type_='foreignkey'
    )
    op.drop_column('invoice_lines', 'vat_code_id')
