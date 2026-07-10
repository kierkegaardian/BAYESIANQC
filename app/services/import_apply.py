from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.import_db_models import ImportBatch, ImportRow, InstrumentRun
from app.import_models import ImportBatchStatus, ImportRowStatus
from app.models import EntrySource, IngestionResult, QCRecordIn, QuarantineResult
from app.rbac import UserContext
from app.services.access_scopes import backlog_item_is_accessible, stream_is_accessible
from app.services.ingestion import process_ingestion
from app.services.import_run_context import (
    fields_have_run_context,
    mark_row_needs_run_context,
    profile_allows_provisional_run,
    profile_for_batch,
)
from app.services.qc_backlog import get_backlog_item


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    raise ValueError("timestamp is required")


def _run_key(batch: ImportBatch, fields: dict[str, Any]) -> str:
    run_id = fields.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()
    backlog_id = fields.get("qc_backlog_item_id")
    if isinstance(backlog_id, int):
        return f"backlog-{backlog_id}"
    if batch.id is None:
        raise RuntimeError("Import batch missing id")
    return f"import-{batch.id}"


def _get_or_create_run(session: Session, batch: ImportBatch, fields: dict[str, Any]) -> InstrumentRun:
    key = _run_key(batch, fields)
    existing = session.exec(select(InstrumentRun).where(InstrumentRun.run_key == key)).first()
    if existing is not None:
        return existing
    run = InstrumentRun(
        run_key=key,
        instrument=fields.get("instrument_id") if isinstance(fields.get("instrument_id"), str) else None,
        source_id=batch.source_id,
        started_at=_as_datetime(fields["timestamp"]),
        qc_backlog_item_id=fields.get("qc_backlog_item_id") if isinstance(fields.get("qc_backlog_item_id"), int) else None,
        import_batch_id=batch.id,
        status="confirmed",
    )
    session.add(run)
    session.flush()
    return run


def _payload_from_row(fields: dict[str, Any]) -> QCRecordIn:
    payload = dict(fields)
    payload["entry_source"] = EntrySource.AUTOMATED
    return QCRecordIn.model_validate(payload)


def _apply_one(session: Session, batch: ImportBatch, row: ImportRow, user: UserContext) -> None:
    fields = dict(row.parsed_fields)
    profile = profile_for_batch(session, batch)
    if not fields_have_run_context(fields) and not profile_allows_provisional_run(profile):
        mark_row_needs_run_context(row)
        session.add(row)
        session.flush()
        return
    stream_id = fields.get("stream_id")
    if not isinstance(stream_id, str) or not stream_is_accessible(session, user, stream_id):
        row.status = ImportRowStatus.IGNORED
        row.errors = [*row.errors, "out of scope for current API key"]
        session.add(row)
        session.flush()
        return
    backlog_id = fields.get("qc_backlog_item_id")
    if isinstance(backlog_id, int) and not backlog_item_is_accessible(session, user, get_backlog_item(session, backlog_id)):
        row.status = ImportRowStatus.IGNORED
        row.errors = [*row.errors, "backlog item out of scope for current API key"]
        session.add(row)
        session.flush()
        return
    run = _get_or_create_run(session, batch, fields)
    if run.id is None:
        raise RuntimeError("Instrument run missing id")
    fields["run_id"] = run.run_key
    row.instrument_run_id = run.id
    row.parsed_fields = fields
    session.add(row)
    session.flush()
    try:
        result = process_ingestion(_payload_from_row(fields), session, user, row.idempotency_key)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT or exc.detail != "possible_duplicate_requires_review":
            raise
        row.status = ImportRowStatus.NEEDS_REVIEW
        row.errors = [*row.errors, "possible_duplicate_requires_review"]
        session.add(row)
        session.flush()
        return
    if isinstance(result, IngestionResult):
        row.status = ImportRowStatus.APPLIED
        row.qc_record_id = result.qc.id
    elif isinstance(result, QuarantineResult):
        row.status = ImportRowStatus.QUARANTINED
        row.quarantine_id = result.quarantine.id
    session.add(row)
    session.flush()


def refresh_batch_status(session: Session, batch: ImportBatch) -> None:
    rows = session.exec(select(ImportRow).where(ImportRow.batch_id == batch.id)).all()
    qc_rows = [row for row in rows if row.row_type.value == "qc_result"]
    batch.total_rows = len(rows)
    batch.ready_rows = sum(row.status == ImportRowStatus.READY_TO_APPLY for row in rows)
    batch.exception_rows = sum(
        row.status in {ImportRowStatus.NEEDS_REVIEW, ImportRowStatus.PARSE_ERROR, ImportRowStatus.QUARANTINED}
        for row in rows
    )
    batch.applied_rows = sum(row.status == ImportRowStatus.APPLIED for row in rows)
    if qc_rows and batch.applied_rows == len(qc_rows):
        batch.status = ImportBatchStatus.APPLIED
    elif batch.applied_rows:
        batch.status = ImportBatchStatus.PARTIALLY_APPLIED
    elif batch.ready_rows and not batch.exception_rows:
        batch.status = ImportBatchStatus.READY_TO_APPLY
    elif batch.status != ImportBatchStatus.FAILED_TO_INGEST:
        batch.status = ImportBatchStatus.PARSED_WITH_EXCEPTIONS
    session.add(batch)
    session.commit()


def apply_ready_rows(session: Session, batch: ImportBatch, user: UserContext) -> ImportBatch:
    rows = session.exec(
        select(ImportRow).where(ImportRow.batch_id == batch.id, ImportRow.status == ImportRowStatus.READY_TO_APPLY)
    ).all()
    for row in rows:
        _apply_one(session, batch, row, user)
    session.refresh(batch)
    refresh_batch_status(session, batch)
    session.refresh(batch)
    return batch
