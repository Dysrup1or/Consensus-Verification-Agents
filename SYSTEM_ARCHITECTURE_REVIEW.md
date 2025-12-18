# CVA System Architecture Review
## Comprehensive Infrastructure, Workflow & Program Analysis

**Date:** December 16, 2025  
**Version:** 1.0  
**Scope:** Backend (FastAPI) + Frontend (Next.js) + Railway Deployment

---

## Executive Summary

The Consensus Verification Agent (CVA) is a sophisticated multi-model AI tribunal system for code verification. After thorough analysis, I've identified **12 critical issues**, **8 moderate concerns**, and **15 optimization opportunities** across infrastructure, startup orchestration, and program requirements.

### Priority Matrix

| Priority | Category | Issue Count | Impact |
|----------|----------|-------------|--------|
| 🔴 Critical | Startup/Reliability | 4 | System crashes, deployment failures |
| 🔴 Critical | Configuration | 3 | Silent failures, security gaps |
| 🟡 Moderate | Performance | 5 | Slow startup, resource waste |
| 🟡 Moderate | Observability | 3 | Difficult debugging |
| 🟢 Optimization | Code Quality | 8 | Technical debt |
| 🟢 Optimization | Developer Experience | 7 | Slower iteration |

---

## Part 1: Infrastructure Design Analysis

### 1.1 Current Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAILWAY PLATFORM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐     Private Net      ┌────────────────┐ │
│  │  CVA Backend       │◄───────────────────►│  Invariant UI  │ │
│  │  (FastAPI/Python)  │    :8080             │  (Next.js)     │ │
│  │                    │                      │                │ │
│  │  Port: $PORT       │                      │  Port: $PORT   │ │
│  │  Host: 0.0.0.0     │                      │  Host: 0.0.0.0 │ │
│  └─────────┬──────────┘                      └───────┬────────┘ │
│            │                                         │          │
│            ▼                                         │          │
│  ┌─────────────────────┐                            │          │
│  │  Railway Postgres   │                            │          │
│  │  (DATABASE_URL)     │                            │          │
│  └─────────────────────┘                            │          │
│                                                      ▼          │
│                                              ┌──────────────┐   │
│                                              │  Public DNS  │   │
│                                              │  Custom Doma │   │
│                                              └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Critical Infrastructure Issues

#### 🔴 CRITICAL-1: Duplicate Startup Event Handlers

**File:** `modules/api.py`  
**Lines:** 441-470 and 2518-2538

```python
# FIRST startup handler (line 441)
@app.on_event("startup")
async def _startup_apply_migrations() -> None:
    await apply_migrations_if_configured()
    await ensure_sqlite_schema()
    # ... monitor worker initialization

# SECOND startup handler (line 2518)  
@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    logger.info("CVA API v1.2 starting up...")
    # ... directory creation
```

**Problem:** Two separate `@app.on_event("startup")` decorators create race conditions. FastAPI executes them sequentially but:
1. No guaranteed order between handlers
2. If `_startup_apply_migrations` fails, `startup_event` may still run
3. Error handling is inconsistent between handlers

**Recommendation:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Unified startup/shutdown lifecycle."""
    # STARTUP
    logger.info("CVA API v1.2 starting up...")
    
    # 1. Ensure directories
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    
    # 2. Database initialization
    await apply_migrations_if_configured()
    await ensure_sqlite_schema()
    
    # 3. Optional monitor worker
    if os.getenv("CVA_MONITOR_WORKER", "false").lower() == "true":
        asyncio.create_task(run_monitor_worker_loop())
    
    yield
    
    # SHUTDOWN
    logger.info("CVA API shutting down...")
    # Close WebSocket connections, etc.

app = FastAPI(lifespan=lifespan, ...)
```

#### 🔴 CRITICAL-2: SQLite Fallback Creates Hidden Failures

**File:** `modules/persistence/db.py` (Lines 10-22)

```python
def _normalized_database_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        # Safe default for local/dev.
        return "sqlite+aiosqlite:///./cva_dev.db"
```

**Problem:** On Railway, if `DATABASE_URL` is unset or empty:
1. App silently falls back to SQLite
2. SQLite uses a local file (`./cva_dev.db`) which is ephemeral on Railway
3. All data is lost on container restart
4. No warning logged to indicate misconfiguration

**Recommendation:**
```python
def _normalized_database_url(raw: str) -> str:
    raw = (raw or "").strip()
    
    production = os.getenv("CVA_PRODUCTION", "false").lower() == "true"
    railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
    
    if not raw:
        if production or railway:
            raise RuntimeError(
                "DATABASE_URL must be set in production/Railway. "
                "Link a Postgres database or set DATABASE_URL explicitly."
            )
        logger.warning("DATABASE_URL not set, using SQLite (dev mode only)")
        return "sqlite+aiosqlite:///./cva_dev.db"
    
    # ... rest of normalization
```

#### 🔴 CRITICAL-3: No Graceful Shutdown Signal Handling

**File:** `start.sh`

```bash
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
```

**Problem:** `exec` replaces the shell with uvicorn, which is good for signal propagation. However:
1. No `--timeout-keep-alive` configured (defaults to 5s, may not be enough)
2. No `--graceful-timeout` for Railway's shutdown grace period
3. WebSocket connections may be abruptly killed

**Recommendation:**
```bash
exec python -m uvicorn modules.api:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --timeout-keep-alive 30 \
    --timeout-graceful-shutdown 30
```

#### 🔴 CRITICAL-4: Health Endpoint Returns 200 on Degraded State

**File:** `modules/api.py` (Lines 1246-1290)

```python
@app.get("/")
async def root() -> Dict[str, Any]:
    health_status = {
        "status": "healthy",
        # ...
    }
    
    # If filesystem check fails:
    health_status["status"] = "degraded"  # But still returns 200!
    
    return health_status  # Always 200 OK
```

**Problem:** Railway health checks expect:
- `200` = healthy (keep routing traffic)
- `5xx` = unhealthy (stop routing, restart)

Returning `200` with `"status": "degraded"` means Railway continues routing to a broken instance.

**Recommendation:**
```python
@app.get("/health")
async def health_check() -> Response:
    """Kubernetes/Railway-compatible health check."""
    # Quick, lightweight check
    return Response(content="OK", media_type="text/plain")

@app.get("/")
async def root() -> Dict[str, Any]:
    """Deep health check for diagnostics (not for load balancer)."""
    health_status = await _deep_health_check()
    
    if health_status["status"] != "healthy":
        raise HTTPException(
            status_code=503,
            detail=health_status
        )
    
    return health_status
```

---

### 1.3 Moderate Infrastructure Concerns

#### 🟡 MODERATE-1: In-Memory Rate Limiting Doesn't Scale

**File:** `modules/api.py` (Lines 188-202)

```python
# Rate limiting state (simple in-memory, use Redis for production)
_rate_limit_tracker: Dict[str, List[float]] = defaultdict(list)
```

**Problem:** Each Railway replica has its own rate limit state. With 2 replicas, a client can make 2x the allowed requests.

**Recommendation:** Already noted in code comment. Implement Redis-based rate limiting:
```python
# Use redis-py or aioredis
# Or Railway's built-in Redis addon
CVA_REDIS_URL = os.getenv("CVA_REDIS_URL")
if CVA_REDIS_URL:
    # Use distributed rate limiter
```

#### 🟡 MODERATE-2: No Connection Pooling Configuration

**File:** `modules/persistence/db.py` (Lines 33-40)

```python
_ENGINE = create_async_engine(
    _database_url_from_env(),
    echo=False,
    pool_pre_ping=True,  # Good!
)
```

**Problem:** Default pool settings may cause connection exhaustion:
- Default `pool_size=5`
- Default `max_overflow=10`
- 15 concurrent connections max per replica

**Recommendation:**
```python
_ENGINE = create_async_engine(
    _database_url_from_env(),
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,  # 30 min - Railway Postgres may close idle
)
```

#### 🟡 MODERATE-3: Missing Readiness vs Liveness Separation

Railway and Kubernetes distinguish:
- **Liveness:** "Is the process alive?" → `/health` (fast, no deps)
- **Readiness:** "Can it serve traffic?" → `/ready` (checks DB, etc.)

**Recommendation:** Add separate endpoints:
```python
@app.get("/health")  # Liveness
async def liveness():
    return {"status": "alive"}

@app.get("/ready")  # Readiness  
async def readiness():
    # Check DB connection
    # Check required API keys
    # Check filesystem
```

---

## Part 2: Startup Script Analysis

### 2.1 Backend Startup (`start.sh`)

**Current Implementation:**
```bash
#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8001}"
HOST="0.0.0.0"

echo "[start.sh] Starting CVA API on ${HOST}:${PORT}"
echo "[start.sh] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[start.sh] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"

exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
```

#### Issues Identified:

| Issue | Severity | Description |
|-------|----------|-------------|
| No pre-flight checks | 🟡 | Script doesn't verify Python/dependencies |
| No log level config | 🟢 | Hardcoded log level |
| No worker configuration | 🟡 | Single worker limits throughput |
| Missing SIGTERM handler | 🔴 | Already addressed in CRITICAL-3 |

#### Recommended `start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# CVA Backend Startup Script
# ============================================================

# Configuration with safe defaults
PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${CVA_WORKERS:-1}"
LOG_LEVEL="${CVA_LOG_LEVEL:-info}"
TIMEOUT_KEEP_ALIVE="${CVA_TIMEOUT_KEEP_ALIVE:-30}"

echo "========================================"
echo "[CVA] Starting CVA API"
echo "[CVA] PORT=${PORT}"
echo "[CVA] HOST=${HOST}"
echo "[CVA] WORKERS=${WORKERS}"
echo "[CVA] LOG_LEVEL=${LOG_LEVEL}"
echo "[CVA] RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not_set}"
echo "[CVA] RAILWAY_PRIVATE_DOMAIN=${RAILWAY_PRIVATE_DOMAIN:-not_set}"
echo "[CVA] DATABASE_URL=${DATABASE_URL:+SET}"
echo "[CVA] CVA_PRODUCTION=${CVA_PRODUCTION:-false}"
echo "========================================"

# Pre-flight: Verify critical config in production
if [[ "${CVA_PRODUCTION:-false}" == "true" ]]; then
    missing=""
    [[ -z "${DATABASE_URL:-}" ]] && missing+="DATABASE_URL "
    [[ -z "${CVA_API_TOKEN:-}" ]] && missing+="CVA_API_TOKEN "
    
    if [[ -n "$missing" ]]; then
        echo "[CVA] FATAL: Missing required variables: $missing"
        exit 1
    fi
fi

# Start with proper configuration
exec python -m uvicorn modules.api:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --timeout-keep-alive "${TIMEOUT_KEEP_ALIVE}" \
    --access-log
```

### 2.2 Frontend Startup (`scripts/start.js`)

**Current Implementation:**
```javascript
const child = spawn(
  process.execPath,
  [
    'node_modules/next/dist/bin/next',
    'start',
    '-p',
    String(port),
    ...(hostname ? ['-H', String(hostname)] : []),
  ],
  { stdio: 'inherit', env: process.env }
);
```

#### Issues Identified:

| Issue | Severity | Description |
|-------|----------|-------------|
| No backend connectivity check | 🟡 | UI starts even if backend unreachable |
| Missing HOSTNAME binding | 🟢 | Should always bind 0.0.0.0 for Railway |
| Hardcoded spawn path | 🟢 | Could use `npx next start` |

#### Recommended Improvement:

```javascript
const port = process.env.PORT || '3000';
const hostname = '0.0.0.0';  // Always bind all interfaces

console.log(`[start.js] Starting Next.js on ${hostname}:${port}`);
console.log(`[start.js] CVA_BACKEND_URL=${process.env.CVA_BACKEND_URL || 'NOT SET'}`);

// Pre-flight: Warn if backend URL not configured
if (!process.env.CVA_BACKEND_URL) {
    console.warn('[start.js] WARNING: CVA_BACKEND_URL not set. API calls will fail.');
}

const child = spawn(
  'npx',
  ['next', 'start', '-p', String(port), '-H', hostname],
  { stdio: 'inherit', env: process.env, shell: true }
);
```

### 2.3 Development Startup (`dev_start.ps1`)

**Strengths:**
- ✅ Comprehensive environment validation
- ✅ Port cleanup before start
- ✅ Health check with timeout
- ✅ Log capture and error reporting
- ✅ Graceful shutdown handling
- ✅ Detached mode support

**Issues Identified:**

| Issue | Severity | Description |
|-------|----------|-------------|
| Health check URL is `/` not `/health` | 🟢 | Deep check is slow |
| No parallel startup | 🟡 | Backend waits before frontend starts |
| Missing .env loading | 🟡 | Requires manual env setup |

#### Recommended Enhancement:

```powershell
# Add to Phase 3 (before backend start):

# Load .env if present
$envFile = Join-Path $BACKEND_DIR ".env"
if (Test-Path $envFile) {
    Write-Step "Loading .env file"
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}
```

---

## Part 3: Workflow & Module Analysis

### 3.1 Module Dependency Graph

```
                    ┌─────────────┐
                    │   api.py    │ ◄── FastAPI Entry Point
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌────────────────┐
│   tribunal    │  │   parser     │  │  file_manager  │
│ (LLM Judges)  │  │ (Extraction) │  │  (Git/Files)   │
└───────┬───────┘  └──────────────┘  └────────────────┘
        │
        ▼
┌───────────────┐
│ judge_engine  │
│ (Orchestrator)│
└───────┬───────┘
        │
        ├───────────────────┐
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│    router     │   │  self_heal    │
│ (Lane Select) │   │ (Auto-fix)    │
└───────────────┘   └───────────────┘
```

### 3.2 Identified Workflow Gaps

#### 🔴 GAP-1: No Circuit Breaker for LLM Calls

**Problem:** If an LLM provider is down, every request still attempts to call it, causing:
- Slow response times (waiting for timeout)
- Wasted API quota on retries
- Poor user experience

**Current Behavior:**
```python
# router.py - Fallback exists but no circuit breaker
fallback:
  models:
    - "openai/gpt-4o"
    - "deepseek/deepseek-chat"
    - "gemini/gemini-2.0-flash-exp"
```

**Recommendation:** Implement circuit breaker pattern:
```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CircuitState:
    failures: int = 0
    last_failure: datetime = None
    open_until: datetime = None
    
    def is_open(self) -> bool:
        if self.open_until and datetime.now() < self.open_until:
            return True
        return False
    
    def record_failure(self):
        self.failures += 1
        self.last_failure = datetime.now()
        if self.failures >= 3:  # Trip after 3 failures
            self.open_until = datetime.now() + timedelta(minutes=5)
```

#### 🟡 GAP-2: No Request Correlation IDs

**Problem:** Debugging distributed requests across Backend/UI/LLMs is difficult without correlation.

**Recommendation:**
```python
from fastapi import Request
import uuid

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    
    return response
```

#### 🟡 GAP-3: WebSocket Reconnection Not Handled

**File:** `modules/api.py`

**Problem:** If WebSocket connection drops (network hiccup), clients have no built-in reconnection logic.

**Recommendation:** UI should implement exponential backoff reconnection:
```javascript
// UI-side
class ReconnectingWebSocket {
    constructor(url, options = {}) {
        this.url = url;
        this.reconnectInterval = 1000;
        this.maxReconnectInterval = 30000;
        this.connect();
    }
    
    connect() {
        this.ws = new WebSocket(this.url);
        this.ws.onclose = () => this.reconnect();
        this.ws.onerror = () => this.reconnect();
    }
    
    reconnect() {
        setTimeout(() => {
            this.reconnectInterval = Math.min(
                this.reconnectInterval * 2,
                this.maxReconnectInterval
            );
            this.connect();
        }, this.reconnectInterval);
    }
}
```

---

## Part 4: Testing Analysis

### 4.1 Test Coverage Assessment

**Test Files Found:** 24 test files

| Category | Files | Coverage |
|----------|-------|----------|
| Integration | 3 | Basic endpoint tests |
| Parser | 1 | Constitution parsing |
| Router | 1 | Lane selection logic |
| Tribunal | 6 | Core judgment logic |
| Persistence | 2 | DB operations |
| WebSocket | 1 | Token auth |
| Self-Heal | 1 | Auto-fix loop |

### 4.2 Testing Gaps

#### 🔴 GAP-T1: No Load/Stress Testing

**Problem:** Unknown behavior under concurrent load. Critical for:
- Railway auto-scaling decisions
- Rate limit tuning
- Connection pool sizing

**Recommendation:** Add load tests using `locust` or `k6`:
```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class CVAUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def health_check(self):
        self.client.get("/")
    
    @task(1)
    def trigger_run(self):
        self.client.post("/run", json={...})
```

#### 🟡 GAP-T2: No Chaos Testing

**Problem:** Unknown behavior when:
- Database connection drops
- LLM provider returns 500
- Network latency spikes

**Recommendation:** Add failure injection tests:
```python
@pytest.fixture
def flaky_db():
    """Simulate intermittent DB failures."""
    original = db.get_engine
    call_count = 0
    
    def flaky_engine():
        nonlocal call_count
        call_count += 1
        if call_count % 3 == 0:
            raise ConnectionError("Simulated failure")
        return original()
    
    db.get_engine = flaky_engine
    yield
    db.get_engine = original
```

#### 🟡 GAP-T3: Missing Railway-Specific Tests

**Problem:** Behavior differs between local and Railway environments.

**Recommendation:** Add environment-specific test fixtures:
```python
@pytest.fixture
def railway_env(monkeypatch):
    """Simulate Railway environment."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("DATABASE_URL", "postgresql://...")
```

---

## Part 5: Security Review

### 5.1 Current Security Measures

| Measure | Status | Notes |
|---------|--------|-------|
| API Token Auth | ✅ | Required in production |
| CORS Configuration | ✅ | Configurable origins |
| Rate Limiting | ⚠️ | In-memory only |
| Input Validation | ✅ | Pydantic schemas |
| SQL Injection | ✅ | SQLAlchemy ORM |
| Secret Logging | ✅ | Tokens masked in logs |

### 5.2 Security Recommendations

#### 🟡 SEC-1: Add Request Signing for Inter-Service Calls

**Problem:** Backend-to-UI communication uses shared token, vulnerable to MITM on private network.

**Recommendation:** Add HMAC request signing:
```python
import hmac
import hashlib

def sign_request(body: bytes, secret: str, timestamp: int) -> str:
    message = f"{timestamp}.{body.decode()}"
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
```

#### 🟡 SEC-2: Add Security Headers

```python
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
```

---

## Part 6: Recommendations Summary

### 6.1 Immediate Actions (Fix Before Next Deploy)

1. **Merge startup handlers** into unified lifespan context
2. **Fail-fast on missing DATABASE_URL** in production
3. **Add `/health` lightweight endpoint** for Railway health checks
4. **Configure uvicorn timeouts** in `start.sh`

### 6.2 Short-Term Improvements (This Week)

1. **Add connection pool configuration** to database engine
2. **Implement correlation IDs** for request tracing
3. **Add pre-flight checks** in `start.sh`
4. **Separate readiness from liveness** endpoints

### 6.3 Medium-Term Enhancements (This Month)

1. **Implement circuit breaker** for LLM calls
2. **Add Redis-based rate limiting** 
3. **Create load testing suite**
4. **Add WebSocket reconnection** in UI

### 6.4 Long-Term Architecture (Next Quarter)

1. **Implement distributed tracing** (OpenTelemetry)
2. **Add chaos testing framework**
3. **Create deployment runbook** with rollback procedures
4. **Implement blue-green deployment** for zero-downtime updates

---

## Appendix A: Environment Variables Reference

### Backend (Required in Production)

| Variable | Purpose | Example |
|----------|---------|---------|
| `PORT` | Railway-injected port | `8080` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://...` |
| `CVA_API_TOKEN` | Shared auth token | `your-secret-token` |
| `CVA_PRODUCTION` | Enable production mode | `true` |

### Backend (Optional)

| Variable | Purpose | Default |
|----------|---------|---------|
| `CVA_WORKERS` | Uvicorn workers | `1` |
| `CVA_LOG_LEVEL` | Log verbosity | `info` |
| `CVA_MONITOR_WORKER` | Enable monitor | `false` |
| `CVA_APPLY_MIGRATIONS` | Auto-migrate | `false` |

### Frontend (Required)

| Variable | Purpose | Example |
|----------|---------|---------|
| `CVA_BACKEND_URL` | Backend private URL | `http://backend.railway.internal:8080` |
| `CVA_API_TOKEN` | Same as backend | `your-secret-token` |
| `NEXTAUTH_URL` | Public URL | `https://app.example.com` |
| `NEXTAUTH_SECRET` | Auth secret | `generated-secret` |

---

## Appendix B: Startup Sequence Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Railway  │     │ start.sh │     │ Uvicorn  │     │ FastAPI  │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ Deploy         │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │                │ Validate env   │                │
     │                │───────────────>│                │
     │                │                │                │
     │                │ exec uvicorn   │                │
     │                │───────────────>│                │
     │                │                │                │
     │                │                │ Load app       │
     │                │                │───────────────>│
     │                │                │                │
     │                │                │                │ lifespan()
     │                │                │                │──┐
     │                │                │                │  │ 1. Create dirs
     │                │                │                │  │ 2. Apply migrations
     │                │                │                │  │ 3. Ensure schema
     │                │                │                │  │ 4. Start worker
     │                │                │                │<─┘
     │                │                │                │
     │                │                │ Ready          │
     │                │                │<───────────────│
     │                │                │                │
     │ Health check /health            │                │
     │────────────────────────────────>│                │
     │                │                │                │
     │ 200 OK         │                │                │
     │<────────────────────────────────│                │
     │                │                │                │
     │ Route traffic  │                │                │
     │═══════════════════════════════════════════════>│
```

---

**Report Generated By:** System Architecture Analysis  
**Review Status:** Complete  
**Next Review:** After implementing critical fixes
