<#
.SYNOPSIS
  Invariant (CVA) unified local startup orchestrator.

.DESCRIPTION
  Starts and validates the two moving parts of this repo:
  - Backend: FastAPI (dysruption_cva) on port 8001
  - Frontend: Next.js (dysruption-ui) on port 3000

  This script is designed for LOCAL DEVELOPMENT.
  Do not use it as a production process supervisor.

  Key properties (best-practice oriented):
  - Fail-fast validation (optional preflight)
  - Idempotent dependency checks (install only if missing)
  - Health checks with timeouts
  - Detached mode with PID file
  - Stop/status helpers

.USAGE
  # Start both services (attached)
  .\startup.ps1

  # Start both services (detached)
  .\startup.ps1 -Detached

  # Validate environment only (no servers)
  .\startup.ps1 -Action Validate

  # Stop services started via this script
  .\startup.ps1 -Action Stop

  # Show status
  .\startup.ps1 -Action Status

.NOTES
  Local-only policy: production should be handled by Railway (or another supervisor)
  with explicit logging, lifecycle, and retention policies.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
  [ValidateSet('Start', 'Stop', 'Status', 'Validate')]
  [string]$Action = 'Start',

  [int]$BackendPort = 8001,
  [int]$FrontendPort = 3000,

  [switch]$Detached,
  [switch]$SkipBrowser,

  [switch]$SkipPreflight,
  [switch]$FixPreflight,

  [switch]$BackendOnly,
  [switch]$FrontendOnly,

  # Local-only convenience flags
  [switch]$MockMode,
  [switch]$NoAuth,

  # Safety: if set, does not kill processes already bound to ports
  [switch]$NoPortCleanup,

  # If set, runs `npm install` when node_modules is missing
  [switch]$InstallFrontendDeps = $true,

  # If set, runs the UI gate suite (lint/typecheck/unit/madge/build/e2e)
  [switch]$RunGate
)

$ErrorActionPreference = 'Stop'

# ----------------------------
# Paths / constants
# ----------------------------
$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }

$BackendDir = Join-Path $RepoRoot 'dysruption_cva'
$FrontendDir = Join-Path $RepoRoot 'dysruption-ui'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$PidFile = Join-Path $RepoRoot '.invariant_pids'
$LogDir = Join-Path $RepoRoot 'logs'

$BackendLog = Join-Path $LogDir 'backend.log'
$FrontendLog = Join-Path $LogDir 'frontend.log'

$script:BackendProcess = $null
$script:FrontendProcess = $null

# ----------------------------
# Output helpers
# ----------------------------
function Write-Step([string]$Text) {
  Write-Host "[" -NoNewline -ForegroundColor DarkGray
  Write-Host "*" -NoNewline -ForegroundColor Cyan
  Write-Host "] " -NoNewline -ForegroundColor DarkGray
  Write-Host $Text
}

function Write-Ok([string]$Text) {
  Write-Host "[" -NoNewline -ForegroundColor DarkGray
  Write-Host "+" -NoNewline -ForegroundColor Green
  Write-Host "] " -NoNewline -ForegroundColor DarkGray
  Write-Host $Text -ForegroundColor Green
}

function Write-Warn([string]$Text) {
  Write-Host "[" -NoNewline -ForegroundColor DarkGray
  Write-Host "!" -NoNewline -ForegroundColor Yellow
  Write-Host "] " -NoNewline -ForegroundColor DarkGray
  Write-Host $Text -ForegroundColor Yellow
}

function Write-Fail([string]$Text) {
  Write-Host "[" -NoNewline -ForegroundColor DarkGray
  Write-Host "X" -NoNewline -ForegroundColor Red
  Write-Host "] " -NoNewline -ForegroundColor DarkGray
  Write-Host $Text -ForegroundColor Red
}

# ----------------------------
# Utility
# ----------------------------
function Resolve-Python {
  if (Test-Path -LiteralPath $VenvPython) { return $VenvPython }
  $py = Get-Command python -ErrorAction SilentlyContinue
  if ($py) { return $py.Path }
  return $null
}

function Ensure-LogDir {
  if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
  }
}

function Import-DotEnv([string]$EnvPath) {
  if (-not (Test-Path -LiteralPath $EnvPath)) { return }

  Get-Content -LiteralPath $EnvPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith('#')) { return }
    if ($line -match '^([^=]+)=(.*)$') {
      $name = $matches[1].Trim()
      $value = $matches[2]

      # Do not override values already set in the process environment.
      if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
      }
    }
  }
}

function Stop-PortProcesses([int]$Port) {
  if ($NoPortCleanup) {
    Write-Warn "Port cleanup disabled (-NoPortCleanup)."
    return
  }

  $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
  if (-not $connections) { return }

  $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -ne 0 }
  foreach ($procId in $pids) {
    if ($PSCmdlet.ShouldProcess("PID $procId", "Stop process bound to port $Port")) {
      try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
}

function Test-ServiceHealth([string]$Url, [string]$Name, [int]$TimeoutSeconds = 60) {
  $start = Get-Date
  $attempt = 0
  while ($true) {
    $attempt++
    $elapsed = ((Get-Date) - $start).TotalSeconds
    if ($elapsed -ge $TimeoutSeconds) { return $false }

    try {
      $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {
      # expected during startup
    }

    Start-Sleep -Seconds 2
  }
}

function Read-Pids {
  if (-not (Test-Path -LiteralPath $PidFile)) { return @() }
  $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $raw) { return @() }

  return $raw.Split(',') | ForEach-Object {
    $s = $_.Trim()
    if ($s -match '^\d+$') { [int]$s }
  } | Where-Object { $_ }
}

function Stop-FromPidFile {
  $pids = Read-Pids
  if (-not $pids -or $pids.Count -eq 0) {
    Write-Warn "No PID file found at $PidFile; falling back to port stop."
    return $false
  }

  foreach ($pid in $pids) {
    try {
      if ($PSCmdlet.ShouldProcess("PID $pid", 'Stop process')) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
      }
    } catch {}
  }

  try { Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue } catch {}
  return $true
}

# ----------------------------
# Validation actions
# ----------------------------
function Validate-Environment {
  Write-Step 'Validating repo structure...'
  if (-not (Test-Path -LiteralPath $BackendDir)) { throw "Backend directory not found: $BackendDir" }
  if (-not (Test-Path -LiteralPath $FrontendDir)) { throw "Frontend directory not found: $FrontendDir" }
  Write-Ok 'Repo directories OK'

  $python = Resolve-Python
  if (-not $python) {
    throw 'Python not found. Create a venv at .venv or install python on PATH.'
  }
  Write-Ok "Python: $python"

  # Load env for local runs (best-effort)
  Import-DotEnv (Join-Path $BackendDir '.env')
  Import-DotEnv (Join-Path $FrontendDir '.env.local')

  if (-not $SkipPreflight) {
    Write-Step 'Running Python preflight...'
    $args = @('preflight.py')
    if ($FixPreflight) { $args += '--fix' }

    & $python @args
    if ($LASTEXITCODE -ne 0) {
      throw 'Preflight failed.'
    }
    Write-Ok 'Preflight OK'
  } else {
    Write-Warn 'Preflight skipped (-SkipPreflight).'
  }

  $nodeModules = Join-Path $FrontendDir 'node_modules'
  if (-not (Test-Path -LiteralPath $nodeModules)) {
    if ($InstallFrontendDeps) {
      Write-Step 'Installing frontend dependencies (node_modules missing)...'
      Push-Location $FrontendDir
      try {
        cmd.exe /c "npm install"
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
      } finally {
        Pop-Location
      }
      Write-Ok 'Frontend deps installed'
    } else {
      Write-Warn 'node_modules missing; set -InstallFrontendDeps to install.'
    }
  } else {
    Write-Ok 'Frontend deps present'
  }

  if ($RunGate) {
    Write-Step 'Running UI gate suite (may take a while)...'
    Push-Location $FrontendDir
    try {
      cmd.exe /c "npm run gate"
      if ($LASTEXITCODE -ne 0) { throw 'npm run gate failed' }
    } finally {
      Pop-Location
    }
    Write-Ok 'Gate suite OK'
  }
}

# ----------------------------
# Start actions
# ----------------------------
function Start-Backend {
  $python = Resolve-Python
  if (-not $python) { throw 'Python not found.' }

  Ensure-LogDir

  Stop-PortProcesses -Port $BackendPort

  Write-Step "Starting backend (:$BackendPort)..."
  $backendStartArgs = @{
    FilePath               = $python
    ArgumentList           = @('-m', 'uvicorn', 'modules.api:app', '--host', '0.0.0.0', '--port', "$BackendPort", '--reload')
    WorkingDirectory       = $BackendDir
    RedirectStandardOutput = $BackendLog
    RedirectStandardError  = "$BackendLog.err"
    PassThru               = $true
    WindowStyle            = 'Hidden'
  }

  $script:BackendProcess = Start-Process @backendStartArgs

  Write-Ok "Backend PID $($script:BackendProcess.Id)"

  Write-Step 'Backend health check...'
  $ok = Test-ServiceHealth -Url "http://localhost:$BackendPort/" -Name 'Backend' -TimeoutSeconds 60
  if (-not $ok) {
    Write-Fail 'Backend failed health check.'
    if (Test-Path -LiteralPath "$BackendLog.err") {
      Get-Content -LiteralPath "$BackendLog.err" -Tail 25 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    }
    throw 'Backend did not become healthy.'
  }

  Write-Ok "Backend healthy: http://localhost:$BackendPort/docs"
}

function Start-Frontend {
  Ensure-LogDir

  Stop-PortProcesses -Port $FrontendPort

  Write-Step "Starting frontend (:$FrontendPort)..."

  # Ensure node_modules exists
  $nodeModules = Join-Path $FrontendDir 'node_modules'
  if (-not (Test-Path -LiteralPath $nodeModules)) {
    if ($InstallFrontendDeps) {
      Write-Step 'Installing frontend dependencies (node_modules missing)...'
      Push-Location $FrontendDir
      try {
        cmd.exe /c "npm install"
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
      } finally {
        Pop-Location
      }
      Write-Ok 'Frontend deps installed'
    } else {
      throw 'node_modules missing and -InstallFrontendDeps disabled.'
    }
  }

  # npm requires cmd wrapper on Windows. Use cmd.exe env var injection to avoid quoting pitfalls.
  $cmdParts = @()
  if ($MockMode) { $cmdParts += 'set NEXT_PUBLIC_USE_MOCK=true' }
  if ($NoAuth) { $cmdParts += 'set CVA_REQUIRE_AUTH=false' }
  $cmdParts += ('cd /d "{0}"' -f $FrontendDir)
  $cmdParts += 'npm run dev'
  $cmdLine = $cmdParts -join ' & '

  $frontendStartArgs = @{
    FilePath               = 'cmd.exe'
    ArgumentList           = @('/c', $cmdLine)
    WorkingDirectory       = $FrontendDir
    RedirectStandardOutput = $FrontendLog
    RedirectStandardError  = "$FrontendLog.err"
    PassThru               = $true
    WindowStyle            = 'Hidden'
  }

  $script:FrontendProcess = Start-Process @frontendStartArgs

  Write-Ok "Frontend PID $($script:FrontendProcess.Id)"

  Write-Step 'Frontend health check...'
  $ok = Test-ServiceHealth -Url "http://localhost:$FrontendPort/login" -Name 'Frontend' -TimeoutSeconds 90
  if (-not $ok) {
    Write-Fail 'Frontend failed health check.'
    if (Test-Path -LiteralPath "$FrontendLog.err") {
      Get-Content -LiteralPath "$FrontendLog.err" -Tail 25 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    }
    throw 'Frontend did not become healthy.'
  }

  Write-Ok "Frontend healthy: http://localhost:$FrontendPort"
}

function Write-Summary {
  Write-Host ''
  Write-Host '======================================================================' -ForegroundColor Green
  Write-Host '                      INVARIANT SYSTEM ONLINE                         ' -ForegroundColor Green
  Write-Host '======================================================================' -ForegroundColor Green
  Write-Host "  Frontend:  http://localhost:$FrontendPort" -ForegroundColor Magenta
  Write-Host "  Backend:   http://localhost:$BackendPort" -ForegroundColor Cyan
  Write-Host "  API Docs:  http://localhost:$BackendPort/docs" -ForegroundColor Yellow
  Write-Host "  Logs:      $LogDir" -ForegroundColor DarkGray
  if ($script:BackendProcess) { Write-Host "  Backend PID:  $($script:BackendProcess.Id)" -ForegroundColor DarkGray }
  if ($script:FrontendProcess) { Write-Host "  Frontend PID: $($script:FrontendProcess.Id)" -ForegroundColor DarkGray }
  Write-Host ''
}

function Save-PidsAndExit {
  Ensure-LogDir
  $pids = @()
  if ($script:BackendProcess) { $pids += $script:BackendProcess.Id }
  if ($script:FrontendProcess) { $pids += $script:FrontendProcess.Id }

  if ($pids.Count -gt 0) {
    $pids -join ',' | Out-File -FilePath $PidFile -Encoding ASCII
    Write-Ok "Saved PIDs to $PidFile"
  }

  Write-Warn 'Detached mode: services running in background.'
  Write-Host "Stop with: .\startup.ps1 -Action Stop" -ForegroundColor DarkGray
  exit 0
}

function Attached-MonitorLoop {
  Write-Host '======================================================================' -ForegroundColor DarkGray
  Write-Host '  Press Ctrl+C to stop all services' -ForegroundColor DarkGray
  Write-Host '======================================================================' -ForegroundColor DarkGray

  try {
    while ($true) {
      if ($script:BackendProcess -and $script:BackendProcess.HasExited) {
        Write-Fail "Backend died (exit $($script:BackendProcess.ExitCode))."
        break
      }
      if ($script:FrontendProcess -and $script:FrontendProcess.HasExited) {
        Write-Fail "Frontend died (exit $($script:FrontendProcess.ExitCode))."
        break
      }
      Start-Sleep -Seconds 3
    }
  } finally {
    Write-Step 'Stopping services...'
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
      try { Stop-Process -Id $script:FrontendProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
      try { Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
    }

    Stop-PortProcesses -Port $BackendPort
    Stop-PortProcesses -Port $FrontendPort

    Write-Ok 'Stopped.'
  }
}

# ----------------------------
# Main dispatcher
# ----------------------------
switch ($Action) {
  'Validate' {
    Validate-Environment
    Write-Ok 'Validation complete.'
    exit 0
  }

  'Status' {
    Write-Step 'Status'
    $pids = Read-Pids
    if ($pids.Count -gt 0) {
      Write-Ok "PID file: $PidFile -> $($pids -join ', ')"
    } else {
      Write-Warn "No PID file at $PidFile"
    }

    try {
      $backendOk = Test-ServiceHealth -Url "http://localhost:$BackendPort/" -Name 'Backend' -TimeoutSeconds 2
      Write-Host "Backend health:  $backendOk" -ForegroundColor DarkGray
    } catch {}

    try {
      $frontOk = Test-ServiceHealth -Url "http://localhost:$FrontendPort/login" -Name 'Frontend' -TimeoutSeconds 2
      Write-Host "Frontend health: $frontOk" -ForegroundColor DarkGray
    } catch {}

    exit 0
  }

  'Stop' {
    Write-Step 'Stopping Invariant services'

    $stopped = Stop-FromPidFile
    if (-not $stopped) {
      Stop-PortProcesses -Port $BackendPort
      Stop-PortProcesses -Port $FrontendPort
    }

    Write-Ok 'Stop complete.'
    exit 0
  }

  'Start' {
    Validate-Environment

    # Load env files (best-effort) for the started processes.
    Import-DotEnv (Join-Path $BackendDir '.env')
    Import-DotEnv (Join-Path $FrontendDir '.env.local')

    if (-not $FrontendOnly) { Start-Backend }
    if (-not $BackendOnly) { Start-Frontend }

    Write-Summary

    if (-not $SkipBrowser -and -not $BackendOnly) {
      Start-Process "http://localhost:$FrontendPort"
    }

    if ($Detached) { Save-PidsAndExit }

    Attached-MonitorLoop
  }
}
