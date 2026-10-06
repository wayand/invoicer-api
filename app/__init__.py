import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from flasgger import Swagger
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

# from app.routes import page_not_found

mail = Mail()
migrate = Migrate()
jwt = JWTManager()
swagger = Swagger()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_class):
    app = Flask(__name__)
    app.config.from_object(config_class)

    proxies = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies)

    limiter.init_app(app)

    @app.errorhandler(RateLimitExceeded)
    def too_many_attempts(_error):
        response = jsonify(error="Too many attempts. Please try again later.")
        response.status_code = 429
        return response

    CORS(
        app,
        origins=[
            "http://localhost:8080",
            "http://localhost:5001",
            "https://invoicer.wayand.dk",
            "http://127.0.0.1:8080",
        ],
        supports_credentials=True,
    )

    mail.init_app(app)
    swagger.init_app(app)

    from app.models.base import db
    from app.routes import bp as routes_bp

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    app.register_blueprint(routes_bp)

    if app.debug:  ## change it to only log when in production
        if not os.path.exists("logs"):
            os.mkdir("logs")

        file_handler = TimedRotatingFileHandler(
            "logs/invoicer_api.log",
            when="D",
            utc=True,
            interval=1,
            backupCount=10,
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)

        logging.getLogger("flask_cors").level = logging.DEBUG

        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info("Invoicer startup...")

        def page_not_found(error):
            app.logger.error("404 Page Not found", exc_info=sys.exc_info())
            return {"error": str(error)}, 404

        app.register_error_handler(404, page_not_found)

        def internal_server_error(error):
            app.logger.error(
                "500 Internal Server Error", exc_info=sys.exc_info()
            )
            return {"error": str(error)}, 500

        app.register_error_handler(500, internal_server_error)

        # print('JWT_BLACKLIST_ENABLED', app.config.get("JWT_BLACKLIST_ENABLED", 'not found'))
        # print('JWT_BLACKLIST_TOKEN_CHECKS', app.config.get("JWT_BLACKLIST_TOKEN_CHECKS", 'not found'))
        # print('JWT_TOKEN_LOCATION', app.config["JWT_TOKEN_LOCATION"])

    return app
