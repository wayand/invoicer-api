"""VAT periods as the API reads and writes them (docs/vat-design.md,
section 8)."""

from marshmallow import Schema, fields, validate


class VatPeriodSchema(Schema):
    id = fields.Integer()
    period_type = fields.String()
    start_date = fields.Date()
    end_date = fields.Date()
    due_date = fields.Date()
    # settled, or filed once the return has been entered in TastSelv Erhverv
    status = fields.String()
    settlement_entry_id = fields.Integer(allow_none=True)
    settlement_voucher_no = fields.Function(
        lambda period: (
            period.settlement_entry.voucher_no
            if period.settlement_entry
            else None
        ),
        allow_none=True,
    )
    settled_at = fields.DateTime()
    settled_by = fields.Integer()
    filed_on = fields.Date(allow_none=True)
    filed_by = fields.Integer(allow_none=True)
    reference = fields.String(allow_none=True)


class OpenPeriodSchema(Schema):
    period_type = fields.String()
    start_date = fields.Date()
    end_date = fields.Date()
    due_date = fields.Date()
    ended = fields.Boolean()
    can_settle = fields.Boolean()
    # What stops it from being settled, or null
    blocked_by = fields.String(allow_none=True)


class VatPeriodsSchema(Schema):
    vat_period_type = fields.String(allow_none=True)
    periods = fields.Nested(VatPeriodSchema, many=True)
    open_period = fields.Nested(OpenPeriodSchema, allow_none=True)


class FilingInputSchema(Schema):
    filed_on = fields.Date()
    reference = fields.String(
        allow_none=True, validate=validate.Length(max=500)
    )


class DueDateInputSchema(Schema):
    due_date = fields.Date(required=True)


vat_period_schema = VatPeriodSchema()
vat_periods_schema = VatPeriodsSchema()
filing_input_schema = FilingInputSchema()
due_date_input_schema = DueDateInputSchema()
