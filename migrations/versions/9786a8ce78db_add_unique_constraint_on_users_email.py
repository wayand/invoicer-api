"""add unique constraint on users.email

Revision ID: 9786a8ce78db
Revises: ebd75be7d7ec
Create Date: 2026-10-01 23:28:28.367725

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '9786a8ce78db'
down_revision = 'ebd75be7d7ec'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_users_email', ['email'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_email', type_='unique')
