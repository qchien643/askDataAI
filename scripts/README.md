# scripts/

PowerShell scripts cho Windows. Chi tiết: xem `docs/SETUP.md`.

## Lần đầu

```powershell
# Cho phép chạy script (chỉ trong session hiện tại, không cần admin)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Cài đặt full (bao gồm download PIGuard model ~736MB vào models/piguard)
.\scripts\setup.ps1

# Bỏ qua download model (nếu đã có hoặc dùng mạng chậm)
.\scripts\setup.ps1 -SkipModels
```

> Sau lần download đầu, `askdataai/security/pi_guardrail.py` load PIGuard từ
> `models/piguard/` với `local_files_only=True` — **không cần mạng**, mọi run
> server đều load từ disk.

## Daily dev

| Lệnh | Việc |
|---|---|
| `.\scripts\start-all.ps1` | Mở 2 cửa sổ: backend (8000) + frontend (3000) |
| `.\scripts\start-backend.ps1` | Chỉ backend |
| `.\scripts\start-frontend.ps1` | Chỉ frontend |
| `.\scripts\stop-all.ps1` | Kill process trên port 8000 + 3000 |
| `.\scripts\clean.ps1` | Reset ChromaDB + semantic memory |
| `.\scripts\download-models.ps1` | Pre-download PIGuard vào models/piguard (offline mode) |
| `.\scripts\download-models.ps1 -Force` | Force re-download |

## Docker

| Lệnh | Việc |
|---|---|
| `.\scripts\docker-up.ps1` | `docker compose up -d` |
| `.\scripts\docker-up.ps1 -Rebuild` | Build lại trước khi up |
| `.\scripts\docker-up.ps1 -Logs` | Tail logs sau khi up |
| `.\scripts\docker-up.ps1 -Down` | Dừng (giữ volumes) |
| `.\scripts\docker-up.ps1 -Reset` | Down + xoá volumes (mất ChromaDB) |

## Tham số chung

Mọi script đều hỗ trợ `-Help` qua PowerShell native:

```powershell
Get-Help .\scripts\start-backend.ps1 -Detailed
```

## Cấu hình port khác

```powershell
.\scripts\start-backend.ps1 -Port 8001
.\scripts\start-frontend.ps1 -Port 3002 -ApiBase http://localhost:8001
.\scripts\start-all.ps1 -BackendPort 8001 -FrontendPort 3002
```
