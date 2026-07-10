from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db_models import AlertRecord, Capa, CapaLink
from app.models import CapaIn, CapaStatus, Role
from app.rbac import UserContext
from app.services.access_scopes import require_alert_access, require_capa_access, require_investigation_access
from app.storage import record_audit


@dataclass(frozen=True)
class CapaMutation:
    row: Capa
    alert_id: Optional[str]
    investigation_id: Optional[int]


def _validate_capa(capa: Capa) -> None:
    if capa.status == CapaStatus.DRAFT:
        return
    required = {
        "root_cause_category": capa.root_cause_category,
        "corrective_actions": capa.corrective_actions,
        "preventive_actions": capa.preventive_actions,
        "owners": capa.owners,
        "due_at": capa.due_at,
        "verification_plan": capa.verification_plan,
    }
    for field, value in required.items():
        if value is None or value == []:
            raise HTTPException(status_code=422, detail=f"{field} is required for CAPA approval")


def capa_link_ids(session: Session, capa_id: int) -> tuple[Optional[str], Optional[int]]:
    link = session.exec(select(CapaLink).where(CapaLink.capa_id == capa_id)).first()
    if link is None:
        return None, None
    alert_id: Optional[str] = None
    if link.alert_id is not None:
        alert = session.exec(select(AlertRecord).where(AlertRecord.id == link.alert_id)).first()
        alert_id = alert.alert_id if alert is not None else None
    return alert_id, link.investigation_id


def create_capa_workflow(session: Session, *, payload: CapaIn, user: UserContext) -> CapaMutation:
    external_alert_id = payload.alert_id.strip() if payload.alert_id else None
    alert = require_alert_access(session, user, external_alert_id) if external_alert_id is not None else None
    investigation = (
        require_investigation_access(session, user, payload.investigation_id)
        if payload.investigation_id is not None
        else None
    )
    streams = {row.stream_id for row in (alert, investigation) if row is not None and row.stream_id is not None}
    if len(streams) > 1:
        raise HTTPException(status_code=422, detail="Linked alert and investigation must belong to the same stream")
    stream_id = next(iter(streams), None)
    if stream_id is None and user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="An accessible alert or investigation link is required")

    capa = Capa(
        stream_id=stream_id,
        status=payload.status or CapaStatus.DRAFT,
        root_cause_category=payload.root_cause_category,
        corrective_actions=payload.corrective_actions,
        preventive_actions=payload.preventive_actions,
        owners=payload.owners,
        due_at=payload.due_at,
        verification_plan=payload.verification_plan,
        effectiveness_criteria=payload.effectiveness_criteria,
        created_by=user.actor,
    )
    _validate_capa(capa)
    try:
        session.add(capa)
        session.flush()
        if capa.id is None:
            raise RuntimeError("CAPA missing id")
        if alert is not None or investigation is not None:
            session.add(
                CapaLink(
                    capa_id=capa.id,
                    alert_id=alert.id if alert is not None else None,
                    investigation_id=investigation.id if investigation is not None else None,
                )
            )
            session.flush()
        after = capa.model_dump(mode="json") | {
            "alert_id": external_alert_id,
            "investigation_id": payload.investigation_id,
        }
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="create_capa",
            entity_type="capa",
            entity_id=str(capa.id),
            before=None,
            after=after,
            reason=payload.reason,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(capa)
    return CapaMutation(row=capa, alert_id=external_alert_id, investigation_id=payload.investigation_id)


def update_capa_workflow(session: Session, *, capa_id: int, payload: CapaIn, user: UserContext) -> CapaMutation:
    capa = require_capa_access(session, user, capa_id)
    before = capa.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id", "investigation_id", "reason"})
    reason = payload.reason.strip() if payload.reason else ""
    if updates and not reason:
        raise HTTPException(status_code=422, detail="reason is required when updating a CAPA")
    for field, value in updates.items():
        setattr(capa, field, value)
    capa.updated_at = datetime.now(timezone.utc)
    _validate_capa(capa)
    alert_id, investigation_id = capa_link_ids(session, capa_id)
    try:
        session.add(capa)
        session.flush()
        after = capa.model_dump(mode="json") | {"alert_id": alert_id, "investigation_id": investigation_id}
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="update_capa",
            entity_type="capa",
            entity_id=str(capa_id),
            before=before,
            after=after,
            reason=reason or None,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(capa)
    return CapaMutation(row=capa, alert_id=alert_id, investigation_id=investigation_id)
