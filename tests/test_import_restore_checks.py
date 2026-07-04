from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.db import get_engine
from app.import_db_models import ImportBatch
from app.import_models import CollectorAction, ImportBatchStatus
from app.services.import_restore_checks import build_restore_summary, sha256_file


def test_restore_proof_hash_reconciliation_detects_changed_files(tmp_path: Path) -> None:
    source_root = tmp_path / "source-archive"
    restored_root = tmp_path / "restored-archive"
    source_file = source_root / "2026" / "07" / "batch.csv"
    restored_file = restored_root / "2026" / "07" / "batch.csv"
    source_file.parent.mkdir(parents=True)
    restored_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"qc,result\n")
    restored_file.write_bytes(b"qc,result\n")
    digest = sha256_file(source_file)
    with Session(get_engine()) as session:
        session.add(
            ImportBatch(
                filename="batch.csv",
                file_hash=digest,
                file_size=10,
                archived_path=str(source_file),
                status=ImportBatchStatus.READY_TO_APPLY,
                collector_action=CollectorAction.MOVE_TO_SENT,
                created_by="test",
            )
        )
        session.commit()
        clean = build_restore_summary(session, source_root, restored_root)
        assert clean["ok"] is True
        restored_file.unlink()
        missing = build_restore_summary(session, source_root, restored_root)
        assert missing["ok"] is False
        assert missing["archive"]["mismatches"][0]["reason"] == "missing_file"
        restored_file.write_bytes(b"changed\n")
        changed = build_restore_summary(session, source_root, restored_root)
        assert changed["ok"] is False
        assert changed["archive"]["mismatches"][0]["reason"] == "hash_mismatch"
