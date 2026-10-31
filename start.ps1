<#
.SYNOPSIS
  Starts vocab-coach and opens the browser: development mode (backend + frontend with hot
  reload) by default, or the use mode (-Use): one process on one port.

.DESCRIPTION
  With -Use (daily use): one uvicorn process on http://127.0.0.1:8000 serves the built frontend
  and the API, without hot reload. The frontend is built when it is missing or older than its
  sources (-Rebuild forces it). A personal database that is behind the application is copied to
  data\backups first, then upgraded. Port 8000 busy: the start stops (no other port is tried).
  The steps below describe the development mode.

  1. Checks the required tools (scripts/check-env.ps1).
  2. Installs or updates dependencies (uv sync, npm install) when needed.
  3. Runs the API on http://127.0.0.1:8000 and the web app on http://127.0.0.1:5173, then opens
     the browser once the API answers (scripts/wait-and-open.mjs).
  Press Ctrl+C to stop both.

.EXAMPLE
  .\start.ps1
  # If scripts are blocked on your machine, double-click start.cmd instead, or run:
  powershell -ExecutionPolicy Bypass -File .\start.ps1

.EXAMPLE
  .\start.ps1 -Demo
  # Fictional demo data in data\vocab-coach-demo.sqlite3 (generated on first use).
  # Your own database is not touched.
#>
[CmdletBinding()]
param(
    # Do not open the browser automatically.
    [switch]$NoBrowser,
    # Use the fictional demo database instead of your own.
    [switch]$Demo,
    # Daily use: one process, one port (8000), no hot reload.
    [switch]$Use,
    # With -Use: build the frontend even if it looks up to date.
    [switch]$Rebuild
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

if ($Demo) {
    # Read by the backend settings: every command below and the API use the demo database.
    $env:VOCAB_DEMO = '1'
    Write-Host 'Demo mode: data\vocab-coach-demo.sqlite3 (fictional data; your database is not touched).' -ForegroundColor Yellow
} else {
    Remove-Item Env:VOCAB_DEMO -ErrorAction SilentlyContinue
}

if ($Use) {
    # Daily use: dependencies, build when needed, database, one process on one port.
    if (-not (Test-Path (Join-Path $root 'node_modules'))) {
        Invoke-Step 'Launcher dependencies (npm install)' { npm install --no-fund --no-audit }
    }
    if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
        Invoke-Step 'Frontend dependencies (npm install)' { npm --prefix frontend install --no-fund --no-audit }
    }

    $index = Join-Path $root 'frontend\dist\index.html'
    $stale = $Rebuild -or -not (Test-Path $index)
    if (-not $stale) {
        $built = (Get-Item $index).LastWriteTime
        $sources = @(Get-ChildItem (Join-Path $root 'frontend\src') -Recurse -File)
        $sources += @(Get-ChildItem (Join-Path $root 'frontend') -File |
            Where-Object { $_.Name -eq 'index.html' -or $_.Name -eq 'package.json' -or $_.Name -like 'vite.config.*' })
        $stale = [bool]($sources | Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 1)
    }
    if ($stale) {
        Invoke-Step 'Frontend build (npm run build)' { npm --prefix frontend run build }
    } else {
        Write-Host '==> Frontend build is up to date' -ForegroundColor Cyan
    }

    # Creates the database, or copies then upgrades a personal one that is behind (exit code 2 = stop).
    Write-Host '==> Database (copy before upgrade, migrations, error taxonomy)' -ForegroundColor Cyan
    uv --directory backend run python -m app db prepare
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'The database was not prepared (see the message above). The app was not started.' -ForegroundColor Red
        exit 2
    }
    if ($Demo) {
        Write-Host '==> Demo data' -ForegroundColor Cyan
        uv --directory backend run python -m app demo seed --if-missing
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'The demo data could not be generated (see the message above). The app was not started.' -ForegroundColor Red
            exit 1
        }
    }

    # One fixed port: another port would be another origin, and the browser would lose the preferences.
    $port = if ($env:VOCAB_PORT) { [int]$env:VOCAB_PORT } else { 8000 }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        $name = if ($owner) { "$($owner.ProcessName) (pid $($listener.OwningProcess))" } else { 'another program' }
        Write-Host "Port $port is already used by $name." -ForegroundColor Red
        Write-Host 'If vocab-coach is already running, use that window or close it, then start again.' -ForegroundColor Red
        exit 2
    }

    $env:VOCAB_USE_MODE = '1'
    if ($NoBrowser) {
        Remove-Item Env:VOCAB_OPEN_BROWSER -ErrorAction SilentlyContinue
    } else {
        $env:VOCAB_OPEN_BROWSER = '1'
        # Opens the browser once /api/health answers, then ends by itself.
        Start-Process -FilePath node -ArgumentList 'scripts/wait-and-open.mjs' -NoNewWindow
    }
    Write-Host ''
    Write-Host 'vocab-coach is starting:' -ForegroundColor Green
    Write-Host "  app  http://127.0.0.1:$port"
    Write-Host "  api  http://127.0.0.1:$port/docs"
    Write-Host 'Press Ctrl+C to stop.'
    Write-Host ''
    uv --directory backend run python -m app --use
    exit $LASTEXITCODE
}

# Creates the database on first run, applies new migrations, loads the error taxonomy.
Write-Host '==> Database (migrations + error taxonomy)' -ForegroundColor Cyan
uv --directory backend run python -m app db upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host 'The database could not be prepared (see the message above). The app was not started.' -ForegroundColor Red
    Write-Host 'If the app is already running in another window, close it and try again.' -ForegroundColor Red
    exit 1
}

if ($Demo) {
    # Generates the demo history the first time only (a few seconds).
    Write-Host '==> Demo data' -ForegroundColor Cyan
    uv --directory backend run python -m app demo seed --if-missing
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'The demo data could not be generated (see the message above). The app was not started.' -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path (Join-Path $root 'node_modules'))) {
    Invoke-Step 'Launcher dependencies (npm install)' { npm install --no-fund --no-audit }
}
if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Invoke-Step 'Frontend dependencies (npm install)' { npm --prefix frontend install --no-fund --no-audit }
}

# scripts\wait-and-open.mjs opens the browser once the API answers, only when this is set.
if ($NoBrowser) {
    Remove-Item Env:VOCAB_OPEN_BROWSER -ErrorAction SilentlyContinue
} else {
    $env:VOCAB_OPEN_BROWSER = '1'
}

Write-Host ''
Write-Host 'vocab-coach is starting:' -ForegroundColor Green
Write-Host '  app  http://127.0.0.1:5173'
Write-Host '  api  http://127.0.0.1:8000/docs'
Write-Host 'Press Ctrl+C to stop.'
Write-Host ''

npm run dev
exit $LASTEXITCODE
