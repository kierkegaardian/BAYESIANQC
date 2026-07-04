from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.main import app

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_profile(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/qc/import-profiles",
        json={
            "name": "Large parse CSV",
            "profile_type": "delimited_direct",
            "status": "active",
            "file_extensions": [".csv"],
            "filename_patterns": ["*.csv"],
            "config": {
                "delimiter": ",",
                "columns": {
                    "timestamp": "Acquired At",
                    "result_value": "Result",
                    "analyte": "Analyte",
                    "qc_level": "Level",
                    "instrument_id": "Instrument",
                    "method_id": "Method",
                    "control_material_lot": "Lot",
                    "units": "Units",
                    "run_id": "Run ID",
                },
                "defaults": {"stream_id": "hba1c-arch"},
            },
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_large_parse_result_returns_without_queue_deadlock(client: httpx.AsyncClient) -> None:
    await _create_profile(client)
    header = "Injection Type,Run ID,Acquired At,Analyte,Result,Level,Instrument,Method,Lot,Units,Sample Name\n"
    rows = [
        f"CheckStandard,QUEUE-{index},2026-07-04T09:{index % 60:02d}:00+00:00,HbA1c,5.2,Level 1,Architect,HPLC,LOT-001,%,QC {index}\n"
        for index in range(600)
    ]
    upload = await client.post(
        "/qc/imports",
        files={"file": ("large-queue.csv", (header + "".join(rows)).encode(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["batch"]["ready_rows"] == 600
