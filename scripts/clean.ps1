<#
.SYNOPSIS
    Reset runtime data: xoa ChromaDB, semantic memory, manifests cu.

.DESCRIPTION
    KHONG xoa configs/ (models.yaml, glossary.yaml). KHONG xoa venv hay node_modules.
    Chi dung khi muon "reset" pipeline state hoac fix ChromaDB corrupt.

.PARAMETER Force
    Bo qua confirmation prompt.

.EXAMPLE
    .\scripts\clean.ps1
    .\scripts\clean.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$targets = @(
    'data/chroma_data',
    'data/semantic_memory.json',
    'data/manifests'
)

Write-Host "=== Clean runtime data ===" -ForegroundColor Cyan
Write-Host "Targets:" -ForegroundColor Yellow
foreach ($t in $targets) {
    $exists = Test-Path $t
    $marker = if ($exists) { '[EXISTS]' } else { '[skip]' }
    Write-Host "  $marker $t"
}

if (-not $Force) {
    $reply = Read-Host "Tiep tuc? (y/N)"
    if ($reply -ne 'y' -and $reply -ne 'Y') {
        Write-Host "Da huy." -ForegroundColor Yellow
        exit 0
    }
}

foreach ($t in $targets) {
    if (Test-Path $t) {
        Remove-Item -Recurse -Force $t
        Write-Host "[OK] Xoa $t" -ForegroundColor Green
    }
}

# Tao lai folder structure
New-Item -ItemType Directory -Path 'data/chroma_data' -Force | Out-Null
New-Item -ItemType Directory -Path 'data/manifests' -Force | Out-Null

Write-Host "[Done] Reset xong. Re-deploy: chay app va connect lai SQL Server." -ForegroundColor Green
