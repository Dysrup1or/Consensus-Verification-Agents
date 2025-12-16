#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Bind host:
# - Railway private networking uses IPv6 for service-to-service communication.
# - Binding to "::" (IPv6 any) accepts BOTH IPv4 and IPv6 connections.
# - This is required for private networking (*.railway.internal) to work.
# - Locally, use 0.0.0.0 for IPv4-only environments.
if [[ -n "${RAILWAY_ENVIRONMENT:-}" ]]; then
    HOST="${HOST:-::}"
else
    HOST="${HOST:-0.0.0.0}"
fi

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] Binding to IPv6 (::) for Railway private networking compatibility"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
