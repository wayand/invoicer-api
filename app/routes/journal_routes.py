from flask import request
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError

from app.ledger import (
    LedgerError,
    LineInput,
    close_fiscal_year,
    get_entry,
    post_entry,
    reverse_entry,
)
from app.models.base import db
from app.models.ledger import FiscalYear, JournalEntry
from app.models.ledger_schema import (
    fiscal_year_schema,
    fiscal_years_schema,
    journal_entries_schema,
    journal_entry_input_schema,
    journal_entry_schema,
    reversal_input_schema,
)
from app.routes import bp

DEFAULT_LIMIT, MAX_LIMIT = 50, 200


def _with_reversals(entries):
    """Set reversed_by_entry_id on the entries: the entry that reverses each."""
    entries = list(entries)
    reversals = {
        reversal.reverses_entry_id: reversal.id
        for reversal in JournalEntry.query.filter(
            JournalEntry.reverses_entry_id.in_([entry.id for entry in entries])
        )
    }
    for entry in entries:
        entry.reversed_by_entry_id = reversals.get(entry.id)
    return entries


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("No input data provided")
    return data


def _failed(error: Exception):
    db.session.rollback()
    if isinstance(error, ValidationError):
        return {"errors": error.messages}, 422
    return {"error": str(error)}, error.status


@bp.post("/journal-entries")
@jwt_required()
def create_journal_entry():
    """Post a manual entry."""
    try:
        data = journal_entry_input_schema.load(_json())
        entry = post_entry(
            current_user.organization_id,
            current_user.id,
            data["entry_date"],
            data["description"],
            [LineInput(**line) for line in data["lines"]],
        )
        db.session.commit()
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return journal_entry_schema.dump(_with_reversals([entry])[0]), 201


@bp.get("/journal-entries")
@jwt_required()
def get_journal_entries():
    query = JournalEntry.query.filter_by(
        organization_id=current_user.organization_id
    )
    fiscal_year_id = request.args.get("fiscal_year_id", type=int)
    if fiscal_year_id is not None:
        query = query.filter_by(fiscal_year_id=fiscal_year_id)
    limit = min(request.args.get("limit", DEFAULT_LIMIT, type=int), MAX_LIMIT)
    offset = max(request.args.get("offset", 0, type=int), 0)
    entries = (
        query.order_by(JournalEntry.voucher_no.desc())
        .limit(max(limit, 1))
        .offset(offset)
        .all()
    )
    return journal_entries_schema.dump(_with_reversals(entries))


@bp.get("/journal-entries/<int:entry_id>")
@jwt_required()
def get_journal_entry(entry_id):
    try:
        entry = get_entry(current_user.organization_id, entry_id)
    except LedgerError as error:
        return _failed(error)
    return journal_entry_schema.dump(_with_reversals([entry])[0])


@bp.post("/journal-entries/<int:entry_id>/reverse")
@jwt_required()
def reverse_journal_entry(entry_id):
    """Post the opposite of an entry. The body is optional: a date (default
    today) and a description."""
    try:
        data = reversal_input_schema.load(request.get_json(silent=True) or {})
        entry = reverse_entry(
            current_user.organization_id,
            current_user.id,
            entry_id,
            entry_date=data.get("entry_date"),
            description=data.get("description"),
        )
        db.session.commit()
    except (LedgerError, ValidationError) as error:
        return _failed(error)
    return journal_entry_schema.dump(_with_reversals([entry])[0]), 201


@bp.get("/fiscal-years")
@jwt_required()
def get_fiscal_years():
    years = FiscalYear.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(FiscalYear.start_date.desc())
    return fiscal_years_schema.dump(years)


@bp.post("/fiscal-years/<int:fiscal_year_id>/close")
@jwt_required()
def close_year(fiscal_year_id):
    try:
        year = close_fiscal_year(current_user.organization_id, fiscal_year_id)
        db.session.commit()
    except LedgerError as error:
        return _failed(error)
    return fiscal_year_schema.dump(year)
