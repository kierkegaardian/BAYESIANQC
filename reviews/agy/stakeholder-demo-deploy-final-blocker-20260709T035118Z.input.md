# BAYESIANQC stakeholder demo deployment final blocker check
Latest validation: bash -n scripts passed; pytest tests/test_deployment_runtime.py 11 passed; Caddy validate passed; exact Compose probe with the same app.env passed: app.env HASH=$$2a$$14$$abc$$def, docker compose --env-file app.env plus service env_file delivered $2a$14$abc$def inside the container; git diff --check passed.
Latest fixes after prior review: Caddyfile blocks /api/docs*, /api/redoc*, /api/openapi.json*; Caddyfile site label includes http://caddy for internal smoke; rollback updates CURRENT_LINK before ensure_edge_admin_key and does not run old Alembic migrations; runbook documents rollback reset-data, no API docs exposure, shared edge-admin audit attribution, SSH host-key prerequisite.
Please verify only remaining P0/P1 blockers. Do not repeat the bcrypt $$ finding unless you can reconcile it with the included exact docker compose probe result.

## FILE scripts/demo_vps.sh
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

## FILE deploy/demo-vps/remote.sh
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
  python3 - <<'PY'
from __future__ import annotations

import secrets

alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
print("".join(secrets.choice(alphabet) for _ in range(24)))
PY
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
    if compose "$release" exec -T api python - <<'PY' >/dev/null 2>&1
from __future__ import annotations

import os
import urllib.request

request = urllib.request.Request(
    "http://api:8010/me",
    headers={"X-API-Key": os.environ["BAYESIANQC_EDGE_ADMIN_API_KEY"]},
)
with urllib.request.urlopen(request, timeout=3) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
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
    if compose "$release" exec -T api python - <<'PY' >/dev/null 2>&1
from __future__ import annotations

import urllib.error
import urllib.request

try:
    urllib.request.urlopen("http://caddy/api/me", timeout=3)
except urllib.error.HTTPError as exc:
    challenge = exc.headers.get("WWW-Authenticate", "")
    raise SystemExit(0 if exc.code == 401 and "Basic" in challenge else 1)
except Exception:
    raise SystemExit(1)
raise SystemExit(1)
PY
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

## FILE deploy/demo-vps/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: bayesianqc
      POSTGRES_USER: bayesianqc
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    volumes:
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bayesianqc -d bayesianqc"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    image: bayesianqc-demo-api:${BAYESIANQC_RELEASE_ID:-local}
    build:
      context: ../..
      dockerfile: deploy/demo-vps/Dockerfile.api
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/secrets/app.env
    environment:
      BAYESIANQC_DB_URL: postgresql+psycopg://bayesianqc:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/bayesianqc
      BAYESIANQC_IMPORT_ARCHIVE_ROOT: /var/lib/bayesianqc/import-archive
      BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT: "1"
      BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP: "0"
    volumes:
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/import-archive:/var/lib/bayesianqc/import-archive
    expose:
      - "8010"

  web:
    image: bayesianqc-demo-web:${BAYESIANQC_RELEASE_ID:-local}
    build:
      context: ../..
      dockerfile: deploy/demo-vps/Dockerfile.web
      args:
        VITE_API_URL: /api
        VITE_AUTH_MODE: edge-basic
    expose:
      - "80"

  caddy:
    image: caddy:2.8-alpine
    depends_on:
      - api
      - web
    env_file:
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/secrets/app.env
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/caddy/data:/data
      - ${BAYESIANQC_REMOTE_ROOT:-/srv/bayesianqc}/caddy/config:/config

## FILE deploy/demo-vps/Caddyfile
{$BAYESIANQC_DOMAIN}, http://caddy {
	encode zstd gzip

	basic_auth {
		admin {$BAYESIANQC_BASIC_AUTH_HASH}
	}

	handle /api/docs* {
		respond 404
	}

	handle /api/redoc* {
		respond 404
	}

	handle /api/openapi.json* {
		respond 404
	}

	handle_path /api/* {
		reverse_proxy api:8010 {
			header_up X-API-Key {$BAYESIANQC_EDGE_ADMIN_API_KEY}
		}
	}

	handle {
		reverse_proxy web:80
	}
}

## FILE docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md
# Stakeholder Demo Docker-Host Deployment

This runbook deploys BAYESIANQC as a synthetic-data stakeholder demo at
`qc.geoffsmiscellany.com`. The existing geoffsmiscellany Webhosting Hub account is
shared cPanel/static hosting, so it remains a domain/front-door asset only. The
FastAPI app, Postgres database, frontend, Caddy proxy, and import archive run on
a Docker-capable Linux host: a VPS if one is available, or an existing owned host
that can receive public HTTP/HTTPS traffic through DNS, port forwarding, or a
tunnel/static-pointer setup.

## Model

- Public URL: `https://qc.geoffsmiscellany.com`
- Browser login: HTTP Basic Auth with username `admin`
- Password: generated during bootstrap or rotation and printed once
- App auth: Caddy injects a hidden admin `X-API-Key` only for `/api/*`
- Data: deterministic synthetic demo reset; stakeholder edits are disposable
- Runtime root: `/srv/bayesianqc`
- Release source: committed Git `HEAD` only

No plaintext stakeholder password is stored in the repo or remote env files.
Caddy stores only the password hash. The hidden edge admin API key is stored in
`/srv/bayesianqc/secrets/app.env` with owner-only permissions.

## Host Prerequisites

- Ubuntu LTS or equivalent Linux host with outbound internet access.
- SSH key access for the deploy operator.
- The operator has connected once with `ssh <ssh-host>` and accepted the host key.
- Docker Engine and Docker Compose plugin installed.
- Firewall allows only SSH, HTTP, and HTTPS from the internet.
- DNS or tunnel routing sends `qc.geoffsmiscellany.com` to this host.
- Deploy operator can write `/srv/bayesianqc`.
- The BAYESIANQC worktree is clean and committed before bootstrap/deploy.

Use `DEMO_VPS_SKIP_PUBLIC_SMOKE=1` only for a private rehearsal before DNS or the
tunnel/static pointer is live. The real Josh walkthrough should leave public
smoke enabled.

## Commands

Bootstrap the first release, load synthetic demo data, and print the one-time
stakeholder password:

```bash
make demo-vps-bootstrap DEMO_VPS_HOST=<ssh-host>
```

Deploy committed code changes without resetting stakeholder edits:

```bash
make demo-vps-deploy DEMO_VPS_HOST=<ssh-host>
```

Reset remote demo data from deterministic synthetic fixtures:

```bash
make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>
```

Rotate the stakeholder password and reload Caddy:

```bash
make demo-vps-rotate-password DEMO_VPS_HOST=<ssh-host>
```

Run remote smoke checks:

```bash
make demo-vps-smoke DEMO_VPS_HOST=<ssh-host>
```

Roll back code to a previous release id:

```bash
make demo-vps-rollback DEMO_VPS_HOST=<ssh-host> DEMO_VPS_RELEASE_ID=<release-id>
```

Optional variables:

```bash
DEMO_VPS_DOMAIN=qc.geoffsmiscellany.com
DEMO_VPS_REMOTE_ROOT=/srv/bayesianqc
DEMO_VPS_SSH_KEY=/path/to/key
DEMO_VPS_SKIP_PUBLIC_SMOKE=1
```

## Release Behavior

`demo-vps-deploy` refuses dirty worktrees so the remote release matches a
committed SHA. The script uploads a `git archive` bundle, builds API/UI images
on the remote host, runs Alembic explicitly, ensures the hidden edge admin API
key is present in the database, restarts the stack, and runs smoke checks.

`demo-vps-bootstrap` uses the same deploy path, then loads the deterministic
synthetic demo suite. It does not load real lab/customer data.

`demo-vps-reset-data` creates a timestamped Postgres dump before destructive
reset, recreates the database, clears the demo import archive, re-runs
migrations, re-seeds the edge admin API key, and reloads the synthetic demo
suite.

`demo-vps-rotate-password` prints a fresh one-time stakeholder password and
force-recreates Caddy so the new password hash is active immediately.

`demo-vps-rollback` switches code/images back to a prior release id but does not
run Alembic downgrade or upgrade steps from the older release. If the rollback
crosses database migrations, run `make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>`
immediately after rollback to recreate the disposable synthetic schema and
fixtures under the rolled-back code.

Smoke checks are split intentionally: the remote helper verifies Postgres, the
API container, and Caddy's internal Basic Auth challenge; the local wrapper then
checks public `https://qc.geoffsmiscellany.com/api/me` from the operator machine
so the result matches the stakeholder path instead of a host hairpin path.

## Acceptance Checks

- Unauthenticated browser access returns a Basic Auth prompt.
- `admin` plus the generated password opens the UI.
- Internal `/me` resolves as role `admin` through the hidden edge API key.
- Public `/api/me` returns a Basic Auth challenge when unauthenticated.
- Direct API and Postgres ports are not exposed publicly.
- `/kiosk/demo`, `/charts`, `/imports`, and `/audit` load after reset.
- FastAPI `/docs`, `/redoc`, `/openapi.json`, and their `/api/*` proxy forms
  are intentionally not exposed through the public demo proxy; the demo is a UI
  walkthrough, not an API sandbox.
- `make import-restore-proof` passes when pointed at the remote DB/archive
  during a production-readiness rehearsal.

## Josh Walkthrough Runbook

1. Commit the deploy slice and confirm the target host routes
   `qc.geoffsmiscellany.com` over HTTPS.
2. Run `make demo-vps-bootstrap DEMO_VPS_HOST=<ssh-host>` for first setup, or
   `make demo-vps-deploy DEMO_VPS_HOST=<ssh-host>` for committed code updates.
3. Run `make demo-vps-reset-data DEMO_VPS_HOST=<ssh-host>` the morning of the
   walkthrough so screenshots, edits, imports, and comments start from known
   synthetic data.
4. Run `make demo-vps-smoke DEMO_VPS_HOST=<ssh-host>` and keep the output with
   the demo notes.
5. Share only `https://qc.geoffsmiscellany.com`, username `admin`, and the
   current generated password. Do not share the hidden edge API key.
6. After the walkthrough, run `make demo-vps-rotate-password
   DEMO_VPS_HOST=<ssh-host>` or shut down the host/tunnel.

All stakeholder actions in this demo are attributed to one shared edge-admin API
key in the backend audit log. That is acceptable for the Josh walkthrough only;
it is not a multi-user production auth model.

## Boundaries

This is not a shared-lab production deployment. It is a stakeholder demo using
synthetic data and a shared admin credential. Rotate the stakeholder password
after the demo, prune old release images when disk pressure appears, and do not
load real lab/customer data without the production validation package and SME
expected-row signoff.

## FILE tests/test_deployment_runtime.py
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from app.db import run_migrations_on_startup

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_run_migrations_on_startup_defaults_enabled(monkeypatch):
    monkeypatch.delenv("BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP", raising=False)

    assert run_migrations_on_startup() is True


def test_run_migrations_on_startup_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP", "0")

    assert run_migrations_on_startup() is False


def test_run_migrations_on_startup_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP", "yes")

    assert run_migrations_on_startup() is True


def test_demo_vps_scripts_have_valid_bash_syntax():
    for script in ["scripts/demo_vps.sh", "deploy/demo-vps/remote.sh"]:
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)


def test_demo_vps_wrapper_validates_help_and_missing_values():
    help_result = subprocess.run(
        ["bash", str(ROOT / "scripts/demo_vps.sh"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "bootstrap|deploy|reset-data|rotate-password|smoke|rollback" in help_result.stdout

    missing_host = subprocess.run(
        ["bash", str(ROOT / "scripts/demo_vps.sh"), "smoke", "--host"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_host.returncode == 2
    assert "--host requires a value" in missing_host.stderr


def test_demo_vps_make_targets_are_wired_to_public_smoke_knob():
    makefile = _read("Makefile")
    for target in [
        "demo-vps-bootstrap",
        "demo-vps-deploy",
        "demo-vps-reset-data",
        "demo-vps-rotate-password",
        "demo-vps-smoke",
        "demo-vps-rollback",
    ]:
        assert f"{target}:" in makefile
    assert "DEMO_VPS_SKIP_PUBLIC_SMOKE" in makefile
    assert "--skip-public-smoke" in makefile


def test_demo_compose_keeps_backend_private_and_requires_archive():
    compose = _read("deploy/demo-vps/docker-compose.yml")
    postgres_section = _section(compose, "  postgres:\n", "\n\n  api:\n")
    api_section = _section(compose, "  api:\n", "\n\n  web:\n")
    caddy_section = _section(compose, "  caddy:\n", "\n")

    assert "ports:" not in postgres_section
    assert "ports:" not in api_section
    assert 'expose:\n      - "8010"' in api_section
    assert "image: bayesianqc-demo-api:${BAYESIANQC_RELEASE_ID:-local}" in api_section
    assert "image: bayesianqc-demo-web:${BAYESIANQC_RELEASE_ID:-local}" in compose
    assert 'BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT: "1"' in api_section
    assert 'BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP: "0"' in api_section
    assert '      - "80:80"' in compose
    assert '      - "443:443"' in compose
    assert "image: caddy:2.8-alpine" in caddy_section


def test_demo_caddy_requires_basic_auth_and_injects_edge_api_key():
    caddyfile = _read("deploy/demo-vps/Caddyfile")

    assert "{$BAYESIANQC_DOMAIN}, http://caddy" in caddyfile
    assert "basic_auth" in caddyfile
    assert "admin {$BAYESIANQC_BASIC_AUTH_HASH}" in caddyfile
    assert "handle /api/docs*" in caddyfile
    assert "handle /api/redoc*" in caddyfile
    assert "handle /api/openapi.json*" in caddyfile
    assert "handle_path /api/*" in caddyfile
    assert "header_up X-API-Key {$BAYESIANQC_EDGE_ADMIN_API_KEY}" in caddyfile


def test_remote_helper_bootstrap_reset_rollback_and_smoke_contracts():
    remote = _read("deploy/demo-vps/remote.sh")
    rollback_section = _section(remote, "rollback() {\n", "\n}\n\ncheck_prereqs")

    assert 'if [[ "$COMMAND" == "bootstrap" ]]' in remote
    assert 'load_demo_fixtures "$release"' in remote
    assert 'hash="${hash//\\$/\\$\\$}"' in remote
    assert 'backup="$REMOTE_ROOT/backups/pre-reset-${stamp}.dump"' in remote
    assert "dropdb --force -U bayesianqc bayesianqc" in remote
    assert "clear_import_archive" in remote
    assert "find /var/lib/bayesianqc/import-archive" in remote
    assert "release_images_exist" in remote
    assert 'if ! release_images_exist "$release"; then' in remote
    assert "run_migrations" not in rollback_section
    assert 'ln -sfn "$release" "$CURRENT_LINK"' in rollback_section
    assert rollback_section.index('ln -sfn "$release" "$CURRENT_LINK"') < rollback_section.index("ensure_edge_admin_key")
    assert "wait_for_caddy_basic_auth" in remote


def test_local_wrapper_owns_public_smoke_check():
    wrapper = _read("scripts/demo_vps.sh")

    assert "public_basic_auth_smoke" in wrapper
    assert "https://$DOMAIN/api/me" in wrapper
    assert "--skip-public-smoke" in wrapper
    assert "BAYESIANQC_SKIP_PUBLIC_SMOKE" in wrapper


def test_edge_admin_key_script_rejects_missing_secret():
    env = {key: value for key, value in os.environ.items() if key != "BAYESIANQC_EDGE_ADMIN_API_KEY"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ensure_edge_admin_key.py")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "BAYESIANQC_EDGE_ADMIN_API_KEY is required" in result.stderr
