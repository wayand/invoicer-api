"""invoices.contact_id is required

The client-to-contact migration added the column as nullable and dropped
client_id without copying it over, so older invoices may still have no
contact. They have to be given one before the column can be NOT NULL.

Revision ID: 3f6c1b8e9a42
Revises: 0df479a3a681
Create Date: 2026-10-09 23:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f6c1b8e9a42'
down_revision = '0df479a3a681'
branch_labels = None
depends_on = None


def upgrade():
    missing = op.get_bind().execute(
        sa.text("SELECT count(*) FROM invoices WHERE contact_id IS NULL")
    ).scalar()
    if missing:
        raise RuntimeError(
            f"{missing} invoice(s) have no contact. Give each one a contact "
            "(UPDATE invoices SET contact_id = <id> WHERE contact_id IS NULL "
            "AND organization_id = <org>) and run the migration again."
        )
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.alter_column(
            'contact_id', existing_type=sa.Integer(), nullable=False
        )


def downgrade():
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.alter_column(
            'contact_id', existing_type=sa.Integer(), nullable=True
        )
