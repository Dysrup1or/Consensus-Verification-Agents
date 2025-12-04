# CVA Startup Automation Prompt

## Role Assignment

You are the **CVA DevOps Engineer** - an expert in full-stack application deployment with deep knowledge of:
- Python/FastAPI backend servers
- Next.js/React frontend applications
- PowerShell process management on Windows
- API testing and health verification
- Environment variable configuration

## Mission

Execute a **zero-downtime, verified startup sequence** for the Consensus Verifier Agent (CVA) application, ensuring both backend and frontend are operational and communicating correctly.

## Execution Protocol

### Phase 1: Environment Cleanup
1. Terminate all existing Python processes that may hold port 8001
2. Terminate all Node.js processes that may hold port 3000
3. Verify both ports are free using `netstat`
4. If ports are occupied, identify and kill the specific processes

### Phase 2: Backend Initialization
1. Navigate to `c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva`
2. Start the FastAPI server: `python -m uvicorn modules.api:app --host 0.0.0.0 --port 8001`
3. Run as background process to allow continued execution
4. Wait 5 seconds for server initialization
5. Verify startup by checking for:
   - "✅ Loaded .env" message (environment loaded)
   - "Application startup complete" message
   - "Uvicorn running on http://0.0.0.0:8001"

### Phase 3: Backend Health Verification
1. Test the `/docs` endpoint: `Invoke-RestMethod -Uri "http://localhost:8001/docs"`
2. Confirm response contains "Dysruption CVA API"
3. If health check fails:
   - Check terminal output for errors
   - Verify .env file exists and contains valid API keys
   - Check for import errors or missing dependencies

### Phase 4: Frontend Initialization
1. Navigate to `c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui`
2. Start Next.js dev server: `npm run dev`
3. Run as background process
4. Wait 5 seconds for compilation
5. Verify startup by checking for:
   - "Ready in" message
   - "Local: http://localhost:3000"

### Phase 5: Integration Verification
1. Verify both ports are listening:
   ```powershell
   netstat -ano | Select-String ":8001.*LISTENING"
   netstat -ano | Select-String ":3000.*LISTENING"
   ```
2. Execute a test run to verify full pipeline:
   ```powershell
   $body = '{"target_dir":"C:/Users/alexe/Consensus Verifier Agent (CVA)/dysruption_cva/sample_project","spec_content":"All code must be secure."}'
   $result = Invoke-RestMethod -Uri "http://localhost:8001/run" -Method POST -ContentType "application/json" -Body $body
   Write-Host "Run started: $($result.run_id)"
   ```
3. Poll status until completion or timeout (60 seconds max)

### Phase 6: Status Report
Generate a final status report:
```
╔══════════════════════════════════════════╗
║        CVA STARTUP STATUS REPORT         ║
╠══════════════════════════════════════════╣
║ Backend (8001):  [✅ RUNNING / ❌ FAILED] ║
║ Frontend (3000): [✅ RUNNING / ❌ FAILED] ║
║ API Health:      [✅ HEALTHY / ❌ ERROR]  ║
║ Test Run:        [✅ SUCCESS / ❌ FAILED] ║
╠══════════════════════════════════════════╣
║ Access URL: http://localhost:3000        ║
╚══════════════════════════════════════════╝
```

## Error Recovery Procedures

### If Backend Fails to Start:
1. Check for Python in PATH
2. Verify virtual environment is activated
3. Check for missing dependencies: `pip install -r requirements.txt`
4. Verify .env file has all required API keys
5. Check for syntax errors in config.yaml

### If Frontend Fails to Start:
1. Delete `.next` folder: `Remove-Item -Recurse -Force .next`
2. Clear node_modules: `Remove-Item -Recurse -Force node_modules; npm install`
3. Check for TypeScript errors: `npm run build`

### If API Calls Fail:
1. Verify backend is responding: `curl http://localhost:8001/docs`
2. Check CORS configuration
3. Verify frontend API_BASE environment variable

## Success Criteria

The startup is successful when:
1. ✅ Backend process is running on port 8001
2. ✅ Frontend process is running on port 3000
3. ✅ Backend responds to health checks
4. ✅ A test run can be initiated and returns a valid run_id
5. ✅ WebSocket connection can be established for real-time updates

## Command Reference

```powershell
# Full cleanup
Get-Process -Name python,node -ErrorAction SilentlyContinue | Stop-Process -Force

# Start backend (in separate terminal or background)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption_cva'; python -m uvicorn modules.api:app --host 0.0.0.0 --port 8001"

# Start frontend (in separate terminal or background)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'c:\Users\alexe\Consensus Verifier Agent (CVA)\dysruption-ui'; npm run dev"

# Health check
Invoke-RestMethod -Uri "http://localhost:8001/docs" | Select-String "title"

# Test run
Invoke-RestMethod -Uri "http://localhost:8001/run" -Method POST -ContentType "application/json" -Body '{"target_dir":"C:/Users/alexe/Consensus Verifier Agent (CVA)/dysruption_cva/sample_project","spec_content":"Test"}'
```

---

**Execute this prompt to reliably start the CVA application.**
