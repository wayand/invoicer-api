"""The VAT codes (docs/vat-design.md): the table against the official file,
the guards on it, the route, the default code of an account and the VAT
period of an organization."""

from datetime import date
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.chart import apply_starter_chart
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.organization import Organization
from app.models.vat_code import VatCode
from app.standard_chart import standard_vat_codes
from app.vat import vat_code_rows

D = Decimal


def headers(user) -> dict:
    token = create_access_token(
        identity=user.email, additional_claims={"tv": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def chart(db_session, organization):
    apply_starter_chart(organization)
    return {
        item.number: item
        for item in Account.query.filter_by(organization_id=organization.id)
    }


def code_id(code: str) -> int:
    return VatCode.query.filter_by(code=code).one().id


def as_app_sends(account_json: dict) -> dict:
    skip = {"id", "account_type", "account_group"}
    skip |= {"created_at", "updated_at", "standard_account", "system_role"}
    return {
        key: value for key, value in account_json.items() if key not in skip
    }


# --- the table -------------------------------------------------------------


def test_the_table_has_the_rows_of_the_official_list(db_session):
    rows = {row["code"]: row for row in vat_code_rows()}
    stored = VatCode.query.order_by(VatCode.id).all()

    assert [item.code for item in stored] == [
        code.new_code for code in standard_vat_codes()
    ]
    for item in stored:
        row = rows[item.code]
        assert item.legacy_code == row["legacy_code"]
        assert item.name == row["name"]
        assert item.title == row["title"]
        assert item.applies_to == row["applies_to"]
        assert item.rate == row["rate"]
        assert item.deduction == row["deduction"]
        assert item.direction == row["direction"]
        assert item.base_box == row["base_box"]
        assert item.is_supported == row["is_supported"]
        assert item.deferred_reason == row["deferred_reason"]
        assert item.valid_from == date.fromisoformat(row["valid_from"])
        assert item.valid_to is None


def test_the_rates_come_out_as_fractions(db_session):
    assert VatCode.query.filter_by(code="S01").one().rate == D("0.2500")
    assert VatCode.query.filter_by(code="K070").one().deduction == D("0.2500")
    assert VatCode.query.filter_by(code="S81").one().rate is None


def raw_insert(db_session, **changes):
    row = {
        "code": "S99",
        "legacy_code": "S-99",
        "name": "Test",
        "title": "Test",
        "applies_to": "sales",
        "rate": D("0.25"),
        "deduction": None,
        "direction": "output",
        "base_box": None,
        "is_supported": True,
        "deferred_reason": None,
        "valid_from": date(2025, 12, 1),
        "valid_to": None,
    }
    row.update(changes)
    db_session.execute(
        text(
            "INSERT INTO vat_codes (code, legacy_code, name, title, "
            "applies_to, rate, deduction, direction, base_box, is_supported, "
            "deferred_reason, valid_from, valid_to) VALUES (:code, "
            ":legacy_code, :name, :title, :applies_to, :rate, :deduction, "
            ":direction, :base_box, :is_supported, :deferred_reason, "
            ":valid_from, :valid_to)"
        ),
        row,
    )
    db_session.flush()


def test_a_valid_row_can_be_added(db_session):
    raw_insert(db_session)

    assert VatCode.query.filter_by(code="S99").count() == 1


@pytest.mark.parametrize(
    "changes, constraint",
    [
        ({"code": "S01"}, "vat_codes_code_key"),
        ({"legacy_code": "S1"}, "vat_codes_legacy_code_key"),
        ({"applies_to": "both"}, "ck_vat_codes_applies_to"),
        ({"direction": "sideways"}, "ck_vat_codes_direction"),
        ({"base_box": "d"}, "ck_vat_codes_base_box"),
        (
            {
                "is_supported": False,
                "direction": None,
                "deferred_reason": "later",
            },
            "ck_vat_codes_deferred_reason",
        ),
        # Supported, but with no direction
        ({"direction": None}, "ck_vat_codes_supported"),
        # Supported, and deferred too
        ({"deferred_reason": "oss"}, "ck_vat_codes_supported"),
        # Deferred, but classified
        (
            {"is_supported": False, "deferred_reason": "oss"},
            "ck_vat_codes_supported",
        ),
        # Deferred, with no reason
        (
            {"is_supported": False, "direction": None},
            "ck_vat_codes_supported",
        ),
        ({"rate": D("1.5")}, "ck_vat_codes_rate"),
        ({"rate": D("-0.1")}, "ck_vat_codes_rate"),
        ({"deduction": D("1.5")}, "ck_vat_codes_deduction"),
        ({"valid_to": date(2025, 1, 1)}, "ck_vat_codes_valid"),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_the_database_refuses_a_row_that_breaks_a_rule(
    db_session, changes, constraint
):
    with pytest.raises(IntegrityError) as error:
        raw_insert(db_session, **changes)

    assert constraint in str(error.value)


# --- the route -------------------------------------------------------------


def test_the_codes_need_a_login(client):
    assert client.get("/vat-codes").status_code == 401


def test_the_route_returns_every_code_in_the_order_of_the_list(
    client, test_user
):
    res = client.get("/vat-codes", headers=headers(test_user))

    assert res.status_code == 200
    body = res.get_json()
    assert [item["code"] for item in body] == [
        code.new_code for code in standard_vat_codes()
    ]
    assert sum(item["is_supported"] for item in body) == 22


def test_a_code_is_returned_with_what_a_screen_needs(client, test_user):
    res = client.get("/vat-codes", headers=headers(test_user))

    by_code = {item["code"]: item for item in res.get_json()}
    assert by_code["K070"] == {
        "id": code_id("K070"),
        "code": "K070",
        "legacy_code": "K25A",
        "name": "K_DK_ReprFradragFuld",
        "title": "Repræsentationsmoms, delvist fradragsberettiget (25%)",
        "applies_to": "purchases",
        "rate": 0.25,
        "deduction": 0.25,
        "direction": "input",
        "base_box": None,
        "is_supported": True,
        "deferred_reason": None,
        "valid_from": "2025-12-01",
        "valid_to": None,
    }
    assert by_code["K020"]["is_supported"] is False
    assert by_code["K020"]["deferred_reason"] == "variable_deduction"
    assert by_code["K020"]["direction"] is None
    assert by_code["K020"]["deduction"] is None
    assert by_code["S81"]["rate"] is None


# --- the default code of an account ---------------------------------------


def test_the_starter_chart_gives_an_account_its_default_code(db_session, chart):
    expected = {
        1010: "S01",
        1050: "S21",
        1150: "S23",
        1610: "K010",
        1630: "K210",
        1710: "K260",
        1910: "K070",
        2390: "K030",
        2450: "K010",
    }
    for number, code in expected.items():
        assert chart[number].default_vat_code_id == code_id(code), number
    # No default: no VAT, or a treatment that is not decided
    for number in (2030, 2650, 2470, 2540, 1650, 6480, 7680):
        assert chart[number].default_vat_code_id is None, number
    assert sum(1 for item in chart.values() if item.default_vat_code_id) == 22


def test_an_account_that_was_there_gets_a_default_it_has_none_of(
    db_session, organization
):
    apply_starter_chart(organization)
    account = Account.query.filter_by(
        organization_id=organization.id, number=1010
    ).one()
    account.default_vat_code_id = None
    db_session.commit()

    result = apply_starter_chart(organization)

    assert result.adopted == [1010]
    assert account.default_vat_code_id == code_id("S01")


def test_an_account_keeps_the_default_it_was_given(db_session, organization):
    apply_starter_chart(organization)
    account = Account.query.filter_by(
        organization_id=organization.id, number=2450
    ).one()
    account.default_vat_code_id = code_id("K030")
    db_session.commit()

    result = apply_starter_chart(organization)

    assert not result.adopted
    assert account.default_vat_code_id == code_id("K030")


def test_an_account_is_returned_with_its_default_code(client, test_user, chart):
    res = client.get(f"/accounts/{chart[1010].id}", headers=headers(test_user))

    assert res.get_json()["default_vat_code_id"] == code_id("S01")


def put(client, user, account, **changes):
    sent = as_app_sends(
        client.get(f"/accounts/{account.id}", headers=headers(user)).get_json()
    )
    sent.update(changes)
    return client.put(
        f"/accounts/{account.id}", json=sent, headers=headers(user)
    )


def test_an_account_can_be_given_another_default_code(
    client, db_session, test_user, chart
):
    res = put(
        client, test_user, chart[2450], default_vat_code_id=code_id("K030")
    )

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["default_vat_code_id"] == code_id("K030")
    logged = (
        AuditLog.query.filter_by(action="account.updated")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert logged.details["changes"]["default_vat_code_id"] == {
        "from": code_id("K010"),
        "to": code_id("K030"),
    }


def test_the_default_code_can_be_cleared(client, test_user, chart):
    res = put(client, test_user, chart[2450], default_vat_code_id=None)

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["default_vat_code_id"] is None


def test_an_account_saved_as_the_app_sends_it_keeps_its_default(
    client, test_user, chart
):
    res = put(client, test_user, chart[2450], name="Kontorartikler og papir")

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["default_vat_code_id"] == code_id("K010")


def test_a_deferred_code_cannot_be_the_default(client, test_user, chart):
    res = put(
        client, test_user, chart[2450], default_vat_code_id=code_id("K020")
    )

    assert res.status_code == 422
    assert res.get_json()["errors"]["default_vat_code_id"] == [
        "The VAT code K020 cannot be used yet"
    ]


def test_an_unknown_code_cannot_be_the_default(client, test_user, chart):
    res = put(client, test_user, chart[2450], default_vat_code_id=999999)

    assert res.status_code == 422
    assert res.get_json()["errors"]["default_vat_code_id"] == [
        "There is no VAT code with id 999999"
    ]


def test_a_new_account_can_have_a_default_code(client, test_user, chart):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent.update(number=2455, name="Papir", default_vat_code_id=code_id("K010"))

    res = client.post("/accounts", json=sent, headers=headers(test_user))

    assert res.status_code == 201, res.get_json()
    assert res.get_json()["default_vat_code_id"] == code_id("K010")


def test_a_new_account_cannot_have_a_deferred_default(client, test_user, chart):
    sent = as_app_sends(
        client.get(
            f"/accounts/{chart[2450].id}", headers=headers(test_user)
        ).get_json()
    )
    sent.update(number=2455, name="Papir", default_vat_code_id=code_id("S83"))

    res = client.post("/accounts", json=sent, headers=headers(test_user))

    assert res.status_code == 422
    assert Account.query.filter_by(number=2455).count() == 0


# --- the VAT period of an organization ------------------------------------


def stored(organization) -> Organization:
    return Organization.query.filter_by(id=organization.id).one()


def put_organization(client, user, organization, **changes):
    body = client.get(
        f"/organizations/{organization.id}", headers=headers(user)
    ).get_json()
    for dropped in (
        "id",
        "created_at",
        "updated_at",
        "country",
        "users",
        "invoice_setting",
    ):
        body.pop(dropped, None)
    body.update(changes)
    return client.put(
        f"/organizations/{organization.id}", json=body, headers=headers(user)
    )


def test_an_organization_has_no_vat_period_until_one_is_set(
    client, test_user, organization
):
    res = client.get(
        f"/organizations/{organization.id}", headers=headers(test_user)
    )

    assert res.get_json()["vat_period_type"] is None


@pytest.mark.parametrize("period", ["half_year", "quarter", "month"])
def test_the_vat_period_can_be_set(client, test_user, organization, period):
    res = put_organization(
        client, test_user, organization, vat_period_type=period
    )

    assert res.status_code == 200, res.get_json()
    assert stored(organization).vat_period_type == period
    assert res.get_json()["vat_period_type"] == period


def test_the_vat_period_can_be_cleared_when_not_registered(
    client, test_user, organization
):
    put_organization(client, test_user, organization, vat_period_type="quarter")

    res = put_organization(
        client, test_user, organization, vat_period_type=None
    )

    assert res.status_code == 200, res.get_json()
    assert stored(organization).vat_period_type is None


def test_saving_the_organization_without_the_field_leaves_it_alone(
    client, test_user, organization
):
    put_organization(client, test_user, organization, vat_period_type="quarter")
    body = client.get(
        f"/organizations/{organization.id}", headers=headers(test_user)
    ).get_json()
    for dropped in (
        "id",
        "created_at",
        "updated_at",
        "country",
        "users",
        "invoice_setting",
        "vat_period_type",
    ):
        body.pop(dropped, None)

    res = client.put(
        f"/organizations/{organization.id}",
        json=body,
        headers=headers(test_user),
    )

    assert res.status_code == 200, res.get_json()
    assert stored(organization).vat_period_type == "quarter"


def test_an_unknown_vat_period_is_refused(client, test_user, organization):
    res = put_organization(
        client, test_user, organization, vat_period_type="week"
    )

    assert res.status_code == 422
    assert "vat_period_type" in res.get_json()["errors"]
    assert stored(organization).vat_period_type is None


def test_the_database_refuses_an_unknown_vat_period(db_session, organization):
    organization.vat_period_type = "week"

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    assert "ck_organizations_vat_period_type" in str(error.value)
