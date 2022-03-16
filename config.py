import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config():
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    CSRF_SESSION_KEY = "secret"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_SECRET_KEY = b'\x1d\xb4n\x8e\x10\xa6\x1b:\r\xb3\xfc}_\xed\xf0\xce'

    UPLOAD_FOLDER = './uploads'
    MAX_CONTENT_LENGTH = 1024 * 2048
    ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    OTP_SECRET = 'S4QW7FGWN7D4OJGN'

    MAIL_SERVER = 'smtp.sendgrid.net'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'apikey'
    MAIL_PASSWORD = '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'
    MAIL_DEFAULT_SENDER = 'lawangjan@gmail.com'

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

class DevelopmentConfig(Config):
    DEBUG = True
    ENV = "development"
    DEVELOPMENT = True
    SQLALCHEMY_ECHO = False
    # SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'my_secrets.db')}"
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://root@localhost:3306/invoicer_db"

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'