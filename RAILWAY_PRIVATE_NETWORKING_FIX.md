# Railway Private Networking: Complete Fix Guide

## The Problem

Your UI shows `CVA_BACKEND_URL=http://:` which means the reference variables resolved to **empty strings**.

## Root Cause

Railway's config-as-code **does NOT support the `variables` section**. Variables must be set **directly in the Railway Dashboard**.

---

## THE FIX: Step-by-Step (Dashboard Only)

### Option A: Use Literal Private Domain (FASTEST)

**In Railway Dashboard → Invariant UI → Variables:**

Set `CVA_BACKEND_URL` to this exact literal value:
```
http://consensus-verification-agents.railway.internal:8001
```

> ⚠️ This is the SIMPLEST fix. No reference variables, just the literal domain.

### Option B: Use Reference Variables with Autocomplete

If you want to use reference variables (more maintainable):

1. Go to **Invariant UI → Variables** in Railway Dashboard
2. Click **"New Variable"**
3. Name: `CVA_BACKEND_URL`
4. Value: Start typing `http://${{` 
5. **Use the autocomplete dropdown** to select your backend service
6. Complete with `.RAILWAY_PRIVATE_DOMAIN}}:8001`

The autocomplete ensures the service name matches exactly (case-sensitive!).

---

## CRITICAL: Also Add PORT to Backend Service

**In Railway Dashboard → Consensus-Verification-Agents → Variables:**

Add this variable manually:
```
PORT = 8001
```

This is REQUIRED because:
- `start.sh` uses `PORT="${PORT:-8001}"` 
- Railway injects its own PORT but for reference variables you need it set explicitly

---

## Why Reference Variables Showed Empty

The `http://:` output means both `RAILWAY_PRIVATE_DOMAIN` and `PORT` resolved to empty because:

1. **Config-as-code doesn't support variables** - The `railway.json` `variables` section is not a real feature
2. **Service name mismatch** - Reference syntax is case-sensitive
3. **Variables not set in Dashboard** - They must be set directly in the UI

---

## Verification After Fix

After setting `CVA_BACKEND_URL` in the Dashboard, redeploy the UI service.

The logs should show:
```
[start.js] CVA_BACKEND_URL=http://consensus-verification-agents.railway.internal:8001
```

NOT:
```
[start.js] CVA_BACKEND_URL=http://:
```

---

## Fallback: Use Public URL

If private networking still fails, use the public domain:
```
CVA_BACKEND_URL=https://invariant-api-production.up.railway.app
```

---

## Quick Reference: Required Dashboard Variables

### Backend Service (Consensus-Verification-Agents):
| Variable | Value |
|----------|-------|
| `PORT` | `8001` |
| `CVA_API_TOKEN` | (your secure token) |
| `DATABASE_URL` | (your database URL) |

### UI Service (Invariant UI):
| Variable | Value |
|----------|-------|
| `CVA_BACKEND_URL` | `http://consensus-verification-agents.railway.internal:8001` |
| `CVA_API_TOKEN` | (same as backend) |
| `NEXTAUTH_URL` | `https://invariant.dysrupt-ion.com` |
| `NEXTAUTH_SECRET` | (your secret) |
