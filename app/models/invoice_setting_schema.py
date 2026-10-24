from flask_marshmallow import Marshmallow
from marshmallow import fields

from app.money import DecimalNumber

from .invoice_setting import InvoiceSetting

ma = Marshmallow()


class InvoiceSettingSchema(ma.SQLAlchemySchema):
    id = fields.Integer(dump_only=True)
    organization_id = fields.Integer()
    default_account_id = fields.Integer()
    default_deposit_account_id = fields.Integer()

    template_id = fields.String(required=True)
    hide_product_numbers = fields.Boolean()
    lines_incl_vat = fields.Boolean()

    invoice_no_mode = fields.String(required=True)
    next_invoice_no = fields.Integer(required=True)
    default_reminder_fee = DecimalNumber(places=2, required=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    class Meta:
        model = InvoiceSetting
        include_fk = True


invoice_setting_schema = InvoiceSettingSchema()
