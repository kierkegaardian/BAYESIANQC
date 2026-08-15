from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from scripts import rehearse_sqlite_to_postgres as rehearsal


@pytest.fixture
def database_url() -> Iterator[str]:
    value = os.getenv("BAYESIANQC_POSTGRES_TEST_URL")
    if not value or not value.startswith("postgresql"):
        pytest.skip("Postgres is required for migration tests")
    base = make_url(value)
    name = f"bayesianqc_eval_migration_{os.getpid()}_{uuid4().hex[:8]}"
    maintenance = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with maintenance.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        maintenance.dispose()


def upgrade(url: str, revision: str) -> None:
    with rehearsal._migration_url(url):
        command.upgrade(rehearsal._alembic_config(url), revision)


def insert_stream(
    connection,
    *,
    stream_id: str,
    baseline_start: datetime | None,
    baseline_end: datetime | None,
) -> None:
    now = datetime.now(timezone.utc)
    connection.execute(
        text(
            "INSERT INTO streamconfig ("
            "stream_id, version, effective_from, created_at, created_by, analyte, method, "
            "instrument, qc_level, control_material_lot, units, target_value, sigma, "
            "action_limit_sd, warning_limit_sd, baseline_start, baseline_end, "
            "risk_threshold_warn, risk_threshold_hold, rule_set"
            ") VALUES ("
            ":stream_id, 1, :effective_from, :created_at, 'legacy', 'A', 'M', 'I', "
            "'L1', 'LOT', 'u', 10, 1, 3, 2, :baseline_start, :baseline_end, 50, 80, "
            "CAST('{\"rules\": []}' AS JSON))"
        ),
        {
            "stream_id": stream_id,
            "effective_from": now,
            "created_at": now,
            "baseline_start": baseline_start,
            "baseline_end": baseline_end,
        },
    )


def insert_baseline_records(connection, *, stream_id: str, timestamp: datetime) -> None:
    for index, value in enumerate((9.0, 11.0), start=1):
        connection.execute(
            text(
                "INSERT INTO qcrecord ("
                "stream_id, timestamp, result_value, analyte, qc_level, instrument_id, method_id, "
                "control_material_lot, units, entry_source, include_in_stats, raw_payload, "
                "duplicate_status, created_at, idempotency_key"
                ") VALUES ("
                ":stream_id, :timestamp, :value, 'A', 'L1', 'I', 'M', 'LOT', 'u', "
                "'MANUAL', true, CAST('{}' AS JSON), 'UNIQUE', :timestamp, :key)"
            ),
            {
                "stream_id": stream_id,
                "timestamp": timestamp,
                "value": value,
                "key": f"legacy-baseline-{index}",
            },
        )


def prepare_legacy_schema(url: str) -> None:
    upgrade(url, "20260704_0006")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE streamconfig DROP COLUMN IF EXISTS control_limit_source"))
        connection.execute(text("ALTER TABLE qcrecord DROP COLUMN IF EXISTS current_evaluation_id"))
        connection.execute(text("ALTER TABLE alertrecord DROP COLUMN IF EXISTS source_evaluation_id"))
    engine.dispose()


def test_legacy_baseline_backfill_and_null_provenance_columns(database_url: str) -> None:
    prepare_legacy_schema(database_url)
    engine = create_engine(database_url)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        insert_stream(connection, stream_id="configured", baseline_start=None, baseline_end=None)
        insert_stream(
            connection,
            stream_id="baseline",
            baseline_start=now,
            baseline_end=now,
        )
        insert_baseline_records(connection, stream_id="baseline", timestamp=now)
    upgrade(database_url, "head")
    with engine.connect() as connection:
        sources = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                text("SELECT stream_id, control_limit_source FROM streamconfig")
            ).all()
        }
        assert sources == {"configured": "configured", "baseline": "fixed_baseline"}
        frozen = connection.execute(
            text(
                "SELECT baseline_centerline, baseline_sigma, baseline_count "
                "FROM streamconfig WHERE stream_id = 'baseline'"
            )
        ).one()
        assert frozen[0] == pytest.approx(10.0)
        assert frozen[1] == pytest.approx(2**0.5)
        assert frozen[2] == 2
    inspector = inspect(engine)
    qc_column = next(
        column for column in inspector.get_columns("qcrecord") if column["name"] == "current_evaluation_id"
    )
    alert_column = next(
        column for column in inspector.get_columns("alertrecord") if column["name"] == "source_evaluation_id"
    )
    assert qc_column["nullable"] is True
    assert alert_column["nullable"] is True
    engine.dispose()


def test_partial_legacy_baseline_aborts_migration(database_url: str) -> None:
    prepare_legacy_schema(database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        insert_stream(
            connection,
            stream_id="partial",
            baseline_start=datetime.now(timezone.utc),
            baseline_end=None,
        )
    with pytest.raises(RuntimeError, match="partial legacy baseline"):
        upgrade(database_url, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260704_0006"
    engine.dispose()
