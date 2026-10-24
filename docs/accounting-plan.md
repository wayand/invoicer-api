# Accounting plan: from invoicing to a Danish accounting system

Drafted 2026-10-24. This is a living document: update it as decisions are made and phases ship.

The goal is for Invoicer to work like a real Danish accounting system (like Dinero): double-entry
bookkeeping, VAT (moms) reporting, purchases, bank reconciliation and financial statements, with
every figure traceable to a posting.

## Assumptions (change these if they are wrong)

- **A hobby project, not live.** Nobody uses it yet, including its owner. It is for the owner's own
  businesses, and for learning how the money flow of a business works: assets, liabilities, equity,
  income, expenses and VAT. So there is no production data to protect: until the first real use,
  the schema, seed data and migrations can change freely.
- **Own businesses first, free for others later.** A self-built system used by the company itself falls
  under [BEK 205/2024](https://retsinformation.dk/eli/lta/2024/205/pdf): the company is responsible
  for compliance. Offering it to other companies is different: a digital *standard* bookkeeping
  system must be registered with Erhvervsstyrelsen before it is marketed in Denmark (see the
  [guidance for providers](https://erhvervsstyrelsen.dk/vejledning-vejledning-til-udbydere-af-digitale-standard-bogfoeringssystemer)).
  Whether a free offering counts, and what it requires, must be checked with Erhvervsstyrelsen
  before anyone else relies on it for their books. Until then, treat use by others as a trial, not
  as a product. The design below (immutable postings, audit trail, SAF-T, e-invoicing, backups) is
  needed either way.
- **No integrations for now.** No bank API and no direct filing to SKAT. Bank statements are
  imported as CSV files. For each VAT period the app shows the figures to enter by hand in
  TastSelv Erhverv: sales VAT (`salgsmoms`), input VAT (`købsmoms`), the A/B/C box values, the
  amount payable, and the deadline.
- **First milestone (M2): ledger, VAT report, and invoices with payments** (phases 0 to 3). Purchases
  and bank import come after.
- **No legal or tax advice.** Before relying on the VAT mapping and the chart of accounts, have an
  accountant check them.

## Where the code is today

What exists: invoices with a draft/approved state, contacts (with a `type`), products linked to a
revenue account, a chart of accounts (account types, groups, accounts), tax rates with a `danish`
group, and per-organization isolation.

What is missing, and everything else depends on it: **there is no ledger.** No journal, postings,
debit/credit, fiscal periods or audit trail. The annual report page is a placeholder.

Problems to fix before a ledger can be trusted (found in the code on 2026-10-19):

- The server trusts the amounts the browser sends: `amount`, `vat_amount` and `gross_amount` are
  stored as received, and the Vue form hardcodes 25% VAT.
- An approved invoice can still be edited freely through `PUT`, and `state`, `is_paid` and
  `is_sent` are set by the client. (Fixed in phase 3, when approving starts to post the invoice.)
- `update_invoice` has a bug: `invoice.template_id = data.get("is_sent", ...)`.
- Money is `Numeric(10,3)`. There is no VAT code per line, no payments table (only an `is_paid`
  flag), no credit notes, no supplier bills, and no user roles beyond `owner`.
- The seed chart is tiny (6 accounts, 2 tax rates) and has no receivables, payables, VAT settlement
  or equity accounts.

## Principles

1. **Double-entry first.** Every business event (invoice, payment, bill, VAT settlement) produces
   balanced postings, enforced in code and in the database.
2. **The server owns the money.** The client sends quantities, prices and VAT codes; the server
   computes every amount.
3. **Posted entries never change.** Corrections are reversing entries. The law requires this too.
4. **Every report is derived from postings**, so reports always agree with each other.
5. **Test the accounting invariants:** debits equal credits, the trial balance is zero, VAT settles
   to the penny, and reports tie out.

## Danish requirements that shape the design

Sources are linked; check the official text before relying on any of this.

- **Bookkeeping act (`bogføringsloven`).** Digital bookkeeping applies from 1 July 2024 for registered
  systems and from 1 January 2025 for non-registered ones, for companies and others that file annual
  reports. For sole proprietors and associations the sources disagree (1 Jan or 1 Jul 2026), so check
  the official rules. See the
  [Erhvervsstyrelsen guidance](https://erhvervsstyrelsen.dk/vejledning-vejledning-til-udbydere-af-digitale-standard-bogfoeringssystemer)
  and the [Dinero FAQ](https://dinero.dk/support/faq-den-nye-bogfoeringslov/).
- **What BEK 205/2024 requires, per summaries of it** (read the regulation text): booked entries
  can't be changed, backdated or deleted, and corrections are new postings; SAF-T export in the
  format Erhvervsstyrelsen defines; sending and receiving e-invoices and credit notes through
  Nemhandel in OIOUBL and Peppol BIS; automatic backup at least weekly; support for bank
  reconciliation.
- **VAT periods and deadlines** ([skat.dk](https://skat.dk/erhverv/moms/frister-indberet-og-betal-moms)):
  half-yearly under 5 mio. kr. turnover (once filed and paid on time); quarterly for new
  businesses, those who apply, and 5-50 mio. kr.; monthly above 50 mio. kr. Quarterly deadlines are
  1 June, 1 September, 1 December and 1 March; half-yearly are 1 September and 1 March; monthly is
  around the 25th of the next month. Late filing means a provisional assessment with a fee. EU sales
  lists are monthly (quarterly on application).
- **VAT codes** (Dinero's set, which matches the Danish return; see
  [their list](https://dinero.dk/support/hvilke-momskoder-har-vi-dinero/)):
  - Sales: `U25` (domestic), `UEUV` / `UEUY` (EU goods / services, box B), `UVV` / `UVY` (exports,
    box C).
  - Purchases: `I25` (domestic), `IEUV` / `IEUY` (EU goods / services, box A), `IVV` / `IVY`
    (non-EU).
  - Partial deduction: `REP` (25% deductible), `HREP` (75% deductible).
  - The exact current layout of the return boxes (A, B, C and the VAT lines) has changed over time:
    confirm it on skat.dk or in TastSelv Erhverv before building the report.
- **Filing to SKAT.** We do not file. The VAT report lists the figures for the period, and they are
  entered by hand in TastSelv Erhverv. (Dinero files through a "NemVirksomhed: access for accounting
  system provider" authorisation tied to its own CVR number, see
  [how it works](https://dinero.dk/support/adgang-til-indberetning-af-moms/). Direct filing from our
  software would probably require being registered with SKAT as a system provider, so it is a later
  idea, not a plan.)

## Roadmap

| # | Phase | What it delivers | Size |
|---|---|---|---|
| 0 | Decisions and groundwork | Money rules (2-decimal amounts, one rounding rule, server-side totals). `template_id` fixed. Chart of accounts proposed and checked with an accountant. | S |
| 1 | Ledger core | Fiscal years and periods, journal entries and lines, a posting service, gapless voucher numbers, reversal entries, an append-only audit log, a manual voucher. Reports: account ledger, trial balance, general ledger. | L |
| 2 | VAT engine | VAT codes with their return-box mapping, VAT per invoice line, server-side VAT, a VAT report for any period showing what to enter by hand in TastSelv (sales VAT, input VAT, boxes A/B/C, amount payable, deadline), VAT settlement posting, period locking after filing. | L |
| 3 | Sales on the ledger | Approving an invoice posts it (receivable, revenue, output VAT) and locks it: an approved invoice is read-only, and mistakes are corrected with a credit note. Payments, partial payments and allocation, replacing `is_paid`. Reminders. | L |
| 4 | Purchases and expenses | Suppliers, bills and vouchers with attachments (kept 5 years), input VAT including `REP`/`HREP`, reverse charge and foreign purchases, EU and non-EU codes. | L |
| 5 | Bank (CSV) | Bank accounts, import of bank statements as CSV (with a configurable column mapping, as banks differ), matching lines against invoices and bills, reconciliation. No bank API. | M |
| 6 | Statements and year-end | Income statement, balance sheet (assets, liabilities and equity), year-end closing to equity, accountant export. | M |
| 7 | Compliance hardening | SAF-T export, weekly automatic backup, user roles (bookkeeper, accountant read-only), e-invoicing (OIOUBL/Peppol), EU sales list. | L |
| 8 | Later | Bank API sync (PSD2), direct VAT filing, multi-currency, recurring invoices, quotes, payroll integration. | - |

### Milestones

- **M1 (end of phase 1):** manual postings with a balanced ledger and a trial balance.
- **M2 (end of phase 3):** approve an invoice, record the payment, and see everything in the ledger
  and in the VAT report for the quarter. The first real "accounting system" moment.
- **M3 (end of phase 5):** the purchase-side workflow, from supplier bill to bank statement match (CSV).
- **M4 (end of phase 6):** a full quarter or year closed.

## Data model sketch

- `fiscal_years` and `fiscal_periods`, with open, closed and VAT-filed states.
- `journal_entries` (voucher number, date, source type and id, `reversed_by`) and `journal_lines`
  (account, debit, credit, VAT code, VAT amount, contact). Debits equal credits per entry, enforced
  in the posting service and by a database constraint.
- `vat_codes`: extend or replace `tax_rates`, adding the return box, the deductible share, and
  whether the code applies to sales or purchases.
- Later: `payments`, `payment_allocations`, `bills`, `bill_lines`, `attachments`,
  `bank_transactions`, `audit_log` (append-only).
- Existing approved invoices get postings backfilled, plus an opening-balance entry.

## How events post (illustration)

Account names are placeholders; the real chart is chosen in phase 0.

| Event | Debit | Credit |
|---|---|---|
| Sale 1,000 + 25% VAT | Receivables 1,250 | Sales 1,000; Output VAT 250 |
| Customer pays | Bank 1,250 | Receivables 1,250 |
| Purchase 800 + 25% VAT | Expense 800; Input VAT 200 | Payables 1,000 |
| VAT settlement for a period | Output VAT 250 | Input VAT 200; VAT payable 50 |
| Pay the VAT | VAT payable 50 | Bank 50 |

In practice VAT is paid through the Skattekonto, so the account structure for it should be decided
with an accountant.

## Phase 0 in detail

1. **Plan in the repo** (this document).
2. **Fix `template_id`** in `update_invoice`, with a regression test.
3. **Money rules.** One rule, documented and tested, used by the server and the app:
   - A line amount is `quantity x unit price`, rounded to 2 decimals (half up).
   - The net total is the sum of the line amounts.
   - VAT is the net total times the rate, rounded to 2 decimals (half up). Until VAT codes arrive in
     phase 2, the rate is one configured constant (25%).
   - Gross is net plus VAT.
   - The server computes `amount`, `vat_amount` and `gross_amount` (and each line's `amount`) and
     ignores the values the client sends. Money columns become `Numeric(14,2)`; quantity and unit
     price keep 3 decimals. The migration rounds existing values (checked 2026-10-24: no existing
     amount has more than 2 decimals).
   - The Vue app uses the same rule for its live preview, and no longer hardcodes 25% in the form,
     the preview or the show page.
   - The `excluding_vat` flag is stored but nothing uses it (every invoice behaves as excluding VAT),
     and no row has it set to false (checked 2026-10-24). Proposal: remove it in this step.
4. **Chart of accounts.** Propose a standard chart including receivables, payables, VAT, VAT
   settlement and equity accounts, and the system accounts the posting service will use, then have an
   accountant check it. This is a document first, not code.

### Deliberately not in phase 0: locking approved invoices

An approved invoice can be edited today (the show page offers Edit while it is approved and not sent).
Locking it before approving creates postings would remove that without any benefit and without a way
to correct a mistake. The lock comes in phase 3, together with postings and credit notes: approving
books the invoice, a booked invoice is read-only, and a credit note corrects it.

## First slices after phase 0

1. Fiscal years and journal tables, the posting service, and balance invariants.
2. Reversals and the audit log.
3. System accounts and the fuller standard chart.
4. Account ledger and trial balance in the API and the app.

## Open decisions

- Whether and when to offer the system to others, which depends on what Erhvervsstyrelsen says about
  free offerings (see Assumptions).
- Fiscal year start, and the VAT settlement period (half-yearly or quarterly) for each organization.
- Whether the rounding rule above (per line, then VAT on the net total) matches what the accountant
  wants, and whether to keep 3-decimal quantities and unit prices.
- Which standard chart of accounts to adopt (not yet verified against Erhvervsstyrelsen's standard
  chart).
- How far to take e-invoicing and direct VAT filing.
