"""Prometheus metrics.

prometheus-flask-exporter provides per-endpoint request counts and latency
histograms at /metrics. We add process metrics (CPU, memory, fds) and these
domain metrics:

* sentinelops_predictions_total{label}       connections classified, by label
* sentinelops_scans_total{status}            scans processed, by final status
* sentinelops_scan_processing_seconds        time spent predicting per scan
* sentinelops_model_info{version}            currently loaded model version

Each app gets its own CollectorRegistry, so tests can create many apps.
Multi-worker gunicorn (Phase 2) will need PROMETHEUS_MULTIPROC_DIR.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, current_app
from prometheus_client import (CollectorRegistry, Counter, Gauge, Histogram, GCCollector,
                               PlatformCollector, ProcessCollector)
from prometheus_flask_exporter import PrometheusMetrics

_KEY = "sentinelops.metrics"


@dataclass
class AppMetrics:
    exporter: PrometheusMetrics
    registry: CollectorRegistry
    predictions: Counter
    scans: Counter
    scan_seconds: Histogram
    model_info: Gauge


def init_metrics(app: Flask) -> AppMetrics | None:
    if not app.config.get("METRICS_ENABLED", True):
        return None
    registry = CollectorRegistry(auto_describe=True)
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)
    GCCollector(registry=registry)

    exporter = PrometheusMetrics(
        app,
        registry=registry,
        group_by="url_rule",  # /scans/<int:scan_id>, not one series per id
        excluded_paths=["^/metrics$", "^/static/"],
    )
    exporter.info("sentinelops_app_info", "SentinelOps build information",
                  version=app.config["APP_VERSION"], env=app.config["ENV_NAME"])

    metrics = AppMetrics(
        exporter=exporter,
        registry=registry,
        predictions=Counter("sentinelops_predictions_total",
                            "Connections classified by the model", ["label"], registry=registry),
        scans=Counter("sentinelops_scans_total", "Scans processed", ["status"], registry=registry),
        scan_seconds=Histogram("sentinelops_scan_processing_seconds",
                               "Time spent running predictions for one scan",
                               buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
                               registry=registry),
        model_info=Gauge("sentinelops_model_info", "Loaded model (value is always 1)",
                         ["version"], registry=registry),
    )
    # Expose zero-valued series from the start so dashboards/alerts have data.
    for label in ("malicious", "benign"):
        metrics.predictions.labels(label=label)
    for status in ("completed", "failed"):
        metrics.scans.labels(status=status)
    app.extensions[_KEY] = metrics
    return metrics


def _metrics() -> AppMetrics | None:
    return current_app.extensions.get(_KEY)


def record_scan(status: str, malicious: int, benign: int, seconds: float) -> None:
    m = _metrics()
    if m is None:
        return
    m.scans.labels(status=status).inc()
    if malicious:
        m.predictions.labels(label="malicious").inc(malicious)
    if benign:
        m.predictions.labels(label="benign").inc(benign)
    m.scan_seconds.observe(seconds)


def record_model_loaded(version: str) -> None:
    m = _metrics()
    if m is not None:
        m.model_info.clear()
        m.model_info.labels(version=version).set(1)
