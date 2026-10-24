# Money rules

How money is stored, rounded and added up. The server owns these rules: amounts sent by a client are
never used. The code is in `app/money.py`; this page is the reference that code and tests follow.
(Part of phase 0 of the [accounting plan](accounting-plan.md).)

## Types

Money is `decimal.Decimal` in Python and `NUMERIC` in PostgreSQL, never a float. PostgreSQL's
`numeric` and `decimal` are the same type, and its documentation recommends `numeric` for monetary
amounts because the arithmetic is exact. Every money column has a fixed precision and scale:

| What | Column type | Decimals |
|---|---|---|
| Amounts: invoice `amount`, `vat_amount`, `gross_amount`, line `amount`, `default_reminder_fee` | `NUMERIC(14,2)` | 2 |
| Quantities and unit prices: line `quantity`, line and product `unit_price` | `NUMERIC(14,3)` | 3 |
| VAT rates (a fraction: 0.25 is 25%): `tax_rates.rate` | `NUMERIC(6,4)` | 4 |

`NUMERIC(14,2)` holds amounts up to 999,999,999,999.99. Raising a scale later loses nothing;
lowering it rounds, so the amount scale starts at 2.

## Rounding

Always **half up, away from zero** to 2 decimals: 1.005 becomes 1.01 and -2.675 becomes -2.68.
PostgreSQL rounds the same way when it stores a value into a column with a smaller scale, so the
database and the application agree. (Python's default, half to even, and floating point do not:
in a browser `1.005 * 100` is `100.49999999999999`.)

## Adding up an invoice

1. **Line amount** = `round(quantity x unit price)`.
2. **Net total** (`amount`) = the sum of the line amounts.
3. **VAT** (`vat_amount`) = `round(net total x rate)`.
4. **Gross total** (`gross_amount`) = net total + VAT.

Each line is rounded before the lines are added, so the totals always match the lines as printed.
VAT is calculated once on the net total, not per line.

| Case | Result |
|---|---|
| 3 x 0.335 | line 1.01, VAT 0.25, gross 1.26 |
| 1 x 0.10 | VAT is 0.025, rounded to 0.03 |
| ten lines of 1 x 0.005 | each line 0.01, net 0.10 (not 0.05), VAT 0.03, gross 0.13 |
| 1 x -2.675 | line -2.68, VAT -0.67, gross -3.35 |

The full table of cases is `tests/unit/money_cases.json`. The `invoicer-vue` repo keeps a copy for
its own tests: change both together.

## The VAT rate

Until invoice lines carry their own VAT code (phase 2), every invoice is calculated with the
organization's single **active sales tax rate** (`tax_rates` with `applies_to_sales` and
`is_active`, such as the seeded "Salgsmoms", 0.25). A rate of 0 is a rate. If the organization has
none or more than one, creating or saving an invoice returns 409 instead of guessing.

## The API

- `amount`, `vat_amount` and `gross_amount` on an invoice, and `amount` on a line, are output only.
  If a client still sends them (the app used to), they are ignored, as is `excluding_vat`, a flag
  that nothing used and that no longer exists.
- Money is returned as JSON numbers (`1250.5`), including negative numbers (credit lines).
- `quantity` and `unit_price` must be JSON numbers with at most 3 decimals and fit their columns
  (below 100 billion); more decimals are rounded half up.
- An amount that cannot be stored (`NUMERIC(14,2)`) returns 422 and nothing is saved.

## Changing the rules

A change to a rule changes `app/money.py`, `tests/unit/money_cases.json`, this page, the matching
code and cases in `invoicer-vue`, and usually needs a migration. Existing invoices keep the
amounts they were saved with; they are recomputed only when they are saved again.
