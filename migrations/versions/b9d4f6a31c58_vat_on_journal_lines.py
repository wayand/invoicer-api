"""VAT on journal lines: the VAT code of a line and what the line is

See docs/vat-design.md.

- journal_lines.vat_code_id and vat_part: both or neither. A line is the net
  amount a code applies to (base), the VAT the engine added (vat), or the part
  of the VAT that cannot be deducted (nondeductible).

The append-only triggers on journal_lines fire on UPDATE, DELETE and TRUNCATE,
not on ALTER TABLE, and the existing lines get null in both columns.

Revision ID: b9d4f6a31c58
Revises: a8c3e5d92f17
Create Date: 2026-11-01 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9d4f6a31c58'
down_revision = 'a8c3e5d92f17'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('journal_lines',
                  sa.Column('vat_code_id', sa.Integer(), nullable=True))
    op.add_column('journal_lines',
                  sa.Column('vat_part', sa.String(length=15), nullable=True))
    op.create_foreign_key('fk_journal_lines_vat_code_id', 'journal_lines',
                          'vat_codes', ['vat_code_id'], ['id'])
    op.create_check_constraint(
        'ck_journal_lines_vat', 'journal_lines',
        '(vat_code_id IS NULL) = (vat_part IS NULL)')
    op.create_check_constraint(
        'ck_journal_lines_vat_part', 'journal_lines',
        "vat_part IS NULL OR vat_part IN ('base', 'vat', 'nondeductible')")


def downgrade():
    op.drop_constraint('ck_journal_lines_vat_part', 'journal_lines',
                       type_='check')
    op.drop_constraint('ck_journal_lines_vat', 'journal_lines', type_='check')
    op.drop_constraint('fk_journal_lines_vat_code_id', 'journal_lines',
                       type_='foreignkey')
    op.drop_column('journal_lines', 'vat_part')
    op.drop_column('journal_lines', 'vat_code_id')
