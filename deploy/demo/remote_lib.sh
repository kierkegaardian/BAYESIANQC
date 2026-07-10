#!/usr/bin/env bash

REMOTE_ROOT="${BAYESIANQC_REMOTE_ROOT:-/home/geoff/services/bayesianqc-josh-demo}"
PROJECT_NAME="bayesianqc-josh-demo"
SECRETS_DIR="$REMOTE_ROOT/secrets"
ENV_FILE="$SECRETS_DIR/app.env"
RUNTIME_DIR="$REMOTE_ROOT/runtime"
CURRENT_LINK="$REMOTE_ROOT/current"

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 2; }
}

validate_remote_root() {
  [[ "$REMOTE_ROOT" == /* && "$REMOTE_ROOT" != "/" && ! "$REMOTE_ROOT" =~ [[:space:]] ]] || {
    echo "BAYESIANQC_REMOTE_ROOT must be an absolute path without whitespace" >&2
    exit 2
  }
}

runtime_preflight() {
  validate_remote_root
  for command_name in docker python3 sha256sum tar ss; do
    require_command "$command_name"
  done
  docker compose version >/dev/null
  docker info >/dev/null
}

prepare_layout() {
  umask 077
  mkdir -p "$REMOTE_ROOT"/{incoming,releases,postgres,import-archive,backups} "$SECRETS_DIR" "$RUNTIME_DIR"
  chmod 700 "$SECRETS_DIR" "$RUNTIME_DIR" "$REMOTE_ROOT/import-archive"
}

stop_project_tunnel_containers() {
  local container_id
  while read -r container_id; do
    [[ -n "$container_id" ]] || continue
    docker container stop "$container_id" >/dev/null
    docker container rm "$container_id" >/dev/null
  done < <(docker ps -aq \
    --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter "label=com.docker.compose.service=cloudflared")
  if docker ps -q \
    --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter "label=com.docker.compose.service=cloudflared" | grep -q .; then
    echo "Project cloudflared container is still running" >&2
    return 1
  fi
  rm -f "$RUNTIME_DIR/tunnel-url.txt" "$RUNTIME_DIR/tunnel-started-at.txt"
}

require_demo_resources() {
  local free_kb available_kb
  free_kb="$(df -Pk "$REMOTE_ROOT" | awk 'NR==2 {print $4}')"
  available_kb="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
  if (( free_kb >= 10485760 && available_kb >= 2097152 )); then
    return 0
  fi
  (( free_kb >= 10485760 )) || echo "Demo host needs at least 10 GiB free" >&2
  (( available_kb >= 2097152 )) || echo "Demo host needs at least 2 GiB available RAM" >&2
  echo "Resource preflight failed; stopping only the project Quick Tunnel." >&2
  stop_project_tunnel_containers || return 1
  return 2
}

get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

set_env() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key, value = sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines() if path.exists() else []
replacement = f"{key}={value}"
for index, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[index] = replacement
        break
else:
    lines.append(replacement)
path.write_text("\n".join(lines) + "\n")
PY
  chmod 600 "$ENV_FILE"
}

random_token() {
  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

rotate_password() {
  local password hash
  password="BQC-$(random_token)"
  hash="$(printf '%s\n' "$password" | docker run --rm -i \
    caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648 \
    caddy hash-password)"
  set_env BAYESIANQC_BASIC_AUTH_HASH "${hash//\$/\$\$}"
  echo "Josh demo login (shown once; plaintext is not stored on internalserver)"
  echo "Username: josh"
  echo "Password: $password"
}

bootstrap_secrets() {
  [[ ! -s "$ENV_FILE" ]] || {
    echo "Demo secrets already exist; use deploy or rotate-password instead of bootstrap" >&2
    exit 2
  }
  : > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  set_env POSTGRES_PASSWORD "$(random_token)"
  set_env BAYESIANQC_BOOTSTRAP_API_KEY "$(random_token)"
  set_env BAYESIANQC_EDGE_API_KEY "$(random_token)"
  rotate_password
}

require_secrets() {
  [[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE; run bootstrap first" >&2; exit 2; }
  local key
  for key in POSTGRES_PASSWORD BAYESIANQC_BOOTSTRAP_API_KEY BAYESIANQC_EDGE_API_KEY BAYESIANQC_BASIC_AUTH_HASH; do
    [[ -n "$(get_env "$key")" ]] || { echo "Missing $key in $ENV_FILE" >&2; exit 2; }
  done
  chmod 600 "$ENV_FILE"
}

release_dir() {
  local release_id="${BAYESIANQC_RELEASE_ID:-}"
  [[ "$release_id" =~ ^[0-9a-f]{40}$ ]] || { echo "BAYESIANQC_RELEASE_ID must be a full Git SHA" >&2; exit 2; }
  printf '%s/releases/%s\n' "$REMOTE_ROOT" "$release_id"
}

current_release() {
  [[ -L "$CURRENT_LINK" ]] || { echo "No current demo release" >&2; exit 2; }
  local release
  release="$(readlink -f "$CURRENT_LINK")"
  [[ "$release" == "$REMOTE_ROOT"/releases/* ]] || { echo "Unsafe current release link" >&2; exit 2; }
  printf '%s\n' "$release"
}

compose() {
  local release="$1"; shift
  BAYESIANQC_RELEASE_ID="$(basename "$release")" \
  BAYESIANQC_REMOTE_ROOT="$REMOTE_ROOT" \
  BAYESIANQC_APP_UID="$(id -u)" BAYESIANQC_APP_GID="$(id -g)" \
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" \
      -f "$release/deploy/demo/docker-compose.yml" \
      -f "$release/deploy/demo/compose.quick-tunnel.yml" "$@"
}

wait_healthy() {
  local release="$1" service="$2" container_id=""
  for _ in $(seq 1 60); do
    container_id="$(compose "$release" ps -q "$service")"
    if [[ -n "$container_id" && "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id")" == "healthy" ]]; then
      return
    fi
    sleep 2
  done
  compose "$release" ps
  echo "$service did not become healthy" >&2
  exit 1
}

sync_database_password() {
  local release="$1" password
  password="$(get_env POSTGRES_PASSWORD)"
  [[ "$password" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Generated database password has unsafe characters" >&2; exit 2; }
  compose "$release" exec -T postgres psql -v ON_ERROR_STOP=1 \
    -U bayesianqc -d postgres >/dev/null <<SQL
ALTER ROLE bayesianqc WITH PASSWORD '$password';
SQL
}

run_migrations() { compose "$1" run --rm api alembic upgrade head; }
ensure_demo_keys() {
  compose "$1" run --rm \
    -e "BAYESIANQC_BOOTSTRAP_API_KEY=$(get_env BAYESIANQC_BOOTSTRAP_API_KEY)" \
    -e "BAYESIANQC_EDGE_API_KEY=$(get_env BAYESIANQC_EDGE_API_KEY)" \
    api python scripts/ensure_demo_keys.py
}

load_fixtures() {
  local release="$1"
  compose "$release" run --rm api python scripts/generate_demo_kiosk_fixtures.py --check
  compose "$release" run --rm \
    -e "BAYESIANQC_BOOTSTRAP_API_KEY=$(get_env BAYESIANQC_BOOTSTRAP_API_KEY)" \
    api sh -c \
    'BAYESIANQC_API_KEY="$BAYESIANQC_BOOTSTRAP_API_KEY" python scripts/load_chart_kiosk_suite.py --base-url http://api:8010 --suite demo'
  ensure_demo_keys "$release"
  compose "$release" run --rm api python scripts/curate_demo_state.py
}

capture_listeners() {
  ss -H -ltnu | awk '{print $1 " " $5}' | sort -u
}

save_listener_baseline() { capture_listeners > "$RUNTIME_DIR/listeners-before.txt"; }

assert_no_new_listeners() {
  [[ -f "$RUNTIME_DIR/listeners-before.txt" ]] || return
  capture_listeners > "$RUNTIME_DIR/listeners-after.txt"
  if comm -13 "$RUNTIME_DIR/listeners-before.txt" "$RUNTIME_DIR/listeners-after.txt" | grep -q .; then
    echo "Unexpected host listeners appeared:" >&2
    comm -13 "$RUNTIME_DIR/listeners-before.txt" "$RUNTIME_DIR/listeners-after.txt" >&2
    exit 1
  fi
}

assert_no_published_ports() {
  local container_id bindings
  while read -r container_id; do
    [[ -n "$container_id" ]] || continue
    bindings="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$container_id")"
    [[ "$bindings" == "null" || "$bindings" == "{}" ]] || { echo "Published ports detected on $container_id" >&2; exit 1; }
  done < <(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")
}

private_smoke() {
  local release="$1"
  compose "$release" exec -T -e "BAYESIANQC_EDGE_API_KEY=$(get_env BAYESIANQC_EDGE_API_KEY)" api python -c \
    'import http.client,os; c=http.client.HTTPConnection("api",8010,timeout=3); c.request("GET","/me",headers={"X-API-Key":os.environ["BAYESIANQC_EDGE_API_KEY"]}); r=c.getresponse(); b=r.read(); raise SystemExit(0 if r.status==200 and b.find(b"stakeholder")>=0 else 1)'
  compose "$release" exec -T api python -c \
    'import http.client; c=http.client.HTTPConnection("caddy",8080,timeout=3); c.request("GET","/api/me"); r=c.getresponse(); raise SystemExit(0 if r.status==401 and "Basic" in (r.getheader("WWW-Authenticate") or "") else 1)'
  assert_no_published_ports
  assert_no_new_listeners
  printf '%s private-smoke=pass release=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "$release")" > "$RUNTIME_DIR/private-smoke.txt"
}

backup_snapshot() {
  local release="$1" label="$2" target="$REMOTE_ROOT/backups/$label"
  mkdir -p "$target"
  compose "$release" exec -T postgres pg_dump -U bayesianqc -Fc bayesianqc > "$target/database.dump"
  tar -C "$REMOTE_ROOT/import-archive" -czf "$target/import-archive.tar.gz" .
  [[ -f "$release/RELEASE_MANIFEST.json" ]] && cp "$release/RELEASE_MANIFEST.json" "$target/"
  printf '%s\n' "$target"
}

write_checksums() {
  local target="$1"
  rm -f "$target/SHA256SUMS"
  (cd "$target" && sha256sum ./* > SHA256SUMS)
}

stop_tunnel() {
  local release="$1"
  compose "$release" stop cloudflared >/dev/null 2>&1 || true
  compose "$release" rm -f cloudflared >/dev/null 2>&1 || true
  stop_project_tunnel_containers
}

reset_data() {
  local release="$1" backup_target
  stop_tunnel "$release"
  compose "$release" up -d postgres
  wait_healthy "$release" postgres
  backup_target="$(backup_snapshot "$release" "pre-reset-$(date -u +%Y%m%dT%H%M%SZ)")"
  write_checksums "$backup_target"
  compose "$release" stop api >/dev/null 2>&1 || true
  compose "$release" exec -T postgres dropdb --force -U bayesianqc bayesianqc
  compose "$release" exec -T postgres createdb -U bayesianqc bayesianqc
  sync_database_password "$release"
  find "$REMOTE_ROOT/import-archive" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  run_migrations "$release"
  ensure_demo_keys "$release"
  compose "$release" up -d api web caddy
  wait_healthy "$release" api
  wait_healthy "$release" web
  wait_healthy "$release" caddy
  load_fixtures "$release"
  private_smoke "$release"
}

record_release_manifest() {
  local release="$1" archive_sha="$2"
  python3 "$release/deploy/demo/release_manifest.py" \
    --release "$release" --archive-sha256 "$archive_sha"
}

start_tunnel() {
  local release="$1" url=""
  private_smoke "$release"
  stop_tunnel "$release"
  compose "$release" up -d cloudflared
  for _ in $(seq 1 40); do
    url="$(compose "$release" logs --no-color cloudflared 2>&1 | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
    [[ -n "$url" ]] && break
    sleep 2
  done
  [[ -n "$url" ]] || { compose "$release" logs cloudflared; echo "Quick Tunnel URL not found" >&2; exit 1; }
  printf '%s\n' "$url" > "$RUNTIME_DIR/tunnel-url.txt"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$RUNTIME_DIR/tunnel-started-at.txt"
  echo "Josh demo URL: $url"
}
