# Invariant (CVA) — Idiot‑Proof Railway Setup (Prod + Staging)

This guide is optimized for your current repo layout and runtime behavior:
- UI: Next.js + NextAuth (root directory: `dysruption-ui`)
- API: FastAPI (root directory: `dysruption_cva`)
- The UI proxies all backend calls via `/api/cva/*` and attaches `CVA_API_TOKEN` server‑side.
- In production (`NODE_ENV=production` on Railway), the proxy requires a valid NextAuth session.

Goal:
- Publicly expose ONLY the UI domains:
  - `https://invariant.dysrupt-ion.com`
  - `https://staging.invariant.dysrupt-ion.com`
- Keep the backend private (no public domain), reachable only from the UI service via Railway private networking.

CRITICAL (to get a green build):
- The UI must run as a server app. This repo uses NextAuth + App Router API routes (`/api/auth/*`, `/api/cva/*`).
- Do not use static export mode. In `dysruption-ui/next.config.js`, `output: 'export'` will break API routes and can cause Railway build/start failures.

---

## 0) What you should have before starting

- Cloudflare DNS for the UI subdomains already pointing at Railway and showing “active”.
- A Railway Project for Invariant with two Environments:
  - `production`
  - `staging`

If you currently have separate Railway projects for prod/staging, stop and consolidate: **one project + two environments** is what makes Shared Variables actually helpful.

---

## 1) Create the two Railway services (per environment)

In the **same Railway Project**:

### Service A — Backend API (FastAPI)
- Name: `invariant-api`
- Source: GitHub repo
- Root Directory: `dysruption_cva`
- Start Command: `bash start.sh`
  - This script binds to Railway’s dynamic `PORT`.

Build command (this is where your log is failing):
- Do NOT set the Railway “Build Command” to `requirements.txt`.
- Either leave Build Command blank (recommended; let Nixpacks run pip install), or set it explicitly to:
  - `pip install -r requirements.txt`

If you see `sh: 1: requirements.txt: not found` or `process "sh -c requirements.txt"`, it means Railway tried to EXECUTE a command named `requirements.txt` (misconfiguration) and/or your root directory is not `dysruption_cva`.

Networking (critical):
- Do **not** attach a public custom domain to this service.
- Use Railway’s **private/internal URL** for service-to-service communication.

### Service B — UI (Next.js)
- Name: `invariant-ui`
- Source: GitHub repo
- Root Directory: `dysruption-ui`
- Build Command: `npm run build`
- Start Command: `npm start`

Build stability (recommended):
- Set Node explicitly for this service (Next 14 is happiest on Node 20):
  - `NIXPACKS_NODE_VERSION=20`

TypeScript build requirement (this repo):
- `dysruption-ui/tsconfig.json` must have a modern `target` (default TS target can be too old and break builds).
  - Recommended: `target: ES2017`.

Domains:
- Attach custom domains to the **UI** service only:
  - Production environment: `invariant.dysrupt-ion.com`
  - Staging environment: `staging.invariant.dysrupt-ion.com`

---

## 2) Shared Variables (set once, used by both services)

In Railway:
Project → Variables → **Shared Variables**.

Set these **per environment** (production values in Production env, staging values in Staging env).

### Required Shared Variables (recommended)

- `CVA_API_TOKEN`
  - Production: strong random secret
  - Staging: different strong random secret
  - Must match between UI and API for the same environment.

- `CVA_BACKEND_URL`
  - Must be the backend’s **private/internal URL**, not the public Railway domain.
  - Example shape (don’t guess; copy from Railway UI): `http(s)://<private-backend-host>`
  - No trailing slash (the UI already strips trailing `/`, but keep it clean).

- `CVA_PRODUCTION`
  - Production env: `true`
  - Staging env: `true`
  - This enables production behavior in the backend.

Backend build stability (recommended):
- Set Python explicitly for the backend service:
  - `NIXPACKS_PYTHON_VERSION=3.11`

Security note: putting these in Shared Variables is safe and intentional because both services need them.

---

## 3) UI Variables (UI-only, but you *can* still set as Shared)

NextAuth and OAuth credentials are only used by the UI, but you asked to use Shared Variables to simplify.

Recommended (safer): set these at **Service → Variables** for `invariant-ui` only.

Simplest (what you asked for): set these as **Shared Variables** (the backend will ignore them).

### Required for `invariant-ui`

- `NEXTAUTH_URL`
  - Production env: `https://invariant.dysrupt-ion.com`
  - Staging env: `https://staging.invariant.dysrupt-ion.com`

- `NEXTAUTH_SECRET`
  - Production env: strong random secret
  - Staging env: different strong random secret

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

- `GITHUB_ID`
- `GITHUB_SECRET`

Optional:
- `CVA_REQUIRE_AUTH=true`
  - Only needed if you want to force auth in non-production.
  - Railway is already `NODE_ENV=production`, so auth is required anyway.

---

## 4) Backend Variables (backend-only)

These can be set as Shared Variables too if you want “one place”, but typically belong on the backend service.

- Provider keys as needed:
  - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.

Your backend `/` endpoint reports whether at least one common provider key exists.

---

## 5) Wiring the private backend URL (most common failure)

The UI proxy uses:
- `CVA_BACKEND_URL` (defaults to `http://localhost:8001` if missing)
- `CVA_API_TOKEN` (sent as `Authorization: Bearer ...`)

**Correct setup**:
1) Open the `invariant-api` service in Railway.
2) Find its **Private / Internal / Service-to-service URL** (Railway UI wording varies).
3) Copy that URL.
4) Paste it into `CVA_BACKEND_URL` in the same environment.

If `CVA_BACKEND_URL` points to:
- `http://localhost:8001` → it will fail on Railway.
- a public Railway domain → it may “work” but violates “backend hidden” and can break with auth/CORS assumptions.

---

## 6) OAuth provider console entries (exact URLs)

Your app uses NextAuth callbacks at:
- Google: `/api/auth/callback/google`
- GitHub: `/api/auth/callback/github`

### Google OAuth
Authorized JavaScript origins:
- `https://invariant.dysrupt-ion.com`
- `https://staging.invariant.dysrupt-ion.com`

Authorized redirect URIs:
- `https://invariant.dysrupt-ion.com/api/auth/callback/google`
- `https://staging.invariant.dysrupt-ion.com/api/auth/callback/google`

### GitHub OAuth
Best practice: **two OAuth apps** (GitHub often only allows one callback URL per app).

- Invariant PROD GitHub OAuth App
  - Homepage: `https://invariant.dysrupt-ion.com`
  - Callback: `https://invariant.dysrupt-ion.com/api/auth/callback/github`

- Invariant STAGING GitHub OAuth App
  - Homepage: `https://staging.invariant.dysrupt-ion.com`
  - Callback: `https://staging.invariant.dysrupt-ion.com/api/auth/callback/github`

---

## 6.5) Get it live first (before OAuth)

If Railway is currently failing builds, use this order to get to “live” fastest:

1) Fix UI server-mode requirement
   - Confirm `dysruption-ui/next.config.js` does not set `output: 'export'`.

2) Deploy backend first
   - Set (in the correct environment):
     - `CVA_PRODUCTION=true`
     - `CVA_API_TOKEN=<token>`
   - Deploy `invariant-api` and confirm it reaches “Running”.

3) Deploy UI with the minimum runtime secrets
   - Set (in the correct environment):
     - `NEXTAUTH_URL` (must match the public domain exactly)
     - `NEXTAUTH_SECRET`
   - Deploy `invariant-ui`.
   - Verify you can load:
     - `https://invariant.dysrupt-ion.com/login`
     - `https://staging.invariant.dysrupt-ion.com/login`

4) Wire UI → backend privately
   - Set (in the correct environment):
     - `CVA_BACKEND_URL=<backend private/internal URL>`
     - `CVA_API_TOKEN=<same token as backend>`
   - Redeploy `invariant-ui`.

Only after steps 1–4 are green should you configure Google/GitHub keys.

---

## 7) “It’s live but not working” debug checklist (fast)

### A) UI is up
- Visit:
  - `https://invariant.dysrupt-ion.com/login`
  - `https://staging.invariant.dysrupt-ion.com/login`
- If the page 500s:
  - check `invariant-ui` logs for missing `NEXTAUTH_SECRET` or bad `NEXTAUTH_URL`.

### B) OAuth is configured
- On `/login`, you should see Google/GitHub options.
- If providers are missing:
  - confirm the env vars exist (the UI only enables providers if the env vars are set).

### C) UI can reach backend privately
- After signing in, trigger any dashboard action that calls `/api/cva/*`.
- If you see “Backend connection failed” alerts:
  - verify `CVA_BACKEND_URL` is set to the backend’s private URL for that environment.
  - verify `CVA_API_TOKEN` matches between UI and API.

### D) Backend actually started
- Check `invariant-api` logs for uvicorn bind errors.
- Confirm it binds to `0.0.0.0:$PORT` (handled by `start.sh`).

### E) Railway “Build failed” quick fixes

1) UI configured as static export
  - Fix: ensure `dysruption-ui/next.config.js` does not set `output: 'export'`.

2) Wrong Node version
  - Fix: set `NIXPACKS_NODE_VERSION=20` on the UI service.

3) Wrong Python version
  - Fix: set `NIXPACKS_PYTHON_VERSION=3.11` on the backend service.

4) Root directory mismatch
  - UI root dir must be `dysruption-ui`.
  - Backend root dir must be `dysruption_cva`.

---

## 8) Optimal default variable layout (copy/paste)

Use this structure to minimize mistakes.

Shared Variables (Production env):
- `CVA_PRODUCTION=true`
- `CVA_API_TOKEN=<prod-token>`
- `CVA_BACKEND_URL=<prod-private-backend-url>`
- `NEXTAUTH_URL=https://invariant.dysrupt-ion.com`
- `NEXTAUTH_SECRET=<prod-nextauth-secret>`
- `GOOGLE_CLIENT_ID=<prod>`
- `GOOGLE_CLIENT_SECRET=<prod>`
- `GITHUB_ID=<prod>`
- `GITHUB_SECRET=<prod>`

Shared Variables (Staging env):
- `CVA_PRODUCTION=true`
- `CVA_API_TOKEN=<staging-token>`
- `CVA_BACKEND_URL=<staging-private-backend-url>`
- `NEXTAUTH_URL=https://staging.invariant.dysrupt-ion.com`
- `NEXTAUTH_SECRET=<staging-nextauth-secret>`
- `GOOGLE_CLIENT_ID=<staging>`
- `GOOGLE_CLIENT_SECRET=<staging>`
- `GITHUB_ID=<staging>`
- `GITHUB_SECRET=<staging>`

Provider keys (recommend service-scoped, but shared is OK):
- `OPENAI_API_KEY` etc.

---

## 9) Two rules that prevent 90% of outages

1) `NEXTAUTH_URL` must exactly match the user-facing domain for that environment.
2) `CVA_BACKEND_URL` must be the backend **private** URL for that environment.
