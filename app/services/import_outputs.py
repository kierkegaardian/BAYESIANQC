from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.import_db_models import ImportArtifact, ImportBatch, ImportRow, InstrumentPeak, InstrumentRun
from app.import_models import (
    ImportArtifactOut,
    ImportBatchDetailOut,
    ImportBatchOut,
    ImportBatchStatus,
    ImportRowOut,
    InstrumentPeakOut,
    InstrumentRunOut,
)
from app.rbac import UserContext
from app.services.access_scopes import effective_scope, stream_is_accessible


def batch_out(batch: ImportBatch) -> ImportBatchOut:
    if batch.id is None:
        raise RuntimeError("Import batch missing id")
    return ImportBatchOut(**batch.model_dump())


def row_out(row: ImportRow) -> ImportRowOut:
    if row.id is None:
        raise RuntimeError("Import row missing id")
    return ImportRowOut(**row.model_dump())


def artifact_out(row: ImportArtifact) -> ImportArtifactOut:
    if row.id is None:
        raise RuntimeError("Import artifact missing id")
    return ImportArtifactOut(**row.model_dump())


def peak_out(row: InstrumentPeak) -> InstrumentPeakOut:
    if row.id is None:
        raise RuntimeError("Instrument peak missing id")
    return InstrumentPeakOut(**row.model_dump())


def run_out(row: InstrumentRun) -> InstrumentRunOut:
    if row.id is None:
        raise RuntimeError("Instrument run missing id")
    return InstrumentRunOut(**row.model_dump())


def get_batch(session: Session, batch_id: int) -> ImportBatch:
    batch = session.exec(select(ImportBatch).where(ImportBatch.id == batch_id)).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch


def _row_visible(session: Session, batch: ImportBatch, user: UserContext, row: ImportRow) -> bool:
    if row.stream_id is None:
        return batch.created_by == user.actor
    return stream_is_accessible(session, user, row.stream_id)


def _visible_rows(session: Session, batch: ImportBatch, user: UserContext) -> list[ImportRow]:
    rows = session.exec(select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(col(ImportRow.row_number))).all()
    if effective_scope(session, user).unrestricted:
        return list(rows)
    return [row for row in rows if _row_visible(session, batch, user, row)]


def batch_detail(session: Session, batch: ImportBatch, user: UserContext | None = None) -> ImportBatchDetailOut:
    if user is None:
        rows = session.exec(select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(col(ImportRow.row_number))).all()
    else:
        rows = _visible_rows(session, batch, user)
        if not rows and batch.created_by != user.actor:
            raise HTTPException(status_code=404, detail="Import batch not found")
    artifacts = session.exec(select(ImportArtifact).where(ImportArtifact.batch_id == batch.id)).all()
    peaks = session.exec(select(InstrumentPeak).where(InstrumentPeak.batch_id == batch.id)).all()
    runs = session.exec(select(InstrumentRun).where(InstrumentRun.import_batch_id == batch.id)).all()
    if user is not None and not effective_scope(session, user).unrestricted:
        visible_row_ids = {row.id for row in rows if row.id is not None}
        visible_run_ids = {row.instrument_run_id for row in rows if row.instrument_run_id is not None}
        artifacts = [row for row in artifacts if row.linked_import_row_id in visible_row_ids]
        peaks = [row for row in peaks if row.import_row_id in visible_row_ids]
        runs = [row for row in runs if row.id in visible_run_ids]
    return ImportBatchDetailOut(
        **batch_out(batch).model_dump(),
        rows=[row_out(row) for row in rows],
        artifacts=[artifact_out(row) for row in artifacts],
        peaks=[peak_out(row) for row in peaks],
        instrument_runs=[run_out(row) for row in runs],
    )


def list_batches(
    session: Session,
    status: Optional[ImportBatchStatus],
    limit: int,
    user: UserContext | None = None,
) -> list[ImportBatchOut]:
    query = select(ImportBatch).order_by(col(ImportBatch.received_at).desc()).limit(limit)
    if status is not None:
        query = query.where(ImportBatch.status == status)
    batches = []
    for batch in session.exec(query).all():
        if user is not None and not effective_scope(session, user).unrestricted:
            if batch.created_by != user.actor and not _visible_rows(session, batch, user):
                continue
        batches.append(batch_out(batch))
    return batches
