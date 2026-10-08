import os
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-will-never-guess"

    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = None

    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

    CSRF_ENABLED = True
    CSRF_SESSION_KEY = os.environ.get("CSRF_SESSION_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT")

    # Public address of the Vue app, used for links in emails.
    SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "http://localhost:8080")

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_STRATEGY = "moving-window"
    RATELIMIT_HEADERS_ENABLED = True
    # Number of reverse proxies in front of the app whose X-Forwarded-For we
    # trust. 0 = trust none (client IP is the direct peer).
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER")
    MAX_CONTENT_LENGTH = 1024 * 2048
    ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = os.environ.get("MAIL_PORT")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")


class ProductionConfig(Config):
    DEBUG = False
    SITE_DOMAIN = "https://invoicer.wayand.dk"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = "development"
    DEVELOPMENT = True
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL")
