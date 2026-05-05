<#
.SYNOPSIS
    Khoi dong backend FastAPI (uvicorn) voi auto-reload.

.PARAMETER Port
    Port de chay backend (mac dinh 8000).

.PARAMETER NoReload
    Tat auto-reload (vi du khi chay production-like local).

.PARAMETER Host
    Host de bind (mac dinh 0.0.0.0).

.EXAMPLE
    .\scripts\start-backend.ps1
    .\scripts\start-backend.ps1 -Port 8001
    .\scripts\start-backend.ps1 -NoReload
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$BindHost = '0.0.0.0',
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# ── Activate venv (tao neu chua co) ──────────────────────────────────────
if (-not (Test-Path venv/Scripts/python.exe)) {
    Write-Host "[..] Khong tim thay venv, dang tao..." -ForegroundColor Yellow
    python -m venv venv
    if (-not $?) { throw "venv creation failed" }
    & "$RepoRoot\venv\Scripts\python.exe" -m pip install -r requirements.txt
    if (-not $?) { throw "pip install failed" }
}

if (-not (Test-Path .env)) {
    Write-Host "[!] Khong co .env file. Chay '.\scripts\setup.ps1' truoc." -ForegroundColor Red
    exit 1
}

$python = "$RepoRoot\venv\Scripts\python.exe"
$args = @(
    '-m', 'uvicorn', 'askdataai.server:app',
    '--host', $BindHost,
    '--port', "$Port",
    '--log-level', 'info'
)
if (-not $NoReload) { $args += '--reload' }

Write-Host "=== Backend ===" -ForegroundColor Cyan
Write-Host "URL    : http://localhost:$Port" -ForegroundColor White
Write-Host "Docs   : http://localhost:$Port/docs" -ForegroundColor White
Write-Host "Health : http://localhost:$Port/health" -ForegroundColor White
Write-Host "Reload : $(-not $NoReload)" -ForegroundColor White
Write-Host ""

& $python @args
