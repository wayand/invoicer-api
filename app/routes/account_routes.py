from flask import request
from sqlalchemy import exc
from app.routes import bp
from app.models import (
    db,
    Account,
    AccountGroup,
    DepositAccountSchema,
    accounts_schema,
    account_schema,
    account_groups_schema,
)
from flask_jwt_extended import jwt_required, current_user


@bp.get("/account-groups")
@jwt_required()
def get_account_groups():
    organization_id = current_user.organization_id
    account_groups = AccountGroup.query.filter_by(organization_id=organization_id)
    return account_groups_schema.jsonify(account_groups)


@bp.get("/deposit-accounts")
@jwt_required()
def get_deposit_accounts():
    organization_id = current_user.organization_id
    accounts = Account.query.filter_by(organization_id=organization_id, is_deposit=True)
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

        account.number = account_data.get("number", account.number)
        account.account_type_id = account_data.get(
            "account_type_id", account.account_type_id
        )
        account.account_group_id = account_data.get(
            "account_group_id", account.account_group_id
        )
        account.tax_rate_id = account_data.get("tax_rate_id", account.tax_rate_id)
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
        account.description = account_data.get("description", account.description)
        account.currency_id = account_data.get("currency_id", account.currency_id)
        account.is_bank_account = account_data.get(
            "is_bank_account", account.is_bank_account
        )
        account.is_payment_enabled = account_data.get(
            "is_payment_enabled", account.is_payment_enabled
        )
        account.is_archived = account_data.get("is_archived", account.is_archived)
        account.update()

        return account_schema.dump(account), 200
    except exc.IntegrityError:
        db.session.rollback()
        return {"error": f"This account name is already in use ({account.name})"}, 409
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
        duplicate_check = Account.query.filter_by(
            organization_id=organization_id, name=account_data.get("name")
        ).first()
        if duplicate_check:
            raise Exception(f"Account name ({duplicate_check.name}) already exists")

        account = Account(**account_data)
        account.save()

        return account_schema.jsonify(account), 201

    except exc.IntegrityError:
        return {"error": f"This account already exists ({account.name})"}, 409
    except Exception as e:
        return {"error": str(e)}, 400
