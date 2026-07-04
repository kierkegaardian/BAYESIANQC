from __future__ import annotations

import pathlib
import os
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, col, select

import app.db as app_db
from app.db_models import PosteriorState, PriorConfig, QCRecord
from app.main import app
from app.models import EntrySource, QCRecordIn, Role
from app.rbac import UserContext
from app.services.ingestion import process_ingestion
from app.storage import seed_defaults
from scripts import rehearse_sqlite_to_postgres as rehearsal

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _index_columns(indexes: Sequence[Mapping[str, object]], index_name: str) -> list[str]:
    for index in indexes:
        if index.get("name") == index_name:
            columns = index.get("column_names")
            if isinstance(columns, list):
                return [str(column) for column in columns]
    raise AssertionError(f"Missing index {index_name}")


def test_copy_rehearsal_rejects_non_disposable_targets() -> None:
    with pytest.raises(RuntimeError, match="disposable Postgres target"):
        rehearsal._require_disposable_copy_target(
            "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"
        )


def _postgres_base_url() -> str:
    value = os.getenv("BAYESIANQC_POSTGRES_TEST_URL")
    if not value:
        pytest.skip("BAYESIANQC_POSTGRES_TEST_URL is required for Postgres migration tests")
    if not value.startswith("postgresql"):
        pytest.skip("BAYESIANQC_POSTGRES_TEST_URL must be a Postgres SQLAlchemy URL")
    return value


@pytest.fixture()
def disposable_postgres_url() -> Iterator[str]:
    base = make_url(_postgres_base_url())
    database_name = f"bayesianqc_test_{os.getpid()}_{uuid4().hex[:10]}"
    maintenance_url = base.set(database="postgres")
    target_url = base.set(database=database_name).render_as_string(hide_password=False)
    admin_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    try:
        yield target_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def _qc_payload(index: int) -> QCRecordIn:
    return QCRecordIn(
        stream_id="hba1c-arch",
        result_value=5.2 + index * 0.01,
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=index),
        analyte="HbA1c",
        qc_level="Level 1",
        instrument_id="Architect",
        method_id="HPLC",
        operator_id="postgres-test",
        reagent_lot="RL-PG",
        control_material_lot="LOT-001",
        calibration_status="ok",
        run_id=f"postgres-test-{index}",
        units="%",
        flags=[],
        entry_source=EntrySource.MANUAL,
        comments="postgres migration test",
    )


def _qc_payload_json(index: int) -> dict[str, object]:
    return _qc_payload(index).model_dump(mode="json")


def _backlog_payload() -> dict[str, object]:
    return {
        "source": "requested",
        "stream_id": "hba1c-arch",
        "due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "priority": "soon",
        "lab_bench": "Chem Bench 1",
        "assignment_group": "day-shift",
        "assigned_to": "postgres-test",
        "reference_material_label": "HbA1c control",
        "notes": "postgres api smoke",
        "requested_by": "migration-test",
    }


def _expected_posterior(prior: PriorConfig, records: Sequence[QCRecord]) -> tuple[float, float, float, float]:
    mu_n = prior.mu0
    kappa_n = prior.kappa0
    alpha_n = prior.alpha0
    beta_n = prior.beta0
    for record in records:
        next_kappa = kappa_n + 1
        next_mu = (kappa_n * mu_n + record.result_value) / next_kappa
        next_alpha = alpha_n + 0.5
        next_beta = beta_n + 0.5 * kappa_n * ((record.result_value - mu_n) ** 2) / next_kappa
        mu_n, kappa_n, alpha_n, beta_n = next_mu, next_kappa, next_alpha, next_beta
    return mu_n, kappa_n, alpha_n, beta_n


def test_alembic_upgrade_head_creates_current_schema(disposable_postgres_url: str) -> None:
    rehearsal.run_upgrade(disposable_postgres_url)

    engine = create_engine(disposable_postgres_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "alembic_version",
        "apikey",
        "auditentry",
        "ingestionreceipt",
        "posteriorstate",
        "qcbacklogitem",
        "qcrecord",
        "qcrecordquarantine",
        "streamconfig",
        "priorconfig",
    } <= tables

    qcrecord_indexes = inspector.get_indexes("qcrecord")
    assert _index_columns(qcrecord_indexes, "ix_qcrecord_stream_timestamp") == ["stream_id", "timestamp"]
    qcrecord_columns = {column["name"] for column in inspector.get_columns("qcrecord")}
    assert "qc_backlog_item_id" in qcrecord_columns
    assert _index_columns(qcrecord_indexes, "ix_qcrecord_qc_backlog_item_id") == ["qc_backlog_item_id"]

    posterior_indexes = inspector.get_indexes("posteriorstate")
    posterior_stream_index = next(
        index for index in posterior_indexes if index.get("name") == "ix_posteriorstate_stream_id"
    )
    assert bool(posterior_stream_index.get("unique")) is True

    receipt_indexes = inspector.get_indexes("ingestionreceipt")
    receipt_key_index = next(
        index for index in receipt_indexes if index.get("name") == "ix_ingestionreceipt_idempotency_key"
    )
    assert bool(receipt_key_index.get("unique")) is True

    alert_indexes = inspector.get_indexes("alertrecord")
    assert _index_columns(alert_indexes, "ix_alertrecord_stream_created") == ["stream_id", "created_at"]

    quarantine_indexes = inspector.get_indexes("qcrecordquarantine")
    assert _index_columns(quarantine_indexes, "ix_qcrecordquarantine_status_created") == ["status", "created_at"]
    backlog_indexes = inspector.get_indexes("qcbacklogitem")
    assert _index_columns(backlog_indexes, "ix_qcbacklogitem_status_due") == ["status", "due_at"]
    assert _index_columns(backlog_indexes, "ix_qcbacklogitem_assignee_due") == ["assigned_to", "due_at"]

    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260703_0002"


def test_rehearsal_revision_head_tracks_alembic_head() -> None:
    expected = ScriptDirectory.from_config(_alembic_config(app_db.DEFAULT_DB_URL)).get_current_head()
    assert rehearsal.revision_head() == expected == "20260703_0002"


def test_init_db_delegates_to_alembic(monkeypatch) -> None:
    calls: list[object] = []

    class DummyEngine:
        url = make_url("postgresql+psycopg://bayesianqc:bayesianqc@localhost/bayesianqc")

    monkeypatch.setattr(app_db, "get_engine", lambda: DummyEngine())
    monkeypatch.setattr(app_db, "run_alembic_migrations", lambda engine: calls.append(engine))

    app_db.init_db()

    assert len(calls) == 1
    assert isinstance(calls[0], DummyEngine)


def test_postgres_alembic_upgrade_creates_current_schema(disposable_postgres_url: str) -> None:
    rehearsal.run_upgrade(disposable_postgres_url)
    engine = create_engine(disposable_postgres_url)

    schema = rehearsal.schema_checks(engine)
    assert schema["alembic_version"] == rehearsal.revision_head()
    assert schema["qcrecord_stream_timestamp"] == ["stream_id", "timestamp"]
    assert schema["posteriorstate_stream_unique"] is True
    assert rehearsal.posterior_checks(engine)["ok"] is True
    engine.dispose()


def test_postgres_downgrade_to_previous_revision_and_reupgrade(disposable_postgres_url: str) -> None:
    rehearsal.run_upgrade(disposable_postgres_url)
    rehearsal.run_downgrade(disposable_postgres_url, "20260703_0001")
    engine = create_engine(disposable_postgres_url)
    inspector = inspect(engine)

    assert "qcbacklogitem" not in set(inspector.get_table_names())
    qcrecord_columns = {column["name"] for column in inspector.get_columns("qcrecord")}
    assert "qc_backlog_item_id" not in qcrecord_columns
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260703_0001"
    engine.dispose()

    rehearsal.run_upgrade(disposable_postgres_url)
    engine = create_engine(disposable_postgres_url)
    assert rehearsal.schema_checks(engine)["alembic_version"] == rehearsal.revision_head()
    engine.dispose()


def test_legacy_sqlite_import_copy_preserves_counts_sequences_and_posterior(
    tmp_path,
    disposable_postgres_url: str,
) -> None:
    sqlite_url = f"sqlite:///{tmp_path / 'sqlite-source.db'}"
    rehearsal.run_upgrade(sqlite_url)
    sqlite_engine = create_engine(sqlite_url)
    with Session(sqlite_engine) as session:
        seed_defaults(session)
        result = process_ingestion(_qc_payload(1), session, UserContext(Role.ADMIN, api_key_id=1), None)
        assert result.status == "accepted"

    target_engine = create_engine(disposable_postgres_url)
    rehearsal.run_upgrade(disposable_postgres_url)
    names = rehearsal.table_names()
    copied = rehearsal.copy_sqlite_rows(sqlite_engine, target_engine, truncate_target=True)
    source_counts = rehearsal.table_counts(sqlite_engine, names)
    target_counts = rehearsal.table_counts(target_engine, names)

    assert copied["qcrecord"] == 1
    assert rehearsal.count_comparison(source_counts, target_counts)["ok"] is True
    assert rehearsal.sequence_checks(target_engine, names)["status"] == "ok"
    posterior = rehearsal.posterior_checks(target_engine)
    assert posterior["ok"] is True
    assert posterior["streams_checked"] == 1

    sqlite_engine.dispose()
    target_engine.dispose()


def test_postgres_same_stream_concurrent_ingestion_matches_posterior_history(
    disposable_postgres_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BAYESIANQC_DB_URL", disposable_postgres_url)
    monkeypatch.setenv("BAYESIANQC_SEED_LOCAL_DEV_KEY", "1")
    app_db.get_engine().dispose()
    app_db.init_db()
    engine = app_db.get_engine()
    with Session(engine) as session:
        seed_defaults(session)

    def ingest(index: int) -> str:
        with Session(engine, expire_on_commit=False) as session:
            result = process_ingestion(_qc_payload(index), session, UserContext(Role.ADMIN, api_key_id=1), None)
            return result.status

    with ThreadPoolExecutor(max_workers=5) as executor:
        statuses = list(executor.map(ingest, range(1, 6)))

    assert statuses == ["accepted", "accepted", "accepted", "accepted", "accepted"]
    with Session(engine) as session:
        records = list(
            session.exec(
                select(QCRecord)
                .where(QCRecord.stream_id == "hba1c-arch", col(QCRecord.include_in_stats) == True)
                .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
            ).all()
        )
        prior = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).first()
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == "hba1c-arch")).first()
        assert prior is not None
        assert state is not None
        assert state.n_obs == len(records) == 5
        expected_mu, expected_kappa, expected_alpha, expected_beta = _expected_posterior(prior, records)
        assert state.mu_n == pytest.approx(expected_mu, abs=1e-12)
        assert state.kappa_n == pytest.approx(expected_kappa, abs=1e-12)
        assert state.alpha_n == pytest.approx(expected_alpha, abs=1e-12)
        assert state.beta_n == pytest.approx(expected_beta, abs=1e-12)

    engine.dispose()


def test_postgres_api_smoke_covers_core_operator_paths(disposable_postgres_url: str, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIANQC_DB_URL", disposable_postgres_url)
    monkeypatch.setenv("BAYESIANQC_SEED_LOCAL_DEV_KEY", "1")
    app_db.get_engine().dispose()

    with TestClient(app) as client:
        headers = {"X-API-Key": "local-dev-key"}
        me_response = client.get("/me", headers=headers)
        assert me_response.status_code == 200
        assert me_response.json()["role"] == "admin"

        backlog_response = client.post("/qc/backlog", json=_backlog_payload(), headers=headers)
        assert backlog_response.status_code == 200, backlog_response.text
        backlog_id = backlog_response.json()["id"]

        accepted_payload = _qc_payload_json(101)
        accepted_payload["qc_backlog_item_id"] = backlog_id
        accepted_response = client.post("/qc/records", json=accepted_payload, headers=headers)
        assert accepted_response.status_code == 200, accepted_response.text
        assert accepted_response.json()["status"] == "accepted"

        quarantine_payload = _qc_payload_json(102)
        quarantine_payload["units"] = "mmol/L"
        quarantine_response = client.post("/qc/records", json=quarantine_payload, headers=headers)
        assert quarantine_response.status_code == 202, quarantine_response.text
        assert quarantine_response.json()["status"] == "quarantined"

        chart_response = client.get("/streams/hba1c-arch/chart", headers=headers)
        assert chart_response.status_code == 200
        assert len(chart_response.json()["records"]) == 1

        backlog_list = client.get("/qc/backlog?status=completed", headers=headers)
        assert backlog_list.status_code == 200
        assert backlog_list.json()[0]["status"] == "completed"

        quarantine_list = client.get("/qc/quarantine", headers=headers)
        assert quarantine_list.status_code == 200
        assert len(quarantine_list.json()) == 1

        audit_response = client.get("/audit", headers=headers)
        assert audit_response.status_code == 200
        actions = [row["action"] for row in audit_response.json()]
        assert "ingest_qc" in actions
        assert "quarantine_qc" in actions

    app_db.get_engine().dispose()
