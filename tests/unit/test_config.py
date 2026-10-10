"""
Production refuses to start with missing, short or well-known secrets, so a
misconfigured server fails loudly instead of signing tokens with a key
anyone can guess. Development and testing keep working without any setup.
"""

import pytest

import config
from app import create_app
from config import ConfigError, DevelopmentConfig, ProductionConfig

STRONG_KEY = "k" * 48
STRONG_SALT = "s" * 24


def production(**overrides):
    values = {
        "SECRET_KEY": STRONG_KEY,
        "JWT_SECRET_KEY": "j" * 48,
        "SECURITY_PASSWORD_SALT": STRONG_SALT,
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://u@localhost/db",
    }
    values.update(overrides)
    return type("TestProductionConfig", (ProductionConfig,), values)


def test_production_starts_with_strong_secrets():
    production().validate()
    assert create_app(production()) is not None


@pytest.mark.parametrize(
    "name",
    [
        "SECRET_KEY",
        "JWT_SECRET_KEY",
        "SECURITY_PASSWORD_SALT",
        "SQLALCHEMY_DATABASE_URI",
    ],
)
@pytest.mark.parametrize("missing", [None, "", "   "])
def test_production_refuses_a_missing_value(name, missing):
    with pytest.raises(ConfigError, match=name):
        production(**{name: missing}).validate()


@pytest.mark.parametrize(
    "name,too_short",
    [
        ("SECRET_KEY", "k" * 31),
        ("JWT_SECRET_KEY", "j" * 31),
        ("SECURITY_PASSWORD_SALT", "s" * 15),
    ],
)
def test_production_refuses_a_short_secret(name, too_short):
    with pytest.raises(ConfigError, match=f"{name}.*too short"):
        production(**{name: too_short}).validate()


@pytest.mark.parametrize(
    "name,at_minimum",
    [
        ("SECRET_KEY", "k" * 32),
        ("JWT_SECRET_KEY", "j" * 32),
        ("SECURITY_PASSWORD_SALT", "s" * 16),
    ],
)
def test_production_accepts_a_secret_of_exactly_the_minimum_length(
    name, at_minimum
):
    production(**{name: at_minimum}).validate()


@pytest.mark.parametrize(
    "placeholder",
    [
        "you-will-never-guess",
        "SOME_VERY_SECURE_KEY",
        "CSRF_SESSION_KEY_HERE",
        "super-secret",
        "salt-for-email-confirmation",
        "CHANGE-ME-CHANGE-ME-CHANGE-ME-CHANGE-ME",
    ],
)
@pytest.mark.parametrize(
    "name", ["SECRET_KEY", "JWT_SECRET_KEY", "SECURITY_PASSWORD_SALT"]
)
def test_production_refuses_a_known_placeholder(name, placeholder):
    # Padded so only the placeholder check, not the length check, can catch it
    with pytest.raises(ConfigError, match=f"{name}.*placeholder"):
        production(**{name: placeholder}).validate()


def test_production_refuses_a_placeholder_whatever_its_case_or_padding():
    with pytest.raises(ConfigError, match="SECRET_KEY.*placeholder"):
        production(SECRET_KEY="  Super-Secret  ").validate()


def test_every_problem_is_reported_at_once():
    with pytest.raises(ConfigError) as error:
        production(SECRET_KEY=None, JWT_SECRET_KEY="short").validate()

    message = str(error.value)
    assert "SECRET_KEY" in message
    assert "JWT_SECRET_KEY" in message


def test_the_error_never_contains_the_secret():
    secret = "do-not-print-me"
    with pytest.raises(ConfigError) as error:
        production(JWT_SECRET_KEY=secret).validate()

    assert secret not in str(error.value)


def test_create_app_refuses_to_start_with_a_weak_production_config():
    with pytest.raises(ConfigError):
        create_app(production(JWT_SECRET_KEY="short"))


def test_there_is_no_default_secret_key_in_production(monkeypatch):
    # An empty SECRET_KEY must stay empty (and be refused), not turn into a
    # built-in default. Set rather than deleted, so a local .env can't fill it.
    monkeypatch.setenv("SECRET_KEY", "")

    import importlib

    reloaded = importlib.reload(config)
    try:
        assert not reloaded.ProductionConfig.SECRET_KEY
        with pytest.raises(reloaded.ConfigError, match="SECRET_KEY is missing"):
            reloaded.ProductionConfig.validate()
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_development_and_testing_need_no_secrets():
    DevelopmentConfig.validate()
    config.TestingConfig.validate()
    assert config.TestingConfig.SECRET_KEY
    assert config.DevelopmentConfig.SECRET_KEY


def test_env_sample_holds_no_usable_secrets():
    """Copying .env.sample to a server must not start production."""
    from pathlib import Path

    sample = (Path(config.basedir) / ".env.sample").read_text()
    values = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1]
        .strip()
        .strip("'\"")
        for line in sample.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    for name in ("SECRET_KEY", "JWT_SECRET_KEY", "SECURITY_PASSWORD_SALT"):
        assert values.get(name, "") == "", f"{name} has a value in .env.sample"
