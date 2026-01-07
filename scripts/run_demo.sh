#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID="${ROOT_DIR}/.demo-backend.pid"
FRONTEND_PID="${ROOT_DIR}/.demo-frontend.pid"
BACKEND_LOG="${ROOT_DIR}/uvicorn.log"
FRONTEND_LOG="${ROOT_DIR}/frontend/vite.log"

start_backend() {
  if [[ -f "${BACKEND_PID}" ]] && kill -0 "$(cat "${BACKEND_PID}")" 2>/dev/null; then
    echo "Backend already running (PID $(cat "${BACKEND_PID}"))."
    return
  fi
  nohup "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8010 \
    > "${BACKEND_LOG}" 2>&1 &
  echo $! > "${BACKEND_PID}"
  echo "Backend started (PID $(cat "${BACKEND_PID}"))."
}

start_frontend() {
  if [[ -f "${FRONTEND_PID}" ]] && kill -0 "$(cat "${FRONTEND_PID}")" 2>/dev/null; then
    echo "Frontend already running (PID $(cat "${FRONTEND_PID}"))."
    return
  fi
  (cd "${ROOT_DIR}/frontend" && nohup npm run dev -- --host 0.0.0.0 --port 5173 \
    > "${FRONTEND_LOG}" 2>&1 & echo $! > "${FRONTEND_PID}")
  echo "Frontend started (PID $(cat "${FRONTEND_PID}"))."
}

start_backend
start_frontend

echo "Open http://localhost:5173 (or your LAN IP) for the UI."
