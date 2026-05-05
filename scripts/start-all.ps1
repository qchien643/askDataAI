<#
.SYNOPSIS
    Khoi dong CA backend va frontend trong 2 cua so PowerShell rieng.

.DESCRIPTION
    Mo 2 process PowerShell moi:
    - Window 1: backend tai port 8000 (uvicorn --reload)
    - Window 2: frontend tai port 3000 (npm run dev)

    De dung tat ca: dong 2 cua so, hoac chay .\scripts\stop-all.ps1.

.PARAMETER BackendPort
    Port backend (mac dinh 8000).

.PARAMETER FrontendPort
    Port frontend (mac dinh 3000).

.EXAMPLE
    .\scripts\start-all.ps1
    .\scripts\start-all.ps1 -BackendPort 8001 -FrontendPort 3002
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

$backendCmd  = "& '$RepoRoot\scripts\start-backend.ps1' -Port $BackendPort"
$frontendCmd = "& '$RepoRoot\scripts\start-frontend.ps1' -Port $FrontendPort -ApiBase 'http://localhost:$BackendPort'"

Write-Host "=== Khoi dong full stack ===" -ForegroundColor Cyan
Write-Host "Backend  -> http://localhost:$BackendPort  (cua so moi)" -ForegroundColor White
Write-Host "Frontend -> http://localhost:$FrontendPort  (cua so moi)" -ForegroundColor White
Write-Host ""

Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-ExecutionPolicy', 'Bypass',
    '-Command', $backendCmd
) -WorkingDirectory $RepoRoot

Start-Sleep -Seconds 2  # Cho backend start truoc

Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-ExecutionPolicy', 'Bypass',
    '-Command', $frontendCmd
) -WorkingDirectory $RepoRoot

Write-Host "[OK] Da mo 2 cua so. Cho ~10s de cac service san sang." -ForegroundColor Green
Write-Host "De dung: chay '.\scripts\stop-all.ps1' hoac dong manual 2 cua so." -ForegroundColor Gray
