<#
.SYNOPSIS
    Build va chay full stack qua Docker Compose.

.PARAMETER Rebuild
    Force rebuild image truoc khi up.

.PARAMETER Logs
    Tail logs sau khi up.

.PARAMETER Down
    Dung va xoa containers (giu volumes).

.PARAMETER Reset
    Down + xoa volumes (mat ChromaDB!).

.EXAMPLE
    .\scripts\docker-up.ps1
    .\scripts\docker-up.ps1 -Rebuild -Logs
    .\scripts\docker-up.ps1 -Down
    .\scripts\docker-up.ps1 -Reset
#>

[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$Logs,
    [switch]$Down,
    [switch]$Reset
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Reset) {
    Write-Host "[..] docker compose down -v (xoa volumes)..." -ForegroundColor Yellow
    docker compose down -v
    Write-Host "[Done]" -ForegroundColor Green
    return
}

if ($Down) {
    Write-Host "[..] docker compose down..." -ForegroundColor Yellow
    docker compose down
    Write-Host "[Done]" -ForegroundColor Green
    return
}

if (-not (Test-Path .env)) {
    Write-Host "[!] Khong co .env. Chay '.\scripts\setup.ps1' truoc hoac copy .env.example." -ForegroundColor Red
    exit 1
}

$args = @('compose', 'up', '-d')
if ($Rebuild) { $args += '--build' }

Write-Host "=== Docker Compose Up ===" -ForegroundColor Cyan
& docker @args
if (-not $?) { throw "docker compose up failed" }

Write-Host ""
Write-Host "Backend  -> http://localhost:8000  (docs: /docs)" -ForegroundColor White
Write-Host "Frontend -> http://localhost:3001" -ForegroundColor White
Write-Host ""

if ($Logs) {
    Write-Host "[..] Tailing logs (Ctrl+C de thoat)..." -ForegroundColor Cyan
    docker compose logs -f
}
