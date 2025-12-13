#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host 0.0.0.0 --port "${PORT}"
