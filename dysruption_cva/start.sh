#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Bind host:
# - Railway requires binding to 0.0.0.0 for both public and private networking.
# - IPv6 (::) can cause issues with some Railway configurations.
# - Always use 0.0.0.0 to ensure the service is reachable.
HOST="${HOST:-0.0.0.0}"

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
