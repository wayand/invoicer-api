from flask_jwt_extended import current_user, jwt_required

from app.models.tax_rate import TaxRate
from app.models.taxrate_schema import taxrates_schema
from app.routes import bp


@bp.get("/tax-rates")
@jwt_required()
def get_taxrates():
    organization_id = current_user.organization_id
    tax_rates = TaxRate.query.filter_by(organization_id=organization_id)
    return taxrates_schema.jsonify(tax_rates)
