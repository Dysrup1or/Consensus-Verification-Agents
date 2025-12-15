#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"
HOST="${HOST:-::}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
