"""SentinelOps: IoT threat-detection service (application factory)."""
from __future__ import annotations

import os

from flask import Flask

from .config import ensure_secret_key, get_config
from .errors import register_error_handlers
from .extensions import db, migrate
from .logging_config import configure_logging

__version__ = "0.1.0"


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config(config_name))
    if overrides:
        app.config.update(overrides)
    app.config["APP_VERSION"] = os.environ.get("APP_VERSION", __version__)

    configure_logging(app)
    ensure_secret_key(app)
    _ensure_sqlite_dir(app)

    db.init_app(app)
    migrate.init_app(app, db)

    register_error_handlers(app)
    register_blueprints(app)
    _register_security_headers(app)

    app.logger.info(
        "app_started",
        extra={"env": app.config["ENV_NAME"], "version": app.config["APP_VERSION"]},
    )
    return app


def register_blueprints(app: Flask) -> None:
    from .main import bp as main_bp

    app.register_blueprint(main_bp)


def _ensure_sqlite_dir(app: Flask) -> None:
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        path = uri[len("sqlite:///"):]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def _headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
