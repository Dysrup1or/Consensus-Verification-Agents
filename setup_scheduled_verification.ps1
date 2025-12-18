<# Scheduled Verification Setup Script

This script sets up a Windows Task Scheduler job to run verification every 15 minutes.

Usage:
    .\setup_scheduled_verification.ps1
    .\setup_scheduled_verification.ps1 -IntervalMinutes 30
    .\setup_scheduled_verification.ps1 -Remove  # To remove the scheduled task
#>

param(
    [int]$IntervalMinutes = 15,
    [string]$RepoPath = "C:\Users\alexe\Invariant\dysruption_cva",
    [switch]$Remove,
    [switch]$RunNow
)

$TaskName = "CVA-ScheduledVerification"
$PythonPath = "C:\Users\alexe\Invariant\.venv\Scripts\python.exe"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   CVA SCHEDULED VERIFICATION SETUP                             ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($Remove) {
    Write-Host "Removing scheduled task: $TaskName" -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Task removed successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Task not found or already removed." -ForegroundColor Gray
    }
    exit 0
}

if ($RunNow) {
    Write-Host "Running single verification check..." -ForegroundColor Cyan
    Set-Location $RepoPath
    & $PythonPath -m modules.monitoring.scheduled_verification --once --repo $RepoPath
    exit 0
}

# Check if Python exists
if (-not (Test-Path $PythonPath)) {
    Write-Host "Error: Python not found at $PythonPath" -ForegroundColor Red
    exit 1
}

# Check if repo exists
if (-not (Test-Path $RepoPath)) {
    Write-Host "Error: Repository not found at $RepoPath" -ForegroundColor Red
    exit 1
}

Write-Host "Configuration:" -ForegroundColor White
Write-Host "  Task Name:  $TaskName"
Write-Host "  Interval:   Every $IntervalMinutes minutes"
Write-Host "  Repository: $RepoPath"
Write-Host "  Python:     $PythonPath"
Write-Host ""

# Build the command
$Arguments = "-m modules.monitoring.scheduled_verification --once --repo `"$RepoPath`""
$WorkingDir = $RepoPath

# Create the scheduled task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $Arguments `
    -WorkingDirectory $WorkingDir

# Create the trigger (repeat every N minutes, indefinitely)
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false

# Create principal (run as current user)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

# Remove existing task if present
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch { }

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "CVA Layered Verification - Runs security checks every $IntervalMinutes minutes" `
        -Force | Out-Null
    
    Write-Host "Scheduled task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The verification will run every $IntervalMinutes minutes." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Useful commands:" -ForegroundColor White
    Write-Host "  View task:    Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Run now:      Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  Remove:       .\setup_scheduled_verification.ps1 -Remove"
    Write-Host "  View report:  Get-Content '$RepoPath\verification_report.json'"
    Write-Host ""
    
} catch {
    Write-Host "Error creating scheduled task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative: Run manually in a terminal:" -ForegroundColor Yellow
    Write-Host "  cd $RepoPath"
    Write-Host "  python -m modules.monitoring.scheduled_verification --interval $IntervalMinutes"
    exit 1
}
