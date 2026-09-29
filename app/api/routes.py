from flask import current_app, g, jsonify, request, url_for

from ..auth.services import authenticate, register_user
from ..errors import AppError
from ..services import scans as svc
from . import bp
from .auth import Unauthorized, issue_token, token_required


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AppError("Request body must be a JSON object (Content-Type: application/json).")
    return data


def _int_arg(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise AppError(f"'{name}' must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f">= {minimum}" + (f" and <= {maximum}" if maximum else "")
        raise AppError(f"'{name}' must be {bounds}.")
    return value


def _page_args(default_per_page: int) -> tuple[int, int]:
    return (_int_arg("page", 1),
            _int_arg("per_page", default_per_page, maximum=current_app.config["API_PAGE_SIZE_MAX"]))


def _paged(pagination, items) -> dict:
    return {"items": items, "page": pagination.page, "per_page": pagination.per_page,
            "total": pagination.total, "pages": pagination.pages}


def _scan_json(scan) -> dict:
    data = scan.to_dict()
    data["links"] = {
        "self": url_for("api.get_scan", scan_id=scan.id),
        "results": url_for("api.get_scan_results", scan_id=scan.id),
    }
    return data


@bp.get("")
def index():
    return jsonify({
        "name": "SentinelOps API", "version": "v1",
        "endpoints": {
            "register": "POST /api/v1/auth/register",
            "token": "POST /api/v1/auth/token",
            "scans": "GET, POST /api/v1/scans",
            "scan": "GET, PATCH, DELETE /api/v1/scans/<id>",
            "results": "GET /api/v1/scans/<id>/results",
        },
    })


# ---- auth -----------------------------------------------------------------

@bp.post("/auth/register")
def register():
    data = _json_body()
    user = register_user(data.get("username", ""), data.get("email", ""), data.get("password", ""))
    return jsonify(user.to_dict()), 201


@bp.post("/auth/token")
def token():
    data = _json_body()
    user = authenticate(data.get("username", ""), data.get("password", ""))
    if user is None:
        raise Unauthorized("Invalid username or password.")
    return jsonify({"access_token": issue_token(user), "token_type": "Bearer",
                    "expires_in": current_app.config["API_TOKEN_TTL_SECONDS"]})


@bp.get("/auth/me")
@token_required
def me():
    return jsonify(g.api_user.to_dict())


# ---- scans ----------------------------------------------------------------

@bp.get("/scans")
@token_required
def list_scans():
    page, per_page = _page_args(20)
    pagination = svc.list_scans(g.api_user, page=page, per_page=per_page)
    return jsonify(_paged(pagination, [_scan_json(s) for s in pagination.items]))


@bp.post("/scans")
@token_required
def create_scan():
    scan = svc.create_scan(g.api_user, request.files.get("file"),
                           name=request.form.get("name"), notes=request.form.get("notes"))
    response = jsonify(_scan_json(scan))
    response.status_code = 201
    response.headers["Location"] = url_for("api.get_scan", scan_id=scan.id)
    return response


@bp.get("/scans/<int:scan_id>")
@token_required
def get_scan(scan_id: int):
    return jsonify(_scan_json(svc.get_scan(g.api_user, scan_id)))


@bp.get("/scans/<int:scan_id>/results")
@token_required
def get_scan_results(scan_id: int):
    scan = svc.get_scan(g.api_user, scan_id)
    page, per_page = _page_args(50)
    pagination = svc.scan_results(scan, page=page, per_page=per_page,
                                  label=request.args.get("label") or None)
    return jsonify(_paged(pagination, [r.to_dict() for r in pagination.items]))


@bp.patch("/scans/<int:scan_id>")
@token_required
def update_scan(scan_id: int):
    scan = svc.get_scan(g.api_user, scan_id)
    data = _json_body()
    unknown = set(data) - {"filename", "notes"}
    if unknown:
        raise AppError(f"Unknown fields: {sorted(unknown)}. Allowed: filename, notes.")
    if not data:
        raise AppError("Provide at least one of: filename, notes.")
    for field in ("filename", "notes"):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            raise AppError(f"'{field}' must be a string.")
    notes = None  # None means "leave unchanged"
    if "notes" in data:
        notes = data["notes"] or ""  # null or "" clears the notes
    svc.update_scan(scan, filename=data.get("filename"), notes=notes)
    return jsonify(_scan_json(scan))


@bp.delete("/scans/<int:scan_id>")
@token_required
def delete_scan(scan_id: int):
    svc.delete_scan(svc.get_scan(g.api_user, scan_id))
    return "", 204
