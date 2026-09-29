"""Structured JSON logging to stdout.

One JSON object per line so that Fluentd / Logstash (Phase 5) can ship logs
without extra parsing rules. Every request gets a request id (taken from the
incoming X-Request-ID header or generated) that is added to each log line and
echoed back in the response.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, g, has_request_context, request

# Attributes present on every LogRecord; anything else was passed via `extra=`.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str = "sentinelops"):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
        }
        if has_request_context():
            payload["request_id"] = getattr(g, "request_id", None)
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=app.config.get("APP_NAME", "sentinelops").lower()))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # Let Flask's logger propagate to the root JSON handler instead of its own.
    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(level)

    # Werkzeug's own access log duplicates ours; keep only its warnings.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    _register_request_logging(app)


def _register_request_logging(app: Flask) -> None:
    access_log = logging.getLogger("sentinelops.access")

    @app.before_request
    def _start_timer():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming[:64] if incoming else uuid.uuid4().hex
        g.request_start = time.perf_counter()

    @app.after_request
    def _log_request(response):
        start = getattr(g, "request_start", None)
        duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        # Skip noisy probe/scrape endpoints at INFO level.
        quiet = request.path in {"/healthz", "/readyz", "/metrics"}
        access_log.log(
            logging.DEBUG if quiet else logging.INFO,
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
            },
        )
        return response
