#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-}"
HOST=""
DOMAIN="qc.geoffsmiscellany.com"
REMOTE_ROOT="/srv/bayesianqc"
SSH_KEY=""
SKIP_PUBLIC_SMOKE="${DEMO_VPS_SKIP_PUBLIC_SMOKE:-0}"

usage() {
  cat <<USAGE
Usage: $0 <bootstrap|deploy|reset-data|rotate-password|smoke|rollback> --host <ssh-host> [options]

Options:
  --domain <domain>          Public domain (default: ${DOMAIN})
  --remote-root <path>       Remote install root (default: ${REMOTE_ROOT})
  --ssh-key <path>           SSH private key
  --release-id <id>          Required for rollback; auto-generated for deploy
  --skip-public-smoke        Skip public https://domain Basic Auth smoke check

USAGE
}

if [[ -z "$COMMAND" || "$COMMAND" == "--help" || "$COMMAND" == "-h" ]]; then
  usage
  exit 0
fi

require_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    echo "$option requires a value" >&2
    exit 2
  fi
  printf '%s\n' "$value"
}

shift || true
ROLLBACK_RELEASE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$(require_value "$1" "${2:-}")"; shift 2 ;;
    --domain) DOMAIN="$(require_value "$1" "${2:-}")"; shift 2 ;;
    --remote-root) REMOTE_ROOT="$(require_value "$1" "${2:-}")"; shift 2 ;;
    --ssh-key) SSH_KEY="$(require_value "$1" "${2:-}")"; shift 2 ;;
    --release-id) ROLLBACK_RELEASE="$(require_value "$1" "${2:-}")"; shift 2 ;;
    --skip-public-smoke) SKIP_PUBLIC_SMOKE=1; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$COMMAND" || -z "$HOST" ]]; then
  usage >&2
  exit 2
fi

if [[ "$REMOTE_ROOT" != /* || "$REMOTE_ROOT" == "/" || "$REMOTE_ROOT" =~ [[:space:]] ]]; then
  echo "--remote-root must be an absolute path without whitespace" >&2
  exit 2
fi

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ ]]; then
  echo "--domain must be a DNS name" >&2
  exit 2
fi

if [[ -n "$SSH_KEY" && ! -f "$SSH_KEY" ]]; then
  echo "--ssh-key does not exist: $SSH_KEY" >&2
  exit 2
fi

SSH_ARGS=(-o BatchMode=yes)
SCP_ARGS=()
if [[ -n "$SSH_KEY" ]]; then
  SSH_ARGS+=(-i "$SSH_KEY")
  SCP_ARGS+=(-i "$SSH_KEY")
fi

remote_env=(
  "BAYESIANQC_REMOTE_ROOT=$REMOTE_ROOT"
  "BAYESIANQC_DOMAIN=$DOMAIN"
  "BAYESIANQC_SKIP_PUBLIC_SMOKE=$SKIP_PUBLIC_SMOKE"
)

shell_join() {
  local quoted=()
  local item
  for item in "$@"; do
    quoted+=("$(printf '%q' "$item")")
  done
  printf '%s' "${quoted[*]}"
}

remote_run() {
  local remote_command
  remote_command="$(shell_join env "${remote_env[@]}" "$@")"
  ssh "${SSH_ARGS[@]}" "$HOST" "$remote_command"
}

public_basic_auth_smoke() {
  if [[ "$SKIP_PUBLIC_SMOKE" =~ ^(1|true|yes)$ ]]; then
    echo "Skipping public Basic Auth smoke because --skip-public-smoke is set."
    return
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required for public smoke checks." >&2
    exit 2
  fi
  for _ in $(seq 1 40); do
    if python3 - "$DOMAIN" <<'PY' >/dev/null 2>&1
from __future__ import annotations

import sys
import urllib.error
import urllib.request

domain = sys.argv[1]
try:
    urllib.request.urlopen(f"https://{domain}/api/me", timeout=5)
except urllib.error.HTTPError as exc:
    challenge = exc.headers.get("WWW-Authenticate", "")
    raise SystemExit(0 if exc.code == 401 and "Basic" in challenge else 1)
except Exception:
    raise SystemExit(1)
raise SystemExit(1)
PY
    then
      echo "Public Basic Auth smoke passed: https://$DOMAIN/api/me"
      return
    fi
    sleep 3
  done
  echo "Public https://$DOMAIN/api/me did not return the expected Basic Auth challenge." >&2
  exit 1
}

upload_remote_helper() {
  remote_run mkdir -p "$REMOTE_ROOT/incoming"
  scp "${SCP_ARGS[@]}" "$ROOT_DIR/deploy/demo-vps/remote.sh" "$HOST:$REMOTE_ROOT/incoming/remote.sh"
  remote_run chmod 700 "$REMOTE_ROOT/incoming/remote.sh"
}

ensure_clean_release() {
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Refusing to deploy from a dirty worktree. Commit or stash changes first." >&2
    exit 3
  fi
}

make_archive() {
  local release_id archive
  release_id="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)-$(date -u +%Y%m%dT%H%M%SZ)"
  archive="${TMPDIR:-/tmp}/bayesianqc-${release_id}.tar.gz"
  git -C "$ROOT_DIR" archive --format=tar.gz --output "$archive" HEAD
  printf '%s\n%s\n' "$release_id" "$archive"
}

run_release_command() {
  ensure_clean_release
  upload_remote_helper
  local release_info release_id archive remote_archive
  release_info="$(make_archive)"
  release_id="$(printf '%s\n' "$release_info" | sed -n '1p')"
  archive="$(printf '%s\n' "$release_info" | sed -n '2p')"
  remote_archive="$REMOTE_ROOT/incoming/bayesianqc-${release_id}.tar.gz"
  scp "${SCP_ARGS[@]}" "$archive" "$HOST:$remote_archive"
  rm -f "$archive"
  remote_run "BAYESIANQC_RELEASE_ID=$release_id" "BAYESIANQC_ARCHIVE=$remote_archive" bash "$REMOTE_ROOT/incoming/remote.sh" "$COMMAND"
  public_basic_auth_smoke
}

case "$COMMAND" in
  bootstrap|deploy)
    run_release_command
    ;;
  reset-data|rotate-password|smoke)
    upload_remote_helper
    remote_run bash "$REMOTE_ROOT/incoming/remote.sh" "$COMMAND"
    public_basic_auth_smoke
    ;;
  rollback)
    if [[ -z "$ROLLBACK_RELEASE" ]]; then
      echo "--release-id is required for rollback" >&2
      exit 2
    fi
    if [[ ! "$ROLLBACK_RELEASE" =~ ^[A-Za-z0-9._-]+$ ]]; then
      echo "--release-id contains unsupported characters" >&2
      exit 2
    fi
    upload_remote_helper
    remote_run "BAYESIANQC_RELEASE_ID=$ROLLBACK_RELEASE" bash "$REMOTE_ROOT/incoming/remote.sh" rollback
    public_basic_auth_smoke
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
