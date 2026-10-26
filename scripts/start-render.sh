#!/bin/sh
# Render free web startup: Gunicorn + Celery in the same 512 MB instance.
#
# Render does not offer a free background-worker plan. To keep the Blueprint at
# $0 while still demonstrating the asynchronous AI flow (HTTP 202 + polling),
# this script runs one Gunicorn worker and one solo Celery worker side by side.
# On a paid plan, run Celery as its own `type: worker` service instead and use
# the Dockerfile CMD for the web service.
set -eu

# Render runs the Docker command from the image working directory, but be
# explicit so `HackFlow.wsgi` is importable regardless of the caller's cwd.
cd /app

: "${PORT:=8000}"
: "${GUNICORN_WORKERS:=1}"
: "${GUNICORN_THREADS:=4}"
: "${GUNICORN_TIMEOUT:=60}"

# ---------------------------------------------------------------------------
# Database setup: run before Gunicorn so tables exist when the first request
# arrives. RESET_DB=1 drops all tables first (use on the initial deploy after
# migration history changes, then remove the env var).
# ---------------------------------------------------------------------------
if [ "${RESET_DB:-0}" = "1" ]; then
    echo "==> RESET_DB=1: dropping all tables for a clean schema..."
    python - <<'PY'
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    tables = connection.introspection.table_names()
    for table in tables:
        cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    cursor.execute('DROP TABLE IF EXISTS "django_migrations" CASCADE')

print("All tables dropped")
PY
fi

echo "==> Running migrations..."
python manage.py migrate --noinput

# Seed demo data when requested (idempotent).
case "${SEED_DEMO_DATA:-1}" in
    1|true|True|TRUE|yes|Yes|YES|on|On|ON)
        echo "==> Seeding demo data..."
        python manage.py seed_demo
        ;;
esac

echo "==> Database ready."
# ---------------------------------------------------------------------------

CELERY_ENABLED=0
CELERY_PID=""
GUNICORN_PID=""

if [ -n "${REDIS_URL:-}" ] && [ "${AI_ASYNC_ENABLED:-True}" != "False" ]; then
    CELERY_ENABLED=1
fi

start_celery() {
    # Solo pool = one task at a time in this process, no extra child process.
    # That is the lowest-memory option for a 512 MB free instance.
    celery -A HackFlow worker \
        --loglevel=INFO \
        --pool=solo \
        --concurrency=1 \
        --without-gossip \
        --without-mingle \
        --without-heartbeat &
    CELERY_PID=$!
}

shutdown() {
    trap - TERM INT
    if [ -n "$CELERY_PID" ]; then
        kill -TERM "$CELERY_PID" 2>/dev/null || true
    fi
    if [ -n "$GUNICORN_PID" ]; then
        kill -TERM "$GUNICORN_PID" 2>/dev/null || true
    fi
    if [ -n "$CELERY_PID" ]; then
        wait "$CELERY_PID" 2>/dev/null || true
    fi
    if [ -n "$GUNICORN_PID" ]; then
        wait "$GUNICORN_PID" 2>/dev/null || true
    fi
    exit 0
}
trap shutdown TERM INT

if [ "$CELERY_ENABLED" = "1" ]; then
    start_celery
fi

gunicorn HackFlow.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --threads "${GUNICORN_THREADS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --graceful-timeout 25 \
    --access-logfile - \
    --error-logfile - &
GUNICORN_PID=$!

# Keep the worker alive while Gunicorn runs. A Redis restart or an OOM kill
# should not leave queued AI tasks without a consumer.
while kill -0 "$GUNICORN_PID" 2>/dev/null; do
    if [ "$CELERY_ENABLED" = "1" ] && ! kill -0 "$CELERY_PID" 2>/dev/null; then
        wait "$CELERY_PID" 2>/dev/null || true
        sleep 2
        start_celery
    fi
    sleep 5
done

set +e
wait "$GUNICORN_PID"
STATUS=$?
set -e

if [ -n "$CELERY_PID" ]; then
    kill -TERM "$CELERY_PID" 2>/dev/null || true
    wait "$CELERY_PID" 2>/dev/null || true
fi

exit "$STATUS"
