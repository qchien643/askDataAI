<#
.SYNOPSIS
    Cài đặt lần đầu cho mini-wren-ai (venv + Python deps + Node deps + .env).

.DESCRIPTION
    Chạy 1 lần khi clone repo về. Idempotent — chạy lại không hỏng gì.

.EXAMPLE
    .\scripts\setup.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipPython,
    [switch]$SkipNode,
    [switch]$SkipModels
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== mini-wren-ai setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot" -ForegroundColor Gray

# ── 1. .env ──────────────────────────────────────────────────────────────
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "[OK] Tao .env tu .env.example - hay sua thong tin SQL Server + OpenAI key" -ForegroundColor Yellow
} else {
    Write-Host "[SKIP] .env da ton tai" -ForegroundColor Gray
}

if (-not (Test-Path web/.env.local)) {
    "NEXT_PUBLIC_API_BASE=http://localhost:8000" | Out-File -Encoding utf8 -NoNewline web/.env.local
    Write-Host "[OK] Tao web/.env.local" -ForegroundColor Green
} else {
    Write-Host "[SKIP] web/.env.local da ton tai" -ForegroundColor Gray
}

# ── 2. Python venv + deps ────────────────────────────────────────────────
if (-not $SkipPython) {
    if (-not (Test-Path venv/Scripts/python.exe)) {
        Write-Host "[..] Tao Python venv..." -ForegroundColor Cyan
        python -m venv venv
        if (-not $?) { throw "venv creation failed" }
    } else {
        Write-Host "[SKIP] venv da ton tai" -ForegroundColor Gray
    }

    Write-Host "[..] Cai Python dependencies..." -ForegroundColor Cyan
    & "$RepoRoot\venv\Scripts\python.exe" -m pip install --upgrade pip
    & "$RepoRoot\venv\Scripts\python.exe" -m pip install -r requirements.txt
    if (-not $?) { throw "pip install failed" }
    Write-Host "[OK] Python deps installed" -ForegroundColor Green
}

# ── 3. Node deps ─────────────────────────────────────────────────────────
if (-not $SkipNode) {
    if (-not (Test-Path web/node_modules)) {
        Write-Host "[..] Cai Node dependencies (web/)..." -ForegroundColor Cyan
        Push-Location web
        try {
            npm install --legacy-peer-deps
            if (-not $?) { throw "npm install failed" }
        } finally {
            Pop-Location
        }
        Write-Host "[OK] Node deps installed" -ForegroundColor Green
    } else {
        Write-Host "[SKIP] web/node_modules da ton tai" -ForegroundColor Gray
    }
}

# ── 4. Tao runtime data dirs ────────────────────────────────────────────
$dataDirs = @('data', 'data/chroma_data', 'data/manifests')
foreach ($d in $dataDirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "[OK] Tao $d/" -ForegroundColor Green
    }
}

# ── 5. Pre-download HuggingFace models (PIGuard) ─────────────────────────
if (-not $SkipModels) {
    if (Test-Path "models/piguard" -PathType Container) {
        $hasFiles = Get-ChildItem -Path "models/piguard" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hasFiles) {
            Write-Host "[SKIP] models/piguard/ already populated" -ForegroundColor Gray
        } else {
            & "$RepoRoot\scripts\download-models.ps1"
        }
    } else {
        Write-Host "[..] Pre-downloading PIGuard model (~736MB, one-time)..." -ForegroundColor Cyan
        & "$RepoRoot\scripts\download-models.ps1"
    }
}

Write-Host ""
Write-Host "=== Setup xong ===" -ForegroundColor Green
Write-Host "Tiep theo:" -ForegroundColor Cyan
Write-Host "  1. Sua .env voi thong tin SQL Server + OpenAI API key"
Write-Host "  2. Chay: .\scripts\start-all.ps1   (hoac start-backend.ps1 + start-frontend.ps1 rieng)"
