# Dysruption CVA Dashboard

The frontend dashboard for the Consensus Verifier Agent (CVA).

## Stack
- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS (dark, professional)
- **State**: React Hooks + WebSocket (with HTTP polling fallback)
- **Testing**: Jest (Unit)

## Getting Started

### Prerequisites
- Node.js 18+
- Python backend running (for real mode)

### Installation
```bash
npm install
```

### Running with Real Backend
1. Start the FastAPI backend:
   ```bash
   cd ../dysruption_cva
  # Local dev default is port 8001
  python -m uvicorn modules.api:app --reload --host 0.0.0.0 --port 8001
   ```
2. Start the UI:
   ```bash
   npm run dev
   ```

### Authentication (Google / GitHub)

The dashboard uses NextAuth and supports Google + GitHub OAuth.

- Copy `.env.example` to `.env.local` and fill:
  - `NEXTAUTH_SECRET`, `NEXTAUTH_URL`
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
  - `GITHUB_ID`, `GITHUB_SECRET`
- In production, the UI proxies requests to the backend and attaches `CVA_API_TOKEN` server-side.

Required backend settings in production:
- `CVA_PRODUCTION=true`
- `CVA_API_TOKEN=<same token the UI uses>`

## Features
- **Real-time Status**: WebSocket connection to CVA backend.
- **Verdict Visualization**: 3-judge tribunal cards with revealable notes.
- **Patch Diff**: Syntax-highlighted unified diff viewer.

## API & WebSocket Schemas

### WebSocket Events (`ws://localhost:8001/ws`)

**watcher:update**
```json
{
  "type": "watcher:update",
  "payload": {
    "status": "idle" | "watcher_detected" | "scanning",
    "files": 12,
    "lastChangeAt": "2025-12-02T20:01:00Z"
  }
}
```

**verdict:update**
```json
{
  "type": "verdict:update",
  "payload": {
    "runId": "run_20251202_2002",
    "stage": "static_analysis" | "llm_judges" | "patch_generation",
    "percent": 42,
    "partialVerdict": null
  }
}
```

**verdict:complete**
```json
{
  "type": "verdict:complete",
  "payload": {
    "runId": "run_20251202_2002",
    "result": "consensus_pass" | "consensus_fail",
    "summary": {
      "filesScanned": ["trading/strategy.py"],
      "pylintScore": 5.4,
      "banditFindings": [{"code": "B307","line":12,"message":"Use of eval()"}]
    },
    "judges": [
      {"name":"architect","model":"claude-4-sonnet","vote":"fail","confidence":0.91,"notes":"..."},
      {"name":"security","model":"deepseek-v3","vote":"veto","confidence":0.97,"notes":"..."},
      {"name":"user_proxy","model":"gemini-2.5-pro","vote":"pass","confidence":0.55,"notes":"..."}
    ],
    "patches": [
      {
        "file": "trading/strategy.py",
        "diffUnified": "@@ -10,7 +10,7 @@\n- result = eval(user_input)\n+ result = ast.literal_eval(user_input)\n",
        "generatedBy": "gpt-4o-mini"
      }
    ],
    "timestamp": "2025-12-02T20:05:00Z"
  }
}
```

## Testing

**Unit Tests**
```bash
npm test
```

## Railway deployment notes

Railway deploys the backend and UI as separate services (recommended):

- **Backend service**
  - Root directory: `dysruption_cva`
  - Start command: `bash start.sh`
  - Railway provides `PORT` automatically; `start.sh` binds to it.
  - Set env vars:
    - `CVA_PRODUCTION=true`
    - `CVA_API_TOKEN=...`

- **UI service**
  - Root directory: `dysruption-ui`
  - Build command: `npm run build`
  - Start command: `npm start` (binds to Railway `PORT`)
  - Set env vars:
    - `NEXTAUTH_URL=https://<your-ui-domain>`
    - `NEXTAUTH_SECRET=...`
    - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
    - `GITHUB_ID` / `GITHUB_SECRET`
    - `CVA_BACKEND_URL=...` (see “Hard to misconfigure: UI → API wiring”)
    - `CVA_API_TOKEN=...` (same token as backend)

## Hard to misconfigure: UI → API wiring

### 1) Use Railway service-to-service variable injection (recommended)

Goal: **avoid hand-typed hostnames** like `consensus-verification-agents.railway.internal`.

In Railway:
- Ensure you have two services in the same project:
  - Backend service (FastAPI)
  - UI service (Next.js)
- On the **UI service** → **Variables**:
  1. Click **New Variable** → **Reference** (or “Add Reference”).
  2. Pick the **Backend service** as the source.
  3. Select the backend’s `RAILWAY_PRIVATE_DOMAIN`.
  4. Name the resulting variable something obvious like `BACKEND_PRIVATE_DOMAIN`.
  5. Set `CVA_BACKEND_URL` to: `http://${BACKEND_PRIVATE_DOMAIN}`

Notes:
- Use `http://` for `*.railway.internal` private domains.
- Do **not** include a port (Railway private domain routes to the service port).

### 2) Add a deploy-time smoke check (fail fast)

This repo includes a GitHub Actions workflow that calls the UI’s diagnostics endpoint and fails the build if the UI cannot reach the backend:
- Workflow: `.github/workflows/ui-backend-smoke.yml`

Setup:
- In GitHub repo settings → **Secrets and variables** → **Actions** → **New repository secret**:
  - `UI_BASE_URL` = your deployed UI origin, e.g. `https://<your-ui-domain>`

What it checks:
- `GET /api/backend/diagnostics` on the UI service
- Ensures the probe to the backend root (`/`) is OK
- Prints the UI build identifiers so you can confirm the deployed commit
