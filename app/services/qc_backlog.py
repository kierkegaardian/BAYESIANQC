from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.db_models import QCBacklogItem, QCRecord
from app.models import (
    Permission,
    QCBacklogItemIn,
    QCBacklogItemOut,
    QCBacklogItemUpdate,
    QCBacklogSource,
    QCBacklogStatus,
    QCRecordIn,
)
from app.rbac import UserContext
from app.services.access_scopes import (
    backlog_context_is_accessible,
    backlog_scope_predicate,
    effective_scope,
    require_backlog_access,
    require_stream_access,
)
from app.storage import get_active_stream_config, record_audit

ACTIVE_STATUSES = [QCBacklogStatus.OPEN, QCBacklogStatus.IN_PROGRESS]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def backlog_out(row: QCBacklogItem) -> QCBacklogItemOut:
    if row.id is None:
        raise RuntimeError("QC backlog item missing id")
    return QCBacklogItemOut(**row.model_dump())


def get_backlog_item(session: Session, item_id: int) -> QCBacklogItem:
    item = session.exec(select(QCBacklogItem).where(QCBacklogItem.id == item_id)).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QC backlog item not found")
    return item


def list_backlog_items(
    session: Session,
    *,
    user: UserContext,
    statuses: Optional[list[QCBacklogStatus]],
    source: Optional[QCBacklogSource],
    instrument: Optional[str],
    lab_bench: Optional[str],
    assignment_group: Optional[str],
    assigned_to: Optional[str],
    stream_id: Optional[str],
    due_from: Optional[datetime],
    due_to: Optional[datetime],
    limit: int,
) -> list[QCBacklogItemOut]:
    selected_statuses = statuses or ACTIVE_STATUSES
    query = select(QCBacklogItem).where(
        col(QCBacklogItem.status).in_(selected_statuses),
        backlog_scope_predicate(effective_scope(session, user)),
    )
    if source:
        query = query.where(QCBacklogItem.source == source)
    if instrument:
        query = query.where(QCBacklogItem.instrument == instrument)
    if lab_bench:
        query = query.where(QCBacklogItem.lab_bench == lab_bench)
    if assignment_group:
        query = query.where(QCBacklogItem.assignment_group == assignment_group)
    if assigned_to:
        query = query.where(QCBacklogItem.assigned_to == assigned_to)
    if stream_id:
        query = query.where(QCBacklogItem.stream_id == stream_id)
    if due_from:
        query = query.where(QCBacklogItem.due_at >= due_from)
    if due_to:
        query = query.where(QCBacklogItem.due_at <= due_to)
    rows = session.exec(query.order_by(col(QCBacklogItem.due_at).asc()).limit(limit)).all()
    return [backlog_out(row) for row in rows]


def create_backlog_item(session: Session, payload: QCBacklogItemIn, user: UserContext) -> QCBacklogItemOut:
    config = get_active_stream_config(session, payload.stream_id, payload.due_at)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not configured")
    require_stream_access(session, user, config.stream_id, hide=False)
    lab_bench = payload.lab_bench or config.lab_bench
    if not backlog_context_is_accessible(
        session,
        user,
        stream_id=config.stream_id,
        site=config.site,
        lab_bench=lab_bench,
        assignment_group=payload.assignment_group,
    ):
        raise HTTPException(status_code=403, detail="Target backlog scope is not allowed")
    item = QCBacklogItem(
        source=payload.source,
        status=QCBacklogStatus.OPEN,
        priority=payload.priority,
        stream_id=config.stream_id,
        analyte=config.analyte,
        method=config.method,
        instrument=config.instrument,
        site=config.site,
        qc_level=config.qc_level,
        units=config.units,
        reference_material_lot=config.control_material_lot,
        reference_material_label=payload.reference_material_label,
        due_at=payload.due_at,
        lab_bench=lab_bench,
        assignment_group=payload.assignment_group,
        assigned_to=payload.assigned_to,
        notes=payload.notes,
        requested_by=payload.requested_by,
        created_by=user.actor,
    )
    session.add(item)
    session.flush()
    out = backlog_out(item)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_qc_backlog_item",
        entity_type="qc_backlog_item",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=payload.notes,
        commit=False,
    )
    session.commit()
    session.refresh(item)
    return backlog_out(item)


def update_backlog_item(
    session: Session,
    item_id: int,
    payload: QCBacklogItemUpdate,
    user: UserContext,
) -> QCBacklogItemOut:
    item = get_backlog_item(session, item_id)
    data = payload.model_dump(exclude_unset=True)
    require_backlog_access(
        session,
        user,
        item,
        target_lab_bench=data.get("lab_bench"),
        target_assignment_group=data.get("assignment_group"),
        target_lab_bench_provided="lab_bench" in data,
        target_assignment_group_provided="assignment_group" in data,
    )
    before = item.model_dump(mode="json")
    target_status = data.pop("status", None)
    reason = data.pop("reason", None)
    if target_status and target_status != item.status:
        if target_status == QCBacklogStatus.COMPLETED:
            raise HTTPException(status_code=422, detail="QC backlog completion requires accepted QC ingestion")
        if target_status == QCBacklogStatus.CANCELED and not user.can(Permission.APPROVE):
            raise HTTPException(status_code=403, detail="Canceling QC backlog items requires approve permission")
        if not reason or not reason.strip():
            raise HTTPException(status_code=422, detail="reason is required when changing QC backlog status")
        item.status = target_status
        if target_status == QCBacklogStatus.IN_PROGRESS and item.started_at is None:
            item.started_at = utcnow()
            item.started_by = user.actor
    for field, value in data.items():
        setattr(item, field, value)
    if item.status == QCBacklogStatus.IN_PROGRESS and item.started_at is not None and item.started_by is None:
        item.started_by = user.actor
    item.updated_at = utcnow()
    session.add(item)
    session.flush()
    out = backlog_out(item)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="update_qc_backlog_item",
        entity_type="qc_backlog_item",
        entity_id=str(item.id),
        before=before,
        after=out.model_dump(mode="json"),
        reason=reason,
        commit=False,
    )
    session.commit()
    session.refresh(item)
    return backlog_out(item)


def validate_backlog_for_payload(session: Session, payload: QCRecordIn) -> QCBacklogItem:
    if payload.qc_backlog_item_id is None:
        raise RuntimeError("validate_backlog_for_payload requires qc_backlog_item_id")
    item = get_backlog_item(session, payload.qc_backlog_item_id)
    if item.status in {QCBacklogStatus.COMPLETED, QCBacklogStatus.CANCELED}:
        raise HTTPException(status_code=409, detail="QC backlog item is not open for ingestion")
    expected = {
        "stream_id": item.stream_id,
        "analyte": item.analyte,
        "qc_level": item.qc_level,
        "instrument_id": item.instrument,
        "method_id": item.method,
        "units": item.units,
        "control_material_lot": item.reference_material_lot,
    }
    actual = payload.model_dump()
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise HTTPException(status_code=422, detail=f"{field} does not match QC backlog item")
    return item


def complete_backlog_item(session: Session, item: QCBacklogItem, record: QCRecord, user: UserContext) -> None:
    if item.id is None or record.id is None:
        raise RuntimeError("Backlog completion requires persisted rows")
    before = item.model_dump(mode="json")
    item.status = QCBacklogStatus.COMPLETED
    item.completed_at = utcnow()
    item.completed_by = user.actor
    item.completed_qc_record_id = record.id
    item.updated_at = item.completed_at
    session.add(item)
    session.flush()
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="complete_qc_backlog_item",
        entity_type="qc_backlog_item",
        entity_id=str(item.id),
        before=before,
        after=backlog_out(item).model_dump(mode="json"),
        reason=record.comments,
        commit=False,
    )


def note_backlog_quarantine(session: Session, item_id: int, quarantine_id: int, user: UserContext) -> None:
    item = get_backlog_item(session, item_id)
    if item.status in {QCBacklogStatus.COMPLETED, QCBacklogStatus.CANCELED}:
        return
    before = item.model_dump(mode="json")
    item.last_quarantine_id = quarantine_id
    item.updated_at = utcnow()
    session.add(item)
    session.flush()
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="qc_backlog_quarantine_attempt",
        entity_type="qc_backlog_item",
        entity_id=str(item.id),
        before=before,
        after=backlog_out(item).model_dump(mode="json"),
        reason="QC run attempt was quarantined",
        commit=False,
    )
    session.flush()
