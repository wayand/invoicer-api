"""two-factor: email code state, totp replay guard, backup codes

Revision ID: 0df479a3a681
Revises: 9786a8ce78db
Create Date: 2026-10-08 22:03:27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0df479a3a681'
down_revision = '9786a8ce78db'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_otp_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('email_otp_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('email_otp_attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('totp_last_used_step', sa.BigInteger(), nullable=True))
        batch_op.alter_column('otp_secret',
               existing_type=sa.String(length=16),
               type_=sa.String(length=32),
               existing_nullable=False)
        batch_op.alter_column('otp_secret_temp',
               existing_type=sa.String(length=16),
               type_=sa.String(length=32),
               existing_nullable=False)

    op.create_table('backup_codes',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'code_hash', name='uq_backup_codes_user_hash')
    )
    with op.batch_alter_table('backup_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backup_codes_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('backup_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backup_codes_user_id'))
    op.drop_table('backup_codes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('otp_secret_temp',
               existing_type=sa.String(length=32),
               type_=sa.String(length=16),
               existing_nullable=False)
        batch_op.alter_column('otp_secret',
               existing_type=sa.String(length=32),
               type_=sa.String(length=16),
               existing_nullable=False)
        batch_op.drop_column('totp_last_used_step')
        batch_op.drop_column('email_otp_attempts')
        batch_op.drop_column('email_otp_expires_at')
        batch_op.drop_column('email_otp_hash')
