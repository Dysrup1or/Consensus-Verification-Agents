<#
.SYNOPSIS
    CVA Development Environment Startup Script v2.0
.DESCRIPTION
    Bulletproof orchestration for FastAPI Backend + Next.js Frontend
    Runs services directly in terminal with full error visibility
.NOTES
    Author: CVA DevOps (10X Systems Engineer Edition)
    Version: 2.0
    
    USAGE: .\dev_start.ps1
           .\dev_start.ps1 -SkipBrowser        # Don't open browser
           .\dev_start.ps1 -Detached           # Start and exit (processes keep running)
    
    Features:
    - Direct process execution with log capture
    - Persistent logging to logs/ directory  
    - Robust HTTP health checks with retry
    - Graceful Ctrl+C shutdown (in attached mode)
    - Automatic port cleanup
#>

param(
    [switch]$SkipBrowser,
    [switch]$Detached
)

$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION
# ============================================================================
$BACKEND_PORT = 8001
$FRONTEND_PORT = 3000
$HEALTH_TIMEOUT_SECONDS = 60
$HEALTH_RETRY_INTERVAL = 2

# Resolve paths
$SCRIPT_ROOT = $PSScriptRoot
if (-not $SCRIPT_ROOT) { $SCRIPT_ROOT = Get-Location }

$BACKEND_DIR = Join-Path $SCRIPT_ROOT "dysruption_cva"
$FRONTEND_DIR = Join-Path $SCRIPT_ROOT "dysruption-ui"
$VENV_PYTHON = Join-Path $SCRIPT_ROOT ".venv\Scripts\python.exe"
$NODE_MODULES = Join-Path $FRONTEND_DIR "node_modules"
$LOG_DIR = Join-Path $SCRIPT_ROOT "logs"

# Process tracking
$script:BackendProcess = $null
$script:FrontendProcess = $null

# ============================================================================
# FUNCTIONS
# ============================================================================

function Write-Step {
    param([string]$Text)
    Write-Host "[" -NoNewline -ForegroundColor DarkGray
    Write-Host "*" -NoNewline -ForegroundColor Cyan
    Write-Host "] " -NoNewline -ForegroundColor DarkGray
    Write-Host $Text
}

function Write-OK {
    param([string]$Text)
    Write-Host "[" -NoNewline -ForegroundColor DarkGray
    Write-Host "+" -NoNewline -ForegroundColor Green
    Write-Host "] " -NoNewline -ForegroundColor DarkGray
    Write-Host $Text -ForegroundColor Green
}

function Write-Fail {
    param([string]$Text)
    Write-Host "[" -NoNewline -ForegroundColor DarkGray
    Write-Host "X" -NoNewline -ForegroundColor Red
    Write-Host "] " -NoNewline -ForegroundColor DarkGray
    Write-Host $Text -ForegroundColor Red
}

function Stop-PortProcesses {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -ne 0 }
        foreach ($procId in $pids) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "    Killed PID $procId on port $Port" -ForegroundColor Yellow
            } catch {}
        }
    }
}

function Test-ServiceHealth {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 60
    )
    
    $startTime = Get-Date
    $attempt = 0
    
    while ($true) {
        $attempt++
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        
        if ($elapsed -ge $TimeoutSeconds) {
            Write-Host ""
            return $false
        }
        
        try {
            $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host ""
                return $true
            }
        } catch {
            # Expected during startup
        }
        
        $remaining = [math]::Ceiling($TimeoutSeconds - $elapsed)
        Write-Host ("`r    Waiting for {0}... (attempt {1}, {2}s remaining)     " -f $ServiceName, $attempt, $remaining) -NoNewline -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
}

function Invoke-Cleanup {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Yellow
    
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Stop-Process -Id $script:FrontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    
    Stop-PortProcesses -Port $BACKEND_PORT
    Stop-PortProcesses -Port $FRONTEND_PORT
    
    Write-OK "Cleanup complete"
}

# ============================================================================
# BANNER
# ============================================================================

Clear-Host
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "           CVA Development Environment v2.0                          " -ForegroundColor Cyan
Write-Host "           Bulletproof Startup Protocol                               " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# PHASE 1: ENVIRONMENT VALIDATION
# ============================================================================

Write-Step "Phase 1: Environment Validation"

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Fail "Python venv not found: $VENV_PYTHON"
    Write-Host "    Fix: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}
Write-OK "Python venv OK"

if (-not (Test-Path $NODE_MODULES)) {
    Write-Fail "Node modules not found: $NODE_MODULES"
    Write-Host "    Fix: cd dysruption-ui && npm install" -ForegroundColor Yellow
    exit 1
}
Write-OK "Node modules OK"

if (-not (Test-Path $BACKEND_DIR)) {
    Write-Fail "Backend not found: $BACKEND_DIR"
    exit 1
}
Write-OK "Backend directory OK"

if (-not (Test-Path $FRONTEND_DIR)) {
    Write-Fail "Frontend not found: $FRONTEND_DIR"
    exit 1
}
Write-OK "Frontend directory OK"

# ============================================================================
# PHASE 2: PORT CLEANUP
# ============================================================================

Write-Host ""
Write-Step "Phase 2: Port Cleanup"
Stop-PortProcesses -Port $BACKEND_PORT
Stop-PortProcesses -Port $FRONTEND_PORT
Start-Sleep -Seconds 2
Write-OK "Ports $BACKEND_PORT and $FRONTEND_PORT cleared"

# ============================================================================
# PHASE 3: CREATE LOG DIRECTORY
# ============================================================================

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}

$BACKEND_LOG = Join-Path $LOG_DIR "backend.log"
$FRONTEND_LOG = Join-Path $LOG_DIR "frontend.log"

# ============================================================================
# PHASE 4: START BACKEND
# ============================================================================

Write-Host ""
Write-Step "Phase 3: Starting Backend (FastAPI on :$BACKEND_PORT)"

$script:BackendProcess = Start-Process -FilePath $VENV_PYTHON `
    -ArgumentList "-m", "uvicorn", "modules.api:app", "--host", "0.0.0.0", "--port", "$BACKEND_PORT" `
    -WorkingDirectory $BACKEND_DIR `
    -RedirectStandardOutput $BACKEND_LOG `
    -RedirectStandardError "$BACKEND_LOG.err" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "    Started PID: $($script:BackendProcess.Id)" -ForegroundColor DarkGray

# Wait for health
Write-Step "Phase 4: Backend Health Check"

$backendOK = Test-ServiceHealth -Url "http://localhost:$BACKEND_PORT/" -ServiceName "Backend" -TimeoutSeconds $HEALTH_TIMEOUT_SECONDS

if (-not $backendOK) {
    Write-Fail "Backend failed to start!"
    Write-Host ""
    Write-Host "    Error log:" -ForegroundColor Red
    if (Test-Path "$BACKEND_LOG.err") {
        Get-Content "$BACKEND_LOG.err" -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    }
    Invoke-Cleanup
    exit 1
}

Write-OK "Backend healthy at http://localhost:$BACKEND_PORT"

# ============================================================================
# PHASE 5: START FRONTEND
# ============================================================================

Write-Host ""
Write-Step "Phase 5: Starting Frontend (Next.js on :$FRONTEND_PORT)"

# npm requires cmd wrapper on Windows
$script:FrontendProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $FRONTEND_DIR `
    -RedirectStandardOutput $FRONTEND_LOG `
    -RedirectStandardError "$FRONTEND_LOG.err" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "    Started PID: $($script:FrontendProcess.Id)" -ForegroundColor DarkGray

# Wait for health
Write-Step "Phase 6: Frontend Health Check"

$frontendOK = Test-ServiceHealth -Url "http://localhost:$FRONTEND_PORT/" -ServiceName "Frontend" -TimeoutSeconds $HEALTH_TIMEOUT_SECONDS

if (-not $frontendOK) {
    Write-Fail "Frontend failed to start!"
    Write-Host ""
    Write-Host "    Error log:" -ForegroundColor Red
    if (Test-Path "$FRONTEND_LOG.err") {
        Get-Content "$FRONTEND_LOG.err" -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    }
    Invoke-Cleanup
    exit 1
}

Write-OK "Frontend healthy at http://localhost:$FRONTEND_PORT"

# ============================================================================
# PHASE 7: LAUNCH BROWSER
# ============================================================================

if (-not $SkipBrowser) {
    Write-Host ""
    Write-Step "Phase 7: Launching Browser"
    Start-Sleep -Seconds 1
    Start-Process "http://localhost:$FRONTEND_PORT"
    Write-OK "Browser launched"
}

# ============================================================================
# SUCCESS BANNER
# ============================================================================

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "                      CVA SYSTEM ONLINE                               " -ForegroundColor Green  
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend:   " -NoNewline -ForegroundColor DarkGray
Write-Host "http://localhost:$BACKEND_PORT" -ForegroundColor Cyan
Write-Host "  Frontend:  " -NoNewline -ForegroundColor DarkGray
Write-Host "http://localhost:$FRONTEND_PORT" -ForegroundColor Magenta
Write-Host "  API Docs:  " -NoNewline -ForegroundColor DarkGray
Write-Host "http://localhost:$BACKEND_PORT/docs" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Logs:      " -NoNewline -ForegroundColor DarkGray
Write-Host "$LOG_DIR" -ForegroundColor White
Write-Host ""
Write-Host "  Backend PID:  $($script:BackendProcess.Id)" -ForegroundColor DarkGray
Write-Host "  Frontend PID: $($script:FrontendProcess.Id)" -ForegroundColor DarkGray
Write-Host ""

# ============================================================================
# DETACHED MODE vs ATTACHED MODE
# ============================================================================

if ($Detached) {
    # Detached mode: just save PIDs and exit, processes keep running
    $pidFile = Join-Path $SCRIPT_ROOT ".cva_pids"
    "$($script:BackendProcess.Id),$($script:FrontendProcess.Id)" | Out-File -FilePath $pidFile -Encoding ASCII
    
    Write-Host "======================================================================" -ForegroundColor DarkGray
    Write-Host "  DETACHED MODE - Processes running in background" -ForegroundColor Yellow
    Write-Host "  Run .\dev_stop.ps1 to stop all services" -ForegroundColor DarkGray
    Write-Host "======================================================================" -ForegroundColor DarkGray
    Write-Host ""
    
    # Exit without cleanup
    exit 0
}

Write-Host "======================================================================" -ForegroundColor DarkGray
Write-Host "  Press Ctrl+C to stop all services" -ForegroundColor DarkGray
Write-Host "======================================================================" -ForegroundColor DarkGray
Write-Host ""

# ============================================================================
# MONITOR LOOP - Keep script running, watch for process death
# ============================================================================

try {
    while ($true) {
        # Check backend
        if ($script:BackendProcess.HasExited) {
            Write-Fail "Backend process died! Exit code: $($script:BackendProcess.ExitCode)"
            if (Test-Path "$BACKEND_LOG.err") {
                Get-Content "$BACKEND_LOG.err" -Tail 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            }
            break
        }
        
        # Check frontend
        if ($script:FrontendProcess.HasExited) {
            Write-Fail "Frontend process died! Exit code: $($script:FrontendProcess.ExitCode)"
            if (Test-Path "$FRONTEND_LOG.err") {
                Get-Content "$FRONTEND_LOG.err" -Tail 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            }
            break
        }
        
        Start-Sleep -Seconds 3
    }
} finally {
    Invoke-Cleanup
}
