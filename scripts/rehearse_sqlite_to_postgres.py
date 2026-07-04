from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, col, select

import app.db_models  # noqa: F401
from app.bayesian import _update_posterior
from app.db_models import PosteriorState, PriorConfig, QCRecord
from app.timeutils import as_utc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSTGRES_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"
_POSTERIOR_TOLERANCE = 1e-9
_DISPOSABLE_TARGET_MARKERS = ("disposable", "rehearsal", "test")


def _alembic_config(db_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def revision_head() -> str:
    head = ScriptDirectory.from_config(_alembic_config(DEFAULT_POSTGRES_URL)).get_current_head()
    if head is None:
        raise RuntimeError("Alembic migration head is not available")
    return head


@contextmanager
def _migration_url(db_url: str):
    previous = os.environ.get("BAYESIANQC_MIGRATION_DB_URL")
    os.environ["BAYESIANQC_MIGRATION_DB_URL"] = db_url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("BAYESIANQC_MIGRATION_DB_URL", None)
        else:
            os.environ["BAYESIANQC_MIGRATION_DB_URL"] = previous


def run_upgrade(db_url: str) -> None:
    with _migration_url(db_url):
        command.upgrade(_alembic_config(db_url), "head")


def run_downgrade(db_url: str, revision: str) -> None:
    with _migration_url(db_url):
        command.downgrade(_alembic_config(db_url), revision)


def table_names() -> list[str]:
    return [table.name for table in SQLModel.metadata.sorted_tables]


def table_counts(engine: Engine, names: Sequence[str]) -> dict[str, int]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for name in names:
            if name not in existing:
                counts[name] = -1
                continue
            counts[name] = int(connection.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one())
    return counts


def _target_has_data(engine: Engine, names: Sequence[str]) -> bool:
    return any(count > 0 for count in table_counts(engine, names).values())


def _reset_postgres_sequences(engine: Engine, names: Sequence[str]) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        for name in names:
            table = SQLModel.metadata.tables[name]
            if "id" not in table.c:
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": name},
            ).scalar_one_or_none()
            if sequence_name is None:
                continue
            connection.execute(
                text(
                    f"""
                    SELECT setval(
                        CAST(:sequence_name AS regclass),
                        COALESCE((SELECT MAX(id) FROM "{name}"), 0) + 1,
                        false
                    )
                    """
                ),
                {"sequence_name": sequence_name},
            )


def sequence_checks(engine: Engine, names: Sequence[str]) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        return {"status": "skipped", "reason": "not_postgres"}

    checks: dict[str, Any] = {"status": "ok", "tables": {}, "mismatches": []}
    with engine.connect() as connection:
        for name in names:
            table = SQLModel.metadata.tables[name]
            if "id" not in table.c:
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": name},
            ).scalar_one_or_none()
            if sequence_name is None:
                continue
            max_id = int(connection.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{name}"')).scalar_one())
            sequence_row = connection.execute(text(f"SELECT last_value, is_called FROM {sequence_name}")).one()
            expected_next = max_id + 1 if max_id > 0 else 1
            actual_last = int(sequence_row.last_value)
            is_called = bool(sequence_row.is_called)
            actual_next = actual_last + 1 if is_called else actual_last
            ok = actual_next == expected_next
            checks["tables"][name] = {
                "max_id": max_id,
                "expected_next": expected_next,
                "last_value": actual_last,
                "actual_next": actual_next,
                "is_called": is_called,
                "ok": ok,
            }
            if not ok:
                checks["mismatches"].append(name)
    if checks["mismatches"]:
        checks["status"] = "mismatch"
    return checks


def copy_sqlite_rows(source: Engine, target: Engine, *, truncate_target: bool) -> dict[str, int]:
    names = table_names()
    if _target_has_data(target, names) and not truncate_target:
        raise RuntimeError("Target database is not empty; pass --truncate-target for a destructive rehearsal reset")

    tables = list(SQLModel.metadata.sorted_tables)
    copied: dict[str, int] = {}
    with source.connect() as source_connection, target.begin() as target_connection:
        if truncate_target:
            for table in reversed(tables):
                target_connection.execute(table.delete())
        for table in tables:
            rows = [dict(row) for row in source_connection.execute(table.select()).mappings().all()]
            if rows:
                target_connection.execute(table.insert(), rows)
            copied[table.name] = len(rows)
    _reset_postgres_sequences(target, names)
    return copied


def count_comparison(source_counts: dict[str, int], target_counts: dict[str, int]) -> dict[str, Any]:
    mismatches = {
        name: {"source": source_counts.get(name), "target": target_counts.get(name)}
        for name in sorted(source_counts)
        if source_counts.get(name) != target_counts.get(name)
    }
    return {"ok": not mismatches, "mismatches": mismatches}


def _expected_posterior(records: Sequence[QCRecord], priors: Sequence[PriorConfig]) -> dict[str, Any] | None:
    if not records or not priors:
        return None

    prior_idx = 0
    first_ts = as_utc(records[0].timestamp)
    while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= first_ts:
        prior_idx += 1
    current_prior = priors[prior_idx]
    mu_n, kappa_n, alpha_n, beta_n = current_prior.mu0, current_prior.kappa0, current_prior.alpha0, current_prior.beta0
    n_obs = 0

    for record in records:
        record_ts = as_utc(record.timestamp)
        while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
            prior_idx += 1
        record_prior = priors[prior_idx]
        if record_prior.id != current_prior.id:
            current_prior = record_prior
            mu_n, kappa_n, alpha_n, beta_n = (
                current_prior.mu0,
                current_prior.kappa0,
                current_prior.alpha0,
                current_prior.beta0,
            )
            n_obs = 0
        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(mu_n, kappa_n, alpha_n, beta_n, record.result_value)
        n_obs += 1

    return {
        "mu_n": mu_n,
        "kappa_n": kappa_n,
        "alpha_n": alpha_n,
        "beta_n": beta_n,
        "n_obs": n_obs,
        "prior_id": current_prior.id,
    }


def _posterior_mismatch(state: PosteriorState, expected: dict[str, Any]) -> dict[str, Any] | None:
    mismatched: dict[str, Any] = {}
    for field in ("mu_n", "kappa_n", "alpha_n", "beta_n"):
        actual_value = float(getattr(state, field))
        expected_value = float(expected[field])
        if not math.isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=_POSTERIOR_TOLERANCE):
            mismatched[field] = {"actual": actual_value, "expected": expected_value}
    for field in ("n_obs", "prior_id"):
        actual_value = getattr(state, field)
        expected_value = expected[field]
        if actual_value != expected_value:
            mismatched[field] = {"actual": actual_value, "expected": expected_value}
    return mismatched or None


def posterior_checks(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    if not {"posteriorstate", "qcrecord", "priorconfig"} <= set(inspector.get_table_names()):
        return {"ok": False, "reason": "missing_posterior_record_or_prior_table", "mismatches": []}

    with Session(engine) as session:
        record_counts = dict(
            session.exec(
                select(QCRecord.stream_id, func.count())
                .where(col(QCRecord.include_in_stats) == True)
                .group_by(QCRecord.stream_id)
            ).all()
        )
        records_by_stream: dict[str, list[QCRecord]] = {}
        records = session.exec(
            select(QCRecord)
            .where(col(QCRecord.include_in_stats) == True)
            .order_by(col(QCRecord.stream_id).asc(), col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
        ).all()
        for record in records:
            records_by_stream.setdefault(record.stream_id, []).append(record)
        states = {
            state.stream_id: state
            for state in session.exec(select(PosteriorState).order_by(PosteriorState.stream_id)).all()
        }
        priors_by_stream = {
            stream_id: list(
                session.exec(
                    select(PriorConfig)
                    .where(PriorConfig.stream_id == stream_id)
                    .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
                ).all()
            )
            for stream_id in records_by_stream
        }

    mismatches: list[dict[str, Any]] = []
    for stream_id, count in sorted(record_counts.items()):
        stream_id = str(stream_id)
        count = int(count)
        state = states.get(stream_id)
        if state is None:
            mismatches.append({"stream_id": stream_id, "record_count": count, "state_n_obs": None})
            continue
        expected = _expected_posterior(records_by_stream.get(stream_id, []), priors_by_stream.get(stream_id, []))
        if expected is None:
            mismatches.append({"stream_id": stream_id, "reason": "missing_records_or_priors"})
            continue
        mismatch = _posterior_mismatch(state, expected)
        if mismatch:
            mismatches.append({"stream_id": stream_id, "fields": mismatch})

    return {
        "ok": not mismatches,
        "streams_checked": len(records_by_stream),
        "posterior_state_rows": len(states),
        "tolerance": _POSTERIOR_TOLERANCE,
        "mismatches": mismatches,
    }


def schema_checks(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    qcrecord_indexes = {index["name"]: index.get("column_names") for index in inspector.get_indexes("qcrecord")}
    posterior_indexes = {index["name"]: bool(index.get("unique")) for index in inspector.get_indexes("posteriorstate")}
    receipt_indexes = {index["name"]: bool(index.get("unique")) for index in inspector.get_indexes("ingestionreceipt")}
    alert_indexes = {index["name"]: index.get("column_names") for index in inspector.get_indexes("alertrecord")}
    comment_indexes = {index["name"]: index.get("column_names") for index in inspector.get_indexes("qccomment")}
    kiosk_indexes = {index["name"]: index.get("column_names") for index in inspector.get_indexes("kioskpanel")}
    instrument_columns = {column["name"] for column in inspector.get_columns("instrument")}
    stream_columns = {column["name"] for column in inspector.get_columns("streamconfig")}
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    return {
        "alembic_version": version,
        "qcrecord_stream_timestamp": qcrecord_indexes.get("ix_qcrecord_stream_timestamp"),
        "posteriorstate_stream_unique": posterior_indexes.get("ix_posteriorstate_stream_id"),
        "ingestionreceipt_key_unique": receipt_indexes.get("ix_ingestionreceipt_idempotency_key"),
        "alertrecord_stream_created": alert_indexes.get("ix_alertrecord_stream_created"),
        "qccomment_target_created": comment_indexes.get("ix_qccomment_target_created"),
        "instrument_lab_bench": "lab_bench" in instrument_columns,
        "streamconfig_lab_bench": "lab_bench" in stream_columns,
        "streamconfig_control_material_id": "control_material_id" in stream_columns,
        "kioskpanel_kiosk_order": kiosk_indexes.get("ix_kioskpanel_kiosk_order"),
    }


def _postgres_url_from_env() -> str | None:
    for name in ("BAYESIANQC_POSTGRES_TEST_URL", "BAYESIANQC_DB_URL"):
        value = os.environ.get(name)
        if value and value.startswith("postgresql"):
            return value
    return None


def _require_disposable_copy_target(postgres_url: str) -> None:
    lowered = postgres_url.lower()
    if any(marker in lowered for marker in _DISPOSABLE_TARGET_MARKERS):
        return
    raise RuntimeError(
        "Legacy SQLite copy rehearsal requires a disposable Postgres target URL. "
        "Include one of these markers in the database name or URL: "
        f"{', '.join(_DISPOSABLE_TARGET_MARKERS)}."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rehearse BAYESIANQC Postgres upgrade and optional legacy import copy")
    parser.add_argument("--sqlite-db", default="bayesianqc.db", help="Legacy SQLite source DB path for count/copy rehearsal")
    parser.add_argument("--postgres-url", default=None, help="Target Postgres SQLAlchemy URL")
    parser.add_argument("--copy-data", action="store_true", help="Copy source SQLite rows into the Postgres target")
    parser.add_argument("--truncate-target", action="store_true", help="Delete target rows before copying")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = table_names()
    summary: dict[str, Any] = {"revision_head": revision_head()}

    sqlite_path = Path(args.sqlite_db)
    summary["sqlite_source"] = {"path": str(sqlite_path), "exists": sqlite_path.exists()}
    if sqlite_path.exists():
        sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
        summary["sqlite_source"]["counts"] = table_counts(sqlite_engine, names)
    else:
        sqlite_engine = None

    postgres_url = args.postgres_url or _postgres_url_from_env()
    if postgres_url is None:
        summary["postgres_rehearsal"] = {"status": "skipped", "reason": "no Postgres URL supplied"}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if args.copy_data:
        _require_disposable_copy_target(postgres_url)

    target_engine = create_engine(postgres_url)
    run_upgrade(postgres_url)
    postgres_summary: dict[str, Any] = {"schema": schema_checks(target_engine)}
    if args.copy_data:
        if sqlite_engine is None:
            raise RuntimeError(f"SQLite source does not exist: {sqlite_path}")
        postgres_summary["copied"] = copy_sqlite_rows(
            sqlite_engine,
            target_engine,
            truncate_target=args.truncate_target,
        )
        postgres_summary["copy_status"] = "copied"
        postgres_summary["target_counts"] = table_counts(target_engine, names)
        postgres_summary["count_comparison"] = count_comparison(
            summary["sqlite_source"]["counts"],
            postgres_summary["target_counts"],
        )
    else:
        postgres_summary["copy_status"] = "not_requested"
        postgres_summary["target_counts"] = table_counts(target_engine, names)
    postgres_summary["sequence_checks"] = sequence_checks(target_engine, names)
    postgres_summary["posterior_checks"] = posterior_checks(target_engine)
    summary["postgres_rehearsal"] = postgres_summary
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
