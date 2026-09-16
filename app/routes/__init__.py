import sys

from flask import Blueprint
from flask import current_app as app

bp = Blueprint("routes", __name__)

from app.routes import (
    account_routes,
    auth_routes,
    contact_routes,
    country_routes,
    invoice_routes,
    invoice_setting_routes,
    invoiceline_routes,
    organization_routes,
    product_routes,
    taxrate_routes,
)

__all__ = [
    "account_routes",
    "auth_routes",
    "contact_routes",
    "country_routes",
    "invoice_routes",
    "invoice_setting_routes",
    "invoiceline_routes",
    "organization_routes",
    "product_routes",
    "taxrate_routes",
]


@bp.errorhandler(404)
def page_not_found(error):
    app.logger.error("404", exc_info=sys.exc_info())
    return {
        "error": "404 We couldn't find the page/item you're looking for."
    }, 404


@bp.errorhandler(500)
def internal_error(error):
    app.logger.error("Unhandled exception", exc_info=sys.exc_info())
    return {"error": "500 Internal Server Error."}, 500
