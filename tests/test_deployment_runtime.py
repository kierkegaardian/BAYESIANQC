from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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


def test_josh_demo_external_images_are_immutable_and_match_declarations():
    lock = json.loads(_read("deploy/demo/image-lock.json"))
    assert lock["schema_version"] == 1
    references = {**lock["build_bases"], **lock["runtime_images"]}
    assert all(re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", ref) for ref in references.values())

    assert lock["build_bases"]["python"] in _read("deploy/demo/Dockerfile.api")
    web_dockerfile = _read("deploy/demo/Dockerfile.web")
    assert lock["build_bases"]["node"] in web_dockerfile
    assert lock["build_bases"]["nginx"] in web_dockerfile
    compose = _read("deploy/demo/docker-compose.yml")
    assert lock["runtime_images"]["postgres"] in compose
    assert lock["runtime_images"]["caddy"] in compose
    assert lock["runtime_images"]["cloudflared"] in _read(
        "deploy/demo/compose.quick-tunnel.yml"
    )
    assert lock["runtime_images"]["caddy"] in _read("deploy/demo/remote_lib.sh")


def test_josh_demo_scripts_and_compose_validate(tmp_path):
    for script in [
        "scripts/josh_demo.sh",
        "deploy/demo/remote.sh",
        "deploy/demo/remote_lib.sh",
    ]:
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)

    env_file = tmp_path / "demo.env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=test-password",
                "BAYESIANQC_EDGE_API_KEY=test-edge-key",
                "BAYESIANQC_BASIC_AUTH_HASH=test-hash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "BAYESIANQC_RELEASE_ID": "a" * 40,
        "BAYESIANQC_REMOTE_ROOT": str(tmp_path / "remote"),
    }
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "deploy/demo/docker-compose.yml"),
            "-f",
            str(ROOT / "deploy/demo/compose.quick-tunnel.yml"),
            "config",
            "--quiet",
        ],
        check=True,
        env=env,
    )


def test_josh_demo_edge_uses_safe_catalog_and_denies_full_stream_list():
    for caddyfile in ["deploy/demo/Caddyfile.quick-tunnel", "deploy/demo/Caddyfile.vps"]:
        content = _read(caddyfile)
        proxy = _section(content, "(stakeholder_api_proxy) {\n", "\n}\n")
        api_read = _section(content, "\t@api_read {\n", "\n\t}\n")
        assert "header_up -Authorization" in proxy
        assert "header_up X-API-Key {$BAYESIANQC_EDGE_API_KEY}" in proxy
        assert "header_up -X-API-Key" not in proxy
        assert "/api/stream-catalog" in api_read
        assert "/api/streams " not in api_read
        assert "^/api/streams/[^/]+/chart$" in content


def test_josh_demo_public_smoke_mutates_once_restores_and_enforces_fifteen_minutes():
    helper = _read("deploy/demo/public_smoke.py")
    wrapper = _read("scripts/josh_demo.sh")
    remote = _read("deploy/demo/remote.sh")

    assert '"status": "acknowledged"' in helper
    assert '"status": "open"' in helper
    assert "finally:" in helper
    assert "JOSH_DEMO_MUTATE_ALERT" in helper
    assert "mutate_alert=0" in wrapper
    assert 'remote_current record-public-smoke "$STABILITY_SECONDS"' in wrapper
    assert '"/api/qc/backlog"' in helper
    assert '"/api/qc/quarantine"' in helper
    assert '"$stability_seconds" -ge 900' in remote
    assert '"$RUNTIME_DIR/tunnel-started-at.txt"' in remote
    assert "elapsed_seconds < required_seconds" in remote
    assert "project_release_from_labels" in remote
    assert 'label=com.docker.compose.project=$PROJECT_NAME' in remote

    rejected = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/josh_demo.sh"),
            "smoke",
            "--stability-seconds",
            "899",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert "at least 900" in rejected.stderr


def test_resource_failure_invokes_project_scoped_tunnel_stop(tmp_path):
    marker = tmp_path / "tunnel-stopped"
    snippet = f"""
set -u
source {ROOT / 'deploy/demo/remote_lib.sh'}
REMOTE_ROOT={tmp_path}
df() {{ printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/x 20 19 1 95%% /\\n'; }}
stop_project_tunnel_containers() {{ printf stopped > {marker}; }}
set +e
require_demo_resources
status=$?
set -e
[[ $status -eq 2 ]]
[[ -f {marker} ]]
"""
    subprocess.run(["bash", "-c", snippet], check=True)
    remote_lib = _read("deploy/demo/remote_lib.sh")
    assert 'label=com.docker.compose.project=$PROJECT_NAME' in remote_lib
    assert "killall" not in remote_lib
    assert "docker prune" not in remote_lib
    start_tunnel_case = _section(
        _read("deploy/demo/remote.sh"),
        "  start-tunnel)\n",
        "    ;;\n",
    )
    assert start_tunnel_case.index("require_demo_resources") < start_tunnel_case.index(
        "start_tunnel"
    )
