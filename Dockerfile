# syntax=docker/dockerfile:1
# SentinelOps container image
#   docker build -t sentinelops:local .
#   docker build --build-arg APP_VERSION=$(git rev-parse --short HEAD) -t sentinelops:<tag> .

ARG PYTHON_VERSION=3.11

# ---- builder: install dependencies into an isolated virtualenv ---------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ---- runtime: slim image, no build tools, non-root user ----------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_VERSION=dev
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="sentinelops" \
      org.opencontainers.image.description="IoT threat-detection service (Flask + scikit-learn)" \
      org.opencontainers.image.source="https://github.com/2301730334/sentinelops" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_VERSION=${APP_VERSION} \
    FLASK_APP=wsgi.py \
    PORT=8000 \
    RUN_MIGRATIONS=true

# Unprivileged user with a fixed UID (matches runAsUser in Kubernetes later).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Application files stay owned by root (read-only for the app user).
COPY wsgi.py ./
COPY app ./app
COPY migrations ./migrations
COPY models ./models
COPY docker/entrypoint.sh docker/gunicorn.conf.py ./docker/

# Strip any Windows line endings, make the entrypoint executable, and give the
# app user a writable instance/ dir (only used by the SQLite fallback).
RUN sed -i 's/\r$//' docker/entrypoint.sh \
 && chmod 0755 docker/entrypoint.sh \
 && mkdir -p instance \
 && chown app:app instance

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/docker/gunicorn.conf.py", "wsgi:app"]
