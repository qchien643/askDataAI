<#
.SYNOPSIS
    Khoi dong Next.js frontend dev server.

.PARAMETER Port
    Port de chay (mac dinh 3000).

.PARAMETER ApiBase
    URL backend (mac dinh http://localhost:8000).

.EXAMPLE
    .\scripts\start-frontend.ps1
    .\scripts\start-frontend.ps1 -Port 3002
    .\scripts\start-frontend.ps1 -ApiBase http://192.168.1.10:8000
#>

[CmdletBinding()]
param(
    [int]$Port = 3000,
    [string]$ApiBase = 'http://localhost:8000'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path web)) {
    Write-Host "[!] Khong tim thay folder web/" -ForegroundColor Red
    exit 1
}

Push-Location web
try {
    # Tao .env.local neu chua co (hoac override neu ApiBase khac default)
    $envFile = Join-Path (Get-Location) '.env.local'
    $envContent = "NEXT_PUBLIC_API_BASE=$ApiBase"
    if (-not (Test-Path $envFile)) {
        $envContent | Out-File -Encoding utf8 -NoNewline $envFile
        Write-Host "[OK] Tao web/.env.local voi NEXT_PUBLIC_API_BASE=$ApiBase" -ForegroundColor Green
    }

    # Cai deps neu chua
    if (-not (Test-Path node_modules)) {
        Write-Host "[..] Cai Node dependencies..." -ForegroundColor Cyan
        npm install --legacy-peer-deps
        if (-not $?) { throw "npm install failed" }
    }

    Write-Host "=== Frontend ===" -ForegroundColor Cyan
    Write-Host "URL      : http://localhost:$Port" -ForegroundColor White
    Write-Host "Backend  : $ApiBase" -ForegroundColor White
    Write-Host ""

    # Next.js doc port qua env var, fallback flag --port
    $env:PORT = "$Port"
    npm run dev -- --port $Port
} finally {
    Pop-Location
}
