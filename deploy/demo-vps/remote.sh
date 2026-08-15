#!/usr/bin/env bash
set -euo pipefail

COMMAND="${1:-}"
REMOTE_ROOT="${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}"
DOMAIN="${BAYESIANQC_DOMAIN:-qc.geoffsmiscellany.com}"
SECRETS_DIR="$REMOTE_ROOT/secrets"
ENV_FILE="$SECRETS_DIR/app.env"
CURRENT_LINK="$REMOTE_ROOT/current"
PROJECT_NAME="bayesianqc-demo"

usage() {
  echo "Usage: $0 <bootstrap|deploy|reset-data|rotate-password|smoke|rollback>" >&2
}
mkdir -p "$REMOTE_ROOT"/{incoming,releases,postgres,import-archive,backups,caddy/data,caddy/config} "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command on remote host: $command_name" >&2
    exit 2
  fi
}
check_prereqs() {
  require_command docker
  require_command python3
  require_command tar
  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required on the remote host." >&2
    exit 2
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is not reachable for this deploy user." >&2
    exit 2
  fi
}
get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}
set_env() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
line = f"{key}={value}\n"
lines = path.read_text().splitlines(keepends=True) if path.exists() else []
for index, existing in enumerate(lines):
    if existing.startswith(f"{key}="):
        lines[index] = line
        break
else:
    lines.append(line)
path.write_text("".join(lines))
PY
  chmod 600 "$ENV_FILE"
}
random_token() {
  python3 -c 'import secrets; alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"; print("".join(secrets.choice(alphabet) for _ in range(24)))'
}
caddy_hash_password() {
  local password="$1"
  docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "$password"
}
ensure_secret() {
  local key="$1" value
  value="$(get_env "$key")"
  if [[ -z "$value" ]]; then
    set_env "$key" "$(random_token)"
  fi
}
rotate_password() {
  local password hash
  password="BQC-$(random_token)"
  hash="$(caddy_hash_password "$password")"
  hash="${hash//\$/\$\$}"
  set_env BAYESIANQC_BASIC_AUTH_HASH "$hash"
  echo "Stakeholder demo login"
  echo "URL: https://$DOMAIN"
  echo "Username: admin"
  echo "Password: $password"
  echo "Rotate this password after the demo."
}
ensure_secrets() {
  set_env BAYESIANQC_DOMAIN "$DOMAIN"
  set_env BAYESIANQC_REMOTE_ROOT "$REMOTE_ROOT"
  ensure_secret POSTGRES_PASSWORD
  ensure_secret BAYESIANQC_EDGE_ADMIN_API_KEY
  if [[ -z "$(get_env BAYESIANQC_BASIC_AUTH_HASH)" ]]; then
    rotate_password
  fi
}

release_dir() {
  local release_id="${BAYESIANQC_RELEASE_ID:-}"
  if [[ -z "$release_id" ]]; then
    echo "BAYESIANQC_RELEASE_ID is required" >&2
    exit 2
  fi
  printf '%s/releases/%s\n' "$REMOTE_ROOT" "$release_id"
}

compose_file_for() {
  printf '%s/deploy/demo-vps/docker-compose.yml\n' "$1"
}

compose() {
  local release="$1"
  local release_id
  release_id="$(basename "$release")"
  shift
  BAYESIANQC_RELEASE_ID="$release_id" BAYESIANQC_REMOTE_ROOT="$REMOTE_ROOT" docker compose \
    --env-file "$ENV_FILE" \
    -p "$PROJECT_NAME" \
    -f "$(compose_file_for "$release")" \
    "$@"
}

current_release() {
  if [[ ! -L "$CURRENT_LINK" ]]; then
    echo "No current release at $CURRENT_LINK" >&2
    exit 2
  fi
  readlink -f "$CURRENT_LINK"
}

wait_for_postgres() {
  local release="$1"
  for _ in $(seq 1 40); do
    if compose "$release" exec -T postgres pg_isready -U bayesianqc -d bayesianqc >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  echo "Postgres did not become ready." >&2
  exit 1
}

run_migrations() {
  local release="$1"
  compose "$release" run --rm api alembic upgrade head
}

ensure_edge_admin_key() {
  local release="$1"
  compose "$release" run --rm api python scripts/ensure_edge_admin_key.py
}

clear_import_archive() {
  local release="$1"
  compose "$release" run --rm api sh -c \
    'find /var/lib/bayesianqc/import-archive -mindepth 1 -maxdepth 1 -exec rm -rf {} +'
}

load_demo_fixtures() {
  local release="$1"
  wait_for_api "$release"
  compose "$release" run --rm api python scripts/generate_demo_kiosk_fixtures.py --check
  compose "$release" run --rm api sh -c \
    'BAYESIANQC_API_KEY="$BAYESIANQC_EDGE_ADMIN_API_KEY" python scripts/load_chart_kiosk_suite.py --base-url http://api:8010 --suite demo'
}

deploy_release() {
  ensure_secrets
  local release archive
  release="$(release_dir)"
  archive="${BAYESIANQC_ARCHIVE:-}"
  if [[ -z "$archive" || ! -f "$archive" ]]; then
    echo "BAYESIANQC_ARCHIVE must point to an uploaded release archive" >&2
    exit 2
  fi
  rm -rf "$release"
  mkdir -p "$release"
  tar -xzf "$archive" -C "$release"
  compose "$release" build
  compose "$release" up -d postgres
  wait_for_postgres "$release"
  run_migrations "$release"
  ensure_edge_admin_key "$release"
  compose "$release" up -d api web caddy
  if [[ "$COMMAND" == "bootstrap" ]]; then
    load_demo_fixtures "$release"
  fi
  smoke_release "$release"
  ln -sfn "$release" "$CURRENT_LINK"
  echo "Deployed $release"
}

backup_db() {
  local release="$1" stamp backup
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="$REMOTE_ROOT/backups/pre-reset-${stamp}.dump"
  compose "$release" exec -T postgres pg_dump -U bayesianqc -Fc bayesianqc > "$backup"
  echo "DB backup: $backup"
}

reset_data() {
  ensure_secrets
  local release
  release="$(current_release)"
  compose "$release" up -d postgres
  wait_for_postgres "$release"
  backup_db "$release"
  compose "$release" stop api >/dev/null 2>&1 || true
  compose "$release" exec -T postgres dropdb --force -U bayesianqc bayesianqc
  compose "$release" exec -T postgres createdb -U bayesianqc bayesianqc
  clear_import_archive "$release"
  run_migrations "$release"
  ensure_edge_admin_key "$release"
  compose "$release" up -d api web caddy
  load_demo_fixtures "$release"
  smoke_release "$release"
}

wait_for_api() {
  local release="$1"
  for _ in $(seq 1 40); do
    if compose "$release" exec -T api python -c 'import http.client, os; c = http.client.HTTPConnection("api", 8010, timeout=3); c.request("GET", "/me", headers={"X-API-Key": os.environ["BAYESIANQC_EDGE_ADMIN_API_KEY"]}); r = c.getresponse(); raise SystemExit(0 if r.status == 200 else 1)' >/dev/null 2>&1
    then
      return
    fi
    sleep 1
  done
  echo "API did not become ready." >&2
  exit 1
}

wait_for_caddy_basic_auth() {
  local release="$1"
  for _ in $(seq 1 40); do
    if compose "$release" exec -T api python -c 'import http.client; c = http.client.HTTPConnection("caddy", 80, timeout=3); c.request("GET", "/api/me"); r = c.getresponse(); raise SystemExit(0 if r.status == 401 and "Basic" in (r.getheader("WWW-Authenticate") or "") else 1)' >/dev/null 2>&1
    then
      return
    fi
    sleep 1
  done
  echo "Caddy did not present a Basic Auth challenge for /api/me." >&2
  exit 1
}

smoke_release() {
  local release="$1"
  compose "$release" ps
  wait_for_postgres "$release"
  wait_for_api "$release"
  wait_for_caddy_basic_auth "$release"
}

release_images_exist() {
  local release="$1"
  local release_id
  release_id="$(basename "$release")"
  docker image inspect "bayesianqc-demo-api:$release_id" "bayesianqc-demo-web:$release_id" >/dev/null 2>&1
}

rollback() {
  ensure_secrets
  local release
  release="$(release_dir)"
  if [[ ! -d "$release" ]]; then
    echo "Release not found: $release" >&2
    exit 2
  fi
  if ! release_images_exist "$release"; then
    compose "$release" build
  fi
  ln -sfn "$release" "$CURRENT_LINK"
  compose "$release" up -d postgres
  wait_for_postgres "$release"
  ensure_edge_admin_key "$release"
  compose "$release" up -d api web caddy
  smoke_release "$release"
}

check_prereqs

case "$COMMAND" in
  bootstrap|deploy) deploy_release ;;
  reset-data) reset_data ;;
  rotate-password)
    ensure_secrets
    rotate_password
    if [[ -L "$CURRENT_LINK" ]]; then
      compose "$(current_release)" up -d --force-recreate caddy
      wait_for_caddy_basic_auth "$(current_release)"
    fi
    ;;
  smoke) smoke_release "$(current_release)" ;;
  rollback) rollback ;;
  *) usage; exit 2 ;;
esac
