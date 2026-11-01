"""VAT periods: the periods that have been settled

See docs/vat-design.md, section 8. One row for each settled period: its
dates, the due date, the voucher of the settlement, and, once the return has
been filed in TastSelv Erhverv, when and by whom. The figures are not stored:
they come from the ledger.

Revision ID: d3f9b5a28e41
Revises: c2e8a4d67b19
Create Date: 2026-11-02 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f9b5a28e41'
down_revision = 'c2e8a4d67b19'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vat_periods',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('period_type', sa.String(length=10), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=10), server_default='settled',
                  nullable=False),
        sa.Column('settlement_entry_id', sa.Integer(), nullable=True),
        sa.Column('settled_at', sa.DateTime(), nullable=False),
        sa.Column('settled_by', sa.Integer(), nullable=False),
        sa.Column('filed_on', sa.Date(), nullable=True),
        sa.Column('filed_by', sa.Integer(), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['settlement_entry_id'],
                                ['journal_entries.id']),
        sa.ForeignKeyConstraint(['settled_by'], ['users.id']),
        sa.ForeignKeyConstraint(['filed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'start_date',
                            name='uq_vat_periods_org_start'),
        sa.CheckConstraint('end_date >= start_date',
                           name='ck_vat_periods_dates'),
        sa.CheckConstraint(
            "period_type IN ('half_year', 'quarter', 'month')",
            name='ck_vat_periods_type'),
        sa.CheckConstraint("status IN ('settled', 'filed')",
                           name='ck_vat_periods_status'),
        sa.CheckConstraint(
            "(status = 'filed') = "
            "(filed_on IS NOT NULL AND filed_by IS NOT NULL)",
            name='ck_vat_periods_filed'),
    )
    op.create_index('ix_vat_periods_org_end', 'vat_periods',
                    ['organization_id', 'end_date'])


def downgrade():
    op.drop_index('ix_vat_periods_org_end', table_name='vat_periods')
    op.drop_table('vat_periods')
