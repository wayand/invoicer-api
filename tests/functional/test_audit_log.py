"""The audit log: what is written, in the same transaction as the change,
and that it cannot be changed (docs/ledger-design.md)."""

from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app.ledger as ledger_module
from app.audit import record
from app.chart import apply_starter_chart
from app.ledger import (
    LedgerError,
    LineInput,
    close_fiscal_year,
    post_entry,
    reverse_entry,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.ledger import JournalEntry
from app.models.organization import Organization
from app.models.user import User

D = Decimal


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
        "bank": accounts[6480],
        "sales": accounts[1010],
        "accounts": accounts,
    }


def post(books, day=date(2026, 3, 1), amount="125.50"):
    return post_entry(
        books["org"].id,
        books["user"].id,
        day,
        "A sale",
        [
            LineInput(account_id=books["bank"].id, debit=D(amount)),
            LineInput(account_id=books["sales"].id, credit=D(amount)),
        ],
    )


def rows(books, **filters):
    return (
        AuditLog.query.filter_by(organization_id=books["org"].id, **filters)
        .order_by(AuditLog.id)
        .all()
    )


def actions(books):
    return [row.action for row in rows(books)]


# --- the log cannot be changed ---------------------------------------------


def logged(books):
    return record(
        books["org"].id,
        books["user"].id,
        "journal_entry.posted",
        "journal_entry",
        1,
        {"voucher_no": 1},
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET action = 'fiscal_year.closed'",
        "UPDATE audit_log SET details = '{}'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ],
)
def test_a_row_cannot_be_changed_or_deleted(db_session, books, statement):
    logged(books)
    db_session.commit()

    with pytest.raises(IntegrityError) as error:
        db_session.execute(text(statement))
    db_session.rollback()

    assert "the audit log is append-only" in str(error.value)
    assert len(rows(books)) == 1


def test_a_row_gets_its_time_from_the_database(db_session, books):
    row = logged(books)
    db_session.commit()

    assert row.occurred_at is not None
    assert row.occurred_at.tzinfo is not None


@pytest.mark.parametrize(
    "action", ["posted", "Journal.posted", "journal_entry.", "a.b.c", ""]
)
def test_an_action_is_an_entity_a_dot_and_a_verb(db_session, books, action):
    with pytest.raises(IntegrityError) as error:
        record(books["org"].id, books["user"].id, action, "x", 1)
    db_session.rollback()

    assert "ck_audit_log_action" in str(error.value)


def test_a_row_needs_a_user_of_the_database(db_session, books):
    with pytest.raises(IntegrityError):
        record(books["org"].id, 999999, "journal_entry.posted", "x", 1)
    db_session.rollback()


def test_the_details_are_stored_as_plain_json(db_session, books):
    row = record(
        books["org"].id,
        books["user"].id,
        "journal_entry.posted",
        "journal_entry",
        1,
        {"day": date(2026, 3, 1), "total": D("125.50"), "nested": [D("1")]},
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(AuditLog, row.id)

    assert stored.details == {
        "day": "2026-03-01",
        "total": "125.50",
        "nested": ["1"],
    }


# --- posting ---------------------------------------------------------------


def test_a_posting_is_logged_with_who_and_what(db_session, books):
    entry = post(books)

    [first_year, posted] = rows(books)

    assert first_year.action == "fiscal_year.opened"
    assert posted.action == "journal_entry.posted"
    assert (posted.entity_type, posted.entity_id) == ("journal_entry", entry.id)
    assert posted.user_id == books["user"].id
    assert posted.details == {
        "voucher_no": 1,
        "entry_date": "2026-03-01",
        "fiscal_year_id": entry.fiscal_year_id,
        "source_type": "manual",
        "line_count": 2,
        "debit_total": "125.50",
    }


def test_the_log_does_not_copy_the_description(db_session, books):
    post(books)

    assert "A sale" not in str([row.details for row in rows(books)])


def test_the_calendar_year_is_logged_when_it_is_opened_and_only_then(
    db_session, books
):
    post(books, date(2026, 3, 1))
    post(books, date(2026, 4, 1))
    post(books, date(2027, 1, 5))

    opened = rows(books, action="fiscal_year.opened")

    assert [row.details["start_date"] for row in opened] == [
        "2026-01-01",
        "2027-01-01",
    ]
    assert opened[0].details["end_date"] == "2026-12-31"
    assert len(rows(books, action="journal_entry.posted")) == 3


def test_a_refused_posting_leaves_no_log(db_session, books):
    with pytest.raises(LedgerError):
        post_entry(
            books["org"].id,
            books["user"].id,
            date(2026, 3, 1),
            "Unbalanced",
            [
                LineInput(account_id=books["bank"].id, debit=D("10")),
                LineInput(account_id=books["sales"].id, credit=D("9")),
            ],
        )

    assert rows(books) == []


def test_a_posting_that_fails_halfway_leaves_no_log(
    db_session, books, monkeypatch
):
    def failing(**kwargs):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(ledger_module, "JournalLine", failing)
    with pytest.raises(RuntimeError):
        post(books)
    monkeypatch.undo()

    # not even the opening of the fiscal year survived
    assert rows(books) == []
    assert (
        JournalEntry.query.filter_by(organization_id=books["org"].id).count()
        == 0
    )


def test_every_entry_has_a_log_row(db_session, books):
    original = post(books)
    post(books, date(2027, 2, 1))
    reverse_entry(books["org"].id, books["user"].id, original.id)

    unlogged = db_session.execute(
        text(
            """
            SELECT e.id FROM journal_entries e
            WHERE e.organization_id = :org AND NOT EXISTS (
                SELECT 1 FROM audit_log a
                WHERE a.organization_id = e.organization_id
                  AND a.action = 'journal_entry.posted'
                  AND a.entity_type = 'journal_entry' AND a.entity_id = e.id)
            """
        ),
        {"org": books["org"].id},
    ).all()

    assert unlogged == []


# --- reversing and closing -------------------------------------------------


def test_a_reversal_is_logged_on_both_entries(db_session, books):
    original = post(books)

    reversal = reverse_entry(
        books["org"].id,
        books["user"].id,
        original.id,
        entry_date=date(2026, 3, 2),
    )

    [reversed_row] = rows(books, action="journal_entry.reversed")
    assert reversed_row.entity_id == original.id
    assert reversed_row.details == {
        "voucher_no": 1,
        "reversal_entry_id": reversal.id,
        "reversal_voucher_no": 2,
    }
    posted = rows(books, action="journal_entry.posted")
    assert [row.entity_id for row in posted] == [original.id, reversal.id]
    assert posted[1].details["source_type"] == "reversal"


def test_a_refused_reversal_leaves_no_log(db_session, books):
    original = post(books)
    reverse_entry(books["org"].id, books["user"].id, original.id)
    before = len(rows(books))

    with pytest.raises(LedgerError):
        reverse_entry(books["org"].id, books["user"].id, original.id)

    assert len(rows(books)) == before


def test_closing_a_fiscal_year_is_logged(db_session, books):
    entry = post(books)

    close_fiscal_year(books["org"].id, entry.fiscal_year_id, books["user"].id)

    [closed] = rows(books, action="fiscal_year.closed")
    assert (closed.entity_type, closed.entity_id) == (
        "fiscal_year",
        entry.fiscal_year_id,
    )
    assert closed.user_id == books["user"].id
    assert closed.details == {
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }


def test_a_refused_close_leaves_no_log(db_session, books):
    entry = post(books)
    close_fiscal_year(books["org"].id, entry.fiscal_year_id, books["user"].id)

    with pytest.raises(LedgerError):
        close_fiscal_year(
            books["org"].id, entry.fiscal_year_id, books["user"].id
        )

    assert len(rows(books, action="fiscal_year.closed")) == 1


# --- through the API -------------------------------------------------------


def api_post(client, books, **overrides):
    body = {
        "entry_date": "2026-03-01",
        "description": "A sale",
        "lines": [
            {"account_id": books["bank"].id, "debit": 125},
            {"account_id": books["sales"].id, "credit": 125},
        ],
    }
    body.update(overrides)
    return client.post("/journal-entries", json=body, headers=books["headers"])


def test_the_log_is_read_newest_first_with_the_name_of_the_user(client, books):
    created = api_post(client, books).get_json()

    res = client.get("/audit-log", headers=books["headers"])

    assert res.status_code == 200
    log = res.get_json()
    assert [item["action"] for item in log] == [
        "journal_entry.posted",
        "fiscal_year.opened",
    ]
    assert log[0]["entity_id"] == created["id"]
    assert log[0]["user_name"] == "test name"
    assert log[0]["details"]["voucher_no"] == 1
    assert log[0]["occurred_at"]


def test_the_log_can_be_filtered_and_paged(client, books):
    first = api_post(client, books).get_json()
    api_post(client, books)
    api_post(client, books)
    client.post(
        f"/journal-entries/{first['id']}/reverse", headers=books["headers"]
    )

    by_action = client.get(
        "/audit-log?action=journal_entry.reversed", headers=books["headers"]
    ).get_json()
    by_entity = client.get(
        f"/audit-log?entity_type=journal_entry&entity_id={first['id']}",
        headers=books["headers"],
    ).get_json()
    page = client.get(
        "/audit-log?limit=2&offset=1", headers=books["headers"]
    ).get_json()

    assert [item["entity_id"] for item in by_action] == [first["id"]]
    assert [item["action"] for item in by_entity] == [
        "journal_entry.reversed",
        "journal_entry.posted",
    ]
    assert len(page) == 2


def test_closing_a_year_through_the_api_is_logged(client, books):
    api_post(client, books)
    year = client.get("/fiscal-years", headers=books["headers"]).get_json()[0]

    client.post(f"/fiscal-years/{year['id']}/close", headers=books["headers"])

    [closed] = client.get(
        "/audit-log?action=fiscal_year.closed", headers=books["headers"]
    ).get_json()
    assert closed["entity_id"] == year["id"]


def test_the_log_needs_a_login(client):
    assert client.get("/audit-log").status_code == 401


def test_another_organization_sees_none_of_it(
    client, db_session, books, country
):
    api_post(client, books)
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

    res = client.get("/audit-log", headers=headers(user))

    assert res.get_json() == []


# --- accounts --------------------------------------------------------------


def account_body(client, books, number) -> dict:
    found = client.get(
        f"/accounts/{books['accounts'][number].id}", headers=books["headers"]
    ).get_json()
    skip = {"id", "account_type", "account_group", "created_at"}
    skip |= {"updated_at", "standard_account", "system_role"}
    return {key: value for key, value in found.items() if key not in skip}


def test_a_new_account_is_logged(client, books):
    existing = books["accounts"][2450]

    res = client.post(
        "/accounts",
        json={
            "name": "Nyt konto",
            "number": 2999,
            "account_type_id": existing.account_type_id,
            "account_group_id": existing.account_group_id,
        },
        headers=books["headers"],
    )

    assert res.status_code == 201, res.get_json()
    [created] = client.get(
        "/audit-log?action=account.created", headers=books["headers"]
    ).get_json()
    assert created["entity_id"] == res.get_json()["id"]
    assert created["details"]["number"] == 2999
    assert created["details"]["name"] == "Nyt konto"


def test_a_renamed_account_is_logged_with_what_it_was(client, books):
    body = account_body(client, books, 2450)
    body.update(name="Kontorartikler og papir", number=2455)

    res = client.put(
        f"/accounts/{books['accounts'][2450].id}",
        json=body,
        headers=books["headers"],
    )

    assert res.status_code == 200, res.get_json()
    [changed] = client.get(
        "/audit-log?action=account.updated", headers=books["headers"]
    ).get_json()
    assert changed["entity_id"] == books["accounts"][2450].id
    assert changed["details"] == {
        "changes": {
            "name": {
                "from": "Kontorartikler",
                "to": "Kontorartikler og papir",
            },
            "number": {"from": 2450, "to": 2455},
        }
    }


def test_saving_an_account_without_a_change_is_not_logged(client, books):
    body = account_body(client, books, 2450)

    res = client.put(
        f"/accounts/{books['accounts'][2450].id}",
        json=body,
        headers=books["headers"],
    )

    assert res.status_code == 200, res.get_json()
    assert (
        client.get(
            "/audit-log?action=account.updated", headers=books["headers"]
        ).get_json()
        == []
    )


def test_bank_numbers_are_not_copied_into_the_log(client, books):
    body = account_body(client, books, 6480)
    body.update(bank_account_number=1234567890, bank_registration_number=1234)

    res = client.put(
        f"/accounts/{books['bank'].id}", json=body, headers=books["headers"]
    )

    assert res.status_code == 200, res.get_json()
    [changed] = client.get(
        "/audit-log?action=account.updated", headers=books["headers"]
    ).get_json()
    assert changed["details"] == {"changes": {}, "bank_details_changed": True}
    assert "1234567890" not in str(changed)


def test_a_refused_account_change_leaves_no_log(client, books):
    body = account_body(client, books, 2450)
    body["number"] = 2410  # in use

    res = client.put(
        f"/accounts/{books['accounts'][2450].id}",
        json=body,
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert (
        client.get(
            "/audit-log?action=account.updated", headers=books["headers"]
        ).get_json()
        == []
    )
