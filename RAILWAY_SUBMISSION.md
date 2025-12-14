# Railway Submission (CVA)

This repo is easiest to run on Railway as **two services**:
- `dysruption_cva` (FastAPI backend)
- `dysruption-ui` (Next.js UI)

## 1) Backend service (FastAPI)

**Service root directory**: `dysruption_cva`

**Build** (Nixpacks default): installs `requirements.txt`.

**Start command**:
- `bash start.sh`

`dysruption_cva/start.sh` binds to Railway’s `PORT` automatically.

**Required env vars (production)**
- `CVA_PRODUCTION=true`
- `CVA_API_TOKEN=<strong-random-token>`

**Recommended env vars**
- Provider keys as needed (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)

## 2) UI service (Next.js)

**Service root directory**: `dysruption-ui`

**Build command**:
- `npm run build`

**Start command**:
- `npm start`

`npm start` runs `node scripts/start.js`, which binds to Railway’s `PORT`.

**Required env vars (production)**
- `NEXTAUTH_URL=https://<your-ui-domain>`
- `NEXTAUTH_SECRET=<strong-random-secret>`
- OAuth provider credentials:
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
  - `GITHUB_ID` / `GITHUB_SECRET`

**Backend connectivity (UI → backend)**
- `CVA_BACKEND_URL=https://<your-backend-domain>`
- `CVA_API_TOKEN=<same token as backend>`

The UI uses a server-side proxy (`/api/cva/*`) to attach the backend token and avoid exposing it to browsers.

## 3) Ports and URLs

- Local dev backend port is documented as `8001`.
- On Railway, backend binds to `PORT` (dynamic).
- Do not hard-code Railway ports into code; use env vars.

## 4) Pre-push sanity

From repo root:
- `git diff`
- `cd dysruption-ui; npm test`
- `cd ../dysruption_cva; python -m pytest -q`

Then:
- `git add -A`
- `git commit -m "Add production auth gating, real cancellation, and OAuth UI auth"`
- `git push`
