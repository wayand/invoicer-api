"""session revocation: users.token_version, revoked token expiry and index

Revision ID: b7d2e41c9f08
Revises: 3f6c1b8e9a42
Create Date: 2026-10-10 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d2e41c9f08'
down_revision = '3f6c1b8e9a42'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'token_version', sa.Integer(), server_default='0', nullable=False
        ))

    # Rows without a jti can never match a token, and a repeated jti is the
    # same revoked token twice.
    op.execute("DELETE FROM revoked_tokens WHERE jti IS NULL")
    op.execute(
        "DELETE FROM revoked_tokens r USING revoked_tokens keep "
        "WHERE r.jti = keep.jti AND r.id > keep.id"
    )
    with op.batch_alter_table('revoked_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))
    # The longest a token can live is the refresh token lifetime, 30 days.
    op.execute(
        "UPDATE revoked_tokens SET expires_at = created_at + interval '30 days'"
    )
    with op.batch_alter_table('revoked_tokens', schema=None) as batch_op:
        batch_op.alter_column('expires_at', existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column('jti', existing_type=sa.String(length=120), nullable=False)
        batch_op.create_unique_constraint('revoked_tokens_jti_key', ['jti'])


def downgrade():
    with op.batch_alter_table('revoked_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('revoked_tokens_jti_key', type_='unique')
        batch_op.alter_column('jti', existing_type=sa.String(length=120), nullable=True)
        batch_op.drop_column('expires_at')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')
