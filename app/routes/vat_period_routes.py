from datetime import date

from flask import request
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError

from app.ledger import LedgerError
from app.models.base import db
from app.models.organization import Organization
from app.models.vat_period_schema import (
    due_date_input_schema,
    filing_input_schema,
    vat_period_schema,
    vat_periods_schema,
)
from app.routes import bp
from app.vat_periods import (
    change_due_date,
    file_period,
    list_periods,
    open_period,
    settle_period,
    why_not_settled,
)


def _failed(error: Exception):
    db.session.rollback()
    if isinstance(error, ValidationError):
        return {"errors": error.messages}, 422
    return {"error": str(error)}, error.status


def _json():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("The body must be an object")
    return data


@bp.get("/vat-periods")
@jwt_required()
def get_vat_periods():
    """The periods that have been settled, newest first, and the open one:
    the first period not settled yet, with what stops it from being settled.
    The open period is null for an organization that is not VAT-registered,
    or has no posting with a VAT code yet."""
    organization_id = current_user.organization_id
    organization = db.session.get(Organization, organization_id)
    period = open_period(organization_id)
    open_ = None
    if period is not None:
        blocked = why_not_settled(organization_id, period, date.today())
        open_ = {
            "period_type": period.period_type,
            "start_date": period.start_date,
            "end_date": period.end_date,
            "due_date": period.due_date,
            "ended": date.today() > period.end_date,
            "can_settle": blocked is None,
            "blocked_by": blocked,
        }
    return vat_periods_schema.dump(
        {
            "vat_period_type": organization.vat_period_type,
            "periods": list_periods(organization_id),
            "open_period": open_,
        }
    )


@bp.post("/vat-periods/settle")
@jwt_required()
def settle_vat_period():
    """Settle the first open period, once it has ended."""
    try:
        _json()
        period = settle_period(current_user.organization_id, current_user.id)
        db.session.commit()
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return vat_period_schema.dump(period), 201


@bp.post("/vat-periods/<int:period_id>/file")
@jwt_required()
def file_vat_period(period_id):
    """Mark a settled period as filed. The body is optional: the date it was
    filed (default today) and a reference."""
    try:
        data = filing_input_schema.load(_json())
        period = file_period(
            current_user.organization_id,
            current_user.id,
            period_id,
            filed_on=data.get("filed_on"),
            reference=data.get("reference"),
        )
        db.session.commit()
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return vat_period_schema.dump(period)


@bp.patch("/vat-periods/<int:period_id>")
@jwt_required()
def change_vat_period(period_id):
    """Correct the due date of a period."""
    try:
        data = due_date_input_schema.load(_json())
        period = change_due_date(
            current_user.organization_id,
            current_user.id,
            period_id,
            data["due_date"],
        )
        db.session.commit()
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return vat_period_schema.dump(period)
