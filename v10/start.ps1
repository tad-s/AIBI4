# v10 起動スクリプト（PowerShell 用）。backend(8000) + frontend(5173) を別ウィンドウで起動する。
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"
)

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$root\frontend'; npm run dev"
)

Write-Host ""
Write-Host "  backend : http://localhost:8000/api/health"
Write-Host "  frontend: http://localhost:5173"
Write-Host "  (各ウィンドウで Ctrl+C で停止)"
