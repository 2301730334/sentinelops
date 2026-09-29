"""REST API v1: stateless JSON endpoints authenticated with bearer tokens."""
from flask import Blueprint

bp = Blueprint("api", __name__, url_prefix="/api/v1")

from . import routes  # noqa: E402,F401
