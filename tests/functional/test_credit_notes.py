"""Credit notes: an invoice of its own kind that corrects an invoice
(app/invoice_posting.py, docs/invoice-posting-design.md, section 8)."""

import random
from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.chart import apply_starter_chart
from app.ledger import LedgerConflict, reverse_entry
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoice_setting import InvoiceSetting
from app.models.invoiceline import InvoiceLine
from app.models.ledger import FiscalYear, JournalEntry
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User
from app.reports import trial_balance, vat_report
from app.vat_periods import settle_period

D = Decimal
LATER = date(2026, 11, 1)


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def books(db_session, organization, test_user, country):
    organization.vat_period_type = "quarter"
    db_session.commit()
    apply_starter_chart(organization)
    accounts = {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }
    setting = InvoiceSetting(
        organization_id=organization.id,
        default_account_id=accounts[1010].id,
        default_deposit_account_id=accounts[6480].id,
        invoice_no_mode="sequential",
        next_invoice_no=1,
    )
    contact = Contact(
        organization_id=organization.id,
        name="Client",
        email="client@example.com",
        country_id=country.id,
    )
    other = Contact(
        organization_id=organization.id,
        name="Another client",
        email="another@example.com",
        country_id=country.id,
    )
    product = Product(
        organization_id=organization.id, name="Consulting", unit_price=100
    )
    db_session.add_all([setting, contact, other, product])
    db_session.commit()
    return {
        "org": organization,
        "user": test_user,
        "headers": headers(test_user),
        "accounts": accounts,
        "setting": setting,
        "contact": contact,
        "other_contact": other,
        "product": product,
    }


def line(books, quantity=1, price=100, code="S01", **extra):
    return {
        "product_id": books["product"].id,
        "description": "Work",
        "vat_code": code,
        "quantity": quantity,
        "unit_price": price,
        **extra,
    }


def invoice_body(books, lines, **extra):
    return {
        "organization_id": books["org"].id,
        "contact_id": books["contact"].id,
        "currency_id": "DKK",
        "invoice_date": "2026-02-10",
        "duedate": "2026-02-24",
        "lines": lines,
        **extra,
    }


def approved_invoice(client, books, lines=None, **extra):
    """An invoice that is approved: 1,250 with 250 VAT unless told otherwise."""
    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json=invoice_body(
            books,
            lines if lines is not None else [line(books, 10, 100)],
            **extra,
        ),
        headers=books["headers"],
    )
    assert res.status_code == 201, res.get_json()
    done = client.post(
        f"/organizations/{books['org'].id}/invoices/{res.get_json()['id']}"
        "/approve",
        json={},
        headers=books["headers"],
    )
    assert done.status_code == 200, done.get_json()
    return done.get_json()


def new_credit_note(client, books, invoice):
    return client.post(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}"
        "/credit-note",
        json={},
        headers=books["headers"],
    )


def draft_note(client, books, invoice):
    res = new_credit_note(client, books, invoice)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def save_note(client, books, note, lines, **extra):
    """Change the lines of a draft credit note (the others stay as they are)."""
    body = {
        "organization_id": books["org"].id,
        "contact_id": note["contact_id"],
        "currency_id": "DKK",
        "invoice_date": note["invoice_date"],
        "duedate": note["duedate"],
        "lines": lines,
        **extra,
    }
    return client.put(
        f"/organizations/{books['org'].id}/invoices/{note['id']}",
        json=body,
        headers=books["headers"],
    )


def approve(client, books, document, body=None):
    return client.post(
        f"/organizations/{books['org'].id}/invoices/{document['id']}/approve",
        json=body or {},
        headers=books["headers"],
    )


def note_lines(note):
    """The lines of a credit note as the API returns them, ready to send."""
    return [
        {
            key: item[key]
            for key in (
                "id",
                "invoice_id",
                "product_id",
                "description",
                "vat_code",
                "quantity",
                "unit_price",
            )
        }
        for item in note["lines"]
    ]


def credit_of(client, books, invoice, price):
    """A credit note of `price` net on a 100-per-unit line, approved."""
    note = draft_note(client, books, invoice)
    res = save_note(
        client, books, note, [line(books, 1, price, id=note["lines"][0]["id"])]
    )
    assert res.status_code == 200, res.get_json()
    done = approve(client, books, note)
    assert done.status_code == 200, done.get_json()
    return done.get_json()


def shown(books, entry):
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


def entry_of(document):
    return JournalEntry.query.filter_by(id=document["journal_entry_id"]).one()


def balances(books):
    report = trial_balance(books["org"].id)
    return {
        item["number"]: item["closing_balance"] for item in report["accounts"]
    }


# --- making a credit note --------------------------------------------------


def test_a_credit_note_is_made_from_an_approved_invoice_with_its_lines(
    client, db_session, books
):
    invoice = approved_invoice(
        client, books, [line(books, 10, 100), line(books, 2, 50, code="S23")]
    )

    res = new_credit_note(client, books, invoice)

    assert res.status_code == 201, res.get_json()
    note = res.get_json()
    assert note["kind"] == "credit_note"
    assert note["credits_invoice_id"] == invoice["id"]
    assert note["credits_invoice_no"] == invoice["invoice_no"]
    assert note["state"] == "draft"
    assert (
        note["invoice_no"] is None
    )  # sequential: the number comes with the approval
    assert note["contact_id"] == books["contact"].id
    assert note["currency_id"] == "DKK"
    assert note["invoice_date"] == date.today().isoformat()
    assert [
        (i["description"], i["vat_code"], i["quantity"], i["unit_price"])
        for i in note["lines"]
    ] == [("Work", "S01", 10.0, 100.0), ("Work", "S23", 2.0, 50.0)]
    # The amounts are positive, as on a printed credit note
    assert (note["amount"], note["vat_amount"], note["gross_amount"]) == (
        1100.0,
        250.0,
        1350.0,
    )
    assert [i["amount"] for i in note["lines"]] == [1000.0, 100.0]


def test_a_credit_note_is_an_invoice_that_can_be_found_like_one(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    listed = client.get("/invoices", headers=books["headers"]).get_json()
    fetched = client.get(f"/invoices/{note['id']}", headers=books["headers"])

    assert {(i["id"], i["kind"]) for i in listed} == {
        (invoice["id"], "invoice"),
        (note["id"], "credit_note"),
    }
    assert fetched.get_json()["kind"] == "credit_note"


def test_the_invoice_lists_its_credit_notes_and_what_they_credit(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    first = credit_of(client, books, invoice, 400)
    draft_note(client, books, invoice)

    body = client.get(
        f"/invoices/{invoice['id']}", headers=books["headers"]
    ).get_json()

    assert [
        (n["invoice_no"], n["state"], n["gross_amount"])
        for n in body["credit_notes"]
    ] == [
        (first["invoice_no"], "approved", 500.0),
        (None, "draft", 1250.0),
    ]
    # Only the approved ones credit anything
    assert body["credited_amount"] == 500.0


def test_a_credit_note_has_no_credit_notes_of_its_own(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    assert note["credit_notes"] == []
    assert note["credited_amount"] == 0.0


@pytest.mark.parametrize("what", ["draft", "credit note"])
def test_only_an_approved_invoice_can_be_credited(
    client, db_session, books, what
):
    invoice = approved_invoice(client, books)
    target = draft_note(client, books, invoice)
    if what == "draft":
        target = client.post(
            f"/organizations/{books['org'].id}/invoices",
            json=invoice_body(books, [line(books)], invoice_no=None),
            headers=books["headers"],
        ).get_json()
    else:
        target = approve(client, books, target).get_json()

    res = new_credit_note(client, books, target)

    assert res.status_code == 409
    # Only the credit note that was made first exists
    assert Invoice.query.filter_by(kind="credit_note").count() == 1


def test_a_credit_note_of_a_credit_note_says_to_post_a_new_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    res = new_credit_note(client, books, note)

    assert res.status_code == 409
    assert "new invoice" in res.get_json()["error"]


def test_an_invoice_that_is_credited_in_full_cannot_be_credited_again(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    approve(client, books, draft_note(client, books, invoice))

    res = new_credit_note(client, books, invoice)

    assert res.status_code == 409
    assert "credited in full" in res.get_json()["error"]


def test_an_invoice_of_nothing_cannot_be_credited(client, db_session, books):
    invoice = approved_invoice(
        client, books, [line(books, 1, 100), line(books, 1, -100)]
    )

    res = new_credit_note(client, books, invoice)

    assert res.status_code == 409
    assert "nothing to credit" in res.get_json()["error"]


def test_an_invoice_that_is_not_found_is_404(client, db_session, books):
    assert new_credit_note(client, books, {"id": 99999}).status_code == 404


def test_the_credit_note_needs_a_login(client, books):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices/1/credit-note", json={}
    )

    assert res.status_code == 401


def test_another_organization_cannot_credit_my_invoice(
    client, db_session, books, country
):
    invoice = approved_invoice(client, books)
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

    res = client.post(
        f"/organizations/{books['org'].id}/invoices/{invoice['id']}"
        "/credit-note",
        json={},
        headers=headers(user),
    )

    assert res.status_code == 404
    assert Invoice.query.filter_by(kind="credit_note").count() == 0


# --- editing the draft -----------------------------------------------------


def test_a_draft_credit_note_is_lowered_to_credit_part_of_the_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    res = save_note(
        client, books, note, [line(books, 4, 100, id=note["lines"][0]["id"])]
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["gross_amount"] == 500.0
    assert res.get_json()["kind"] == "credit_note"
    assert res.get_json()["credits_invoice_id"] == invoice["id"]


def test_the_customer_of_a_credit_note_is_the_customer_of_the_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    note["contact_id"] = books["other_contact"].id

    res = save_note(client, books, note, note_lines(note))

    assert res.status_code == 422
    assert "customer of the invoice" in res.get_json()["error"]


@pytest.mark.parametrize(
    "field",
    [
        {"kind": "invoice"},
        {"credits_invoice_id": 1},
        {"credits_invoice_no": "1"},
    ],
)
def test_the_client_cannot_change_what_a_credit_note_is(
    client, db_session, books, field
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    res = save_note(client, books, note, note_lines(note), **field)

    assert res.status_code == 422


@pytest.mark.parametrize(
    "field", [{"kind": "credit_note"}, {"credits_invoice_id": 1}]
)
def test_a_new_invoice_cannot_say_that_it_is_a_credit_note(
    client, db_session, books, field
):
    res = client.post(
        f"/organizations/{books['org'].id}/invoices",
        json=invoice_body(books, [line(books)], **field),
        headers=books["headers"],
    )

    assert res.status_code == 422
    assert Invoice.query.count() == 0


def test_a_draft_credit_note_can_be_deleted(client, db_session, books):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    res = client.delete(
        f"/organizations/{books['org'].id}/invoices/{note['id']}",
        headers=books["headers"],
    )

    assert res.status_code == 200
    assert Invoice.query.filter_by(id=note["id"]).count() == 0
    assert Invoice.query.filter_by(id=invoice["id"]).count() == 1


# --- approving it ----------------------------------------------------------


def test_a_credit_note_is_posted_the_other_way_round(client, db_session, books):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    res = approve(client, books, note)

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["state"] == "approved"
    assert body["kind"] == "credit_note"
    # The credit note has its number, from the series of the invoices
    assert (invoice["invoice_no"], body["invoice_no"]) == ("1", "2")
    assert (body["amount"], body["vat_amount"], body["gross_amount"]) == (
        1000.0,
        250.0,
        1250.0,
    )
    entry = entry_of(body)
    assert shown(books, entry) == [
        (6190, None, None, D("0.00"), D("1250.00")),
        (1010, "S01", "base", D("1000.00"), D("0.00")),
        (7680, "S01", "vat", D("250.00"), D("0.00")),
    ]
    assert entry.source_type == "credit_note"
    assert entry.source_id == note["id"]
    assert entry.description == "Credit note 2"
    assert entry.entry_date == date.today()
    # The customer is on the receivable line
    assert entry.lines[0].contact_id == books["contact"].id


def test_the_audit_log_names_the_invoice_that_was_credited(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    row = AuditLog.query.filter_by(
        action="credit_note.approved", entity_id=note["id"]
    ).one()

    assert row.details["invoice_no"] == "2"
    assert row.details["credits_invoice_no"] == "1"
    assert row.details["gross_amount"] == "1250.00"
    assert AuditLog.query.filter_by(action="invoice.approved").count() == 1


def test_an_invoice_and_its_credit_note_leave_nothing_in_the_books(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    approve(client, books, draft_note(client, books, invoice))

    after = balances(books)

    for number in (6190, 1010, 7680):
        assert after.get(number, D(0)) == D(0)
    assert trial_balance(books["org"].id)["balanced"]
    report = vat_report(books["org"].id, date(2026, 1, 1), date.today())
    assert report["sales_vat"] == D("0.00")
    assert report["boxes"]["c"] == D("0.00")
    assert report["ledger_check"]["ties"] is True


def test_a_credit_note_of_part_of_the_invoice_credits_that_part(
    client, db_session, books
):
    invoice = approved_invoice(client, books)

    note = credit_of(client, books, invoice, 400)

    assert note["gross_amount"] == 500.0
    after = balances(books)
    assert after[6190] == D("750.00")
    assert after[7680] == D("-150.00")
    assert after[1010] == D("-600.00")


def test_several_credit_notes_add_up_to_at_most_the_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)  # 1,250
    credit_of(client, books, invoice, 600)  # 750
    note = draft_note(client, books, invoice)
    save_note(
        client, books, note, [line(books, 1, 600, id=note["lines"][0]["id"])]
    )

    # 750 + 750 is more than 1,250
    res = approve(client, books, note)

    assert res.status_code == 409
    assert "credits more than the invoice" in res.get_json()["error"]
    assert JournalEntry.query.count() == 2  # the invoice and the first note
    stored = Invoice.query.filter_by(id=note["id"]).one()
    assert (stored.state, stored.invoice_no) == ("draft", None)

    # 400 more is exactly what is left
    save_note(
        client, books, note, [line(books, 1, 400, id=note["lines"][0]["id"])]
    )
    ok = approve(client, books, note)
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()["gross_amount"] == 500.0
    assert new_credit_note(client, books, invoice).status_code == 409


def test_two_drafts_cannot_each_credit_all_of_the_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    first = draft_note(client, books, invoice)
    second = draft_note(client, books, invoice)

    assert approve(client, books, first).status_code == 200
    res = approve(client, books, second)

    assert res.status_code == 409
    assert "credits more than the invoice" in res.get_json()["error"]


def test_a_credit_note_must_credit_something(client, db_session, books):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    save_note(
        client, books, note, [line(books, 1, -100, id=note["lines"][0]["id"])]
    )

    res = approve(client, books, note)

    assert res.status_code == 422
    assert "must credit something" in res.get_json()["error"]


def test_a_credit_note_of_only_text_has_nothing_to_book(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    save_note(
        client, books, note, [line(books, 1, 0, id=note["lines"][0]["id"])]
    )

    res = approve(client, books, note)

    assert res.status_code == 422
    assert "nothing to book" in res.get_json()["error"]


def test_a_credit_note_is_not_dated_before_its_invoice(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    note["invoice_date"] = "2026-02-09"
    save_note(client, books, note, note_lines(note))

    res = approve(client, books, note)

    assert res.status_code == 422
    assert "before the invoice" in res.get_json()["error"]


def test_a_credit_note_is_not_dated_in_the_future(client, db_session, books):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    note["invoice_date"] = "2099-01-01"
    save_note(client, books, note, note_lines(note))

    res = approve(client, books, note)

    assert res.status_code == 422
    assert "future" in res.get_json()["error"]


def test_a_credit_note_dated_in_a_settled_vat_period_is_refused(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    settle_period(books["org"].id, books["user"].id, LATER)
    note = draft_note(client, books, invoice)
    note["invoice_date"] = "2026-03-20"
    save_note(client, books, note, note_lines(note))

    res = approve(client, books, note)

    assert res.status_code == 409
    assert "is settled" in res.get_json()["error"]


def test_a_credit_note_in_a_closed_fiscal_year_is_refused(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    note["invoice_date"] = date.today().isoformat()
    save_note(client, books, note, note_lines(note))
    FiscalYear.query.filter_by(organization_id=books["org"].id).update(
        {"status": "closed"}
    )
    db_session.commit()
    entries = JournalEntry.query.count()

    res = approve(client, books, note)

    assert res.status_code == 409
    assert JournalEntry.query.count() == entries


def test_a_refused_credit_note_gives_its_number_back(client, db_session, books):
    invoice = approved_invoice(client, books)
    refused = draft_note(client, books, invoice)
    refused["invoice_date"] = "2026-02-09"
    save_note(client, books, refused, note_lines(refused))
    fine = draft_note(client, books, invoice)

    assert approve(client, books, refused).status_code == 422
    body = approve(client, books, fine).get_json()

    assert body["invoice_no"] == "2"


def test_a_credit_note_in_manual_mode_takes_the_number_given(
    client, db_session, books
):
    books["setting"].invoice_no_mode = "manual"
    db_session.commit()
    invoice = approved_invoice(client, books, invoice_no="1001")
    note = draft_note(client, books, invoice)

    res = approve(client, books, note, {"invoice_no": "K-1"})

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["invoice_no"] == "K-1"


def test_the_numbers_of_invoices_and_credit_notes_have_no_gap(
    client, db_session, books
):
    generator = random.Random(3)
    numbers = []
    invoices = []
    for _ in range(6):
        invoice = approved_invoice(client, books)
        numbers.append(int(invoice["invoice_no"]))
        invoices.append(invoice)
        if generator.random() < 0.7:
            note = draft_note(client, books, invoice)
            if generator.random() < 0.3:
                note["invoice_date"] = (
                    "2026-01-01"  # refused: before the invoice
                )
                save_note(client, books, note, note_lines(note))
            res = approve(client, books, note)
            if res.status_code == 200:
                numbers.append(int(res.get_json()["invoice_no"]))

    assert sorted(numbers) == list(range(1, len(numbers) + 1))


def test_an_organization_without_vat_credits_without_vat_codes(
    client, db_session, books
):
    books["org"].vat_period_type = None
    db_session.commit()
    invoice = approved_invoice(client, books, [line(books, 2, 500, code="S81")])

    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    assert shown(books, entry_of(note)) == [
        (6190, None, None, D("0.00"), D("1000.00")),
        (1010, None, None, D("1000.00"), D("0.00")),
    ]


def test_a_credit_note_with_vat_is_refused_when_the_organization_has_none(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)
    books["org"].vat_period_type = None
    db_session.commit()

    res = approve(client, books, note)

    assert res.status_code == 422
    assert "not VAT-registered" in res.get_json()["error"]


# --- locked ----------------------------------------------------------------


def test_an_approved_credit_note_cannot_be_changed_or_deleted(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    updated = save_note(client, books, note, note_lines(note))
    deleted = client.delete(
        f"/organizations/{books['org'].id}/invoices/{note['id']}",
        headers=books["headers"],
    )

    assert updated.status_code == 409
    assert deleted.status_code == 409
    assert Invoice.query.filter_by(id=note["id"]).count() == 1


def test_an_approved_credit_note_cannot_be_approved_again(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    res = approve(client, books, note)

    assert res.status_code == 409
    assert "credit note is already approved" in res.get_json()["error"]


def test_the_voucher_of_a_credit_note_cannot_be_reversed(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    note = approve(client, books, draft_note(client, books, invoice)).get_json()

    res = client.post(
        f"/journal-entries/{note['journal_entry_id']}/reverse",
        json={},
        headers=books["headers"],
    )

    assert res.status_code == 409
    assert "new invoice" in res.get_json()["error"]
    with pytest.raises(LedgerConflict):
        reverse_entry(
            books["org"].id, books["user"].id, note["journal_entry_id"]
        )


def test_the_invoice_that_was_credited_stays_as_it_was_posted(
    client, db_session, books
):
    invoice = approved_invoice(client, books)
    before = [
        (i.account_id, i.debit, i.credit) for i in entry_of(invoice).lines
    ]

    approve(client, books, draft_note(client, books, invoice))

    assert [
        (i.account_id, i.debit, i.credit) for i in entry_of(invoice).lines
    ] == before
    assert Invoice.query.filter_by(id=invoice["id"]).one().state == "approved"


# --- the database ----------------------------------------------------------


def make(db_session, books, **fields):
    return Invoice(
        organization_id=books["org"].id,
        contact_id=books["contact"].id,
        invoice_date=date(2026, 1, 1),
        duedate=date(2026, 1, 15),
        **fields,
    )


def test_the_database_wants_a_credit_note_to_refer_to_an_invoice(
    db_session, books
):
    db_session.add(make(db_session, books, kind="credit_note"))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_database_does_not_let_an_invoice_refer_to_another(
    db_session, books
):
    original = make(db_session, books)
    db_session.add(original)
    db_session.flush()
    db_session.add(make(db_session, books, credits_invoice_id=original.id))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_database_does_not_let_a_credit_note_correct_itself(
    db_session, books
):
    original = make(db_session, books)
    db_session.add(original)
    db_session.flush()
    note = make(
        db_session, books, kind="credit_note", credits_invoice_id=original.id
    )
    db_session.add(note)
    db_session.flush()
    note.credits_invoice_id = note.id

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_database_refuses_a_kind_that_does_not_exist(db_session, books):
    db_session.add(make(db_session, books, kind="memo"))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_lines_of_a_credit_note_are_its_own(client, db_session, books):
    invoice = approved_invoice(client, books)
    note = draft_note(client, books, invoice)

    ids = {i.id for i in InvoiceLine.query.filter_by(invoice_id=invoice["id"])}
    note_ids = {
        i.id for i in InvoiceLine.query.filter_by(invoice_id=note["id"])
    }

    assert ids and note_ids and not ids & note_ids


# --- random credit notes ---------------------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_the_books_agree_with_the_invoices_and_credit_notes(
    client, db_session, books, seed
):
    generator = random.Random(seed)
    gross = D("0")
    vat = D("0")
    for _ in range(generator.randint(1, 4)):
        lines = [
            line(
                books,
                generator.choice([1, 2, 3, 7]),
                generator.choice([100, 19.99, 1250, 0.335]),
                code=generator.choice(["S01", "S01", "S02", "S23"]),
            )
            for _ in range(generator.randint(1, 3))
        ]
        invoice = approved_invoice(client, books, lines)
        gross += D(str(invoice["gross_amount"]))
        vat += D(str(invoice["vat_amount"]))
        for _ in range(generator.randint(0, 2)):
            note = new_credit_note(client, books, invoice)
            if note.status_code != 201:
                break
            note = note.get_json()
            keep = [
                {**item, "quantity": generator.choice([1, 0.5, 2])}
                for item in note_lines(note)
                if generator.random() < 0.7
            ] or note_lines(note)[:1]
            save_note(client, books, note, keep)
            done = approve(client, books, note)
            if done.status_code == 200:
                body = done.get_json()
                gross -= D(str(body["gross_amount"]))
                vat -= D(str(body["vat_amount"]))
            else:
                assert done.status_code in (409, 422)

    after = balances(books)
    assert after.get(6190, D(0)) == gross
    assert trial_balance(books["org"].id)["balanced"]
    report = vat_report(books["org"].id, date(2026, 1, 1), date.today())
    assert report["sales_vat"] == vat
    assert report["ledger_check"]["ties"] is True
