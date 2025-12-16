# Railway Private Networking: Complete Fix Guide

## The Problem

Your UI shows `CVA_BACKEND_URL=NOT SET` even though you configured it in Railway.

## Root Causes Identified

### 1. Missing Reference Variable Syntax
You're pasting a literal URL instead of using Railway's reference variable system.

### 2. PORT Not Explicitly Defined on Backend
Railway's `${{service.PORT}}` only resolves to a **manually set PORT variable**, NOT the runtime injected PORT.

### 3. 402 Error = Billing Issue
A 402 error means Railway credit/payment issue. Check: https://railway.app/account/billing

---

## THE FIX: Step-by-Step

### Step 1: Add PORT Variable to Backend Service

**In Railway Dashboard → Consensus-Verification-Agents → Variables:**

Add a new variable:
```
PORT = 8001
```

> ⚠️ This is CRITICAL. Without this, reference variables cannot resolve the port.

### Step 2: Set CVA_BACKEND_URL Using Reference Variables

**In Railway Dashboard → Invariant UI → Variables:**

Delete the current `CVA_BACKEND_URL` and add it with this EXACT syntax:

```
CVA_BACKEND_URL = http://${{Consensus-Verification-Agents.RAILWAY_PRIVATE_DOMAIN}}:${{Consensus-Verification-Agents.PORT}}
```

> **IMPORTANT:** The service name must match EXACTLY including case and hyphens.
> Use the autocomplete dropdown in Railway's variable editor to get the correct name.

### Step 3: Verify Backend is Binding Correctly

Your backend's `start.sh` should have:
```bash
HOST="::"
```
This enables IPv6 binding for Railway's private network.

### Step 4: Deploy Both Services

After making these changes:
1. Click "Deploy Changes" on the Backend service
2. Click "Deploy Changes" on the UI service
3. Wait for both deployments to complete

---

## Alternative: Use Public Domain (If Private Networking Continues to Fail)

If private networking still doesn't work, use the public domain as a fallback:

**In Railway Dashboard → Invariant UI → Variables:**
```
CVA_BACKEND_URL = https://invariant-api-production.up.railway.app
```

This bypasses private networking entirely but works reliably.

---

## Verification Checklist

After deployment, check the UI service logs. You should see:
```
[start.js] CVA_BACKEND_URL=http://consensus-verification-agents.railway.internal:8001
```

If you still see `NOT SET`, the reference variable didn't resolve. Check:
- [ ] Backend service has `PORT=8001` variable set manually
- [ ] Service name in reference matches exactly (case-sensitive!)
- [ ] Both services are in the SAME Railway environment
- [ ] You clicked "Deploy Changes" after adding variables

---

## Railway Reference Variable Syntax

| Purpose | Syntax |
|---------|--------|
| Reference another service's variable | `${{ServiceName.VAR_NAME}}` |
| Reference shared variable | `${{shared.VAR_NAME}}` |
| Reference same service variable | `${{VAR_NAME}}` |

### Common Railway-Provided Variables
- `RAILWAY_PRIVATE_DOMAIN` - Internal DNS name (e.g., `service.railway.internal`)
- `RAILWAY_PUBLIC_DOMAIN` - Public domain if generated
- `PORT` - **Must be set manually for reference variables to work!**

---

## 402 Payment Required Error

This is a billing issue, not a networking issue:

1. Go to https://railway.app/account/billing
2. Add credits or upgrade to Hobby plan ($5/month)
3. Free tier has limited execution hours

---

## Quick Reference: Correct Configuration

### Backend Service (Consensus-Verification-Agents) Variables:
```
PORT = 8001
CVA_API_TOKEN = your-secure-token-here
DATABASE_URL = (your database URL)
```

### UI Service (Invariant UI) Variables:
```
CVA_BACKEND_URL = http://${{Consensus-Verification-Agents.RAILWAY_PRIVATE_DOMAIN}}:${{Consensus-Verification-Agents.PORT}}
CVA_API_TOKEN = (same token as backend)
NEXTAUTH_URL = https://invariant.dysrupt-ion.com
NEXTAUTH_SECRET = (your secret)
```

---

## Debug Commands (Railway CLI)

If you have Railway CLI installed:

```bash
# See resolved variables for a service
railway variables --service "Consensus-Verification-Agents"

# Run a command with Railway environment
railway run --service "Invariant UI" -- node -e "console.log(process.env.CVA_BACKEND_URL)"
```
