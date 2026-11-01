from flask import request
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError

from app.ledger import LedgerError
from app.models.report_schema import (
    account_ledger_query_schema,
    account_ledger_schema,
    trial_balance_query_schema,
    trial_balance_schema,
    vat_report_schema,
)
from app.reports import account_ledger, trial_balance, vat_report
from app.routes import bp


def _failed(error: Exception):
    if isinstance(error, ValidationError):
        return {"errors": error.messages}, 422
    return {"error": str(error)}, error.status


@bp.get("/reports/account-ledger")
@jwt_required()
def get_account_ledger():
    """Every posting on one account, with a running balance. Query:
    account_id, and from and to (dates, both optional)."""
    try:
        query = account_ledger_query_schema.load(request.args.to_dict())
        report = account_ledger(
            current_user.organization_id,
            query["account_id"],
            query.get("date_from"),
            query.get("date_to"),
        )
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return account_ledger_schema.dump(report)


@bp.get("/reports/trial-balance")
@jwt_required()
def get_trial_balance():
    """The balance of every account with postings. Query: from and to
    (dates, both optional): without them, everything posted."""
    try:
        query = trial_balance_query_schema.load(request.args.to_dict())
        report = trial_balance(
            current_user.organization_id,
            query.get("date_from"),
            query.get("date_to"),
        )
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return trial_balance_schema.dump(report)


@bp.get("/reports/vat")
@jwt_required()
def get_vat_report():
    """The VAT of a range of dates as the return asks for it, per VAT code,
    and checked against the VAT accounts of the ledger. Query: from and to
    (dates, both optional): without them, everything posted."""
    try:
        query = trial_balance_query_schema.load(request.args.to_dict())
        report = vat_report(
            current_user.organization_id,
            query.get("date_from"),
            query.get("date_to"),
        )
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return vat_report_schema.dump(report)
