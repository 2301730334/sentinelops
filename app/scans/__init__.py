from flask import Blueprint

bp = Blueprint("scans", __name__, url_prefix="/scans")

from . import routes  # noqa: E402,F401
