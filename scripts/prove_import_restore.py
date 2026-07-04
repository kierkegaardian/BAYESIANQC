#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlmodel import Session

from app.services.import_restore_checks import build_restore_summary
from app.services.import_settings import import_settings


DISPOSABLE_MARKERS = ("disposable", "rehearsal", "test", "restore_proof", "restore-proof")
DEFAULT_SOURCE_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"


def _url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Restore proof requires a Postgres SQLAlchemy URL")
    return url


def _database_name(url: URL) -> str:
    if not url.database:
        raise RuntimeError("Postgres URL must include a database name")
    return url.database


def _quote_identifier(name: str) -> str:
    if "\x00" in name or '"' in name:
        raise RuntimeError("Unsafe database name")
    return f'"{name}"'


def _require_disposable_database(url: URL) -> None:
    database = _database_name(url).lower()
    if any(marker in database for marker in DISPOSABLE_MARKERS):
        return
    raise RuntimeError(
        "Restore proof target database must look disposable: include one of "
        f"{', '.join(DISPOSABLE_MARKERS)} in the database name."
    )


def _default_restore_url(source_url: URL) -> URL:
    source_database = _database_name(source_url)
    return source_url.set(database=f"{source_database}_restore_proof_{os.getpid()}")


def _maintenance_url(url: URL) -> str:
    return url.set(database="postgres").render_as_string(hide_password=False)


def _cli_connection(url: URL) -> tuple[list[str], dict[str, str]]:
    args: list[str] = []
    if url.host:
        args.extend(["-h", url.host])
    if url.port:
        args.extend(["-p", str(url.port)])
    if url.username:
        args.extend(["-U", url.username])
    args.extend(["-d", _database_name(url)])
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return args, env


def _run_postgres_tool(
    command: list[str],
    env: dict[str, str],
    stdout_path: Path | None = None,
    *,
    discard_stdout: bool = False,
) -> None:
    if stdout_path is None:
        subprocess.run(command, env=env, check=True, stdout=subprocess.DEVNULL if discard_stdout else None)
        return
    with stdout_path.open("wb") as handle:
        subprocess.run(command, env=env, check=True, stdout=handle)


def _remove_unsupported_dump_settings(path: Path) -> None:
    filtered_path = path.with_name(f"{path.name}.filtered")
    try:
        with path.open("r", encoding="utf-8") as source, filtered_path.open("w", encoding="utf-8") as target:
            for line in source:
                if not line.startswith("SET transaction_timeout"):
                    target.write(line)
        filtered_path.replace(path)
    finally:
        filtered_path.unlink(missing_ok=True)


def _recreate_restore_database(url: URL) -> None:
    _require_disposable_database(url)
    database = _quote_identifier(_database_name(url))
    engine = create_engine(_maintenance_url(url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": _database_name(url)},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {database}"))
            connection.execute(text(f"CREATE DATABASE {database}"))
    finally:
        engine.dispose()


def _drop_restore_database(url: URL) -> None:
    _require_disposable_database(url)
    database = _quote_identifier(_database_name(url))
    engine = create_engine(_maintenance_url(url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": _database_name(url)},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {database}"))
    finally:
        engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove BAYESIANQC import DB plus archive restore integrity")
    parser.add_argument("--source-url", default=os.getenv("BAYESIANQC_DB_URL", DEFAULT_SOURCE_URL))
    parser.add_argument("--restore-url", default=None, help="Disposable restore DB URL; generated when omitted")
    parser.add_argument("--archive-root", default=None, help="Mounted archive root to verify")
    parser.add_argument("--db-archive-root", default=None, help="Archive root prefix stored in the restored DB")
    parser.add_argument("--keep-restore-db", action="store_true", help="Leave the disposable restore database in place")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_url = _url(args.source_url)
    restore_url = _url(args.restore_url) if args.restore_url else _default_restore_url(source_url)
    _require_disposable_database(restore_url)
    archive_root = Path(args.archive_root).expanduser() if args.archive_root else import_settings().archive_root
    db_archive_root = Path(args.db_archive_root).expanduser() if args.db_archive_root else archive_root
    if not archive_root.exists():
        raise RuntimeError(f"Archive root does not exist: {archive_root}")

    with tempfile.TemporaryDirectory(prefix="bayesianqc-import-restore-") as tmp:
        tmp_path = Path(tmp)
        dump_path = tmp_path / "source.sql"
        source_args, source_env = _cli_connection(source_url)
        restore_args, restore_env = _cli_connection(restore_url)
        _recreate_restore_database(restore_url)
        try:
            _run_postgres_tool(["pg_dump", "--no-owner", "--no-privileges", *source_args], source_env, dump_path)
            _remove_unsupported_dump_settings(dump_path)
            _run_postgres_tool(
                ["psql", "--quiet", "--set", "ON_ERROR_STOP=1", *restore_args, "-f", str(dump_path)],
                restore_env,
                discard_stdout=True,
            )
            engine = create_engine(restore_url.render_as_string(hide_password=False))
            try:
                with Session(engine) as session:
                    proof: dict[str, Any] = build_restore_summary(session, db_archive_root, archive_root)
            finally:
                engine.dispose()
            summary = {
                "ok": proof["ok"],
                "source_database": _database_name(source_url),
                "restore_database": _database_name(restore_url),
                "db_archive_root": str(db_archive_root),
                "archive_root": str(archive_root),
                "proof": proof,
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            if not proof["ok"]:
                raise SystemExit(1)
        finally:
            if not args.keep_restore_db:
                _drop_restore_database(restore_url)


if __name__ == "__main__":
    main()
