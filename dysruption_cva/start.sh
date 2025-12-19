#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# CVA Backend Startup Script
# =============================================================================
# This script starts the FastAPI backend with proper configuration for Railway.
#
# Environment Variables:
#   PORT                    - Port to listen on (Railway injects this)
#   HOST                    - Host to bind (default: 0.0.0.0)
#   CVA_WORKERS             - Number of Uvicorn workers (default: 1)
#   CVA_LOG_LEVEL           - Log level: debug, info, warning, error (default: info)
#   CVA_TIMEOUT_KEEP_ALIVE  - HTTP keep-alive timeout in seconds (default: 30)
#   CVA_TIMEOUT_GRACEFUL    - Graceful shutdown timeout in seconds (default: 30)
#   CVA_PRODUCTION          - Enable production mode (default: false)
#   CVA_API_TOKEN           - Required in production mode
#   DATABASE_URL            - Required in production/Railway
# =============================================================================

# Configuration with defaults
PORT="${PORT:-8001}"
# For Railway private networking (legacy environments), must bind to IPv6
# Railway docs: "uvicorn app:app --host :: --port ${PORT}"
# Legacy environments (created before Oct 16, 2025) only support IPv6
# Set HOST=0.0.0.0 to override for local development
HOST="${HOST:-::}"
WORKERS="${CVA_WORKERS:-1}"
LOG_LEVEL="${CVA_LOG_LEVEL:-info}"
TIMEOUT_KEEP_ALIVE="${CVA_TIMEOUT_KEEP_ALIVE:-30}"
TIMEOUT_GRACEFUL="${CVA_TIMEOUT_GRACEFUL:-30}"

# =============================================================================
# Startup Banner
# =============================================================================
echo "========================================"
echo "[CVA] Starting CVA Backend"
echo "[CVA] Version: 1.2.0"
echo "========================================"
echo "[CVA] PORT=${PORT}"
echo "[CVA] HOST=${HOST}"
echo "[CVA] WORKERS=${WORKERS}"
echo "[CVA] LOG_LEVEL=${LOG_LEVEL}"
echo "[CVA] TIMEOUT_KEEP_ALIVE=${TIMEOUT_KEEP_ALIVE}s"
echo "[CVA] TIMEOUT_GRACEFUL=${TIMEOUT_GRACEFUL}s"
echo "[CVA] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[CVA] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"
echo "[CVA] CVA_PRODUCTION=${CVA_PRODUCTION:-false}"
echo "[CVA] DATABASE_URL=${DATABASE_URL:+SET (hidden)}"
echo "[CVA] CVA_API_TOKEN=${CVA_API_TOKEN:+SET (hidden)}"
echo "========================================"

# =============================================================================
# Pre-flight Checks (Production Only)
# =============================================================================
if [[ "${CVA_PRODUCTION:-false}" == "true" ]]; then
    echo "[CVA] Production mode enabled, validating configuration..."
    
    MISSING=""
    
    # Check required variables
    if [[ -z "${DATABASE_URL:-}" ]]; then
        MISSING="${MISSING}DATABASE_URL "
    fi
    
    if [[ -z "${CVA_API_TOKEN:-}" ]]; then
        MISSING="${MISSING}CVA_API_TOKEN "
    fi
    
    if [[ -n "${MISSING}" ]]; then
        echo "========================================"
        echo "[CVA] FATAL: Missing required environment variables:"
        echo "[CVA]   ${MISSING}"
        echo "[CVA] "
        echo "[CVA] To fix:"
        echo "[CVA]   1. Go to Railway Dashboard"
        echo "[CVA]   2. Select the Backend service"
        echo "[CVA]   3. Go to Variables tab"
        echo "[CVA]   4. Add the missing variables"
        echo "========================================"
        exit 1
    fi
    
    echo "[CVA] Production validation passed"
fi

# =============================================================================
# Start Uvicorn
# =============================================================================
echo "[CVA] Starting Uvicorn..."

exec python -m uvicorn modules.api:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --timeout-keep-alive "${TIMEOUT_KEEP_ALIVE}" \
    --timeout-graceful-shutdown "${TIMEOUT_GRACEFUL}" \
    --access-log
