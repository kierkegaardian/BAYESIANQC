from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from scripts import rehearse_sqlite_to_postgres as rehearsal

ROOT = Path(__file__).resolve().parents[1]


def _base_url() -> str:
    value = os.getenv("BAYESIANQC_POSTGRES_TEST_URL")
    if not value or not value.startswith("postgresql"):
        pytest.skip("BAYESIANQC_POSTGRES_TEST_URL is required")
    return value


@pytest.fixture()
def workflow_migration_url() -> Iterator[str]:
    base = make_url(_base_url())
    name = f"bayesianqc_workflow_test_{uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = base.set(database=name).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield target
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _prepare_pre_scope_schema(db_url: str) -> None:
    """Create current metadata, then use the migration's downgrade as the v0008 fixture."""
    rehearsal.run_upgrade(db_url)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    with rehearsal._migration_url(db_url):
        command.downgrade(config, "20260709_0008")


def _insert_alert(connection, alert_id: str, stream_id: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO alertrecord (
                alert_id, stream_id, created_at, status, severity, disposition,
                signals, bayesian_risk
            ) VALUES (
                :alert_id, :stream_id, CURRENT_TIMESTAMP, 'OPEN', 'high', 'reject',
                CAST('[]' AS JSON), CAST('{}' AS JSON)
            ) RETURNING id
            """
        ),
        {"alert_id": alert_id, "stream_id": stream_id},
    ).scalar_one()


def _insert_investigation(connection, label: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO investigation (
                status, problem_statement, created_at, updated_at, created_by
            ) VALUES ('OPEN', :label, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'migration-test')
            RETURNING id
            """
        ),
        {"label": label},
    ).scalar_one()


def test_workflow_scope_migration_backfills_populated_links(workflow_migration_url: str) -> None:
    _prepare_pre_scope_schema(workflow_migration_url)
    engine = create_engine(workflow_migration_url)
    with engine.begin() as connection:
        alert_id = _insert_alert(connection, "backfill-alert", "stream-a")
        investigation_id = _insert_investigation(connection, "backfill investigation")
        connection.execute(
            text(
                "INSERT INTO investigationalertlink (investigation_id, alert_id) "
                "VALUES (:investigation_id, :alert_id)"
            ),
            {"investigation_id": investigation_id, "alert_id": alert_id},
        )
        capa_id = connection.execute(
            text(
                """
                INSERT INTO capa (status, created_at, updated_at, created_by)
                VALUES ('DRAFT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'migration-test')
                RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO capalink (capa_id, alert_id, investigation_id) "
                "VALUES (:capa_id, :alert_id, :investigation_id)"
            ),
            {"capa_id": capa_id, "alert_id": alert_id, "investigation_id": investigation_id},
        )
    engine.dispose()

    rehearsal.run_upgrade(workflow_migration_url)
    engine = create_engine(workflow_migration_url)
    with engine.connect() as connection:
        investigation_stream = connection.execute(
            text("SELECT stream_id FROM investigation WHERE id = :id"), {"id": investigation_id}
        ).scalar_one()
        capa_stream = connection.execute(
            text("SELECT stream_id FROM capa WHERE id = :id"), {"id": capa_id}
        ).scalar_one()
    inspector = inspect(engine)
    assert investigation_stream == capa_stream == "stream-a"
    assert any(
        constraint.get("column_names") == ["investigation_id", "alert_id"]
        for constraint in inspector.get_unique_constraints("investigationalertlink")
    )
    assert any(
        constraint.get("column_names") == ["capa_id"]
        for constraint in inspector.get_unique_constraints("capalink")
    )
    engine.dispose()


def test_workflow_scope_migration_aborts_conflicting_links(workflow_migration_url: str) -> None:
    _prepare_pre_scope_schema(workflow_migration_url)
    engine = create_engine(workflow_migration_url)
    with engine.begin() as connection:
        first_alert = _insert_alert(connection, "conflict-a", "stream-a")
        second_alert = _insert_alert(connection, "conflict-b", "stream-b")
        investigation_id = _insert_investigation(connection, "conflicting investigation")
        connection.execute(
            text(
                "INSERT INTO investigationalertlink (investigation_id, alert_id) "
                "VALUES (:investigation_id, :first_alert), (:investigation_id, :second_alert)"
            ),
            {
                "investigation_id": investigation_id,
                "first_alert": first_alert,
                "second_alert": second_alert,
            },
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="multiple streams"):
        rehearsal.run_upgrade(workflow_migration_url)

    engine = create_engine(workflow_migration_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260709_0008"
    assert "stream_id" not in {column["name"] for column in inspect(engine).get_columns("investigation")}
    engine.dispose()
