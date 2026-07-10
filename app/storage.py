from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.db_models import (
    AlertRecord,
    ApiKey,
    Analyte,
    AuditEntry,
    DEFAULT_RULE_SET,
    EnterpriseSite,
    IngestionReceipt,
    Instrument,
    Method,
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
from app.security import api_key_hash_needs_migration, api_key_lookup_hash, hash_api_key, legacy_sha256_hash, verify_api_key
from app.stats import sample_mean_sd


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


_SEED_EFFECTIVE_FROM = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _seed_local_dev_key_enabled() -> bool:
    value = os.getenv("BAYESIANQC_SEED_LOCAL_DEV_KEY")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def seed_defaults(session: Session) -> None:
    site = session.exec(select(EnterpriseSite).where(EnterpriseSite.name == "Main Lab")).first()
    if not site:
        site = EnterpriseSite(name="Main Lab", created_by="seed")
        session.add(site)
        session.commit()
        session.refresh(site)
    if site.id is None:
        raise RuntimeError("Seed site missing id")

    instrument = session.exec(select(Instrument).where(Instrument.name == "Architect")).first()
    if not instrument:
        instrument = Instrument(
            name="Architect",
            manufacturer="Abbott",
            model="Architect",
            site_id=site.id,
            site="Main Lab",
            created_by="seed",
        )
        session.add(instrument)
        session.commit()
        session.refresh(instrument)
    elif instrument.site_id is None:
        instrument.site_id = site.id
        instrument.site = instrument.site or site.name
        session.add(instrument)
        session.commit()

    instrument_id = instrument.id
    if instrument_id is None:
        raise RuntimeError("Seed instrument missing id")

    method = session.exec(
        select(Method).where(Method.name == "HPLC", Method.instrument_id == instrument_id)
    ).first()
    if not method:
        method = Method(
            name="HPLC",
            instrument_id=instrument_id,
            technique="HPLC",
            created_by="seed",
        )
        session.add(method)
        session.commit()
        session.refresh(method)

    method_id = method.id
    if method_id is None:
        raise RuntimeError("Seed method missing id")

    analyte = session.exec(
        select(Analyte).where(Analyte.name == "HbA1c", Analyte.method_id == method_id)
    ).first()
    if not analyte:
        analyte = Analyte(
            name="HbA1c",
            method_id=method_id,
            units="%",
            created_by="seed",
        )
        session.add(analyte)
        session.commit()
        session.refresh(analyte)

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
            # Bayesian policy defaults: warn on moderate risk of leaving +/-2 SD;
            # hold requires persistence to prevent one-point stop.
            bayes_warn_prob_threshold=0.25,
            bayes_warn_consecutive=1,
            bayes_hold_prob_threshold=0.8,
            bayes_hold_consecutive=2,
            effective_from=_SEED_EFFECTIVE_FROM,
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
            effective_from=_SEED_EFFECTIVE_FROM,
            created_by="seed",
        )
        session.add(prior)
        session.commit()

    if _seed_local_dev_key_enabled():
        default_key = "local-dev-key"
        lookup_hash = api_key_lookup_hash(default_key)
        legacy_hash = legacy_sha256_hash(default_key)
        api_key = session.exec(
            select(ApiKey).where(
                col(ApiKey.active) == True,
                or_(col(ApiKey.key_lookup_hash) == lookup_hash, col(ApiKey.key_hash) == legacy_hash),
            )
        ).first()
        if api_key is None:
            api_key = session.exec(
                select(ApiKey).where(col(ApiKey.active) == True, ApiKey.description == "local dev key")
            ).first()
            if api_key is not None and not verify_api_key(default_key, api_key.key_hash):
                api_key = None
        if api_key:
            if api_key_hash_needs_migration(api_key.key_hash):
                api_key.key_hash = hash_api_key(default_key)
            api_key.key_lookup_hash = lookup_hash
            api_key.role = Role.ADMIN
            api_key.description = api_key.description or "local dev key"
            session.add(api_key)
            session.commit()
        else:
            session.add(
                ApiKey(
                    key_hash=hash_api_key(default_key),
                    key_lookup_hash=lookup_hash,
                    role=Role.ADMIN,
                    description="local dev key",
                )
            )
            session.commit()


def create_stream_config(
    session: Session,
    payload: StreamConfigIn,
    created_by: str,
    *,
    commit: bool = True,
) -> StreamConfig:
    current_version = session.exec(
        select(StreamConfig.version)
        .where(StreamConfig.stream_id == payload.stream_id)
        .order_by(col(StreamConfig.version).desc())
    ).first()
    next_version = (current_version or 0) + 1
    config = StreamConfig(
        stream_id=payload.stream_id,
        analyte=payload.analyte,
        method=payload.method,
        instrument=payload.instrument,
        site=payload.site,
        lab_bench=payload.lab_bench,
        matrix=payload.matrix,
        qc_level=payload.qc_level,
        control_material_lot=payload.control_material_lot,
        control_material_id=payload.control_material_id,
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
        bayes_warn_prob_threshold=payload.bayes_warn_prob_threshold,
        bayes_warn_consecutive=payload.bayes_warn_consecutive,
        bayes_hold_prob_threshold=payload.bayes_hold_prob_threshold,
        bayes_hold_consecutive=payload.bayes_hold_consecutive,
        rule_set=payload.rule_set or DEFAULT_RULE_SET.copy(),
        effective_from=payload.effective_from or utcnow(),
        version=next_version,
        created_by=created_by,
    )
    session.add(config)
    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(config)
    return config


def get_active_stream_config(session: Session, stream_id: str, at_time: datetime) -> Optional[StreamConfig]:
    return session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id, StreamConfig.effective_from <= at_time)
        .order_by(col(StreamConfig.effective_from).desc(), col(StreamConfig.version).desc())
    ).first()


def list_stream_configs(session: Session, stream_id: str) -> list[StreamConfig]:
    return list(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.version).desc())
        ).all()
    )


def create_prior_config(
    session: Session,
    stream_id: str,
    payload: PriorConfigIn,
    created_by: str,
    *,
    commit: bool = True,
) -> PriorConfig:
    if payload.beta0 is None:
        raise ValueError("beta0 must be derived before persisting a prior")
    current_version = session.exec(
        select(PriorConfig.version)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(col(PriorConfig.version).desc())
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
    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(config)
    return config


def get_active_prior(session: Session, stream_id: str, at_time: datetime) -> Optional[PriorConfig]:
    return session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id, PriorConfig.effective_from <= at_time)
        .order_by(col(PriorConfig.effective_from).desc(), col(PriorConfig.version).desc())
    ).first()


def baseline_stats(session: Session, config: StreamConfig, at_time: datetime) -> Tuple[float, float]:
    if config.baseline_start and config.baseline_end:
        rows = session.exec(
            select(QCRecord)
            .where(
                QCRecord.stream_id == config.stream_id,
                QCRecord.include_in_stats == True,
                QCRecord.timestamp >= config.baseline_start,
                QCRecord.timestamp <= config.baseline_end,
            )
            .order_by(col(QCRecord.timestamp))
        ).all()
        if len(rows) >= 2:
            return sample_mean_sd([r.result_value for r in rows])
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
    rows = session.exec(
        select(QCRecord)
        .where(
            QCRecord.stream_id == stream_id,
            QCRecord.include_in_stats == True,
            QCRecord.timestamp < before,
        )
        .order_by(col(QCRecord.timestamp).desc())
        .limit(limit)
    ).all()
    return list(rows)[::-1]


def get_idempotent_response(session: Session, key: str) -> Optional[IngestionReceipt]:
    return session.exec(select(IngestionReceipt).where(IngestionReceipt.idempotency_key == key)).first()


def store_receipt(
    session: Session,
    key: Optional[str],
    response: dict,
    record_id: Optional[int],
    stream_id: Optional[str],
    api_key_id: Optional[int],
    *,
    commit: bool = False,
) -> None:
    if not key:
        return
    receipt = IngestionReceipt(
        idempotency_key=key,
        response=response,
        qc_record_id=record_id,
        stream_id=stream_id,
        api_key_id=api_key_id,
    )
    session.add(receipt)
    session.flush()


def record_audit(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    before: Optional[dict],
    after: Optional[dict],
    reason: Optional[str],
    *,
    actor_role: Optional[Role] = None,
    api_key_id: Optional[int] = None,
    commit: bool = False,
) -> AuditEntry:
    if actor_role is None:
        role_value = actor.split(":key-", 1)[0]
        try:
            actor_role = Role(role_value)
        except ValueError:
            actor_role = None
    if api_key_id is None and ":key-" in actor:
        _, key_id_text = actor.rsplit(":key-", 1)
        if key_id_text.isdigit():
            api_key_id = int(key_id_text)
    entry = AuditEntry(
        actor=actor,
        actor_role=actor_role,
        api_key_id=api_key_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
    )
    session.add(entry)
    session.flush()
    session.refresh(entry)
    return entry


def create_event(session: Session, event: QCEvent) -> QCEvent:
    session.add(event)
    session.flush()
    session.refresh(event)
    return event


def create_alert(session: Session, alert: AlertRecord) -> AlertRecord:
    session.add(alert)
    session.flush()
    session.refresh(alert)
    return alert
