import os
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))

# Only for development and tests. Production has no fallback.
DEV_SECRET_KEY = "dev-only-secret-key-not-for-production"

# Values that have appeared in sample files or tutorials, compared in lower case.
KNOWN_PLACEHOLDERS = {
    "you-will-never-guess",
    "some_very_secure_key",
    "csrf_session_key_here",
    "super-secret",
    "salt-for-email-confirmation",
    "change-me-change-me-change-me-change-me",
    DEV_SECRET_KEY,
}
MIN_KEY_LENGTH = 32
MIN_SALT_LENGTH = 16


class ConfigError(RuntimeError):
    """The configuration is not safe to run with."""


class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY")

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

    @classmethod
    def validate(cls):
        """Raise ConfigError if the configuration is not safe to run with."""


class ProductionConfig(Config):
    DEBUG = False
    SITE_DOMAIN = "https://invoicer.wayand.dk"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        """Refuse to start with a missing, short or well-known secret, so a
        misconfigured server fails loudly instead of signing tokens with a key
        anyone can guess. Reports every problem, never a value."""
        checks = {
            "SECRET_KEY": MIN_KEY_LENGTH,
            "JWT_SECRET_KEY": MIN_KEY_LENGTH,
            "SECURITY_PASSWORD_SALT": MIN_SALT_LENGTH,
            "SQLALCHEMY_DATABASE_URI": None,
        }
        problems = []
        for name, minimum in checks.items():
            value = (getattr(cls, name, None) or "").strip()
            if not value:
                problems.append(f"{name} is missing")
            elif minimum is None:
                continue
            elif value.lower() in KNOWN_PLACEHOLDERS:
                problems.append(f"{name} is a well-known placeholder value")
            elif len(value) < minimum:
                problems.append(
                    f"{name} is too short ({len(value)} characters, "
                    f"need at least {minimum})"
                )
        if problems:
            raise ConfigError(
                "Refusing to start with an insecure configuration: "
                + "; ".join(problems)
                + ". Generate secrets with: python -c "
                '"import secrets; print(secrets.token_urlsafe(48))"'
            )


class DevelopmentConfig(Config):
    SECRET_KEY = os.environ.get("SECRET_KEY") or DEV_SECRET_KEY
    DEBUG = True
    ENV = "development"
    DEVELOPMENT = True
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


class TestingConfig(Config):
    SECRET_KEY = os.environ.get("SECRET_KEY") or DEV_SECRET_KEY
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL")
