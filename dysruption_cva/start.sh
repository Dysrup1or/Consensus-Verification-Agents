#!/usr/bin/env bash
set -euo pipefail

# Railway sets PORT automatically.
PORT="${PORT:-8001}"

# Bind host:
# - On Railway private networking, service DNS may resolve to IPv6.
#   Default to IPv6 ("::") so the server is reachable via .railway.internal.
# - Locally, default to IPv4 ("0.0.0.0").
if [[ -n "${RAILWAY_ENVIRONMENT:-}" ]]; then
	HOST="${HOST:-::}"
else
	HOST="${HOST:-0.0.0.0}"
fi

# Run the CVA FastAPI server.
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
