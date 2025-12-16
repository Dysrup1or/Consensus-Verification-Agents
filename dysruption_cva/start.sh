#!/usr/bin/env bash
set -euo pipefail

# Use Railway's injected PORT (required for public networking).
# Railway's proxy expects the app to listen on the injected PORT.
# If we override it, Railway can't route traffic and kills the container.
#
# To set a consistent port:
# 1. Add PORT=8001 as a service variable in Railway Dashboard for the backend
# 2. Set CVA_BACKEND_URL=http://<backend>.railway.internal:8001 in the UI
#
# If PORT is not set, default to 8001 for local development.
PORT="${PORT:-8001}"

# Use 0.0.0.0 for IPv4 binding (works reliably with Uvicorn CLI).
HOST="0.0.0.0"

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
