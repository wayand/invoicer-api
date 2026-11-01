from flask import request
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError
from sqlalchemy import and_, exc, not_

from app.invoice_posting import approve_invoice
from app.invoice_vat import (
    MAX_INVOICE_LINES,
    InvoiceVatError,
    apply_totals,
    sales_codes,
)
from app.ledger import LedgerError
from app.models.base import db
from app.models.contact import Contact
from app.models.invoice import Invoice
from app.models.invoice_schema import (
    approve_input_schema,
    invoice_schema_with_lines,
    invoices_schema,
)
from app.models.invoice_setting import InvoiceSetting
from app.models.invoiceline import InvoiceLine
from app.models.organization import Organization
from app.models.product import Product
from app.money import MoneyError
from app.routes import bp
from app.routes.authz import org_member_required

LOCKED = (
    "An approved invoice cannot be changed: a mistake is corrected with a "
    "credit note"
)


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
        if invoice.state != "approved":
            return {
                "error": "Only an approved invoice can be marked as sent"
            }, 409

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
@org_member_required
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
        invoice_loaded["organization_id"] = organization_id
        invoice_setting = InvoiceSetting.query.filter_by(
            organization_id=organization_id
        ).first()
        if invoice_setting is None:
            return {
                "error": "Invoice settings are missing for this organization. "
                "Set them up under Settings, Invoicing before creating "
                "invoices."
            }, 409
        _check_line_count(invoice_loaded["lines"])
        codes = _line_codes(organization_id, invoice_loaded["lines"])
        invoice_loaded["invoice_no"] = _draft_number(
            invoice_setting, invoice_loaded.get("invoice_no")
        )
        if not _contact_in_org(organization_id, invoice_loaded["contact_id"]):
            return {
                "error": f"Contact with id {invoice_loaded['contact_id']} not found!"
            }, 404
        for line in invoice_loaded["lines"]:
            if not _product_in_org(organization_id, line.get("product_id")):
                return {
                    "error": f"Product with id {line.get('product_id')} not found!"
                }, 404
        if invoice_loaded["invoice_no"] is not None:
            duplicate_check = Invoice.query.filter_by(
                organization_id=organization_id,
                invoice_no=invoice_loaded["invoice_no"],
            ).first()
            if duplicate_check:
                raise Exception(
                    f"Invoice_no ({duplicate_check.invoice_no}) already exists"
                )
        lines = invoice_loaded.pop("lines")
        invoice = Invoice(
            **invoice_loaded,
            lines=[InvoiceLine(**_with_code_id(line, codes)) for line in lines],
        )
        apply_totals(invoice, invoice.lines, _by_id(codes))
        invoice.save(commit=False)
        db.session.commit()

        return invoice_schema_with_lines.dump(invoice), 201
    except (MoneyError, InvoiceVatError) as e:
        db.session.rollback()
        return {"error": str(e)}, 422
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}, 400


def _line_codes(organization_id, lines):
    """The VAT codes of the lines by name. Raises InvoiceVatError for one that
    an invoice cannot have: an organization that is not VAT-registered may not
    show VAT, so it can only use the code without it."""
    organization = db.session.get(Organization, organization_id)
    return sales_codes(
        (line["vat_code"] for line in lines),
        registered=organization.vat_period_type is not None,
    )


def _check_line_count(lines):
    if len(lines) > MAX_INVOICE_LINES:
        raise InvoiceVatError(
            f"An invoice has at most {MAX_INVOICE_LINES} lines"
        )


def _draft_number(invoice_setting, given):
    """The number a draft is saved with. In sequential mode it has none: the
    number is taken when the invoice is approved, so that a deleted draft
    leaves no gap, and a number the client sends is not used. In manual mode
    it is the number the user typed, if any."""
    if invoice_setting.invoice_no_mode == "sequential":
        return None
    return (given or "").strip() or None


def _by_id(codes):
    return {code.id: code for code in codes.values()}


def _with_code_id(line, codes):
    """The line as the model takes it: with the id of its VAT code."""
    line = dict(line)
    line["vat_code_id"] = codes[line.pop("vat_code")].id
    return line


def _contact_in_org(organization_id, contact_id):
    return Contact.query.filter_by(
        organization_id=organization_id, id=contact_id
    ).first()


def _product_in_org(organization_id, product_id):
    return Product.query.filter_by(
        organization_id=organization_id, id=product_id
    ).first()


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
@org_member_required
def update_invoice(organization_id, invoice_id):
    invoice = Invoice.query.filter_by(
        organization_id=organization_id, id=invoice_id
    ).first_or_404(description=f"Invoice with id {invoice_id} not found!")
    if invoice.state != "draft":
        return {"error": LOCKED}, 409

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
        _check_line_count(data["lines"])
        codes = _line_codes(organization_id, data["lines"])
        invoice_setting = InvoiceSetting.query.filter_by(
            organization_id=organization_id
        ).first()
        if invoice_setting is None:
            return {
                "error": "Invoice settings are missing for this organization. "
                "Set them up under Settings, Invoicing before saving "
                "invoices."
            }, 409
        data["invoice_no"] = _draft_number(
            invoice_setting, data.get("invoice_no")
        )
        if not _contact_in_org(organization_id, data["contact_id"]):
            return {
                "error": f"Contact with id {data['contact_id']} not found!"
            }, 404
        if data["invoice_no"] is not None and _invoice_no_exists(
            invoice_id, organization_id, data["invoice_no"]
        ):
            return {
                "error": f"Invoice_no {data['invoice_no']} already exists"
            }, 400

        lines = data.get("lines")
        if len(lines) < 1:
            return {
                "error": "InvoiceLines length should be greater than 1!"
            }, 400

        invoice.contact_id = data.get("contact_id", invoice.contact_id)
        invoice.invoice_no = data["invoice_no"]
        invoice.invoice_date = data.get("invoice_date", invoice.invoice_date)
        invoice.duedate = data.get("duedate", invoice.duedate)
        invoice.currency_id = data.get("currency_id", invoice.currency_id)
        invoice.template_id = data.get("template_id", invoice.template_id)

        # delete lines that are removed
        to_be_deleted = [line.get("id") for line in lines if line.get("id")]
        InvoiceLine.query.filter_by(invoice_id=invoice_id).filter(
            InvoiceLine.id.not_in(to_be_deleted)
        ).delete(synchronize_session=False)

        for line in lines:
            line = _with_code_id(line, codes)
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
                invoiceline.unit_price = line.get(
                    "unit_price", invoiceline.unit_price
                )
                invoiceline.description = line.get(
                    "description", invoiceline.description
                )
                invoiceline.vat_code_id = line["vat_code_id"]
                invoice.lines.append(invoiceline)
            else:
                Product.query.filter_by(
                    organization_id=organization_id, id=line.get("product_id")
                ).first_or_404(
                    description=f"Product with id {line.get('product_id')} not found!"
                )
                invoice.lines.append(InvoiceLine(**line))

        db.session.flush()
        saved_lines = (
            InvoiceLine.query.filter_by(invoice_id=invoice.id)
            .order_by(InvoiceLine.id)
            .all()
        )
        apply_totals(invoice, saved_lines, _by_id(codes))
        invoice.update()
        return invoice_schema_with_lines.dump(invoice), 200
    except (MoneyError, InvoiceVatError) as e:
        db.session.rollback()
        return {"error": str(e)}, 422
    except exc.IntegrityError as e:
        db.session.rollback()
        return {"error": str(e)}, 202
    except FileNotFoundError as e:
        return {"eerror": str(e)}, 404


@bp.delete("/organizations/<int:organization_id>/invoices/<int:invoice_id>")
@jwt_required()
@org_member_required
def delete_invoice(organization_id, invoice_id):
    invoice = Invoice.query.filter_by(
        organization_id=organization_id, id=invoice_id
    ).first_or_404(description=f"Invoice with id {invoice_id} not found!")
    # Once approved an invoice is part of the books: deleting it would leave a
    # gap in the numbering, and its voucher without a document.
    if invoice.state != "draft":
        return {"error": "Only draft invoices can be deleted"}, 409
    try:
        invoice.delete()
        return {
            "message": f"invoice with id {invoice_id} and all its lines are deleted!!"
        }, 200
    except Exception as e:
        return {"error": str(e)}, 400


@bp.post(
    "/organizations/<int:organization_id>/invoices/<int:invoice_id>/approve"
)
@jwt_required()
@org_member_required
def approve_invoice_route(organization_id, invoice_id):
    """Approve a draft invoice: it gets its number and is posted to the
    ledger, and from then on it cannot be changed. The body is optional: the
    invoice number, for an organization that numbers its invoices by hand."""
    try:
        data = approve_input_schema.load(request.get_json(silent=True) or {})
        invoice = approve_invoice(
            organization_id,
            current_user.id,
            invoice_id,
            invoice_no=data.get("invoice_no"),
        )
        db.session.commit()
    except ValidationError as error:
        db.session.rollback()
        return {"errors": error.messages}, 422
    except LedgerError as error:
        db.session.rollback()
        return {"error": str(error)}, error.status
    return invoice_schema_with_lines.dump(invoice), 200
