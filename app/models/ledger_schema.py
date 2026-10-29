"""The journal as the API reads and writes it (docs/ledger-design.md).

Amounts are JSON numbers with 2 decimals, as everywhere else (money-rules.md).
"""

from decimal import Decimal

from marshmallow import Schema, ValidationError, fields, pre_load, validate

from app.ledger import MAX_LINES, MAX_TEXT
from app.money import MAX_AMOUNT, DecimalNumber

AMOUNT = {"places": 2, "validate": validate.Range(min=0, max=MAX_AMOUNT)}


class JournalLineInputSchema(Schema):
    account_id = fields.Integer(required=True)
    debit = DecimalNumber(load_default=Decimal("0"), **AMOUNT)
    credit = DecimalNumber(load_default=Decimal("0"), **AMOUNT)
    description = fields.String(
        allow_none=True, validate=validate.Length(max=MAX_TEXT)
    )
    contact_id = fields.Integer(allow_none=True)

    @pre_load
    def amounts_are_numbers(self, data, **kwargs):
        for key in ("debit", "credit"):
            value = data.get(key) if isinstance(data, dict) else None
            if key in (data or {}) and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise ValidationError("Invalid type. Expected Number.", key)
        return data


class JournalEntryInputSchema(Schema):
    entry_date = fields.Date(required=True)
    description = fields.String(
        required=True, validate=validate.Length(min=1, max=MAX_TEXT)
    )
    lines = fields.List(
        fields.Nested(JournalLineInputSchema),
        required=True,
        validate=validate.Length(min=2, max=MAX_LINES),
    )


class ReversalInputSchema(Schema):
    entry_date = fields.Date()
    description = fields.String(validate=validate.Length(min=1, max=MAX_TEXT))


class JournalLineSchema(Schema):
    id = fields.Integer()
    line_no = fields.Integer()
    account_id = fields.Integer()
    account_number = fields.Integer(attribute="account.number")
    account_name = fields.String(attribute="account.name")
    debit = DecimalNumber(places=2)
    credit = DecimalNumber(places=2)
    description = fields.String(allow_none=True)
    contact_id = fields.Integer(allow_none=True)


class JournalEntrySchema(Schema):
    id = fields.Integer()
    voucher_no = fields.Integer()
    fiscal_year_id = fields.Integer()
    entry_date = fields.Date()
    description = fields.String()
    source_type = fields.String()
    source_id = fields.Integer(allow_none=True)
    reverses_entry_id = fields.Integer(allow_none=True)
    # The voucher id of the entry that reverses this one, set by the route
    reversed_by_entry_id = fields.Integer(allow_none=True)
    created_by = fields.Integer()
    created_at = fields.DateTime()
    lines = fields.Nested(JournalLineSchema, many=True)


class FiscalYearSchema(Schema):
    id = fields.Integer()
    start_date = fields.Date()
    end_date = fields.Date()
    status = fields.String()


journal_entry_input_schema = JournalEntryInputSchema()
reversal_input_schema = ReversalInputSchema()
journal_entry_schema = JournalEntrySchema()
journal_entries_schema = JournalEntrySchema(many=True)
fiscal_years_schema = FiscalYearSchema(many=True)
fiscal_year_schema = FiscalYearSchema()
