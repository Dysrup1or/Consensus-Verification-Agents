# Invariant Railway Migration Guide (December 2025)

This guide covers the complete Railway deployment for Invariant, including the latest migrations (003_analytics_tables.sql, 004_remediation_tables.sql) and VS Code Extension cloud support.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAILWAY PROJECT                           │
│                                                                   │
│  ┌─────────────────┐    Private URL    ┌─────────────────────┐ │
│  │  invariant-ui   │ ←───────────────→ │   invariant-api     │ │
│  │   (Next.js)     │                   │     (FastAPI)       │ │
│  │                 │                   │                     │ │
│  │ Public Domain:  │                   │ No Public Domain    │ │
│  │ invariant.      │                   │ (internal only)     │ │
│  │ dysrupt-ion.com │                   │                     │ │
│  └────────┬────────┘                   └──────────┬──────────┘ │
│           │                                       │             │
│           │                            ┌──────────▼──────────┐ │
│           │                            │     PostgreSQL      │ │
│           │                            │   (Railway Plugin)  │ │
│           └────────────────────────────│                     │ │
│              Shared Variables          │ New Tables:         │ │
│                                        │ - analytics_*       │ │
│                                        │ - remediation_*     │ │
│                                        └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                    VS Code Extension
                   (cva.useCloudBackend=true)
```

---

## 1. Prerequisites

### 1.1 Railway Account & Project
- Railway account with billing enabled
- One Railway Project with two environments: `production` and `staging`

### 1.2 PostgreSQL Database
Each environment needs a PostgreSQL database:
1. In Railway Dashboard → Add Plugin → PostgreSQL
2. Do this for both `production` and `staging` environments
3. Railway auto-injects `DATABASE_URL` into linked services

### 1.3 GitHub Repository
- Push latest code including migrations 003 and 004
- Railway auto-deploys on push to main/staging branches

---

## 2. Backend Service Setup (invariant-api)

### 2.1 Create Service
- **Source**: GitHub repo
- **Root Directory**: `dysruption_cva`
- **Build Command**: *(leave blank - Nixpacks auto-detects)*
- **Start Command**: `bash start.sh`

### 2.2 Link PostgreSQL
In service settings → Variables → Link the PostgreSQL plugin.
This auto-injects `DATABASE_URL`.

### 2.3 Required Environment Variables

```bash
# Core settings
CVA_PRODUCTION=true
CVA_API_TOKEN=<strong-random-token-32chars>

# Database migrations (IMPORTANT for new tables)
CVA_APPLY_MIGRATIONS=true

# LLM Provider Keys (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Optional: Monitor worker
CVA_MONITOR_WORKER=true
```

### 2.4 Networking
- **DO NOT** add a public domain
- Copy the **private/internal URL** for UI configuration
- Format: `http://invariant-api.railway.internal:PORT`

---

## 3. UI Service Setup (invariant-ui)

### 3.1 Create Service
- **Source**: GitHub repo
- **Root Directory**: `dysruption-ui`
- **Build Command**: `npm run build`
- **Start Command**: `npm start`

### 3.2 Required Environment Variables

```bash
# Backend connection (use PRIVATE URL from backend service)
CVA_BACKEND_URL=http://invariant-api.railway.internal:PORT
CVA_API_TOKEN=<same-token-as-backend>

# NextAuth
NEXTAUTH_URL=https://invariant.dysrupt-ion.com
NEXTAUTH_SECRET=<strong-random-secret-32chars>

# OAuth Providers
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_ID=...
GITHUB_SECRET=...

# Build stability
NIXPACKS_NODE_VERSION=20
```

### 3.3 Custom Domain
- Add domain: `invariant.dysrupt-ion.com` (production)
- Add domain: `staging.invariant.dysrupt-ion.com` (staging)
- Configure DNS in Cloudflare → CNAME to Railway

---

## 4. Database Migrations

### 4.1 Migration Files
The backend includes these migrations in `db/migrations/`:

| Version | File | Purpose |
|---------|------|---------|
| 001 | `001_init.sql` | Core tables (runs, repo_connections, etc.) |
| 002 | `002_monitor_jobs.sql` | Monitor job queue |
| 003 | `003_analytics_tables.sql` | **NEW**: Analytics dashboard |
| 004 | `004_remediation_tables.sql` | **NEW**: Autonomous remediation |

### 4.2 Automatic Migration
Migrations run automatically on startup when:
```bash
CVA_APPLY_MIGRATIONS=true
DATABASE_URL=<postgres-url>
```

The backend:
1. Creates `schema_migrations` table if missing
2. Checks which migrations are already applied
3. Runs only new migrations in order
4. Logs progress

### 4.3 Verify Migrations Ran
Check backend logs after deploy:
```
[CVA] Applying migration 003_analytics_tables
[CVA] Applying migration 004_remediation_tables
[CVA] Migrations applied: 2
```

### 4.4 Manual Migration (if needed)
If migrations need to be run manually:
```bash
# Connect to Railway PostgreSQL via CLI
railway connect postgres

# Then run migrations manually
\i /app/db/migrations/003_analytics_tables.sql
\i /app/db/migrations/004_remediation_tables.sql
```

---

## 5. VS Code Extension Cloud Mode

### 5.1 Extension Settings
Users configure cloud mode in VS Code settings:

```json
{
  "cva.useCloudBackend": true,
  "cva.cloudBackendUrl": "https://invariant.dysrupt-ion.com",
  "cva.cloudApiToken": "<user-api-token>"
}
```

### 5.2 How It Works
When `useCloudBackend=true`:
- Extension skips local Python backend startup
- All API calls go to cloud URL with Bearer token
- WebSocket connects to `wss://invariant.dysrupt-ion.com/ws`

### 5.3 Token Generation
Users need API tokens. Options:
1. **Manual**: Admin generates tokens and shares
2. **Self-service**: UI dashboard → Settings → Generate Token
3. **OAuth flow**: Extension opens browser for login (future)

---

## 6. Shared Variables (Recommended Setup)

Use Railway's **Shared Variables** for settings used by both services:

### Production Environment
```bash
CVA_PRODUCTION=true
CVA_API_TOKEN=<prod-token>
CVA_BACKEND_URL=<prod-private-backend-url>
CVA_APPLY_MIGRATIONS=true

NEXTAUTH_URL=https://invariant.dysrupt-ion.com
NEXTAUTH_SECRET=<prod-secret>

GOOGLE_CLIENT_ID=<prod>
GOOGLE_CLIENT_SECRET=<prod>
GITHUB_ID=<prod>
GITHUB_SECRET=<prod>
```

### Staging Environment
```bash
CVA_PRODUCTION=true
CVA_API_TOKEN=<staging-token>
CVA_BACKEND_URL=<staging-private-backend-url>
CVA_APPLY_MIGRATIONS=true

NEXTAUTH_URL=https://staging.invariant.dysrupt-ion.com
NEXTAUTH_SECRET=<staging-secret>

GOOGLE_CLIENT_ID=<staging>
GOOGLE_CLIENT_SECRET=<staging>
GITHUB_ID=<staging>
GITHUB_SECRET=<staging>
```

---

## 7. What Changed from Previous Setup

### 7.1 New Environment Variables
| Variable | Required | Purpose |
|----------|----------|---------|
| `CVA_APPLY_MIGRATIONS` | Yes | Run DB migrations on startup |
| `CVA_MONITOR_WORKER` | Optional | Enable background job worker |

### 7.2 New Database Tables
- `analytics_run_metrics` - Denormalized run data for dashboards
- `analytics_daily_rollups` - Pre-aggregated daily stats
- `analytics_rule_performance` - Per-rule pass/fail rates
- `remediation_runs` - Autonomous fix tracking
- `remediation_issues` - Issues detected per run
- `remediation_fixes` - Fix attempts and results
- `remediation_root_causes` - Root cause analysis

### 7.3 What's No Longer Needed
| Item | Status |
|------|--------|
| SQLite fallback | Still works for local dev, but not used in Railway |
| Manual `pip install` | Nixpacks handles this |
| Port hardcoding | Uses Railway `$PORT` via start.sh |

---

## 8. Deployment Checklist

### Pre-Deploy
- [ ] Code pushed to GitHub (main or staging branch)
- [ ] PostgreSQL plugin linked to backend service
- [ ] All environment variables set
- [ ] `CVA_APPLY_MIGRATIONS=true` set on backend

### Deploy Backend First
- [ ] Trigger deploy on `invariant-api`
- [ ] Check logs for: `Migrations applied: N`
- [ ] Check logs for: `CVA API v1.2 starting up`
- [ ] Verify health: `GET /health` returns 200

### Deploy UI Second
- [ ] Trigger deploy on `invariant-ui`
- [ ] Verify login page loads
- [ ] Test OAuth flow (Google/GitHub)
- [ ] Test backend connectivity (any API action)

### Post-Deploy Verification
- [ ] Create a repo connection in UI
- [ ] Trigger a verification run
- [ ] Check analytics dashboard loads
- [ ] Test VS Code extension with cloud mode

---

## 9. Troubleshooting

### "DATABASE_URL is required" Error
```
RuntimeError: DATABASE_URL environment variable is required in production/Railway
```
**Fix**: Link PostgreSQL plugin to the backend service in Railway Dashboard.

### Migrations Not Running
Check backend logs for:
```
[CVA] CVA_APPLY_MIGRATIONS not set, skipping migrations
```
**Fix**: Set `CVA_APPLY_MIGRATIONS=true` in backend service variables.

### UI Can't Reach Backend
```
Backend connection failed
```
**Fix**: Verify `CVA_BACKEND_URL` uses the **private internal URL**, not a public domain.

### Extension Shows "Backend not healthy"
1. Check `cva.cloudApiToken` is set in VS Code settings
2. Verify the token matches `CVA_API_TOKEN` on Railway
3. Check `cva.cloudBackendUrl` is correct

---

## 10. Quick Reference Commands

### Railway CLI
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link

# View logs
railway logs -s invariant-api

# Open PostgreSQL shell
railway connect postgres

# Deploy manually
railway up
```

### Health Checks
```bash
# Backend health
curl https://invariant.dysrupt-ion.com/health

# API info (with auth)
curl -H "Authorization: Bearer <token>" https://invariant.dysrupt-ion.com/
```

---

## Summary

| Service | Root Dir | Start Command | Public Domain |
|---------|----------|---------------|---------------|
| invariant-api | `dysruption_cva` | `bash start.sh` | None (private) |
| invariant-ui | `dysruption-ui` | `npm start` | invariant.dysrupt-ion.com |

| Key Variable | Where | Purpose |
|--------------|-------|---------|
| `CVA_APPLY_MIGRATIONS` | Backend | Run new migrations |
| `CVA_API_TOKEN` | Both | Internal auth |
| `CVA_BACKEND_URL` | UI | Private backend URL |
| `cva.cloudApiToken` | VS Code | Extension auth |
