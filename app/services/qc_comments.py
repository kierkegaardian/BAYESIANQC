from __future__ import annotations

from typing import Optional, TypedDict

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.db_models import AlertRecord, QCComment, QCRecord
from app.models import QCCommentIn, QCCommentOut, QCCommentTargetType
from app.rbac import UserContext
from app.services.access_scopes import (
    require_alert_access,
    require_comment_target_access,
    require_record_access,
    stream_id_scope_predicate,
)
from app.storage import record_audit


class TargetContext(TypedDict):
    stream_id: Optional[str]
    qc_record_id: Optional[int]
    alert_id: Optional[str]
    run_id: Optional[str]


def comment_out(comment: QCComment) -> QCCommentOut:
    if comment.id is None:
        raise RuntimeError("QC comment missing id")
    return QCCommentOut(
        id=comment.id,
        target_type=comment.target_type,
        target_id=comment.target_id,
        stream_id=comment.stream_id,
        qc_record_id=comment.qc_record_id,
        alert_id=comment.alert_id,
        run_id=comment.run_id,
        body=comment.body,
        actor=comment.actor,
        actor_role=comment.actor_role,
        api_key_id=comment.api_key_id,
        created_at=comment.created_at,
    )


def _target_record_context(session: Session, target_id: str) -> TargetContext:
    try:
        record_id = int(target_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="qc_record target_id must be an integer") from exc
    record = session.exec(select(QCRecord).where(QCRecord.id == record_id)).first()
    if record is None or record.id is None:
        raise HTTPException(status_code=404, detail="QC record target not found")
    return {
        "stream_id": record.stream_id,
        "qc_record_id": record.id,
        "alert_id": None,
        "run_id": record.run_id,
    }


def _target_alert_context(session: Session, target_id: str) -> TargetContext:
    alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == target_id)).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert target not found")
    run_id: Optional[str] = None
    if alert.qc_record_id is not None:
        record = session.exec(select(QCRecord).where(QCRecord.id == alert.qc_record_id)).first()
        run_id = record.run_id if record else None
    return {
        "stream_id": alert.stream_id,
        "qc_record_id": alert.qc_record_id,
        "alert_id": alert.alert_id,
        "run_id": run_id,
    }


def _target_run_context(session: Session, target_id: str, stream_id: Optional[str]) -> TargetContext:
    records = list(
        session.exec(
            select(QCRecord)
            .where(QCRecord.run_id == target_id)
            .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
            .limit(25)
        ).all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="QC run target not found")
    stream_ids = {record.stream_id for record in records}
    if stream_id is not None and stream_id not in stream_ids:
        raise HTTPException(status_code=404, detail="QC run target not found")
    return {
        "stream_id": stream_id or (next(iter(stream_ids)) if len(stream_ids) == 1 else None),
        "qc_record_id": records[0].id if len(records) == 1 else None,
        "alert_id": None,
        "run_id": target_id,
    }


def _target_context(session: Session, payload: QCCommentIn) -> TargetContext:
    if payload.target_type == QCCommentTargetType.QC_RECORD:
        return _target_record_context(session, payload.target_id)
    if payload.target_type == QCCommentTargetType.ALERT:
        return _target_alert_context(session, payload.target_id)
    return _target_run_context(session, payload.target_id, payload.stream_id)


def create_comment(session: Session, payload: QCCommentIn, user: UserContext) -> QCCommentOut:
    context = _target_context(session, payload)
    require_comment_target_access(session, user, stream_id=context["stream_id"], hide=True)
    comment = QCComment(
        target_type=payload.target_type,
        target_id=payload.target_id,
        stream_id=context["stream_id"],
        qc_record_id=context["qc_record_id"],
        alert_id=context["alert_id"],
        run_id=context["run_id"],
        body=payload.body,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
    )
    try:
        session.add(comment)
        session.flush()
        out = comment_out(comment)
        record_audit(
            session=session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="create_qc_comment",
            entity_type="qc_comment",
            entity_id=str(out.id),
            before=None,
            after=out.model_dump(mode="json"),
            reason=out.body,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(comment)
    return comment_out(comment)


def list_comments(
    session: Session,
    *,
    user: UserContext,
    target_type: Optional[QCCommentTargetType] = None,
    target_id: Optional[str] = None,
    stream_id: Optional[str] = None,
    qc_record_id: Optional[int] = None,
    alert_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 200,
) -> list[QCCommentOut]:
    if target_type is not None and target_id is not None:
        require_comment_target_access(session, user, stream_id=_target_context(session, QCCommentIn(target_type=target_type, target_id=target_id, body="scope-check", stream_id=stream_id))["stream_id"])
    if qc_record_id is not None:
        require_record_access(session, user, qc_record_id)
    if alert_id is not None:
        require_alert_access(session, user, alert_id)
    if stream_id is not None:
        require_comment_target_access(session, user, stream_id=stream_id)
    query = select(QCComment)
    if target_type is not None:
        query = query.where(QCComment.target_type == target_type)
    if target_id is not None:
        query = query.where(QCComment.target_id == target_id)
    if stream_id is not None:
        query = query.where(QCComment.stream_id == stream_id)
    if qc_record_id is not None:
        query = query.where(QCComment.qc_record_id == qc_record_id)
    if alert_id is not None:
        query = query.where(QCComment.alert_id == alert_id)
    if run_id is not None:
        query = query.where(QCComment.run_id == run_id)
    query = query.where(stream_id_scope_predicate(session, user, col(QCComment.stream_id)))
    rows = session.exec(
        query.order_by(col(QCComment.created_at).asc(), col(QCComment.id).asc()).limit(limit)
    ).all()
    return [comment_out(row) for row in rows]
