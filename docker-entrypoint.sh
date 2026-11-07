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

# Wait for Qdrant using qdrant-client from the API image. The official
# Qdrant image is minimal and does not guarantee curl or wget is installed.
python - <<'PY'
import os
import sys
import time

from qdrant_client import QdrantClient

url = os.environ.get("QDRANT_URL", "http://localhost:6333")
api_key = os.environ.get("QDRANT_API_KEY") or None
client = QdrantClient(url=url, api_key=api_key, timeout=5)

for attempt in range(1, 61):
    try:
        client.get_collections()
        client.close()
        print("qdrant ready", flush=True)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - retry transient startup failures
        print(
            f"waiting for qdrant ({attempt}/60): {exc.__class__.__name__}",
            flush=True,
        )
        time.sleep(2)

client.close()
print("qdrant never became ready", flush=True)
sys.exit(1)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "applying database migrations"
    alembic upgrade head
fi

exec "$@"
