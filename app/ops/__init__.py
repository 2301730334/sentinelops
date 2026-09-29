"""Operational endpoints for Kubernetes probes.

/healthz  liveness: the process is up and serving requests (no dependencies)
/readyz   readiness: the database answers and the model is loaded
"""
from __future__ import annotations

import logging
import time

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from ..extensions import db
from ..ml import get_predictor

bp = Blueprint("ops", __name__)
log = logging.getLogger(__name__)


@bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "version": current_app.config["APP_VERSION"]})


@bp.get("/readyz")
def readyz():
    checks: dict[str, dict] = {}
    ready = True

    start = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok",
                              "latency_ms": round((time.perf_counter() - start) * 1000, 2)}
    except Exception as exc:
        db.session.rollback()
        ready = False
        checks["database"] = {"status": "error", "error": type(exc).__name__}
        log.warning("readiness_db_failed", extra={"error": str(exc)})

    try:
        checks["model"] = {"status": "ok", "version": get_predictor().version}
    except Exception as exc:
        ready = False
        checks["model"] = {"status": "error", "error": getattr(exc, "message", type(exc).__name__)}
        log.warning("readiness_model_failed", extra={"error": str(exc)})

    body = {"status": "ready" if ready else "not_ready", "checks": checks,
            "version": current_app.config["APP_VERSION"]}
    return jsonify(body), 200 if ready else 503
