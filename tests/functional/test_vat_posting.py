"""VAT in the posting service: a line with a VAT code is a net line, and the
service adds the VAT lines (app/vat_engine.py, docs/vat-design.md)."""

import random
from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.chart import apply_starter_chart
from app.ledger import (
    LedgerConflict,
    LedgerError,
    LineInput,
    post_entry,
    reverse_entry,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.ledger import JournalEntry, LedgerCounter
from app.models.vat_code import VatCode
from app.money import round_money
from app.reports import trial_balance
from app.vat_engine import NetLine, Rule, vat_lines

D = Decimal
DAY = date(2026, 3, 1)


@pytest.fixture
def books(db_session, organization, test_user):
    organization.vat_period_type = "quarter"
    db_session.commit()
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    return {"org": organization, "user": test_user, "accounts": accounts}


def line(books, number, code=None, **amount):
    return LineInput(
        account_id=books["accounts"][number].id,
        debit=D(amount.get("debit", "0")),
        credit=D(amount.get("credit", "0")),
        vat_code=code,
    )


def post(books, lines, day=DAY, description="VAT"):
    return post_entry(
        books["org"].id, books["user"].id, day, description, lines
    )


def shown(books, entry):
    """The lines of an entry as (account number, code, part, debit, credit)."""
    numbers = {a.id: n for n, a in books["accounts"].items()}
    return [
        (
            numbers[item.account_id],
            item.vat_code.code if item.vat_code_id else None,
            item.vat_part,
            item.debit,
            item.credit,
        )
        for item in entry.lines
    ]


def entries(books):
    return JournalEntry.query.filter_by(organization_id=books["org"].id)


# --- what is posted ------------------------------------------------------


def test_a_sale_gets_its_output_vat(db_session, books):
    entry = post(
        books,
        [
            line(books, 6480, debit="125"),
            line(books, 1010, "S01", credit="100"),
        ],
    )

    assert shown(books, entry) == [
        (6480, None, None, D("125.00"), D("0.00")),
        (1010, "S01", "base", D("0.00"), D("100.00")),
        (7680, "S01", "vat", D("0.00"), D("25.00")),
    ]
    assert entry.lines[2].description == "VAT S01"
    assert [item.line_no for item in entry.lines] == [1, 2, 3]


def test_a_domestic_purchase_gets_its_input_vat(db_session, books):
    entry = post(
        books,
        [
            line(books, 1610, "K010", debit="800"),
            line(books, 7440, credit="1000"),
        ],
    )

    assert shown(books, entry)[2] == (
        7740,
        "K010",
        "vat",
        D("200.00"),
        D("0.00"),
    )


def test_the_part_of_the_vat_that_is_not_deducted_is_a_cost(db_session, books):
    entry = post(
        books,
        [
            line(books, 1910, "K070", debit="100"),
            line(books, 7440, credit="125"),
        ],
    )

    assert shown(books, entry) == [
        (1910, "K070", "base", D("100.00"), D("0.00")),
        (7440, None, None, D("0.00"), D("125.00")),
        (7740, "K070", "vat", D("6.25"), D("0.00")),
        (1910, "K070", "nondeductible", D("18.75"), D("0.00")),
    ]
    assert entry.lines[3].description == "Non-deductible VAT K070"


def test_services_from_the_eu_are_acquisition_vat_and_input_vat(
    db_session, books
):
    entry = post(
        books,
        [
            line(books, 1710, "K260", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )

    assert shown(books, entry)[2:] == [
        (7720, "K260", "vat", D("0.00"), D("200.00")),
        (7740, "K260", "vat", D("200.00"), D("0.00")),
    ]


def test_goods_from_the_eu_without_deduction_cost_the_vat(db_session, books):
    entry = post(
        books,
        [
            line(books, 1630, "K230", debit="800"),
            line(books, 7440, credit="800"),
        ],
    )

    assert shown(books, entry)[2:] == [
        (7700, "K230", "vat", D("0.00"), D("200.00")),
        (1630, "K230", "nondeductible", D("200.00"), D("0.00")),
    ]


def test_a_credit_note_has_its_vat_on_the_other_side(db_session, books):
    entry = post(
        books,
        [
            line(books, 1010, "S01", debit="100"),
            line(books, 6480, credit="125"),
        ],
    )

    assert shown(books, entry)[2] == (
        7680,
        "S01",
        "vat",
        D("25.00"),
        D("0.00"),
    )


def test_vat_is_rounded_once_for_a_code_and_not_for_each_line(
    db_session, books
):
    entry = post(
        books,
        [
            line(books, 6480, debit="0.38"),
            line(books, 1010, "S01", credit="0.10"),
            line(books, 1010, "S01", credit="0.10"),
            line(books, 1210, "S01", credit="0.10"),
        ],
    )

    assert shown(books, entry)[4] == (7680, "S01", "vat", D("0.00"), D("0.08"))


def test_codes_without_vat_are_recorded_and_add_nothing(db_session, books):
    entry = post(
        books,
        [
            line(books, 6480, debit="400"),
            line(books, 1150, "S23", credit="400"),
        ],
    )

    assert shown(books, entry) == [
        (6480, None, None, D("400.00"), D("0.00")),
        (1150, "S23", "base", D("0.00"), D("400.00")),
    ]


def test_an_entry_with_no_code_is_posted_as_before(db_session, books):
    entry = post(
        books,
        [
            line(books, 6480, debit="125"),
            line(books, 1010, credit="100"),
            line(books, 7680, credit="25"),
        ],
    )

    assert {item.vat_code_id for item in entry.lines} == {None}
    assert {item.vat_part for item in entry.lines} == {None}


def test_the_audit_log_names_the_codes(db_session, books):
    entry = post(
        books,
        [
            line(books, 6480, debit="525"),
            line(books, 1010, "S01", credit="100"),
            line(books, 1150, "S23", credit="400"),
        ],
    )

    row = AuditLog.query.filter_by(
        action="journal_entry.posted", entity_id=entry.id
    ).one()
    assert row.details["vat_codes"] == ["S01", "S23"]
    assert row.details["line_count"] == 4


# --- what is refused -------------------------------------------------------


def nothing_was_posted(books):
    assert entries(books).count() == 0
    counter = LedgerCounter.query.filter_by(
        organization_id=books["org"].id
    ).first()
    assert counter is None or counter.next_voucher_no == 1


def test_the_lines_must_balance_with_the_vat_lines(db_session, books):
    with pytest.raises(LedgerError) as error:
        post(
            books,
            [
                line(books, 6480, debit="100"),
                line(books, 1010, "S01", credit="100"),
            ],
        )

    assert (
        str(error.value)
        == "The entry does not balance: debit 100.00, credit 125.00 "
        "(with the VAT lines)"
    )
    nothing_was_posted(books)


def test_an_organization_that_is_not_registered_uses_no_codes(
    db_session, books
):
    books["org"].vat_period_type = None
    db_session.commit()

    with pytest.raises(LedgerError, match="not VAT-registered"):
        post(
            books,
            [
                line(books, 6480, debit="100"),
                line(books, 1010, "S01", credit="100"),
            ],
        )
    nothing_was_posted(books)


def test_an_unknown_code_is_refused(db_session, books):
    with pytest.raises(LedgerError) as error:
        post(
            books,
            [
                line(books, 6480, debit="100"),
                line(books, 1010, "X99", credit="100"),
            ],
        )

    assert str(error.value) == "Line 2: there is no VAT code X99"


def test_a_code_that_cannot_be_used_yet_is_refused(db_session, books):
    with pytest.raises(LedgerError) as error:
        post(
            books,
            [
                line(books, 2450, "K020", debit="100"),
                line(books, 7440, credit="125"),
            ],
        )

    assert str(error.value) == "Line 1: the VAT code K020 cannot be used yet"


def test_the_old_name_of_a_code_is_not_a_code(db_session, books):
    with pytest.raises(LedgerError, match="there is no VAT code S1"):
        post(
            books,
            [
                line(books, 6480, debit="125"),
                line(books, 1010, "S1", credit="100"),
            ],
        )


def test_a_vat_code_cannot_be_put_on_a_vat_account(db_session, books):
    with pytest.raises(LedgerError) as error:
        post(
            books,
            [
                line(books, 6480, debit="25"),
                line(books, 7680, "S01", credit="25"),
            ],
        )

    assert "a VAT code cannot be used on the VAT account 7680" in str(
        error.value
    )


def test_the_vat_part_is_not_the_callers(db_session, books):
    given = LineInput(
        account_id=books["accounts"][1010].id,
        credit=D("100"),
        vat_code="S01",
        vat_part="base",
    )

    with pytest.raises(LedgerError, match="set by the server"):
        post(books, [line(books, 6480, debit="125"), given])


def test_a_part_without_a_code_is_refused_too(db_session, books):
    given = LineInput(
        account_id=books["accounts"][1010].id,
        credit=D("100"),
        vat_part="vat",
    )

    with pytest.raises(LedgerError, match="set by the server"):
        post(books, [line(books, 6480, debit="100"), given])


@pytest.mark.parametrize(
    "code, part, message",
    [
        ("S01", None, "go together"),
        (None, "vat", "go together"),
        ("S01", "net", "unknown VAT part"),
    ],
)
def test_lines_that_are_copied_must_be_whole(
    db_session, books, code, part, message
):
    copied = LineInput(
        account_id=books["accounts"][1010].id,
        credit=D("100"),
        vat_code=code,
        vat_part=part,
    )

    with pytest.raises(LedgerError, match=message):
        post_entry(
            books["org"].id,
            books["user"].id,
            DAY,
            "Copy",
            [line(books, 6480, debit="100"), copied],
            add_vat=False,
        )


def test_an_organization_without_the_vat_account_cannot_post_the_vat(
    db_session, books
):
    books["accounts"][7680].system_role = None
    db_session.commit()

    with pytest.raises(LedgerConflict) as error:
        post(
            books,
            [
                line(books, 6480, debit="125"),
                line(books, 1010, "S01", credit="100"),
            ],
        )

    assert str(error.value) == (
        "The organization has no account with role output_vat"
    )
    nothing_was_posted(books)


def test_an_archived_vat_account_is_refused(db_session, books):
    books["accounts"][7680].is_archived = True
    db_session.commit()

    with pytest.raises(LedgerError, match="7680 Salgsmoms is archived"):
        post(
            books,
            [
                line(books, 6480, debit="125"),
                line(books, 1010, "S01", credit="100"),
            ],
        )
    nothing_was_posted(books)


# --- reversals -------------------------------------------------------------


def test_a_reversal_copies_every_line_with_its_code_and_part(db_session, books):
    original = post(
        books,
        [
            line(books, 1910, "K070", debit="100"),
            line(books, 7440, credit="125"),
        ],
    )

    reversal = reverse_entry(books["org"].id, books["user"].id, original.id)

    assert shown(books, reversal) == [
        (1910, "K070", "base", D("0.00"), D("100.00")),
        (7440, None, None, D("125.00"), D("0.00")),
        (7740, "K070", "vat", D("0.00"), D("6.25")),
        (1910, "K070", "nondeductible", D("0.00"), D("18.75")),
    ]


def test_a_reversal_does_not_calculate_the_vat_again(db_session, books):
    original = post(
        books,
        [
            line(books, 6480, debit="125"),
            line(books, 1010, "S01", credit="100"),
        ],
    )

    reversal = reverse_entry(books["org"].id, books["user"].id, original.id)

    assert len(reversal.lines) == len(original.lines) == 3


def test_a_reversal_is_allowed_after_the_organization_left_vat(
    db_session, books
):
    original = post(
        books,
        [
            line(books, 6480, debit="125"),
            line(books, 1010, "S01", credit="100"),
        ],
    )
    books["org"].vat_period_type = None
    db_session.commit()

    reversal = reverse_entry(books["org"].id, books["user"].id, original.id)

    assert reversal.reverses_entry_id == original.id


def test_every_vat_account_nets_to_zero_after_a_reversal(db_session, books):
    original = post(
        books,
        [
            line(books, 6480, debit="125"),
            line(books, 1010, "S01", credit="100"),
        ],
    )
    reverse_entry(books["org"].id, books["user"].id, original.id)

    report = trial_balance(books["org"].id)

    assert report["balanced"]
    assert {item["closing_balance"] for item in report["accounts"]} == {
        D("0.00")
    }


# --- the database guards ----------------------------------------------------


def raw_line(db_session, entry, code_id, part):
    db_session.execute(
        text(
            "INSERT INTO journal_lines (journal_entry_id, organization_id, "
            "line_no, account_id, debit, credit, vat_code_id, vat_part) "
            "SELECT :entry, organization_id, 99, account_id, 0, 1, :code, "
            ":part FROM journal_lines WHERE journal_entry_id = :entry LIMIT 1"
        ),
        {"entry": entry.id, "code": code_id, "part": part},
    )


@pytest.mark.parametrize(
    "with_code, part, constraint",
    [
        (True, None, "ck_journal_lines_vat"),
        (False, "vat", "ck_journal_lines_vat"),
        (True, "net", "ck_journal_lines_vat_part"),
    ],
)
def test_the_database_wants_a_code_and_a_part_together(
    db_session, books, with_code, part, constraint
):
    entry = post(
        books,
        [line(books, 6480, debit="10"), line(books, 1010, credit="10")],
    )
    code_id = (
        VatCode.query.filter_by(code="S01").one().id if with_code else None
    )

    with pytest.raises(IntegrityError) as error:
        raw_line(db_session, entry, code_id, part)

    assert constraint in str(error.value)


def test_a_line_cannot_point_at_a_code_that_does_not_exist(db_session, books):
    entry = post(
        books,
        [line(books, 6480, debit="10"), line(books, 1010, credit="10")],
    )

    with pytest.raises(IntegrityError) as error:
        raw_line(db_session, entry, 999999, "base")

    assert "fk_journal_lines_vat_code_id" in str(error.value)


# --- random entries ---------------------------------------------------------

SALES = [("S01", 1010), ("S23", 1150), ("S21", 1050), ("S81", 1010)]
PURCHASES = [
    ("K010", 1610),
    ("K070", 1910),
    ("K040", 2410),
    ("K260", 1710),
    ("K230", 1630),
    ("K460", 1710),
    ("K480", 1710),
]


def counterpart(books, lines) -> LineInput:
    """The caller's own gross line: what makes the lines and the VAT lines
    balance. The engine says what the VAT lines are."""
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
    net = [
        NetLine(item.account_id, item.debit, item.credit, rules[item.vat_code])
        for item in lines
    ]
    added = vat_lines(net)
    balance = sum((item.debit - item.credit for item in lines), D("0.00"))
    balance += sum((item.debit - item.credit for item in added), D("0.00"))
    account = books["accounts"][6480].id
    if balance > 0:
        return LineInput(account_id=account, credit=balance)
    return LineInput(account_id=account, debit=-balance)


@pytest.mark.parametrize("seed", range(25))
def test_random_entries_carry_the_vat_of_their_codes(db_session, books, seed):
    generator = random.Random(seed)
    lines = []
    for _ in range(generator.randint(1, 5)):
        code, number = generator.choice(SALES + PURCHASES)
        amount = D(generator.randint(1, 900_000)) / 100
        side = "debit" if code.startswith("K") else "credit"
        lines.append(line(books, number, code, **{side: amount}))

    posted = post(books, lines + [counterpart(books, lines)])

    # The VAT of each code, recomputed from the lines in the database
    ids = {item.vat_code_id for item in posted.lines if item.vat_code_id}
    for code in VatCode.query.filter(VatCode.id.in_(ids)):
        mine = [item for item in posted.lines if item.vat_code_id == code.id]
        sales = code.applies_to == "sales"
        base = sum(
            (
                (item.credit - item.debit)
                if sales
                else (item.debit - item.credit)
                for item in mine
                if item.vat_part == "base"
            ),
            D("0.00"),
        )
        added = [item for item in mine if item.vat_part != "base"]
        net_added = sum((item.debit - item.credit for item in added), D("0.00"))
        if code.direction == "none":
            assert added == []
            continue
        vat = round_money(base * code.rate)
        if code.direction == "output":
            assert net_added == -vat
        elif code.direction == "input":
            assert net_added == vat
        else:
            # The acquisition VAT is a credit of all of it, and the deduction
            # and the cost together are a debit of the same
            assert net_added == 0
    assert sum((i.debit - i.credit for i in posted.lines), D("0.00")) == 0
    assert trial_balance(books["org"].id)["balanced"]


# --- the API ----------------------------------------------------------------


def api_headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


def api_body(books, **overrides) -> dict:
    body = {
        "entry_date": "2026-03-01",
        "description": "Sale",
        "lines": [
            {"account_id": books["accounts"][6480].id, "debit": 125},
            {
                "account_id": books["accounts"][1010].id,
                "credit": 100,
                "vat_code": "S01",
            },
        ],
    }
    body.update(overrides)
    return body


def test_the_api_posts_a_net_line_and_returns_the_vat_line(
    client, books, test_user
):
    res = client.post(
        "/journal-entries",
        json=api_body(books),
        headers=api_headers(test_user),
    )

    assert res.status_code == 201, res.get_json()
    lines = res.get_json()["lines"]
    assert [
        (item["account_number"], item["vat_code"], item["vat_part"])
        for item in lines
    ] == [(6480, None, None), (1010, "S01", "base"), (7680, "S01", "vat")]
    assert lines[2]["credit"] == 25.0
    assert lines[2]["description"] == "VAT S01"


def test_the_api_reads_the_vat_lines_back(client, books, test_user):
    created = client.post(
        "/journal-entries",
        json=api_body(books),
        headers=api_headers(test_user),
    ).get_json()

    read = client.get(
        f"/journal-entries/{created['id']}", headers=api_headers(test_user)
    ).get_json()
    listed = client.get(
        "/journal-entries", headers=api_headers(test_user)
    ).get_json()

    assert [item["vat_part"] for item in read["lines"]] == [
        None,
        "base",
        "vat",
    ]
    assert len(listed[0]["lines"]) == 3


def test_the_api_reverses_with_the_codes(client, books, test_user):
    created = client.post(
        "/journal-entries",
        json=api_body(books),
        headers=api_headers(test_user),
    ).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse",
        headers=api_headers(test_user),
    )

    assert res.status_code == 201, res.get_json()
    assert [
        (item["vat_code"], item["vat_part"]) for item in res.get_json()["lines"]
    ] == [(None, None), ("S01", "base"), ("S01", "vat")]


@pytest.mark.parametrize(
    "bad, status, message",
    [
        ({"vat_code": "X99"}, 422, "there is no VAT code X99"),
        ({"vat_code": "K020"}, 422, "cannot be used yet"),
        ({"vat_code": "S1"}, 422, "there is no VAT code S1"),
    ],
)
def test_the_api_refuses_a_bad_code(
    client, books, test_user, bad, status, message
):
    body = api_body(books)
    body["lines"][1].update(bad)

    res = client.post(
        "/journal-entries", json=body, headers=api_headers(test_user)
    )

    assert res.status_code == status
    assert message in res.get_json()["error"]


def test_the_api_refuses_a_code_when_not_registered(client, books, test_user):
    books["org"].vat_period_type = None

    res = client.post(
        "/journal-entries",
        json=api_body(books),
        headers=api_headers(test_user),
    )

    assert res.status_code == 422
    assert "not VAT-registered" in res.get_json()["error"]


def test_the_api_does_not_take_the_part_from_the_client(
    client, books, test_user
):
    body = api_body(books)
    body["lines"][1]["vat_part"] = "base"

    res = client.post(
        "/journal-entries", json=body, headers=api_headers(test_user)
    )

    assert res.status_code == 422
    assert "vat_part" in res.get_json()["errors"]["lines"]["1"]


def test_the_api_names_what_is_missing_when_the_lines_do_not_balance(
    client, books, test_user
):
    body = api_body(books)
    body["lines"][0]["debit"] = 100

    res = client.post(
        "/journal-entries", json=body, headers=api_headers(test_user)
    )

    assert res.status_code == 422
    assert "(with the VAT lines)" in res.get_json()["error"]
