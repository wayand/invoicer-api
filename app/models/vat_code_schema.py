from flask_marshmallow import Marshmallow
from marshmallow import fields

from app.money import DecimalNumber

ma = Marshmallow()


class VatCodeSchema(ma.Schema):
    """A VAT code as the API returns it. Read only: the codes are the
    official list, and nobody edits them."""

    id = fields.Integer()
    code = fields.String()
    legacy_code = fields.String()
    name = fields.String()
    title = fields.String()
    applies_to = fields.String()
    # Fractions: 0.25 is 25%
    rate = DecimalNumber(places=4, allow_none=True)
    deduction = DecimalNumber(places=4, allow_none=True)
    direction = fields.String(allow_none=True)
    base_box = fields.String(allow_none=True)
    is_supported = fields.Boolean()
    deferred_reason = fields.String(allow_none=True)
    valid_from = fields.Date()
    valid_to = fields.Date(allow_none=True)


vat_codes_schema = VatCodeSchema(many=True)
