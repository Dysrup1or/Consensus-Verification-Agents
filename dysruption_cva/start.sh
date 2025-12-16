#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically at runtime.
PORT="${PORT:-8001}"

# Bind to :: (all interfaces) for dual-stack IPv4+IPv6 support.
# This is REQUIRED for Railway private networking in legacy environments
# (created before October 16, 2025) which only support IPv6.
# NOTE: Uvicorn with :: does NOT support dual-stack automatically,
# but Railway's network layer handles IPv4-to-IPv6 translation.
HOST="::"

echo "[start.sh] Starting CVA API on [${HOST}]:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"

# Run the CVA FastAPI server with IPv6 binding.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
