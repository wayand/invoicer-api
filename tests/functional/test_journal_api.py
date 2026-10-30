"""The journal routes: post a manual entry, read it back, reverse it, and
close a fiscal year."""

from datetime import date, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.chart import apply_starter_chart
from app.models.account import Account
from app.models.organization import Organization
from app.models.user import User


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
        "bank": accounts[6480].id,
        "sales": accounts[1010].id,
        "vat": accounts[7680].id,
        "receivables": accounts[6190].id,
    }


def entry_body(books, **overrides) -> dict:
    body = {
        "entry_date": "2026-03-01",
        "description": "Sale for cash",
        "lines": [
            {"account_id": books["bank"], "debit": 125},
            {"account_id": books["sales"], "credit": 100},
            {"account_id": books["vat"], "credit": 25},
        ],
    }
    body.update(overrides)
    return body


def post_entry(client, books, **overrides):
    return client.post(
        "/journal-entries",
        json=entry_body(books, **overrides),
        headers=books["headers"],
    )


# --- posting ---------------------------------------------------------------


def test_a_manual_entry_is_posted(client, books):
    res = post_entry(client, books)

    assert res.status_code == 201, res.get_json()
    entry = res.get_json()
    assert entry["voucher_no"] == 1
    assert entry["entry_date"] == "2026-03-01"
    assert entry["description"] == "Sale for cash"
    assert entry["source_type"] == "manual"
    assert entry["created_by"] == books["user"].id
    assert entry["reverses_entry_id"] is None
    assert entry["reversed_by_entry_id"] is None
    assert [
        (line["line_no"], line["account_number"], line["debit"], line["credit"])
        for line in entry["lines"]
    ] == [(1, 6480, 125.0, 0.0), (2, 1010, 0.0, 100.0), (3, 7680, 0.0, 25.0)]
    assert entry["lines"][0]["account_name"] == "Bankkonto"


def test_voucher_numbers_follow_each_other(client, books):
    numbers = [
        post_entry(client, books).get_json()["voucher_no"],
        post_entry(client, books, entry_date="2027-01-15").get_json()[
            "voucher_no"
        ],
    ]

    assert numbers == [1, 2]


def test_amounts_are_rounded_half_up(client, books):
    res = post_entry(
        client,
        books,
        lines=[
            {"account_id": books["bank"], "debit": 10.005},
            {"account_id": books["sales"], "credit": 10.01},
        ],
    )

    assert res.status_code == 201, res.get_json()
    assert res.get_json()["lines"][0]["debit"] == 10.01


def test_an_unbalanced_entry_is_refused_with_the_reason(client, books):
    res = post_entry(
        client,
        books,
        lines=[
            {"account_id": books["bank"], "debit": 100},
            {"account_id": books["sales"], "credit": 90},
        ],
    )

    assert res.status_code == 422
    assert "does not balance" in res.get_json()["error"]


def test_an_entry_in_a_closed_year_is_a_conflict(client, books):
    year = client.get("/fiscal-years", headers=books["headers"])
    assert year.get_json() == []
    first = post_entry(client, books).get_json()
    year_id = client.get("/fiscal-years", headers=books["headers"]).get_json()[
        0
    ]["id"]
    client.post(f"/fiscal-years/{year_id}/close", headers=books["headers"])

    res = post_entry(client, books)

    assert first["voucher_no"] == 1
    assert res.status_code == 409
    assert "is closed" in res.get_json()["error"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"entry_date": None}, "entry_date"),
        ({"entry_date": "not a date"}, "entry_date"),
        ({"description": ""}, "description"),
        ({"description": "x" * 256}, "description"),
        ({"lines": []}, "lines"),
        ({"lines": [{"account_id": 1, "debit": 5}]}, "lines"),
    ],
)
def test_a_bad_entry_is_refused_with_the_field(client, books, overrides, field):
    res = post_entry(client, books, **overrides)

    assert res.status_code == 422
    assert field in res.get_json()["errors"]


def test_missing_fields_are_listed(client, books):
    res = client.post("/journal-entries", json={}, headers=books["headers"])

    assert res.status_code == 422
    assert set(res.get_json()["errors"]) == {
        "entry_date",
        "description",
        "lines",
    }


@pytest.mark.parametrize("amount", ["100", True, None, [100]])
def test_an_amount_must_be_a_number(client, books, amount):
    lines = entry_body(books)["lines"]
    lines[0]["debit"] = amount

    res = post_entry(client, books, lines=lines)

    assert res.status_code == 422
    assert "debit" in res.get_json()["errors"]["lines"]["0"]


def test_a_negative_amount_is_refused(client, books):
    lines = entry_body(books)["lines"]
    lines[0]["debit"] = -125

    res = post_entry(client, books, lines=lines)

    assert res.status_code == 422
    assert "debit" in res.get_json()["errors"]["lines"]["0"]


def test_an_unknown_field_is_refused(client, books):
    lines = entry_body(books)["lines"]
    lines[0]["amount"] = 125

    res = post_entry(client, books, lines=lines, voucher_no=99)

    assert res.status_code == 422
    errors = res.get_json()["errors"]
    assert "voucher_no" in errors
    assert "amount" in errors["lines"]["0"]


def test_an_entry_cannot_set_what_the_server_decides(client, books):
    res = post_entry(
        client, books, voucher_no=99, created_by=1, source_type="x"
    )

    assert res.status_code == 422
    assert {"voucher_no", "created_by", "source_type"} <= set(
        res.get_json()["errors"]
    )


def test_an_entry_needs_a_body(client, books):
    res = client.post("/journal-entries", headers=books["headers"])

    assert res.status_code == 422


def test_an_unknown_account_is_refused(client, books):
    lines = entry_body(books)["lines"]
    lines[0]["account_id"] = 999999

    res = post_entry(client, books, lines=lines)

    assert res.status_code == 422
    assert "no account with id 999999" in res.get_json()["error"]


# --- reading ---------------------------------------------------------------


def test_an_entry_can_be_read_back(client, books):
    created = post_entry(client, books).get_json()

    res = client.get(
        f"/journal-entries/{created['id']}", headers=books["headers"]
    )

    assert res.status_code == 200
    assert res.get_json() == created


def test_an_unknown_entry_is_not_found(client, books):
    res = client.get("/journal-entries/999999", headers=books["headers"])

    assert res.status_code == 404


def test_the_list_is_newest_voucher_first(client, books):
    for day in ("2026-01-10", "2026-02-10", "2026-03-10"):
        post_entry(client, books, entry_date=day)

    res = client.get("/journal-entries", headers=books["headers"])

    assert [item["voucher_no"] for item in res.get_json()] == [3, 2, 1]


def test_the_list_can_be_limited_and_paged(client, books):
    for _ in range(3):
        post_entry(client, books)

    first = client.get("/journal-entries?limit=2", headers=books["headers"])
    rest = client.get(
        "/journal-entries?limit=2&offset=2", headers=books["headers"]
    )

    assert [item["voucher_no"] for item in first.get_json()] == [3, 2]
    assert [item["voucher_no"] for item in rest.get_json()] == [1]


def test_the_list_can_be_for_one_fiscal_year(client, books):
    post_entry(client, books, entry_date="2026-03-01")
    post_entry(client, books, entry_date="2027-03-01")
    years = client.get("/fiscal-years", headers=books["headers"]).get_json()
    first_year = next(
        year["id"] for year in years if year["start_date"] == "2026-01-01"
    )

    res = client.get(
        f"/journal-entries?fiscal_year_id={first_year}",
        headers=books["headers"],
    )

    assert [item["voucher_no"] for item in res.get_json()] == [1]


# --- reversing -------------------------------------------------------------


def test_an_entry_is_reversed(client, books):
    created = post_entry(client, books).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse",
        json={"entry_date": "2026-03-02", "description": "Wrong customer"},
        headers=books["headers"],
    )

    assert res.status_code == 201, res.get_json()
    reversal = res.get_json()
    assert reversal["voucher_no"] == 2
    assert reversal["reverses_entry_id"] == created["id"]
    assert reversal["source_type"] == "reversal"
    assert reversal["description"] == "Wrong customer"
    assert [
        (line["account_number"], line["debit"], line["credit"])
        for line in reversal["lines"]
    ] == [(6480, 0.0, 125.0), (1010, 100.0, 0.0), (7680, 25.0, 0.0)]


def test_the_original_shows_what_reversed_it(client, books):
    created = post_entry(client, books).get_json()
    reversal = client.post(
        f"/journal-entries/{created['id']}/reverse", headers=books["headers"]
    ).get_json()

    original = client.get(
        f"/journal-entries/{created['id']}", headers=books["headers"]
    ).get_json()
    listed = client.get("/journal-entries", headers=books["headers"]).get_json()

    assert original["reversed_by_entry_id"] == reversal["id"]
    assert {item["id"]: item["reversed_by_entry_id"] for item in listed} == {
        created["id"]: reversal["id"],
        reversal["id"]: None,
    }


def test_a_reversal_needs_no_body_and_is_dated_today(client, books):
    created = post_entry(client, books).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse", headers=books["headers"]
    )

    assert res.status_code == 201
    assert res.get_json()["entry_date"] == date.today().isoformat()
    assert res.get_json()["description"].startswith("Reversal of voucher 1")


def test_a_reversal_is_not_dated_before_a_future_dated_entry(client, books):
    later = (date.today() + timedelta(days=3)).isoformat()
    created = post_entry(client, books, entry_date=later).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse", headers=books["headers"]
    )

    assert res.status_code == 201
    assert res.get_json()["entry_date"] == later


def test_an_entry_cannot_be_reversed_twice(client, books):
    created = post_entry(client, books).get_json()
    url = f"/journal-entries/{created['id']}/reverse"
    client.post(url, headers=books["headers"])

    res = client.post(url, headers=books["headers"])

    assert res.status_code == 409
    assert "already reversed" in res.get_json()["error"]


def test_a_reversal_cannot_be_reversed(client, books):
    created = post_entry(client, books).get_json()
    reversal = client.post(
        f"/journal-entries/{created['id']}/reverse", headers=books["headers"]
    ).get_json()

    res = client.post(
        f"/journal-entries/{reversal['id']}/reverse", headers=books["headers"]
    )

    assert res.status_code == 409


def test_a_bad_reversal_date_is_refused(client, books):
    created = post_entry(client, books).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse",
        json={"entry_date": "tomorrow"},
        headers=books["headers"],
    )

    assert res.status_code == 422
    assert "entry_date" in res.get_json()["errors"]


def test_an_unknown_entry_cannot_be_reversed(client, books):
    res = client.post(
        "/journal-entries/999999/reverse", headers=books["headers"]
    )

    assert res.status_code == 404


# --- fiscal years ----------------------------------------------------------


def test_fiscal_years_are_listed_newest_first(client, books):
    post_entry(client, books, entry_date="2026-03-01")
    post_entry(client, books, entry_date="2027-03-01")

    res = client.get("/fiscal-years", headers=books["headers"])

    assert [
        (year["start_date"], year["end_date"], year["status"])
        for year in res.get_json()
    ] == [
        ("2027-01-01", "2027-12-31", "open"),
        ("2026-01-01", "2026-12-31", "open"),
    ]


def test_a_fiscal_year_is_closed_once(client, books):
    post_entry(client, books)
    year_id = client.get("/fiscal-years", headers=books["headers"]).get_json()[
        0
    ]["id"]

    first = client.post(
        f"/fiscal-years/{year_id}/close", headers=books["headers"]
    )
    second = client.post(
        f"/fiscal-years/{year_id}/close", headers=books["headers"]
    )

    assert first.status_code == 200
    assert first.get_json()["status"] == "closed"
    assert second.status_code == 409


def test_an_unknown_fiscal_year_cannot_be_closed(client, books):
    res = client.post("/fiscal-years/999999/close", headers=books["headers"])

    assert res.status_code == 404


# --- who may do what -------------------------------------------------------

ROUTES = [
    ("POST", "/journal-entries"),
    ("GET", "/journal-entries"),
    ("GET", "/journal-entries/1"),
    ("POST", "/journal-entries/1/reverse"),
    ("GET", "/fiscal-years"),
    ("POST", "/fiscal-years/1/close"),
]


@pytest.mark.parametrize(("method", "url"), ROUTES)
def test_every_route_needs_a_login(client, method, url):
    res = client.open(url, method=method, json={})

    assert res.status_code == 401


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
    return headers(user)


def test_another_organization_cannot_read_an_entry(client, books, stranger):
    created = post_entry(client, books).get_json()

    res = client.get(f"/journal-entries/{created['id']}", headers=stranger)

    assert res.status_code == 404


def test_another_organization_cannot_reverse_an_entry(client, books, stranger):
    created = post_entry(client, books).get_json()

    res = client.post(
        f"/journal-entries/{created['id']}/reverse", headers=stranger
    )

    assert res.status_code == 404
    assert (
        client.get(
            f"/journal-entries/{created['id']}", headers=books["headers"]
        ).get_json()["reversed_by_entry_id"]
        is None
    )


def test_another_organization_sees_only_its_own_entries_and_years(
    client, books, stranger
):
    post_entry(client, books)

    entries = client.get("/journal-entries", headers=stranger)
    years = client.get("/fiscal-years", headers=stranger)

    assert entries.get_json() == []
    assert years.get_json() == []


def test_another_organization_cannot_close_a_fiscal_year(
    client, books, stranger
):
    post_entry(client, books)
    year_id = client.get("/fiscal-years", headers=books["headers"]).get_json()[
        0
    ]["id"]

    res = client.post(f"/fiscal-years/{year_id}/close", headers=stranger)

    assert res.status_code == 404


def test_an_account_of_another_organization_cannot_be_used(
    client, books, db_session, stranger
):
    theirs = (
        Account.query.join(Organization)
        .filter(Organization.slug == "other-aps", Account.number == 6480)
        .one()
    )
    lines = entry_body(books)["lines"]
    lines[0]["account_id"] = theirs.id

    res = post_entry(client, books, lines=lines)

    assert res.status_code == 422
    assert "no account with id" in res.get_json()["error"]
