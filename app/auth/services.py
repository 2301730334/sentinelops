"""User account operations shared by the web UI and the REST API."""
from __future__ import annotations

import logging

from sqlalchemy import func, or_, select

from ..errors import AppError, ValidationError
from ..extensions import db
from ..models import User
from .validators import validate_registration

log = logging.getLogger(__name__)


def register_user(username: str, email: str, password: str, confirm: str | None = None) -> User:
    username = (username or "").strip()
    email = (email or "").strip().lower()
    errors = validate_registration(username, email, password, confirm)
    if errors:
        raise ValidationError("Registration details are invalid.", details={"fields": errors})

    existing = db.session.scalar(
        select(User).where(or_(func.lower(User.username) == username.lower(), User.email == email))
    )
    if existing:
        raise AppError("That username or email is already registered.", status_code=409,
                       error_type="conflict")

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    log.info("user_registered", extra={"user_id": user.id})
    return user


def authenticate(username_or_email: str, password: str) -> User | None:
    ident = (username_or_email or "").strip()
    user = db.session.scalar(
        select(User).where(or_(func.lower(User.username) == ident.lower(), User.email == ident.lower()))
    )
    if user and user.check_password(password or ""):
        return user
    log.info("login_failed")
    return None
