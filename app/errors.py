"""Centralised error handling.

API requests (paths under /api/) always get a JSON error body:

    {"error": {"status": 422, "type": "unprocessable_entity",
               "message": "...", "details": {...}}, "request_id": "..."}

Browser requests get a friendly HTML page rendered from errors/error.html.
"""
from __future__ import annotations

import logging

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    """Domain error that maps cleanly to an HTTP status."""

    status_code = 400
    error_type = "bad_request"

    def __init__(self, message: str, status_code: int | None = None,
                 details: dict | None = None, error_type: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_type is not None:
            self.error_type = error_type
        self.details = details or {}


class ValidationError(AppError):
    status_code = 422
    error_type = "validation_error"


FRIENDLY = {
    400: ("Bad request", "The request could not be understood."),
    401: ("Please sign in", "You need to be signed in to see this page."),
    403: ("Forbidden", "You don't have permission to do that."),
    404: ("Not found", "We couldn't find what you were looking for."),
    405: ("Method not allowed", "That action isn't supported here."),
    413: ("File too large", "The uploaded file is larger than the allowed limit."),
    415: ("Unsupported file type", "Please upload a .csv file."),
    422: ("Invalid input", "The submitted data could not be processed."),
    429: ("Too many requests", "Please slow down and try again shortly."),
    500: ("Something went wrong", "An unexpected error occurred. It has been logged."),
    503: ("Service unavailable", "The service is temporarily unavailable."),
}


def wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _type_from_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


def error_response(status: int, message: str, error_type: str | None = None,
                   details: dict | None = None):
    title, default_msg = FRIENDLY.get(status, ("Error", "An error occurred."))
    if wants_json():
        body = {
            "error": {
                "status": status,
                "type": error_type or _type_from_name(title),
                "message": message or default_msg,
            },
            "request_id": getattr(g, "request_id", None),
        }
        if details:
            body["error"]["details"] = details
        response = jsonify(body)
        response.status_code = status
        if status == 401:
            response.headers["WWW-Authenticate"] = 'Bearer realm="sentinelops"'
        return response
    html = render_template(
        "errors/error.html", status=status, title=title,
        message=message or default_msg, details=details,
    )
    return html, status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        log.info("app_error", extra={"status": err.status_code, "error": err.message})
        return error_response(err.status_code, err.message, err.error_type, err.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        status = err.code or 500
        message = err.description if status not in (404, 500) else None
        if status == 413:
            message = f"File exceeds the {app.config['MAX_UPLOAD_MB']} MB upload limit."
        return error_response(status, message)

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.exception("unhandled_exception")
        try:
            from .extensions import db
            db.session.rollback()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
        return error_response(500, None, "internal_server_error")
