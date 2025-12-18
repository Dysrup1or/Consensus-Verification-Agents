# Cleanup generated artifacts while keeping recent context.
#
# Policy:
# - Keep the newest 2 files in logs/ and top-level *REPORT*/ *READINESS*/ *ANALYSIS* markdown files.
# - Keep the newest 2 run folders under dysruption_cva/run_artifacts/.
# - Delete temp upload contents (keep .gitkeep).
# - Delete common build caches (.next/, out/, test-results/, __pycache__/, .pytest_cache/).
#
# Safe defaults: only touches known generated directories/files.

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
  [ValidateRange(0, 1000)]
  [int]$KeepCount = 2
)

$ErrorActionPreference = 'Stop'

function Remove-ItemSafe {
  param(
    [Parameter(Mandatory = $true)]
    [string]$LiteralPath,
    [switch]$Recurse
  )

  if (-not (Test-Path -LiteralPath $LiteralPath)) { return }
  if (-not $PSCmdlet.ShouldProcess($LiteralPath, 'Remove')) { return }

  $removeParams = @{
    LiteralPath  = $LiteralPath
    Force        = $true
    ErrorAction  = 'SilentlyContinue'
    WhatIf       = $WhatIfPreference
    Confirm      = $false
  }
  if ($Recurse) { $removeParams.Recurse = $true }

  Remove-Item @removeParams
}

function Keep-NewestFiles([string]$Path, [string]$Filter, [int]$Keep) {
  if (-not (Test-Path $Path)) { return }
  $items = Get-ChildItem -LiteralPath $Path -File -Filter $Filter -ErrorAction SilentlyContinue |
    Sort-Object -Property LastWriteTime -Descending
  if (-not $items) { return }
  $toDelete = $items | Select-Object -Skip $Keep
  foreach ($item in $toDelete) {
    Remove-ItemSafe -LiteralPath $item.FullName
  }
}

function Keep-NewestDirs([string]$Path, [int]$Keep) {
  if (-not (Test-Path $Path)) { return }
  $dirs = Get-ChildItem -LiteralPath $Path -Directory -ErrorAction SilentlyContinue |
    Sort-Object -Property LastWriteTime -Descending
  if (-not $dirs) { return }
  $toDelete = $dirs | Select-Object -Skip $Keep
  foreach ($dir in $toDelete) {
    Remove-ItemSafe -LiteralPath $dir.FullName -Recurse
  }
}

function Clear-DirButKeepGitkeep([string]$Path) {
  if (-not (Test-Path $Path)) { return }
  Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne '.gitkeep' } |
    ForEach-Object { Remove-ItemSafe -LiteralPath $_.FullName -Recurse }
}

Write-Host "[cleanup] Removing caches..."
$cacheDirs = @(
  'dysruption-ui/.next',
  'dysruption-ui/out',
  'dysruption-ui/test-results',
  'dysruption-ui/playwright-report',
  '__pycache__',
  '.pytest_cache',
  'dysruption_cva/__pycache__',
  'dysruption_cva/.pytest_cache'
)
foreach ($d in $cacheDirs) {
  if (Test-Path $d) {
    Remove-ItemSafe -LiteralPath $d -Recurse
  }
}

Write-Host "[cleanup] Pruning logs (keep newest $KeepCount files)..."
Keep-NewestFiles -Path 'logs' -Filter '*' -Keep $KeepCount

Write-Host "[cleanup] Pruning top-level reports (keep newest $KeepCount)..."
# Treat these as generated reports; keep 2 newest across patterns.
$reportPatterns = @('CVA_RUN_ANALYSIS_*.md', '*READINESS*.md', '*REPORT*.md')
$allReportFiles = @()
foreach ($pat in $reportPatterns) {
  $allReportFiles += Get-ChildItem -LiteralPath '.' -File -Filter $pat -ErrorAction SilentlyContinue
}
$allReportFiles = $allReportFiles |
  Sort-Object -Property FullName -Unique |
  Sort-Object -Property LastWriteTime -Descending
$allReportFiles | Select-Object -Skip $KeepCount | ForEach-Object {
  Remove-ItemSafe -LiteralPath $_.FullName
}

Write-Host "[cleanup] Pruning CVA run artifacts (keep newest $KeepCount runs)..."
Keep-NewestDirs -Path 'dysruption_cva/run_artifacts' -Keep $KeepCount

Write-Host "[cleanup] Clearing temp uploads (keep .gitkeep)..."
Clear-DirButKeepGitkeep -Path 'temp_uploads'
Clear-DirButKeepGitkeep -Path 'dysruption_cva/temp_uploads'

Write-Host "[cleanup] Removing generated CVA report artifacts (best-effort)..."
$generatedCvaFiles = @(
  'dysruption_cva/REPORT.md',
  'dysruption_cva/pytest_results.txt',
  'dysruption_cva/verdict.json',
  'dysruption_cva/verdict.sarif',
  'dysruption_cva/verification_report.json',
  'dysruption_cva/verification_report.sarif'
)
foreach ($f in $generatedCvaFiles) {
  if (Test-Path $f) {
    Remove-ItemSafe -LiteralPath $f
  }
}

Write-Host "[cleanup] Done.";
