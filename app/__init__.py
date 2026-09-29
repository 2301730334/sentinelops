"""SentinelOps: IoT threat-detection service (application factory)."""
from __future__ import annotations

import os

from flask import Flask, flash, redirect, request, url_for

from .config import ensure_secret_key, get_config
from .errors import register_error_handlers
from .extensions import db, login_manager, migrate
from .logging_config import configure_logging
from .security import init_csrf

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

    from . import models  # noqa: F401  (register models with SQLAlchemy/Alembic)

    db.init_app(app)
    migrate.init_app(app, db)
    _init_login(app)
    init_csrf(app)

    register_error_handlers(app)
    register_blueprints(app)
    _register_security_headers(app)

    app.logger.info(
        "app_started",
        extra={"env": app.config["ENV_NAME"], "version": app.config["APP_VERSION"]},
    )
    return app


def register_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)


def _init_login(app: Flask) -> None:
    from .errors import error_response, wants_json
    from .models import User

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if wants_json():
            return error_response(401, "Authentication required.")
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


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
