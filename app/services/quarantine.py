from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session

from app.db_models import AuditEntry, QCRecordQuarantine, StreamConfig
from app.models import (
    AuditEntryOut,
    QCRecordIn,
    QCRecordQuarantineOut,
    QuarantineFailureOut,
    QuarantineReason,
    QuarantineResult,
    QuarantineStatus,
)
from app.rbac import UserContext
from app.storage import record_audit, store_receipt
from app.timeutils import as_utc

FUTURE_TIMESTAMP_GRACE = timedelta(minutes=5)


@dataclass(frozen=True)
class QuarantineFailure:
    reason: QuarantineReason
    detail: str
    field: Optional[str] = None

    def to_json(self) -> dict[str, str]:
        data = {"reason": self.reason.value, "detail": self.detail}
        if self.field:
            data["field"] = self.field
        return data


def quarantine_out(row: QCRecordQuarantine) -> QCRecordQuarantineOut:
    if row.id is None:
        raise RuntimeError("Quarantine record missing id")
    return QCRecordQuarantineOut(
        id=row.id,
        status=row.status,
        reason=row.reason,
        reason_detail=row.reason_detail,
        stream_id=row.stream_id,
        payload=row.payload,
        context=row.context,
        failures=[QuarantineFailureOut.model_validate(failure) for failure in row.failures],
        actor=row.actor,
        actor_role=row.actor_role,
        api_key_id=row.api_key_id,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
        review_reason=row.review_reason,
        qc_record_id=row.qc_record_id,
        idempotency_key=row.idempotency_key,
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


def suspicious_timestamp_failure(payload: QCRecordIn, now: Optional[datetime] = None) -> Optional[QuarantineFailure]:
    checked_at = as_utc(now or datetime.now(timezone.utc))
    observed_at = as_utc(payload.timestamp)
    if observed_at > checked_at + FUTURE_TIMESTAMP_GRACE:
        return QuarantineFailure(
            reason=QuarantineReason.SUSPICIOUS_TIMESTAMP,
            field="timestamp",
            detail="Timestamp is more than five minutes in the future",
        )
    return None


def mapping_failures(payload: QCRecordIn, config: StreamConfig) -> list[QuarantineFailure]:
    expected = {
        "analyte": config.analyte,
        "qc_level": config.qc_level,
        "instrument_id": config.instrument,
        "method_id": config.method,
    }
    actual = {
        "analyte": payload.analyte,
        "qc_level": payload.qc_level,
        "instrument_id": payload.instrument_id,
        "method_id": payload.method_id,
    }
    failures: list[QuarantineFailure] = []
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            failures.append(
                QuarantineFailure(
                    reason=QuarantineReason.MAPPING_FAILURE,
                    field=field,
                    detail=f"{field} does not match stream configuration",
                )
            )
    return failures


def unit_mismatch_failure(payload: QCRecordIn, config: StreamConfig) -> Optional[QuarantineFailure]:
    if payload.units == config.units:
        return None
    if config.unit_conversions and payload.units in config.unit_conversions:
        return None
    if config.allowed_units and payload.units in config.allowed_units and payload.units == config.units:
        return None
    return QuarantineFailure(
        reason=QuarantineReason.UNIT_MISMATCH,
        field="units",
        detail="Units do not match stream configuration and no conversion rule is available",
    )


def bounds_failures(value: float, config: StreamConfig) -> list[QuarantineFailure]:
    failures: list[QuarantineFailure] = []
    if config.min_value is not None and value < config.min_value:
        failures.append(
            QuarantineFailure(
                reason=QuarantineReason.OUT_OF_BOUNDS,
                field="result_value",
                detail="Result below configured minimum",
            )
        )
    if config.max_value is not None and value > config.max_value:
        failures.append(
            QuarantineFailure(
                reason=QuarantineReason.OUT_OF_BOUNDS,
                field="result_value",
                detail="Result above configured maximum",
            )
        )
    return failures


def quarantine_context(
    payload: QCRecordIn,
    config: Optional[StreamConfig],
    *,
    normalized_value: Optional[float] = None,
) -> dict:
    context: dict[str, object] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "received_stream_id": payload.stream_id,
        "entry_source": payload.entry_source.value,
    }
    if normalized_value is not None:
        context["normalized_value"] = normalized_value
    if config is None:
        context["stream_config"] = None
        return context
    context["stream_config"] = {
        "stream_id": config.stream_id,
        "version": config.version,
        "analyte": config.analyte,
        "qc_level": config.qc_level,
        "instrument": config.instrument,
        "method": config.method,
        "units": config.units,
        "min_value": config.min_value,
        "max_value": config.max_value,
        "target_value": config.target_value,
        "sigma": config.sigma,
    }
    return context


def quarantine_ingestion(
    payload: QCRecordIn,
    session: Session,
    user: UserContext,
    failures: list[QuarantineFailure],
    context: dict,
    idempotency_key: Optional[str],
) -> QuarantineResult:
    if not failures:
        raise RuntimeError("Cannot quarantine ingestion without a failure")
    primary = failures[0]
    row = QCRecordQuarantine(
        status=QuarantineStatus.OPEN,
        reason=primary.reason,
        reason_detail=primary.detail,
        stream_id=payload.stream_id,
        payload=payload.model_dump(mode="json"),
        context=context,
        failures=[failure.to_json() for failure in failures],
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        idempotency_key=idempotency_key,
    )
    session.add(row)
    session.flush()
    out = quarantine_out(row)
    audit_entry = record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="quarantine_qc",
        entity_type="qc_quarantine",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=primary.detail,
        commit=False,
    )
    result = QuarantineResult(
        quarantine=out,
        audit_entry=audit_out(audit_entry),
        idempotency_key=idempotency_key,
    )
    store_receipt(
        session,
        idempotency_key,
        result.model_dump(mode="json"),
        None,
        payload.stream_id,
        user.api_key_id,
        commit=False,
    )
    session.commit()
    return result
