# Ledger tables (design for phase 1, PR 1)

The design for the first code PR of phase 1 of the [accounting plan](accounting-plan.md): the data
the ledger stands on. It uses the account numbers and roles from the
[chart of accounts](chart-of-accounts.md) and the money rules in [money-rules.md](money-rules.md).
This page is for approval before any migration is written.

## Scope of PR 1

In:

1. The two official files from Erhvervsstyrelsen in the repo, with a loader and tests.
2. `organizations.company_form`.
3. `accounts`: a stable key and the new `standard_account` and `system_role` columns.
4. New tables `fiscal_years`, `ledger_counters`, `journal_entries` and `journal_lines`, with
   database guards that keep every entry balanced and every posting unchangeable.

Not in PR 1 (each is its own PR, in this order):

- The seed of the starter chart and a command to apply it to an organization (PR 2).
- The posting service: voucher numbers, balance and fiscal year checks, reversals (PR 3).
- The audit log and the ledger reports, in the API and the app (PR 4 and 5).
- VAT codes on lines and a `vat_codes` table (phase 2).

Nothing in the app changes in PR 1. The tables are empty until PR 3.

## 1. The official files

`app/seed/standard/` gets `2026-01-01-Standardkontoplan.json` and `2026-01-01-Momskoder-Bruttoliste.json`
(unchanged copies) and a `SOURCE.md` with where they came from, the download date and the SHA-256 of
each. `app/standard_chart.py` reads them: the accounts by number (name, kind, group) and the VAT
codes. Tests check the hashes (so a file cannot change by accident), the counts (603 accounts,
72 VAT codes), and a few known accounts such as 6190 and 7680.

When Erhvervsstyrelsen publishes a new version, the new file is added next to the old one and a
migration decides what changes for existing organizations. Nothing is overwritten.

## 2. `organizations.company_form`

A text column, `enkeltmandsvirksomhed` or `aps`, not null, with a check constraint. It defaults to
`enkeltmandsvirksomhed`, as that is what the first organizations are. It decides the equity accounts
the seed creates (PR 2) and how the year is closed (phase 6).

## 3. `accounts`

Today the primary key is `(organization_id, name, number)`, with a separate unique `id`. Renaming an
account changes its key, and the account update route does change the name and number. Journal lines
must be able to point at an account that is later renamed, so:

- `id` becomes the primary key.
- New unique constraints: `(organization_id, number)` and `(organization_id, name)`. The second
  keeps what the old key and the create route's duplicate check already enforce.
- The foreign keys that point at `accounts.id` (`invoice_settings` has two) are dropped and
  recreated around the key change. The migration is checked on a scratch database in both
  directions, as for the money columns.
- `standard_account` (integer, nullable): the number of the standard account this account stands
  for. Not a foreign key, since the standard is a file. For accounts that use the standard's own
  number it equals `number`.
- `system_role` (text, nullable): the role the posting service looks up (`receivables`, `bank`,
  ...). A unique index on `(organization_id, system_role)` where it is not null, so a role has one
  account. The roles are a fixed list in code, with a check constraint in the database.
- The account API does **not** return the new fields yet. The app's account form sends the whole
  account back when it saves, and the API refuses fields it does not know, so exposing them would
  break editing an account until the form is changed. They are exposed in PR 2, together with the
  seed and that change in the app.
- `account_types` and `account_groups` keep their current shape and keys. They have the same
  name-in-the-key problem, but nothing points at them by anything other than `id`, so it can wait.

## 4. `fiscal_years`

| Column | Notes |
|---|---|
| `id` | primary key |
| `organization_id` | foreign key |
| `start_date`, `end_date` | `end_date` on or after `start_date`; unique `(organization_id, start_date)` |
| `status` | `open` or `closed` |
| `created_at`, `updated_at` | as the other tables |

Fiscal years of one organization must not overlap. A database constraint for that needs an extension
(`btree_gist`), so the posting service checks it inside a transaction instead, with a test. Closing a
year only sets `status`: it does not delete or change anything else.

## 5. `journal_entries` (a voucher)

| Column | Notes |
|---|---|
| `id` | primary key |
| `organization_id`, `fiscal_year_id` | foreign keys |
| `voucher_no` | integer; unique `(organization_id, voucher_no)` |
| `entry_date` | the date the entry is for (must be inside the fiscal year: checked in PR 3) |
| fiscal year | foreign key `(fiscal_year_id, organization_id)` to `fiscal_years`, so the year is the organization's own |
| `description` | text |
| `source_type`, `source_id` | what produced it: `manual`, later `invoice`, `payment`, `vat_settlement` |
| `reverses_entry_id` | nullable foreign key to another entry; unique, so an entry is reversed once |
| `created_by` | foreign key to the user |
| `created_at` | no `updated_at`: an entry is never updated |
| `created_txid` | the PostgreSQL transaction that posted the entry (default `txid_current()`): see section 7 |

**Voucher numbers** are one running sequence per organization (1, 2, 3, ...), never restarting
and never with a gap. Danish bookkeeping law requires every booked transaction to have a unique,
sequential number ([KPMG's summary](https://assets.kpmg.com/content/dam/kpmg/dk/pdf/dk-2024/november/Seneste%20udvikling%20i%20den%20nye%20bogf%C3%B8ringslov%202024.pdf)
of the rules that apply from 2025). I could not find a source on whether the sequence may restart
each fiscal year, so a sequence that never restarts is the one that cannot be wrong. The voucher can
still be shown with its year. The number comes from a counter row:

`ledger_counters`: `organization_id` (primary key, foreign key) and `next_voucher_no` (integer,
starts at 1).

The posting service locks that row, takes the number and writes the entry in one transaction, so a
failed posting rolls the counter back and no number is lost.

## 6. `journal_lines`

| Column | Notes |
|---|---|
| `id` | primary key |
| `journal_entry_id` | foreign key |
| `organization_id` | foreign key. With the two keys below it makes a line unable to use an entry or an account of another organization |
| `line_no` | position in the entry; unique `(journal_entry_id, line_no)` |
| `account_id` | foreign key `(account_id, organization_id)` to `accounts`; an account that has lines cannot be deleted |
| `debit`, `credit` | `NUMERIC(14,2)`, both at least 0 |
| `description` | text, nullable |
| `contact_id` | nullable foreign key: the customer or supplier the line is for |

Checks: `debit` and `credit` are each at least 0, and exactly one of them is above 0. A line is one
side of an entry, never both and never empty. Amounts follow the money rules (2 decimals, half up
rounding is done before posting). All amounts are in DKK: foreign currency is not part of phase 1.

The VAT columns (VAT code and VAT amount per line) come in phase 2 with their own migration.

## 7. Guards in the database

Two rules protect the books, and they are enforced by PostgreSQL itself so no code path, script or
manual SQL session can break them by accident:

1. **Balanced.** A deferred constraint trigger on `journal_lines` and `journal_entries` checks, when
   the transaction commits, that every touched entry has at least two lines and that the debits
   equal the credits. A broken entry makes the commit fail.
2. **Append only.** Triggers refuse `UPDATE` and `DELETE` on `journal_entries` and `journal_lines`
   (and `TRUNCATE`). A line can only be inserted in the transaction that posted its entry
   (`created_txid`), so a posted entry cannot grow a balanced pair of extra lines later. A mistake is corrected with a reversal entry, which is a new entry that points
   at the old one and swaps debit and credit. This is the "postings cannot be changed or deleted"
   requirement of BEK 205/2024 in the plan.

The cost is on purpose: no SQL fix-ups of posted entries. The only way to remove them is to drop the
tables, which a migration downgrade does.

## Tests

- The loader and the file hashes and counts.
- The migration upgrades and downgrades on a scratch database that has old-style accounts (key swap,
  new columns, foreign keys intact).
- The account API shows the new fields and still creates, renames and renumbers accounts.
- Through raw SQL on the test database: a balanced entry commits; an unbalanced one, an entry with
  one line, a line with both debit and credit, a negative amount and a second reversal of the same
  entry are all refused; `UPDATE`, `DELETE` and `TRUNCATE` on posted entries and lines are refused;
  an account with lines cannot be deleted; two accounts cannot hold one role; two entries cannot
  share a voucher number.

## Decisions (approved 2026-10-25, except the voucher numbering, which changed)

1. **Database triggers** for balance and append-only (section 7): approved.
2. **Voucher numbers.** Proposed as restarting each fiscal year. Changed to one running sequence per
   organization, because I could not confirm that a yearly restart is allowed (section 5). To be
   confirmed by you.
3. **No overlap check in the database** for fiscal years (it needs the `btree_gist` extension).
4. **Existing organizations.** There is no production data: everything is in the test phase. The
   migration changes only the structure, and PR 2 reseeds the demo organizations with the starter
   chart instead of renumbering their old accounts.
5. **`account_types` and `account_groups` stay as they are** for now.
