<#
.SYNOPSIS
    Pre-download HuggingFace models used by askDataAI into ./models/.

.DESCRIPTION
    Currently downloads:
    - leolee99/PIGuard (~736MB) — prompt-injection guardrail (Stage 0).

    After download, askdataai loads models from ./models/ with
    local_files_only=True so subsequent runs never re-download.

.PARAMETER Force
    Re-download even if a local copy already exists.

.EXAMPLE
    .\scripts\download-models.ps1
    .\scripts\download-models.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Ensure venv exists
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[!] venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Ensure huggingface_hub is installed (needed only for this script)
$python = "$RepoRoot\venv\Scripts\python.exe"
& $python -c "import huggingface_hub" 2>$null
if (-not $?) {
    Write-Host "[..] Installing huggingface_hub..." -ForegroundColor Cyan
    & $python -m pip install huggingface_hub
}

$args = @("$RepoRoot\scripts\download_models.py")
if ($Force) { $args += '--force' }

Write-Host "=== Downloading PIGuard ===" -ForegroundColor Cyan
& $python @args
if (-not $?) {
    Write-Host "[FAIL] Model download failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[Done] Models cached locally at: $RepoRoot\models\" -ForegroundColor Green
Write-Host "PIGuard will now load offline (no network) on subsequent runs." -ForegroundColor Gray
