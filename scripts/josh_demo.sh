#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-}"
REMOTE_ROOT="${JOSH_DEMO_REMOTE_ROOT:-/home/geoff/services/bayesianqc-josh-demo}"
STABILITY_SECONDS="${JOSH_DEMO_STABILITY_SECONDS:-900}"
ARCHIVE=""
BASIC_PASSWORD="${JOSH_DEMO_BASIC_PASSWORD:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/josh_demo.sh <command> [options]

Commands:
  bootstrap       Deploy a clean committed SHA with fresh secrets and synthetic data
  deploy          Deploy a clean committed SHA while retaining existing secrets
  reset           Recreate the synthetic database and import archive from scratch
  smoke           Run private/public authorization checks and URL stability monitoring
  status          Show the exact release, image manifest, containers, and tunnel URL
  start-tunnel    Start an accountless Quick Tunnel after private smoke passes
  stop            Stop the project tunnel first, then all project containers
  teardown        Stop the tunnel, snapshot, remove project containers and secrets
  rotate-password Rotate the one-time Basic Auth password without storing plaintext

Options:
  --remote-root PATH          Default: /home/geoff/services/bayesianqc-josh-demo
  --stability-seconds N       Public smoke duration; minimum/default: 900

For authenticated public smoke, export JOSH_DEMO_BASIC_PASSWORD or enter it at the prompt.
USAGE
}

[[ -n "$COMMAND" && "$COMMAND" != "--help" && "$COMMAND" != "-h" ]] || { usage; exit 0; }
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --stability-seconds) STABILITY_SECONDS="${2:-}"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$REMOTE_ROOT" == /* && "$REMOTE_ROOT" != "/" && ! "$REMOTE_ROOT" =~ [[:space:]] ]] || {
  echo "--remote-root must be an absolute path without whitespace" >&2
  exit 2
}
[[ "$STABILITY_SECONDS" =~ ^[0-9]+$ && "$STABILITY_SECONDS" -le 3600 ]] || {
  echo "--stability-seconds must be an integer from 0 through 3600" >&2
  exit 2
}
if [[ "$COMMAND" == "smoke" && "$STABILITY_SECONDS" -lt 900 ]]; then
  echo "smoke requires --stability-seconds of at least 900 before recording a pass" >&2
  exit 2
fi
command -v homeops-ssh-ubuntu >/dev/null 2>&1 || { echo "homeops-ssh-ubuntu is required" >&2; exit 2; }

cleanup() { [[ -z "$ARCHIVE" ]] || rm -f "$ARCHIVE"; }
trap cleanup EXIT

shell_join() {
  local quoted=() item
  for item in "$@"; do quoted+=("$(printf '%q' "$item")"); done
  printf '%s' "${quoted[*]}"
}

remote_run() {
  local command
  command="$(shell_join "$@")"
  homeops-ssh-ubuntu "$command"
}

stream_file() {
  local source="$1" destination="$2" mode="$3" command
  command="$(shell_join sh -c 'umask 077; target=$1; mode=$2; tmp="${target}.tmp.$$"; cat > "$tmp"; chmod "$mode" "$tmp"; mv -f "$tmp" "$target"' _ "$destination" "$mode")"
  homeops-ssh-ubuntu "$command" < "$source"
}

upload_bootstrap_helpers() {
  remote_run install -d -m 700 "$REMOTE_ROOT/incoming"
  stream_file "$ROOT_DIR/deploy/demo/remote.sh" "$REMOTE_ROOT/incoming/remote.sh" 700
  stream_file "$ROOT_DIR/deploy/demo/remote_lib.sh" "$REMOTE_ROOT/incoming/remote_lib.sh" 600
}

remote_current() {
  remote_run env "BAYESIANQC_REMOTE_ROOT=$REMOTE_ROOT" \
    bash "$REMOTE_ROOT/current/deploy/demo/remote.sh" "$@"
}

ensure_release_source() {
  [[ -z "$(git -C "$ROOT_DIR" status --porcelain=v1 --untracked-files=all)" ]] || {
    echo "Refusing release from a dirty worktree. Commit the intended release first." >&2
    exit 3
  }
  [[ "$(git -C "$ROOT_DIR" branch --show-current)" == "codex/josh-demo-hardening" ]] || {
    echo "Release must be built from branch codex/josh-demo-hardening" >&2
    exit 3
  }
  git -C "$ROOT_DIR" diff --check
}

deploy_release() {
  local mode="$1" release_sha archive_sha remote_archive
  ensure_release_source
  release_sha="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  ARCHIVE="$(mktemp "${TMPDIR:-/tmp}/bayesianqc-${release_sha}.XXXXXX.tar.gz")"
  git -C "$ROOT_DIR" archive --format=tar HEAD | gzip -n > "$ARCHIVE"
  archive_sha="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
  remote_archive="$REMOTE_ROOT/incoming/bayesianqc-${release_sha}.tar.gz"
  upload_bootstrap_helpers
  stream_file "$ARCHIVE" "$remote_archive" 600
  remote_run env "BAYESIANQC_REMOTE_ROOT=$REMOTE_ROOT" "BAYESIANQC_RELEASE_ID=$release_sha" \
    "BAYESIANQC_ARCHIVE=$remote_archive" "BAYESIANQC_ARCHIVE_SHA256=$archive_sha" \
    bash "$REMOTE_ROOT/incoming/remote.sh" "$mode"
  echo "Local release SHA: $release_sha"
  echo "Archive SHA-256: $archive_sha"
}

fetch_url() { remote_current url; }

wait_for_basic_challenge() {
  local url="$1"
  for _ in $(seq 1 40); do
    if JOSH_DEMO_URL="$url" python3 - <<'PY' >/dev/null 2>&1
import os
import urllib.error
import urllib.request

try:
    urllib.request.urlopen(os.environ["JOSH_DEMO_URL"] + "/api/me", timeout=5)
except urllib.error.HTTPError as exc:
    raise SystemExit(0 if exc.code == 401 and "Basic" in exc.headers.get("WWW-Authenticate", "") else 1)
except Exception:
    raise SystemExit(1)
raise SystemExit(1)
PY
    then
      return
    fi
    sleep 3
  done
  echo "$url did not present the expected Basic Auth challenge" >&2
  return 1
}

public_smoke() {
  local url="$1" mutate_alert="${2:-0}"
  if [[ -z "$BASIC_PASSWORD" && -t 0 ]]; then
    read -r -s -p "Josh demo Basic Auth password: " BASIC_PASSWORD
    echo
  fi
  [[ -n "$BASIC_PASSWORD" ]] || {
    echo "Set JOSH_DEMO_BASIC_PASSWORD for authenticated public smoke" >&2
    return 2
  }
  JOSH_DEMO_URL="$url" JOSH_DEMO_BASIC_PASSWORD="$BASIC_PASSWORD" \
    JOSH_DEMO_MUTATE_ALERT="$mutate_alert" \
    python3 "$ROOT_DIR/deploy/demo/public_smoke.py"
}

stable_public_smoke() {
  local url="$1" elapsed=0 current mutate_alert=1
  while :; do
    current="$(fetch_url)" || return 1
    [[ "$current" == "$url" ]] || {
      echo "Quick Tunnel URL changed during stability check" >&2
      return 1
    }
    wait_for_basic_challenge "$url" || return 1
    public_smoke "$url" "$mutate_alert" || return 1
    mutate_alert=0
    (( elapsed >= STABILITY_SECONDS )) && break
    sleep 30
    elapsed=$((elapsed + 30))
  done
  remote_current record-public-smoke "$STABILITY_SECONDS" || return 1
  echo "Public smoke passed; URL remained stable for at least ${STABILITY_SECONDS}s: $url"
}

poll_url_dead() {
  local url="$1"
  [[ -n "$url" ]] || return
  for _ in $(seq 1 30); do
    if ! JOSH_DEMO_URL="$url" python3 - <<'PY' >/dev/null 2>&1
import os
import urllib.error
import urllib.request
try:
    urllib.request.urlopen(os.environ["JOSH_DEMO_URL"] + "/api/me", timeout=4)
except urllib.error.HTTPError as exc:
    raise SystemExit(1 if exc.code == 401 else 0)
except Exception:
    raise SystemExit(0)
raise SystemExit(1)
PY
    then sleep 2; else echo "Old Quick Tunnel URL is dead: $url"; return; fi
  done
  echo "Old Quick Tunnel URL still answers with the demo Basic challenge" >&2
  exit 1
}

case "$COMMAND" in
  bootstrap|deploy) deploy_release "$COMMAND" ;;
  reset)
    old_url="$(fetch_url 2>/dev/null || true)"; remote_current reset; poll_url_dead "$old_url"
    ;;
  smoke)
    remote_current smoke
    url="$(fetch_url)"
    if ! stable_public_smoke "$url"; then
      remote_current stop-tunnel || true
      echo "Public smoke failed; the project Quick Tunnel was stopped." >&2
      exit 1
    fi
    ;;
  status) remote_current status ;;
  start-tunnel)
    remote_current start-tunnel
    url="$(fetch_url)"
    if ! wait_for_basic_challenge "$url"; then
      remote_current stop-tunnel || true
      echo "Quick Tunnel challenge failed; the project tunnel was stopped." >&2
      exit 1
    fi
    echo "Tunnel challenge verified: $url"
    ;;
  stop)
    old_url="$(fetch_url 2>/dev/null || true)"; remote_current stop; poll_url_dead "$old_url"
    ;;
  teardown)
    old_url="$(fetch_url 2>/dev/null || true)"; remote_current teardown; poll_url_dead "$old_url"
    ;;
  rotate-password) remote_current rotate-password ;;
  *) usage >&2; exit 2 ;;
esac
