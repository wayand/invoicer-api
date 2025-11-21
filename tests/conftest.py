import os
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner
from flask_migrate import upgrade as db_upgrade
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app import create_app
from app.models.base import db
from app.models.country import Country
from app.models.organization import Organization
from app.models.user import User
from config import TestingConfig

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME")


@pytest.fixture(scope="module")
def new_user():
    user = User(1, "demo_test@gmail.com", "TheName", "TheTextPassword")
    return user


def create_test_db():
    """Create the test db, if not already exists"""

    engine = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        # 2. Create test_db if it doesn’t exist
        exists = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname='{TEST_DB_NAME}'")
        ).scalar()

        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
            print(f"Database '{TEST_DB_NAME}' created.")


def drop_test_db():
    """Drop the test database after all tests."""
    engine = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        # disconnect all sessions first (Postgres requires no connections to drop)
        conn.execute(
            text(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid();
        """)
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        print(f"Database '{TEST_DB_NAME}' dropped.")


@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    """
    Create the test db schema before any tests run,
    and drop it after tests are done.
    """
    create_test_db()

    os.environ["SQLALCHEMY_DATABASE_URI"] = (
        f"{TEST_DATABASE_URL}/{TEST_DB_NAME}"
    )

    TestingConfig.SQLALCHEMY_DATABASE_URI = os.environ[
        "SQLALCHEMY_DATABASE_URI"
    ]
    app: Flask = create_app(TestingConfig)

    with app.app_context():
        db_upgrade()  # Run Alembic migrations

        yield app

        db.session.remove()
        drop_test_db()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def db_session(app: Flask) -> Generator[Session, None, None]:
    """
    Each test is isolated, and the test database is fresh every time

    • At the start of a test, the fixture opens a database transaction.
    • All inserts, updates, and deletes happen inside that transaction.
    • When the test finishes, the fixture rolls the transaction back.
    • Because of this rollback, nothing is permanently written to the test database.
    • The next test starts with a completely clean state.
    """
    connection = db.engine.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(
        bind=connection, autoflush=False, future=True
    )
    sessionRegistry = scoped_session(session_factory)

    # preserve original db.session so we can restore later (best practice)
    original_db_session = getattr(db, "session", None)
    db.session = sessionRegistry

    try:
        yield sessionRegistry
    finally:
        # remove scoped session, rollback transaction, close connection
        sessionRegistry.remove()  # removes all sessions; this provides .remove() behavior
        transaction.rollback()
        connection.close()
        # restore original db.session if needed
        if original_db_session is not None:
            db.session = original_db_session


@pytest.fixture
def runner(app: Flask) -> FlaskCliRunner:
    return app.test_cli_runner()


@pytest.fixture
def country(db_session):
    c = Country(currency_id="DKK", locale_id="da_DK", name="Danmark", icon="dk")
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def organization(db_session, country: Country):
    org = Organization(
        name="Demo ApS",
        slug="demo-aps",
        country_id=country.id,
        email="demo@hotmail.com",
        logo="",
    )
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def test_user(db_session, organization: Organization) -> User:
    user = User(
        organization_id=organization.id,
        password_plaintext="password123",
        name="test name",
        email="test@example.com",
        otp_secret=User.generate_otp_secret(),
    )

    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def tokens(client: FlaskClient, test_user):
    otp = test_user.get_totp_code(expire_in_sec=3600)
    assert test_user.verify_totp(otp, expire_in_sec=3600)

    payload = {
        "email": "test@example.com",
        "password": "password123",
        "otp_2fa": otp,
    }
    res = client.post("/auth/token", json=payload)
    assert res.status_code == 200

    data = res.get_json()
    assert "accessToken" in data
    assert "refreshToken" in data

    return {
        "accessToken": data["accessToken"],
        "refreshToken": data["refreshToken"],
    }
