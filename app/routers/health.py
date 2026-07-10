from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlmodel import Session

from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _archive_ready() -> tuple[bool, str | None]:
    raw_root = os.getenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", "").strip()
    required = os.getenv("BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not raw_root:
        return (not required, "import archive root is required" if required else None)
    root = Path(raw_root).expanduser()
    if not root.is_dir():
        return False, "import archive root does not exist"
    if not os.access(root, os.W_OK):
        return False, "import archive root is not writable"
    return True, None


@lru_cache(maxsize=1)
def _expected_migration_head() -> str:
    config = Config(os.getenv("BAYESIANQC_ALEMBIC_CONFIG", "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Alembic migration head is unavailable")
    return head


@router.get("/readyz")
def readyz(session: Session = Depends(get_session)) -> JSONResponse:
    failures: list[str] = []
    try:
        connection = session.connection()
        connection.execute(text("SELECT 1")).one()
        migration = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if migration != _expected_migration_head():
            failures.append("database migration is not at the release head")
    except Exception:
        failures.append("database is unavailable")

    archive_ok, archive_failure = _archive_ready()
    if not archive_ok and archive_failure:
        failures.append(archive_failure)

    status_code = 200 if not failures else 503
    payload: dict[str, object] = {"status": "ready" if not failures else "not_ready"}
    if failures:
        payload["failures"] = failures
    return JSONResponse(status_code=status_code, content=payload)
