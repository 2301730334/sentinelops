#!/bin/sh
# Container entrypoint: apply database migrations, then start the given command
# (gunicorn by default). Set RUN_MIGRATIONS=false when migrations run elsewhere
# (e.g. a Kubernetes Job or init container in Phase 3).
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    attempts="${MIGRATION_RETRIES:-10}"
    i=1
    until flask db upgrade; do
        if [ "$i" -ge "$attempts" ]; then
            echo '{"level": "ERROR", "message": "database migrations failed, giving up"}' >&2
            exit 1
        fi
        echo "{\"level\": \"WARNING\", \"message\": \"migration attempt $i/$attempts failed, retrying in 3s\"}" >&2
        i=$((i + 1))
        sleep 3
    done
fi

exec "$@"
