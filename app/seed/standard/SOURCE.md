# Official standard files

Unchanged copies of two files published by Erhvervsstyrelsen (the Danish Business Authority) in the
repository <https://git.erst.dk/standard-filformater/standard-filformater>, folder
`Standardkontoplanen/JSON/`, downloaded from the `master` branch on 2026-10-25. They are the
reference for the chart of accounts and the VAT codes (see `docs/chart-of-accounts.md`). Do not edit
them: `tests/unit/test_standard_chart.py` checks the hashes.

| File | Valid from | Bytes | SHA-256 |
|---|---|---|---|
| `2026-01-01-Standardkontoplan.json` | 2026-01-01 | 127283 | `ad5b9ba73856c29e5d4a81e2a89751efce86c5d69fa705f693a79204d6f55f97` |
| `2026-01-01-Momskoder-Bruttoliste.json` | 2025-12-01 | 83640 | `2c6e42779ab5fa60e32d2c6e27ddc643dda038216154f1cb764580f1924e90d9` |

The chart was reissued in February 2026 after errors were found in the first version, and the
download is from after that.

## When a new version is published

Add the new file next to the old one (a new date in the name), point `app/standard_chart.py` at it,
and write a migration for what changes for existing organizations. Never overwrite a file: posted
entries refer to the accounts of the version that was valid when they were made.
