from flask_jwt_extended import jwt_required
from sqlalchemy import and_

from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.invoiceline_schema import (
    invoiceline_schema,
    invoicelines_schema,
)
from app.routes import bp


@bp.get(
    "/organizations/<int:organization_id>/invoices/<int:invoice_id>/invoice-lines"
)
@jwt_required()
def get_invoicelines(organization_id, invoice_id):
    invoicelines = (
        InvoiceLine.query.filter_by(invoice_id=invoice_id)
        .join(Invoice)
        .filter(
            and_(
                Invoice.organization_id == organization_id,
                Invoice.id == invoice_id,
            )
        )
    )
    return invoicelines_schema.jsonify(invoicelines)


@bp.get(
    "/organizations/<int:organization_id>/invoices/<int:invoice_id>/invoice-lines/<int:line_id>"
)
@jwt_required()
def get_invoiceline(organization_id, invoice_id, line_id):
    invoiceline = (
        InvoiceLine.query.filter_by(invoice_id=invoice_id, id=line_id)
        .join(Invoice)
        .filter(
            and_(
                Invoice.organization_id == organization_id,
                Invoice.id == invoice_id,
            )
        )
        .first_or_404(
            description=f"InvoiceLine with id {line_id} for invoice id {invoice_id} not found !"
        )
    )
    return invoiceline_schema.jsonify(invoiceline)


@bp.delete(
    "/organizations/<int:organization_id>/invoices/<int:invoice_id>/invoice-lines/<int:line_id>"
)
@jwt_required()
def delete_invoiceline(organization_id, invoice_id, line_id):
    invoiceline = (
        InvoiceLine.query.filter_by(invoice_id=invoice_id, id=line_id)
        .join(Invoice)
        .filter(
            and_(
                Invoice.organization_id == organization_id,
                Invoice.id == invoice_id,
            )
        )
        .first_or_404(
            description=f"InvoiceLine with id {line_id} for invoice id {invoice_id} not found !"
        )
    )
    invoiceline.delete()
    return {
        "message": f"invoiceline with id {line_id} is deleted from invoice id {invoice_id}!!"
    }, 200
