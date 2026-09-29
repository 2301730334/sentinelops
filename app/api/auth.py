"""Bearer-token authentication for the API.

Tokens are signed with SECRET_KEY (itsdangerous, bundled with Flask) and
expire after API_TOKEN_TTL_SECONDS. They embed a fingerprint of the user's
password hash, so changing the password invalidates every issued token.
"""
from __future__ import annotations

import hashlib
from functools import wraps

from flask import current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..errors import AppError
from ..extensions import db
from ..models import User

_SALT = "sentinelops.api-token.v1"


class Unauthorized(AppError):
    status_code = 401
    error_type = "unauthorized"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def _fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def issue_token(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "fp": _fingerprint(user)})


def verify_token(token: str) -> User:
    try:
        data = _serializer().loads(token, max_age=current_app.config["API_TOKEN_TTL_SECONDS"])
    except SignatureExpired:
        raise Unauthorized("Token expired. Request a new one from /api/v1/auth/token.")
    except BadSignature:
        raise Unauthorized("Invalid token.")
    user = db.session.get(User, data.get("uid")) if isinstance(data, dict) else None
    if user is None or data.get("fp") != _fingerprint(user):
        raise Unauthorized("Invalid token.")
    return user


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise Unauthorized("Missing bearer token. Send 'Authorization: Bearer <token>'.")
        g.api_user = verify_token(token.strip())
        return view(*args, **kwargs)
    return wrapper
