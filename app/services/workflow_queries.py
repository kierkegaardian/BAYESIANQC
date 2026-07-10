from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import false, func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.db_models import AlertRecord, AuditEntry, Capa, Investigation, QCRecord
from app.models import AlertStatus, CapaStatus, InvestigationStatus, Role
from app.rbac import UserContext
from app.services.access_scopes import (
    effective_scope,
    require_stream_access,
    stream_id_scope_predicate,
    workflow_stream_scope_predicate,
)
from app.services.workflow_capas import capa_link_ids
from app.services.workflow_investigations import investigation_alert_id


@dataclass(frozen=True)
class AlertPage:
    rows: list[tuple[AlertRecord, Optional[datetime]]]
    total: int


@dataclass(frozen=True)
class AuditPage:
    rows: list[AuditEntry]
    total: int


@dataclass(frozen=True)
class InvestigationView:
    row: Investigation
    alert_id: Optional[str]


@dataclass(frozen=True)
class CapaView:
    row: Capa
    alert_id: Optional[str]
    investigation_id: Optional[int]


@dataclass(frozen=True)
class WorkflowSummary:
    alert_total: int
    alert_open: int
    alert_acknowledged: int
    alert_closed: int
    investigation_total: int
    investigation_open: int
    capa_total: int
    capa_open: int


def _count(session: Session, model: type, clauses: list[ColumnElement[bool]]) -> int:
    value = session.exec(select(func.count()).select_from(model).where(*clauses)).one()
    return int(value)


def list_alert_page(
    session: Session,
    *,
    user: UserContext,
    limit: int,
    offset: int,
    status_filter: Optional[AlertStatus],
    stream_id: Optional[str],
    severity: Optional[str],
    disposition: Optional[str],
    assigned_to: Optional[str],
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> AlertPage:
    clauses: list[ColumnElement[bool]] = [
        stream_id_scope_predicate(session, user, col(AlertRecord.stream_id))
    ]
    if stream_id is not None:
        require_stream_access(session, user, stream_id)
        clauses.append(col(AlertRecord.stream_id) == stream_id)
    if status_filter is not None:
        clauses.append(col(AlertRecord.status) == status_filter)
    else:
        clauses.append(col(AlertRecord.status).in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]))
    if severity is not None:
        clauses.append(col(AlertRecord.severity) == severity)
    if disposition is not None:
        clauses.append(col(AlertRecord.disposition) == disposition)
    if assigned_to is not None:
        clauses.append(col(AlertRecord.assigned_to) == assigned_to)
    if from_time is not None:
        clauses.append(col(AlertRecord.created_at) >= from_time)
    if to_time is not None:
        clauses.append(col(AlertRecord.created_at) <= to_time)
    total = _count(session, AlertRecord, clauses)
    raw_rows = session.exec(
        select(AlertRecord, QCRecord.timestamp)
        .join(QCRecord, col(QCRecord.id) == col(AlertRecord.qc_record_id), isouter=True)
        .where(*clauses)
        .order_by(col(AlertRecord.created_at).desc(), col(AlertRecord.id).desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return AlertPage(rows=[(row[0], row[1]) for row in raw_rows], total=total)


def list_audit_page(
    session: Session,
    *,
    user: UserContext,
    limit: int,
    offset: int,
    action: Optional[str],
    entity_type: Optional[str],
    actor_role: Optional[Role],
) -> AuditPage:
    clauses: list[ColumnElement[bool]] = []
    scope = effective_scope(session, user)
    if not scope.unrestricted:
        if user.api_key_id is None:
            clauses.append(false())
        else:
            clauses.append(col(AuditEntry.api_key_id) == user.api_key_id)
    if action is not None:
        clauses.append(col(AuditEntry.action) == action)
    if entity_type is not None:
        clauses.append(col(AuditEntry.entity_type) == entity_type)
    if actor_role is not None:
        clauses.append(col(AuditEntry.actor_role) == actor_role)
    total = _count(session, AuditEntry, clauses)
    rows = list(
        session.exec(
            select(AuditEntry)
            .where(*clauses)
            .order_by(col(AuditEntry.timestamp).desc(), col(AuditEntry.id).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return AuditPage(rows=rows, total=total)


def list_investigation_views(
    session: Session,
    *,
    user: UserContext,
    status_filter: Optional[InvestigationStatus],
) -> list[InvestigationView]:
    query = select(Investigation).where(
        workflow_stream_scope_predicate(session, user, col(Investigation.stream_id))
    )
    if status_filter is not None:
        query = query.where(Investigation.status == status_filter)
    rows = session.exec(query.order_by(col(Investigation.created_at).desc(), col(Investigation.id).desc())).all()
    return [
        InvestigationView(row=row, alert_id=investigation_alert_id(session, row.id))
        for row in rows
        if row.id is not None
    ]


def list_capa_views(
    session: Session,
    *,
    user: UserContext,
    status_filter: Optional[CapaStatus],
) -> list[CapaView]:
    query = select(Capa).where(workflow_stream_scope_predicate(session, user, col(Capa.stream_id)))
    if status_filter is not None:
        query = query.where(Capa.status == status_filter)
    rows = session.exec(query.order_by(col(Capa.created_at).desc(), col(Capa.id).desc())).all()
    results: list[CapaView] = []
    for row in rows:
        if row.id is None:
            continue
        alert_id, investigation_id = capa_link_ids(session, row.id)
        results.append(CapaView(row=row, alert_id=alert_id, investigation_id=investigation_id))
    return results


def workflow_summary(session: Session, *, user: UserContext) -> WorkflowSummary:
    alert_scope = stream_id_scope_predicate(session, user, col(AlertRecord.stream_id))
    investigation_scope = workflow_stream_scope_predicate(session, user, col(Investigation.stream_id))
    capa_scope = workflow_stream_scope_predicate(session, user, col(Capa.stream_id))
    return WorkflowSummary(
        alert_total=_count(session, AlertRecord, [alert_scope]),
        alert_open=_count(session, AlertRecord, [alert_scope, col(AlertRecord.status) == AlertStatus.OPEN]),
        alert_acknowledged=_count(
            session,
            AlertRecord,
            [alert_scope, col(AlertRecord.status) == AlertStatus.ACKNOWLEDGED],
        ),
        alert_closed=_count(session, AlertRecord, [alert_scope, col(AlertRecord.status) == AlertStatus.CLOSED]),
        investigation_total=_count(session, Investigation, [investigation_scope]),
        investigation_open=_count(
            session,
            Investigation,
            [investigation_scope, col(Investigation.status) != InvestigationStatus.CLOSED],
        ),
        capa_total=_count(session, Capa, [capa_scope]),
        capa_open=_count(
            session,
            Capa,
            [capa_scope, col(Capa.status).not_in([CapaStatus.CLOSED, CapaStatus.DRAFT])],
        ),
    )
