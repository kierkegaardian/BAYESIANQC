from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

_ENGINE: Optional[Engine] = None


def _build_engine() -> Engine:
    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(db_url, echo=False, connect_args=connect_args)
    if db_url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def get_engine() -> Engine:
    global _ENGINE
    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
    if _ENGINE is None or str(_ENGINE.url) != db_url:
        _ENGINE = _build_engine()
    return _ENGINE


async def get_session() -> AsyncIterator[Session]:
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as session:
        yield session


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_columns(engine)


def _ensure_sqlite_columns(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    connection = engine.raw_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA table_info(qcrecord)")
        columns = {row[1] for row in cursor.fetchall()}
        if "include_in_stats" not in columns:
            cursor.execute("ALTER TABLE qcrecord ADD COLUMN include_in_stats BOOLEAN DEFAULT 1")
        if "resolved_at" not in columns:
            cursor.execute("ALTER TABLE qcrecord ADD COLUMN resolved_at DATETIME")
        if "resolved_by" not in columns:
            cursor.execute("ALTER TABLE qcrecord ADD COLUMN resolved_by VARCHAR")
        if "resolved_reason" not in columns:
            cursor.execute("ALTER TABLE qcrecord ADD COLUMN resolved_reason VARCHAR")
        cursor.execute("UPDATE qcrecord SET include_in_stats = 1 WHERE include_in_stats IS NULL")

        cursor.execute("PRAGMA table_info(posteriorstate)")
        columns = {row[1] for row in cursor.fetchall()}
        if "prior_id" not in columns:
            cursor.execute("ALTER TABLE posteriorstate ADD COLUMN prior_id INTEGER")
        if "config_id" not in columns:
            cursor.execute("ALTER TABLE posteriorstate ADD COLUMN config_id INTEGER")
        if "warn_streak" not in columns:
            cursor.execute("ALTER TABLE posteriorstate ADD COLUMN warn_streak INTEGER DEFAULT 0")
        if "hold_streak" not in columns:
            cursor.execute("ALTER TABLE posteriorstate ADD COLUMN hold_streak INTEGER DEFAULT 0")
        cursor.execute("UPDATE posteriorstate SET warn_streak = 0 WHERE warn_streak IS NULL")
        cursor.execute("UPDATE posteriorstate SET hold_streak = 0 WHERE hold_streak IS NULL")

        cursor.execute("PRAGMA table_info(streamconfig)")
        columns = {row[1] for row in cursor.fetchall()}
        if "bayes_warn_prob_threshold" not in columns:
            cursor.execute("ALTER TABLE streamconfig ADD COLUMN bayes_warn_prob_threshold FLOAT")
        if "bayes_warn_consecutive" not in columns:
            cursor.execute("ALTER TABLE streamconfig ADD COLUMN bayes_warn_consecutive INTEGER")
        if "bayes_hold_prob_threshold" not in columns:
            cursor.execute("ALTER TABLE streamconfig ADD COLUMN bayes_hold_prob_threshold FLOAT")
        if "bayes_hold_consecutive" not in columns:
            cursor.execute("ALTER TABLE streamconfig ADD COLUMN bayes_hold_consecutive INTEGER")
        # Backfill defaults for existing rows (safe for local prototype).
        cursor.execute(
            """
            UPDATE streamconfig
            SET
              bayes_warn_prob_threshold = COALESCE(bayes_warn_prob_threshold, 0.25),
              bayes_warn_consecutive = COALESCE(bayes_warn_consecutive, 1),
              bayes_hold_prob_threshold = COALESCE(bayes_hold_prob_threshold, 0.8),
              bayes_hold_consecutive = COALESCE(bayes_hold_consecutive, 2)
            """
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()
