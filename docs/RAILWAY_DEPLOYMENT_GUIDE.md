# Railway Deployment Guide: Complete Reference

> **Last Updated**: December 16, 2025  
> **Based on**: Railway documentation, community forums, and hands-on debugging

This document consolidates all Railway deployment knowledge gathered during the Invariant/CVA deployment. Use it as a reference for future Railway projects.

---

## Table of Contents

1. [Understanding Railway's Architecture](#understanding-railways-architecture)
2. [PORT Configuration (Critical)](#port-configuration-critical)
3. [Private Networking](#private-networking)
4. [Environment Variables](#environment-variables)
5. [Service-to-Service Communication](#service-to-service-communication)
6. [Config-as-Code](#config-as-code)
7. [Framework-Specific Configuration](#framework-specific-configuration)
8. [Common Errors and Solutions](#common-errors-and-solutions)
9. [Cost Optimization Tips](#cost-optimization-tips)
10. [Debugging Checklist](#debugging-checklist)

---

## Understanding Railway's Architecture

### How Railway Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Railway Project                               │
│  ┌─────────────────┐                    ┌─────────────────┐         │
│  │   Public Proxy  │                    │  Private Network │         │
│  │  (edge routing) │                    │  (wireguard mesh)│         │
│  └────────┬────────┘                    └────────┬─────────┘         │
│           │                                      │                   │
│           ▼                                      ▼                   │
│  ┌─────────────────┐    internal DNS    ┌─────────────────┐         │
│  │    Frontend     │◄──────────────────►│     Backend     │         │
│  │   (Next.js)     │  .railway.internal │    (FastAPI)    │         │
│  │   PORT=8080     │                    │    PORT=8080    │         │
│  └─────────────────┘                    └─────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Project** | Container for all services, databases, and environments |
| **Environment** | Isolated deployment context (production, staging, PR previews) |
| **Service** | Individual deployable unit (your app, database, etc.) |
| **Private Network** | Encrypted Wireguard mesh between services in same environment |

---

## PORT Configuration (Critical)

### The Golden Rule

> **Railway's proxy routes traffic to your service based on the PORT environment variable. Your app MUST listen on the PORT that Railway injects, or Railway will kill your container.**

### How PORT Works

```
Railway injects PORT ──► Your app reads $PORT ──► App listens on $PORT
         │                                               │
         └───────────────────────────────────────────────┘
                   Must match! Or "connection refused"
```

### Correct Start Commands

```bash
# ✅ CORRECT: Use Railway's injected PORT
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}

# ✅ CORRECT: Next.js
next start -p ${PORT:-3000}

# ❌ WRONG: Hardcoded port (Railway can't route to it)
uvicorn app:app --host 0.0.0.0 --port 8001
```

### Setting a Fixed PORT

If you need a predictable port (e.g., for private networking URLs):

1. Go to **Railway Dashboard → Service → Variables**
2. Add: `PORT = 8001`
3. This overrides Railway's auto-injection
4. Your app will use this PORT consistently

### Common PORT Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Hardcoding PORT in code | "Connection refused", container restarts | Use `${PORT:-default}` |
| Different PORT for public/private | 502 errors on public, works on private | Use same PORT for both |
| Not binding to 0.0.0.0 | "Connection refused" | Use `--host 0.0.0.0` |

---

## Private Networking

### Overview

Private networking allows service-to-service communication without exposing ports publicly. Each service gets a DNS name under `.railway.internal`.

### Requirements

1. **Same Environment**: Services must be in the same Railway environment
2. **Explicit PORT**: You must specify the port in the URL
3. **Correct Host Binding**: App must bind to `0.0.0.0` or `::`
4. **Not Available at Build Time**: Private networking only works at runtime

### URL Format

```
http://<service-name>.railway.internal:<PORT>
```

**Examples:**
```
http://api.railway.internal:8080
http://backend.railway.internal:3000
http://postgres.railway.internal:5432
```

> ⚠️ **CRITICAL**: The PORT is REQUIRED. `http://api.railway.internal` alone will NOT work!

### IPv4 vs IPv6

| Environment Type | IPv4 Support | IPv6 Support | Recommendation |
|-----------------|--------------|--------------|----------------|
| New (after Oct 16, 2025) | ✅ Yes | ✅ Yes | Use `0.0.0.0` or `::` |
| Legacy (before Oct 16, 2025) | ❌ No | ✅ Yes | Use `::` and ensure dual-stack |

### Host Binding by Framework

| Framework | Recommended Host | Notes |
|-----------|-----------------|-------|
| **Uvicorn (Python)** | `0.0.0.0` | `::` doesn't support dual-stack |
| **Gunicorn** | `[::]:PORT` or `0.0.0.0:PORT` | Dual-stack works |
| **Next.js** | `::` | Or set `HOSTNAME=::` |
| **Express/Node** | `::` | Dual-stack works |

---

## Environment Variables

### Railway-Provided Variables

These are automatically available in every deployment:

| Variable | Description | Example |
|----------|-------------|---------|
| `PORT` | Port Railway expects your app to listen on | `8080` |
| `RAILWAY_ENVIRONMENT` | Current environment name | `production` |
| `RAILWAY_PRIVATE_DOMAIN` | Private DNS name | `api.railway.internal` |
| `RAILWAY_PUBLIC_DOMAIN` | Public domain (if configured) | `app.up.railway.app` |
| `RAILWAY_SERVICE_NAME` | Service name | `backend` |
| `RAILWAY_PROJECT_ID` | Project UUID | `abc-123-def` |

### Setting Variables

**In Dashboard (Recommended):**
1. Go to Service → Variables tab
2. Click "New Variable"
3. Enter name and value
4. Click "Deploy Changes"

**In Code (Config-as-Code - Limited):**
> ⚠️ The `variables` section in `railway.json` is **NOT supported**. Variables must be set in the Dashboard.

### Reference Variables (Cross-Service)

Reference another service's variables:
```
${{ServiceName.VARIABLE_NAME}}
```

**Example:**
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
BACKEND_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}
```

> ⚠️ **IMPORTANT**: `${{service.PORT}}` only resolves to a **manually set** PORT variable, NOT Railway's auto-injected PORT!

### Shared Variables

For variables used across multiple services:
1. Go to Project Settings → Shared Variables
2. Add variable
3. Reference with `${{shared.VAR_NAME}}`

---

## Service-to-Service Communication

### Pattern: Frontend → Backend

**Backend Service Variables:**
```
PORT=8001
CVA_API_TOKEN=your-secure-token
```

**Frontend Service Variables:**
```
CVA_BACKEND_URL=http://backend.railway.internal:8001
CVA_API_TOKEN=your-secure-token
```

### Using Reference Variables

```
BACKEND_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:${{backend.PORT}}
```

Where `backend` is the exact service name (case-sensitive!).

### Debugging Connectivity

1. Check both services are in the same environment
2. Verify PORT matches between URL and backend's actual port
3. Check backend logs - is it actually running?
4. Try public URL as fallback to isolate private networking issues

---

## Config-as-Code

### Supported: `railway.json` / `railway.toml`

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

### What's Supported

| Section | Supported | Notes |
|---------|-----------|-------|
| `build.builder` | ✅ | RAILPACK, NIXPACKS, DOCKERFILE |
| `build.buildCommand` | ✅ | Custom build command |
| `build.watchPatterns` | ✅ | Trigger deploys on file changes |
| `deploy.startCommand` | ✅ | Override start command |
| `deploy.healthcheckPath` | ✅ | Health check endpoint |
| `deploy.restartPolicyType` | ✅ | ON_FAILURE, ALWAYS, NEVER |
| `variables` | ❌ | **NOT SUPPORTED** - use Dashboard |

### Environment Overrides

```json
{
  "environments": {
    "production": {
      "deploy": {
        "startCommand": "npm run start:prod"
      }
    },
    "staging": {
      "deploy": {
        "startCommand": "npm run start:staging"
      }
    }
  }
}
```

---

## Framework-Specific Configuration

### Python / FastAPI / Uvicorn

```bash
# start.sh
#!/usr/bin/env bash
PORT="${PORT:-8000}"
HOST="0.0.0.0"
exec python -m uvicorn modules.api:app --host "${HOST}" --port "${PORT}"
```

**Key Points:**
- Use `0.0.0.0`, NOT `::` (Uvicorn doesn't support dual-stack with `::`)
- Never override Railway's PORT unless you set it in Dashboard
- Use `exec` to replace shell process (proper signal handling)

### Next.js

```javascript
// scripts/start.js
const port = process.env.PORT || '3000';
spawn('next', ['start', '-p', port, '-H', '::']);
```

Or set environment variable:
```
HOSTNAME=::
```

**Key Points:**
- Use `::` for dual-stack binding
- Next.js `NEXT_PUBLIC_*` vars are baked at build time
- Use runtime injection for dynamic env vars

### Node.js / Express

```javascript
const port = process.env.PORT || 3000;
app.listen(port, '::', () => {
  console.log(`Server listening on [::]:${port}`);
});
```

---

## Common Errors and Solutions

### 502 Bad Gateway

**Symptoms:**
- "Application failed to respond"
- HTTP 502 errors

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| App not listening on Railway's PORT | Use `${PORT:-default}` |
| App binding to wrong interface | Use `0.0.0.0` or `::` |
| App crashing on startup | Check logs for errors |
| Health check failing | Add `/health` endpoint or increase timeout |

### Connection Refused (Private Networking)

**Symptoms:**
- 502 on private networking
- "connection refused" in logs

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Missing PORT in URL | Add `:PORT` to URL |
| PORT mismatch | Ensure URL port matches app's actual port |
| Different environments | Move services to same environment |
| IPv6-only legacy env | Bind to `::` instead of `0.0.0.0` |

### 402 Payment Required

**Cause:** Railway credit/billing issue

**Fix:**
1. Go to https://railway.app/account/billing
2. Add credits or upgrade plan
3. Hobby plan is $5/month with $5 included usage

### Container Immediately Exits

**Symptoms:**
- App starts then immediately shuts down
- "Finished server process" right after startup

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| PORT mismatch with Railway proxy | Use Railway's injected PORT |
| Invalid host binding | Use `0.0.0.0` instead of empty string |
| Missing required env vars | Check all required vars are set |

### Environment Variable "NOT SET"

**Symptoms:**
- Logs show `VAR=NOT SET`
- Reference variables resolve to empty

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Variable not in Dashboard | Add it in Service → Variables |
| Config-as-code `variables` | Not supported - use Dashboard |
| Wrong service name in reference | Check exact name (case-sensitive) |
| Different environment | Variables are environment-scoped |

---

## Cost Optimization Tips

### Railway Pricing Model

- **Trial**: $5 one-time credit, no monthly fee
- **Hobby**: $5/month + usage (includes $5 usage)
- **Pro**: $20/month + usage, team features

### Usage-Based Costs

| Resource | Cost |
|----------|------|
| vCPU | $0.000231/minute |
| Memory | $0.000231/GB/minute |
| Network Egress | $0.10/GB |
| Disk | $0.000231/GB/minute |

### Optimization Strategies

1. **Use App Sleeping** - Services with no traffic sleep automatically (Hobby+)
2. **Optimize Docker Images** - Smaller images = faster deploys, less disk
3. **Use Private Networking** - No egress costs for internal traffic
4. **Set Resource Limits** - Prevent runaway costs
5. **Use Cron Jobs** - For periodic tasks instead of always-on services

### Monitoring Costs

1. Go to Project → Usage
2. Review by service
3. Set up billing alerts

---

## Debugging Checklist

When something doesn't work, check these in order:

### Deployment Issues

- [ ] Build succeeded? Check build logs
- [ ] Start command correct? Check `railway.json` or Dashboard
- [ ] All required env vars set? Check Variables tab
- [ ] Health check passing? Check healthcheck path and timeout

### Networking Issues

- [ ] App binding to correct host? (`0.0.0.0` or `::`)
- [ ] App using Railway's PORT? (`${PORT:-default}`)
- [ ] Services in same environment? (for private networking)
- [ ] PORT included in private networking URL?
- [ ] Service name exact match for reference variables?

### Variable Issues

- [ ] Variable set in Dashboard (not just config-as-code)?
- [ ] Reference variable syntax correct? (`${{service.VAR}}`)
- [ ] Service name case-sensitive match?
- [ ] Using autocomplete for service references?

### General

- [ ] Recent deploy? Variables only apply after deploy
- [ ] Check service logs for errors
- [ ] Try public URL to isolate private networking
- [ ] Check Railway status page for platform issues

---

## Quick Reference Card

### Start Commands

```bash
# Python/Uvicorn
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}

# Python/Gunicorn
gunicorn app:app --bind 0.0.0.0:${PORT:-8000}

# Node.js/Next.js
next start -p ${PORT:-3000} -H ::

# Node.js/Express
node server.js  # (read PORT in code)
```

### Private Networking URL

```
http://<service-name>.railway.internal:<PORT>
```

### Reference Variable

```
${{ServiceName.VARIABLE_NAME}}
```

### Railway-Provided Variables

```
PORT, RAILWAY_ENVIRONMENT, RAILWAY_PRIVATE_DOMAIN, 
RAILWAY_PUBLIC_DOMAIN, RAILWAY_SERVICE_NAME
```

---

## Resources

- [Railway Documentation](https://docs.railway.com/)
- [Private Networking Guide](https://docs.railway.com/guides/private-networking)
- [Variables Reference](https://docs.railway.com/reference/variables)
- [Config as Code](https://docs.railway.com/reference/config-as-code)
- [Pricing](https://docs.railway.com/reference/pricing)
- [Railway Status](https://status.railway.com/)
- [Railway Community](https://community.railway.app/)

---

## Document History

| Date | Changes |
|------|---------|
| 2025-12-16 | Initial version based on Invariant/CVA deployment debugging |
