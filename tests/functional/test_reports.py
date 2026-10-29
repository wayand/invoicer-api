"""The account ledger and the trial balance (app/reports.py): worked
examples with known numbers, and a check of every figure against a plain
sum of the lines posted."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.chart import apply_starter_chart
from app.ledger import LineInput, post_entry, reverse_entry
from app.models.account import Account
from app.models.base import db
from app.models.organization import Organization
from app.models.user import User

D = Decimal


def money(value) -> Decimal:
    """A JSON number from the API as the exact amount it stands for."""
    return D(str(value))


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def books(db_session, organization, test_user):
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    return {
        "org": organization,
        "user": test_user,
        "headers": headers(test_user),
        "accounts": accounts,
        "bank": accounts[6480],
        "sales": accounts[1010],
        "vat": accounts[7680],
        "expense": accounts[2450],
    }


def post(books, day, debits, credits, description="Entry"):
    """debits and credits are lists of (account, amount)."""
    lines = [
        LineInput(account_id=account.id, debit=D(amount))
        for account, amount in debits
    ] + [
        LineInput(account_id=account.id, credit=D(amount))
        for account, amount in credits
    ]
    return post_entry(
        books["org"].id, books["user"].id, day, description, lines
    )


@pytest.fixture
def worked(db_session, books):
    """Four entries over two fiscal years, and a reversal of the second."""
    b = books
    first = post(
        b,
        date(2026, 1, 10),
        [(b["bank"], "125")],
        [(b["sales"], "100"), (b["vat"], "25")],
        "Sale 1",
    )
    second = post(
        b,
        date(2026, 2, 15),
        [(b["bank"], "250")],
        [(b["sales"], "200"), (b["vat"], "50")],
        "Sale 2",
    )
    third = post(
        b,
        date(2026, 2, 15),
        [(b["expense"], "40")],
        [(b["bank"], "40")],
        "Paper",
    )
    fourth = post(
        b,
        date(2027, 1, 5),
        [(b["bank"], "62.50")],
        [(b["sales"], "50"), (b["vat"], "12.50")],
        "Sale 3",
    )
    reversal = reverse_entry(
        b["org"].id, b["user"].id, second.id, entry_date=date(2026, 3, 1)
    )
    db_session.commit()
    return [first, second, third, fourth, reversal]


def ledger(client, books, account, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(
        f"/reports/account-ledger?account_id={account.id}&{query}",
        headers=books["headers"],
    )


def trial(client, books, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(
        f"/reports/trial-balance?{query}", headers=books["headers"]
    )


def balances(report):
    return {
        item["number"]: money(item["closing_balance"])
        for item in report["accounts"]
    }


# --- the account ledger ----------------------------------------------------


def test_the_ledger_lists_every_posting_with_a_running_balance(
    client, books, worked
):
    res = ledger(client, books, books["bank"])

    assert res.status_code == 200, res.get_json()
    report = res.get_json()
    assert report["account"] == {
        "id": books["bank"].id,
        "number": 6480,
        "name": "Bankkonto",
        "normal_balance": "debit",
    }
    # by date, then voucher number: the reversal (March) comes before the
    # sale in 2027
    assert [
        (
            row["voucher_no"],
            row["entry_date"],
            row["debit"],
            row["credit"],
            row["balance"],
        )
        for row in report["rows"]
    ] == [
        (1, "2026-01-10", 125.0, 0.0, 125.0),
        (2, "2026-02-15", 250.0, 0.0, 375.0),
        (3, "2026-02-15", 0.0, 40.0, 335.0),
        (5, "2026-03-01", 0.0, 250.0, 85.0),
        (4, "2027-01-05", 62.5, 0.0, 147.5),
    ]
    assert report["opening_balance"] == 0.0
    assert report["total_debit"] == 437.5
    assert report["total_credit"] == 290.0
    assert report["closing_balance"] == 147.5
    assert report["rows"][0]["description"] == "Sale 1"


def test_the_ledger_of_a_credit_account_has_negative_balances(
    client, books, worked
):
    report = ledger(client, books, books["sales"]).get_json()

    assert report["account"]["normal_balance"] == "credit"
    assert [row["balance"] for row in report["rows"]] == [
        -100.0,
        -300.0,
        -100.0,
        -150.0,
    ]
    assert report["closing_balance"] == -150.0


def test_a_range_starts_with_the_balance_carried_in(client, books, worked):
    report = ledger(
        client,
        books,
        books["bank"],
        **{"from": "2026-02-16", "to": "2026-12-31"},
    ).get_json()

    assert report["opening_balance"] == 335.0  # 125 + 250 - 40
    assert [row["voucher_no"] for row in report["rows"]] == [5]
    assert report["closing_balance"] == 85.0
    assert report["from"] == "2026-02-16"
    assert report["to"] == "2026-12-31"


def test_the_dates_of_a_range_are_included(client, books, worked):
    report = ledger(
        client,
        books,
        books["bank"],
        **{"from": "2026-02-15", "to": "2026-02-15"},
    ).get_json()

    assert [row["voucher_no"] for row in report["rows"]] == [2, 3]
    assert report["opening_balance"] == 125.0
    assert report["closing_balance"] == 335.0


def test_a_range_with_no_postings_keeps_the_balance(client, books, worked):
    after = ledger(
        client, books, books["bank"], **{"from": "2028-01-01"}
    ).get_json()
    before = ledger(
        client, books, books["bank"], **{"to": "2025-12-31"}
    ).get_json()

    assert after["rows"] == [] and before["rows"] == []
    assert after["opening_balance"] == after["closing_balance"] == 147.5
    assert before["opening_balance"] == before["closing_balance"] == 0.0


def test_an_account_without_postings_has_an_empty_ledger(client, books, worked):
    report = ledger(client, books, books["accounts"][2410]).get_json()

    assert report["rows"] == []
    assert report["closing_balance"] == 0.0


def test_the_ledger_crosses_fiscal_years(client, books, worked):
    report = ledger(
        client, books, books["bank"], **{"from": "2027-01-01"}
    ).get_json()

    assert report["opening_balance"] == 85.0  # everything of 2026
    assert [row["voucher_no"] for row in report["rows"]] == [4]


def test_a_reversal_nets_a_posting_out_of_the_ledger(client, books, worked):
    report = ledger(
        client, books, books["vat"], **{"to": "2026-12-31"}
    ).get_json()

    # 25 + 50 credited, 50 debited by the reversal
    assert report["closing_balance"] == -25.0


def test_the_ledger_shows_the_description_of_a_line(client, books):
    post_entry(
        books["org"].id,
        books["user"].id,
        date(2026, 1, 2),
        "Sale",
        [
            LineInput(
                account_id=books["bank"].id, debit=D("10"), description="Cash"
            ),
            LineInput(account_id=books["sales"].id, credit=D("10")),
        ],
    )

    rows = ledger(client, books, books["bank"]).get_json()["rows"]

    assert rows[0]["line_description"] == "Cash"
    assert rows[0]["description"] == "Sale"


# --- the trial balance -----------------------------------------------------


def test_the_trial_balance_lists_the_accounts_with_postings(
    client, books, worked
):
    res = trial(client, books)

    assert res.status_code == 200, res.get_json()
    report = res.get_json()
    assert [item["number"] for item in report["accounts"]] == [
        1010,
        2450,
        6480,
        7680,
    ]
    assert balances(report) == {
        1010: D("-150.00"),
        2450: D("40.00"),
        6480: D("147.50"),
        7680: D("-37.50"),
    }
    bank = report["accounts"][2]
    assert (
        bank["account_type"],
        bank["normal_balance"],
        bank["report_type"],
    ) == (
        "Asset",
        "debit",
        "balanceSheet",
    )
    assert (bank["opening_balance"], bank["debit"], bank["credit"]) == (
        0.0,
        437.5,
        290.0,
    )


def test_the_trial_balance_nets_to_zero(client, books, worked):
    report = trial(client, books).get_json()

    assert report["balanced"] is True
    assert report["total_closing_balance"] == 0.0
    assert report["total_opening_balance"] == 0.0
    assert report["total_debit"] == report["total_credit"]


def test_a_range_splits_the_balance_into_opening_and_movements(
    client, books, worked
):
    report = trial(
        client, books, **{"from": "2026-02-16", "to": "2026-12-31"}
    ).get_json()

    by_number = {item["number"]: item for item in report["accounts"]}
    bank = by_number[6480]
    assert (
        bank["opening_balance"],
        bank["debit"],
        bank["credit"],
        bank["closing_balance"],
    ) == (
        335.0,
        0.0,
        250.0,
        85.0,
    )
    # the sale of 2027 is after the range: not there
    assert by_number[1010]["opening_balance"] == -300.0
    assert report["balanced"] is True
    assert report["total_opening_balance"] == 0.0


def test_an_account_that_is_not_posted_to_until_later_is_not_listed(
    client, books, worked
):
    report = trial(client, books, **{"to": "2026-01-31"}).get_json()

    assert [item["number"] for item in report["accounts"]] == [1010, 6480, 7680]
    assert balances(report) == {1010: D("-100"), 6480: D("125"), 7680: D("-25")}


def test_an_account_posted_to_before_the_range_is_listed_with_its_opening_balance(
    client, books, worked
):
    report = trial(client, books, **{"from": "2027-01-01"}).get_json()

    expense = next(
        item for item in report["accounts"] if item["number"] == 2450
    )
    assert expense["opening_balance"] == 40.0
    assert (expense["debit"], expense["credit"]) == (0.0, 0.0)


def test_a_fully_reversed_account_is_listed_with_a_zero_balance(client, books):
    entry = post(
        books,
        date(2026, 5, 1),
        [(books["expense"], "10")],
        [(books["bank"], "10")],
    )
    reverse_entry(
        books["org"].id, books["user"].id, entry.id, entry_date=date(2026, 5, 2)
    )

    report = trial(client, books).get_json()

    assert balances(report) == {2450: D("0"), 6480: D("0")}
    assert report["balanced"] is True


def test_empty_books_have_an_empty_balanced_trial_balance(client, books):
    report = trial(client, books).get_json()

    assert report["accounts"] == []
    assert report["balanced"] is True
    assert report["total_closing_balance"] == 0.0


def test_the_ledger_and_the_trial_balance_agree(client, books, worked):
    report = trial(client, books).get_json()

    for item in report["accounts"]:
        account = db.session.get(Account, item["account_id"])
        closing = ledger(client, books, account).get_json()["closing_balance"]
        assert closing == item["closing_balance"], item["number"]


# --- input and who may see what --------------------------------------------


def test_a_missing_account_is_refused(client, books):
    res = client.get("/reports/account-ledger", headers=books["headers"])

    assert res.status_code == 422
    assert "account_id" in res.get_json()["errors"]


@pytest.mark.parametrize(
    "query", ["from=yesterday", "to=2026-13-01", "from=2026-01-01&to=nope"]
)
def test_a_bad_date_is_refused(client, books, query):
    ledger_res = client.get(
        f"/reports/account-ledger?account_id={books['bank'].id}&{query}",
        headers=books["headers"],
    )
    trial_res = client.get(
        f"/reports/trial-balance?{query}", headers=books["headers"]
    )

    assert ledger_res.status_code == 422
    assert trial_res.status_code == 422


def test_a_range_cannot_end_before_it_starts(client, books):
    query = "from=2026-12-31&to=2026-01-01"

    ledger_res = client.get(
        f"/reports/account-ledger?account_id={books['bank'].id}&{query}",
        headers=books["headers"],
    )
    trial_res = client.get(
        f"/reports/trial-balance?{query}", headers=books["headers"]
    )

    assert ledger_res.status_code == 422
    assert trial_res.status_code == 422
    assert "from date is after the to date" in trial_res.get_json()["error"]


def test_an_unknown_query_field_is_refused(client, books):
    res = client.get(
        "/reports/trial-balance?fiscal_year=1", headers=books["headers"]
    )

    assert res.status_code == 422
    assert "fiscal_year" in res.get_json()["errors"]


def test_an_unknown_account_is_not_found(client, books):
    res = client.get(
        "/reports/account-ledger?account_id=999999", headers=books["headers"]
    )

    assert res.status_code == 404


@pytest.mark.parametrize(
    "url",
    ["/reports/account-ledger?account_id=1", "/reports/trial-balance"],
)
def test_the_reports_need_a_login(client, url):
    assert client.get(url).status_code == 401


@pytest.fixture
def stranger(db_session, country):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
    )
    db_session.add(other)
    db_session.flush()
    user = User(
        organization_id=other.id,
        password_plaintext="password123",
        name="Other",
        email="other@example.com",
        otp_secret=User.generate_otp_secret(),
    )
    db_session.add(user)
    db_session.commit()
    apply_starter_chart(other)
    mine = {
        item.number: item
        for item in Account.query.filter_by(organization_id=other.id)
    }
    return {
        "org": other,
        "user": user,
        "headers": headers(user),
        "accounts": mine,
    }


def test_another_organization_has_its_own_books(
    client, books, worked, stranger
):
    theirs = stranger["accounts"]
    post_entry(
        stranger["org"].id,
        stranger["user"].id,
        date(2026, 4, 1),
        "Theirs",
        [
            LineInput(account_id=theirs[6480].id, debit=D("999")),
            LineInput(account_id=theirs[1010].id, credit=D("999")),
        ],
    )

    mine = trial(client, books).get_json()
    theirs_report = client.get(
        "/reports/trial-balance", headers=stranger["headers"]
    ).get_json()

    assert balances(mine)[6480] == D("147.50")
    assert balances(theirs_report) == {1010: D("-999"), 6480: D("999")}


def test_an_account_of_another_organization_is_not_found(
    client, books, worked, stranger
):
    res = client.get(
        f"/reports/account-ledger?account_id={stranger['accounts'][6480].id}",
        headers=books["headers"],
    )

    assert res.status_code == 404


# --- every figure against a plain sum --------------------------------------


@pytest.fixture
def random_books(db_session, books):
    """Many random balanced entries over three years, some reversed, and the
    lines of each as posted, for the figures to be checked against."""
    rng = random.Random(20261030)
    pool = [
        books["accounts"][number]
        for number in (1010, 1610, 2450, 2410, 6190, 6480, 7680, 7740, 7840)
    ]
    entries = []
    for _ in range(70):
        total = D(rng.randint(1, 500000)) / 100
        debit_accounts = rng.sample(pool, rng.randint(1, 3))
        credit_accounts = rng.sample(pool, rng.randint(1, 3))
        entries.append(
            post_entry(
                books["org"].id,
                books["user"].id,
                date(2025, 1, 1) + timedelta(days=rng.randint(0, 3 * 365 - 1)),
                "Random",
                _split(rng, debit_accounts, total, True)
                + _split(rng, credit_accounts, total, False),
            )
        )
    for original in rng.sample(entries, 12):
        entries.append(
            reverse_entry(
                books["org"].id,
                books["user"].id,
                original.id,
                entry_date=original.entry_date
                + timedelta(days=rng.randint(0, 40)),
            )
        )
    db_session.commit()
    lines = [
        (
            line.account_id,
            entry.entry_date,
            entry.voucher_no,
            line.line_no,
            line.debit,
            line.credit,
        )
        for entry in entries
        for line in entry.lines
    ]
    # enough to be a real check: many lines over many accounts
    assert len(lines) > 150
    assert len({line[0] for line in lines}) >= 8
    return lines


def _split(rng, accounts, total, debit):
    """The total split in cents over the accounts."""
    cents = int(total * 100)
    cuts = (
        sorted(rng.sample(range(1, cents), len(accounts) - 1))
        if len(accounts) > 1 and cents > len(accounts)
        else []
    )
    parts = [b - a for a, b in zip([0, *cuts], [*cuts, cents])]
    return [
        LineInput(
            account_id=account.id,
            **(
                {"debit": D(part) / 100} if debit else {"credit": D(part) / 100}
            ),
        )
        for account, part in zip(accounts, parts)
        if part > 0
    ]


WINDOWS = [
    (None, None),
    (date(2025, 6, 1), None),
    (None, date(2026, 3, 15)),
    (date(2025, 7, 4), date(2026, 8, 20)),
    (date(2027, 1, 1), date(2027, 12, 31)),
    (date(2030, 1, 1), None),
]


def window(lines, start, end):
    return [
        line
        for line in lines
        if (start is None or line[1] >= start)
        and (end is None or line[1] <= end)
    ]


@pytest.mark.parametrize(("start", "end"), WINDOWS)
def test_the_trial_balance_matches_a_plain_sum_of_the_lines(
    client, books, random_books, start, end
):
    params = {}
    if start:
        params["from"] = start.isoformat()
    if end:
        params["to"] = end.isoformat()

    report = trial(client, books, **params).get_json()

    reported = {item["account_id"]: item for item in report["accounts"]}
    up_to_end = window(random_books, None, end)
    assert set(reported) == {line[0] for line in up_to_end}
    for account_id, item in reported.items():
        lines = [line for line in up_to_end if line[0] == account_id]
        before = [line for line in lines if start and line[1] < start]
        inside = window(lines, start, end)
        opening = sum((line[4] - line[5] for line in before), D("0"))
        debit = sum((line[4] for line in inside), D("0"))
        credit = sum((line[5] for line in inside), D("0"))
        assert money(item["opening_balance"]) == opening
        assert money(item["debit"]) == debit
        assert money(item["credit"]) == credit
        assert money(item["closing_balance"]) == opening + debit - credit
    # every entry balances, so the whole report nets to zero
    assert report["balanced"] is True
    assert (
        sum(money(item["closing_balance"]) for item in reported.values()) == 0
    )
    assert (
        sum(money(item["opening_balance"]) for item in reported.values()) == 0
    )


@pytest.mark.parametrize(("start", "end"), WINDOWS)
def test_the_ledger_matches_a_plain_sum_and_ends_at_the_trial_balance(
    client, books, random_books, start, end
):
    params = {}
    if start:
        params["from"] = start.isoformat()
    if end:
        params["to"] = end.isoformat()
    trial_report = trial(client, books, **params).get_json()

    for item in trial_report["accounts"]:
        account = db.session.get(Account, item["account_id"])
        report = ledger(client, books, account, **params).get_json()
        lines = sorted(
            window(
                [line for line in random_books if line[0] == account.id],
                start,
                end,
            ),
            key=lambda line: (line[1], line[2], line[3]),
        )
        opening = sum(
            (
                line[4] - line[5]
                for line in random_books
                if line[0] == account.id and start and line[1] < start
            ),
            D("0"),
        )
        running, expected = opening, []
        for line in lines:
            running += line[4] - line[5]
            expected.append((line[2], line[4], line[5], running))
        assert [
            (
                row["voucher_no"],
                money(row["debit"]),
                money(row["credit"]),
                money(row["balance"]),
            )
            for row in report["rows"]
        ] == expected
        assert money(report["opening_balance"]) == opening
        assert money(report["closing_balance"]) == running
        assert report["closing_balance"] == item["closing_balance"]
