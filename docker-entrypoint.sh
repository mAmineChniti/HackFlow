#!/bin/sh
set -e

# Wait for PostgreSQL before running migrations. Supports both a full
# DATABASE_URL and the split POSTGRES_* variables used by docker-compose.
python - <<'PY'
import os
import sys
import time

import psycopg

database_url = os.getenv("DATABASE_URL", "").strip()

if database_url and not database_url.startswith(("postgres://", "postgresql://")):
    print("DATABASE_URL is not PostgreSQL; skipping readiness wait")
    sys.exit(0)

if database_url:
    def connect():
        return psycopg.connect(database_url, connect_timeout=2)

    target = "DATABASE_URL"
else:
    host = os.getenv("POSTGRES_HOST", "db")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    dbname = os.getenv("POSTGRES_DB", "hackflow")
    user = os.getenv("POSTGRES_USER", "hackflow")
    password = os.getenv("POSTGRES_PASSWORD", "")

    def connect():
        return psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=2,
        )

    target = f"{host}:{port}/{dbname}"

print(f"Waiting for PostgreSQL at {target}...")
for attempt in range(1, 61):
    try:
        with connect():
            print("PostgreSQL reachable")
            break
    except psycopg.OperationalError as exc:
        if attempt == 60:
            print(f"PostgreSQL not reachable after 60s: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
PY

# Optional: reset database schema (use on first deploy after migration changes)
if [ "${RESET_DB:-0}" = "1" ]; then
    echo "Resetting database schema..."
    # Drop all tables and re-run migrations from scratch to ensure a clean
    # state after migration changes. flush only deletes data, not schema.
    python - <<'PY'
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")
django.setup()

from django.db import connection

# Drop all tables to ensure a clean slate, then let migrate recreate them.
with connection.cursor() as cursor:
    tables = connection.introspection.table_names()
    for table in tables:
        cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    cursor.execute('DROP TABLE IF EXISTS "django_migrations" CASCADE')

print("All tables dropped")
PY
    python manage.py migrate --noinput
else
    # Migrations belong to the web process. Workers set
    # RUN_MIGRATIONS=0 so several containers never race
    # over the same schema during startup.
    if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
        python manage.py migrate --noinput
    fi
fi

# Demo data is on by default because this is a demo project. It runs only in
# the web container (workers set RUN_MIGRATIONS=0) and is idempotent, so it is
# safe on every restart. Set SEED_DEMO_DATA=False for an empty database.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    case "${SEED_DEMO_DATA:-1}" in
        1|true|True|TRUE|yes|Yes|YES|on|On|ON)
            python manage.py seed_demo
            ;;
    esac
fi

exec "$@"
