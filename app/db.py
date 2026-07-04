from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.migrations import run_alembic_migrations

_ENGINE: Optional[Engine] = None
DEFAULT_DB_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"


def _database_url() -> str:
    db_url = os.getenv("BAYESIANQC_DB_URL", DEFAULT_DB_URL)
    if db_url.startswith("sqlite"):
        raise RuntimeError("BAYESIANQC app runtime requires Postgres; SQLite is legacy-import input only.")
    if not db_url.startswith("postgresql"):
        raise RuntimeError("BAYESIANQC app runtime requires a postgresql+psycopg SQLAlchemy URL.")
    return db_url


def _build_engine() -> Engine:
    return create_engine(_database_url(), echo=False)


def _engine_url(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


def get_engine() -> Engine:
    global _ENGINE
    db_url = _database_url()
    if _ENGINE is None or _engine_url(_ENGINE) != db_url:
        _ENGINE = _build_engine()
    return _ENGINE


def get_session() -> Iterator[Session]:
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as session:
        yield session


def init_db() -> None:
    engine = get_engine()
    run_alembic_migrations(engine)
