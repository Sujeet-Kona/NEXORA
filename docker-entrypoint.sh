#!/bin/sh
set -e

# Wait for Postgres to accept connections before running migrations.
# Only the exception class is logged, never the URL (it carries the password).
python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine

url = os.environ["DATABASE_URL"]
engine = create_engine(url)

for attempt in range(1, 31):
    try:
        engine.connect().close()
        print("database ready", flush=True)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - retry on any connection error
        print(
            f"waiting for database ({attempt}/30): {exc.__class__.__name__}",
            flush=True,
        )
        time.sleep(2)

print("database never became ready", flush=True)
sys.exit(1)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "applying database migrations"
    alembic upgrade head
fi

exec "$@"
