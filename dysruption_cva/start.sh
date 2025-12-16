#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Bind to 0.0.0.0 (IPv4) - Railway handles IPv6 routing at the network layer.
# The public healthcheck uses IPv4, and Railway's private networking
# translates IPv6 requests to reach IPv4-bound services.
HOST="0.0.0.0"

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
