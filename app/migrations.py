from __future__ import annotations

from typing import Optional

from sqlalchemy.engine import Engine

SQLITE_SCHEMA_VERSION = 4
_DEFAULT_BUSY_TIMEOUT_MS = 5000


def _sqlite_user_version(cursor) -> int:
    cursor.execute("PRAGMA user_version")
    row = cursor.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def _sqlite_set_user_version(cursor, version: int) -> None:
    cursor.execute(f"PRAGMA user_version = {int(version)}")


def _sqlite_table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {str(row[1]) for row in cursor.fetchall()}


def _sqlite_add_column_if_missing(cursor, table_name: str, column_name: str, column_sql: str) -> None:
    columns = _sqlite_table_columns(cursor, table_name)
    if column_name in columns:
        return
    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _migrate_0_to_1(cursor) -> None:
    # QC record resolution/exclusion fields.
    _sqlite_add_column_if_missing(cursor, "qcrecord", "include_in_stats", "include_in_stats BOOLEAN DEFAULT 1")
    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_at", "resolved_at DATETIME")
    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_by", "resolved_by VARCHAR")
    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_reason", "resolved_reason VARCHAR")
    cursor.execute("UPDATE qcrecord SET include_in_stats = 1 WHERE include_in_stats IS NULL")


def _migrate_1_to_2(cursor) -> None:
    # PosteriorState metadata and streaks.
    _sqlite_add_column_if_missing(cursor, "posteriorstate", "prior_id", "prior_id INTEGER")
    _sqlite_add_column_if_missing(cursor, "posteriorstate", "config_id", "config_id INTEGER")
    _sqlite_add_column_if_missing(cursor, "posteriorstate", "warn_streak", "warn_streak INTEGER DEFAULT 0")
    _sqlite_add_column_if_missing(cursor, "posteriorstate", "hold_streak", "hold_streak INTEGER DEFAULT 0")
    cursor.execute("UPDATE posteriorstate SET warn_streak = 0 WHERE warn_streak IS NULL")
    cursor.execute("UPDATE posteriorstate SET hold_streak = 0 WHERE hold_streak IS NULL")


def _migrate_2_to_3(cursor) -> None:
    # StreamConfig Bayesian policy fields.
    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_warn_prob_threshold", "bayes_warn_prob_threshold FLOAT")
    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_warn_consecutive", "bayes_warn_consecutive INTEGER")
    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_hold_prob_threshold", "bayes_hold_prob_threshold FLOAT")
    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_hold_consecutive", "bayes_hold_consecutive INTEGER")
    # Intentionally do not backfill defaults here; leaving NULL makes misconfiguration visible,
    # and the app already has backwards-compatible fallbacks.


def _migrate_3_to_4(cursor) -> None:
    # Persisted per-record evaluations for read-mostly charts.
    _sqlite_add_column_if_missing(cursor, "qcrecord", "signals", "signals JSON")
    _sqlite_add_column_if_missing(cursor, "qcrecord", "bayesian_risk", "bayesian_risk JSON")
    _sqlite_add_column_if_missing(cursor, "qcrecord", "disposition", "disposition VARCHAR")


def run_sqlite_migrations(engine: Engine, *, target_version: Optional[int] = None) -> None:
    if not str(engine.url).startswith("sqlite"):
        return

    desired_version = SQLITE_SCHEMA_VERSION if target_version is None else int(target_version)
    if desired_version < 0:
        raise ValueError("target_version must be >= 0")

    connection = engine.raw_connection()
    cursor = connection.cursor()
    try:
        # Allow migrations to wait briefly if another process is touching the DB at startup.
        cursor.execute(f"PRAGMA busy_timeout = {_DEFAULT_BUSY_TIMEOUT_MS}")
        while True:
            # SQLite doesn't support row-level locks; take a write lock for schema changes.
            cursor.execute("BEGIN IMMEDIATE")
            try:
                current = _sqlite_user_version(cursor)
                if current >= desired_version:
                    connection.commit()
                    return

                next_version = current + 1
                if current == 0:
                    _migrate_0_to_1(cursor)
                elif current == 1:
                    _migrate_1_to_2(cursor)
                elif current == 2:
                    _migrate_2_to_3(cursor)
                elif current == 3:
                    _migrate_3_to_4(cursor)
                else:
                    raise RuntimeError(f"Unknown sqlite schema version {current}")

                _sqlite_set_user_version(cursor, next_version)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        cursor.close()
        connection.close()
