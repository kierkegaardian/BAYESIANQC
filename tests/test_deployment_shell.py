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
