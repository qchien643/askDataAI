<#
.SYNOPSIS
    Dung backend + frontend dang chay tren cac port mac dinh.

.DESCRIPTION
    Tim process dang lang nghe port 8000 (backend) va 3000 (frontend) roi kill.

.PARAMETER BackendPort
    Port backend can dung (mac dinh 8000).

.PARAMETER FrontendPort
    Port frontend can dung (mac dinh 3000).

.EXAMPLE
    .\scripts\stop-all.ps1
    .\scripts\stop-all.ps1 -BackendPort 8001 -FrontendPort 3002
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

function Stop-PortProcess {
    param([int]$Port, [string]$Label)

    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "[SKIP] $Label (port $Port): khong co process nao listen" -ForegroundColor Gray
        return
    }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        try {
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $processId -Force
                Write-Host "[OK] Killed $Label PID=$processId ($($proc.ProcessName)) on port $Port" -ForegroundColor Green
            }
        } catch {
            Write-Host "[!!] Khong the kill PID=$processId : $_" -ForegroundColor Red
        }
    }
}

Write-Host "=== Stop dev servers ===" -ForegroundColor Cyan
Stop-PortProcess -Port $BackendPort -Label 'backend'
Stop-PortProcess -Port $FrontendPort -Label 'frontend'
Write-Host "[Done]" -ForegroundColor Green
