# CVA Critical Fixes Implementation Plan
## Step-by-Step Remediation Guide

**Created:** December 16, 2025  
**Priority:** Address before next Railway deployment  
**Estimated Time:** 2-3 hours total

---

## Table of Contents

1. [CRITICAL-1: Merge Duplicate Startup Handlers](#critical-1-merge-duplicate-startup-handlers)
2. [CRITICAL-2: Fail-Fast on Missing DATABASE_URL](#critical-2-fail-fast-on-missing-database_url)
3. [CRITICAL-3: Add Graceful Shutdown Configuration](#critical-3-add-graceful-shutdown-configuration)
4. [CRITICAL-4: Fix Health Endpoint HTTP Status](#critical-4-fix-health-endpoint-http-status)
5. [Verification Checklist](#verification-checklist)

---

## CRITICAL-1: Merge Duplicate Startup Handlers

### Finding Description

The file `dysruption_cva/modules/api.py` contains **two separate startup event handlers**:

| Handler | Location | Purpose |
|---------|----------|---------|
| `_startup_apply_migrations()` | Line 441 | Database migrations, SQLite schema, monitor worker |
| `startup_event()` | Line 2518 | Logging, directory creation |

**Why This Is a Problem:**
- FastAPI's `@app.on_event("startup")` is deprecated (use `lifespan` instead)
- Two handlers can execute in unpredictable order
- If the first handler fails, the second may still run, leaving the app in a broken state
- Error handling is inconsistent between handlers

### Technical Requirements

- Python 3.11+
- FastAPI 0.109.0+ (already installed)
- Must maintain all existing functionality:
  - Apply PostgreSQL migrations when configured
  - Ensure SQLite schema in dev mode
  - Start monitor worker when `CVA_MONITOR_WORKER=true`
  - Create `temp_uploads/` and `run_artifacts/` directories
  - Log startup configuration

### Implementation Tasks

#### Task 1.1: Add Lifespan Import

**File:** `dysruption_cva/modules/api.py`  
**Location:** Top of file, in the imports section

**Find this code (around line 49):**
```python
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
```

**Add this import:**
```python
from contextlib import asynccontextmanager
```

**Note:** This import may already exist elsewhere in the file. Search first with `Ctrl+F`.

#### Task 1.2: Create Unified Lifespan Function

**File:** `dysruption_cva/modules/api.py`  
**Location:** Insert BEFORE the `app = FastAPI(...)` line (around line 432)

**Add this new function:**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Unified application lifecycle manager.
    
    Startup sequence (in order):
    1. Create runtime directories (temp_uploads, run_artifacts)
    2. Apply PostgreSQL migrations (if CVA_APPLY_MIGRATIONS=true)
    3. Ensure SQLite schema (dev/test only)
    4. Start monitor worker (if CVA_MONITOR_WORKER=true)
    
    Shutdown sequence:
    1. Close all WebSocket connections
    2. Log shutdown
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    logger.info("CVA API v1.2 starting up...")
    logger.info("Endpoints: /run, /status/{run_id}, /verdict/{run_id}, /ws/{run_id}")

    # Step 1: Ensure runtime directories exist
    try:
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        RUN_ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
        logger.info(f"Runtime directories ready: {UPLOAD_ROOT}, {RUN_ARTIFACTS_ROOT}")
    except Exception as e:
        logger.error(f"Failed to create runtime directories: {e}")
        raise  # Fail startup if we can't write files

    # Step 2: Apply PostgreSQL migrations (production)
    try:
        await apply_migrations_if_configured()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise  # Fail startup if migrations fail

    # Step 3: Ensure SQLite schema (dev/test)
    try:
        await ensure_sqlite_schema()
    except Exception as e:
        logger.error(f"SQLite schema creation failed: {e}")
        raise  # Fail startup if schema fails

    # Step 4: Start monitor worker (optional)
    monitor_enabled = os.getenv("CVA_MONITOR_WORKER", "false").lower() == "true"
    if monitor_enabled:
        try:
            # Validate: Postgres requires migrations for monitor tables
            engine = get_engine()
            dialect_name = getattr(engine.dialect, "name", "")
            apply_migrations_enabled = os.getenv("CVA_APPLY_MIGRATIONS", "false").lower() == "true"
            
            if dialect_name != "sqlite" and not apply_migrations_enabled:
                logger.error(
                    "Monitor worker requires CVA_APPLY_MIGRATIONS=true on Postgres. "
                    "Skipping worker startup."
                )
            else:
                asyncio.create_task(run_monitor_worker_loop())
                logger.info("Monitor worker started")
        except Exception as e:
            logger.warning(f"Failed to start monitor worker: {e}")
            # Don't fail startup for optional worker

    # Log final configuration
    logger.info(
        "Startup complete: production=%s, port=%s, upload_root=%s",
        PRODUCTION_MODE,
        os.getenv("PORT", "not_set"),
        str(UPLOAD_ROOT),
    )

    # =========================================================================
    # YIELD (app runs here)
    # =========================================================================
    yield

    # =========================================================================
    # SHUTDOWN
    # =========================================================================
    logger.info("CVA API shutting down...")
    
    # Close all WebSocket connections gracefully
    for run_id, connections in list(ws_manager.active_connections.items()):
        for ws in connections:
            try:
                await ws.close(code=1001, reason="Server shutdown")
            except Exception:
                pass  # Connection may already be closed
    
    logger.info("Shutdown complete")
```

#### Task 1.3: Update FastAPI App Initialization

**File:** `dysruption_cva/modules/api.py`  
**Location:** Around line 432-438

**Find this code:**
```python
app = FastAPI(
    title="Dysruption CVA API",
    description="Consensus Verifier Agent - Multi-Model AI Tribunal for Code Verification",
    version="1.2.0",
    docs_url="/docs" if not PRODUCTION_MODE else None,
    redoc_url="/redoc" if not PRODUCTION_MODE else None,
)
```

**Replace with:**
```python
app = FastAPI(
    title="Dysruption CVA API",
    description="Consensus Verifier Agent - Multi-Model AI Tribunal for Code Verification",
    version="1.2.0",
    docs_url="/docs" if not PRODUCTION_MODE else None,
    redoc_url="/redoc" if not PRODUCTION_MODE else None,
    lifespan=lifespan,  # <-- ADD THIS LINE
)
```

#### Task 1.4: Remove Old Startup Handler #1

**File:** `dysruption_cva/modules/api.py`  
**Location:** Lines 441-478 (approximately)

**Find and DELETE this entire block:**
```python
@app.on_event("startup")
async def _startup_apply_migrations() -> None:
    await apply_migrations_if_configured()
    await ensure_sqlite_schema()

    # Optional continuous monitoring worker (single-process).
    # Enable with CVA_MONITOR_WORKER=true.
    try:
        monitor_enabled = os.getenv("CVA_MONITOR_WORKER", "false").lower() == "true"
        apply_migrations_enabled = os.getenv("CVA_APPLY_MIGRATIONS", "false").lower() == "true"

        if not monitor_enabled:
            return

        # Guard: on Postgres, the monitor worker requires SQL migrations (monitor_jobs, etc.).
        # If migrations aren't enabled, skip starting the worker rather than crash-looping.
        try:
            engine = get_engine()
            dialect_name = getattr(engine.dialect, "name", "")
        except Exception:
            dialect_name = ""

        if monitor_enabled and dialect_name and dialect_name != "sqlite" and not apply_migrations_enabled:
            logger.error(
                "Monitor worker enabled but migrations are not. Set CVA_APPLY_MIGRATIONS=true to create required tables. "
                f"(dialect={dialect_name})"
            )
            return

        asyncio.create_task(run_monitor_worker_loop())
```

#### Task 1.5: Remove Old Startup Handler #2

**File:** `dysruption_cva/modules/api.py`  
**Location:** Lines 2518-2538 (approximately)

**Find and DELETE this entire block:**
```python
@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    logger.info("CVA API v1.2 starting up...")
    logger.info("Endpoints: /run, /status/{run_id}, /verdict/{run_id}, /ws/{run_id}")

    # Ensure runtime directories exist (important on Railway + ephemeral filesystems).
    try:
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        RUN_ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create runtime dirs: {e}")

    logger.info(
        "Startup config: production=%s port=%s upload_root=%s run_artifacts_root=%s",
        PRODUCTION_MODE,
        os.getenv("PORT", ""),
        str(UPLOAD_ROOT),
        str(RUN_ARTIFACTS_ROOT),
    )
```

#### Task 1.6: Remove Old Shutdown Handler

**File:** `dysruption_cva/modules/api.py`  
**Location:** Lines 2540-2552 (approximately)

**Find and DELETE this entire block:**
```python
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    logger.info("CVA API shutting down...")
    # Close all WebSocket connections
    for run_id, connections in ws_manager.active_connections.items():
        for ws in connections:
            try:
                await ws.close()
            except Exception:
                pass
```

### Expected Outcome

After completing all tasks:
- Single `lifespan` context manager handles all startup/shutdown
- Startup fails fast if any critical step fails
- All functionality is preserved
- Code is cleaner and follows FastAPI best practices

### Verification

Run locally:
```powershell
cd dysruption_cva
..\.venv\Scripts\python.exe -m uvicorn modules.api:app --host 127.0.0.1 --port 8001
```

**Expected console output:**
```
INFO:     CVA API v1.2 starting up...
INFO:     Runtime directories ready: ...
INFO:     Startup complete: production=False, port=not_set, ...
INFO:     Uvicorn running on http://127.0.0.1:8001
```

---

## CRITICAL-2: Fail-Fast on Missing DATABASE_URL

### Finding Description

The file `dysruption_cva/modules/persistence/db.py` silently falls back to SQLite when `DATABASE_URL` is not set:

```python
def _normalized_database_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "sqlite+aiosqlite:///./cva_dev.db"  # Silent fallback!
```

**Why This Is a Problem:**
- On Railway, if `DATABASE_URL` is not linked, app uses local SQLite
- SQLite file is stored in container's ephemeral filesystem
- All data is lost when container restarts
- No error or warning indicates misconfiguration
- Developer thinks data is persisted, but it's not

### Technical Requirements

- Must detect Railway environment (`RAILWAY_ENVIRONMENT` env var)
- Must detect production mode (`CVA_PRODUCTION` env var)
- Must fail with clear error message
- Must still allow SQLite for local development

### Implementation Tasks

#### Task 2.1: Update Database URL Function

**File:** `dysruption_cva/modules/persistence/db.py`  
**Location:** Lines 10-23

**Find this code:**
```python
def _normalized_database_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        # Safe default for local/dev.
        return "sqlite+aiosqlite:///./cva_dev.db"

    # Railway Postgres typically provides DATABASE_URL (postgresql://...).
    # For SQLAlchemy async driver we need postgresql+asyncpg://...
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw
```

**Replace with:**
```python
def _normalized_database_url(raw: str) -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy async drivers.
    
    Behavior:
    - Production/Railway: REQUIRES DATABASE_URL, fails if missing
    - Local development: Falls back to SQLite with warning
    
    Raises:
        RuntimeError: If DATABASE_URL is missing in production/Railway
    """
    raw = (raw or "").strip()
    
    if not raw:
        # Check if we're in production or Railway
        is_production = os.getenv("CVA_PRODUCTION", "false").lower() == "true"
        is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
        
        if is_production or is_railway:
            raise RuntimeError(
                "DATABASE_URL environment variable is required in production/Railway. "
                "Please link a PostgreSQL database to this service in Railway Dashboard, "
                "or set DATABASE_URL manually. "
                f"(CVA_PRODUCTION={is_production}, RAILWAY_ENVIRONMENT={os.getenv('RAILWAY_ENVIRONMENT', 'not_set')})"
            )
        
        # Local development: allow SQLite with warning
        logger.warning(
            "DATABASE_URL not set. Using SQLite for local development. "
            "This is NOT suitable for production - data will be lost on restart."
        )
        return "sqlite+aiosqlite:///./cva_dev.db"

    # Railway Postgres typically provides DATABASE_URL (postgresql://...).
    # For SQLAlchemy async driver we need postgresql+asyncpg://...
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    
    return raw
```

#### Task 2.2: Add Logger Import

**File:** `dysruption_cva/modules/persistence/db.py`  
**Location:** Top of file, after existing imports

**Find these imports (around lines 1-8):**
```python
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
```

**Add after them:**
```python
from loguru import logger
```

### Expected Outcome

| Environment | DATABASE_URL | Behavior |
|-------------|--------------|----------|
| Local dev | Not set | SQLite + warning log |
| Local dev | Set | Uses provided URL |
| Railway | Not set | **CRASH with clear error** |
| Railway | Set | Uses provided URL |
| Production | Not set | **CRASH with clear error** |
| Production | Set | Uses provided URL |

### Verification

**Test 1: Local without DATABASE_URL (should work)**
```powershell
$env:CVA_PRODUCTION = "false"
$env:RAILWAY_ENVIRONMENT = $null
cd dysruption_cva
..\.venv\Scripts\python.exe -c "from modules.persistence.db import get_engine; print(get_engine().url)"
```
Expected: `sqlite+aiosqlite:///./cva_dev.db` with warning

**Test 2: Simulated Railway without DATABASE_URL (should crash)**
```powershell
$env:RAILWAY_ENVIRONMENT = "production"
$env:DATABASE_URL = $null
cd dysruption_cva
..\.venv\Scripts\python.exe -c "from modules.persistence.db import get_engine; print(get_engine().url)"
```
Expected: `RuntimeError: DATABASE_URL environment variable is required...`

---

## CRITICAL-3: Add Graceful Shutdown Configuration

### Finding Description

The file `dysruption_cva/start.sh` starts Uvicorn without timeout configuration:

```bash
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
```

**Why This Is a Problem:**
- Default `timeout-keep-alive` is 5 seconds (may be too short for slow clients)
- No graceful shutdown timeout (Railway sends SIGTERM, then SIGKILL after 10s)
- Long-running requests may be killed mid-execution
- WebSocket connections dropped without warning

### Technical Requirements

- Add `--timeout-keep-alive` for HTTP keep-alive connections
- Add `--timeout-graceful-shutdown` for Railway's shutdown sequence
- Make timeouts configurable via environment variables
- Add pre-flight validation for production mode

### Implementation Tasks

#### Task 3.1: Update start.sh

**File:** `dysruption_cva/start.sh`

**Find the entire current content:**
```bash
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
```

**Replace with:**
```bash
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
HOST="${HOST:-0.0.0.0}"
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
```

### Expected Outcome

- Uvicorn starts with proper timeout configuration
- Production mode validates required variables before starting
- Clear error messages guide developer to fix issues
- Graceful shutdown allows Railway to drain connections

### Verification

**Test locally:**
```powershell
cd dysruption_cva
bash start.sh
```

**Expected output:**
```
========================================
[CVA] Starting CVA Backend
[CVA] Version: 1.2.0
========================================
[CVA] PORT=8001
[CVA] HOST=0.0.0.0
[CVA] WORKERS=1
...
[CVA] Starting Uvicorn...
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     CVA API v1.2 starting up...
```

---

## CRITICAL-4: Fix Health Endpoint HTTP Status

### Finding Description

The root endpoint `/` returns HTTP 200 even when the system is degraded:

```python
@app.get("/")
async def root() -> Dict[str, Any]:
    health_status = {
        "status": "healthy",
        ...
    }
    
    # If check fails:
    health_status["status"] = "degraded"  # But returns 200!
    
    return health_status  # Always 200 OK
```

**Why This Is a Problem:**
- Railway health checks look at HTTP status code
- 200 = healthy, route traffic to this instance
- Degraded instance still receives traffic
- Users experience errors

### Technical Requirements

- Create lightweight `/health` endpoint for Railway (fast, no deps)
- Keep `/` as deep health check for diagnostics
- Return 503 Service Unavailable when degraded
- Don't break existing API clients

### Implementation Tasks

#### Task 4.1: Add Lightweight Health Endpoint

**File:** `dysruption_cva/modules/api.py`  
**Location:** After the CORS middleware setup, before REST endpoints (around line 500)

**Add this new endpoint:**
```python
# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/health", include_in_schema=False)
async def health_liveness():
    """
    Lightweight liveness probe for Railway/Kubernetes.
    
    This endpoint:
    - Returns immediately (no database or external calls)
    - Returns 200 if the process is alive
    - Used by Railway to determine if container should be restarted
    
    For detailed health info, use GET /
    """
    return {"status": "alive", "version": "1.2.0"}


@app.get("/ready", include_in_schema=False)
async def health_readiness():
    """
    Readiness probe - can this instance serve traffic?
    
    Checks:
    - Database connection
    - Required directories exist
    - At least one LLM API key present
    
    Returns 503 if not ready.
    """
    checks = {
        "database": "unknown",
        "filesystem": "unknown", 
        "api_keys": "unknown",
    }
    ready = True
    
    # Check 1: Database connection
    try:
        from .persistence.db import get_engine
        engine = get_engine()
        # Just verify engine was created, don't actually query
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        ready = False
    
    # Check 2: Filesystem
    try:
        if UPLOAD_ROOT.exists() and RUN_ARTIFACTS_ROOT.exists():
            checks["filesystem"] = "ok"
        else:
            checks["filesystem"] = "directories missing"
            ready = False
    except Exception as e:
        checks["filesystem"] = f"error: {str(e)}"
        ready = False
    
    # Check 3: API Keys (at least one)
    keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY"]
    has_key = any(os.environ.get(k) for k in keys)
    if has_key:
        checks["api_keys"] = "ok"
    else:
        checks["api_keys"] = "no LLM keys configured"
        # Don't fail readiness for this - might use local models
    
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks}
        )
    
    return {"status": "ready", "checks": checks}
```

#### Task 4.2: Update Root Endpoint to Return Proper Status Codes

**File:** `dysruption_cva/modules/api.py`  
**Location:** Lines 1246-1290 (the `root()` function)

**Find this code:**
```python
@app.get("/")
async def root() -> Dict[str, Any]:
    """
    Deep Health Check & API Info.
    Verifies file system permissions and API key presence.
    """
    health_status = {
        "name": "Dysruption CVA API",
        "version": "1.2.0",
        "status": "healthy",
        "checks": {
            "filesystem": "unknown",
            "api_keys": "unknown",
        },
        "endpoints": {
            "run": "POST /run - Start verification run",
            "upload": "POST /upload - Upload files for analysis",
            "status": "GET /status/{run_id} - Get run status",
            "verdict": "GET /verdict/{run_id} - Get final verdict",
            "ws": "WS /ws/{run_id} - Real-time status streaming",
        },
    }

    # 1. File System Check
    try:
        test_file = UPLOAD_ROOT / ".healthcheck"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("ok")
        test_file.unlink()
        health_status["checks"]["filesystem"] = "ok"
    except Exception as e:
        health_status["checks"]["filesystem"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # 2. API Key Check
    # Check for common LLM keys. At least one should be present.
    keys_present = []
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_API_KEY", "LITELLM_API_KEY"]:
        if os.environ.get(key):
            keys_present.append(key)
    
    if keys_present:
        health_status["checks"]["api_keys"] = "ok"
    else:
        health_status["checks"]["api_keys"] = "missing (OPENAI_API_KEY, etc.)"
        # We don't mark as degraded yet as user might rely on local models, 
        # but it's good info.

    return health_status
```

**Replace with:**
```python
@app.get("/")
async def root() -> Dict[str, Any]:
    """
    Deep Health Check & API Info.
    
    Returns:
    - 200 OK: System is healthy
    - 503 Service Unavailable: System is degraded (with details)
    
    For lightweight health checks, use GET /health
    """
    health_status = {
        "name": "Dysruption CVA API",
        "version": "1.2.0",
        "status": "healthy",
        "checks": {
            "filesystem": "unknown",
            "api_keys": "unknown",
        },
        "endpoints": {
            "health": "GET /health - Lightweight liveness check",
            "ready": "GET /ready - Readiness check with dependencies",
            "run": "POST /run - Start verification run",
            "upload": "POST /upload - Upload files for analysis",
            "status": "GET /status/{run_id} - Get run status",
            "verdict": "GET /verdict/{run_id} - Get final verdict",
            "ws": "WS /ws/{run_id} - Real-time status streaming",
        },
    }
    
    is_degraded = False

    # 1. File System Check (critical)
    try:
        test_file = UPLOAD_ROOT / ".healthcheck"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("ok")
        test_file.unlink()
        health_status["checks"]["filesystem"] = "ok"
    except Exception as e:
        health_status["checks"]["filesystem"] = f"error: {str(e)}"
        is_degraded = True

    # 2. API Key Check (informational)
    keys_present = []
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY"]:
        if os.environ.get(key):
            keys_present.append(key)
    
    if keys_present:
        health_status["checks"]["api_keys"] = f"ok ({len(keys_present)} configured)"
    else:
        health_status["checks"]["api_keys"] = "warning: no LLM keys configured"
        # Don't mark as degraded - might use local models

    # Return appropriate status code
    if is_degraded:
        health_status["status"] = "degraded"
        raise HTTPException(
            status_code=503,
            detail=health_status
        )

    return health_status
```

### Expected Outcome

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /health` | Railway liveness | Always 200 (if process alive) |
| `GET /ready` | Railway readiness | 200 if ready, 503 if not |
| `GET /` | Deep diagnostics | 200 if healthy, 503 if degraded |

### Verification

**Test 1: Health endpoint**
```powershell
curl http://localhost:8001/health
```
Expected: `{"status": "alive", "version": "1.2.0"}`

**Test 2: Ready endpoint**
```powershell
curl http://localhost:8001/ready
```
Expected: `{"status": "ready", "checks": {...}}`

**Test 3: Root endpoint**
```powershell
curl http://localhost:8001/
```
Expected: Full health info with 200 OK

---

## Verification Checklist

After implementing all fixes, verify each one:

### Pre-Deployment Checklist

- [ ] **CRITICAL-1**: Run backend locally, check for single startup sequence in logs
- [ ] **CRITICAL-2**: Test with/without DATABASE_URL in simulated Railway env
- [ ] **CRITICAL-3**: Verify `start.sh` shows timeout configuration
- [ ] **CRITICAL-4**: Test all three health endpoints return correct status codes

### Integration Test

```powershell
# Start backend
cd C:\Users\alexe\Invariant\dysruption_cva
..\.venv\Scripts\python.exe -m uvicorn modules.api:app --host 127.0.0.1 --port 8001

# In another terminal, test endpoints
curl http://localhost:8001/health   # Should return 200
curl http://localhost:8001/ready    # Should return 200
curl http://localhost:8001/         # Should return 200 with full health
```

### Railway Deployment Test

After pushing changes:
1. Check Railway deploy logs for startup sequence
2. Verify backend shows "healthy" in Railway dashboard
3. Test private networking from UI service

---

## Appendix: Quick Reference

### Files Modified

| File | Changes |
|------|---------|
| `modules/api.py` | Lifespan manager, health endpoints |
| `modules/persistence/db.py` | Fail-fast on missing DATABASE_URL |
| `start.sh` | Timeout config, pre-flight checks |

### New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CVA_WORKERS` | 1 | Uvicorn worker processes |
| `CVA_LOG_LEVEL` | info | Logging verbosity |
| `CVA_TIMEOUT_KEEP_ALIVE` | 30 | HTTP keep-alive timeout (seconds) |
| `CVA_TIMEOUT_GRACEFUL` | 30 | Shutdown grace period (seconds) |

### Rollback Procedure

If issues occur after deployment:
1. Revert to previous commit: `git revert HEAD`
2. Push to Railway: `git push`
3. Railway will auto-deploy previous version
