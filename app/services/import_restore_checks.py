from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import func, select as sa_select
from sqlmodel import Session, col, select

from app.db_models import AuditEntry, QCRecord, QCRecordQuarantine
from app.import_db_models import ImportArtifact, ImportBatch, ImportRow
from app.import_models import ImportRowStatus

_MISMATCH_SAMPLE_LIMIT = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def restored_archive_path(stored_path: str, db_archive_root: Path, archive_root: Path) -> Path | None:
    try:
        relative = Path(stored_path).resolve().relative_to(db_archive_root.resolve())
    except ValueError:
        return None
    return archive_root / relative


def _archive_rows(session: Session) -> Iterator[tuple[str, int, str, str]]:
    for row_id, archived_path, file_hash in session.exec(
        select(col(ImportBatch.id), col(ImportBatch.archived_path), col(ImportBatch.file_hash))
        .order_by(col(ImportBatch.id))
        .execution_options(yield_per=1000, stream_results=True)
    ):
        if row_id is not None:
            yield ("import_batch", row_id, archived_path, file_hash)
    for row_id, archived_path, file_hash in session.exec(
        select(col(ImportArtifact.id), col(ImportArtifact.archived_path), col(ImportArtifact.file_hash))
        .order_by(col(ImportArtifact.id))
        .execution_options(yield_per=1000, stream_results=True)
    ):
        if row_id is not None:
            yield ("import_artifact", row_id, archived_path, file_hash)


def verify_archive_hashes(session: Session, db_archive_root: Path, archive_root: Path) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    mismatch_count = 0
    checked = 0

    def add_mismatch(value: dict[str, Any]) -> None:
        nonlocal mismatch_count
        mismatch_count += 1
        if len(mismatches) < _MISMATCH_SAMPLE_LIMIT:
            mismatches.append(value)

    for kind, row_id, stored_path, expected_hash in _archive_rows(session):
        checked += 1
        restored_path = restored_archive_path(stored_path, db_archive_root, archive_root)
        if restored_path is None:
            add_mismatch({"kind": kind, "id": row_id, "reason": "outside_archive_root", "path": stored_path})
            continue
        if not restored_path.exists():
            add_mismatch({"kind": kind, "id": row_id, "reason": "missing_file", "path": str(restored_path)})
            continue
        actual_hash = sha256_file(restored_path)
        if actual_hash != expected_hash:
            add_mismatch(
                {
                    "kind": kind,
                    "id": row_id,
                    "reason": "hash_mismatch",
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )
    return {"ok": mismatch_count == 0, "checked": checked, "mismatch_count": mismatch_count, "mismatches": mismatches}


def _count_rows(session: Session, status: ImportRowStatus) -> int:
    return int(session.exec(select(func.count(col(ImportRow.id))).where(col(ImportRow.status) == status)).one())


def _collect_mismatches(statement: Any, session: Session, reason: str, reference_field: str) -> tuple[int, list[dict[str, Any]]]:
    count = 0
    samples: list[dict[str, Any]] = []
    for import_row_id, reference_id in session.execute(
        statement.execution_options(yield_per=1000, stream_results=True)
    ):
        count += 1
        if len(samples) < _MISMATCH_SAMPLE_LIMIT:
            samples.append({"import_row_id": import_row_id, "reason": reason, reference_field: reference_id})
    return count, samples


def verify_import_links(session: Session) -> dict[str, Any]:
    missing_batch = (
        sa_select(col(ImportRow.id), col(ImportRow.batch_id))
        .select_from(ImportRow)
        .outerjoin(ImportBatch, col(ImportRow.batch_id) == col(ImportBatch.id))
        .where(col(ImportBatch.id).is_(None))
        .order_by(col(ImportRow.id))
    )
    missing_record = (
        sa_select(col(ImportRow.id), col(ImportRow.qc_record_id))
        .select_from(ImportRow)
        .outerjoin(QCRecord, col(ImportRow.qc_record_id) == col(QCRecord.id))
        .where(col(ImportRow.status) == ImportRowStatus.APPLIED, col(QCRecord.id).is_(None))
        .order_by(col(ImportRow.id))
    )
    missing_quarantine = (
        sa_select(col(ImportRow.id), col(ImportRow.quarantine_id))
        .select_from(ImportRow)
        .outerjoin(QCRecordQuarantine, col(ImportRow.quarantine_id) == col(QCRecordQuarantine.id))
        .where(col(ImportRow.status) == ImportRowStatus.QUARANTINED, col(QCRecordQuarantine.id).is_(None))
        .order_by(col(ImportRow.id))
    )
    mismatch_count = 0
    mismatches: list[dict[str, Any]] = []
    for statement, reason, field in [
        (missing_batch, "missing_import_batch", "batch_id"),
        (missing_record, "missing_qc_record", "qc_record_id"),
        (missing_quarantine, "missing_quarantine", "quarantine_id"),
    ]:
        count, samples = _collect_mismatches(statement, session, reason, field)
        mismatch_count += count
        mismatches.extend(samples)
    audit_count = session.exec(
        select(func.count(col(AuditEntry.id))).where(
            col(AuditEntry.entity_type).in_(["parser_profile", "import_batch", "import_row", "qc_record_quarantine"])
        )
    ).one()
    return {
        "ok": mismatch_count == 0,
        "applied_rows": _count_rows(session, ImportRowStatus.APPLIED),
        "quarantined_rows": _count_rows(session, ImportRowStatus.QUARANTINED),
        "audit_entries": audit_count,
        "mismatch_count": mismatch_count,
        "mismatches": mismatches,
    }


def build_restore_summary(session: Session, db_archive_root: Path, archive_root: Path) -> dict[str, Any]:
    archive = verify_archive_hashes(session, db_archive_root, archive_root)
    links = verify_import_links(session)
    return {
        "ok": bool(archive["ok"] and links["ok"]),
        "archive": archive,
        "links": links,
    }
