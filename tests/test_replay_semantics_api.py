from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.main import app

AUTH = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def payload(timestamp: datetime, run_id: str) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": 5.8,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "control_material_lot": "LOT-001",
        "units": "%",
        "entry_source": "manual",
        "run_id": run_id,
    }


@pytest.mark.anyio
async def test_same_timestamp_records_do_not_observe_each_other_but_next_timestamp_does(
    client: httpx.AsyncClient,
) -> None:
    timestamp = datetime.now(timezone.utc) + timedelta(seconds=1)
    first = await client.post("/qc/records", json=payload(timestamp, "same-1"), headers=AUTH)
    second = await client.post("/qc/records", json=payload(timestamp, "same-2"), headers=AUTH)
    third = await client.post(
        "/qc/records",
        json=payload(timestamp + timedelta(seconds=1), "next"),
        headers=AUTH,
    )
    assert first.status_code == second.status_code == third.status_code == 200
    assert "2-2s" not in [signal["rule"] for signal in first.json()["qc"]["signals"]]
    assert "2-2s" not in [signal["rule"] for signal in second.json()["qc"]["signals"]]
    assert "2-2s" in [signal["rule"] for signal in third.json()["qc"]["signals"]]
