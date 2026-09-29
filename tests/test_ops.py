import re

from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db
from app.ml import Predictor, set_predictor
from app.ml.sklearn_predictor import ModelUnavailableError

from .conftest import upload


def metric_value(body: str, name: str, **labels) -> float:
    label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
    pattern = rf"^{re.escape(name)}{{{re.escape(label_str)}}} ([0-9.e+]+)$" if labels \
        else rf"^{re.escape(name)} ([0-9.e+]+)$"
    match = re.search(pattern, body, re.MULTILINE)
    assert match, f"{name}{labels} not found"
    return float(match.group(1))


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_readyz_ok(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["model"]["version"] == "test-stub"


def test_readyz_db_down(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db.session, "execute", broken)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["checks"]["database"]["status"] == "error"


def test_readyz_model_missing(tmp_path):
    app = create_app("testing", overrides={"MODEL_PATH": str(tmp_path / "none.joblib"),
                                           "MODEL_FALLBACK_STUB": False})
    with app.app_context():
        resp = app.test_client().get("/readyz")
    assert resp.status_code == 503
    assert "not found" in resp.get_json()["checks"]["model"]["error"]


def test_metrics_endpoint_exposes_defaults(client):
    client.get("/healthz")
    body = client.get("/metrics").data.decode()
    assert "flask_http_request_total" in body
    assert "process_resident_memory_bytes" in body  # CPU/memory for Grafana
    assert 'sentinelops_app_info{env="testing"' in body
    assert metric_value(body, "sentinelops_model_info", version="test-stub") == 1.0
    assert metric_value(body, "sentinelops_predictions_total", label="malicious") == 0.0


def test_prediction_counters_increment(auth_client):
    upload(auth_client)
    upload(auth_client)
    body = auth_client.get("/metrics").data.decode()
    assert metric_value(body, "sentinelops_predictions_total", label="malicious") == 2.0
    assert metric_value(body, "sentinelops_predictions_total", label="benign") == 2.0
    assert metric_value(body, "sentinelops_scans_total", status="completed") == 2.0
    assert metric_value(body, "sentinelops_scan_processing_seconds_count") == 2.0


def test_failed_scans_counted(auth_client, app):
    class Broken(Predictor):
        version = "broken"

        def predict(self, rows):
            raise ModelUnavailableError("model offline")

    set_predictor(app, Broken())
    upload(auth_client)
    body = auth_client.get("/metrics").data.decode()
    assert metric_value(body, "sentinelops_scans_total", status="failed") == 1.0
    assert metric_value(body, "sentinelops_model_info", version="broken") == 1.0


def test_request_metrics_grouped_by_route(auth_client):
    auth_client.get("/scans/41")
    auth_client.get("/scans/42")
    body = auth_client.get("/metrics").data.decode()
    assert 'url_rule="/scans/<int:scan_id>"' in body
    assert "/scans/42" not in body


def test_metrics_can_be_disabled():
    app = create_app("testing", overrides={"METRICS_ENABLED": False})
    assert app.test_client().get("/metrics").status_code == 404
