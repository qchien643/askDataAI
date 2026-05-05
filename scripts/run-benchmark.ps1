<#
.SYNOPSIS
    Run text-to-SQL benchmark against running askDataAI backend.

.DESCRIPTION
    Pre-requisites:
      1. Backend running: .\scripts\start-backend.ps1
      2. DB connected (via UI or POST /v1/connections/connect)
      3. .env has OPENAI_API_KEY (for LLM judge)

    Output: benchmarks/run_<sha>_<ts>_<tag>.json

.PARAMETER Tag
    Run tag for output filename (default: 'default').

.PARAMETER Limit
    Run only first N samples (smoke test).

.PARAMETER Difficulty
    Filter by difficulty: easy | medium | hard.

.PARAMETER ExampleId
    Run only one example by id (e.g. 'easy_001').

.PARAMETER Backend
    Backend URL (default http://localhost:8000).

.PARAMETER VerifyOnly
    Just verify gold SQL execution, skip benchmark.

.EXAMPLE
    .\scripts\run-benchmark.ps1 -Tag baseline
    .\scripts\run-benchmark.ps1 -Tag smoke -Limit 3
    .\scripts\run-benchmark.ps1 -ExampleId easy_001
    .\scripts\run-benchmark.ps1 -VerifyOnly
#>

[CmdletBinding()]
param(
    [string]$Tag = "default",
    [int]$Limit = 0,
    [string]$Difficulty,
    [string]$ExampleId,
    [string]$Backend = "http://localhost:8000",
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[!] venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$python = "$RepoRoot\venv\Scripts\python.exe"

# httpx is needed for HTTP client. Install if missing.
& $python -c "import httpx" 2>$null
if (-not $?) {
    Write-Host "[..] Installing httpx..." -ForegroundColor Cyan
    & $python -m pip install httpx
}

if ($VerifyOnly) {
    Write-Host "=== Verifying dataset (no benchmark) ===" -ForegroundColor Cyan
    & $python tests\eval\verify_dataset.py
    exit $LASTEXITCODE
}

$args = @("tests\eval\benchmark_runner.py", "--tag", $Tag, "--backend", $Backend)
if ($Limit -gt 0) { $args += @("--limit", "$Limit") }
if ($Difficulty) { $args += @("--difficulty", $Difficulty) }
if ($ExampleId) { $args += @("--example-id", $ExampleId) }

Write-Host "=== Running benchmark ===" -ForegroundColor Cyan
Write-Host "Tag:        $Tag" -ForegroundColor Gray
Write-Host "Backend:    $Backend" -ForegroundColor Gray
if ($Limit -gt 0) { Write-Host "Limit:      $Limit" -ForegroundColor Gray }
if ($Difficulty) { Write-Host "Difficulty: $Difficulty" -ForegroundColor Gray }
if ($ExampleId) { Write-Host "ExampleId:  $ExampleId" -ForegroundColor Gray }
Write-Host ""

& $python @args
exit $LASTEXITCODE
