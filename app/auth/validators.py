"""Input validation for registration and login."""
from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def validate_registration(username: str, email: str, password: str,
                          confirm: str | None = None) -> dict[str, str]:
    """Return a mapping of field -> error message (empty when valid)."""
    errors: dict[str, str] = {}
    if not USERNAME_RE.match(username or ""):
        errors["username"] = "Username must be 3-32 characters: letters, digits or underscore."
    if not EMAIL_RE.match(email or "") or len(email) > 255:
        errors["email"] = "Enter a valid email address."
    if len(password or "") < MIN_PASSWORD_LENGTH:
        errors["password"] = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    elif len(password) > 128:
        errors["password"] = "Password must be at most 128 characters."
    if confirm is not None and confirm != password:
        errors["confirm"] = "Passwords do not match."
    return errors
