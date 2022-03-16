from flask import request
from sqlalchemy import exc
from app.routes import bp
from app.models import db, InvoiceSetting, invoice_setting, invoice_setting_schema
from flask_jwt_extended import (
    jwt_required,
    current_user
)

@bp.get("/invoice-setting")
@jwt_required()
def get_invoice_setting():
    organization_id = current_user.organization_id
    invoice_setting = InvoiceSetting.query.filter_by(organization_id=organization_id)
    return invoice_setting_schema.jsonify(invoice_setting)


@bp.put("/invoice-setting")
@jwt_required()
def update_invoice_setting():
    try:
        organization_id = current_user.organization_id

        json_data = request.get_json()

        errors = invoice_setting_schema.validate(json_data)
        if errors:
            return {
                "errors": errors
            }, 422

        invoice_setting_data = invoice_setting_schema.load(json_data)

        invoice_setting = InvoiceSetting.query.filter_by(organization_id=organization_id).scalar()
        if not invoice_setting:
            """ no invoice setting, so create one with values from json_data """
            invoice_setting = InvoiceSetting(**invoice_setting_data)
            invoice_setting.save()
        else:
            """ Invoice setting are there, so we update them """
            invoice_setting.organization_id = invoice_setting_data.get("organization_id", invoice_setting.organization_id)
            invoice_setting.default_account_id = invoice_setting_data.get("default_account_id", invoice_setting.default_account_id) #1, # Salg af varer/ydelser m/moms
            invoice_setting.default_deposit_account_id = invoice_setting_data.get("default_deposit_account_id", invoice_setting.default_deposit_account_id) #5, # Bank, den primære bankkonto
            invoice_setting.template_id = invoice_setting_data.get("template_id", invoice_setting.template_id) #1, # default template id
            invoice_setting.hide_product_numbers = invoice_setting_data.get("hide_product_numbers", invoice_setting.hide_product_numbers) #False, # Hide product number in invoice lines
            invoice_setting.lines_incl_vat = invoice_setting_data.get("lines_incl_vat", invoice_setting.lines_incl_vat) #False, # Invoice lines amount including vat
            invoice_setting.invoice_no_mode = invoice_setting_data.get("invoice_no_mode", invoice_setting.invoice_no_mode) #'Sequential', # Invoice numbering mode: Sequential OR Manual
            invoice_setting.next_invoice_no = invoice_setting_data.get("next_invoice_no", invoice_setting.next_invoice_no) #1, # The next invoice number, if invoice-numbering: Sequential
            invoice_setting.default_reminder_fee = invoice_setting_data.get("default_reminder_fee", invoice_setting.default_reminder_fee) #100
            invoice_setting.update()

        return invoice_setting_schema.jsonify(invoice_setting)

    except exc.MultipleResultsFound as e:
        return { 'error': str(e) }, 409
    except Exception as e:
        return {'error': str(e)}, 500