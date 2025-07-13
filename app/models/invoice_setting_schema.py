from app.models import ma, InvoiceSetting
from marshmallow import (
    fields,
    validate,
    post_dump
)

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
    default_reminder_fee = fields.Decimal(required=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    @post_dump()
    def convert_decimal(self, data, many):
        if data:
            data['default_reminder_fee'] = float(data.get('default_reminder_fee')) if data.get('default_reminder_fee') else None
        return data

    class Meta:
        model = InvoiceSetting
        include_fk = True

invoice_setting_schema = InvoiceSettingSchema()