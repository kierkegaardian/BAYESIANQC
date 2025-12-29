from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlmodel import Session, select

from app.db_models import (
    AlertRecord,
    ApiKey,
    AuditEntry,
    Capa,
    CapaLink,
    DEFAULT_RULE_SET,
    IngestionReceipt,
    Investigation,
    InvestigationAlertLink,
    PriorConfig,
    QCEvent,
    QCRecord,
    StreamConfig,
)
from app.models import (
    DuplicateStatus,
    PriorConfigIn,
    Role,
    StreamConfigIn,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def seed_defaults(session: Session) -> None:
    stream_exists = session.exec(select(StreamConfig).where(StreamConfig.stream_id == "hba1c-arch")).first()
    if not stream_exists:
        stream = StreamConfig(
            stream_id="hba1c-arch",
            analyte="HbA1c",
            method="HPLC",
            instrument="Architect",
            site="Main Lab",
            matrix=None,
            qc_level="Level 1",
            control_material_lot="LOT-001",
            units="%",
            target_value=5.2,
            sigma=0.25,
            action_limit_sd=3.0,
            warning_limit_sd=2.0,
            created_by="seed",
        )
        session.add(stream)
        session.commit()

    prior_exists = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).first()
    if not prior_exists:
        prior = PriorConfig(
            stream_id="hba1c-arch",
            mu0=5.2,
            kappa0=1.0,
            alpha0=2.0,
            beta0=0.25**2,
            created_by="seed",
        )
        session.add(prior)
        session.commit()

    api_key_exists = session.exec(select(ApiKey)).first()
    if not api_key_exists:
        default_key = "local-dev-key"
        key_hash = hashlib.sha256(default_key.encode("utf-8")).hexdigest()
        session.add(ApiKey(key_hash=key_hash, role=Role.QC_ANALYST, description="local dev key"))
        session.commit()


def create_stream_config(session: Session, payload: StreamConfigIn, created_by: str) -> StreamConfig:
    current_version = session.exec(
        select(StreamConfig.version).where(StreamConfig.stream_id == payload.stream_id).order_by(StreamConfig.version.desc())
    ).first()
    next_version = (current_version or 0) + 1
    config = StreamConfig(
        stream_id=payload.stream_id,
        analyte=payload.analyte,
        method=payload.method,
        instrument=payload.instrument,
        site=payload.site,
        matrix=payload.matrix,
        qc_level=payload.qc_level,
        control_material_lot=payload.control_material_lot,
        units=payload.units,
        target_value=payload.target_value,
        sigma=payload.sigma,
        action_limit_sd=payload.action_limit_sd,
        warning_limit_sd=payload.warning_limit_sd,
        min_value=payload.min_value,
        max_value=payload.max_value,
        allowed_units=payload.allowed_units,
        unit_conversions=payload.unit_conversions,
        baseline_start=payload.baseline_start,
        baseline_end=payload.baseline_end,
        risk_threshold_warn=payload.risk_threshold_warn,
        risk_threshold_hold=payload.risk_threshold_hold,
        rule_set=payload.rule_set or DEFAULT_RULE_SET.copy(),
        effective_from=payload.effective_from or utcnow(),
        version=next_version,
        created_by=created_by,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def get_active_stream_config(session: Session, stream_id: str, at_time: datetime) -> Optional[StreamConfig]:
    config = session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id, StreamConfig.effective_from <= at_time)
        .order_by(StreamConfig.effective_from.desc(), StreamConfig.version.desc())
    ).first()
    if config:
        return config
    return session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id)
        .order_by(StreamConfig.effective_from.asc(), StreamConfig.version.asc())
    ).first()


def list_stream_configs(session: Session, stream_id: str) -> list[StreamConfig]:
    return session.exec(
        select(StreamConfig).where(StreamConfig.stream_id == stream_id).order_by(StreamConfig.version.desc())
    ).all()


def create_prior_config(session: Session, stream_id: str, payload: PriorConfigIn, created_by: str) -> PriorConfig:
    current_version = session.exec(
        select(PriorConfig.version).where(PriorConfig.stream_id == stream_id).order_by(PriorConfig.version.desc())
    ).first()
    next_version = (current_version or 0) + 1
    config = PriorConfig(
        stream_id=stream_id,
        mu0=payload.mu0,
        kappa0=payload.kappa0,
        alpha0=payload.alpha0,
        beta0=payload.beta0,
        effective_from=payload.effective_from or utcnow(),
        version=next_version,
        created_by=created_by,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def get_active_prior(session: Session, stream_id: str, at_time: datetime) -> Optional[PriorConfig]:
    prior = session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id, PriorConfig.effective_from <= at_time)
        .order_by(PriorConfig.effective_from.desc(), PriorConfig.version.desc())
    ).first()
    if prior:
        return prior
    return session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(PriorConfig.effective_from.asc(), PriorConfig.version.asc())
    ).first()


def baseline_stats(session: Session, config: StreamConfig, at_time: datetime) -> Optional[Tuple[float, float]]:
    if config.baseline_start and config.baseline_end:
        rows = session.exec(
            select(QCRecord)
            .where(
                QCRecord.stream_id == config.stream_id,
                QCRecord.timestamp >= config.baseline_start,
                QCRecord.timestamp <= config.baseline_end,
            )
            .order_by(QCRecord.timestamp)
        ).all()
        if len(rows) >= 2:
            values = [r.result_value for r in rows]
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            return mean, variance ** 0.5
    return config.target_value, config.sigma


def detect_duplicate(session: Session, record: QCRecord) -> DuplicateStatus:
    exact = session.exec(
        select(QCRecord).where(
            QCRecord.stream_id == record.stream_id,
            QCRecord.timestamp == record.timestamp,
            QCRecord.result_value == record.result_value,
            QCRecord.run_id == record.run_id,
        )
    ).first()
    if exact:
        return DuplicateStatus.DUPLICATE
    possible = session.exec(
        select(QCRecord).where(QCRecord.stream_id == record.stream_id, QCRecord.timestamp == record.timestamp)
    ).first()
    if possible:
        return DuplicateStatus.POSSIBLE_DUPLICATE
    return DuplicateStatus.UNIQUE


def get_recent_records(session: Session, stream_id: str, before: datetime, limit: int) -> list[QCRecord]:
    return session.exec(
        select(QCRecord)
        .where(QCRecord.stream_id == stream_id, QCRecord.timestamp < before)
        .order_by(QCRecord.timestamp.desc())
        .limit(limit)
    ).all()[::-1]


def get_idempotent_response(session: Session, key: str) -> Optional[IngestionReceipt]:
    return session.exec(select(IngestionReceipt).where(IngestionReceipt.idempotency_key == key)).first()


def store_receipt(session: Session, key: Optional[str], response: dict, record_id: Optional[int]) -> None:
    if not key:
        return
    receipt = IngestionReceipt(idempotency_key=key, response=response, qc_record_id=record_id)
    session.add(receipt)
    session.commit()


def record_audit(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    before: Optional[dict],
    after: Optional[dict],
    reason: Optional[str],
) -> AuditEntry:
    entry = AuditEntry(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def create_event(session: Session, event: QCEvent) -> QCEvent:
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def create_alert(session: Session, alert: AlertRecord) -> AlertRecord:
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def update_alert(session: Session, alert: AlertRecord) -> AlertRecord:
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def create_investigation(session: Session, investigation: Investigation, alert_id: Optional[int]) -> Investigation:
    session.add(investigation)
    session.commit()
    session.refresh(investigation)
    if alert_id:
        session.add(InvestigationAlertLink(investigation_id=investigation.id, alert_id=alert_id))
        session.commit()
    return investigation


def update_investigation(session: Session, investigation: Investigation) -> Investigation:
    investigation.updated_at = utcnow()
    session.add(investigation)
    session.commit()
    session.refresh(investigation)
    return investigation


def create_capa(session: Session, capa: Capa, alert_id: Optional[int], investigation_id: Optional[int]) -> Capa:
    session.add(capa)
    session.commit()
    session.refresh(capa)
    if alert_id or investigation_id:
        session.add(CapaLink(capa_id=capa.id, alert_id=alert_id, investigation_id=investigation_id))
        session.commit()
    return capa


def update_capa(session: Session, capa: Capa) -> Capa:
    capa.updated_at = utcnow()
    session.add(capa)
    session.commit()
    session.refresh(capa)
    return capa
