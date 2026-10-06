"""Gunicorn settings for the container image (all overridable via env vars).

Why one worker process by default: each container/pod runs a single Python
process with several threads, so Prometheus scrapes one consistent set of
metrics per pod and we scale out with more replicas (docker compose --scale,
Kubernetes replicas/HPA) instead of more processes inside one container.
If you raise GUNICORN_WORKERS above 1, prometheus-flask-exporter needs
multiprocess mode (PROMETHEUS_MULTIPROC_DIR) to aggregate metrics.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 20
keepalive = 5
# Heartbeat files in RAM: works with a read-only root filesystem.
worker_tmp_dir = "/dev/shm"
# Recycle workers occasionally to bound memory growth.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200
# Gunicorn's control socket would live in $HOME, which the app user doesn't have.
control_socket_disable = True
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")

# The Flask app already writes one JSON access-log line per request, so the
# gunicorn access log is off and gunicorn's own messages are JSON as well.
accesslog = None
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "app.logging_config.JsonFormatter", "service": "sentinelops"}},
    "handlers": {
        "stdout": {"class": "logging.StreamHandler", "formatter": "json", "stream": "ext://sys.stdout"},
    },
    "root": {"handlers": ["stdout"], "level": "INFO"},
    "loggers": {
        "gunicorn.error": {"handlers": ["stdout"], "level": loglevel.upper(), "propagate": False},
        "gunicorn.access": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
    },
}
