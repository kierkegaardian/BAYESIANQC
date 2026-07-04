#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID="${ROOT_DIR}/.demo-backend.pid"
FRONTEND_PID="${ROOT_DIR}/.demo-frontend.pid"
BACKEND_LOG="${ROOT_DIR}/uvicorn.log"
FRONTEND_LOG="${ROOT_DIR}/frontend/vite.log"
POSTGRES_URL="${BAYESIANQC_DB_URL:-postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc}"

start_postgres() {
  docker compose -f "${ROOT_DIR}/docker-compose.yml" up -d postgres
  wait_for_postgres
}

wait_for_postgres() {
  for _ in {1..40}; do
    if docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
      pg_isready -U bayesianqc -d bayesianqc >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "Postgres did not become ready in time." >&2
  exit 1
}

start_backend() {
  if [[ -f "${BACKEND_PID}" ]] && kill -0 "$(cat "${BACKEND_PID}")" 2>/dev/null; then
    echo "Backend already running (PID $(cat "${BACKEND_PID}"))."
    return
  fi
  env BAYESIANQC_DB_URL="${POSTGRES_URL}" BAYESIANQC_SEED_LOCAL_DEV_KEY=1 \
    setsid "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8010 \
    > "${BACKEND_LOG}" 2>&1 < /dev/null &
  echo $! > "${BACKEND_PID}"
  echo "Backend started (PID $(cat "${BACKEND_PID}"))."
}

start_frontend() {
  if [[ -f "${FRONTEND_PID}" ]] && kill -0 "$(cat "${FRONTEND_PID}")" 2>/dev/null; then
    echo "Frontend already running (PID $(cat "${FRONTEND_PID}"))."
    return
  fi
  setsid bash -lc "cd '${ROOT_DIR}/frontend' && exec npm run dev -- --host 0.0.0.0 --port 5177" \
    > "${FRONTEND_LOG}" 2>&1 < /dev/null &
  echo $! > "${FRONTEND_PID}"
  echo "Frontend started (PID $(cat "${FRONTEND_PID}"))."
}

start_postgres
start_backend
start_frontend

echo "Open http://localhost:5177 (or your LAN IP) for the UI."
