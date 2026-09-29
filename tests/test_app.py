import json
import logging

import pytest

from app import create_app
from app.config import get_config
from app.logging_config import JsonFormatter


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"SentinelOps" in resp.data


def test_security_headers_and_request_id(client):
    resp = client.get("/", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Request-ID"] == "abc123"


def test_request_id_generated_when_missing(client):
    resp = client.get("/")
    assert len(resp.headers["X-Request-ID"]) == 32


def test_404_html_for_browser(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert b"Not found" in resp.data
    assert resp.content_type.startswith("text/html")


def test_404_json_for_api(client):
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["status"] == 404
    assert "request_id" in body


def test_unknown_config_rejected():
    with pytest.raises(RuntimeError):
        get_config("staging")


def test_production_requires_secret_key(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", overrides={"SECRET_KEY": None, "SQLALCHEMY_DATABASE_URI": "sqlite://"})


def test_postgres_scheme_normalised(monkeypatch):
    from app import config

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db:5432/x")
    assert config._database_url("sqlite://") == "postgresql://u:p@db:5432/x"


def test_json_formatter_includes_extra_fields():
    record = logging.makeLogRecord({"msg": "hello", "levelname": "INFO", "name": "t", "status": 201})
    out = json.loads(JsonFormatter().format(record))
    assert out["message"] == "hello"
    assert out["status"] == 201
    assert "ts" in out
