from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db import get_session
from app.evaluation_models import (
    EvaluationReprocessApplyIn,
    EvaluationReprocessApplyOut,
    EvaluationReprocessPreviewOut,
)
from app.evaluations import apply_stream_reprocessing, preview_stream_evaluations
from app.models import Permission, Role
from app.rbac import UserContext, require_permission
from app.services.access_scopes import require_stream_access
from app.services.locks import stream_write_lock
from app.storage import record_audit

router = APIRouter(prefix="/streams/{stream_id}/evaluation-reprocess", tags=["evaluations"])


def _require_admin(user: UserContext) -> None:
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator authority required",
        )


@router.post("/preview", response_model=EvaluationReprocessPreviewOut)
def preview_evaluation_reprocess(
    stream_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: UserContext = Depends(require_permission(Permission.OVERRIDE)),
    session: Session = Depends(get_session),
) -> EvaluationReprocessPreviewOut:
    _require_admin(user)
    require_stream_access(session, user, stream_id, hide=False)
    with stream_write_lock(session, stream_id):
        try:
            return preview_stream_evaluations(session, stream_id, offset=offset, limit=limit)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc


@router.post("/apply", response_model=EvaluationReprocessApplyOut)
def apply_evaluation_reprocess(
    stream_id: str,
    payload: EvaluationReprocessApplyIn,
    user: UserContext = Depends(require_permission(Permission.OVERRIDE)),
    session: Session = Depends(get_session),
) -> EvaluationReprocessApplyOut:
    _require_admin(user)
    require_stream_access(session, user, stream_id, hide=False)
    with stream_write_lock(session, stream_id):
        try:
            persisted = apply_stream_reprocessing(
                session,
                stream_id,
                preview_fingerprint=payload.preview_fingerprint,
                actor=user.actor,
                reason=payload.reason,
                commit=False,
            )
            record_audit(
                session,
                actor=user.actor,
                actor_role=user.role,
                api_key_id=user.api_key_id,
                action="apply_evaluation_reprocess",
                entity_type="evaluation_run",
                entity_id=persisted.response.run_id,
                before=None,
                after=persisted.response.model_dump(mode="json"),
                reason=payload.reason,
                commit=False,
            )
            session.commit()
            return persisted.response
        except ValueError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception:
            session.rollback()
            raise
