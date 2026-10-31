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

## The posting service (PR 3)

`app/ledger.py` is the one way an entry gets into the journal. It checks the entry before the
database sees it, writes it in a savepoint (so a failure leaves nothing behind, not even a used
voucher number), and flushes without committing: the caller commits.

**Checks**, each refused with `LedgerError` (422) and a message that says which line is wrong:

- a description of 1 to 255 characters, and a date in 2000 to 2100 (anything else is a typing
  mistake that would open a fiscal year nobody wants);
- 2 to 500 lines, each with either a debit or a credit above 0 (never both, never neither, never
  negative), rounded half up to 2 decimals as in `money-rules.md` before they are added up. So
  `0.005 + 0.005` against a credit of `0.01` is refused: it rounds to `0.02`;
- the debits equal the credits;
- every account and contact belongs to the organization and the accounts are not archived. An
  account of another organization looks the same as one that does not exist.

**Fiscal year.** The open fiscal year that covers the date is used. If none covers it, the
**calendar year is opened automatically**, so nobody is blocked from posting on 1 January. It is not
opened if it would overlap an existing year (for example a year from July to June): that is a
conflict (409) and the user opens the right year. Posting in a **closed** year is a conflict (409).
Closing a year is a manual step (`POST /fiscal-years/<id>/close`); there is no reopening yet.

**Voucher numbers** come from the counter row, locked until the transaction ends: one running
sequence per organization, no gaps, no restarts. Checked with 8 simultaneous writers: 48 postings
got the numbers 1 to 48, and each calendar year was opened once.

**Reversal.** `reverse_entry` posts the same accounts with debit and credit swapped, dated today
(or on the entry's own date if that is later, so a reversal never comes before the entry it
cancels) unless told otherwise, with `source_type` `reversal` and `reverses_entry_id` set. An entry is
reversed once (409 the second time; the database refuses it too, so two simultaneous reversals
leave exactly one) and a reversal cannot be reversed: post a new entry instead. A reversal copies every line, VAT lines and VAT codes included, and
does not calculate the VAT again ([vat-design.md](vat-design.md), section 5).

**The database is still the last line of defence.** After the lines are written the service asks the
database to check the balance at once, so a bug in these checks would be raised and rolled back with
the entry, not at the commit.

**API.** All routes need a login and work on the user's own organization:

| Route | |
|---|---|
| `POST /journal-entries` | post a manual entry: `entry_date`, `description`, `lines` (`account_id`, `debit`, `credit`, `description`, `contact_id`) |
| `GET /journal-entries` | newest voucher first; `fiscal_year_id`, `limit` (at most 200), `offset` |
| `GET /journal-entries/<id>` | one entry with its lines |
| `POST /journal-entries/<id>/reverse` | optional body: `entry_date`, `description` |
| `GET /fiscal-years` | newest first |
| `POST /fiscal-years/<id>/close` | |

Amounts are JSON numbers (a string is refused). The voucher number, the user, the fiscal year and
the source cannot be set by the client: unknown fields are refused. An entry shows
`reversed_by_entry_id` when it has been reversed.

Not in PR 3: the audit log and the reports (account ledger, trial balance), and any screen in the
app.

## The audit log (PR 4)

The table `audit_log` is an append-only record of who did what to the books and when. A trigger
refuses any `UPDATE`, `DELETE` or `TRUNCATE` on it, as for the journal.

| Column | |
|---|---|
| `id` | bigint, in the order things happened |
| `organization_id`, `user_id` | whose books, and who did it |
| `occurred_at` | set by the database (`now()`, with time zone), never by the application |
| `action` | an entity, a dot and what happened: `journal_entry.posted` |
| `entity_type`, `entity_id` | what it happened to |
| `details` | JSON with the facts a reader needs: voucher number, date, totals |

`app/audit.py` has one function, `record`. It adds the row to the session and flushes: the row is
committed, or rolled back, **together with the change it describes**, so the log and the books can
never disagree. A refused or failed posting leaves no log row, not even for a fiscal year it opened.

**What is logged:**

| Action | When | Details |
|---|---|---|
| `journal_entry.posted` | every entry, including a reversal | voucher number, date, fiscal year, source, line count, debit total |
| `journal_entry.reversed` | on the original, when it is reversed | its voucher number, the reversal's id and voucher number |
| `fiscal_year.opened` | the first posting in a calendar year | start and end |
| `fiscal_year.closed` | when a year is closed | start and end |
| `account.created` | a new account | number, name, type, group |
| `account.updated` | an account is saved with a change | what changed, each as `{from, to}`: number, name, description, type, group, VAT rate, currency, the bank and payment flags, archived |

Accounts are logged because renaming or renumbering one changes how every old entry on it reads.
The log says only that the bank details changed, not what they were: they are personal data and the
journal does not need them. The entry description is not copied either: the entry itself is
unchangeable and can be looked up from the voucher number.

Every entry has a `journal_entry.posted` row: a test checks it with a query, so an entry that
bypassed the posting service shows up.

**API:** `GET /audit-log`, newest first, for the user's own organization. Filters: `entity_type`,
`entity_id`, `action`, and `limit` (at most 200) and `offset`.

**Not logged yet:** the starter chart created by `flask chart-apply` and `flask seed` (an operator
action with no user), logins, and invoices (they enter the ledger in phase 3). Nothing makes the log
tamper-evident against someone who owns the database; a hash chain over the rows would, and belongs
with the compliance work in phase 7.

## The reports (PR 5)

`app/reports.py` has the two reports every bookkeeping starts from. They read the journal and
nothing else, so they cannot disagree with it.

- **By the date of the entry** (`entry_date`), not the date it was posted, and over a plain range
  of dates: `from` and `to` are both included and both optional. A report does not care which
  fiscal year an entry is in, and closed years are included. The income statement accounts that
  start from zero each year are the year-end closing's business (phase 6), not the reports'.
- **Reversals are entries like any other**, so a reversed entry nets out: its account shows the
  entry and the reversal, ending at the same balance as before the entry.
- **A balance is debit minus credit**, a signed amount: a debit balance is positive, a credit
  balance negative. The account's `normal_balance` (`debit` or `credit`) comes with it, so a
  screen can show sales as a positive number.
- Amounts are JSON numbers with 2 decimals; the sums are made in the database on exact
  `NUMERIC`, never as floats.

**`GET /reports/account-ledger?account_id=&from=&to=`** lists every posting on one account in the
range, by date, then voucher number, then line, each with a running `balance`. The report has the
`opening_balance` carried in from before `from`, the `total_debit` and `total_credit` of the range,
and the `closing_balance`. The ledger of an account of another organization is a 404, as for an
unknown one.

**`GET /reports/trial-balance?from=&to=`** lists, for every account with a posting up to `to`, its
`opening_balance` (before `from`), what was `debit`ed and `credit`ed in the range, and the
`closing_balance`. An account that was posted to and reversed is listed with a zero balance;
accounts never posted to are not listed. Sorted by account number. The totals are zero (opening
and closing) or equal (debit and credit), because every entry balances, and `balanced` says so: if
it is ever `false`, something has bypassed the posting service and the database guards.

Unknown query fields and bad or reversed dates are refused with 422.

**Checked against a plain sum.** Besides the worked examples, a test posts 70 random balanced
entries over three years (some reversed) and, for six different date ranges, compares every figure
of both reports with a sum made in Python from the lines that were posted. Every ledger must end at
the trial balance's closing balance for the same account, and the trial balance must net to zero.

Not in PR 5: screens in the app, a balance sheet and income statement (phase 6), and paging of a
very long ledger: an account with many thousands of postings returns them all.
