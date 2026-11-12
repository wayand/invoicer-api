"""Credit notes: an invoice of its own kind that corrects an invoice

See docs/invoice-posting-design.md, section 8.

- invoices.kind: invoice or credit_note. Every invoice that exists is an
  invoice.
- invoices.credits_invoice_id: the invoice a credit note corrects. The
  database keeps the two together: a credit note has one, an invoice does not,
  and nothing corrects itself.

Revision ID: f6c3e9d25a84
Revises: e5b2d8c14f73
Create Date: 2026-11-02 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6c3e9d25a84'
down_revision = 'e5b2d8c14f73'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('kind', sa.String(length=20),
                                        server_default='invoice',
                                        nullable=False))
    op.add_column('invoices', sa.Column('credits_invoice_id', sa.Integer(),
                                        nullable=True))
    op.create_foreign_key('fk_invoices_credits_invoice_id', 'invoices',
                          'invoices', ['credits_invoice_id'], ['id'])
    op.create_index('ix_invoices_credits_invoice_id', 'invoices',
                    ['credits_invoice_id'])
    op.create_check_constraint(
        'ck_invoices_kind', 'invoices', "kind IN ('invoice', 'credit_note')")
    op.create_check_constraint(
        'ck_invoices_credits', 'invoices',
        "(kind = 'credit_note') = (credits_invoice_id IS NOT NULL) "
        "AND (credits_invoice_id IS NULL OR credits_invoice_id <> id)")


def downgrade():
    # A credit note cannot exist without its kind: they go with the column
    op.execute("DELETE FROM invoice_lines WHERE invoice_id IN "
               "(SELECT id FROM invoices WHERE kind = 'credit_note')")
    op.drop_constraint('ck_invoices_credits', 'invoices', type_='check')
    op.drop_constraint('ck_invoices_kind', 'invoices', type_='check')
    op.execute("DELETE FROM invoices WHERE kind = 'credit_note'")
    op.drop_index('ix_invoices_credits_invoice_id', table_name='invoices')
    op.drop_constraint('fk_invoices_credits_invoice_id', 'invoices',
                       type_='foreignkey')
    op.drop_column('invoices', 'credits_invoice_id')
    op.drop_column('invoices', 'kind')
