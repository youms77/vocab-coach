<#
.SYNOPSIS
  Checks that the tools vocab-coach needs are installed, and explains how to install what is missing.

.DESCRIPTION
  Required: Git, uv, Node.js (>= 22.22, LTS recommended) with npm.
  Python itself is managed by uv (uv downloads Python 3.13 if it is not installed),
  so a system Python is reported but not required.

  Exit code 0 when every required tool is present, 1 otherwise.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\check-env.ps1
#>
[CmdletBinding()]
param(
    # Print only problems (used by start.ps1).
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$script:missing = 0

function Write-Ok([string]$message) {
    if (-not $Quiet) { Write-Host "  [ok]      $message" -ForegroundColor Green }
}

function Write-Missing([string]$message, [string[]]$help) {
    $script:missing++
    Write-Host "  [missing] $message" -ForegroundColor Red
    foreach ($line in $help) { Write-Host "            $line" -ForegroundColor Yellow }
}

function Write-Note([string]$message) {
    if (-not $Quiet) { Write-Host "  [info]    $message" -ForegroundColor Cyan }
}

function Get-CommandVersion([string]$command, [string[]]$arguments) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { return $null }
    try {
        $output = & $command @arguments 2>&1 | Out-String
        $match = [regex]::Match($output, '(\d+)\.(\d+)(?:\.(\d+))?')
        if ($match.Success) { return [version]$match.Value }
    } catch {
        return $null
    }
    return $null
}

if (-not $Quiet) { Write-Host "Checking the vocab-coach development environment..." }

# Git
$git = Get-CommandVersion 'git' @('--version')
if ($git) { Write-Ok "Git $git" }
else {
    Write-Missing 'Git' @('Install:  winget install --id Git.Git -e', 'Then open a new terminal.')
}

# uv (Python package and project manager)
$uv = Get-CommandVersion 'uv' @('--version')
if ($uv) { Write-Ok "uv $uv" }
else {
    Write-Missing 'uv' @(
        'Install:  winget install --id astral-sh.uv -e',
        '   or:    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
        'Then open a new terminal.'
    )
}

# Node.js and npm
$minNode = [version]'22.22.0'
$node = Get-CommandVersion 'node' @('--version')
if (-not $node) {
    Write-Missing 'Node.js' @('Install the LTS version:  winget install --id OpenJS.NodeJS.LTS -e', 'Then open a new terminal.')
} elseif ($node -lt $minNode) {
    Write-Missing "Node.js $node is too old (need >= $minNode)" @('Upgrade:  winget upgrade --id OpenJS.NodeJS.LTS -e')
} else {
    Write-Ok "Node.js $node"
}

$npm = Get-CommandVersion 'npm' @('--version')
if ($npm) { Write-Ok "npm $npm" }
elseif ($node) { Write-Missing 'npm (should come with Node.js)' @('Reinstall Node.js LTS:  winget install --id OpenJS.NodeJS.LTS -e') }

# Python: informative only, uv provides the interpreter pinned in backend/.python-version.
$python = Get-CommandVersion 'py' @('-3', '--version')
if (-not $python) { $python = Get-CommandVersion 'python' @('--version') }
if ($python) { Write-Note "System Python $python found (uv will use Python 3.13 from backend/.python-version)." }
else { Write-Note 'No system Python found. That is fine: uv downloads Python 3.13 on first run.' }

# GitHub CLI: optional, handy to create the repository.
$gh = Get-CommandVersion 'gh' @('--version')
if ($gh) { Write-Note "GitHub CLI $gh (optional)" }
else { Write-Note 'GitHub CLI not found (optional):  winget install --id GitHub.cli -e' }

if ($script:missing -gt 0) {
    Write-Host ""
    Write-Host "$($script:missing) required tool(s) missing. Install them, open a new terminal and run this script again." -ForegroundColor Red
    exit 1
}

if (-not $Quiet) { Write-Host "All required tools are installed." -ForegroundColor Green }
exit 0
