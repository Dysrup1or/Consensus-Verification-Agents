# ============================================================
# CVA System Startup Script
# ============================================================
# Based on 12-Factor App principles:
# - Explicit dependencies
# - Config in environment
# - Fast startup / graceful shutdown
# ============================================================

param(
    [switch]$SkipPreflight,
    [switch]$MockMode,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ScriptDir = $PSScriptRoot
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DYSRUPTION CVA SYSTEM LAUNCHER" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# PREFLIGHT CHECKS
# ============================================================
if (-not $SkipPreflight) {
    Write-Host "[1/4] Running Preflight Checks..." -ForegroundColor Yellow
    
    $preflightResult = python "$ScriptDir\preflight.py"
    $preflightResult | ForEach-Object { Write-Host $_ }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Preflight failed. Use -SkipPreflight to bypass (not recommended)." -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "[1/4] Preflight Checks SKIPPED" -ForegroundColor DarkGray
}

# ============================================================
# ENVIRONMENT SETUP
# ============================================================
Write-Host "[2/4] Loading Environment..." -ForegroundColor Yellow

$envFile = "$ScriptDir\dysruption_cva\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
    Write-Host "  Loaded API keys from .env" -ForegroundColor Green
}
else {
    Write-Host "  Warning: .env file not found" -ForegroundColor Yellow
}

# ============================================================
# START BACKEND
# ============================================================
if (-not $FrontendOnly) {
    Write-Host "[3/4] Starting Backend (FastAPI on :8000)..." -ForegroundColor Yellow
    
    $backendCmd = "cd '$ScriptDir\dysruption_cva'; Write-Host 'CVA Backend Starting...' -ForegroundColor Cyan; uvicorn modules.api:app --reload --port 8001 --host 0.0.0.0 --timeout-keep-alive 300"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
    
    # Wait for backend to be ready
    Write-Host "  Waiting for backend..." -ForegroundColor DarkGray
    $maxAttempts = 15
    $attempt = 0
    do {
        Start-Sleep -Milliseconds 500
        $attempt++
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8001/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "  Backend ready!" -ForegroundColor Green
                break
            }
        }
        catch { }
    } while ($attempt -lt $maxAttempts)
    
    if ($attempt -ge $maxAttempts) {
        Write-Host "  Backend may still be starting..." -ForegroundColor Yellow
    }
}
else {
    Write-Host "[3/4] Backend SKIPPED (FrontendOnly mode)" -ForegroundColor DarkGray
}

# ============================================================
# START FRONTEND
# ============================================================
if (-not $BackendOnly) {
    Write-Host "[4/4] Starting Frontend (Next.js on :3000)..." -ForegroundColor Yellow
    
    $frontendDir = "$ScriptDir\dysruption-ui"
    
    # Check node_modules
    if (-not (Test-Path "$frontendDir\node_modules")) {
        Write-Host "  Installing dependencies (first run)..." -ForegroundColor Yellow
        Push-Location $frontendDir
        npm install
        Pop-Location
    }
    
    # Set mock mode if requested
    $envPrefix = ""
    if ($MockMode) {
        $envPrefix = '$env:NEXT_PUBLIC_USE_MOCK="true"; '
        Write-Host "  Mock Mode ENABLED" -ForegroundColor Magenta
    }
    
    $frontendCmd = "${envPrefix}cd '$frontendDir'; Write-Host 'CVA Frontend Starting...' -ForegroundColor Magenta; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
    
    Write-Host "  Frontend launching..." -ForegroundColor Green
}
else {
    Write-Host "[4/4] Frontend SKIPPED (BackendOnly mode)" -ForegroundColor DarkGray
}

# ============================================================
# SUMMARY
# ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CVA SYSTEM LAUNCHED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
if (-not $BackendOnly) {
    Write-Host "  Dashboard:  http://localhost:3000" -ForegroundColor Magenta
}
if (-not $FrontendOnly) {
    Write-Host "  API Docs:   http://localhost:8001/docs" -ForegroundColor Green
    Write-Host "  WebSocket:  ws://localhost:8001/ws" -ForegroundColor Green
}
Write-Host ""
Write-Host "  Options:" -ForegroundColor DarkGray
Write-Host "    -MockMode       Run frontend with mock data" -ForegroundColor DarkGray
Write-Host "    -BackendOnly    Only start FastAPI server" -ForegroundColor DarkGray
Write-Host "    -FrontendOnly   Only start Next.js dev server" -ForegroundColor DarkGray
Write-Host "    -SkipPreflight  Skip health checks (not recommended)" -ForegroundColor DarkGray
Write-Host ""
