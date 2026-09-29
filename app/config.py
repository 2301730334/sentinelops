"""Application configuration.

All settings come from environment variables (12-factor). Nothing secret is
hard-coded: SECRET_KEY must be supplied in production, and a throw-away random
key is generated for development/testing when it is missing.
"""
from __future__ import annotations

import os
import secrets

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got {value!r}") from exc


def _database_url(default: str) -> str:
    url = os.environ.get("DATABASE_URL") or default
    # Some platforms still hand out the legacy "postgres://" scheme.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _resolve_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


class Config:
    APP_NAME = "SentinelOps"
    ENV_NAME = "base"

    SECRET_KEY = os.environ.get("SECRET_KEY") or None

    SQLALCHEMY_DATABASE_URI = _database_url(
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "sentinelops.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Uploads
    MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 5)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    MAX_CSV_ROWS = _env_int("MAX_CSV_ROWS", 20000)

    # ML
    MODEL_PATH = _resolve_path(os.environ.get("MODEL_PATH", "models/model.joblib"))
    MODEL_FALLBACK_STUB = _env_bool("MODEL_FALLBACK_STUB", True)

    # API
    API_TOKEN_TTL_SECONDS = _env_int("API_TOKEN_TTL_SECONDS", 3600)
    API_PAGE_SIZE_MAX = 100

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Security
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True

    # Metrics
    METRICS_ENABLED = True


class DevelopmentConfig(Config):
    ENV_NAME = "development"
    DEBUG = False  # enable with FLASK_DEBUG=1 on the CLI


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}
    CSRF_ENABLED = False
    MAX_CSV_ROWS = 500
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024
    LOG_LEVEL = "WARNING"


class ProductionConfig(Config):
    ENV_NAME = "production"
    MODEL_FALLBACK_STUB = _env_bool("MODEL_FALLBACK_STUB", False)
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    name = (name or os.environ.get("APP_ENV") or "development").lower()
    try:
        return CONFIGS[name]
    except KeyError as exc:
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of {sorted(CONFIGS)}") from exc


def ensure_secret_key(app) -> None:
    """Fail fast in production without a SECRET_KEY; use an ephemeral one otherwise."""
    if app.config.get("SECRET_KEY"):
        return
    if app.config.get("ENV_NAME") == "production":
        raise RuntimeError("SECRET_KEY must be set in production")
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.logger.warning(
        "SECRET_KEY not set; using an ephemeral random key (sessions reset on restart)"
    )
