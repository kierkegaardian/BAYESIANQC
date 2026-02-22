from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.migrations import run_sqlite_migrations

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
    run_sqlite_migrations(engine)
