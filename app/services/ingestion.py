from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.db_models import AlertRecord, QCRecord
from app.domain import Disposition
from app.models import (
    AlertStatus,
    DuplicateStatus,
    IngestionResult,
    QCRecordIn,
    QCRecordOut,
    QuarantineReason,
    QuarantineResult,
)
from app.rbac import UserContext
from app.services.access_scopes import require_backlog_access, require_stream_access
from app.services.ingestion_duplicates import duplicate_candidates, return_exact_duplicate
from app.services.ingestion_evaluation import evaluate_new_record
from app.services.ingestion_support import alert_out, alert_severity, audit_out, normalize_units
from app.services.locks import stream_write_lock
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
    create_alert,
    get_active_stream_config,
    get_idempotent_response,
    record_audit,
    store_receipt,
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
    session.commit()
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

            exact_duplicate, possible_duplicate = duplicate_candidates(session, record)
            if exact_duplicate is not None:
                return return_exact_duplicate(
                    session,
                    existing=exact_duplicate,
                    user=user,
                    idempotency_key=idempotency_key,
                )
            if possible_duplicate is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="possible_duplicate_requires_review",
                )

            duplicate_status = DuplicateStatus.UNIQUE
            record.duplicate_status = duplicate_status
            try:
                with session.begin_nested():
                    signals, risk, disposition = evaluate_new_record(
                        session,
                        record=record,
                        config=config,
                        user=user,
                    )
            except (ArithmeticError, OverflowError, ValueError) as exc:
                return quarantine_with_backlog_note(
                    payload,
                    session,
                    user,
                    [
                        QuarantineFailure(
                            reason=QuarantineReason.MODEL_EVALUATION_FAILURE,
                            detail="Statistical model evaluation failed",
                        )
                    ],
                    {
                        **quarantine_context(payload, config, normalized_value=normalized_value),
                        "model_error_type": type(exc).__name__,
                    },
                    idempotency_key,
                )

            record_payload = payload.model_copy(update={"result_value": normalized_value, "units": normalized_units})
            qc_out = QCRecordOut(
                id=record.id,
                record=record_payload,
                signals=signals,
                bayesian_risk=risk,
                disposition=disposition,
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

            alert_created = None
            if disposition != Disposition.ACCEPT:
                alert_record = session.exec(
                    select(AlertRecord).where(
                        AlertRecord.qc_record_id == record.id,
                        col(AlertRecord.status).in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
                    )
                ).first()
                if alert_record is None:
                    alert_record = create_alert(
                        session,
                        AlertRecord(
                            alert_id=str(uuid4()),
                            stream_id=record.stream_id,
                            qc_record_id=record.id,
                            severity=alert_severity(disposition),
                            disposition=disposition.value,
                            signals=[s.model_dump(mode="json") for s in signals],
                            bayesian_risk=risk.model_dump(mode="json"),
                        ),
                    )
                alert_created = alert_out(alert_record, qc_record_timestamp=record.timestamp)

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
        except HTTPException as exc:
            if exc.status_code == status.HTTP_409_CONFLICT and exc.detail == "possible_duplicate_requires_review":
                raise
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
