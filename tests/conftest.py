import os
import pathlib
import sys

import pytest
from sqlmodel import Session, delete

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB_PATH = pathlib.Path("/tmp/bayesianqc_test.db")
os.environ.setdefault("BAYESIANQC_DB_URL", f"sqlite:///{TEST_DB_PATH}")

from app.db import get_engine, init_db
from app.db_models import (
    AlertRecord,
    ApiKey,
    Analyte,
    AuditEntry,
    Capa,
    CapaLink,
    IngestionReceipt,
    Instrument,
    Investigation,
    InvestigationAlertLink,
    Method,
    PosteriorState,
    PriorConfig,
    QCEvent,
    QCRecord,
    StreamConfig,
)
from app.storage import seed_defaults


@pytest.fixture(autouse=True)
def reset_db():
    db_path = TEST_DB_PATH
    init_db()
    with Session(get_engine()) as session:
        for table in [
            IngestionReceipt,
            AlertRecord,
            QCRecord,
            QCEvent,
            InvestigationAlertLink,
            Investigation,
            CapaLink,
            Capa,
            AuditEntry,
            PosteriorState,
            PriorConfig,
            StreamConfig,
            Analyte,
            Method,
            Instrument,
            ApiKey,
        ]:
            session.exec(delete(table))
        session.commit()
        seed_defaults(session)
    yield
    get_engine().dispose()
    if db_path.exists():
        db_path.unlink()
