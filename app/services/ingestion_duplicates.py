from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.db_models import QCRecord
from app.domain import Disposition
from app.models import BayesianRisk, DuplicateStatus, FrequentistSignal, IngestionResult, QCRecordIn, QCRecordOut
from app.rbac import UserContext
from app.services.ingestion_support import audit_out
from app.storage import record_audit, store_receipt


def duplicate_candidates(
    session: Session,
    record: QCRecord,
) -> tuple[Optional[QCRecord], Optional[QCRecord]]:
    same_timestamp = list(
        session.exec(
            select(QCRecord).where(
                QCRecord.stream_id == record.stream_id,
                QCRecord.timestamp == record.timestamp,
            )
        ).all()
    )
    exact = next(
        (
            row
            for row in same_timestamp
            if row.result_value == record.result_value and row.run_id == record.run_id
        ),
        None,
    )
    possible = next((row for row in same_timestamp if row is not exact), None)
    return exact, possible


def _stored_qc_out(record: QCRecord) -> QCRecordOut:
    if record.id is None or record.signals is None or record.bayesian_risk is None or record.disposition is None:
        raise RuntimeError("Existing duplicate record is missing its evaluation snapshot")
    payload = QCRecordIn(
        stream_id=record.stream_id,
        result_value=record.result_value,
        timestamp=record.timestamp,
        analyte=record.analyte,
        qc_level=record.qc_level,
        instrument_id=record.instrument_id,
        method_id=record.method_id,
        operator_id=record.operator_id,
        reagent_lot=record.reagent_lot,
        control_material_lot=record.control_material_lot,
        calibration_status=record.calibration_status,
        run_id=record.run_id,
        units=record.units,
        flags=record.flags,
        entry_source=record.entry_source,
        comments=record.comments,
        qc_backlog_item_id=record.qc_backlog_item_id,
    )
    return QCRecordOut(
        id=record.id,
        record=payload,
        signals=[FrequentistSignal.model_validate(signal) for signal in record.signals],
        bayesian_risk=BayesianRisk.model_validate(record.bayesian_risk),
        disposition=Disposition(record.disposition),
    )


def return_exact_duplicate(
    session: Session,
    *,
    existing: QCRecord,
    user: UserContext,
    idempotency_key: Optional[str],
) -> IngestionResult:
    qc_out = _stored_qc_out(existing)
    audit_entry = record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="duplicate_qc_attempt",
        entity_type="qc_record",
        entity_id=str(existing.id),
        before=None,
        after=qc_out.model_dump(mode="json"),
        reason="exact duplicate returned existing evaluation snapshot",
        commit=False,
    )
    result = IngestionResult(
        status="duplicate",
        duplicate=DuplicateStatus.DUPLICATE,
        qc=qc_out,
        alert_created=None,
        audit_entry=audit_out(audit_entry),
        idempotency_key=idempotency_key,
    )
    store_receipt(
        session,
        idempotency_key,
        result.model_dump(mode="json"),
        existing.id,
        existing.stream_id,
        user.api_key_id,
        commit=False,
    )
    session.commit()
    return result
