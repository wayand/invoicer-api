"""store user emails lowercase

Addresses were compared exactly, so Test@Example.com and test@example.com
were two different (and one unusable) logins. They are now stored lowercase
and the database enforces it.

Revision ID: c4a9f1d27e63
Revises: b7d2e41c9f08
Create Date: 2026-10-15 22:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a9f1d27e63'
down_revision = 'b7d2e41c9f08'
branch_labels = None
depends_on = None


def upgrade():
    clashes = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM ("
        "  SELECT 1 FROM users GROUP BY lower(btrim(email)) HAVING count(*) > 1"
        ") AS clashing"
    )).scalar()
    if clashes:
        raise RuntimeError(
            f"{clashes} email address(es) exist more than once when case is "
            "ignored. Merge or delete the duplicate users first. Find them "
            "with: SELECT lower(btrim(email)), count(*) FROM users "
            "GROUP BY 1 HAVING count(*) > 1"
        )
    op.execute(
        "UPDATE users SET email = lower(btrim(email)) "
        "WHERE email <> lower(btrim(email))"
    )
    op.create_check_constraint(
        'ck_users_email_lowercase', 'users', 'email = lower(email)'
    )


def downgrade():
    op.drop_constraint('ck_users_email_lowercase', 'users', type_='check')
