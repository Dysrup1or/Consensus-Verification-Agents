# Dysruption CVA Dashboard

The frontend dashboard for the Consensus Verifier Agent (CVA).

## Stack
- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS + Custom Cyberpunk Theme
- **State**: React Hooks + WebSocket
- **Testing**: Jest (Unit) + Cypress (E2E)

## Getting Started

### Prerequisites
- Node.js 18+
- Python backend running (for real mode)

### Installation
```bash
npm install
```

### Running in Mock Mode (Development)
Run the UI with a built-in mock server that simulates the CVA pipeline events.
```bash
# Linux/Mac
USE_MOCK=true npm run dev

# Windows (PowerShell)
$env:USE_MOCK="true"; npm run dev
```
Visit `http://localhost:3000`.

### Running with Real Backend
1. Start the FastAPI backend:
   ```bash
   cd ../dysruption_cva
   uvicorn modules.api:app --reload
   ```
2. Start the UI:
   ```bash
   npm run dev
   ```

## Features
- **Real-time Status**: WebSocket connection to CVA backend.
- **Verdict Visualization**: 3-judge tribunal cards with revealable notes.
- **Veto Highlighting**: Pulsing red alert for security vetoes.
- **Patch Diff**: Syntax-highlighted unified diff viewer.
- **Spec View**: Live constitution invariant tracking.

## API & WebSocket Schemas

### WebSocket Events (`ws://localhost:8000/ws`)

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

**E2E Tests**
```bash
npm run cypress:open
```
