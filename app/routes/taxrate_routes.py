from flask import request
from app.routes import bp
from app.models import TaxRate, taxrate_schema, taxrates_schema
from flask_jwt_extended import (
    jwt_required,
    current_user
)

@bp.get("/tax-rates")
@jwt_required()
def get_taxrates():
    organization_id = current_user.organization_id
    tax_rates = TaxRate.query.filter_by(organization_id=organization_id)
    return taxrates_schema.jsonify(tax_rates)