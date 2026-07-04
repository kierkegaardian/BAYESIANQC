import os
import pathlib
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, delete

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_TEST_BASE_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"
_TEST_DATABASE_NAME = f"bayesianqc_pytest_{os.getpid()}"
_TEST_DATABASE_CREATED = False
_BASE_POSTGRES_URL: str | None = None


def _postgres_base_url() -> str:
    global _BASE_POSTGRES_URL
    if _BASE_POSTGRES_URL is not None:
        return _BASE_POSTGRES_URL
    value = (
        os.environ.get("BAYESIANQC_POSTGRES_TEST_URL")
        or os.environ.get("BAYESIANQC_DB_URL")
        or DEFAULT_TEST_BASE_URL
    )
    if value.startswith("sqlite"):
        raise RuntimeError("Tests are Postgres-only; set BAYESIANQC_POSTGRES_TEST_URL to a Postgres URL.")
    if not value.startswith("postgresql"):
        raise RuntimeError("BAYESIANQC tests require a postgresql+psycopg SQLAlchemy URL.")
    _BASE_POSTGRES_URL = value
    return value


def _test_database_url() -> str:
    base = make_url(_postgres_base_url())
    return base.set(database=_TEST_DATABASE_NAME).render_as_string(hide_password=False)


def _maintenance_url() -> str:
    return make_url(_postgres_base_url()).set(database="postgres").render_as_string(hide_password=False)


def _ensure_test_database() -> None:
    global _TEST_DATABASE_CREATED
    if _TEST_DATABASE_CREATED:
        return
    admin_engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DATABASE_NAME}"'))
            connection.execute(text(f'CREATE DATABASE "{_TEST_DATABASE_NAME}"'))
    except OperationalError as exc:
        raise RuntimeError(
            "BAYESIANQC tests require local Postgres. Run `docker compose up -d postgres` "
            "or set BAYESIANQC_POSTGRES_TEST_URL to a reachable disposable Postgres base URL."
        ) from exc
    finally:
        admin_engine.dispose()
    _TEST_DATABASE_CREATED = True


def _drop_test_database() -> None:
    if not _TEST_DATABASE_CREATED:
        return
    admin_engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": _TEST_DATABASE_NAME},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DATABASE_NAME}"'))
    admin_engine.dispose()


os.environ.setdefault("BAYESIANQC_POSTGRES_TEST_URL", _postgres_base_url())
os.environ["BAYESIANQC_DB_URL"] = _test_database_url()
os.environ.setdefault("BAYESIANQC_SEED_LOCAL_DEV_KEY", "1")

from app.db import get_engine, init_db
from app.db_models import (
    AlertRecord,
    ApiKey,
    Analyte,
    AuditEntry,
    Capa,
    CapaLink,
    ControlMaterial,
    IngestionReceipt,
    Instrument,
    Investigation,
    InvestigationAlertLink,
    Method,
    PosteriorState,
    QCBacklogItem,
    QCComment,
    KioskLayout,
    KioskPanel,
    PriorConfig,
    QCEvent,
    QCRecord,
    QCRecordQuarantine,
    StreamConfig,
)
from app.import_db_models import (
    CollectorTransferEvent,
    ImportArtifact,
    ImportBatch,
    ImportRow,
    InstrumentPeak,
    InstrumentRun,
    ParserProfile,
)
from app.storage import seed_defaults


@pytest.fixture(autouse=True)
def reset_db():
    _ensure_test_database()
    init_db()
    with Session(get_engine()) as session:
        for table in [
            IngestionReceipt,
            CollectorTransferEvent,
            InstrumentPeak,
            ImportArtifact,
            ImportRow,
            InstrumentRun,
            ImportBatch,
            ParserProfile,
            QCComment,
            KioskPanel,
            KioskLayout,
            AlertRecord,
            QCRecord,
            QCRecordQuarantine,
            QCBacklogItem,
            QCEvent,
            InvestigationAlertLink,
            Investigation,
            CapaLink,
            Capa,
            AuditEntry,
            PosteriorState,
            PriorConfig,
            StreamConfig,
            ControlMaterial,
            Analyte,
            Method,
            Instrument,
            ApiKey,
        ]:
            session.execute(delete(table))
        session.commit()
        seed_defaults(session)
    yield
    get_engine().dispose()


def pytest_sessionfinish(session, exitstatus) -> None:
    del session, exitstatus
    get_engine().dispose()
    _drop_test_database()
