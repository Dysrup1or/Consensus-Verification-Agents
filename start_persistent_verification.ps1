<# Persistent Verification Daemon Starter

This script starts the layered verification daemon for continuous
constitutional verification of your codebase.

Features:
- Layered approach: cheap regex first, expensive LLM only if needed
- Git diff detection for incremental scanning
- Configurable thresholds

Usage:
    .\start_persistent_verification.ps1
    .\start_persistent_verification.ps1 -RepoPath "C:\path\to\repo"
    .\start_persistent_verification.ps1 -NoLLM  # Quick scan only
#>

param(
    [Parameter(Position=0)]
    [string]$RepoPath = ".",
    
    [Parameter()]
    [string]$ConstitutionPath = "",
    
    [Parameter()]
    [int]$PollInterval = 5,
    
    [Parameter()]
    [int]$Threshold = 20,
    
    [Parameter()]
    [switch]$NoLLM
)

# Colors for output
$Colors = @{
    Header = "Cyan"
    Success = "Green"
    Warning = "Yellow"
    Error = "Red"
    Info = "White"
}

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor $Colors.Header
Write-Host "║   PERSISTENT LAYERED VERIFICATION DAEMON                       ║" -ForegroundColor $Colors.Header
Write-Host "╠═══════════════════════════════════════════════════════════════╣" -ForegroundColor $Colors.Header
Write-Host "║  Layer 0: Git Diff Detection (what changed)                   ║" -ForegroundColor $Colors.Info
Write-Host "║  Layer 1: Quick Constitutional Scan (FREE - regex only)       ║" -ForegroundColor $Colors.Info
Write-Host "║  Layer 2: Issue Ranking + Threshold Check                     ║" -ForegroundColor $Colors.Info
Write-Host "║  Layer 3: Full LLM Verification (EXPENSIVE - only if needed)  ║" -ForegroundColor $Colors.Info
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor $Colors.Header
Write-Host ""

# Resolve paths
$RepoFullPath = Resolve-Path $RepoPath -ErrorAction SilentlyContinue
if (-not $RepoFullPath) {
    Write-Host "Error: Repository path not found: $RepoPath" -ForegroundColor $Colors.Error
    exit 1
}

# Change to dysruption_cva directory
$CVAPath = Join-Path $PSScriptRoot "dysruption_cva"
if (Test-Path $CVAPath) {
    Set-Location $CVAPath
} else {
    # Assume we're already in or near the right directory
    $CVAPath = Join-Path $PSScriptRoot "." | Resolve-Path
}

# Set environment variables
$env:CVA_POLL_INTERVAL = $PollInterval.ToString()
$env:CVA_ESCALATION_THRESHOLD = $Threshold.ToString()
if ($NoLLM) {
    $env:CVA_ENABLE_LLM_ESCALATION = "false"
} else {
    $env:CVA_ENABLE_LLM_ESCALATION = "true"
}

Write-Host "Configuration:" -ForegroundColor $Colors.Header
Write-Host "  Repository:    $RepoFullPath" -ForegroundColor $Colors.Info
Write-Host "  Poll Interval: ${PollInterval}s" -ForegroundColor $Colors.Info
Write-Host "  Threshold:     $Threshold" -ForegroundColor $Colors.Info
Write-Host "  LLM Enabled:   $(-not $NoLLM)" -ForegroundColor $Colors.Info
Write-Host ""

# Build command
$PythonArgs = @("-m", "modules.monitoring.persistent_verification", "--repo", $RepoFullPath.Path)

if ($ConstitutionPath -and (Test-Path $ConstitutionPath)) {
    $PythonArgs += "--constitution"
    $PythonArgs += (Resolve-Path $ConstitutionPath).Path
}

if ($NoLLM) {
    $PythonArgs += "--no-llm"
}

Write-Host "Starting daemon... (Press Ctrl+C to stop)" -ForegroundColor $Colors.Success
Write-Host ""

# Run the daemon
try {
    python $PythonArgs
} catch {
    Write-Host "Error running daemon: $_" -ForegroundColor $Colors.Error
    exit 1
}
