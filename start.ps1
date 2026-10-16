<#
.SYNOPSIS
  Starts vocab-coach in development mode (backend + frontend) and opens the browser.

.DESCRIPTION
  1. Checks the required tools (scripts/check-env.ps1).
  2. Installs or updates dependencies (uv sync, npm install) when needed.
  3. Runs the API on http://127.0.0.1:8000 and the web app on http://127.0.0.1:5173.
  Press Ctrl+C to stop both.

.EXAMPLE
  .\start.ps1
  # If scripts are blocked on your machine, double-click start.cmd instead, or run:
  powershell -ExecutionPolicy Bypass -File .\start.ps1
#>
[CmdletBinding()]
param(
    # Do not open the browser automatically.
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Invoke-Step([string]$label, [scriptblock]$action) {
    Write-Host "==> $label" -ForegroundColor Cyan
    & $action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Step failed: $label (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

& (Join-Path $root 'scripts\check-env.ps1') -Quiet
if ($LASTEXITCODE -ne 0) { exit 1 }

# uv sync is fast and idempotent: it creates backend\.venv on first run and
# downloads Python 3.13 if needed.
Invoke-Step 'Backend dependencies (uv sync)' { uv --directory backend sync --quiet }

# Creates data\vocab-coach.sqlite3 on first run, applies new migrations, loads the error taxonomy.
Write-Host '==> Database (migrations + error taxonomy)' -ForegroundColor Cyan
uv --directory backend run python -m app db upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host 'The database could not be prepared (see the message above). The app was not started.' -ForegroundColor Red
    Write-Host 'If the app is already running in another window, close it and try again.' -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $root 'node_modules'))) {
    Invoke-Step 'Launcher dependencies (npm install)' { npm install --no-fund --no-audit }
}
if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Invoke-Step 'Frontend dependencies (npm install)' { npm --prefix frontend install --no-fund --no-audit }
}

if (-not $NoBrowser) { $env:VOCAB_OPEN_BROWSER = '1' }

Write-Host ''
Write-Host 'vocab-coach is starting:' -ForegroundColor Green
Write-Host '  app  http://127.0.0.1:5173'
Write-Host '  api  http://127.0.0.1:8000/docs'
Write-Host 'Press Ctrl+C to stop.'
Write-Host ''

npm run dev
exit $LASTEXITCODE
