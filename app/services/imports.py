from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.import_db_models import CollectorTransferEvent, ImportArtifact, ImportBatch, ImportRow, InstrumentPeak, ParserProfile
from app.import_models import (
    CollectorAction,
    CollectorTransferEventIn,
    CollectorTransferEventOut,
    ImportArtifactRole,
    ImportBatchStatus,
    ImportRowStatus,
)
from app.models import EntrySource, QCRecordIn
from app.rbac import UserContext
from app.services.import_apply import apply_ready_rows, refresh_batch_status
from app.services.import_mapping import build_import_row
from app.services.import_outputs import batch_out
from app.services.import_profiles import select_profile
from app.services.import_readers import read_source_rows
from app.storage import get_active_stream_config, record_audit


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _archive_root() -> Path:
    return Path(os.getenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", "data/import-archive"))


def _safe_name(filename: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in filename)
    return cleaned or "upload.bin"


def archive_file(data: bytes, filename: str) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    now = utcnow()
    folder = _archive_root() / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest[:16]}__{_safe_name(filename)}"
    if not target.exists():
        target.write_bytes(data)
    return digest, str(target)


def _create_failed_batch(
    session: Session,
    *,
    filename: str,
    source_id: Optional[str],
    source_path: Optional[str],
    digest: str,
    archived_path: str,
    size: int,
    reason: str,
    user: UserContext,
) -> ImportBatch:
    batch = ImportBatch(
        filename=filename,
        source_id=source_id,
        source_path=source_path,
        file_hash=digest,
        file_size=size,
        archived_path=archived_path,
        status=ImportBatchStatus.FAILED_TO_INGEST,
        failure_reason=reason,
        collector_action=CollectorAction.MOVE_TO_FAILED,
        created_by=user.actor,
    )
    session.add(batch)
    session.flush()
    session.commit()
    return batch


def _artifact_role(profile: ParserProfile) -> ImportArtifactRole | None:
    role = profile.config.get("artifact_role")
    if not isinstance(role, str):
        return None
    try:
        return ImportArtifactRole(role)
    except ValueError:
        return None


def _maybe_record_artifact(session: Session, batch: ImportBatch, profile: ParserProfile) -> None:
    role = _artifact_role(profile)
    if role is None:
        return
    artifact = ImportArtifact(
        batch_id=batch.id or 0,
        role=role,
        filename=batch.filename,
        file_hash=batch.file_hash,
        archived_path=batch.archived_path,
    )
    session.add(artifact)
    batch.artifact_count += 1


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _record_peak(session: Session, batch: ImportBatch, row: ImportRow) -> None:
    fields = row.parsed_fields
    peak = InstrumentPeak(
        batch_id=batch.id or 0,
        import_row_id=row.id,
        analyte=fields.get("analyte") if isinstance(fields.get("analyte"), str) else None,
        peak_name=fields.get("peak_name") if isinstance(fields.get("peak_name"), str) else None,
        retention_time=_float_or_none(fields.get("retention_time")),
        area=_float_or_none(fields.get("area")),
        height=_float_or_none(fields.get("height")),
        raw=row.raw,
    )
    session.add(peak)


def create_import(
    session: Session,
    *,
    filename: str,
    data: bytes,
    source_id: Optional[str],
    source_path: Optional[str],
    profile_id: Optional[int],
    auto_apply: bool,
    user: UserContext,
) -> ImportBatch:
    digest, archived_path = archive_file(data, filename)
    header = data[:4096].decode("utf-8", errors="ignore")
    try:
        profile = select_profile(session, filename=filename, source_id=source_id, explicit_profile_id=profile_id, header_text=header)
    except HTTPException as exc:
        return _create_failed_batch(
            session,
            filename=filename,
            source_id=source_id,
            source_path=source_path,
            digest=digest,
            archived_path=archived_path,
            size=len(data),
            reason=str(exc.detail),
            user=user,
        )
    batch = ImportBatch(
        filename=filename,
        source_id=source_id,
        source_path=source_path,
        file_hash=digest,
        file_size=len(data),
        archived_path=archived_path,
        parser_profile_id=profile.id,
        parser_profile_version=profile.version,
        status=ImportBatchStatus.RECEIVED,
        collector_action=CollectorAction.MOVE_TO_SENT,
        created_by=user.actor,
    )
    session.add(batch)
    session.flush()
    try:
        source_rows = read_source_rows(data, filename, profile)
    except HTTPException as exc:
        if _artifact_role(profile):
            _maybe_record_artifact(session, batch, profile)
            batch.status = ImportBatchStatus.PARSED_WITH_EXCEPTIONS
            batch.failure_reason = str(exc.detail)
            session.add(batch)
            session.commit()
            return batch
        batch.status = ImportBatchStatus.FAILED_TO_INGEST
        batch.failure_reason = str(exc.detail)
        batch.collector_action = CollectorAction.MOVE_TO_FAILED
        session.add(batch)
        session.commit()
        return batch
    _maybe_record_artifact(session, batch, profile)
    for source in source_rows:
        row = build_import_row(session, batch, profile, source)
        session.add(row)
        session.flush()
        if row.row_type.value == "peak":
            _record_peak(session, batch, row)
    session.flush()
    refresh_batch_status(session, batch)
    if auto_apply or bool(profile.config.get("auto_apply_ready_rows")):
        batch = apply_ready_rows(session, batch, user)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_import_batch",
        entity_type="import_batch",
        entity_id=str(batch.id),
        before=None,
        after=batch_out(batch).model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    return batch


def update_row(session: Session, row_id: int, payload, user: UserContext) -> ImportRow:
    row = session.exec(select(ImportRow).where(ImportRow.id == row_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Import row not found")
    before = row.model_dump(mode="json")
    fields = dict(row.parsed_fields)
    if payload.parsed_fields:
        fields.update(payload.parsed_fields)
    if payload.stream_id:
        timestamp = datetime.fromisoformat(str(fields["timestamp"]).replace("Z", "+00:00"))
        config = get_active_stream_config(session, payload.stream_id, timestamp)
        if config is None:
            raise HTTPException(status_code=422, detail="Stream not configured")
        fields.update(
            stream_id=config.stream_id,
            analyte=config.analyte,
            qc_level=config.qc_level,
            instrument_id=config.instrument,
            method_id=config.method,
            control_material_lot=config.control_material_lot,
            units=config.units,
        )
        row.stream_id = config.stream_id
    if payload.qc_backlog_item_id is not None:
        fields["qc_backlog_item_id"] = payload.qc_backlog_item_id
        row.qc_backlog_item_id = payload.qc_backlog_item_id
    QCRecordIn.model_validate({**fields, "entry_source": EntrySource.AUTOMATED})
    row.parsed_fields = fields
    row.errors = []
    row.warnings = []
    row.status = ImportRowStatus.READY_TO_APPLY
    session.add(row)
    session.flush()
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="update_import_row",
        entity_type="import_row",
        entity_id=str(row.id),
        before=before,
        after=row.model_dump(mode="json"),
        reason=payload.reason,
        commit=False,
    )
    session.commit()
    return row


def create_collector_event(
    session: Session, transfer_id: str, payload: CollectorTransferEventIn, user: UserContext
) -> CollectorTransferEventOut:
    row = CollectorTransferEvent(transfer_id=transfer_id, created_by=user.actor, **payload.model_dump())
    session.add(row)
    session.commit()
    session.refresh(row)
    if row.id is None:
        raise RuntimeError("Collector transfer event missing id")
    return CollectorTransferEventOut(**row.model_dump())
