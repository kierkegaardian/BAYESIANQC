#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID="${ROOT_DIR}/.demo-backend.pid"
FRONTEND_PID="${ROOT_DIR}/.demo-frontend.pid"

stop_pid() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}"
      echo "Stopped process ${pid}."
    fi
    rm -f "${pid_file}"
  fi
}

stop_pid "${FRONTEND_PID}"
stop_pid "${BACKEND_PID}"
