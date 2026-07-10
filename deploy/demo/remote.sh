#!/usr/bin/env bash
set -euo pipefail

COMMAND="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/remote_lib.sh"

usage() {
  echo "Usage: $0 <bootstrap|deploy|reset|smoke|status|start-tunnel|stop-tunnel|stop|teardown|rotate-password>" >&2
}

deploy_release() {
  local mode="$1" release archive expected_sha old_release=""
  runtime_preflight
  prepare_layout
  require_demo_resources
  release="$(release_dir)"
  archive="${BAYESIANQC_ARCHIVE:-}"
  expected_sha="${BAYESIANQC_ARCHIVE_SHA256:-}"
  [[ -f "$archive" && "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || {
    echo "BAYESIANQC_ARCHIVE and its SHA-256 are required" >&2
    exit 2
  }
  echo "$expected_sha  $archive" | sha256sum -c -
  if [[ "$mode" == "bootstrap" ]]; then
    if [[ -s "$ENV_FILE" && -L "$CURRENT_LINK" ]]; then
      echo "A bootstrapped demo already exists; use deploy instead" >&2
      exit 2
    elif [[ -s "$ENV_FILE" ]]; then
      require_secrets
      rotate_password
    else
      bootstrap_secrets
    fi
  else
    require_secrets
  fi
  save_listener_baseline
  [[ -L "$CURRENT_LINK" ]] && old_release="$(current_release)"
  [[ -z "$old_release" ]] || stop_tunnel "$old_release"
  rm -rf "$release"
  mkdir -p "$release"
  tar -xzf "$archive" -C "$release"
  [[ -f "$release/deploy/demo/docker-compose.yml" ]] || { echo "Invalid release archive" >&2; exit 2; }
  compose "$release" build api web
  compose "$release" pull --policy missing postgres caddy cloudflared
  record_release_manifest "$release" "$expected_sha"
  compose "$release" up -d postgres
  wait_healthy "$release" postgres
  sync_database_password "$release"
  reset_data "$release"
  ln -sfn "$release" "$CURRENT_LINK"
  echo "Deployed release SHA: $(basename "$release")"
  echo "Release manifest: $release/RELEASE_MANIFEST.json"
}

show_status() {
  runtime_preflight
  echo "Compose project: $PROJECT_NAME"
  if [[ -L "$CURRENT_LINK" ]]; then
    local release
    release="$(current_release)"
    echo "Release SHA: $(basename "$release")"
    [[ -f "$release/RELEASE_MANIFEST.json" ]] && cat "$release/RELEASE_MANIFEST.json"
    if [[ -f "$ENV_FILE" ]]; then
      compose "$release" ps
    else
      echo "Secrets removed; project is expected to be torn down."
      docker ps -a --filter "label=com.docker.compose.project=$PROJECT_NAME"
    fi
  else
    echo "No current release."
  fi
  [[ -f "$RUNTIME_DIR/tunnel-url.txt" ]] && echo "Tunnel URL: $(cat "$RUNTIME_DIR/tunnel-url.txt")"
  [[ -f "$RUNTIME_DIR/tunnel-started-at.txt" ]] && echo "Tunnel started: $(cat "$RUNTIME_DIR/tunnel-started-at.txt")"
  [[ -f "$RUNTIME_DIR/public-smoke.txt" ]] && cat "$RUNTIME_DIR/public-smoke.txt"
  return 0
}

record_public_smoke() {
  local stability_seconds="$1" release url
  [[ "$stability_seconds" =~ ^[0-9]+$ && "$stability_seconds" -ge 900 ]] || {
    echo "Refusing to record public smoke without at least 900 stability seconds" >&2
    return 2
  }
  release="$(current_release)"
  [[ -f "$RUNTIME_DIR/tunnel-started-at.txt" ]] || {
    echo "Cannot record public smoke without a tunnel start timestamp" >&2
    return 2
  }
  python3 - "$RUNTIME_DIR/tunnel-started-at.txt" "$stability_seconds" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys

started_at = datetime.fromisoformat(Path(sys.argv[1]).read_text().strip().replace("Z", "+00:00"))
required_seconds = int(sys.argv[2])
elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
if elapsed_seconds < required_seconds:
    raise SystemExit(
        f"tunnel age {elapsed_seconds:.1f}s is below required {required_seconds}s"
    )
PY
  url="$(cat "$RUNTIME_DIR/tunnel-url.txt")"
  printf '%s public-smoke=pass release=%s url=%s stability_seconds=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "$release")" "$url" \
    "$stability_seconds" > "$RUNTIME_DIR/public-smoke.txt"
}

project_release_from_labels() {
  local container_id config_files release
  while read -r container_id; do
    [[ -n "$container_id" ]] || continue
    config_files="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' "$container_id")"
    release="${config_files%%/deploy/demo/docker-compose.yml*}"
    if [[ "$release" == "$REMOTE_ROOT"/releases/* && -f "$release/deploy/demo/docker-compose.yml" ]]; then
      printf '%s\n' "$release"
      return 0
    fi
  done < <(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")
  return 1
}

remove_project_containers_by_label() {
  local container_id
  while read -r container_id; do
    [[ -n "$container_id" ]] || continue
    docker container stop "$container_id" >/dev/null 2>&1 || true
    docker container rm "$container_id" >/dev/null
  done < <(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")
}

teardown_demo() {
  local release url="none" started="unknown" ended target
  runtime_preflight
  require_secrets
  if ! release="$(current_release 2>/dev/null)"; then
    release="$(project_release_from_labels)" || {
      stop_project_tunnel_containers
      remove_project_containers_by_label
      rm -f "$ENV_FILE"
      echo "No recoverable release metadata; removed only project-labeled containers without a snapshot." >&2
      return 0
    }
    echo "Recovered demo release from project container labels: $release" >&2
  fi
  [[ -f "$RUNTIME_DIR/tunnel-url.txt" ]] && url="$(cat "$RUNTIME_DIR/tunnel-url.txt")"
  [[ -f "$RUNTIME_DIR/tunnel-started-at.txt" ]] && started="$(cat "$RUNTIME_DIR/tunnel-started-at.txt")"
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  stop_tunnel "$release"
  target="$(backup_snapshot "$release" "teardown-$(date -u +%Y%m%dT%H%M%SZ)")"
  {
    echo "release_sha=$(basename "$release")"
    echo "url=$url"
    echo "started_at=$started"
    echo "ended_at=$ended"
    [[ -f "$RUNTIME_DIR/private-smoke.txt" ]] && cat "$RUNTIME_DIR/private-smoke.txt"
    [[ -f "$RUNTIME_DIR/public-smoke.txt" ]] && cat "$RUNTIME_DIR/public-smoke.txt"
    echo "retention=retain_stopped_snapshot_for_7_days_pending_explicit_purge_approval"
  } > "$target/DEMO_RECORD.txt"
  write_checksums "$target"
  compose "$release" down --remove-orphans
  rm -f "$ENV_FILE"
  if docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME" | grep -q .; then
    echo "Project-labeled containers remain after teardown" >&2
    exit 1
  fi
  assert_no_new_listeners
  echo "Teardown snapshot: $target"
  echo "Retain for seven days; purge only with explicit approval."
  echo "Stopped tunnel URL: $url"
}

case "$COMMAND" in
  bootstrap|deploy) deploy_release "$COMMAND" ;;
  reset)
    runtime_preflight; prepare_layout; require_secrets; save_listener_baseline
    require_demo_resources
    reset_data "$(current_release)"
    ;;
  smoke)
    runtime_preflight; require_secrets; private_smoke "$(current_release)"
    echo "Private smoke passed."
    ;;
  status) show_status ;;
  start-tunnel)
    runtime_preflight; require_secrets; require_demo_resources
    start_tunnel "$(current_release)"
    ;;
  stop-tunnel)
    runtime_preflight; require_secrets; stop_tunnel "$(current_release)"
    ;;
  stop)
    runtime_preflight; require_secrets
    release="$(current_release)"; stop_tunnel "$release"; compose "$release" stop
    ;;
  teardown) teardown_demo ;;
  rotate-password)
    runtime_preflight; require_secrets; rotate_password
    release="$(current_release)"; compose "$release" up -d --force-recreate caddy; wait_healthy "$release" caddy
    ;;
  record-public-smoke) record_public_smoke "${2:-}" ;;
  url) [[ -f "$RUNTIME_DIR/tunnel-url.txt" ]] && cat "$RUNTIME_DIR/tunnel-url.txt" ;;
  *) usage; exit 2 ;;
esac
