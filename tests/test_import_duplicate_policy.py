from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, select

from app.db import get_engine
from app.db_models import QCRecord
from app.main import app

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture(autouse=True)
def import_archive_root(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path / "import-archive"))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.anyio
async def test_import_marks_possible_duplicate_for_review_and_continues_batch(client: httpx.AsyncClient) -> None:
    profile = await client.post(
        "/qc/import-profiles",
        json={
            "name": "duplicate policy CSV",
            "profile_type": "delimited_direct",
            "status": "active",
            "file_extensions": [".csv"],
            "filename_patterns": ["*.csv"],
            "config": {
                "delimiter": ",",
                "run_context_policy": "allow_provisional",
                "columns": {
                    "timestamp": "Timestamp",
                    "result_value": "Result",
                    "analyte": "Analyte",
                    "qc_level": "Level",
                    "instrument_id": "Instrument",
                    "method_id": "Method",
                    "control_material_lot": "Lot",
                    "units": "Units",
                },
                "defaults": {"stream_id": "hba1c-arch"},
            },
        },
        headers=AUTH_HEADERS,
    )
    assert profile.status_code == 200, profile.text
    first_time = datetime.now(timezone.utc) + timedelta(seconds=1)
    second_time = first_time + timedelta(seconds=1)
    header = "Timestamp,Result,Analyte,Level,Instrument,Method,Lot,Units\n"
    rows = [
        f"{first_time.isoformat()},5.2,HbA1c,Level 1,Architect,HPLC,LOT-001,%\n",
        f"{first_time.isoformat()},5.3,HbA1c,Level 1,Architect,HPLC,LOT-001,%\n",
        f"{second_time.isoformat()},5.4,HbA1c,Level 1,Architect,HPLC,LOT-001,%\n",
    ]
    upload = await client.post(
        "/qc/imports",
        files={"file": ("duplicates.csv", (header + "".join(rows)).encode(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["id"]

    applied = await client.post(f"/qc/imports/{batch_id}/apply", headers=AUTH_HEADERS)

    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["status"] == "partially_applied"
    statuses = [row["status"] for row in body["rows"]]
    assert statuses.count("applied") == 2
    assert statuses.count("needs_review") == 1
    conflict = next(row for row in body["rows"] if row["status"] == "needs_review")
    assert "possible_duplicate_requires_review" in conflict["errors"]
    with Session(get_engine()) as session:
        records = session.exec(select(QCRecord).where(QCRecord.stream_id == "hba1c-arch")).all()
        assert len(records) == 2
