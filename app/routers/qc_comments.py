from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.models import Permission, QCCommentIn, QCCommentOut, QCCommentTargetType
from app.rbac import UserContext, require_permission
from app.services.qc_comments import create_comment, list_comments

router = APIRouter(prefix="/qc/comments", tags=["qc-comments"])


@router.get("", response_model=list[QCCommentOut])
def list_qc_comments(
    target_type: Optional[QCCommentTargetType] = None,
    target_id: Optional[str] = None,
    stream_id: Optional[str] = None,
    qc_record_id: Optional[int] = None,
    alert_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[QCCommentOut]:
    del user
    return list_comments(
        session,
        target_type=target_type,
        target_id=target_id,
        stream_id=stream_id,
        qc_record_id=qc_record_id,
        alert_id=alert_id,
        run_id=run_id,
        limit=limit,
    )


@router.post("", response_model=QCCommentOut)
def create_qc_comment(
    payload: QCCommentIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> QCCommentOut:
    return create_comment(session, payload, user)
