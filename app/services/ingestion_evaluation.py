from __future__ import annotations

from sqlmodel import Session, select

from app import bayesian, frequentist
from app.db_models import QCRecord, StreamConfig
from app.domain import Disposition
from app.evaluations import reprocess_stream_evaluations
from app.models import BayesianRisk, FrequentistSignal
from app.rbac import UserContext
from app.services.ingestion_support import determine_disposition


def evaluate_new_record(
    session: Session,
    *,
    record: QCRecord,
    config: StreamConfig,
    user: UserContext,
) -> tuple[list[FrequentistSignal], BayesianRisk, Disposition]:
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
    if has_later_record:
        reprocess_stream_evaluations(
            session,
            record.stream_id,
            commit=False,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
        )
        session.refresh(record)
        if record.signals is None or record.bayesian_risk is None or record.disposition is None:
            raise RuntimeError("Reprocessing did not persist evaluations for ingested record")
        return (
            [FrequentistSignal.model_validate(signal) for signal in record.signals],
            BayesianRisk.model_validate(record.bayesian_risk),
            Disposition(record.disposition),
        )

    signals = frequentist.evaluate_rules(
        session,
        record.result_value,
        record.timestamp,
        record.stream_id,
        config,
    )
    risk = bayesian.infer_risk(
        session,
        record.result_value,
        record.timestamp,
        record.stream_id,
        config,
        commit=False,
    )
    disposition = determine_disposition(signals, risk, config)
    record.signals = [signal.model_dump(mode="json") for signal in signals]
    record.bayesian_risk = risk.model_dump(mode="json")
    record.disposition = disposition.value
    session.add(record)
    return signals, risk, disposition
