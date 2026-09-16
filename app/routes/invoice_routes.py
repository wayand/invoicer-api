from flask import request
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import and_, exc, not_

from app.models.base import db
from app.models.invoice import Invoice
from app.models.invoice_schema import invoice_schema_with_lines, invoices_schema
from app.models.invoice_setting import InvoiceSetting
from app.models.invoiceline import InvoiceLine
from app.models.product import Product
from app.routes import bp


@bp.patch("/invoices/<int:invoice_id>/mark-as-sent")
@jwt_required()
def mark_as_sent(invoice_id):
    try:
        invoice_data = request.get_json()
        if not invoice_data:
            return {"error": "No input data provided"}, 400

        organization_id = current_user.organization_id
        invoice = Invoice.query.filter_by(
            organization_id=organization_id, id=invoice_id
        ).first_or_404(description=f"Invoice with id {invoice_id} not found!")
        if not isinstance(invoice_data["is_sent"], bool):
            return {"error": '"is_sent" is NOT of type boolean!'}, 422

        invoice.is_sent = invoice_data.get("is_sent", invoice.is_sent)
        invoice.update()

        return invoice_schema_with_lines.dump(invoice)

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}, 500


@bp.get("/invoices")
@jwt_required()
def get_invoices():
    organization_id = current_user.organization_id
    invoices = Invoice.query.filter_by(organization_id=organization_id)
    return invoices_schema.jsonify(invoices)


@bp.get("/invoices/<int:invoice_id>")
@jwt_required()
def get_invoice(invoice_id):
    organization_id = current_user.organization_id
    invoice = Invoice.query.filter_by(
        organization_id=organization_id, id=invoice_id
    ).first_or_404(description=f"Invoice with id {invoice_id} not found!")
    return invoice_schema_with_lines.jsonify(invoice)


@bp.post("/organizations/<int:organization_id>/invoices")
@jwt_required()
def create_invoice(organization_id):
    try:
        invoice_data = request.get_json()
        if not invoice_data:
            return {"error": "No input data provided"}, 400
    except Exception as e:
        return {"error": str(e)}, 400

    errors = invoice_schema_with_lines.validate(invoice_data)
    if errors:
        return {"errors": errors}, 422

    try:
        invoice_loaded = invoice_schema_with_lines.load(invoice_data)
        duplicate_check = Invoice.query.filter_by(
            organization_id=organization_id,
            invoice_no=invoice_loaded.get("invoice_no"),
        ).first()
        if duplicate_check:
            raise Exception(
                f"Invoice_no ({duplicate_check.invoice_no}) already exists"
            )
        lines = invoice_loaded.pop("lines")
        invoice = Invoice(
            **invoice_loaded, lines=[InvoiceLine(**line) for line in lines]
        )
        invoice.save()

        """
        Now update the Organization.invoiceSetting.next_invoice_no +1
        """
        invoice_setting = InvoiceSetting.query.filter_by(
            organization_id=current_user.organization_id
        ).first_or_404(
            description=f'invoice-setting with organization_id: {current_user.organization_id} not found! so didnt update "InvoiceSetting.next_invoice_no"'
        )
        invoice_setting.next_invoice_no = int(invoice.invoice_no) + 1
        invoice_setting.update()
        # the_organization = Organization.query.filter_by(id=current_user.organization_id).first_or_404(description=f'Organization with id {current_user.organization_id} not found! so didnt update "Organization.next_invoice_no"')
        # the_organization.next_invoice_no = int(invoice.invoice_no) + 1
        # the_organization.update()

        return invoice_schema_with_lines.dump(invoice), 201
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}, 400


def _invoice_no_exists(id, organization_id, invoice_no):
    return (
        db.session.query(Invoice)
        .filter(
            and_(
                Invoice.invoice_no == invoice_no,
                Invoice.organization_id == organization_id,
            )
        )
        .filter(
            not_(
                Invoice.id == id,
            )
        )
        .first()
    )


@bp.put("/organizations/<int:organization_id>/invoices/<int:invoice_id>")
@jwt_required()
def update_invoice(organization_id, invoice_id):
    invoice = Invoice.query.filter_by(
        organization_id=organization_id, id=invoice_id
    ).first_or_404(description=f"Invoice with id {invoice_id} not found!")

    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": "No input data provided"}, 400
    except Exception as e:
        return {"error": str(e)}, 400

    errors = invoice_schema_with_lines.validate(json_data)
    if errors:
        return {"errors": errors}, 422

    try:
        data = invoice_schema_with_lines.load(json_data)
        if _invoice_no_exists(
            invoice_id, organization_id, data.get("invoice_no")
        ):
            return {
                "error": f"Invoice_no {data.get('invoice_no')} already exists"
            }, 400

        lines = data.get("lines")
        if len(lines) < 1:
            return {
                "error": "InvoiceLines length should be greater than 1!"
            }, 400

        invoice.contact_id = data.get("contact_id", invoice.contact_id)
        invoice.invoice_no = data.get("invoice_no", invoice.invoice_no)
        invoice.invoice_date = data.get("invoice_date", invoice.invoice_date)
        invoice.duedate = data.get("duedate", invoice.duedate)
        invoice.amount = data.get("amount", invoice.amount)
        invoice.gross_amount = data.get("gross_amount", invoice.gross_amount)
        invoice.vat_amount = data.get("vat_amount", invoice.vat_amount)
        invoice.is_paid = data.get("is_paid", invoice.is_paid)
        invoice.is_sent = data.get("is_sent", invoice.is_sent)
        invoice.state = data.get("state", invoice.state)
        invoice.currency_id = data.get("currency_id", invoice.currency_id)
        invoice.template_id = data.get("is_sent", invoice.template_id)
        invoice.excluding_vat = data.get("excluding_vat", invoice.excluding_vat)

        # delete lines that are removed
        to_be_deleted = [line.get("id") for line in lines if line.get("id")]
        InvoiceLine.query.filter_by(invoice_id=invoice_id).filter(
            InvoiceLine.id.not_in(to_be_deleted)
        ).delete(synchronize_session=False)

        for line in lines:
            if line.get("id"):
                invoiceline = InvoiceLine.query.filter_by(
                    id=line.get("id"), invoice_id=invoice.id
                ).first_or_404(
                    description=f"InvoiceLine with id {line.get('id')} not found!"
                )
                Product.query.filter_by(
                    organization_id=organization_id, id=line.get("product_id")
                ).first_or_404(
                    description=f"Product with id {line.get('product_id')} not found!"
                )
                invoiceline.product_id = line.get(
                    "product_id", invoiceline.product_id
                )
                invoiceline.quantity = line.get(
                    "quantity", invoiceline.quantity
                )
                invoiceline.amount = line.get("amount", invoiceline.amount)
                invoiceline.unit_price = line.get(
                    "unit_price", invoiceline.unit_price
                )
                invoiceline.description = line.get(
                    "description", invoiceline.description
                )
                invoice.lines.append(invoiceline)
            else:
                Product.query.filter_by(
                    organization_id=organization_id, id=line.get("product_id")
                ).first_or_404(
                    description=f"Product with id {line.get('product_id')} not found!"
                )
                invoice.lines.append(InvoiceLine(**line))
        invoice.update()
        return invoice_schema_with_lines.dump(invoice), 200
    except exc.IntegrityError as e:
        db.session.rollback()
        return {"error": str(e)}, 202
    except FileNotFoundError as e:
        return {"eerror": str(e)}, 404


@bp.delete("/organizations/<int:organization_id>/invoices/<int:invoice_id>")
@jwt_required()
def delete_invoice(organization_id, invoice_id):
    invoice = Invoice.query.filter_by(
        organization_id=organization_id, id=invoice_id
    ).first_or_404(description=f"Invoice with id {invoice_id} not found!")
    try:
        invoice.delete()
        return {
            "message": f"invoice with id {invoice_id} and all its lines are deleted!!"
        }, 200
    except Exception as e:
        return {"error": str(e)}, 400
