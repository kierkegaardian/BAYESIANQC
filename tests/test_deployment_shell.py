from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backup_snapshot_is_safe_with_nounset(tmp_path: Path) -> None:
    import_archive = tmp_path / "import-archive"
    import_archive.mkdir()
    (import_archive / "evidence.txt").write_text("synthetic\n", encoding="utf-8")
    snippet = f"""
set -euo pipefail
source {ROOT / 'deploy/demo/remote_lib.sh'}
REMOTE_ROOT={tmp_path}
compose() {{ printf 'synthetic-database'; }}
target="$(backup_snapshot /tmp/release pre-reset-test)"
[[ "$target" == {tmp_path}/backups/pre-reset-test ]]
[[ -s "$target/database.dump" ]]
[[ -s "$target/import-archive.tar.gz" ]]
"""
    subprocess.run(["bash", "-c", snippet], check=True)


def test_web_image_normalizes_config_mode_after_secure_release_extract() -> None:
    dockerfile = (ROOT / "deploy/demo/Dockerfile.web").read_text(encoding="utf-8")
    assert "COPY --chmod=0644 deploy/demo/nginx.conf /etc/nginx/nginx.conf" in dockerfile


def test_status_and_post_load_smoke_contracts_are_stable() -> None:
    remote = (ROOT / "deploy/demo/remote.sh").read_text(encoding="utf-8")
    remote_lib = (ROOT / "deploy/demo/remote_lib.sh").read_text(encoding="utf-8")
    show_status = remote.split("show_status() {", 1)[1].split("\n}", 1)[0]
    assert '[[ -f "$RUNTIME_DIR/public-smoke.txt" ]] && cat' in show_status
    assert show_status.rstrip().endswith("return 0")
    assert 'wait_healthy "$release" api; wait_healthy "$release" caddy; private_smoke' in remote_lib


def test_retry_uses_locally_available_pinned_runtime_images() -> None:
    remote = (ROOT / "deploy/demo/remote.sh").read_text(encoding="utf-8")
    assert 'pull --policy missing postgres caddy cloudflared' in remote
