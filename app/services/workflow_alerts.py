from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session

from app.db_models import AlertRecord
from app.models import AlertStatus, AlertUpdate
from app.rbac import UserContext
from app.services.access_scopes import require_alert_access
from app.storage import record_audit


def update_alert_workflow(
    session: Session,
    *,
    alert_id: str,
    payload: AlertUpdate,
    user: UserContext,
) -> AlertRecord:
    alert = require_alert_access(session, user, alert_id)
    before = alert.model_dump(mode="json")
    changed = False
    if payload.status is not None and payload.status != alert.status:
        alert.status = payload.status
        changed = True
        if payload.status in {AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED}:
            alert.acknowledged_by = user.actor
            alert.acknowledged_at = datetime.now(timezone.utc)
        elif payload.status == AlertStatus.OPEN:
            alert.acknowledged_by = None
            alert.acknowledged_at = None
    if payload.assigned_to is not None and payload.assigned_to != alert.assigned_to:
        alert.assigned_to = payload.assigned_to
        changed = True
    if payload.due_at is not None and payload.due_at != alert.due_at:
        alert.due_at = payload.due_at
        changed = True
    reason = payload.reason.strip() if payload.reason else ""
    if changed and not reason:
        raise HTTPException(status_code=422, detail="reason is required when updating an alert")
    if not changed:
        return alert
    try:
        session.add(alert)
        session.flush()
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="update_alert",
            entity_type="alert",
            entity_id=alert.alert_id,
            before=before,
            after=alert.model_dump(mode="json"),
            reason=reason or None,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(alert)
    return alert
