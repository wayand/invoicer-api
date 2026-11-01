"""The VAT report (app/reports.py, docs/vat-design.md, section 6): worked
examples with known numbers, the check against the ledger, and random entries
against figures worked out from the inputs alone."""

import random
from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.chart import apply_starter_chart
from app.ledger import LineInput, post_entry, reverse_entry
from app.models.account import Account
from app.models.organization import Organization
from app.models.user import User
from app.models.vat_code import VatCode
from app.money import round_money
from app.reports import trial_balance
from app.vat_engine import NetLine, Rule, vat_lines

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
    organization.vat_period_type = "quarter"
    db_session.commit()
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
    }


def line(books, number, code=None, **amount):
    return LineInput(
        account_id=books["accounts"][number].id,
        debit=D(amount.get("debit", "0")),
        credit=D(amount.get("credit", "0")),
        vat_code=code,
    )


def post(books, day, lines, description="Entry"):
    return post_entry(
        books["org"].id, books["user"].id, day, description, lines
    )


def report(client, books, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(f"/reports/vat?{query}", headers=books["headers"])


def figures(body) -> dict:
    """The headline figures of a report, as exact amounts."""
    return {
        key: money(body[key])
        for key in (
            "sales_vat",
            "input_vat",
            "eu_goods_vat",
            "eu_services_vat",
            "total_to_pay",
        )
    }


def by_code(body) -> dict:
    return {item["code"]: item for item in body["codes"]}


@pytest.fixture
def worked(db_session, books):
    """Six VAT entries in the first quarter of 2026 and one in the second."""
    post(
        books,
        date(2026, 1, 10),
        [
            line(books, 6480, debit="1250"),
            line(books, 1010, "S01", credit="1000"),
        ],
    )
    post(
        books,
        date(2026, 2, 1),
        [
            line(books, 6480, debit="400"),
            line(books, 1150, "S23", credit="400"),
        ],
    )
    post(
        books,
        date(2026, 2, 10),
        [
            line(books, 1610, "K010", debit="800"),
            line(books, 7440, credit="1000"),
        ],
    )
    post(
        books,
        date(2026, 2, 20),
        [
            line(books, 1910, "K070", debit="100"),
            line(books, 7440, credit="125"),
        ],
    )
    post(
        books,
        date(2026, 3, 5),
        [
            line(books, 1710, "K260", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )
    post(
        books,
        date(2026, 3, 6),
        [
            line(books, 1630, "K230", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )
    post(
        books,
        date(2026, 4, 15),
        [
            line(books, 6480, debit="125"),
            line(books, 1010, "S01", credit="100"),
        ],
    )


# --- the figures of the return ---------------------------------------------


def test_the_report_gives_the_figures_of_the_return(client, books, worked):
    res = report(client, books, **{"from": "2026-01-01", "to": "2026-03-31"})

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["from"] == "2026-01-01"
    assert body["to"] == "2026-03-31"
    # 250 on the sale. Input VAT is 200 + 6.25 + 200: the purchase, the
    # deductible share of the representation, and the acquisition VAT on
    # services, which is deducted in full
    assert figures(body) == {
        "sales_vat": D("250"),
        "input_vat": D("406.25"),
        "eu_goods_vat": D("200"),
        "eu_services_vat": D("200"),
        # 250 + 200 + 200 - 406.25
        "total_to_pay": D("243.75"),
    }


def test_the_net_amounts_go_to_the_boxes_of_the_return(client, books, worked):
    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    assert {key: money(value) for key, value in body["boxes"].items()} == {
        "a_goods": D("800"),
        "a_services": D("800"),
        "b_goods": D("0"),
        "b_services": D("400"),
        "c": D("0"),
    }


def test_every_figure_is_given_per_code(client, books, worked):
    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    assert [item["code"] for item in body["codes"]] == [
        "K010",
        "K070",
        "K230",
        "K260",
        "S01",
        "S23",
    ]
    codes = by_code(body)

    def of(code, *keys):
        return tuple(money(codes[code][key]) for key in keys)

    keys = (
        "base",
        "output_vat",
        "input_vat",
        "acquisition_vat",
        "nondeductible_vat",
    )
    assert of("S01", *keys) == (D(1000), D(250), D(0), D(0), D(0))
    assert of("K010", *keys) == (D(800), D(0), D(200), D(0), D(0))
    # 25% of 25 is deducted, the other 18.75 is a cost
    assert of("K070", *keys) == (D(100), D(0), D("6.25"), D(0), D("18.75"))
    assert of("K260", *keys) == (D(800), D(0), D(200), D(200), D(0))
    assert of("K230", *keys) == (D(800), D(0), D(0), D(200), D(200))
    assert of("S23", *keys) == (D(400), D(0), D(0), D(0), D(0))


def test_a_code_is_described_with_its_rate_and_its_box(client, books, worked):
    codes = by_code(
        report(
            client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
        ).get_json()
    )

    assert codes["K070"]["rate"] == 0.25
    assert codes["K070"]["deduction"] == 0.25
    assert codes["K070"]["applies_to"] == "purchases"
    assert codes["K070"]["base_box"] is None
    assert codes["K260"]["base_box"] == "a_services"
    assert codes["S23"]["direction"] == "none"
    assert codes["S23"]["base_box"] == "b_services"
    assert codes["S01"]["title"]


def test_a_range_counts_only_its_own_dates(client, books, worked):
    first = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()
    second = report(
        client, books, **{"from": "2026-04-01", "to": "2026-06-30"}
    ).get_json()

    assert figures(second) == {
        "sales_vat": D("25"),
        "input_vat": D("0"),
        "eu_goods_vat": D("0"),
        "eu_services_vat": D("0"),
        "total_to_pay": D("25"),
    }
    assert [item["code"] for item in second["codes"]] == ["S01"]
    assert figures(first)["sales_vat"] + figures(second)["sales_vat"] == D(275)


def test_the_dates_of_a_range_are_included(client, books, worked):
    on_the_day = report(
        client, books, **{"from": "2026-01-10", "to": "2026-01-10"}
    ).get_json()
    the_day_before = report(
        client, books, **{"from": "2026-01-01", "to": "2026-01-09"}
    ).get_json()

    assert figures(on_the_day)["sales_vat"] == D(250)
    assert figures(the_day_before)["sales_vat"] == D(0)


def test_without_a_range_it_is_everything_posted(client, books, worked):
    body = report(client, books).get_json()

    assert body["from"] is None
    assert body["to"] is None
    assert figures(body)["sales_vat"] == D(275)


def test_a_credit_note_takes_the_vat_back(client, books, worked):
    post(
        books,
        date(2026, 3, 20),
        [
            line(books, 1010, "S01", debit="100"),
            line(books, 6480, credit="125"),
        ],
    )

    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    assert figures(body)["sales_vat"] == D(225)
    assert money(by_code(body)["S01"]["base"]) == D(900)


def test_a_reversal_sets_every_figure_back(client, books, worked):
    before = report(client, books).get_json()
    entry = post(
        books,
        date(2026, 3, 25),
        [
            line(books, 1610, "K040", debit="1000"),
            line(books, 7440, credit="1250"),
            line(books, 1630, "K230", debit="400"),
            line(books, 7440, credit="400"),
        ],
    )
    assert report(client, books).get_json() != before

    reverse_entry(
        books["org"].id,
        books["user"].id,
        entry.id,
        entry_date=date(2026, 3, 26),
    )

    after = report(client, books).get_json()
    assert figures(after) == figures(before)
    assert after["boxes"] == before["boxes"]
    keys = ("base", "output_vat", "input_vat", "acquisition_vat")
    was = {
        item["code"]: [money(item[key]) for key in keys]
        for item in before["codes"]
    }
    now = {
        item["code"]: [money(item[key]) for key in keys]
        for item in after["codes"]
    }
    # Every code is what it was, and the new ones are back to nothing
    assert {code: now[code] for code in was} == was
    assert {code: now[code] for code in now.keys() - was.keys()} == {
        "K040": [D(0)] * 4
    }
    # The codes of the reversed entry are still listed, with nothing left
    assert money(by_code(after)["K040"]["base"]) == D(0)
    assert money(by_code(after)["K040"]["input_vat"]) == D(0)


def test_empty_books_have_an_empty_report_that_ties(client, books):
    body = report(client, books).get_json()

    assert figures(body) == {
        "sales_vat": D(0),
        "input_vat": D(0),
        "eu_goods_vat": D(0),
        "eu_services_vat": D(0),
        "total_to_pay": D(0),
    }
    assert body["codes"] == []
    assert {money(value) for value in body["boxes"].values()} == {D(0)}
    assert body["ledger_check"]["ties"] is True
    assert body["ledger_check"]["uncoded_lines"] == []


def test_an_organization_that_left_vat_can_still_read_its_report(
    client, db_session, books, worked
):
    books["org"].vat_period_type = None
    db_session.commit()

    res = report(client, books)

    assert res.status_code == 200
    assert figures(res.get_json())["sales_vat"] == D(275)


# --- the check against the ledger ------------------------------------------


def check_of(body) -> dict:
    return {item["role"]: item for item in body["ledger_check"]["accounts"]}


def test_the_figures_equal_the_balances_of_the_vat_accounts(
    client, books, worked
):
    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    check = check_of(body)
    assert [item["role"] for item in body["ledger_check"]["accounts"]] == [
        "output_vat",
        "input_vat",
        "vat_eu_goods",
        "vat_eu_services",
    ]
    assert {
        role: (
            item["account"]["number"],
            money(item["ledger_balance"]),
            money(item["reported"]),
            money(item["difference"]),
        )
        for role, item in check.items()
    } == {
        "output_vat": (7680, D(250), D(250), D(0)),
        "input_vat": (7740, D("406.25"), D("406.25"), D(0)),
        "vat_eu_goods": (7700, D(200), D(200), D(0)),
        "vat_eu_services": (7720, D(200), D(200), D(0)),
    }
    assert body["ledger_check"]["ties"] is True
    assert body["ledger_check"]["uncoded_lines"] == []


def test_a_posting_without_a_code_is_the_difference_and_is_listed(
    client, books, worked
):
    manual = post(
        books,
        date(2026, 3, 15),
        [
            line(books, 6480, debit="30"),
            line(books, 7680, credit="30"),
        ],
        "VAT by hand",
    )

    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    output = check_of(body)["output_vat"]
    assert money(output["ledger_balance"]) == D(280)
    assert money(output["reported"]) == D(250)
    assert money(output["difference"]) == D(30)
    assert body["ledger_check"]["ties"] is False
    # What the return gets is what has a code
    assert figures(body)["sales_vat"] == D(250)
    [listed] = body["ledger_check"]["uncoded_lines"]
    assert listed["entry_id"] == manual.id
    assert listed["voucher_no"] == manual.voucher_no
    assert listed["entry_date"] == "2026-03-15"
    assert listed["description"] == "VAT by hand"
    assert listed["role"] == "output_vat"
    assert listed["account"]["number"] == 7680
    assert (money(listed["debit"]), money(listed["credit"])) == (D(0), D(30))


def test_an_uncoded_posting_outside_the_range_is_not_listed(
    client, books, worked
):
    post(
        books,
        date(2026, 5, 15),
        [line(books, 6480, debit="30"), line(books, 7680, credit="30")],
    )

    body = report(
        client, books, **{"from": "2026-01-01", "to": "2026-03-31"}
    ).get_json()

    assert body["ledger_check"]["ties"] is True
    assert body["ledger_check"]["uncoded_lines"] == []


def test_uncoded_postings_on_all_four_vat_accounts_are_found(client, books):
    post(
        books,
        date(2026, 3, 1),
        [
            line(books, 7680, credit="10"),
            line(books, 7700, credit="20"),
            line(books, 7720, credit="30"),
            line(books, 7740, debit="60"),
        ],
    )

    body = report(client, books).get_json()

    assert {
        role: money(item["difference"]) for role, item in check_of(body).items()
    } == {
        "output_vat": D(10),
        "input_vat": D(60),
        "vat_eu_goods": D(20),
        "vat_eu_services": D(30),
    }
    assert [item["role"] for item in body["ledger_check"]["uncoded_lines"]] == [
        "output_vat",
        "vat_eu_goods",
        "vat_eu_services",
        "input_vat",
    ]


def test_an_organization_without_a_chart_has_no_vat_accounts_to_check(
    client, organization, test_user
):
    res = client.get("/reports/vat", headers=headers(test_user))

    assert res.status_code == 200
    body = res.get_json()
    assert [
        (item["role"], item["account"], money(item["difference"]))
        for item in body["ledger_check"]["accounts"]
    ] == [
        ("output_vat", None, D(0)),
        ("input_vat", None, D(0)),
        ("vat_eu_goods", None, D(0)),
        ("vat_eu_services", None, D(0)),
    ]
    assert body["ledger_check"]["ties"] is True


# --- who can read it -------------------------------------------------------


def test_the_report_needs_a_login(client):
    assert client.get("/reports/vat").status_code == 401


@pytest.fixture
def stranger(db_session, country):
    other = Organization(
        name="Other ApS",
        slug="other-aps",
        country_id=country.id,
        email="other@example.com",
        logo="",
        vat_period_type="quarter",
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


def test_another_organization_has_its_own_report(
    client, books, worked, stranger
):
    post(
        stranger,
        date(2026, 2, 1),
        [
            line(stranger, 6480, debit="62.50"),
            line(stranger, 1010, "S01", credit="50"),
        ],
    )

    mine = report(client, books).get_json()
    theirs = client.get("/reports/vat", headers=stranger["headers"]).get_json()

    assert figures(mine)["sales_vat"] == D(275)
    assert figures(theirs)["sales_vat"] == D("12.50")
    assert [item["code"] for item in theirs["codes"]] == ["S01"]
    assert theirs["ledger_check"]["ties"] is True


# --- what is refused -------------------------------------------------------


@pytest.mark.parametrize(
    "query", ["from=yesterday", "to=2026-13-01", "from=2026-1-1x"]
)
def test_a_bad_date_is_refused(client, books, query):
    res = client.get(f"/reports/vat?{query}", headers=books["headers"])

    assert res.status_code == 422
    assert "errors" in res.get_json()


def test_a_range_cannot_end_before_it_starts(client, books):
    res = report(client, books, **{"from": "2026-04-01", "to": "2026-03-31"})

    assert res.status_code == 422
    assert "after the to date" in res.get_json()["error"]


def test_an_unknown_query_field_is_refused(client, books):
    res = client.get("/reports/vat?year=2026", headers=books["headers"])

    assert res.status_code == 422


# --- random entries against figures worked out from the inputs -------------

SALES_CODES = [("S01", 1010), ("S02", 1010), ("S23", 1150), ("S21", 1050)]
DOMESTIC_PURCHASES = [("K010", 1610), ("K040", 2410), ("K070", 1910)]
ACQUISITIONS = [
    ("K260", 1710),
    ("K280", 1710),
    ("K230", 1630),
    ("K210", 1630),
]
OTHER_PURCHASES = [("K030", 1610), ("K340", 1630)]


def random_entry(books, generator):
    """An entry of one kind (a sale, a domestic purchase, or purchases from
    abroad) with several coded lines, and its gross line. Returns the lines
    and a list of (code, signed net)."""
    kind = generator.choice(["sale", "domestic", "abroad", "other"])
    choices = {
        "sale": SALES_CODES,
        "domestic": DOMESTIC_PURCHASES,
        "abroad": ACQUISITIONS,
        "other": OTHER_PURCHASES,
    }[kind]
    sign = generator.choice([1, 1, 1, -1])  # now and then a credit note
    nets = []
    lines = []
    for _ in range(generator.randint(1, 4)):
        code, number = generator.choice(choices)
        amount = D(generator.randint(1, 500_000)) / 100
        nets.append((code, sign * amount))
        sale = kind == "sale"
        debit_side = (sign > 0) != sale
        lines.append(
            line(
                books,
                number,
                code,
                **{("debit" if debit_side else "credit"): amount},
            )
        )

    rules = {
        code.code: Rule(
            code.code,
            code.applies_to,
            code.rate,
            code.deduction,
            code.direction,
        )
        for code in VatCode.query
    }
    added = vat_lines(
        [
            NetLine(
                item.account_id, item.debit, item.credit, rules[item.vat_code]
            )
            for item in lines
        ]
    )
    balance = sum((item.debit - item.credit for item in lines), D("0.00"))
    balance += sum((item.debit - item.credit for item in added), D("0.00"))
    gross = books["accounts"][6480 if kind == "sale" else 7440].id
    if balance > 0:
        lines.append(LineInput(account_id=gross, credit=balance))
    else:
        lines.append(LineInput(account_id=gross, debit=-balance))
    return lines, nets


def expected_figures(entries):
    """The report of entries, worked out from what was put in: for each code
    in each entry the net amounts add up to a base, the VAT is rounded once,
    and the deductible part once more."""
    rules = {code.code: code for code in VatCode.query}
    sales = purchases = goods = services = D(0)
    boxes = {}
    per_code = {}
    for nets in entries:
        bases = {}
        for code, net in nets:
            bases[code] = bases.get(code, D(0)) + net
        for code, base in bases.items():
            rule = rules[code]
            vat = round_money(base * (rule.rate or 0)) if rule.rate else D(0)
            item = per_code.setdefault(code, {"base": D(0), "vat": D(0)})
            item["base"] += base
            if rule.base_box:
                boxes[rule.base_box] = boxes.get(rule.base_box, D(0)) + base
            if rule.direction == "output":
                sales += vat
                item["vat"] += vat
            elif rule.direction in (
                "input",
                "acquisition_goods",
                "acquisition_services",
            ):
                deductible = round_money(vat * rule.deduction)
                purchases += deductible
                item["vat"] += deductible
                if rule.direction == "acquisition_goods":
                    goods += vat
                elif rule.direction == "acquisition_services":
                    services += vat
    return {
        "sales_vat": sales,
        "input_vat": purchases,
        "eu_goods_vat": goods,
        "eu_services_vat": services,
        "total_to_pay": sales + goods + services - purchases,
        "boxes": boxes,
        "per_code": per_code,
    }


@pytest.mark.parametrize("seed", range(40))
def test_random_entries_give_the_figures_worked_out_from_the_inputs(
    client, db_session, books, seed
):
    generator = random.Random(seed)
    posted = []
    for number in range(generator.randint(1, 12)):
        lines, nets = random_entry(books, generator)
        day = date(2026, generator.randint(1, 3), generator.randint(1, 28))
        entry = post(books, day, lines, f"Entry {number}")
        posted.append((entry, nets))
    # Some of them are reversed, as the reversal is dated after the range
    reversed_ = set()
    for index, (entry, _nets) in enumerate(posted):
        if generator.random() < 0.25:
            reverse_entry(
                books["org"].id,
                books["user"].id,
                entry.id,
                entry_date=date(2026, 6, 1),
            )
            reversed_.add(index)

    body = report(client, books, **{"to": "2026-03-31"}).get_json()
    expected = expected_figures(
        [
            nets
            for index, (_e, nets) in enumerate(posted)
            if index not in reversed_
        ]
    )
    # What was reversed is dated after the range: the range shows all of it
    everything = expected_figures([nets for _entry, nets in posted])
    assert figures(body) == {
        key: value
        for key, value in everything.items()
        if key
        in (
            "sales_vat",
            "input_vat",
            "eu_goods_vat",
            "eu_services_vat",
            "total_to_pay",
        )
    }

    # Over everything posted the reversed entries net out
    full = report(client, books).get_json()
    assert figures(full) == {
        key: value
        for key, value in expected.items()
        if key
        in (
            "sales_vat",
            "input_vat",
            "eu_goods_vat",
            "eu_services_vat",
            "total_to_pay",
        )
    }
    assert {
        box: money(value) for box, value in full["boxes"].items() if value
    } == {box: value for box, value in expected["boxes"].items() if value}
    assert {
        item["code"]: (
            money(item["base"]),
            money(item["output_vat"]) + money(item["input_vat"]),
        )
        for item in full["codes"]
        if money(item["base"])
        or money(item["input_vat"])
        or money(item["output_vat"])
    } == {
        code: (item["base"], item["vat"])
        for code, item in expected["per_code"].items()
        if item["base"] or item["vat"]
    }

    # Each figure equals the balance of its account, and nothing is left over
    check = full["ledger_check"]
    assert check["ties"] is True
    assert check["uncoded_lines"] == []
    balances = {
        item["number"]: item["closing_balance"]
        for item in trial_balance(books["org"].id)["accounts"]
    }
    assert -balances.get(7680, D(0)) == figures(full)["sales_vat"]
    assert balances.get(7740, D(0)) == figures(full)["input_vat"]
    assert -balances.get(7700, D(0)) == figures(full)["eu_goods_vat"]
    assert -balances.get(7720, D(0)) == figures(full)["eu_services_vat"]
