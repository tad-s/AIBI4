#!/usr/bin/env bash
# v10 起動スクリプト（Git Bash 用）。backend(8000) + frontend(5173) を起動する。
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "starting v10 backend on :8000 ..."
(cd "$DIR/backend" && ./.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000) &
BE_PID=$!

echo "starting v10 frontend on :5173 ..."
(cd "$DIR/frontend" && npm run dev) &
FE_PID=$!

echo ""
echo "  backend : http://localhost:8000/api/health"
echo "  frontend: http://localhost:5173"
echo "  (Ctrl+C で両方停止)"

trap "kill $BE_PID $FE_PID 2>/dev/null" INT TERM
wait
