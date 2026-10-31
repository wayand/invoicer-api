from flask_jwt_extended import jwt_required

from app.models.vat_code import VatCode
from app.models.vat_code_schema import vat_codes_schema
from app.routes import bp


@bp.get("/vat-codes")
@jwt_required()
def get_vat_codes():
    """Every official VAT code, supported or not, in the order of the list.
    The codes are the same for every organization."""
    codes = VatCode.query.order_by(VatCode.id)
    return vat_codes_schema.jsonify(codes)
