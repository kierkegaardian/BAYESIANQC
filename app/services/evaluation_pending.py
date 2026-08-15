from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, col, select

from app.db_models import PriorConfig, QCRecord, StreamConfig
from app.evaluation_db_models import EvaluationRun
from app.evaluation_models import EvaluationTrigger
from app.timeutils import as_utc


def historical_reprocess_required(session: Session, stream_id: str) -> bool:
    records = list(session.exec(select(QCRecord).where(QCRecord.stream_id == stream_id)).all())
    if not records:
        return False
    last_apply = session.exec(
        select(EvaluationRun)
        .where(
            EvaluationRun.stream_id == stream_id,
            EvaluationRun.trigger == EvaluationTrigger.MANUAL_REPROCESS,
        )
        .order_by(col(EvaluationRun.completed_at).desc())
    ).first()
    applied_at = as_utc(last_apply.completed_at) if last_apply and last_apply.completed_at else None
    versions: list[StreamConfig | PriorConfig] = [
        *session.exec(select(StreamConfig).where(StreamConfig.stream_id == stream_id)).all(),
        *session.exec(select(PriorConfig).where(PriorConfig.stream_id == stream_id)).all(),
    ]
    return any(_is_pending(version.effective_from, version.created_at, records, applied_at) for version in versions)


def _is_pending(
    effective_from: datetime,
    created_at: datetime,
    records: list[QCRecord],
    applied_at: datetime | None,
) -> bool:
    created_utc = as_utc(created_at)
    if applied_at is not None and created_utc <= applied_at:
        return False
    return any(
        as_utc(record.timestamp) >= as_utc(effective_from)
        and as_utc(record.created_at) < created_utc
        for record in records
    )
