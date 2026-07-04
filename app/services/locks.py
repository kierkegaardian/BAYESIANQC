from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.db_models import StreamConfig


def _uses_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _lock_stream_key(session: Session, stream_id: str) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:stream_id))"), {"stream_id": stream_id}).one()


def _lock_stream_row(session: Session, stream_id: str) -> None:
    session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id)
        .order_by(col(StreamConfig.version).desc())
        .with_for_update()
    ).all()


@contextmanager
def stream_write_lock(session: Session, stream_id: str) -> Iterator[None]:
    if _uses_postgres(session):
        _lock_stream_key(session, stream_id)
        _lock_stream_row(session, stream_id)
    yield
