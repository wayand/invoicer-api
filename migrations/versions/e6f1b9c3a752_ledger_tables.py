"""ledger tables: company form, a stable account key, fiscal years and journal

See docs/ledger-design.md.

- organizations.company_form
- accounts: id becomes the primary key (a rename used to change the key), the
  name and number are unique per organization, and the account gets
  standard_account and system_role
- new tables fiscal_years, ledger_counters, journal_entries, journal_lines
- triggers: a posted entry is append-only, and every entry balances

Revision ID: e6f1b9c3a752
Revises: d5e8a3b71c24
Create Date: 2026-10-26 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f1b9c3a752'
down_revision = 'd5e8a3b71c24'
branch_labels = None
depends_on = None

# The same list as SYSTEM_ROLES in app/models/account.py. It is repeated here
# because a migration must not change when the application code does.
SYSTEM_ROLES = (
    'receivables', 'payables', 'sales', 'sales_eu_goods', 'sales_eu_services',
    'sales_non_eu_goods', 'sales_non_eu_services', 'purchases', 'output_vat',
    'input_vat', 'vat_eu_goods', 'vat_eu_services', 'vat_payable',
    'vat_receivable', 'tax_account', 'bank', 'rounding', 'owner_capital',
    'owner_withdrawals', 'owner_deposits', 'annual_result', 'share_capital',
    'retained_earnings',
)

# The foreign keys that point at accounts.id: table, column, constraint name
ACCOUNT_FOREIGN_KEYS = [
    ('invoice_settings', 'default_account_id',
     'invoice_settings_default_account_id_fkey'),
    ('invoice_settings', 'default_deposit_account_id',
     'invoice_settings_default_deposit_account_id_fkey'),
    ('products', 'account_id', 'products_account_id_fkey'),
]

REFUSE_CHANGE = """
CREATE FUNCTION ledger_refuse_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        '% on % is not allowed: posted entries are append-only, post a reversal instead',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$
"""

CHECK_LINE_INSERT = """
CREATE FUNCTION ledger_check_line_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    entry_txid bigint;
BEGIN
    SELECT created_txid INTO entry_txid
    FROM journal_entries WHERE id = NEW.journal_entry_id;
    IF entry_txid IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION
            'line % cannot be added to journal entry %: it was posted in an earlier transaction',
            NEW.line_no, NEW.journal_entry_id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$
"""

CHECK_BALANCED = """
CREATE FUNCTION ledger_check_balanced() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    entry_id integer;
    line_count integer;
    debit_total numeric;
    credit_total numeric;
BEGIN
    IF TG_TABLE_NAME = 'journal_entries' THEN
        entry_id = NEW.id;
    ELSE
        entry_id = NEW.journal_entry_id;
    END IF;
    SELECT count(*), coalesce(sum(debit), 0), coalesce(sum(credit), 0)
    INTO line_count, debit_total, credit_total
    FROM journal_lines WHERE journal_entry_id = entry_id;
    IF line_count < 2 THEN
        RAISE EXCEPTION
            'journal entry % has % line(s): at least 2 are required',
            entry_id, line_count
            USING ERRCODE = 'check_violation';
    END IF;
    IF debit_total <> credit_total THEN
        RAISE EXCEPTION
            'journal entry % is not balanced: debit %, credit %',
            entry_id, debit_total, credit_total
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$
"""

TRIGGERS = [
    """CREATE TRIGGER journal_entries_append_only
       BEFORE UPDATE OR DELETE ON journal_entries
       FOR EACH ROW EXECUTE FUNCTION ledger_refuse_change()""",
    """CREATE TRIGGER journal_lines_append_only
       BEFORE UPDATE OR DELETE ON journal_lines
       FOR EACH ROW EXECUTE FUNCTION ledger_refuse_change()""",
    """CREATE TRIGGER journal_entries_no_truncate
       BEFORE TRUNCATE ON journal_entries
       FOR EACH STATEMENT EXECUTE FUNCTION ledger_refuse_change()""",
    """CREATE TRIGGER journal_lines_no_truncate
       BEFORE TRUNCATE ON journal_lines
       FOR EACH STATEMENT EXECUTE FUNCTION ledger_refuse_change()""",
    """CREATE TRIGGER journal_lines_same_transaction
       BEFORE INSERT ON journal_lines
       FOR EACH ROW EXECUTE FUNCTION ledger_check_line_insert()""",
    """CREATE CONSTRAINT TRIGGER journal_entries_balanced
       AFTER INSERT ON journal_entries
       DEFERRABLE INITIALLY DEFERRED
       FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced()""",
    """CREATE CONSTRAINT TRIGGER journal_lines_balanced
       AFTER INSERT ON journal_lines
       DEFERRABLE INITIALLY DEFERRED
       FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced()""",
]


def drop_account_foreign_keys():
    for table, _column, name in ACCOUNT_FOREIGN_KEYS:
        op.drop_constraint(name, table, type_='foreignkey')


def create_account_foreign_keys():
    for table, column, name in ACCOUNT_FOREIGN_KEYS:
        op.create_foreign_key(name, table, 'accounts', [column], ['id'])


def upgrade():
    # organizations.company_form
    op.add_column('organizations', sa.Column(
        'company_form', sa.String(length=30),
        server_default='enkeltmandsvirksomhed', nullable=False))
    op.create_check_constraint(
        'ck_organizations_company_form', 'organizations',
        "company_form IN ('enkeltmandsvirksomhed', 'aps')")

    # accounts: id becomes the primary key. The foreign keys depend on the
    # unique constraint on id, which the primary key replaces.
    drop_account_foreign_keys()
    op.drop_constraint('accounts_pkey', 'accounts', type_='primary')
    op.drop_constraint('accounts_id_key', 'accounts', type_='unique')
    op.create_primary_key('accounts_pkey', 'accounts', ['id'])
    create_account_foreign_keys()
    op.create_unique_constraint(
        'uq_accounts_org_number', 'accounts', ['organization_id', 'number'])
    op.create_unique_constraint(
        'uq_accounts_org_name', 'accounts', ['organization_id', 'name'])
    op.create_unique_constraint(
        'uq_accounts_id_org', 'accounts', ['id', 'organization_id'])
    op.add_column('accounts', sa.Column(
        'standard_account', sa.Integer(), nullable=True))
    op.add_column('accounts', sa.Column(
        'system_role', sa.String(length=40), nullable=True))
    op.create_index(
        'uq_accounts_org_system_role', 'accounts',
        ['organization_id', 'system_role'], unique=True,
        postgresql_where=sa.text('system_role IS NOT NULL'))
    roles = ', '.join(f"'{role}'" for role in SYSTEM_ROLES)
    op.create_check_constraint(
        'ck_accounts_system_role', 'accounts', f'system_role IN ({roles})')

    # fiscal_years
    op.create_table(
        'fiscal_years',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=10), server_default='open',
                  nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'start_date',
                            name='uq_fiscal_years_org_start'),
        sa.UniqueConstraint('id', 'organization_id',
                            name='uq_fiscal_years_id_org'),
        sa.CheckConstraint('end_date >= start_date',
                           name='ck_fiscal_years_dates'),
        sa.CheckConstraint("status IN ('open', 'closed')",
                           name='ck_fiscal_years_status'),
    )

    # ledger_counters
    op.create_table(
        'ledger_counters',
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('next_voucher_no', sa.Integer(), server_default='1',
                  nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('organization_id'),
    )

    # journal_entries
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('voucher_no', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=30),
                  server_default='manual', nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('reverses_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_txid', sa.BigInteger(),
                  server_default=sa.text('txid_current()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(
            ['fiscal_year_id', 'organization_id'],
            ['fiscal_years.id', 'fiscal_years.organization_id'],
            name='fk_journal_entries_fiscal_year_org'),
        sa.ForeignKeyConstraint(['reverses_entry_id'],
                                ['journal_entries.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reverses_entry_id'),
        sa.UniqueConstraint('organization_id', 'voucher_no',
                            name='uq_journal_entries_voucher'),
        sa.UniqueConstraint('id', 'organization_id',
                            name='uq_journal_entries_id_org'),
        sa.CheckConstraint('voucher_no >= 1', name='ck_journal_entries_no'),
        sa.CheckConstraint('reverses_entry_id IS NULL OR reverses_entry_id <> id',
                           name='ck_journal_entries_reverses_other'),
    )
    op.create_index('ix_journal_entries_org_date', 'journal_entries',
                    ['organization_id', 'entry_date'])

    # journal_lines
    op.create_table(
        'journal_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('debit', sa.Numeric(precision=14, scale=2),
                  server_default='0', nullable=False),
        sa.Column('credit', sa.Numeric(precision=14, scale=2),
                  server_default='0', nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('contact_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(
            ['journal_entry_id', 'organization_id'],
            ['journal_entries.id', 'journal_entries.organization_id'],
            name='fk_journal_lines_entry_org'),
        sa.ForeignKeyConstraint(
            ['account_id', 'organization_id'],
            ['accounts.id', 'accounts.organization_id'],
            name='fk_journal_lines_account_org'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('journal_entry_id', 'line_no',
                            name='uq_journal_lines_no'),
        sa.CheckConstraint('line_no >= 1', name='ck_journal_lines_no'),
        sa.CheckConstraint(
            '(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)',
            name='ck_journal_lines_one_side'),
    )
    op.create_index('ix_journal_lines_account', 'journal_lines',
                    ['account_id'])

    # The guards
    op.execute(sa.text(REFUSE_CHANGE))
    op.execute(sa.text(CHECK_LINE_INSERT))
    op.execute(sa.text(CHECK_BALANCED))
    for trigger in TRIGGERS:
        op.execute(sa.text(trigger))


def downgrade():
    # Dropping the tables drops their triggers. The ledger is lost with them:
    # that is the one way to remove posted entries.
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_table('ledger_counters')
    op.drop_table('fiscal_years')
    op.execute(sa.text('DROP FUNCTION ledger_check_balanced()'))
    op.execute(sa.text('DROP FUNCTION ledger_check_line_insert()'))
    op.execute(sa.text('DROP FUNCTION ledger_refuse_change()'))

    op.drop_constraint('ck_accounts_system_role', 'accounts', type_='check')
    op.drop_index('uq_accounts_org_system_role', table_name='accounts')
    op.drop_column('accounts', 'system_role')
    op.drop_column('accounts', 'standard_account')
    op.drop_constraint('uq_accounts_id_org', 'accounts', type_='unique')
    op.drop_constraint('uq_accounts_org_name', 'accounts', type_='unique')
    op.drop_constraint('uq_accounts_org_number', 'accounts', type_='unique')
    drop_account_foreign_keys()
    op.drop_constraint('accounts_pkey', 'accounts', type_='primary')
    op.create_unique_constraint('accounts_id_key', 'accounts', ['id'])
    op.create_primary_key(
        'accounts_pkey', 'accounts', ['organization_id', 'name', 'number'])
    create_account_foreign_keys()

    op.drop_constraint('ck_organizations_company_form', 'organizations',
                       type_='check')
    op.drop_column('organizations', 'company_form')
