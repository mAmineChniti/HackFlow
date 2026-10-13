#!/bin/sh
set -e

# Wait for MySQL (skip when DATABASE_URL points to external managed DB)
if [ -z "$DATABASE_URL" ]; then
  echo "Waiting for MySQL at ${MYSQL_HOST:-db}:${MYSQL_PORT:-3306}..."
  python - <<'PY'
import os, socket, time
host = os.getenv("MYSQL_HOST", "db")
port = int(os.getenv("MYSQL_PORT", "3306"))
for i in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("MySQL reachable")
            break
    except OSError:
        time.sleep(1)
else:
    print("MySQL not reachable after 60s, continuing anyway")
PY
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput || true

exec "$@"
