"""audit log

An append-only record of who did what to the books and when. See
docs/ledger-design.md. A trigger refuses any change to a row.

Revision ID: f7a2c8d41b63
Revises: e6f1b9c3a752
Create Date: 2026-10-29 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f7a2c8d41b63'
down_revision = 'e6f1b9c3a752'
branch_labels = None
depends_on = None

REFUSE_CHANGE = """
CREATE FUNCTION audit_refuse_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % is not allowed: the audit log is append-only',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$
"""

TRIGGERS = [
    """CREATE TRIGGER audit_log_append_only
       BEFORE UPDATE OR DELETE ON audit_log
       FOR EACH ROW EXECUTE FUNCTION audit_refuse_change()""",
    """CREATE TRIGGER audit_log_no_truncate
       BEFORE TRUNCATE ON audit_log
       FOR EACH STATEMENT EXECUTE FUNCTION audit_refuse_change()""",
]


def upgrade():
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=30), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("action ~ '^[a-z_]+[.][a-z_]+$'",
                           name='ck_audit_log_action'),
    )
    op.create_index('ix_audit_log_entity', 'audit_log',
                    ['organization_id', 'entity_type', 'entity_id'])
    op.create_index('ix_audit_log_org_time', 'audit_log',
                    ['organization_id', 'occurred_at'])
    op.execute(sa.text(REFUSE_CHANGE))
    for trigger in TRIGGERS:
        op.execute(sa.text(trigger))


def downgrade():
    # Dropping the table drops its triggers. The log is lost with it: that is
    # the one way to remove it.
    op.drop_table('audit_log')
    op.execute(sa.text('DROP FUNCTION audit_refuse_change()'))
