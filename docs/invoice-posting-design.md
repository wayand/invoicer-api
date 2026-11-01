# Phase 3: sales on the ledger

Design, drafted 2026-11-01. Nothing here is built yet. Part of the [accounting plan](accounting-plan.md),
after the [ledger](ledger-design.md) (phase 1) and [VAT](vat-design.md) (phase 2). Read those first:
this document uses the posting service, the VAT engine, the VAT periods and the report check as they
are, and does not repeat them.

The decisions that are yours are in section 12, each with my recommendation. Everything else is
written as if the recommendations are taken.

## 1. What phase 3 delivers, and what it does not

Phase 3 is the milestone M2 of the plan: approve an invoice, record the payment, and see everything in
the ledger and in the VAT report. It delivers:

1. **Approving an invoice posts it.** One voucher: the customer owes the gross amount, the sales
   accounts and the output VAT are credited. The invoice gets its number, becomes read-only, and is
   tied to its voucher.
2. **Credit notes** correct an approved invoice. An approved invoice is never edited or deleted.
3. **Payments** from customers, with allocation to invoices, partial payments and credit kept for
   the customer. This replaces the `is_paid` flag, which the browser can set today.
4. **A receivables report** (who owes what, by invoice) that must agree with the receivables account
   of the ledger, the same idea as the check of the VAT report.
5. **Reminders** (`rykkere`), as records first. Their fees are posted once the accountant has
   answered where they go (section 9).

It does not deliver: e-invoicing and sending invoices by e-mail (phase 7), bank import and matching
(phase 5), more than one currency, cash-basis VAT, bad debts and write-offs, a refund of a credit
balance to a customer, interest on late payment, recurring invoices and quotes (phase 8). Section 11
lists what each of them needs when its time comes.

## 2. Where the code is today

What exists, found in the code on 2026-11-01:

- An invoice has `state` (`draft` or `approved`), `is_sent` and `is_paid`. **All three are set by the
  client.** `PUT` lets the browser change an approved invoice freely, including its lines and its
  state, and `DELETE` trusts those flags. Nothing is posted. The plan said this
  would be fixed when approving starts to post, and this is that phase.
- Totals are the server's: amounts per line, VAT per VAT code, a `vat_by_code` list (phase 2). The
  numbers are those of the VAT engine, and a test keeps them equal.
- The invoice number is a text. In `sequential` mode the number comes from
  `invoice_settings.next_invoice_no` **when the draft is created**, so a deleted draft leaves a gap.
  In `manual` mode the user types it. The primary key of `invoices` is `(organization_id,
  invoice_no)`, with `id` as a unique column that the lines point at.
- A line has a product, and a product may have an account (`products.account_id`). There is no
  account on the line, and the settings have a default account and a deposit account.
- The posting service takes lines with a contact (`journal_lines.contact_id`), a source type and a
  source id, and has the roles for receivables and for each kind of sale (`sales`, `sales_eu_goods`,
  `sales_eu_services`, `sales_non_eu_goods`, `sales_non_eu_services`). Nothing posts an invoice yet.
- `reverse_entry` reverses any entry. For an invoice that would leave an approved invoice with a
  reversed voucher and no way to see it, so section 8 closes it.

## 3. The Danish rules that shape it

Checked on 2026-11-01 against the official texts (the Tax Agency's legal guidance at info.skat.dk,
Erhvervsstyrelsen, and retsinformation.dk). What I could not read in the official text is marked.
The system follows Danish rules only.

- **An invoice for every taxable supply.** A VAT-registered business issues an invoice for each
  supply with VAT, to businesses and to private persons alike (`momsloven` § 52 a, stk. 1). If
  payment is due before the supply is complete, an invoice is issued for that amount. A business
  that is **not** VAT-registered may not show VAT on its invoices, and has to pay what it shows if it
  does (§ 52 a, stk. 6 and 7)
  ([A.B.3.3.1.2](https://info.skat.dk/data.aspx?oid=2068787)). Section 4 uses this.
- **What a full invoice shows** (`momsbekendtgørelsen` § 58, stk. 1; the order is BEK nr. 1435 of
  2023 with later changes, so the newest number is looked up on retsinformation.dk): the issue date, a sequential number, the seller's CVR number, the names and addresses of
  seller and buyer, the quantity and kind of goods or the scope and kind of services, the date of
  supply **if it differs from the issue date**, the unit price without VAT and any discount, the VAT
  rate, and the VAT amount
  ([A.B.3.3.1.4](https://info.skat.dk/data.aspx?oid=2068789)). The template is checked against this
  list in a separate task (section 11).
- **Numbering.** The number is sequential, "based on one or more series", and identifies the invoice.
  The same demands apply to credit notes, so one series or several are both allowed, and a number is
  never used twice. Only utilities and telephone companies with customer numbers are excused. This
  is why the number is taken when the invoice is approved (section 6), and not when a draft is
  started: a draft that is deleted must not leave a gap in a series of invoices that were issued.
- **Credit notes.** A sent invoice cannot be cancelled by cancelling it in the books: a credit note
  goes to the customer. The guidance does **not** say that the credit note must carry the number of
  the invoice. It says that a document that "specifically and unambiguously" changes or refers to
  the invoice is treated as an invoice (§ 58, stk. 2). Referring to the invoice is the way to be
  that, and it is how Dinero and Pleo describe the rule, so the design requires the reference
  (decision 4).
- **When the VAT belongs to a period.** VAT is due when the supply is made (`momsloven` § 23, stk. 1).
  If an invoice is issued before the supply ends, or soon after it, the date of the invoice counts as
  the time of supply (stk. 2). A payment received before the supply can also be the time of supply
  (stk. 3). So the VAT is booked on the invoice date, and the invoice date has to be the day the
  invoice is issued, shortly before or after the supply. An invoice sent long after the supply has
  its VAT in the period of the supply: the app does not decide this for the user, and the date of
  supply (section 11) is what an auditor would look at. A payment after the invoice never touches VAT.
- **Posted entries.** A system a company builds for its own use falls under the requirements for
  non-registered systems
  ([Erhvervsstyrelsen](https://erhvervsstyrelsen.dk/ikke-registrerede-digitale-bogfoeringssystemer),
  section 4.2): it must not be possible to delete, change or backdate a finally booked transaction,
  and an error is corrected "ved en ny postering". A booked invoice is therefore corrected with a
  credit note and a new invoice, never edited.
- **Reminders** (`renteloven` § 9 b, in [LBK nr. 459 of 2014](https://www.retsinformation.dk/eli/lta/2014/459)):
  a fee of at most 100 kr. per reminder, for at most three reminders about the same claim, and only
  for reminders sent at least 10 days apart, and only when the reminder was sent with good reason
  (stk. 2). A collection fee of at most 100 kr. is allowed (stk. 3). Late payment carries interest at
  the central bank's lending rate of 1 January and 1 July plus 8 percentage points (§ 5). For
  business claims a fixed compensation of 310 kr. for collection costs can be claimed without a
  reminder (§ 9 a, stk. 3, and BEK nr. 105 of 2013). The interest and the fee are not part of the
  taxable amount: Landsskatteretten held that reminder fees are compensation for costs and not a
  payment for the supply, so **there is no VAT on them** (SKM2003.541.LSR, on
  [info.skat.dk](https://info.skat.dk/data.aspx?oid=170881)), and interest is excluded by `momsloven`
  § 27, stk. 3, nr. 4. I could read these texts only through summaries, because retsinformation.dk
  does not give its text to a program: the amounts are checked against the consolidated acts there
  before reminders are built.

## 4. Approving an invoice

`POST /organizations/<id>/invoices/<id>/approve`, for a draft invoice (like the other routes that
change an invoice). In one transaction (so that nothing is half done):

1. Lock the books of the organization (the same lock every posting takes, and the VAT settlement).
2. Check the invoice:
   - it is a draft, and has a contact of the organization and at least one line with an amount;
   - the currency is DKK (other currencies are refused, decision 10);
   - the date is not in the future (decision 7);
   - every VAT code is a supported sales code (as when it was saved) and every line has an account
     (section 5).
3. Take the number (section 6).
4. Post one entry dated the invoice date, `source_type` `invoice`, `source_id` the invoice:

   | Line | Debit | Credit | Contact |
   |---|---|---|---|
   | `receivables` (6190): the gross amount | gross | | the customer |
   | one line per invoice line, on its sales account, with its VAT code | | the line amount | |
   | output VAT, by the engine | | the VAT of each code | |

   The caller gives the net lines and the gross line, and the VAT service adds the VAT lines, exactly
   as for a voucher with codes (phase 2). A negative line (a discount) becomes a debit on its account
   and the VAT follows the sign. A line of 0 is not posted: it is text. If the gross amount is 0
   there is no receivable line. An invoice where all lines are 0 is refused: there is nothing to
   book.
5. Set `state` to `approved`, store `journal_entry_id`, `approved_at` and `approved_by`, and write
   `invoice.approved` to the audit log.

It is refused, with nothing written and no number taken, when the entry is refused: a closed fiscal
year (409), a VAT period that is settled (409: the invoice has to be dated in the open period, which
is possible because it is still a draft), or a chart without the accounts it needs (409).

**An organization that is not VAT-registered** (a sole proprietorship under the limit, say) may not
show VAT on its invoices (section 3). The code of phase 2 does not fit it yet: the posting service
refuses every VAT code for an organization with no VAT period, so approving an invoice would be
refused, and the invoice form preselects `S01` (25%) for every organization. So, for such an
organization:

- the lines of an invoice can only have a code that carries no VAT: `S81`, "outside the scope of the
  VAT law" (which code is the right one is a question for the accountant). The app preselects it and
  does not show the choice. An invoice with VAT (`S01`) is refused, on save and on approval, with 422;
- approving posts the invoice **without VAT codes**: there is no VAT to report and no VAT period, so
  the entry is the receivable against the sales accounts, nothing more;
- if the organization registers later, its earlier invoices stay as they were posted.

This closes a gap in phase 2 as well, and is part of PR 1 and PR 2 below.

The invoice and its entry then agree by construction: the gross amount of the invoice is the
receivable line, and the VAT of each code is the VAT of the lines. A test checks it on random invoices
(section 10).

## 5. The sales account of a line

A line has no account of its own. The account is found when the invoice is approved, in this order:

1. the account of the product, if the product has one: the user chose it;
2. otherwise the account with the role of the VAT code:

   | Code | Role |
   |---|---|
   | `S01`, `S02`, `S81`, `S82`, `S24`, `S43` | `sales` |
   | `S21`, `S22` | `sales_eu_goods` |
   | `S23` | `sales_eu_services` |
   | `S41` | `sales_non_eu_goods` |
   | `S42` | `sales_non_eu_services` |

3. the default account of the invoice settings, for the codes that go on `sales`, when the chart has
   no account with the role.

The product's account wins because it is the user's choice, but a product with a domestic account on
an EU sale then lands on the wrong account for the return. That is a mistake of the product, and the
VAT report shows the net amount of the code in its box whatever the account. The screen can warn, and
phase 6 (statements) will group by account, so the rule is documented here. It is also decision 3.

## 6. The number

- **Sequential mode.** A draft has no number (`invoice_no` is null) and the screen shows "Draft".
  The number is taken from `invoice_settings.next_invoice_no` when the invoice is approved, in the
  same transaction as the posting, with the row locked. A failed approval gives the number back, so
  the series has no gaps, the same way as the voucher numbers. Invoices and credit notes share the
  series (decision 1).
- **Manual mode.** The user types the number, in the draft or when approving (the body of the
  approval takes it). It has to be unique among the numbers of the organization. A number that is
  taken is refused with 409 when approving. A plain number moves `next_invoice_no` to the one after
  it, so the app can suggest it. The series is the user's responsibility, as it is now.
  In sequential mode a number that the client sends with a draft is ignored.
- The number is a text as today. An approved invoice keeps its number, and it cannot be changed.

The database change: the primary key of `invoices` becomes `id`, and `(organization_id, invoice_no)`
is a unique constraint (a null does not collide with another null). The lines already point at `id`.

## 7. Locking, and what the client can no longer set

- `PUT /organizations/<id>/invoices/<id>` and `DELETE` are refused with 409 for an approved invoice,
  and for a credit note. A draft can still be edited and deleted.
- `state`, `is_paid`, `kind` and the fields of the approval are no longer accepted from the client
  (422, as the totals already are). `is_paid` is removed: whether an invoice is paid follows from the
  payments (section 9).
- `is_sent` stays, and `PATCH .../mark-as-sent` is allowed for an approved invoice: it is a note about
  what the user did outside the program. (Sending by e-mail is phase 7.)
- An invoice response has `kind`, `voucher_no`, `approved_at`, `payment_status`, `open_amount` and
  `due` (below), and the list of its credit notes.
- The app hides Edit and Delete for an approved invoice, and offers Credit note instead.

## 8. Credit notes

A credit note is an invoice with `kind` `credit_note` and `credits_invoice_id`, the invoice it
corrects. It has lines, VAT codes, a date, a number and a state like any invoice.

- `POST /invoices/<id>/credit-note` makes a draft credit note from an approved invoice, with its
  lines copied. The user lowers or removes lines for a partial credit note, or adds a line, and
  approves it. A credit note always refers to an invoice of the program (decision 4).
- **The amounts on the document are positive** (a credit note of 1,000 + 250 VAT shows 1,000, 250
  and 1,250), as on a printed credit note, with the word "Kreditnota". The ledger has them as a
  debit on the sales account, the VAT on the other side (the engine does this with a negative base)
  and a credit on receivables. The app shows them with a minus in lists.
- The total credited on one invoice, in gross amount, cannot be more than the invoice. The check is
  made when a credit note is approved, on the approved credit notes of the invoice plus this one, so
  two drafts cannot each credit all of it.
- Approving it posts it the same way as an invoice, `source_type` `credit_note`. It cannot be dated
  in a settled VAT period, and not before the invoice it corrects.
- **It settles the invoice.** On approval the credit note is allocated to the invoice it credits, up
  to the invoice's open amount (section 9). If the customer has paid, the rest stays as credit for the
  customer. Paying it out is the refund of section 11.
- A credit note is never edited or deleted once approved, and there is no credit note of a credit
  note: a mistake is a new invoice.

**Reversing a voucher of a document.** An entry with the source type `invoice`, `credit_note`,
`payment` or `vat_settlement` cannot be reversed from the voucher screen or the journal API (409,
saying what to do instead): the document would not know. The invoice is corrected with a credit note,
a payment with its own reversal (section 9), and a settlement not at all (phase 2).

## 9. Payments and what is owed

Today an invoice is paid when someone sets a flag. A payment is an event of its own.

**`payments`**: `id`, `organization_id`, `contact_id`, `payment_date`, `amount` (above 0), `account_id`
(the bank account that is debited, by default the deposit account of the invoice settings),
`reference` (text, at most 100), `journal_entry_id`, `status` (`active` or `reversed`), who and when.

**`receivable_allocations`**: `id`, `organization_id`, a source that is a payment **or** a credit
note, `invoice_id`, `amount` (above 0). The database checks that exactly one source is set.

`POST /payments` with the contact, the date, the amount, the account and a list of allocations (an
invoice and an amount each). It posts one entry dated `payment_date`, `source_type` `payment`:

| Debit | Credit |
|---|---|
| the bank account: the amount | `receivables`: the amount, with the contact of the customer |

Rules, each refused with 422 or 409 and nothing written:

- every invoice in the allocations is approved, of the same contact as the payment and of the same
  organization, and not a credit note;
- an allocation is at most what is open on the invoice, and the allocations add up to at most the
  payment. The rest of the payment is **credit for the customer**: it stays on the receivable with
  the contact, and can be allocated later with `POST /payments/<id>/allocate`, or to a new invoice;
- a payment cannot be dated before the invoice date of what it pays, and cannot be in a closed
  fiscal year. It can be in a settled VAT period, because it touches no VAT line or VAT account.

`POST /payments/<id>/reverse` reverses the entry of the payment (the posting service does it) and sets
the payment to `reversed`. Its allocations then count for nothing, and the invoices are open again.
A reversed payment is not reversed twice.

**Open amount.** For an approved invoice: the gross amount, less the allocations from active payments
and from credit notes. `payment_status` is `unpaid` (nothing allocated), `partial` or `paid` (open
amount 0), and `due` says that it is past the due date and not `paid`. Nothing of this is stored on
the invoice: it follows from the allocations, so it cannot disagree with them.

**The receivables report**, `GET /reports/receivables`: for each contact, the open invoices (number,
dates, gross, allocated, open), the credit the customer has, and the total. The check against the
ledger: for each contact, the balance of the receivables account on the lines with that contact (debit
minus credit) must equal the total of the report. If it does not, the difference is shown with the
entries that have a receivable line without a contact. The report cannot be wrong without the books
being wrong.

**Reminders.** `reminders`: `invoice_id`, `level` (1 to 3), `reminder_date`, `fee`. A reminder can be
made for an invoice that is past its due date and not paid, at least 10 days after the one before. The
fee is at most 100 kr. and is zero by default (the setting `default_reminder_fee` is the starting
value). The fee has no VAT (section 3). Which account it is posted to (3490 or 1010) is still question
5 of the accountant's list, so in the first version a reminder is a record, and the fee is not
posted. Decision 6.

## 10. How it is tested

The invariants, as tests, in the style of phases 1 and 2:

- **An approved invoice and its entry agree.** For many random invoices (several codes, negative
  lines, zero lines): the receivable line is the gross amount of the invoice, each sales line is its
  line amount, and the VAT lines are the invoice's `vat_by_code`. The VAT report for the range
  gives the same figures as the invoices added up, and ties to the ledger.
- **Numbers have no gaps.** After many approvals, some refused for any reason (a closed year, a
  settled period, a missing account): the numbers of the approved invoices and credit notes are
  `1..n` with nothing missing. A refusal leaves nothing behind: no number, no voucher number, no
  audit row.
- **Locked means locked.** Every route that can change an invoice (`PUT`, `DELETE`, the line routes,
  the status fields) refuses an approved invoice, and the invoice is the same after the attempt.
- **A credit note undoes an invoice.** Invoice and full credit note: the receivable is zero, every
  sales account and VAT account is zero, and the VAT report of the period shows zero. A partial
  credit note leaves the right part.
- **Receivables tie out.** After random invoices, credit notes, partial payments, overpayments and
  reversals of payments: for every contact, the open amounts of the report equal the balance of the
  receivables account for that contact, and the trial balance is balanced.
- **A reversed payment sets everything back:** the open amounts, the bank account and the report.
- **A voucher of a document cannot be reversed from the journal.**
- **An organization that is not VAT-registered:** an invoice with `S01` is refused on save and on
  approval, and one with `S81` is approved and posted with no VAT code and no VAT line.
- **The invoice date decides the period:** an invoice dated in a settled VAT period is refused, one
  dated after it is posted, and its VAT lands in that period's report.
- **Two approvals at once** (two connections): different numbers, no gap, one entry each; and two
  approvals of the same invoice: one succeeds and the other gets 409.

## 11. Left out on purpose

- **Refunding a credit balance** (a payment out, allocated to a credit note), **write-offs** and
  small differences (a customer pays 1,249.95 against 1,250). A write-off of a bad debt also has VAT
  rules of its own. They are the next step after the first version, and need the accountant.
- **Interest on late payment** (the lending rate plus 8 points) and the fixed compensation of 310 kr.
  for collection costs. The fee of a reminder is handled in decision 6; interest and compensation are
  separate calculations and postings, and neither carries VAT.
- **E-mailing invoices, e-invoicing (OIOUBL, Peppol)** and the EU sales list: phase 7. The contacts
  have no VAT number yet, which the EU list and the EU codes need.
- **The invoice template against the requirements of § 58** (section 3 has the list): the date of
  supply when it differs from the invoice date, the names and addresses of both parties, the unit
  price without VAT, and the buyer's VAT number for EU sales. The invoice has no date of supply
  today, and the VAT period of a late invoice depends on it (`momsloven` § 23).
- **The setting `lines_incl_vat`.** The server treats every price as excluding VAT, and the setting
  does nothing. It is removed from the screen or built, in a later step.
- **Other currencies.** Approving an invoice that is not in DKK is refused.
- **Cash-basis VAT** and **recurring invoices**, **quotes**: later, if ever.
- **An aging report** (30, 60, 90 days), which is the receivables report grouped by how late each
  invoice is.

## 12. Decisions to confirm

Each has my recommendation. On 2026-11-01 the answer was "there are no real invoices in any
database, production included, so do whatever is easy; the system is only for Denmark". That settles
decision 2 and takes the others as recommended, except where checking the official rules (section 3)
changed the recommendation, which is said under the decision.

1. **Numbers.** Take the number when the invoice is approved, so a deleted draft leaves no gap, with
   invoices and credit notes in one series (recommended). The alternative is to keep taking it when the
   draft is created, which is simpler but leaves gaps that an auditor asks about, or a series per
   kind (`K-1001`), which the rules allow.
2. **Invoices that exist.** The migration puts every invoice that is not a draft back to draft, so
   it can be approved and posted, and drops `is_paid` (recommended: nothing is live, and a backfill of
   postings for test data is not worth it). The alternative is a backfill that posts them with an
   opening balance, as the plan sketched. **Decided:** back to draft.
3. **The sales account of a line.** The product's account, then the account with the role of the
   VAT code, then the default of the settings (recommended), or the role of the code first, which
   makes the VAT code decide and ignores what the user chose on the product.
4. **Credit notes.** An invoice of its own kind that refers to the invoice it corrects, partial
   credit notes allowed, the total credited at most the invoice, and always an invoice of the program
   to refer to (recommended). A credit note for an invoice from before the program was used is not
   possible, for the same reason as the backfill of decision 2. The official guidance does not
   demand the reference, only that the document "specifically and unambiguously" changes the
   invoice, so this is the safe way, and not a legal requirement.
5. **Payments.** Allocated by hand to named invoices, partial payments allowed, an overpayment kept
   as credit for the customer, no write-offs and no small-difference account in the first version
   (recommended). The alternative is to allow a small difference (say up to 1 kr.) to go to the
   rounding account `2720`.
6. **Reminders.** Records first, with the fee not posted until the accountant has answered
   question 5, and no interest (recommended). The alternative is to post the fee now on `3490`
   (without VAT, which section 3 confirms), the account being my guess and not the accountant's
   answer.
7. **The date of an invoice.** Not in the future, and otherwise free apart from the two automatic
   rules (a closed fiscal year and a settled VAT period) (recommended). The alternative is also to
   refuse a date earlier than the latest approved invoice, so that the numbers follow the dates, which
   auditors like and which makes it harder to enter a forgotten invoice (it can still be done in
   manual mode).
8. **Where the receivable of a customer is kept.** All on 6190 `Tilgodehavender` with the contact on
   each line (recommended: the chart stays small, and the report is the sub-ledger). The alternative
   is an account per customer, which fills the chart.
9. **EU codes and the country of the contact.** The screen warns when `S21`, `S22` or `S23` is used
   for a contact outside the EU, or `S01` for one inside it, and the server does not refuse
   (recommended, until the contacts have VAT numbers in phase 7).
10. **Currency.** DKK only: approving an invoice in another currency is refused (recommended).
    **Decided:** the system is for Denmark only.
11. **An organization that is not VAT-registered** invoices with `S81` and no VAT, and its invoices
    are posted without VAT codes (section 4). New with the rules check; recommended because the law
    forbids showing VAT on its invoices.

## 13. The PRs of phase 3

Each is a branch, with tests, and each is merged before the next.

| # | Repo | What | Needs |
|---|---|---|---|
| 1 | api | Approve and lock: the number at approval, the posting of an invoice, the primary key change, `journal_entry_id` and the approval fields, the client no longer sets `state` or `is_paid`, reversal of documents refused, the migration of existing invoices (back to draft), invoices of an organization that is not VAT-registered (`S81` only, posted without VAT codes) | decisions 1, 2, 3, 7, 8, 10, 11 |
| 2 | app | The approve flow: Approve button, "Draft" instead of a number, read-only approved invoices, the voucher of an invoice, `is_paid` gone, and `S81` preselected (and the choice hidden) for an organization that is not VAT-registered | PR 1 |
| 3 | api | Credit notes: the kind, the reference, create from an invoice, approve, the check of the total, settling the invoice | PR 1 and decision 4 |
| 4 | app | Credit notes: create from an invoice, edit as a draft, approve, show on the invoice | PR 3 |
| 5 | api | Payments and allocations, open amounts and `payment_status`, reversal of a payment, the receivables report with the check against the ledger | PR 3 and decision 5 |
| 6 | app | Register a payment (with allocation), the payments list, status and open amount on the invoices, the receivables screen | PR 5 |
| 7 | api and app | Reminders as records, and their screen | PR 5 and decision 6 |

PR 1 is the large one, and carries the risk. If it is too large to review, it splits in two: the
number and the lock first, then the posting.

The app PRs use the same rules as the server where they show amounts, and the invoice screens of
phase 2 as they are.
