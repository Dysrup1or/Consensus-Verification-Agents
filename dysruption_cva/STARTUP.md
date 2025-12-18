# CVA Startup Guide

## Recommended (local dev): use the repo root startup orchestrator

From the repo root:

```powershell
cd "c:\Users\alexe\Invariant"

# Start both backend + UI (attached)
.\startup.ps1

# Or start detached (background) and return control to your shell
.\startup.ps1 -Detached

# Stop services started by the script
.\startup.ps1 -Action Stop
```

Notes:
- This is intended for **local development only**.
- Production startup is handled by Railway service configuration (`dysruption_cva/start.sh` for API, `npm start` for UI) and should not rely on local PowerShell orchestration.

## Quick Start (TL;DR)

**Open two separate PowerShell windows:**

```powershell
# Window 1 - Backend
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva"
python -m uvicorn modules.api:app --host 0.0.0.0 --port 8001

# Window 2 - Frontend  
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui"
npm run dev
```

Then open: **http://localhost:3000**

---

## Startup Sequence (Verified & Tested)

### Step 1: Kill Existing Processes
```powershell
Get-Process -Name python,node -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
```

### Step 2: Start Backend (New Window)
```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva'; python -m uvicorn modules.api:app --host 0.0.0.0 --port 8001"
```

Wait for: `✅ Loaded .env` and `Uvicorn running on http://0.0.0.0:8001`

### Step 3: Start Frontend (New Window)
```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui'; npm run dev"
```

Wait for: `✓ Ready in X.Xs`

### Step 4: Verify Both Running
```powershell
netstat -ano | Select-String ":8001.*LISTENING|:3000.*LISTENING"
```

You should see both ports LISTENING.

---

## Connection Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Port 3000)                     │
│                  http://localhost:3000                      │
├─────────────────────────────────────────────────────────────┤
│  Connection Methods (in order of preference):               │
│                                                             │
│  1. WebSocket: ws://localhost:8001/ws/{run_id}             │
│     → Real-time updates, bidirectional                      │
│     → Falls back to HTTP polling if disconnected            │
│                                                             │
│  2. HTTP Polling: GET /status/{run_id} every 2 seconds      │
│     → Automatic fallback when WS fails                      │
│     → Ensures UI always gets updates                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (Port 8001)                      │
│                  http://localhost:8001                      │
├─────────────────────────────────────────────────────────────┤
│  Endpoints:                                                 │
│  • POST /run         - Start verification                   │
│  • GET  /status/{id} - Get run status                       │
│  • GET  /verdict/{id}- Get final verdict                    │
│  • GET  /runs        - List all runs                        │
│  • WS   /ws/{id}     - Real-time updates                    │
│  • GET  /docs        - Swagger UI                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites Checklist

### 1. Environment Variables (`.env`)
Ensure all API keys are set in `dysruption_cva/.env`:
- ✅ `GOOGLE_API_KEY` - For Gemini models (extraction, user proxy)
- ✅ `OPENAI_API_KEY` - For GPT-4o-mini (remediation)
- ✅ `ANTHROPIC_API_KEY` - For Claude (architect judge, synthesizer)
- ✅ `GROQ_API_KEY` - For Llama 3.3 70B (security judge)

### 2. Python Environment
```powershell
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)"
.\.venv\Scripts\Activate.ps1
pip install -r dysruption_cva/requirements.txt
```

### 3. Node.js Dependencies
```powershell
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui"
npm install
```

---

## Startup Sequence (Detailed)

### Step 1: Kill Any Existing Processes
```powershell
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Step 2: Verify Ports Are Free
```powershell
netstat -ano | Select-String ":8001"  # Should be empty
netstat -ano | Select-String ":3000"  # Should be empty
```

### Step 3: Start Backend (Port 8001)
**In a new PowerShell window:**
```powershell
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva"
python -m uvicorn modules.api:app --host 0.0.0.0 --port 8001
```

**Expected output:**
```
✅ Loaded .env from C:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva\.env
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     CVA API v1.1 starting up...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

### Step 4: Verify Backend Health
```powershell
Invoke-RestMethod -Uri "http://localhost:8001/docs" | Select-String "title"
# Should return: Dysruption CVA API - Swagger UI
```

### Step 5: Start Frontend (Port 3000)
**In another PowerShell window:**
```powershell
cd "c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui"
npm run dev
```

**Expected output:**
```
▲ Next.js 14.1.0
- Local:        http://localhost:3000
✓ Ready in X.Xs
```

### Step 6: Open Application
Navigate to: http://localhost:3000

---

## Verification Tests

### Test 1: API Health Check
```powershell
Invoke-RestMethod -Uri "http://localhost:8001/run" -Method POST `
  -ContentType "application/json" `
  -Body '{"target_dir":"C:/Users/alexe/Consensus Verifier Agent (CVA)/dysruption_cva/sample_project","spec_content":"All code must be secure."}'
```

### Test 2: Check Run Status
```powershell
# Replace RUN_ID with actual run ID from Test 1
Invoke-RestMethod -Uri "http://localhost:8001/status/RUN_ID" -Method GET
```

---

## Troubleshooting

### Backend Won't Start
1. **Port in use**: Kill existing process: `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8001).OwningProcess`
2. **Missing .env**: Ensure `.env` file exists with all API keys
3. **Python not found**: Activate venv: `.\.venv\Scripts\Activate.ps1`

### Frontend Won't Start
1. **Port in use**: Kill process on 3000
2. **Missing dependencies**: Run `npm install`
3. **Build errors**: Delete `.next` folder and restart

### API Errors
1. **"Model not found"**: Check `config.yaml` model names match provider's available models
2. **"API key invalid"**: Verify keys in `.env` are current
3. **"Connection refused"**: Ensure backend is running on 8001

---

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│   Frontend (3000)   │────▶│   Backend (8001)    │
│   Next.js + React   │◀────│   FastAPI + Uvicorn │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
             ┌──────────┐       ┌──────────┐       ┌──────────┐
             │ Anthropic│       │  Google  │       │   Groq   │
             │ (Claude) │       │ (Gemini) │       │ (Llama)  │
             └──────────┘       └──────────┘       └──────────┘
```

---

## LLM Model Configuration

| Role | Model | Provider | Purpose |
|------|-------|----------|---------|
| Architect Judge | claude-sonnet-4 | Anthropic | Logic, structure, efficiency |
| Security Judge | llama-3.3-70b | Groq | Vulnerabilities, OWASP risks |
| User Proxy Judge | gemini-2.0-flash | Google | Spec alignment, user intent |
| Extraction | gemini-2.0-flash | Google | Parse invariants from spec |
| Remediation | gpt-4o-mini | OpenAI | Generate code fixes |
| Synthesizer | claude-sonnet-4 | Anthropic | Create fix prompts |

---

*Last Updated: December 3, 2025*
