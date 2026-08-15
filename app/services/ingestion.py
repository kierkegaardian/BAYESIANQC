from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.db_models import AlertRecord, AuditEntry, QCRecord, StreamConfig
from app.domain import Disposition
from app.evaluation_models import AlertEvaluationStatus, EvaluationTrigger
from app.evaluations import reprocess_stream_evaluations
from app.models import (
    AlertOut,
    AlertStatus,
    AuditEntryOut,
    BayesianRisk,
    DuplicateStatus,
    FrequentistSignal,
    IngestionResult,
    QCRecordIn,
    QCRecordOut,
    QuarantineReason,
    QuarantineResult,
)
from app.rbac import UserContext
from app.services.access_scopes import require_backlog_access, require_stream_access
from app.services.locks import stream_write_lock
from app.services.evaluation_provenance import alert_evaluation_view, record_evaluation_provenance
from app.services.evaluation_pending import historical_reprocess_required
from app.services.qc_backlog import complete_backlog_item, note_backlog_quarantine, validate_backlog_for_payload
from app.services.quarantine import (
    QuarantineFailure,
    bounds_failures,
    mapping_failures,
    quarantine_context,
    quarantine_ingestion,
    suspicious_timestamp_failure,
    unit_mismatch_failure,
)
from app.storage import (
    detect_duplicate,
    get_active_stream_config,
    get_idempotent_response,
    record_audit,
    store_receipt,
)


def normalize_units(value: float, units: str, config: StreamConfig) -> tuple[float, str]:
    if units == config.units:
        return value, units
    if config.unit_conversions and units in config.unit_conversions:
        conversion = config.unit_conversions[units]
        if isinstance(conversion, dict):
            factor = float(conversion.get("factor", 1.0))
            offset = float(conversion.get("offset", 0.0))
        else:
            factor = float(conversion)
            offset = 0.0
        return value * factor + offset, config.units
    if config.allowed_units and units in config.allowed_units and units == config.units:
        return value, units
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Units do not match stream configuration")


def validate_bounds(value: float, config: StreamConfig) -> None:
    if config.min_value is not None and value < config.min_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Result below configured minimum")
    if config.max_value is not None and value > config.max_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Result above configured maximum")


def alert_out(
    alert: AlertRecord,
    qc_record_timestamp: Optional[datetime] = None,
    session: Session | None = None,
) -> AlertOut:
    acknowledged = alert.status in {AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED}
    evaluation_view = alert_evaluation_view(session, alert) if session is not None else None
    return AlertOut(
        id=alert.alert_id,
        stream_id=alert.stream_id,
        created_at=alert.created_at,
        qc_record_id=alert.qc_record_id,
        qc_record_timestamp=qc_record_timestamp,
        signals=[FrequentistSignal.model_validate(signal) for signal in alert.signals],
        bayesian_risk=BayesianRisk.model_validate(alert.bayesian_risk),
        disposition=Disposition(alert.disposition),
        acknowledged=acknowledged,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        due_at=alert.due_at,
        evaluation=evaluation_view.evaluation if evaluation_view is not None else None,
        evaluation_status=(
            evaluation_view.status
            if evaluation_view is not None
            else AlertEvaluationStatus.LEGACY_UNVERIFIED
        ),
        current_evaluation_id=(
            evaluation_view.current_evaluation_id if evaluation_view is not None else None
        ),
        source_evaluation_id=(
            evaluation_view.source_evaluation_id if evaluation_view is not None else None
        ),
        replacement_alert_id=(
            evaluation_view.replacement_alert_id if evaluation_view is not None else None
        ),
    )


def audit_out(entry: AuditEntry) -> AuditEntryOut:
    after = entry.after
    if after is None:
        raise RuntimeError("Audit entry missing after snapshot")
    return AuditEntryOut(
        timestamp=entry.timestamp,
        actor=entry.actor,
        actor_role=entry.actor_role,
        api_key_id=entry.api_key_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=after,
        reason=entry.reason,
    )


def quarantine_with_backlog_note(
    payload: QCRecordIn,
    session: Session,
    user: UserContext,
    failures: list[QuarantineFailure],
    context: dict,
    idempotency_key: Optional[str],
) -> QuarantineResult:
    result = quarantine_ingestion(payload, session, user, failures, context, idempotency_key)
    if payload.qc_backlog_item_id is not None:
        note_backlog_quarantine(session, payload.qc_backlog_item_id, result.quarantine.id, user)
    return result


def process_ingestion(
    payload: QCRecordIn,
    session: Session,
    user: UserContext,
    idempotency_key: Optional[str],
) -> IngestionResult | QuarantineResult:
    with stream_write_lock(session, payload.stream_id):
        try:
            if idempotency_key:
                receipt = get_idempotent_response(session, idempotency_key)
                if receipt:
                    require_stream_access(session, user, receipt.stream_id or payload.stream_id)
                    if receipt.response.get("status") == "quarantined":
                        return QuarantineResult.model_validate(receipt.response)
                    return IngestionResult.model_validate(receipt.response)

            backlog_item = validate_backlog_for_payload(session, payload) if payload.qc_backlog_item_id else None
            if backlog_item is not None:
                require_backlog_access(session, user, backlog_item)
            config = get_active_stream_config(session, payload.stream_id, payload.timestamp)
            if config is not None:
                require_stream_access(session, user, config.stream_id)
            else:
                require_stream_access(session, user, payload.stream_id)
            if not config:
                return quarantine_with_backlog_note(
                    payload,
                    session,
                    user,
                    [
                        QuarantineFailure(
                            reason=QuarantineReason.MAPPING_FAILURE,
                            field="stream_id",
                            detail="Stream not configured",
                        )
                    ],
                    quarantine_context(payload, None),
                    idempotency_key,
                )
            if historical_reprocess_required(session, payload.stream_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A backdated configuration or prior requires administrator "
                        "evaluation preview/apply before further ingestion"
                    ),
                )

            failures = mapping_failures(payload, config)
            timestamp_failure = suspicious_timestamp_failure(payload)
            if timestamp_failure:
                failures.append(timestamp_failure)
            unit_failure = unit_mismatch_failure(payload, config)
            if unit_failure:
                failures.append(unit_failure)
                normalized_value = payload.result_value
                normalized_units = payload.units
            else:
                normalized_value, normalized_units = normalize_units(payload.result_value, payload.units, config)
                failures.extend(bounds_failures(normalized_value, config))

            if failures:
                return quarantine_with_backlog_note(
                    payload,
                    session,
                    user,
                    failures,
                    quarantine_context(payload, config, normalized_value=normalized_value),
                    idempotency_key,
                )

            record = QCRecord(
                stream_id=payload.stream_id,
                timestamp=payload.timestamp,
                result_value=normalized_value,
                analyte=payload.analyte,
                qc_level=payload.qc_level,
                instrument_id=payload.instrument_id,
                method_id=payload.method_id,
                operator_id=payload.operator_id,
                reagent_lot=payload.reagent_lot,
                control_material_lot=payload.control_material_lot,
                calibration_status=payload.calibration_status,
                run_id=payload.run_id,
                units=normalized_units,
                flags=payload.flags,
                entry_source=payload.entry_source,
                comments=payload.comments,
                raw_payload=payload.model_dump(mode="json"),
                duplicate_status=DuplicateStatus.UNIQUE,
                idempotency_key=idempotency_key,
                qc_backlog_item_id=payload.qc_backlog_item_id,
            )

            duplicate_status = detect_duplicate(session, record)
            record.duplicate_status = duplicate_status
            session.add(record)
            session.flush()
            if record.id is None:
                raise RuntimeError("QC record missing id after flush")

            has_later_record = (
                session.exec(
                    select(QCRecord.id)
                    .where(QCRecord.stream_id == record.stream_id, QCRecord.timestamp > record.timestamp)
                    .limit(1)
                ).first()
                is not None
            )
            evaluation_run = reprocess_stream_evaluations(
                session,
                record.stream_id,
                trigger=(
                    EvaluationTrigger.OUT_OF_ORDER_INGEST
                    if has_later_record
                    else EvaluationTrigger.INGEST
                ),
                actor=user.actor,
                reason=(
                    f"Out-of-order ingestion of QC record {record.id}"
                    if has_later_record
                    else f"Ingestion of QC record {record.id}"
                ),
                record_ids=None if has_later_record else {record.id},
                commit=False,
            )
            session.refresh(record)
            if record.signals is None or record.bayesian_risk is None or record.disposition is None:
                raise RuntimeError("Evaluation did not persist for ingested record")
            signals = [FrequentistSignal.model_validate(signal) for signal in record.signals]
            risk = BayesianRisk.model_validate(record.bayesian_risk)
            disposition = Disposition(record.disposition)

            record_payload = payload.model_copy(update={"result_value": normalized_value, "units": normalized_units})
            qc_out = QCRecordOut(
                id=record.id,
                record=record_payload,
                signals=signals,
                bayesian_risk=risk,
                disposition=disposition,
                evaluation=record_evaluation_provenance(session, record),
            )

            audit_entry = record_audit(
                session=session,
                actor=user.actor,
                actor_role=user.role,
                api_key_id=user.api_key_id,
                action="ingest_qc",
                entity_type="qc_record",
                entity_id=str(record.id),
                before=None,
                after=qc_out.model_dump(mode="json"),
                reason=payload.comments,
                commit=False,
            )

            alert_record = evaluation_run.created_alerts_by_record.get(record.id)
            alert_created = (
                alert_out(alert_record, qc_record_timestamp=record.timestamp, session=session)
                if alert_record is not None
                else None
            )

            if backlog_item is not None:
                complete_backlog_item(session, backlog_item, record, user)

            result = IngestionResult(
                status="accepted",
                duplicate=duplicate_status,
                qc=qc_out,
                alert_created=alert_created,
                audit_entry=audit_out(audit_entry),
                idempotency_key=idempotency_key,
            )
            store_receipt(
                session,
                idempotency_key,
                result.model_dump(mode="json"),
                record.id,
                record.stream_id,
                user.api_key_id,
                commit=False,
            )
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
