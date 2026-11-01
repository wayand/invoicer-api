"""The reports as the API reads and writes them. Amounts are JSON numbers
with 2 decimals, as everywhere else (docs/money-rules.md)."""

from marshmallow import Schema, fields

from app.money import DecimalNumber


class TrialBalanceQuerySchema(Schema):
    date_from = fields.Date(data_key="from")
    date_to = fields.Date(data_key="to")


class AccountLedgerQuerySchema(TrialBalanceQuerySchema):
    account_id = fields.Integer(required=True)


def amount():
    return DecimalNumber(places=2)


class LedgerAccountSchema(Schema):
    id = fields.Integer()
    number = fields.Integer()
    name = fields.String()
    normal_balance = fields.String()


class LedgerRowSchema(Schema):
    entry_id = fields.Integer()
    voucher_no = fields.Integer()
    entry_date = fields.Date()
    description = fields.String()
    line_description = fields.String(allow_none=True)
    debit = amount()
    credit = amount()
    balance = amount()


class AccountLedgerSchema(Schema):
    account = fields.Nested(LedgerAccountSchema)
    date_from = fields.Date(allow_none=True, data_key="from")
    date_to = fields.Date(allow_none=True, data_key="to")
    opening_balance = amount()
    total_debit = amount()
    total_credit = amount()
    closing_balance = amount()
    rows = fields.Nested(LedgerRowSchema, many=True)


class TrialBalanceAccountSchema(Schema):
    account_id = fields.Integer()
    number = fields.Integer()
    name = fields.String()
    account_type = fields.String()
    normal_balance = fields.String()
    report_type = fields.String()
    opening_balance = amount()
    debit = amount()
    credit = amount()
    closing_balance = amount()


class TrialBalanceSchema(Schema):
    date_from = fields.Date(allow_none=True, data_key="from")
    date_to = fields.Date(allow_none=True, data_key="to")
    accounts = fields.Nested(TrialBalanceAccountSchema, many=True)
    total_opening_balance = amount()
    total_debit = amount()
    total_credit = amount()
    total_closing_balance = amount()
    balanced = fields.Boolean()


class VatBoxesSchema(Schema):
    a_goods = amount()
    a_services = amount()
    b_goods = amount()
    b_services = amount()
    c = amount()


class VatCodeFiguresSchema(Schema):
    code = fields.String()
    title = fields.String()
    applies_to = fields.String()
    direction = fields.String(allow_none=True)
    base_box = fields.String(allow_none=True)
    # Fractions: 0.25 is 25%
    rate = DecimalNumber(places=4, allow_none=True)
    deduction = DecimalNumber(places=4, allow_none=True)
    base = amount()
    output_vat = amount()
    input_vat = amount()
    acquisition_vat = amount()
    nondeductible_vat = amount()


class VatAccountRefSchema(Schema):
    id = fields.Integer()
    number = fields.Integer()
    name = fields.String()


class VatLedgerAccountSchema(Schema):
    role = fields.String()
    account = fields.Nested(VatAccountRefSchema, allow_none=True)
    ledger_balance = amount()
    reported = amount()
    difference = amount()


class VatUncodedLineSchema(Schema):
    entry_id = fields.Integer()
    voucher_no = fields.Integer()
    entry_date = fields.Date()
    description = fields.String()
    account = fields.Nested(VatAccountRefSchema)
    role = fields.String()
    line_description = fields.String(allow_none=True)
    debit = amount()
    credit = amount()


class VatLedgerCheckSchema(Schema):
    accounts = fields.Nested(VatLedgerAccountSchema, many=True)
    uncoded_lines = fields.Nested(VatUncodedLineSchema, many=True)
    ties = fields.Boolean()


class VatReportSchema(Schema):
    date_from = fields.Date(allow_none=True, data_key="from")
    date_to = fields.Date(allow_none=True, data_key="to")
    sales_vat = amount()
    input_vat = amount()
    eu_goods_vat = amount()
    eu_services_vat = amount()
    total_to_pay = amount()
    boxes = fields.Nested(VatBoxesSchema)
    codes = fields.Nested(VatCodeFiguresSchema, many=True)
    ledger_check = fields.Nested(VatLedgerCheckSchema)


trial_balance_query_schema = TrialBalanceQuerySchema()
account_ledger_query_schema = AccountLedgerQuerySchema()
account_ledger_schema = AccountLedgerSchema()
trial_balance_schema = TrialBalanceSchema()
vat_report_schema = VatReportSchema()
