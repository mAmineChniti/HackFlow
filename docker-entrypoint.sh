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

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
