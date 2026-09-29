"""Small security helpers: CSRF protection for HTML forms and safe redirects.

The REST API under /api/ is authenticated with bearer tokens (no cookies), so
it is exempt from CSRF checks.
"""
from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit

from flask import Flask, abort, request, session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_SESSION_KEY = "_csrf_token"


def generate_csrf_token() -> str:
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def init_csrf(app: Flask) -> None:
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def _csrf_protect():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if request.method in _SAFE_METHODS or request.path.startswith("/api/"):
            return None
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get(_SESSION_KEY, "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="Your form session expired. Please reload the page and try again.")
        return None


def is_safe_redirect(target: str | None) -> bool:
    """Only allow relative, same-site redirect targets (prevents open redirects)."""
    if not target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")
