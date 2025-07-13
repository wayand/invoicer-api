from flask import request, abort, Blueprint, current_app as app
import sys

bp = Blueprint('routes', __name__)

# @bp.before_request
# def limit_remote_addr():
#     trusted_ips = ('127.0.0.1', '138.197.190.226', '10.135.16.185')
#     if not request.remote_addr in trusted_ips:
#         abort(403, description=f'your ip addr. is: => {request.remote_addr}')  # Forbidden

@bp.errorhandler(404)
def page_not_found(error):
    app.logger.error('404', exc_info=sys.exc_info())
    return {'error': '404 We couldn\'t find the page/item you\'re looking for.'}, 404

@bp.errorhandler(500)
def internal_error(error):
    app.logger.error('Unhandled exception', exc_info=sys.exc_info())
    return {'error': '500 Internal Server Error.'}, 500

from app.routes import organization_routes
from app.routes import taxrate_routes
from app.routes import country_routes
from app.routes import product_routes
from app.routes import client_routes
from app.routes import account_routes
from app.routes import invoice_routes
from app.routes import invoiceline_routes
from app.routes import auth_routes
from app.routes import invoice_setting_routes