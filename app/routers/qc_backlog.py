from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.models import (
    Permission,
    QCBacklogItemIn,
    QCBacklogItemOut,
    QCBacklogItemUpdate,
    QCBacklogSource,
    QCBacklogStatus,
)
from app.rbac import UserContext, require_permission
from app.services.qc_backlog import (
    backlog_out,
    create_backlog_item,
    get_backlog_item,
    list_backlog_items,
    update_backlog_item,
)

router = APIRouter(prefix="/qc/backlog", tags=["qc-backlog"])


@router.get("", response_model=list[QCBacklogItemOut])
def list_qc_backlog(
    status_filter: Optional[list[QCBacklogStatus]] = Query(default=None, alias="status"),
    source: Optional[QCBacklogSource] = None,
    instrument: Optional[str] = None,
    lab_bench: Optional[str] = None,
    assignment_group: Optional[str] = None,
    assigned_to: Optional[str] = None,
    stream_id: Optional[str] = None,
    due_from: Optional[datetime] = None,
    due_to: Optional[datetime] = None,
    limit: int = Query(default=200, ge=1, le=500),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[QCBacklogItemOut]:
    del user
    return list_backlog_items(
        session,
        statuses=status_filter,
        source=source,
        instrument=instrument,
        lab_bench=lab_bench,
        assignment_group=assignment_group,
        assigned_to=assigned_to,
        stream_id=stream_id,
        due_from=due_from,
        due_to=due_to,
        limit=limit,
    )


@router.get("/{item_id}", response_model=QCBacklogItemOut)
def get_qc_backlog_item(
    item_id: int,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> QCBacklogItemOut:
    del user
    return backlog_out(get_backlog_item(session, item_id))


@router.post("", response_model=QCBacklogItemOut)
def create_qc_backlog_item(
    payload: QCBacklogItemIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> QCBacklogItemOut:
    return create_backlog_item(session, payload, user)


@router.patch("/{item_id}", response_model=QCBacklogItemOut)
def update_qc_backlog_item(
    item_id: int,
    payload: QCBacklogItemUpdate,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> QCBacklogItemOut:
    return update_backlog_item(session, item_id, payload, user)
