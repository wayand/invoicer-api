# VAT engine (design for phase 2)

The design for phase 2 of the [accounting plan](accounting-plan.md): VAT (`moms`) on every posting,
a VAT report for any period, the settlement posting, and locking a period once it is settled. It
uses the accounts and roles of the [chart of accounts](chart-of-accounts.md), the posting service of
the [ledger design](ledger-design.md) and the money rules in [money-rules.md](money-rules.md). This
page is for approval before any migration is written. Section 11 lists what I need you (and
the accountant) to decide.

No legal or tax advice: the VAT treatment of each code has to be checked by an accountant before
anyone relies on the report.

## 1. What phase 2 delivers, and what it does not

In:

1. The official VAT codes (72) as a table, each classified by us: where its VAT is posted, which
   box of the return its amount goes to, and whether this phase can calculate it.
2. A VAT engine: given net amounts and VAT codes, the server calculates the VAT and posts it, for
   manual vouchers now and for invoices and bills in phases 3 and 4.
3. A VAT code on every invoice line (replacing the single sales tax rate of the organization), with
   VAT calculated per code.
4. The VAT report for any range of dates: the figures to enter by hand in TastSelv Erhverv, derived
   from the ledger and checked against it.
5. VAT periods (half-yearly, quarterly or monthly), the deadline of each, the settlement posting
   that moves the VAT to `7840 Skyldig moms` (or `6320`), and a lock on the settled period.

Not in phase 2 (see section 10): filing to SKAT, the EU sales list, OSS, import VAT from customs,
the special schemes (used goods, margin, cars), deduction that needs a percentage the user decides,
and cash-basis VAT.

VAT belongs to the period in which the supply is made, and an invoice issued before the supply ends
or soon after it counts as the time of supply (`momsloven` § 23, stk. 1 and 2): this is invoice-based
VAT, not cash-basis. So VAT is booked on the invoice date, not when the customer pays. That is how the
ledger works too: approving an invoice posts the VAT (phase 3), and the payment does not touch it. An
invoice issued long after the supply belongs to the period of the supply: see
[invoice-posting-design.md](invoice-posting-design.md), section 3.

## 2. The official codes, and which ones phase 2 supports

`Momskoder-Bruttoliste` (valid from 2025-12-01, already in `app/seed/standard/`) lists 72 codes. Each
code has an old name (`S1`, `K-EU-V-1`) and a new one (`S01`, `K210`). The file describes each in
words: the rate, the deduction share (`fradragsret`), and where it goes on the return
(`momsangivelse`). None of that is in a form a program can use, so we classify every code once, in
our own file that is checked against the official one (section 3).

A code is **supported** in phase 2 when its VAT can be calculated from the net amount alone: a rate
of 25% or 0%, and a fixed deduction share. That is **22 of the 72**:

| Code (old) | Official name | Rate | Deduction | VAT posted as | Net amount goes to box |
|---|---|---|---|---|---|
| S01 (S1) | S_DK_25 | 25% | | output | |
| S02 (S0) | S_DK_0 | 0% | | none | C |
| S81 (S%) | S_DK_UdenforMomslov | | | none | |
| S82 (SMF) | S_DK_Momsfritaget | | | none | |
| S21 (S2) | S_EU_Varer_MomsNulPct | 0% | | none | B goods |
| S22 (S7) | S_EU_Varer_MomsNulPct_ejEU_salgsangiv | 0% | | none | B goods, not on the EU sales list |
| S23 (S3) | S_EU_Ydelser_MomsNulPct | 0% | | none | B services |
| S24 (SMFEU) | S_EU_Momsfritaget | | | none | |
| S41 (S4) | S_ejEU_Varer_MomsNulPct | 0% | | none | C |
| S42 (S5) | S_ejEU_Ydelser_MomsNulPct | 0% | | none | C |
| S43 (S6) | S_ejEU_Momsfritaget | | | none | |
| K010 (K1) | K_DK_FuldFradrag | 25% | 100% | input | |
| K030 (K0) | K_DK_IngenFradrag | | 0% | none | |
| K040 (K5A) | K_DK_FastnettelefonFuld | 25% | 50% | input | |
| K070 (K25A) | K_DK_ReprFradragFuld | 25% | 25% | input | |
| K210 (K-EU-V-1) | K_EU_Varer_Fradrag | 25% | 100% | acquisition, goods | A goods |
| K230 (K-EU-V-0) | K_EU_Varer_IngenFradrag | 25% | 0% | acquisition, goods | A goods |
| K260 (K-EU-Y-1) | K_EU_Ydelser_FuldFradrag | 25% | 100% | acquisition, services | A services |
| K280 (K-EU-Y-0) | K_EU_Ydelser_IngenFradrag | 25% | 0% | acquisition, services | A services |
| K340 (K-EU-MF) | K_EU_Momsfritaget | 0% | 0% | none | |
| K460 (K-%EU-Y-1) | K_ejEU_Ydelser_FuldFradrag | 25% | 100% | acquisition, services | |
| K480 (K-%EU-Y-0) | K_ejEU_OmvBetPl_Ydelser_IngenFradrag | 25% | 0% | acquisition, services | |

The other **50 are listed but cannot be chosen yet**, in these groups:

| Why not yet | Count | Codes |
|---|---|---|
| Deduction that needs a percentage or a calculation (estimated, partial, by area or sector, leasing cars) | 23 | K020, K090, K100, K110, K120, K130, K220, K240, K250, K270, K290, K300, K310, K320, K420, K440, K450, K470, K490, K500, K670, K680, K700 |
| Special schemes: used goods, margin VAT, cars, artists, VAT in another country | 10 | S83 to S88, K620 to K650 |
| OSS: online sales to consumers in the EU | 5 | S61 to S65 |
| A fixed share I would like the accountant to confirm (the file says 66,6%, 50%, 33,3% and 25%) | 5 | K050, K060, K080, K330, K610 |
| Domestic reverse charge | 2 | K660, K690 |
| Refund scheme | 2 | K710, K720 |
| Import VAT: the amount comes from the customs documents, not from the invoice | 2 | K410, K430 |
| Triangular trade: needs the EU sales list (phase 7) | 1 | S25 |

A deferred code is a row like the others, with its reason and no direction (a constraint makes a
code either supported with a direction, or deferred with a reason): posted lines point at the code
table, and the table must hold every official code from the start. Only a supported code can be
the default code of an account.

## 3. Data model

**`vat_codes`** (one table for everyone, not one per organization: the codes are the same for all).

| Column | Meaning |
|---|---|
| `id` | key, the one posted lines point at |
| `code` | the new name (`S01`, `K210`), unique. See decision 2 |
| `legacy_code` | the old name (`S1`, `K-EU-V-1`) |
| `name`, `title` | the official long name and the heading of the file |
| `applies_to` | `sales` or `purchases` |
| `rate` | `NUMERIC(6,4)`: 0.2500, 0.0000, or null when the file leaves it open |
| `deduction` | `NUMERIC(6,4)` share of the VAT that is deductible, null for sales |
| `direction` | `output`, `input`, `acquisition_goods`, `acquisition_services` or `none`. Null for a deferred code |
| `base_box` | where the net amount is reported: `a_goods`, `a_services`, `b_goods`, `b_services`, `c`, or null |
| `is_supported` | whether the engine calculates it (section 2) |
| `deferred_reason` | why a code cannot be chosen yet (the groups of section 2), null for a supported one |
| `valid_from`, `valid_to` | the version of the file it came from |

A migration inserts the rows as data. It does not read the JSON file in the repository, because a
migration must give the same result for ever. A test compares the table with the official file and
with our classification, so every official code has to be classified, and a new file version fails
the test until it is.

When Erhvervsstyrelsen publishes a new list, a new migration adds the new codes and sets
`valid_to` on the ones that are gone. Rows are never deleted or changed: posted lines refer to them.

**`journal_lines`** gets two columns and a constraint.

| Column | Meaning |
|---|---|
| `vat_code_id` | the code, or null for a line that has nothing to do with VAT |
| `vat_part` | `base`, `vat` or `nondeductible` (below), null exactly when `vat_code_id` is null |

- `base` is the net line: the sale or the expense, with the code that applies to it. Its amount is
  what goes to box A, B or C.
- `vat` is the VAT line the engine adds on a VAT account.
- `nondeductible` is the part of the VAT that cannot be deducted. It is a separate line on the same
  account as the `base` line, so the cost is the full amount while the report still sees the net
  amount. A line per part, instead of one rounded-up expense line, keeps the account ledger and the
  report honest.

These are written by the posting service only. The database already keeps entries balanced and
unchangeable; it does not check the VAT calculation, because that needs the rates and the rounding
rule. That is checked by the service, by tests (section 9) and by the reconciliation of the report
(section 6).

**`organizations`** gets `vat_period_type` (in the organization API, null until it is set):
`half_year`, `quarter`, `month`, or null when the organization is not VAT-registered. A sole proprietorship below the turnover limit has no VAT and
uses no codes (decision 1).

**`accounts`** gets `default_vat_code_id`: the code a new line on the account starts with. The
starter chart sets the defaults of [chart-of-accounts.md](chart-of-accounts.md). It is a
suggestion for the screen, never enforced.

**`invoice_lines`** gets `vat_code_id` (section 7).

**`vat_periods`**: one row per settled period, created by the settlement (section 8).

## 4. The calculation

All of it with `Decimal`, rounded half up to 2 decimals, as in the money rules.

For the lines of one entry (a voucher, an invoice) that carry the same code:

1. `base` = the sum of their net amounts, each line rounded as before.
2. `VAT` = `round(base x rate)`. One rounding per code and entry, not per line: the same rule the
   invoice has today (VAT once on the net total), now applied per code. With a single code the
   results do not change, so the existing cases of `money_cases.json` stay valid, and new cases
   with several codes are added to the same file for the app.
3. For a purchase, the deductible VAT is `round(VAT x deduction)` and the rest, `VAT - deductible`,
   is the `nondeductible` line.

What is posted, by direction. "Cost" is the account of the `base` line.

| Direction | Lines the engine adds |
|---|---|
| `output` (sale) | credit `7680 Salgsmoms` for the VAT |
| `input` (domestic purchase) | debit `7740 Købsmoms` for the deductible VAT, and debit the cost account for the rest |
| `acquisition_goods` | credit `7700 Moms af varekøb udland` for the VAT, debit `7740` for the deductible part, and debit the cost account for the rest |
| `acquisition_services` | the same with `7720 Moms af ydelseskøb udland` |
| `none` | nothing: no VAT |

Accounts are found by their roles (`output_vat`, `input_vat`, `vat_eu_goods`, `vat_eu_services`),
never by number. If the organization has no account with a needed role, the entry is refused with
409 and the name of the role.

A caller sends only the net lines with a `vat_code`. The VAT lines are the server's. A caller can
no longer make the VAT wrong by sending a wrong figure, the same principle as for invoice totals.
Lines without a code are posted as they are, as today. The lines the caller gives must balance
together with the VAT lines (the refusal says "with the VAT lines"), so a caller adds the VAT to its
gross line the same way: the engine (`app/vat_engine.py`) is a pure function for this, and its cases
in `tests/unit/vat_cases.json` are shared with the app.

The non-deductible VAT is shared over the lines of the code in proportion to their amounts, to the
cent, so each cost account gets its own part. What is left after rounding down goes to the largest
remainders, the first line first when they are equal. A credit note shares like the invoice it
corrects, negated.

What the service refuses, each with 422 and nothing posted: a code that does not exist (the old
name `S1` is not a code), a code that cannot be used yet, a code on one of the VAT accounts, an
organization that is not VAT-registered, a `vat_part` from the caller, and lines that do not
balance with the VAT lines. It refuses with 409 when the organization has no account for a role the
VAT needs.

### Worked examples (25% VAT, accounts as in the starter chart)

| Event | Lines |
|---|---|
| Sale 1,000 with `S01`, and 400 of EU services with `S23` | Dr `6190` 1,650; Cr `1010` 1,000; Cr `1150` 400; Cr `7680` 250 (the 250 is `S01` only) |
| Domestic purchase 800 with `K010` | Dr `1610` 800; Dr `7740` 200; Cr `7440` 1,000 |
| Representation 100 with `K070` (25% deductible) | VAT 25.00, deductible 6.25: Dr `1910` 100; Dr `1910` 18.75 (nondeductible); Dr `7740` 6.25; Cr `7440` 125 |
| EU services 800 with `K260` | Dr cost 800; Dr `7740` 200; Cr `7440` 800; Cr `7720` 200 |
| EU goods 800 with `K230` (no deduction) | Dr `1630` 800; Dr `1630` 200 (nondeductible); Cr `7440` 800; Cr `7700` 200 |

In the EU rows the supplier charges no VAT, so the payable is 800. We owe the 200 to SKAT as
acquisition VAT, and deduct it again when the code allows.

## 5. Reversals and credit notes

A reversal copies every line with debit and credit swapped, and now also its `vat_code_id` and
`vat_part`. So a reversal cancels the VAT in the report as well, with no extra code. It is dated
today, or on the date of the voucher if that is later, so a correction of a settled period lands in
the current period. That is how Danish VAT corrections work in practice. (Corrections that
reach back more than a period have rules of their own: a later phase.)

## 6. The VAT report

`GET /reports/vat?from=&to=` for any range of dates, like the other reports. It reads the journal and
nothing else, by the date of the entry. It returns what to enter in TastSelv Erhverv:

| Part of the return | Where the figure comes from |
|---|---|
| Salgsmoms (udgående moms) | `vat` lines on the `output_vat` account: credit minus debit |
| Købsmoms (indgående moms) | `vat` lines on the `input_vat` account: debit minus credit |
| Moms af varekøb i udlandet | `vat` lines on the `vat_eu_goods` account |
| Moms af ydelseskøb i udlandet | `vat` lines on the `vat_eu_services` account |
| Rubrik A, varer and ydelser | `base` lines of the codes with `base_box` `a_goods`, `a_services` |
| Rubrik B, varer and ydelser | `base` lines of the codes with `b_goods`, `b_services` |
| Rubrik C | `base` lines of the codes with `c` |
| Total to pay (or refund) | salgsmoms + the two acquisition lines - købsmoms |

Each figure is also given per code, so any number can be traced to the vouchers behind it. The
response (`app/reports.py`, `vat_report`), all amounts as positive numbers with 2 decimals:

- `sales_vat`, `input_vat`, `eu_goods_vat`, `eu_services_vat`, and `total_to_pay` (negative when
  the period is to be refunded).
- `boxes`: `a_goods`, `a_services`, `b_goods`, `b_services` and `c`, the net amounts of the codes
  with that `base_box`. A sale counts as credit minus debit, a purchase as debit minus credit, so
  a credit note reduces its box.
- `codes`: for each code with a posting in the range, sorted by code: `code`, `title`,
  `applies_to`, `direction`, `base_box`, `rate`, `deduction`, and `base`, `output_vat`,
  `input_vat`, `acquisition_vat` and `nondeductible_vat`. `input_vat` is only what is deducted; the
  rest of the VAT of a purchase is `nondeductible_vat`, which is a cost and is not on the return.
  A code whose entries were all reversed is still listed, with zeros.
- `ledger_check`: `accounts`, one for each of the four VAT roles (`role`, `account`,
  `ledger_balance`, `reported`, `difference`, with `account` null when the organization has no
  account with the role), `uncoded_lines`, and `ties`, which says that every difference is zero.

Only lines with a VAT code and part count toward a figure. An organization that has left VAT can
still read its report. The report has a second part: **the check against the ledger.** For each of the four VAT accounts it
shows the balance of the account in the range next to the figure above. They must be equal. If
they are not, the difference is made of postings on a VAT account that have no VAT code (for
example a voucher typed by hand with its VAT line, as before phase 2), and they are listed.

Two things to confirm in the real return before the report is built (decision 6): the exact labels
and order of the boxes, and whether amounts are entered in whole kroner or with øre. The boxes above
are what skat.dk and the guidance of PwC describe: A is the value of purchases from other EU
countries, B the value of sales without VAT to other EU countries, C the value of other sales
without VAT, and the VAT of purchases abroad is its own line, counted both as VAT to pay and in
the input VAT. The return also has lines for oil, electricity, gas, coal, CO2 and water duties. We
do not handle those.

## 7. Invoices

- `invoice_lines.vat_code_id` is required. It starts from the default of the line's account.
  Only supported sales codes can be used on an invoice.
- Totals are calculated per code (section 4): `amount` is the net total, `vat_amount` the sum of
  the VAT of each code, `gross_amount` the sum. An invoice response also lists the VAT per code
  (`code`, `rate`, `base`, `vat`) because a Danish invoice must show it by rate.
- The single "active sales tax rate" of the organization, and the 409 when there is none or several,
  are gone. `money-rules.md` is updated: the rule is the same, VAT once per code and not once per
  invoice.
- An organization that is not VAT-registered can still make invoices: it uses a code without VAT
  (`S81`, `S82` ...). The registration is checked when the invoice is posted in phase 3, as it is
  for a voucher.
- Lines that existed before the codes got `S01`, the rate every invoice was calculated with, and
  keep their amounts until the invoice is saved again.
- Invoices are still not posted. Approving an invoice posts it in phase 3, using this engine.
- `tax_rates`, `accounts.tax_rate_id`, the `/tax-rates` routes and the tax rate store in the app
  are replaced by the VAT codes and removed in the same PR as the invoice change. Nothing is live,
  so no data is migrated.

## 8. VAT periods, settlement and locking

**Periods.** From `organizations.vat_period_type`: half-yearly (January to June, July to December),
quarterly, or monthly. The first period starts at the beginning of the calendar period of the
first VAT-coded posting. After a settled period, the next one starts the day after it and runs to
the next boundary of the current type, so changing the type works from the next period on.

**Deadlines.** The filing and the payment are due on the same date. For half-yearly and quarterly
periods it is the first day of the third month after the period ends: 1 June, 1 September,
1 December and 1 March for quarters, 1 September and 1 March for half-years. When that day is a
weekend or a holiday the date moves (it was 2 March 2026). Monthly deadlines are around the 25th
of the next month, with exceptions (the June 2026 period is due 17 August). The engine calculates
the plain date and moves it past weekends. Danish holidays and exceptions are not coded, so the
date is stored on the period and can be corrected, and the screen says to check
[skat.dk](https://skat.dk/erhverv/moms/frister-indberet-og-betal-moms). Missing it gives a
provisional assessment, a fee (1,400 kr. per period at the time of writing) and interest.

**Settlement.** `POST /vat-periods/settle` for the first open period, only after the period has
ended (decision 7: before that it is refused with 409 and says from when it can be settled). The
posting service makes one voucher (`source_type` `vat_settlement`, `source_id` the period), dated
the last day of the period, that moves the whole balance of the VAT accounts of the period to
`7840`. This is what the accountant's note describes.

| Lines | |
|---|---|
| Debit `7680` for the sales VAT, `7700` and `7720` for the acquisition VAT | what is owed |
| Credit `7740` for the input VAT | what is deducted |
| Credit `7840 Skyldig moms` for the difference | when the result is VAT to pay |
| or debit `6320 Tilgodehavende moms` | when the result is a refund |

Example: sales VAT 250, acquisition VAT 200, input VAT 400. Debit `7680` 250 and `7720` 200,
credit `7740` 400 and `7840` 50. The VAT accounts are then zero for the period, and `7840` holds
the 50 until SKAT has drawn it from the Skattekonto (phase 5 covers the payment). An account whose
balance is on the other side (a credit note larger than the sales) is cleared the other way. A period
where nothing moves (only codes that carry no VAT) is settled with no voucher.

The settlement refuses (409) when the report does not tie to the ledger (section 6): you cannot
settle a period with postings on VAT accounts that are not coded, so the return always agrees
with the books (decision 5). The fix is to reverse them, with the reversal dated inside the period
(a reversal is otherwise dated today, and the posting would stay in the period), and post them
again with a code. Uncoded postings that cancel inside the period are no obstacle, because the
report and the ledger then agree. The report of a period leaves out the settlement voucher in its
check against the ledger, so a settled period still shows the figures that were settled and ties.

**Filing.** The user enters the figures in TastSelv Erhverv and then marks the period filed:
`POST /vat-periods/<id>/file` with the date it was filed (default today, not in the future and not
before the period ends) and an optional reference. A period is filed once. Filing locks nothing more
than settling does; it records that the deadline was met, and the audit log says whether it was.

**Locking.** An entry dated inside a settled period is refused (409, with the period) if it touches
VAT: a line with a VAT code, or a line on `7680`, `7700`, `7720`, `7740`, `7840` or `6320`. Other
entries, for example a bank fee posted late, are still allowed (decision 4). A reversal is dated
today or later (section 5), so it falls in an open period. There is no way to un-settle: a
mistake in a settled period is corrected in a later one, and the settlement voucher itself cannot be
reversed. The lock is in the posting service. It runs after the service has taken the lock of the
books of the organization (the same row every posting locks for its voucher number), and so does the
settlement, so an entry and a settlement cannot pass each other: whichever comes second sees the
other. The settlement is let through its own lock, which is why it can be dated inside the period.

**`vat_periods`**: `id`, `organization_id`, `period_type`, `start_date`, `end_date`, `due_date`,
`status` (`settled` or `filed`), `settlement_entry_id` (null when nothing was moved), `settled_at`,
`settled_by`, `filed_on` (the day the user says it was filed), `filed_by`, `reference`. The figures
are not stored: they come from the ledger, and the lock keeps them unchanged. A period that is filed
must say when and by whom, which the database checks. Settling, filing and a corrected due date
are written to the audit log (`vat_period.settled`, `vat_period.filed`,
`vat_period.due_date_changed`).

**The API.**

- `GET /vat-periods`: the settled periods, newest first, and `open_period`: the first period not
  settled yet, with `ended`, `can_settle` and `blocked_by` (what stops it, in words), or null when
  the organization is not VAT-registered or nothing has a VAT code yet. The open period is not stored:
  it follows from the last settled period, and for the first one from the earliest posting with a code.
- `POST /vat-periods/settle`: settles the open period, 201 with the period.
- `POST /vat-periods/<id>/file`: body optional (`filed_on`, `reference`).
- `PATCH /vat-periods/<id>` with `due_date`: corrects the due date, after the period ends.

## 9. How it is tested

The invariants, as tests, in the style of phases 0 and 1:

- For many random entries with several codes: debit equals credit, every `vat` line equals the
  calculation for its code and entry, and the `nondeductible` part plus the deductible part equal
  the VAT.
- The report ties to the ledger: for random data, each VAT figure equals the balance of its
  account for the same range, and a posting without a code shows as a difference.
- Reversing any entry sets every figure of the report back to what it was.
- Settlement leaves the four VAT accounts at zero for the period, whatever the mix of codes, and
  the amount on `7840` or `6320` equals the total of the report.
- A settled period refuses an entry that touches VAT and allows one that does not; a refusal
  leaves nothing behind (the savepoint).
- The cases of `money_cases.json` (shared with the app) have new multi-code cases, and the app's
  `money.js` is tested on the same file.
- Every official code is classified, and the table equals the file (section 3).

## 10. Open items, left out on purpose

- Filing to SKAT, and anything that needs a registration with SKAT as a system provider.
- The EU sales list (`EU-salgsangivelse`) and triangular trade, with the SAF-T export in phase 7.
- OSS, import VAT from customs (the amount is on the import specification, not on the invoice),
  domestic reverse charge, refund schemes, and the special schemes. Section 2 lists the codes.
- Deduction that depends on a percentage the owner sets (`K020`, `K110` and others): this needs a
  setting per organization, and its own PR after the first five.
- Cash-basis VAT, duties (oil, electricity, gas and so on), and VAT groups.
- A VAT period that spans a change of company form, and registering for VAT in the middle of a year
  (the first period starts at the calendar boundary).

## 11. Decisions to confirm

Each has my recommendation. Decisions 4, 5 and 7 were taken as recommended when PR 5 was built, and
are marked **Decided**. The others are still open.

1. **Which of your businesses are VAT-registered, and with which period?** The sole proprietorship
   may be below the limit and have no VAT at all, in which case `vat_period_type` stays empty and
   the VAT screens stay hidden. Recommendation: set it per organization when you have the answer.
2. **The code name used in the app and the database.** The new one (`S01`, `K010`) or the old
   one (`S1`, `K1`). Recommendation: the new, because it is the one the standard is moving to, and
   show the old one next to it. Which one SAF-T wants is a question for phase 7.
3. **The 22 supported codes.** Is that the right set for your businesses? In particular the
   fixed shares: `K040` 50% and `K070` 25% are supported, the others at 66,6%, 33,3% and 50% wait
   for the accountant.
4. **What a settled period locks.** Only entries that touch VAT (recommended), or every entry dated
   in the period. The second is stricter, but it blocks a late bank fee or a correction of an
   expense, and the fiscal-year closing of phase 6 is the better place for it. **Decided:** only
   entries that touch VAT (PR 5).
5. **Uncoded postings on VAT accounts.** Allowed, shown in the report, and settlement refused until
   fixed (recommended), or refused when posted. The second breaks the vouchers typed by hand
   with a VAT line, which are useful for odd cases. **Decided:** allowed and shown, settlement
   refused until fixed (PR 5).
6. **The real return.** Please open the VAT return in TastSelv Erhverv (or the guide on skat.dk)
   and check three things: the labels and order of the boxes, whether amounts are whole
   kroner or with øre, and whether there is a box I have not mentioned that applies to you. I
   could not read the official guidance PDF I found (it is from 2017), so the boxes in section 6
   come from skat.dk and PwC pages and are not yet checked against the form.
7. **Settling before the period has ended.** Refused (recommended), or allowed for a period still
   running. **Decided:** refused (PR 5).
8. **The default VAT code per account**, which is my guess in the chart of accounts document:
   rent and insurance without VAT, postage and fares exempt, cars limited. The accountant should
   confirm it.

## 12. The PRs of phase 2

Each is a branch, with tests, and each is merged before the next.

| # | Repo | What | Needs |
|---|---|---|---|
| 1 | api | `vat_codes` table with the 72 rows and our classification, the test against the official file, `GET /vat-codes`, `vat_period_type` and `accounts.default_vat_code_id`, the starter chart defaults | decisions 1, 2, 3, 8 |
| 2 | api | The engine and the posting service: `vat_code` on lines, the VAT lines, the `journal_lines` columns, reversals copying the codes, manual vouchers with codes | PR 1 |
| 3 | api | Invoices with a VAT code per line and VAT per code, the rule in `money-rules.md` and the shared cases, `tax_rates` removed | PR 1 |
| 4 | api | `GET /reports/vat` with the check against the ledger | PR 2 |
| 5 | api | `vat_periods`, the deadlines, settlement, filing and the lock | PR 2, 4 and decisions 4, 5, 7 (6 does not change it: the boxes are the report's) |
| 6 | app | VAT code per line in the voucher form, with the VAT lines shown as they will be posted | PR 2 |
| 7 | app | VAT code per invoice line, VAT per code in the preview and on the show page | PR 3 |
| 8 | app | The VAT report screen and the periods screen (deadline, settle, mark filed) | PR 4 and 5 |

The app PRs use the same rules as the server, in whole numbers (`money.js`), and the same shared
test cases, as for invoices in phase 0.
