from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, false, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.db_models import AccessGrant, AlertRecord, KioskLayout, KioskPanel, QCBacklogItem, QCRecord, StreamConfig
from app.models import EffectiveScopeOut, Role
from app.rbac import UserContext


@dataclass(frozen=True)
class GrantRule:
    site: Optional[str]
    lab_bench: Optional[str]
    stream_id: Optional[str]
    assignment_group: Optional[str]


@dataclass(frozen=True)
class AccessScope:
    unrestricted: bool
    enforced: bool
    grants: tuple[GrantRule, ...] = ()

    def summary(self) -> EffectiveScopeOut:
        return EffectiveScopeOut(
            unrestricted=self.unrestricted,
            enforced=self.enforced,
            sites=sorted({grant.site for grant in self.grants if grant.site}),
            lab_benches=sorted({grant.lab_bench for grant in self.grants if grant.lab_bench}),
            stream_ids=sorted({grant.stream_id for grant in self.grants if grant.stream_id}),
            assignment_groups=sorted({grant.assignment_group for grant in self.grants if grant.assignment_group}),
        )


def access_grants_enforced() -> bool:
    return os.getenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _break_glass_admin_enabled() -> bool:
    return os.getenv("BAYESIANQC_BREAK_GLASS_UNRESTRICTED_ADMIN", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def effective_scope(session: Session, user: UserContext) -> AccessScope:
    enforced = access_grants_enforced()
    if not enforced:
        return AccessScope(unrestricted=True, enforced=False)
    if user.api_key_id is None:
        return AccessScope(unrestricted=user.role == Role.ADMIN and _break_glass_admin_enabled(), enforced=True)
    rows = session.exec(
        select(AccessGrant).where(AccessGrant.api_key_id == user.api_key_id, col(AccessGrant.active) == True)
    ).all()
    grants = tuple(
        GrantRule(
            site=_clean(row.site),
            lab_bench=_clean(row.lab_bench),
            stream_id=_clean(row.stream_id),
            assignment_group=_clean(row.assignment_group),
        )
        for row in rows
    )
    if any(not any((grant.site, grant.lab_bench, grant.stream_id, grant.assignment_group)) for grant in grants):
        return AccessScope(unrestricted=True, enforced=True, grants=grants)
    if not grants and user.role == Role.ADMIN and _break_glass_admin_enabled():
        return AccessScope(unrestricted=True, enforced=True)
    return AccessScope(unrestricted=False, enforced=True, grants=grants)


def scope_summary_for_me(session: Session, user: UserContext) -> EffectiveScopeOut:
    return effective_scope(session, user).summary()


def stream_scope_predicate(scope: AccessScope) -> ColumnElement[bool]:
    if scope.unrestricted:
        return col(StreamConfig.stream_id).is_not(None)
    clauses: list[ColumnElement[bool]] = []
    for grant in scope.grants:
        if grant.assignment_group:
            continue
        conditions: list[ColumnElement[bool]] = []
        if grant.stream_id:
            conditions.append(col(StreamConfig.stream_id) == grant.stream_id)
        if grant.site:
            conditions.append(col(StreamConfig.site) == grant.site)
        if grant.lab_bench:
            conditions.append(col(StreamConfig.lab_bench) == grant.lab_bench)
        if conditions:
            clauses.append(and_(*conditions))
    return or_(*clauses) if clauses else false()


def backlog_scope_predicate(scope: AccessScope) -> ColumnElement[bool]:
    if scope.unrestricted:
        return col(QCBacklogItem.id).is_not(None)
    clauses: list[ColumnElement[bool]] = []
    for grant in scope.grants:
        conditions: list[ColumnElement[bool]] = []
        if grant.stream_id:
            conditions.append(col(QCBacklogItem.stream_id) == grant.stream_id)
        if grant.site:
            conditions.append(col(QCBacklogItem.site) == grant.site)
        if grant.lab_bench:
            conditions.append(col(QCBacklogItem.lab_bench) == grant.lab_bench)
        if grant.assignment_group:
            conditions.append(col(QCBacklogItem.assignment_group) == grant.assignment_group)
        if conditions:
            clauses.append(and_(*conditions))
    return or_(*clauses) if clauses else false()


def _latest_stream_context(session: Session, stream_id: str) -> tuple[Optional[str], Optional[str]] | None:
    row = session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id)
        .order_by(col(StreamConfig.effective_from).desc(), col(StreamConfig.version).desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return row.site, row.lab_bench


def _grant_matches_stream(grant: GrantRule, stream_id: str, site: Optional[str], lab_bench: Optional[str]) -> bool:
    if grant.assignment_group:
        return False
    if grant.stream_id and grant.stream_id != stream_id:
        return False
    if grant.site and grant.site != site:
        return False
    if grant.lab_bench and grant.lab_bench != lab_bench:
        return False
    return bool(grant.stream_id or grant.site or grant.lab_bench)


def stream_is_accessible(session: Session, user: UserContext, stream_id: Optional[str]) -> bool:
    scope = effective_scope(session, user)
    if scope.unrestricted:
        return True
    if not stream_id:
        return False
    context = _latest_stream_context(session, stream_id)
    site, lab_bench = context if context is not None else (None, None)
    return any(_grant_matches_stream(grant, stream_id, site, lab_bench) for grant in scope.grants)


def stream_context_is_accessible(
    session: Session,
    user: UserContext,
    *,
    stream_id: str,
    site: Optional[str],
    lab_bench: Optional[str],
) -> bool:
    scope = effective_scope(session, user)
    if scope.unrestricted:
        return True
    return any(_grant_matches_stream(grant, stream_id, _clean(site), _clean(lab_bench)) for grant in scope.grants)


def require_stream_access(session: Session, user: UserContext, stream_id: Optional[str], *, hide: bool = True) -> None:
    if stream_is_accessible(session, user, stream_id):
        return
    raise HTTPException(status_code=404 if hide else 403, detail="Resource not found")


def require_stream_context_access(
    session: Session,
    user: UserContext,
    *,
    stream_id: str,
    site: Optional[str],
    lab_bench: Optional[str],
) -> None:
    if stream_context_is_accessible(session, user, stream_id=stream_id, site=site, lab_bench=lab_bench):
        return
    raise HTTPException(status_code=403, detail="Target stream scope is not allowed")


def require_record_access(session: Session, user: UserContext, record_id: int, *, hide: bool = True) -> QCRecord:
    record = session.exec(select(QCRecord).where(QCRecord.id == record_id)).first()
    if record is None:
        raise HTTPException(status_code=404, detail="QC record not found")
    require_stream_access(session, user, record.stream_id, hide=hide)
    return record


def require_alert_access(session: Session, user: UserContext, alert_id: str, *, hide: bool = True) -> AlertRecord:
    alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == alert_id)).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    require_stream_access(session, user, alert.stream_id, hide=hide)
    return alert


def require_comment_target_access(
    session: Session,
    user: UserContext,
    *,
    stream_id: Optional[str],
    hide: bool = True,
) -> None:
    require_stream_access(session, user, stream_id, hide=hide)


def _backlog_context_allowed(
    scope: AccessScope,
    stream_id: str,
    site: Optional[str],
    lab_bench: Optional[str],
    assignment_group: Optional[str],
) -> bool:
    if scope.unrestricted:
        return True
    for grant in scope.grants:
        if grant.stream_id and grant.stream_id != stream_id:
            continue
        if grant.site and grant.site != site:
            continue
        if grant.lab_bench and grant.lab_bench != lab_bench:
            continue
        if grant.assignment_group and grant.assignment_group != assignment_group:
            continue
        if any((grant.stream_id, grant.site, grant.lab_bench, grant.assignment_group)):
            return True
    return False


def backlog_item_is_accessible(session: Session, user: UserContext, item: QCBacklogItem) -> bool:
    return _backlog_context_allowed(
        effective_scope(session, user),
        item.stream_id,
        item.site,
        item.lab_bench,
        item.assignment_group,
    )


def backlog_context_is_accessible(
    session: Session,
    user: UserContext,
    *,
    stream_id: str,
    site: Optional[str],
    lab_bench: Optional[str],
    assignment_group: Optional[str],
) -> bool:
    return _backlog_context_allowed(effective_scope(session, user), stream_id, site, lab_bench, assignment_group)


def require_backlog_access(
    session: Session,
    user: UserContext,
    item: QCBacklogItem,
    *,
    target_lab_bench: Optional[str] = None,
    target_assignment_group: Optional[str] = None,
    target_lab_bench_provided: bool = False,
    target_assignment_group_provided: bool = False,
) -> None:
    scope = effective_scope(session, user)
    if not _backlog_context_allowed(scope, item.stream_id, item.site, item.lab_bench, item.assignment_group):
        raise HTTPException(status_code=404, detail="QC backlog item not found")
    target_bench = target_lab_bench if target_lab_bench_provided else item.lab_bench
    target_group = target_assignment_group if target_assignment_group_provided else item.assignment_group
    if not _backlog_context_allowed(scope, item.stream_id, item.site, target_bench, target_group):
        raise HTTPException(status_code=403, detail="Target backlog scope is not allowed")


def require_kiosk_access(session: Session, user: UserContext, layout: KioskLayout) -> None:
    scope = effective_scope(session, user)
    if scope.unrestricted or layout.id is None:
        return
    panels = session.exec(select(KioskPanel).where(KioskPanel.kiosk_id == layout.id, KioskPanel.active == True)).all()
    if not panels:
        if _backlog_context_allowed(scope, "", layout.site, layout.lab_bench, None):
            return
        raise HTTPException(status_code=404, detail="Kiosk layout not found")
    for panel in panels:
        if not stream_is_accessible(session, user, panel.stream_id):
            raise HTTPException(status_code=404, detail="Kiosk layout not found")
