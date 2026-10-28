from flask import request
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import exc

from app.models.account import Account, AccountGroup
from app.models.account_schema import (
    DepositAccountSchema,
    account_groups_schema,
    account_schema,
    accounts_schema,
)
from app.models.base import db
from app.routes import bp


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

        conflict = _conflict(
            organization_id,
            account_data.get("number", account.number),
            account_data.get("name", account.name),
            account.id,
        )
        if conflict:
            return {"error": conflict}, 409

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
        conflict = _conflict(
            organization_id,
            account_data.get("number"),
            account_data.get("name"),
        )
        if conflict:
            return {"error": conflict}, 409

        account_data["organization_id"] = organization_id
        account = Account(**account_data)
        account.save()

        return account_schema.jsonify(account), 201

    except exc.IntegrityError:
        return {"error": f"This account already exists ({account.name})"}, 409
    except Exception as e:
        return {"error": str(e)}, 400
