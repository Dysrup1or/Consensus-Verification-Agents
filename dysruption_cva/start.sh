#!/usr/bin/env bash
set -euo pipefail

# Force PORT to 8001 for consistency with UI configuration.
# Railway injects its own PORT, but we override it to ensure predictable networking.
# The UI is configured to connect to port 8001, so the backend MUST use 8001.
PORT="8001"

# Use empty string host for dual-stack IPv4+IPv6 binding.
# Uvicorn does NOT support dual-stack with "::" - it only binds IPv6.
# Using "" (empty string) enables proper dual-stack binding (Uvicorn 0.30+).
# Fallback to "::" for older Uvicorn versions (IPv6-only, but Railway translates).
HOST=""

echo "[start.sh] Starting CVA API on port ${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"

# Run the CVA FastAPI server with dual-stack binding.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
