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
