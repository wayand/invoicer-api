"""An invoice is approved by posting it: number, voucher and lock

See docs/invoice-posting-design.md, sections 4 to 7.

- invoices.journal_entry_id, approved_at and approved_by: set together when the
  invoice is approved and posted. A check constraint keeps them together with
  the state and the number.
- The primary key of invoices is id. The number is a unique column that can be
  null: a draft in sequential mode has no number until it is approved, so a
  deleted draft cannot leave a gap in the series.
- invoices.is_paid is dropped: whether an invoice is paid follows from the
  payments (phase 3, later).
- Nothing is live: every invoice that is not a draft goes back to draft, so it
  can be approved and posted. The drafts of organizations with sequential
  numbering lose their number, which they get when they are approved.
  `is_sent` goes back to false with them.

Revision ID: e5b2d8c14f73
Revises: d3f9b5a28e41
Create Date: 2026-11-02 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b2d8c14f73'
down_revision = 'd3f9b5a28e41'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('journal_entry_id', sa.Integer(),
                                        nullable=True))
    op.add_column('invoices', sa.Column('approved_at', sa.DateTime(),
                                        nullable=True))
    op.add_column('invoices', sa.Column('approved_by', sa.Integer(),
                                        nullable=True))
    op.create_foreign_key('fk_invoices_journal_entry_id', 'invoices',
                          'journal_entries', ['journal_entry_id'], ['id'])
    op.create_foreign_key('fk_invoices_approved_by', 'invoices', 'users',
                          ['approved_by'], ['id'])
    op.create_unique_constraint('uq_invoices_journal_entry_id', 'invoices',
                                ['journal_entry_id'])

    # The primary key is id. The lines point at id, and their foreign key
    # depends on the unique constraint that id had, so it is made again.
    op.drop_constraint('invoice_lines_invoice_id_fkey', 'invoice_lines',
                       type_='foreignkey')
    op.drop_constraint('invoices_pkey', 'invoices', type_='primary')
    op.drop_constraint('invoices_id_key', 'invoices', type_='unique')
    op.create_primary_key('invoices_pkey', 'invoices', ['id'])
    op.create_foreign_key('invoice_lines_invoice_id_fkey', 'invoice_lines',
                          'invoices', ['invoice_id'], ['id'])
    op.alter_column('invoices', 'invoice_no', nullable=True)
    op.create_unique_constraint('uq_invoices_org_no', 'invoices',
                                ['organization_id', 'invoice_no'])

    op.execute("UPDATE invoices SET state = 'draft', is_sent = false "
               "WHERE state <> 'draft'")
    op.execute(
        "UPDATE invoices SET invoice_no = NULL WHERE organization_id IN "
        "(SELECT organization_id FROM invoice_settings "
        "WHERE invoice_no_mode = 'sequential')")
    op.drop_column('invoices', 'is_paid')

    op.create_check_constraint(
        'ck_invoices_state', 'invoices', "state IN ('draft', 'approved')")
    op.create_check_constraint(
        'ck_invoices_approved', 'invoices',
        "(state = 'approved') = (invoice_no IS NOT NULL "
        "AND journal_entry_id IS NOT NULL AND approved_at IS NOT NULL "
        "AND approved_by IS NOT NULL)")


def downgrade():
    op.drop_constraint('ck_invoices_approved', 'invoices', type_='check')
    op.drop_constraint('ck_invoices_state', 'invoices', type_='check')
    op.add_column('invoices', sa.Column('is_paid', sa.Boolean(),
                                        server_default=sa.text('false'),
                                        nullable=False))

    # An invoice with no number gets one that cannot be taken for a real one
    op.execute("UPDATE invoices SET invoice_no = 'draft-' || id "
               "WHERE invoice_no IS NULL")
    op.drop_constraint('uq_invoices_org_no', 'invoices', type_='unique')
    op.alter_column('invoices', 'invoice_no', nullable=False)
    op.drop_constraint('invoice_lines_invoice_id_fkey', 'invoice_lines',
                       type_='foreignkey')
    op.drop_constraint('invoices_pkey', 'invoices', type_='primary')
    op.create_unique_constraint('invoices_id_key', 'invoices', ['id'])
    op.create_primary_key('invoices_pkey', 'invoices',
                          ['organization_id', 'invoice_no'])
    op.create_foreign_key('invoice_lines_invoice_id_fkey', 'invoice_lines',
                          'invoices', ['invoice_id'], ['id'])

    op.drop_constraint('uq_invoices_journal_entry_id', 'invoices',
                       type_='unique')
    op.drop_constraint('fk_invoices_approved_by', 'invoices',
                       type_='foreignkey')
    op.drop_constraint('fk_invoices_journal_entry_id', 'invoices',
                       type_='foreignkey')
    op.drop_column('invoices', 'approved_by')
    op.drop_column('invoices', 'approved_at')
    op.drop_column('invoices', 'journal_entry_id')
