from flask import request
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import exc

from app.audit import record
from app.models.account import Account, AccountGroup
from app.models.account_schema import (
    DepositAccountSchema,
    account_groups_schema,
    account_schema,
    accounts_schema,
)
from app.models.base import db
from app.models.vat_code import VatCode
from app.routes import bp

# What is logged when an account is changed. The bank numbers are not copied
# into the log: it says only that they changed.
LOGGED_FIELDS = (
    "number",
    "name",
    "description",
    "account_type_id",
    "account_group_id",
    "tax_rate_id",
    "default_vat_code_id",
    "currency_id",
    "is_bank_account",
    "is_payment_enabled",
    "is_archived",
)
BANK_FIELDS = (
    "bank_id",
    "bank_account_number",
    "bank_registration_number",
    "bank_iban_number",
    "bank_swift_number",
)


def _snapshot(account):
    return {
        key: getattr(account, key) for key in (*LOGGED_FIELDS, *BANK_FIELDS)
    }


def _log_changes(account, before):
    """Log an account change with what changed, if anything did."""
    after = _snapshot(account)
    changes = {
        key: {"from": before[key], "to": after[key]}
        for key in LOGGED_FIELDS
        if before[key] != after[key]
    }
    bank_changed = any(before[key] != after[key] for key in BANK_FIELDS)
    if changes or bank_changed:
        details = {"changes": changes}
        if bank_changed:
            details["bank_details_changed"] = True
        record(
            account.organization_id,
            current_user.id,
            "account.updated",
            "account",
            account.id,
            details,
        )


def _conflict(organization_id, number, name, account_id=None):
    """Why the number or name cannot be used, or None. Both are unique per
    organization; account_id is the account being changed, if any."""
    query = Account.query.filter(Account.organization_id == organization_id)
    if account_id is not None:
        query = query.filter(Account.id != account_id)
    if number is not None and query.filter(Account.number == number).first():
        return f"Account number {number} is already in use"
    if name is not None and query.filter(Account.name == name).first():
        return f"Account name ({name}) is already in use"
    return None


def _vat_code_problem(vat_code_id):
    """Why the id cannot be the default VAT code of an account, or None."""
    if vat_code_id is None:
        return None
    code = db.session.get(VatCode, vat_code_id)
    if code is None:
        return f"There is no VAT code with id {vat_code_id}"
    if not code.is_supported:
        return f"The VAT code {code.code} cannot be used yet"
    return None


@bp.get("/account-groups")
@jwt_required()
def get_account_groups():
    organization_id = current_user.organization_id
    account_groups = AccountGroup.query.filter_by(
        organization_id=organization_id
    )
    return account_groups_schema.jsonify(account_groups)


@bp.get("/deposit-accounts")
@jwt_required()
def get_deposit_accounts():
    organization_id = current_user.organization_id
    accounts = Account.query.filter_by(
        organization_id=organization_id, is_deposit=True
    )
    return DepositAccountSchema(many=True).jsonify(accounts)


@bp.get("/accounts")
@jwt_required()
def get_accounts():
    organization_id = current_user.organization_id
    accounts = Account.query.filter_by(organization_id=organization_id)
    return accounts_schema.jsonify(accounts)


@bp.get("/accounts/<int:account_id>")
@jwt_required()
def get_account(account_id):
    organization_id = current_user.organization_id
    account = Account.query.filter_by(
        organization_id=organization_id, id=account_id
    ).first_or_404(description=f"Account with id {account_id} not found !")
    return account_schema.jsonify(account)


@bp.put("/accounts/<int:account_id>")
@jwt_required()
def update_account(account_id):
    organization_id = current_user.organization_id
    account = Account.query.filter_by(
        organization_id=organization_id, id=account_id
    ).first_or_404(description=f"Account with id {account_id} not found!")

    try:
        json_data = request.get_json()

        errors = account_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        account_data = account_schema.load(json_data)

        problem = _vat_code_problem(account_data.get("default_vat_code_id"))
        if problem:
            return {"errors": {"default_vat_code_id": [problem]}}, 422

        conflict = _conflict(
            organization_id,
            account_data.get("number", account.number),
            account_data.get("name", account.name),
            account.id,
        )
        if conflict:
            return {"error": conflict}, 409

        before = _snapshot(account)
        account.number = account_data.get("number", account.number)
        account.account_type_id = account_data.get(
            "account_type_id", account.account_type_id
        )
        account.account_group_id = account_data.get(
            "account_group_id", account.account_group_id
        )
        account.tax_rate_id = account_data.get(
            "tax_rate_id", account.tax_rate_id
        )
        account.default_vat_code_id = account_data.get(
            "default_vat_code_id", account.default_vat_code_id
        )
        account.name = account_data.get("name", account.name)
        account.bank_account_number = account_data.get(
            "bank_account_number", account.bank_account_number
        )
        account.bank_registration_number = account_data.get(
            "bank_registration_number", account.bank_registration_number
        )
        account.bank_iban_number = account_data.get(
            "bank_iban_number", account.bank_iban_number
        )
        account.bank_swift_number = account_data.get(
            "bank_swift_number", account.bank_swift_number
        )
        account.bank_id = account_data.get("bank_id", account.bank_id)
        account.description = account_data.get(
            "description", account.description
        )
        account.currency_id = account_data.get(
            "currency_id", account.currency_id
        )
        account.is_bank_account = account_data.get(
            "is_bank_account", account.is_bank_account
        )
        account.is_payment_enabled = account_data.get(
            "is_payment_enabled", account.is_payment_enabled
        )
        account.is_archived = account_data.get(
            "is_archived", account.is_archived
        )
        # The log row is committed with the change
        _log_changes(account, before)
        account.update()

        return account_schema.dump(account), 200
    except exc.IntegrityError:
        db.session.rollback()
        return {
            "error": f"This account name is already in use ({account.name})"
        }, 409
    except Exception as e:
        return {"error": str(e)}, 500


@bp.post("/accounts")
@jwt_required()
def create_account():
    organization_id = current_user.organization_id
    try:
        json_data = request.get_json()

        errors = account_schema.validate(json_data)
        if errors:
            return {"errors": errors}, 422

        account_data = account_schema.load(json_data)

        problem = _vat_code_problem(account_data.get("default_vat_code_id"))
        if problem:
            return {"errors": {"default_vat_code_id": [problem]}}, 422

        conflict = _conflict(
            organization_id,
            account_data.get("number"),
            account_data.get("name"),
        )
        if conflict:
            return {"error": conflict}, 409

        account_data["organization_id"] = organization_id
        account = Account(**account_data)
        db.session.add(account)
        db.session.flush()
        record(
            organization_id,
            current_user.id,
            "account.created",
            "account",
            account.id,
            {
                "number": account.number,
                "name": account.name,
                "account_type_id": account.account_type_id,
                "account_group_id": account.account_group_id,
            },
        )
        db.session.commit()

        return account_schema.jsonify(account), 201

    except exc.IntegrityError:
        return {"error": f"This account already exists ({account.name})"}, 409
    except Exception as e:
        return {"error": str(e)}, 400
