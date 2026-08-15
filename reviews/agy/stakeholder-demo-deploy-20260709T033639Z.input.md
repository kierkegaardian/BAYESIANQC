# BAYESIANQC stakeholder demo deployment review packet
Scope: review the password-protected synthetic-data demo deploy path for qc.geoffsmiscellany.com.
Validation already run: bash -n scripts, scripts/demo_vps.sh --help, make -n demo-vps targets, docker compose config with temp remote root, Caddy validate, make lint, make typecheck, make build, pytest tests/test_deployment_runtime.py, full make test (84 passed), git diff --check.
Known baseline: worktree contains unrelated pre-existing dirty BAYESIANQC changes; review this packet for deployment/auth/runbook blockers only.
Files in scope: Makefile, README.md stakeholder-demo link, scripts/demo_vps.sh, scripts/ensure_edge_admin_key.py, deploy/demo-vps/*, docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md, tests/test_deployment_runtime.py.

## Git status
## codex/import-readiness-production-fixes
 M Makefile
 M README.md
 M app/db.py
 M app/db_models.py
 M app/main.py
 M app/models.py
 M app/routers/stream_setups.py
 M app/services/stream_setup_assets.py
 M app/services/stream_setups.py
 M app/storage.py
 M app/stream_setup_models.py
 M frontend/src/api/client.ts
 M frontend/src/api/contracts.ts
 M frontend/src/api/schema.ts
 M frontend/src/components/AppLayout.vue
 M frontend/src/pages/DatastreamSetup.vue
 M frontend/src/pages/datastreamSetup.ts
 M frontend/src/router/index.ts
 M migrations/versions/20260703_0001_initial_sqlmodel_schema.py
 M scripts/rehearse_sqlite_to_postgres.py
 M tests/conftest.py
 M tests/test_access_scopes.py
 M tests/test_migrations.py
?? .dockerignore
?? app/routers/locations.py
?? app/routers/tests.py
?? app/services/locations.py
?? deploy/
?? docs/DEPLOYMENT_DEFAULTS_CONFIG_PLAN.md
?? docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md
?? frontend/src/pages/ConfigCreate.vue
?? frontend/src/pages/DatastreamPreviewTable.vue
?? frontend/src/pages/datastreamOptions.ts
?? migrations/versions/20260704_0007_location_config.py
?? reports/
?? scripts/demo_vps.sh
?? scripts/ensure_edge_admin_key.py
?? tests/test_deployment_runtime.py
?? tests/test_location_config.py
## Tracked diff excerpt
diff --git a/Makefile b/Makefile
index 573f74f..b6e7eb1 100644
--- a/Makefile
+++ b/Makefile
@@ -7,7 +7,15 @@ POSTGRES_COPY_URL ?=
 IMPORT_ARCHIVE_ROOT ?= $(HOME)/.local/state/bayesianqc/import-archive
 DB_IMPORT_ARCHIVE_ROOT ?= $(IMPORT_ARCHIVE_ROOT)
 
-.PHONY: lint typecheck test build check postgres-up postgres-upgrade test-postgres migration-upgrade migration-rehearse migration-rehearse-postgres migration-rehearse-postgres-copy import-restore-proof check-postgres
+DEMO_VPS_HOST ?=
+DEMO_VPS_DOMAIN ?= qc.geoffsmiscellany.com
+DEMO_VPS_REMOTE_ROOT ?= /srv/bayesianqc
+DEMO_VPS_SSH_KEY ?=
+DEMO_VPS_SKIP_PUBLIC_SMOKE ?= 0
+DEMO_VPS_SSH_KEY_ARG := $(if $(DEMO_VPS_SSH_KEY),--ssh-key "$(DEMO_VPS_SSH_KEY)",)
+DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG := $(if $(filter 1 true yes,$(DEMO_VPS_SKIP_PUBLIC_SMOKE)),--skip-public-smoke,)
+
+.PHONY: lint typecheck test build check postgres-up postgres-upgrade test-postgres migration-upgrade migration-rehearse migration-rehearse-postgres migration-rehearse-postgres-copy import-restore-proof check-postgres demo-vps-bootstrap demo-vps-deploy demo-vps-reset-data demo-vps-rotate-password demo-vps-smoke demo-vps-rollback
 
 lint:
 	$(PYTHON) -m ruff check app tests scripts
@@ -50,3 +58,28 @@ import-restore-proof:
 	BAYESIANQC_IMPORT_ARCHIVE_ROOT="$(IMPORT_ARCHIVE_ROOT)" $(PYTHON) scripts/prove_import_restore.py --source-url "$(POSTGRES_URL)" --archive-root "$(IMPORT_ARCHIVE_ROOT)" --db-archive-root "$(DB_IMPORT_ARCHIVE_ROOT)"
 
 check-postgres: postgres-up postgres-upgrade test-postgres migration-rehearse-postgres
+
+demo-vps-bootstrap:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	scripts/demo_vps.sh bootstrap --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
+
+demo-vps-deploy:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	scripts/demo_vps.sh deploy --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
+
+demo-vps-reset-data:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	scripts/demo_vps.sh reset-data --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
+
+demo-vps-rotate-password:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	scripts/demo_vps.sh rotate-password --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
+
+demo-vps-smoke:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	scripts/demo_vps.sh smoke --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
+
+demo-vps-rollback:
+	test -n "$(DEMO_VPS_HOST)" || (echo "Set DEMO_VPS_HOST"; exit 2)
+	test -n "$(DEMO_VPS_RELEASE_ID)" || (echo "Set DEMO_VPS_RELEASE_ID"; exit 2)
+	scripts/demo_vps.sh rollback --host "$(DEMO_VPS_HOST)" --domain "$(DEMO_VPS_DOMAIN)" --remote-root "$(DEMO_VPS_REMOTE_ROOT)" --release-id "$(DEMO_VPS_RELEASE_ID)" $(DEMO_VPS_SSH_KEY_ARG) $(DEMO_VPS_SKIP_PUBLIC_SMOKE_ARG)
diff --git a/README.md b/README.md
index 3cfc185..68ca5a8 100644
--- a/README.md
+++ b/README.md
@@ -59,6 +59,8 @@ uvicorn app.main:app --reload --port 8010
 ```
 `init_db()` applies Alembic migrations automatically. The app rejects `sqlite://` URLs at startup; legacy SQLite files are import sources only.
 See [Lab Readiness](docs/LAB_READINESS.md), [Validation Package](docs/VALIDATION_PACKAGE.md), and [Migration Strategy](docs/MIGRATION_STRATEGY.md) before any lab-like deployment.
+For a password-protected synthetic stakeholder demo on a Docker-capable host, see
+[Stakeholder Demo Docker-Host Deployment](docs/STAKEHOLDER_DEMO_VPS_DEPLOYMENT.md).
 
 To rehearse the current Postgres schema:
 ```bash
@@ -111,7 +113,7 @@ python scripts/load_chart_kiosk_suite.py --suite demo
 ```
 The demo fixtures are synthetic product-demo data only, not validated ASTM, manufacturer, clinical, pharmacological, or regulatory reference data.
 
-The guided datastream setup workflow is available in the UI at `Configuration -> Add Datastream`. It can create or reuse the instrument, method, parameter/analyte, control material, stream config, Bayesian prior, and optional saved kiosk assignment in one reviewed setup. Bulk setup starts from `GET /stream-setups/template.xlsx`, then uses `/stream-setups/import/preview` and `/stream-setups/apply`.
+The flat datastream setup workflow is available in the UI at `Configuration -> Add Datastream`. It selects governed enterprise site, lab bench/area, instrument, test/method, analyte, and control material records, with explicit Add-new routes that return to the builder. Preview/Apply still creates or versions the stream config, Bayesian prior, and optional saved kiosk assignment as one reviewed setup. Bulk setup starts from `GET /stream-setups/template.xlsx`, then uses `/stream-setups/import/preview` and `/stream-setups/apply`.
 
 ## Endpoint map
 - `GET /` Landing page with links and basic usage.
@@ -123,7 +125,13 @@ The guided datastream setup workflow is available in the UI at `Configuration ->
 - `PATCH /qc/records/{record_id}/resolution` Resolve/reinstate a QC record (requires `X-API-Key` + approve permission).
 - `GET /qc/comments` List comments by record, alert, run, or stream context.
 - `POST /qc/comments` Add a contextual QC comment for a QC record, alert, or run (requires `X-API-Key` + ingest permission).
-- `GET /instruments` List instruments.
+- `GET /enterprise-sites` List governed enterprise sites.
+- `POST /enterprise-sites` Create an enterprise site (requires `X-API-Key` + edit permission and unrestricted scope when access grants are enforced).
+- `PATCH /enterprise-sites/{site_id}` Update an enterprise site (requires `X-API-Key` + edit permission).
+- `GET /lab-areas` List governed lab benches/areas, optionally filtered by `site_id`.
+- `POST /lab-areas` Create a lab bench/area under a site (requires `X-API-Key` + edit permission and allowed site scope).
+- `PATCH /lab-areas/{area_id}` Update a lab bench/area (requires `X-API-Key` + edit permission).
+- `GET /instruments` List instruments, optionally filtered by `site_id`, `lab_area_id`, `site`, or `lab_bench`.
 - `POST /instruments` Create an instrument (requires `X-API-Key` + edit permission).
 - `PATCH /instruments/{instrument_id}` Update an instrument (requires `X-API-Key` + edit permission).
 - `GET /methods` List methods.
@@ -132,6 +140,7 @@ The guided datastream setup workflow is available in the UI at `Configuration ->
 - `GET /analytes` List analytes.
 - `POST /analytes` Create an analyte (requires `X-API-Key` + edit permission).
 - `PATCH /analytes/{analyte_id}` Update an analyte (requires `X-API-Key` + edit permission).
+- `POST /tests` Create or reuse one method plus a required analyte in one transaction (requires `X-API-Key` + edit permission).
 - `GET /control-materials` List control materials.
 - `POST /control-materials` Create a control material (requires `X-API-Key` + edit permission).
 - `GET /kiosks` List saved kiosk layouts.
@@ -167,7 +176,7 @@ The guided datastream setup workflow is available in the UI at `Configuration ->
 - Start Postgres, then run the automated checks:
   ```bash
   docker compose up -d postgres
-  pytest
+  .venv/bin/pytest
   ```
   The test harness creates a disposable Postgres database from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
 - Run the local/dev Postgres gate:
@@ -188,7 +197,7 @@ The guided datastream setup workflow is available in the UI at `Configuration ->
 
 ### Visualization & UI
 - **Risk Trendline:** Add a secondary Y-axis to the Levey-Jennings chart to visualize the "Risk Score" trajectory over time.
-- **Configuration UI:** Build dedicated UI forms for managing `StreamConfig` and `PriorConfig` (currently API-driven).
+- **Configuration UI:** Add dedicated management pages for governed sites and lab areas beyond the datastream-builder create-return flow.
 - **Uncertainty Visualization (Fan Charts):**
   - *Goal:* Visualize the evolution of belief over time by overlaying Credible Intervals (CI) for the mean and Predictive Intervals (PI) for future results on the Levey-Jennings chart.
   - *Research:*

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
}

case "$COMMAND" in
  bootstrap|deploy)
    run_release_command
    ;;
  reset-data|rotate-password|smoke)
    upload_remote_helper
    remote_run bash "$REMOTE_ROOT/incoming/remote.sh" "$COMMAND"
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
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

## FILE scripts/ensure_edge_admin_key.py
#!/usr/bin/env python3
from __future__ import annotations

import os

from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import ApiKey
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key


def main() -> None:
    raw_key = os.environ.get("BAYESIANQC_EDGE_ADMIN_API_KEY", "").strip()
    if not raw_key:
        raise SystemExit("BAYESIANQC_EDGE_ADMIN_API_KEY is required")

    description = os.environ.get("BAYESIANQC_EDGE_ADMIN_DESCRIPTION", "edge basic auth admin")
    lookup_hash = api_key_lookup_hash(raw_key)

    with Session(get_engine()) as session:
        api_key = session.exec(select(ApiKey).where(col(ApiKey.key_lookup_hash) == lookup_hash)).first()
        if api_key is None:
            api_key = ApiKey(
                key_hash=hash_api_key(raw_key),
                key_lookup_hash=lookup_hash,
                role=Role.ADMIN,
                description=description,
                active=True,
            )
        else:
            api_key.key_hash = hash_api_key(raw_key)
            api_key.key_lookup_hash = lookup_hash
            api_key.role = Role.ADMIN
            api_key.description = description
            api_key.active = True
        session.add(api_key)
        session.commit()

    print("edge admin key ready")


if __name__ == "__main__":
    main()

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
  shift
  BAYESIANQC_REMOTE_ROOT="$REMOTE_ROOT" docker compose \
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
  find "$REMOTE_ROOT/import-archive" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  run_migrations "$release"
  ensure_edge_admin_key "$release"
  compose "$release" up -d api web caddy
  load_demo_fixtures "$release"
  smoke_release "$release"
}

wait_for_api() {
  local release="$1"
  for _ in $(seq 1 40); do
    if compose "$release" run --rm api python - <<'PY' >/dev/null 2>&1
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
    if compose "$release" run --rm api python - <<'PY' >/dev/null 2>&1
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

wait_for_public_basic_auth() {
  if [[ "${BAYESIANQC_SKIP_PUBLIC_SMOKE:-0}" =~ ^(1|true|yes)$ ]]; then
    echo "Skipping public Basic Auth smoke because BAYESIANQC_SKIP_PUBLIC_SMOKE is set."
    return
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
      return
    fi
    sleep 3
  done
  echo "Public https://$DOMAIN/api/me did not return the expected Basic Auth challenge." >&2
  exit 1
}

smoke_release() {
  local release="$1"
  compose "$release" ps
  wait_for_postgres "$release"
  wait_for_api "$release"
  wait_for_caddy_basic_auth "$release"
  wait_for_public_basic_auth
}

rollback() {
  ensure_secrets
  local release
  release="$(release_dir)"
  if [[ ! -d "$release" ]]; then
    echo "Release not found: $release" >&2
    exit 2
  fi
  compose "$release" build
  compose "$release" up -d postgres
  wait_for_postgres "$release"
  run_migrations "$release"
  ensure_edge_admin_key "$release"
  compose "$release" up -d api web caddy
  smoke_release "$release"
  ln -sfn "$release" "$CURRENT_LINK"
}

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
{$BAYESIANQC_DOMAIN} {
	encode zstd gzip

	basic_auth {
		admin {$BAYESIANQC_BASIC_AUTH_HASH}
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

## FILE deploy/demo-vps/nginx.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}

## FILE deploy/demo-vps/Dockerfile.api
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY samples ./samples

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

## FILE deploy/demo-vps/Dockerfile.web
FROM node:20-alpine AS build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_URL=/api
ARG VITE_AUTH_MODE=edge-basic
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE

RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/demo-vps/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

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

## Acceptance Checks

- Unauthenticated browser access returns a Basic Auth prompt.
- `admin` plus the generated password opens the UI.
- Internal `/me` resolves as role `admin` through the hidden edge API key.
- Public `/api/me` returns a Basic Auth challenge when unauthenticated.
- Direct API and Postgres ports are not exposed publicly.
- `/kiosk/demo`, `/charts`, `/imports`, and `/audit` load after reset.
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

## Boundaries

This is not a shared-lab production deployment. It is a stakeholder demo using
synthetic data and a shared admin credential. Rotate the stakeholder password
after the demo, and do not load real lab/customer data without the production
validation package and SME expected-row signoff.

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
    assert 'BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT: "1"' in api_section
    assert 'BAYESIANQC_RUN_MIGRATIONS_ON_STARTUP: "0"' in api_section
    assert '      - "80:80"' in compose
    assert '      - "443:443"' in compose
    assert "image: caddy:2.8-alpine" in caddy_section


def test_demo_caddy_requires_basic_auth_and_injects_edge_api_key():
    caddyfile = _read("deploy/demo-vps/Caddyfile")

    assert "basic_auth" in caddyfile
    assert "admin {$BAYESIANQC_BASIC_AUTH_HASH}" in caddyfile
    assert "handle_path /api/*" in caddyfile
    assert "header_up X-API-Key {$BAYESIANQC_EDGE_ADMIN_API_KEY}" in caddyfile


def test_remote_helper_bootstrap_reset_rollback_and_smoke_contracts():
    remote = _read("deploy/demo-vps/remote.sh")

    assert 'if [[ "$COMMAND" == "bootstrap" ]]' in remote
    assert 'load_demo_fixtures "$release"' in remote
    assert 'backup="$REMOTE_ROOT/backups/pre-reset-${stamp}.dump"' in remote
    assert "dropdb --force -U bayesianqc bayesianqc" in remote
    assert 'compose "$release" build' in remote
    assert "wait_for_caddy_basic_auth" in remote
    assert "wait_for_public_basic_auth" in remote
    assert "BAYESIANQC_SKIP_PUBLIC_SMOKE" in remote


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
