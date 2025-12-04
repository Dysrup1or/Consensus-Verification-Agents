<#
.SYNOPSIS
    CVA Development Environment Stop Script
.DESCRIPTION
    Stops all CVA services (Backend and Frontend)
.NOTES
    Author: CVA DevOps (10X Systems Engineer Edition)
    Version: 2.0
    
    USAGE: .\dev_stop.ps1
#>

$ErrorActionPreference = "SilentlyContinue"

$BACKEND_PORT = 8001
$FRONTEND_PORT = 3000
$SCRIPT_ROOT = $PSScriptRoot
if (-not $SCRIPT_ROOT) { $SCRIPT_ROOT = Get-Location }

$pidFile = Join-Path $SCRIPT_ROOT ".cva_pids"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Yellow
Write-Host "           CVA Development Environment - Shutdown" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Yellow
Write-Host ""

# Function to stop port processes
function Stop-PortProcesses {
    param([int]$Port, [string]$Name)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -ne 0 }
        foreach ($procId in $pids) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "[+] Stopped $Name (PID: $procId, Port: $Port)" -ForegroundColor Green
            } catch {
                Write-Host "[!] Could not stop PID $procId" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "[-] No $Name found on port $Port" -ForegroundColor DarkGray
    }
}

# Stop backend
Stop-PortProcesses -Port $BACKEND_PORT -Name "Backend"

# Stop frontend  
Stop-PortProcesses -Port $FRONTEND_PORT -Name "Frontend"

# Clean up PID file
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force
    Write-Host "[+] Cleaned up PID file" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "           CVA Services Stopped" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
