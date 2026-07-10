from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db_models import AlertRecord, Investigation, InvestigationAlertLink
from app.models import InvestigationIn, InvestigationStatus, Role
from app.rbac import UserContext
from app.services.access_scopes import require_alert_access, require_investigation_access
from app.storage import record_audit


@dataclass(frozen=True)
class InvestigationMutation:
    row: Investigation
    alert_id: Optional[str]


def investigation_alert_id(session: Session, investigation_id: int) -> Optional[str]:
    link = session.exec(
        select(InvestigationAlertLink).where(InvestigationAlertLink.investigation_id == investigation_id)
    ).first()
    if link is None:
        return None
    alert = session.exec(select(AlertRecord).where(AlertRecord.id == link.alert_id)).first()
    return alert.alert_id if alert is not None else None


def create_investigation_workflow(
    session: Session,
    *,
    payload: InvestigationIn,
    user: UserContext,
) -> InvestigationMutation:
    external_alert_id = payload.alert_id.strip() if payload.alert_id else None
    alert: Optional[AlertRecord] = None
    if external_alert_id is not None:
        alert = require_alert_access(session, user, external_alert_id)
    elif user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="An accessible alert link is required")

    investigation = Investigation(
        stream_id=alert.stream_id if alert is not None else None,
        problem_statement=payload.problem_statement,
        suspected_cause=payload.suspected_cause,
        containment=payload.containment,
        data_reviewed=payload.data_reviewed,
        outcome=payload.outcome,
        decision=payload.decision,
        status=payload.status or InvestigationStatus.OPEN,
        created_by=user.actor,
    )
    try:
        session.add(investigation)
        session.flush()
        if investigation.id is None:
            raise RuntimeError("Investigation missing id")
        if alert is not None:
            if alert.id is None:
                raise RuntimeError("Alert missing id")
            session.add(InvestigationAlertLink(investigation_id=investigation.id, alert_id=alert.id))
            session.flush()
        after = investigation.model_dump(mode="json") | {"alert_id": external_alert_id}
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="create_investigation",
            entity_type="investigation",
            entity_id=str(investigation.id),
            before=None,
            after=after,
            reason=payload.reason,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(investigation)
    return InvestigationMutation(row=investigation, alert_id=external_alert_id)


def update_investigation_workflow(
    session: Session,
    *,
    investigation_id: int,
    payload: InvestigationIn,
    user: UserContext,
) -> InvestigationMutation:
    investigation = require_investigation_access(session, user, investigation_id)
    before = investigation.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id", "reason"})
    reason = payload.reason.strip() if payload.reason else ""
    if updates and not reason:
        raise HTTPException(status_code=422, detail="reason is required when updating an investigation")
    for field, value in updates.items():
        setattr(investigation, field, value)
    investigation.updated_at = datetime.now(timezone.utc)
    external_alert_id = investigation_alert_id(session, investigation_id)
    try:
        session.add(investigation)
        session.flush()
        after = investigation.model_dump(mode="json") | {"alert_id": external_alert_id}
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="update_investigation",
            entity_type="investigation",
            entity_id=str(investigation_id),
            before=before,
            after=after,
            reason=reason or None,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(investigation)
    return InvestigationMutation(row=investigation, alert_id=external_alert_id)
