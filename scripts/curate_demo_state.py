#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, col, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_engine
from app.db_models import (
    AlertRecord,
    Capa,
    CapaLink,
    Investigation,
    InvestigationAlertLink,
    QCBacklogItem,
    QCRecord,
    QCRecordQuarantine,
    StreamConfig,
)
from app.models import AlertStatus, CapaStatus, InvestigationStatus, QCBacklogStatus, QuarantineStatus

_CREATOR = "demo-fixture"
_FIXTURE_REVIEWED_AT = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
_FIXTURE_CAPA_DUE_AT = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
_FUEL_OUTLIER_STREAM = "demo-fuel_astm-optidist-fuel-01-d86-ibp"
_PHARMA_DRIFT_STREAM = "demo-pharma_qc-uplc-impurity-02-impurity-b"


def _ensure_investigation(
    session: Session,
    *,
    label: str,
    alert: AlertRecord,
) -> Investigation:
    row = session.exec(
        select(Investigation).where(
            Investigation.created_by == _CREATOR,
            Investigation.problem_statement == label,
        )
    ).first()
    if row is None:
        row = Investigation(
            stream_id=alert.stream_id,
            status=InvestigationStatus.OPEN,
            problem_statement=label,
            suspected_cause="Synthetic demonstration hypothesis pending review",
            containment="Synthetic batch held while evidence is reviewed",
            data_reviewed="QC chart, alert snapshot, and synthetic event history",
            created_by=_CREATOR,
        )
        session.add(row)
        session.flush()
    else:
        row.stream_id = alert.stream_id
        row.status = InvestigationStatus.OPEN
        session.add(row)
        session.flush()
    if row.id is None or alert.id is None:
        raise RuntimeError("Demo workflow rows require persisted identifiers")
    link = session.exec(
        select(InvestigationAlertLink).where(
            InvestigationAlertLink.investigation_id == row.id,
            InvestigationAlertLink.alert_id == alert.id,
        )
    ).first()
    if link is None:
        session.add(InvestigationAlertLink(investigation_id=row.id, alert_id=alert.id))
        session.flush()
    return row


def _ensure_capa(session: Session, alert: AlertRecord, investigation: Investigation) -> Capa:
    row = session.exec(
        select(Capa).where(
            Capa.created_by == _CREATOR,
            Capa.root_cause_category == "Synthetic method drift exercise",
        )
    ).first()
    if row is None:
        row = Capa(
            stream_id=alert.stream_id,
            status=CapaStatus.IMPLEMENTING,
            root_cause_category="Synthetic method drift exercise",
            corrective_actions=[{"action": "Review calibration evidence", "status": "in_progress"}],
            preventive_actions=[{"action": "Add synthetic trend review", "status": "planned"}],
            owners=["Josh demo stakeholder"],
            due_at=_FIXTURE_CAPA_DUE_AT,
            verification_plan="Confirm the next five synthetic controls remain within the selected limits.",
            effectiveness_criteria={"fixture_id": "josh-demo-capa-1", "required_points": 5},
            created_by=_CREATOR,
        )
        session.add(row)
        session.flush()
    else:
        row.stream_id = alert.stream_id
        row.status = CapaStatus.IMPLEMENTING
        row.due_at = _FIXTURE_CAPA_DUE_AT
        session.add(row)
        session.flush()
    if row.id is None or alert.id is None or investigation.id is None:
        raise RuntimeError("Demo CAPA links require persisted identifiers")
    link = session.exec(select(CapaLink).where(CapaLink.capa_id == row.id)).first()
    if link is None:
        session.add(CapaLink(capa_id=row.id, alert_id=alert.id, investigation_id=investigation.id))
        session.flush()
    return row


def _assert_no_r4s(session: Session) -> None:
    for config in session.exec(select(StreamConfig).where(col(StreamConfig.stream_id).like("demo-%"))).all():
        if "R-4s" in config.rule_set.get("rules", []):
            raise RuntimeError(f"R-4s remains configured for {config.stream_id}")
    for record in session.exec(select(QCRecord).where(col(QCRecord.stream_id).like("demo-%"))).all():
        if any(signal.get("rule") == "R-4s" for signal in (record.signals or [])):
            raise RuntimeError(f"R-4s remains in record {record.id}")


def _required_alert(session: Session, alerts: list[AlertRecord], stream_id: str) -> AlertRecord:
    candidates = [alert for alert in alerts if alert.stream_id == stream_id]
    if not candidates:
        raise RuntimeError(f"Guided demo stream has no alert: {stream_id}")
    candidates.sort(key=lambda row: (row.created_at, row.id or 0), reverse=True)
    alert = candidates[0]
    if alert.qc_record_id is None:
        raise RuntimeError(f"Guided demo alert is not linked to a QC record: {stream_id}")
    record = session.get(QCRecord, alert.qc_record_id)
    if record is None or not record.comments or "synthetic demo" not in record.comments:
        raise RuntimeError(f"Guided demo alert is not backed by the expected synthetic scenario: {stream_id}")
    return alert


def main() -> None:
    with Session(get_engine()) as session:
        alerts = list(
            session.exec(
                select(AlertRecord).order_by(col(AlertRecord.created_at).desc(), col(AlertRecord.id).desc())
            ).all()
        )
        if len(alerts) < 14:
            raise SystemExit(f"Synthetic fixture produced only {len(alerts)} alerts; at least 14 are required")
        fuel_alert = _required_alert(session, alerts, _FUEL_OUTLIER_STREAM)
        pharma_alert = _required_alert(session, alerts, _PHARMA_DRIFT_STREAM)
        required_alert_ids = {fuel_alert.id, pharma_alert.id}
        ordered_alerts = [
            fuel_alert,
            pharma_alert,
            *[row for row in alerts if row.id not in required_alert_ids],
        ]
        for index, alert in enumerate(ordered_alerts):
            alert.status = AlertStatus.OPEN if index < 8 else AlertStatus.ACKNOWLEDGED if index < 14 else AlertStatus.CLOSED
            if alert.status == AlertStatus.OPEN:
                alert.acknowledged_at = None
                alert.acknowledged_by = None
            else:
                alert.acknowledged_at = _FIXTURE_REVIEWED_AT
                alert.acknowledged_by = _CREATOR
            session.add(alert)

        first = _ensure_investigation(session, label="Synthetic fuel outlier review", alert=fuel_alert)
        _ensure_investigation(session, label="Synthetic pharma drift review", alert=pharma_alert)
        _ensure_capa(session, fuel_alert, first)

        quarantines = list(
            session.exec(
                select(QCRecordQuarantine).order_by(
                    col(QCRecordQuarantine.created_at).asc(),
                    col(QCRecordQuarantine.id).asc(),
                )
            ).all()
        )
        if len(quarantines) < 2:
            raise SystemExit("Synthetic fixture must include at least two quarantine examples")
        quarantines[0].status = QuarantineStatus.REVIEWED
        quarantines[0].reviewed_at = _FIXTURE_REVIEWED_AT
        quarantines[0].reviewed_by = _CREATOR
        quarantines[0].review_reason = "Synthetic mismatch reviewed for the guided demonstration"
        session.add(quarantines[0])
        _assert_no_r4s(session)
        session.commit()

        backlog = list(session.exec(select(QCBacklogItem)).all())
        open_backlog = sum(row.status == QCBacklogStatus.OPEN for row in backlog)
        completed_backlog = sum(row.status == QCBacklogStatus.COMPLETED for row in backlog)
        if not open_backlog or not completed_backlog:
            raise SystemExit("Synthetic fixture must contain both open and completed backlog rows")
        summary = {
            "alerts": {"open": 8, "acknowledged": 6, "closed": len(alerts) - 14},
            "investigations_open": 2,
            "capas_implementing": 1,
            "backlog": {"open": open_backlog, "completed": completed_backlog},
            "quarantine": {"open": len(quarantines) - 1, "reviewed": 1},
        }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
