from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from app.db_models import AlertRecord, AuditEntry, StreamConfig
from app.domain import Disposition, SignalSeverity
from app.models import (
    AlertOut,
    AlertStatus,
    AuditEntryOut,
    BayesianRisk,
    BayesianRiskStatus,
    FrequentistSignal,
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
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Units do not match stream configuration",
    )


def determine_disposition(
    signals: Sequence[FrequentistSignal],
    risk: Optional[BayesianRisk],
    config: StreamConfig,
) -> Disposition:
    if any(signal.severity == SignalSeverity.ACTION for signal in signals):
        return Disposition.REJECT
    if risk is not None and risk.status == BayesianRiskStatus.UNAVAILABLE:
        return Disposition.HOLD_FOR_REVIEW
    required_hold = config.bayes_hold_consecutive or 1
    required_warn = config.bayes_warn_consecutive or 1
    if risk is not None and risk.hold_streak >= required_hold:
        return Disposition.HOLD_FOR_REVIEW
    if signals or (risk is not None and risk.warn_streak >= required_warn):
        return Disposition.MONITOR
    return Disposition.ACCEPT


def alert_severity(disposition: Disposition) -> str:
    if disposition in {Disposition.REJECT, Disposition.HOLD_FOR_REVIEW}:
        return "action"
    if disposition == Disposition.MONITOR:
        return "warn"
    return "info"


def alert_out(alert: AlertRecord, qc_record_timestamp: Optional[datetime] = None) -> AlertOut:
    return AlertOut(
        id=alert.alert_id,
        stream_id=alert.stream_id,
        created_at=alert.created_at,
        qc_record_id=alert.qc_record_id,
        qc_record_timestamp=qc_record_timestamp,
        signals=[FrequentistSignal.model_validate(signal) for signal in alert.signals],
        bayesian_risk=BayesianRisk.model_validate(alert.bayesian_risk),
        disposition=Disposition(alert.disposition),
        acknowledged=alert.status in {AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED},
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        due_at=alert.due_at,
    )


def audit_out(entry: AuditEntry) -> AuditEntryOut:
    if entry.after is None:
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
        after=entry.after,
        reason=entry.reason,
    )
