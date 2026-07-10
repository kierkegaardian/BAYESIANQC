from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, col, select

from app.db_models import AlertRecord, QCRecord
from app.domain import Disposition
from app.models import AlertStatus, Role
from app.storage import record_audit

_SUPERSEDED_REASON = "evaluation superseded by reprocess"


def _severity(disposition: Disposition) -> str:
    if disposition in {Disposition.REJECT, Disposition.HOLD_FOR_REVIEW}:
        return "action"
    if disposition == Disposition.MONITOR:
        return "warn"
    return "info"


def _audit(
    session: Session,
    *,
    alert: AlertRecord,
    before: Optional[dict],
    actor: str,
    actor_role: Optional[Role],
    api_key_id: Optional[int],
) -> None:
    record_audit(
        session=session,
        actor=actor,
        actor_role=actor_role,
        api_key_id=api_key_id,
        action="reconcile_alert",
        entity_type="alert",
        entity_id=alert.alert_id,
        before=before,
        after=alert.model_dump(mode="json"),
        reason=_SUPERSEDED_REASON,
        commit=False,
    )


def reconcile_stream_alerts(
    session: Session,
    stream_id: str,
    *,
    actor: str = "system:reprocess",
    actor_role: Optional[Role] = None,
    api_key_id: Optional[int] = None,
) -> None:
    records = list(
        session.exec(
            select(QCRecord)
            .where(QCRecord.stream_id == stream_id)
            .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
        ).all()
    )
    alerts = list(
        session.exec(
            select(AlertRecord)
            .where(AlertRecord.stream_id == stream_id)
            .order_by(col(AlertRecord.created_at).asc(), col(AlertRecord.id).asc())
        ).all()
    )
    active_by_record: dict[int, list[AlertRecord]] = defaultdict(list)
    for alert in alerts:
        if alert.qc_record_id is not None and alert.status in {AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED}:
            active_by_record[alert.qc_record_id].append(alert)

    now = datetime.now(timezone.utc)
    for record in records:
        if record.id is None:
            raise RuntimeError("QC record missing id during alert reconciliation")
        active = active_by_record.get(record.id, [])
        accepting = (
            not record.include_in_stats
            or record.disposition is None
            or record.disposition == Disposition.ACCEPT.value
        )
        if accepting:
            for alert in active:
                before = alert.model_dump(mode="json")
                alert.status = AlertStatus.CLOSED
                alert.acknowledged_at = now
                alert.acknowledged_by = actor
                session.add(alert)
                session.flush()
                _audit(
                    session,
                    alert=alert,
                    before=before,
                    actor=actor,
                    actor_role=actor_role,
                    api_key_id=api_key_id,
                )
            continue

        if record.signals is None or record.bayesian_risk is None:
            raise RuntimeError("Non-accepting record is missing its evaluation snapshot")
        disposition = Disposition(record.disposition)
        primary = active[0] if active else None
        if primary is None:
            primary = AlertRecord(
                alert_id=str(uuid4()),
                stream_id=stream_id,
                qc_record_id=record.id,
                severity=_severity(disposition),
                disposition=disposition.value,
                signals=record.signals,
                bayesian_risk=record.bayesian_risk,
            )
            before = None
        else:
            before = primary.model_dump(mode="json")
            primary.severity = _severity(disposition)
            primary.disposition = disposition.value
            primary.signals = record.signals
            primary.bayesian_risk = record.bayesian_risk
        session.add(primary)
        session.flush()
        if before is None or before != primary.model_dump(mode="json"):
            _audit(
                session,
                alert=primary,
                before=before,
                actor=actor,
                actor_role=actor_role,
                api_key_id=api_key_id,
            )

        for stale in active[1:]:
            before = stale.model_dump(mode="json")
            stale.status = AlertStatus.CLOSED
            stale.acknowledged_at = now
            stale.acknowledged_by = actor
            session.add(stale)
            session.flush()
            _audit(
                session,
                alert=stale,
                before=before,
                actor=actor,
                actor_role=actor_role,
                api_key_id=api_key_id,
            )
