# Chart of accounts (draft for an accountant)

The proposed chart of accounts and system accounts for the ledger (phase 1 of the
[accounting plan](accounting-plan.md)). This is a document first: nothing here is in the code yet,
and an accountant has answered only part of it (see "Accountant's note" below).

## Status and what is verified

- The numbers below are from Erhvervsstyrelsen's **fællesoffentlige standardkontoplan, version
  2026-01-01**, published as JSON in the
  [standard-filformater repository](https://git.erst.dk/standard-filformater/standard-filformater)
  (`Standardkontoplanen/JSON/2026-01-01-Standardkontoplan.json` and
  `2026-01-01-Momskoder-Bruttoliste.json`). Erhvervsstyrelsen
  [published a corrected version in February 2026](https://erhvervsstyrelsen.dk/saf-t-version-2-og-rettelser-til-standardkontoplanen)
  after critical errors were found in the first one.
- **Every account number and name and every VAT code below was checked against the files**
  downloaded from the repository's `master` branch on 2026-10-25 (so after the correction):
  `Standardkontoplan.json` is 127,283 bytes, SHA-256 `ad5b9ba7...6f55f97`, 603 accounts plus a list
  of sum accounts; `Momskoder-Bruttoliste.json` is 83,640 bytes, SHA-256 `2c6e4277...24e90d9`, valid
  from 2025-12-01, 72 codes. The files are in the repo, in `app/seed/standard/` (with their source
  and hashes), and a test checks that the tables below agree with them.
- The standard is **not mandatory**: a company can use its own chart if each account is mapped to a
  standard account, and the standard chart can also be built straight into the system
  ([Erhvervsstyrelsen](https://erhvervsstyrelsen.dk/standardkontoplan-saf-t)). As I understand it,
  the SAF-T export (phase 7) refers to each account's standard account; confirm that when phase 7
  is built.

## Proposal

1. **Use the official account numbers and names directly** for the accounts we create. Then the
   standard account of an account is its own number, and the SAF-T mapping needs no work.
2. **Every account has a `standard_account` field anyway**, so an organization can add its own
   accounts (for example a project account) and map them to a standard one.
3. **Start with a small chart** (below), not the whole standard. An organization adds accounts
   from the standard when it needs them.
4. **The posting service finds accounts by role** (`receivables`, `output_vat`, ...), never by
   number, so an organization can renumber or replace an account without touching code.

The standard's numbering: 1000-3810 is the income statement (revenue 1001-1550, external costs
1595-2810, personnel 2841-2947, depreciation 2991-3099, financial items 3191-3690, tax 3703-3810),
5001-6462 is assets, and 6500 and up is equity and liabilities. The file has headings (`hovedkonto`)
and groups with sub-accounts (`gruppekonto`). It has no field that says which entries can be posted
to, so the seed has to decide that per account.

## Starter chart

"Role" is the system account the posting service uses. "VAT" is the default VAT code for postings
to the account (the official code list is covered below).

### Income statement

| No. | Name (as in the standard) | Role | VAT |
|---|---|---|---|
| 1010 | Salg af varer og ydelser | `sales` (the default for an invoice line) | S1 |
| 1050 | Salg af varer udland, EU | `sales_eu_goods` | S2 |
| 1100 | Salg af varer udland, ikke-EU | `sales_non_eu_goods` | S4 |
| 1150 | Salg af ydelser udland, EU | `sales_eu_services` | S3 |
| 1200 | Salg af ydelser udland, ikke-EU | `sales_non_eu_services` | S5 |
| 1210 | Salgsrabatter | | S1 |
| 1250 | Salgsfragt | | S1 |
| 1610 | Varekøb | `purchases` (the default for a bill line) | K1 |
| 1630 | Varekøb udland, EU | | K-EU-V-1 |
| 1650 | Varekøb udland, ikke-EU | | K-%EU-V-1 |
| 1710 | Ydelseskøb udland, EU | | K-EU-Y-1 |
| 1760 | Fragtomkostninger | | K1 |
| 2720 | Øreafrunding/kassedifferencer | `rounding` (small differences, for example when matching bank payments in phase 5) | none |
| 3470 | Renter fra banker | | none |
| 3490 | Renter vedr. tilgodehavende fra salg af varer og tjenesteydelser | | none (interest charged to customers; see question 5) |
| 3650 | Renter vedr. leverandører af varer og tjenesteydelser | | none |
| 3670 | Renter til banker og realkreditinstitutter | | none |
| 3675 | Renter til det offentlige (ej fradragsberettiget skattemæssigt) | | none |

The common expense accounts (all detail accounts, with no sub-accounts, in the standard):

| No. | Name (as in the standard) | VAT |
|---|---|---|
| 1850 | Annoncering og reklame | K1 |
| 1910 | Repræsentationsomkostninger, skattemæssigt begrænset fradrag | K25A |
| 1930 | Repræsentationsomkostninger, fuld fradragsret skattemæssigt | K1 |
| 2030 | Husleje | none |
| 2230 | Småanskaffelser under skattemæssig grænse for småaktiver | K1 |
| 2310 | It-udstyr (hardware, software inkl. licenser og abonnementer) | K1 |
| 2370 | Kontingenter | K1 |
| 2390 | Porto og gebyrer | K0 (the note says postage and bank fees are exempt; check parcels) |
| 2410 | Telefon og internet mv. (kun virksomhed) | K1 |
| 2450 | Kontorartikler | K1 |
| 2470 | Rejseomkostninger (administrationsomkostning) | K0 for train and flight tickets (exempt, per the note), K1 for the rest; check |
| 2540 | Driftsomkostninger, personbiler | check |
| 2650 | Øvrige forsikringer | none |
| 2660 | Offentlige gebyrer og bøder (ej fradragsberettiget skattemæssigt) | none |
| 2670 | Revision og regnskabsmæssig assistance | K1 |
| 2895 | Skattefri rejse- og befordringsgodtgørelse | none (the closest to the seed's "Kørselsgodtgørelse"; check) |
| 2896 | Kursusudgifter | K1 |

The default VAT code per expense account is my guess at the usual treatment: the file has no such
default. In the database it is the column `accounts.default_vat_code_id`, set by the starter chart
with the new names of the codes (`S1` is `S01`, `K1` is `K010`, `K25A` is `K070`, `K-EU-V-1` is
`K210`), and only for the 22 accounts whose code is a supported one. 1650 has no default because
`K-%EU-V-1` (`K410`) is import VAT, which phase 2 does not calculate, and 2470 and 2540 have none
until they are checked. Check it with the accountant (rent and insurance are normally without VAT, cars are
limited). Accounts whose names end in "kun klasse A" exist for sole proprietorships and are marked
below.

### Balance sheet

| No. | Name (as in the standard) | Role | Note |
|---|---|---|---|
| 6190 | Tilgodehavender fra salg og tjenesteydelser | `receivables` | Customers' open invoices (debitorer) |
| 6320 | Tilgodehavende moms (omsætningsaktiv) | `vat_receivable` | When input VAT exceeds output VAT in a period |
| 6481 | Skattekonto | `tax_account` | Our own account, not in the standard. Mapped to 6330 Øvrige tilgodehavender (omsætningsaktiv). See the accountant's note. |
| 6480 | Bankkonto | `bank` | One account per bank account; the role marks the default. Payments and bank import post here. |
| 7440 | Leverandører af varer og tjenesteydelser (kortfristet) | `payables` | 7450 is the sum account for the group, not for posting |
| 7680 | Salgsmoms | `output_vat` | |
| 7700 | Moms af varekøb udland, EU og ikke-EU | `vat_eu_goods` | VAT on goods acquired abroad (reverse charge) |
| 7720 | Moms af ydelseskøb udland, EU og ikke-EU | `vat_eu_services` | VAT on services bought abroad (reverse charge) |
| 7740 | Købsmoms | `input_vat` | |
| 7840 | Skyldig moms | `vat_payable` | What is owed for the settled period |

### Equity depends on the company form

The owner's businesses are sole proprietorships (enkeltmandsvirksomhed), and the system must also
handle an ApS. So an organization has a **company form** (`enkeltmandsvirksomhed` or `aps`) that decides
which equity accounts are created and how the year is closed (phase 6). The standard has accounts
for both: those marked "kun klasse A" are the ones for personally owned businesses. I take class A
to mean sole proprietorships; confirm that with the accountant.

| Role | Sole proprietorship | ApS |
|---|---|---|
| Capital | 6915 Egenkapital primo (kun klasse A) | 6510 Registreret kapital mv. (and 6520 when paid in) |
| Owner's withdrawals | `owner_withdrawals`: 6923 Privat hævet | not used: dividends go to 6956 Udloddet udbytte |
| Owner's deposits | `owner_deposits`: 6924 Privat indskud | not used: a capital increase goes to 6510 |
| Result for the year | `annual_result`: 6916 Årets resultat | `retained_earnings`: 6940 Overført resultat, jf. resultatdisponering (with 6935 as the opening balance) |
| Private share of costs | 6920 Private andele, 6921 Private afskrivninger, 6922 Driftsudgifter uden fradrag | not used |

An ApS also has a corporate tax payable and a proposed dividend (6960 Foreslået udbytte jf.
resultatdisponeringen). Neither is in the starter chart yet: they come with year-end in phase 6.
The same goes for how a sole proprietorship closes its result and withdrawals at year end.

## System accounts and the posting rules

The posting service needs these roles to exist for every organization: `receivables`, `payables`,
`sales`, `purchases`, `output_vat`, `input_vat`, `vat_payable`, `vat_receivable`, `tax_account`,
`bank` and `rounding`. The equity roles in the table above depend on the company form. A role maps to
exactly one account per organization, and an account that holds a role cannot be deleted. The VAT
roles are first used in phase 2.

All the examples use 25% VAT. "Dr" is debit and "Cr" is credit.

| Event | Dr | Cr |
|---|---|---|
| Approve an invoice, 1,000 + 250 VAT | 6190 Tilgodehavender 1,250 | 1010 Salg 1,000; 7680 Salgsmoms 250 |
| Customer pays 1,250 | 6480 Bankkonto 1,250 | 6190 Tilgodehavender 1,250 |
| Credit note, 1,000 + 250 VAT | 1010 Salg 1,000; 7680 Salgsmoms 250 | 6190 Tilgodehavender 1,250 |
| Bill from a supplier, 800 + 200 VAT | an expense account 800; 7740 Købsmoms 200 | 7440 Leverandører 1,000 |
| Pay the supplier 1,000 | 7440 Leverandører 1,000 | 6480 Bankkonto 1,000 |
| EU goods bought for 800, fully deductible (reverse charge) | 1630 Varekøb udland, EU 800; 7740 Købsmoms 200 | 7440 Leverandører 800; 7700 Moms af varekøb udland 200 |
| VAT settlement for the period (sales 250, purchases 200) | 7680 Salgsmoms 250 | 7740 Købsmoms 200; 7840 Skyldig moms 50 |
| Pay the VAT (50) to SKAT | 6481 Skattekonto 50 | 6480 Bankkonto 50 |
| SKAT settles the VAT against the Skattekonto | 7840 Skyldig moms 50 | 6481 Skattekonto 50 |

If input VAT is higher than output VAT, the settlement difference goes to 6320 Tilgodehavende moms
instead of 7840. The standard chart has no account for VAT settlement itself, which is why the
settlement above is posted through the two VAT accounts and 7840. The payment goes through the
Skattekonto, not straight against 7840, because SKAT covers the oldest claim first (see the note).

An invoice never needs the rounding account: the money rules make its lines add up exactly to its
totals ([money-rules.md](money-rules.md)).

## VAT codes

The plan's phase 2 lists Dinero's VAT codes (`U25`, `I25`, ...). We should use Erhvervsstyrelsen's
official list instead, which goes with the standard chart: `Momskoder-Bruttoliste` (72 codes, 23 for
sales and 49 for purchases, valid from 2025-12-01). Each code has two names, an old one (`S1`, `K1`)
and a new one (`S01`, `K010`) with a long name such as `S_DK_25`. Which one is the code the SAF-T
file uses is a question for phase 7. The first column is the old code, with the new one in brackets.

| Code | Meaning | Rate | Deduction | Where it goes on the return (the file's `momsangivelse`) |
|---|---|---|---|---|
| S1 (S01) | Taxable sales in Denmark | 25% | | Salgsmoms (udgående moms) |
| S0 (S02) | Taxable sales in Denmark at 0% | 0% | | Rubrik C, for example domestic reverse charge or sales to ships in foreign traffic |
| S2 (S21) | Goods to an EU business | 0% | | Rubrik B - varer (and the EU sales list) |
| S3 (S23) | Services to an EU business | 0% | | Rubrik B - ydelser |
| S4 (S41), S5 (S42) | Goods, services to a business outside the EU | 0% | | Rubrik C - eksport udenfor EU |
| K1 (K010) | Input VAT, full deduction | 25% | 100% | Købsmoms (indgående moms) |
| K0 (K030) | Purchase without deduction | | 0% | not on the return |
| K25A (K070) | Representation, limited deduction | 25% | 25% | Købsmoms (indgående moms) |
| K-EU-V-1 (K210) | Goods from the EU, full deduction | 25% | 100% | Rubrik A - varer, plus moms af varekøb i udlandet (7700) and købsmoms |
| K-EU-Y-1 (K260) | Services from the EU, full deduction | 25% | 100% | Rubrik A - ydelser, plus moms af ydelseskøb i udlandet (7720) and købsmoms |
| K-%EU-V-1 (K410) | Goods from outside the EU, full deduction | 25% | 100% | Moms af varekøb i udlandet, plus købsmoms (no box A) |
| K-%EU-Y-1 (K460) | Services from outside the EU, full deduction | 25% | 100% | Moms af ydelseskøb i udlandet, plus købsmoms |

The file also has the codes for partial and estimated deduction (`K2`, `K3`), cars, used goods,
margin schemes, domestic reverse charge (`K-DK...`) and OSS online sales. The list says which
posting accounts each code uses in words, not as account numbers, so the code to account mapping
for the VAT report is ours to define and to check with the accountant. The box layout of the
current return still has to be checked on skat.dk before the VAT report is built.

## Changes the ledger needs in the current code

- The seed charts (`app/seed/orgs/demo.json`, `tolk-wb.json`) use an older numbering: 1110 Salg,
  1210 Vareindkøb, 5710 Bank, 7200 Skyldig moms, and others. Several of those numbers mean
  something else in the standard (1100 is "Salg af varer udland, ikke-EU"). Nothing is live, so
  the seed is replaced, not migrated.
- `accounts` has a composite primary key of `(organization_id, name, number)`, so renaming an
  account changes its key. Journal lines need a stable key: they should reference `accounts.id`,
  with a unique `(organization_id, number)` and the name as an ordinary column.
- `accounts.tax_rate_id` pointed at one tax rate. VAT moved to VAT codes on the posting and the
  invoice line (phase 2), and `tax_rates` and that column are gone: `accounts.default_vat_code_id`
  is the suggestion that replaces it.
- New columns on `accounts`: `standard_account` and `system_role` (unique per organization). New
  column `company_form` on the organization (`enkeltmandsvirksomhed` or `aps`).
- The account groups with number intervals in the seed are replaced by the standard's own
  headings.

## Accountant's note (received 2026-10-25)

A note on year-end for sole proprietorships, VAT settlement and the Skattekonto
(`regnskabsnotat_moms_og_aarsafslutning.md`; it names no author beyond "Dansk Revisor /
Regnskabskonsulent"). The first versions used account numbers that are not in the official chart
(for example 6410, 57130 and 2010). **The current version uses the official numbers: I checked every
account in it against the file, and they exist with the names the note gives.** The advice is used
as given:

- **Year-end of a sole proprietorship.** All accounts of the income statement (1000-3810) are closed
  and the result goes straight to equity on 6916 Årets resultat (kun klasse A). The standard's
  4999 "Årets resultat" is a sum account, not one to post to. Equity from earlier years is 6915
  Egenkapital primo. Private withdrawals, and B-skat paid privately, are posted during the year on
  6923 Privat hævet and closed against 6915 at year end, so they start at 0 in the new year. The
  same goes for deposits on 6924 Privat indskud. The company pays no company tax (the 37xx accounts
  such as 3740 are for companies). The result goes on the owner's tax return. **B-skat is never an
  expense of the business.**
- **VAT settlement** moves the whole balance of the sales VAT (7680), input VAT (7740) and
  acquisition VAT (7700, 7720) accounts to 7840 Skyldig moms at the end of the VAT period, which
  freezes the period (see the posting examples above).
- **A Skattekonto account is needed**, and the standard has none. The VAT payment goes from the bank
  (6480) to the Skattekonto, and SKAT then draws the VAT from it, oldest claim first. Posting the
  payment straight against the VAT debt would leave the books different from skat.dk when SKAT has
  covered a reminder fee or interest first. The note's own account is **6481 Skattekonto**, next to
  the bank. We map it to 6330 Øvrige tilgodehavender (omsætningsaktiv) in `standard_account`: a
  credit balance with SKAT is a receivable, and a debt stays on 7840. Interest and fees from SKAT go
  to 3675, which is not deductible.
- **EU purchases.** Services from the EU are posted on 1710 Ydelseskøb udland, EU, with the VAT on
  7740 and 7720. Goods from the EU are posted on 1630 Varekøb udland, EU, with the VAT on 7740 and
  7700. This agrees with the posting examples above.
- **Exempt purchases** (no VAT, `K0`): bank fees and postage (2390 Porto og gebyrer), insurance
  (2650) and, in the earlier versions, passenger transport (train and flight tickets) and medical
  care.

The VAT code names in the note (`UBL`, `IVY`, `IVV`, "Momsfrit") are not the official ones. The
official codes are `K1`, `K-EU-Y-1` (services from the EU), `K-EU-V-1` (goods from the EU) and `K0`.
In Dinero's list `IVY` and `IVV` are purchases from outside the EU and `UBL` is not in it, so those
names are not used. Their meaning (a domestic purchase at 25%, EU services and goods at 0% with 25%
acquisition VAT reported in box A, exempt purchases) is the same as the official codes.

## Still open for the accountant

1. Is this starter chart enough for each business, and which expense accounts and default VAT
   codes are missing or wrong? (The default VAT codes on the expense accounts are my guess, except
   for the exempt ones in the note.)
2. Sole proprietorship: the note treats the "kun klasse A" accounts as the ones for sole
   proprietorships: please confirm. It puts private cash withdrawals and B-skat on 6923. Where does
   the private share of mixed costs (telephone, car) go: on 6923 too, or on 6920-6922?
3. Mapping the Skattekonto, our own 6481, to 6330 rather than to the bank account 6480: acceptable?
4. Reverse charge on EU purchases (7700, 7720 with 7740): are these the right accounts and signs?
5. Where do reminder fees and interest charged to customers go (3490 or 1010)? Is there VAT on
   them?
6. ApS: do 6935 and 6940 work as described for the opening balance and the year-end closing, and
   how are the company tax and the proposed dividend posted?
7. Is the rounding rule (per line, then VAT on the net total) the one you want?

## In the code

`app/chart.py` holds the starter chart as a list of account numbers, types and roles. Names and
standard accounts come from the official file, and the code never writes a number or name by hand
for an account of the standard. `flask chart-apply <slug>` gives an organization the accounts of its
company form; `flask seed` does it for the demo organizations. Running it again changes nothing: an
account with the number is kept, and gets its standard account and role if it has none.

VAT codes on the accounts (the defaults in the tables above) are not seeded yet: they come with the
VAT codes in phase 2.
