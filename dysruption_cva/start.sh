#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Bind to IPv4 by default; Railway expects 0.0.0.0:$PORT.
HOST="${HOST:-0.0.0.0}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
