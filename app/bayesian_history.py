from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, select

from app.db_models import PriorConfig, QCRecord, StreamConfig
from app.timeutils import as_utc


def list_priors(session: Session, stream_id: str) -> list[PriorConfig]:
    return list(
        session.exec(
            select(PriorConfig)
            .where(PriorConfig.stream_id == stream_id)
            .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
        ).all()
    )


def active_prior(priors: list[PriorConfig], at_time: datetime) -> Optional[PriorConfig]:
    active: Optional[PriorConfig] = None
    at_time_utc = as_utc(at_time)
    for prior in priors:
        if as_utc(prior.effective_from) > at_time_utc:
            break
        active = prior
    return active


def list_stream_configs(session: Session, stream_id: str) -> list[StreamConfig]:
    return list(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
        ).all()
    )


def included_records(
    session: Session,
    stream_id: str,
    *,
    through: Optional[datetime] = None,
) -> list[QCRecord]:
    query = select(QCRecord).where(
        QCRecord.stream_id == stream_id,
        QCRecord.include_in_stats == True,
    )
    if through is not None:
        query = query.where(QCRecord.timestamp <= through)
    return list(session.exec(query.order_by(col(QCRecord.timestamp).asc())).all())


def records_after_first_prior(
    records: list[QCRecord],
    priors: list[PriorConfig],
) -> list[QCRecord]:
    if not priors:
        return []
    first_effective = as_utc(priors[0].effective_from)
    return [record for record in records if as_utc(record.timestamp) >= first_effective]
