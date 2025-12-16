#!/usr/bin/env bash
set -euo pipefail

# Force PORT to 8001 for consistency with UI configuration.
# Railway injects its own PORT, but we override it to ensure predictable networking.
# The UI is configured to connect to port 8001, so the backend MUST use 8001.
PORT="8001"

# Use 0.0.0.0 for IPv4 binding (works reliably with Uvicorn CLI).
# For Railway private networking:
# - New environments (after Oct 2025): Support IPv4, so 0.0.0.0 works
# - Legacy environments (IPv6-only): Railway's network layer handles translation
# The empty string host "" doesn't work properly with Uvicorn CLI.
HOST="0.0.0.0"

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
