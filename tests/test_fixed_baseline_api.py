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


def record(timestamp: datetime, value: float) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": value,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "control_material_lot": "LOT-001",
        "units": "%",
        "entry_source": "manual",
    }


def fixed_config(
    *,
    baseline_start: datetime,
    baseline_end: datetime,
    effective_from: datetime,
) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "analyte": "HbA1c",
        "method": "HPLC",
        "instrument": "Architect",
        "site": "Main Lab",
        "qc_level": "Level 1",
        "control_material_lot": "LOT-001",
        "units": "%",
        "target_value": 99,
        "sigma": 0.5,
        "warning_limit_sd": 2,
        "action_limit_sd": 3,
        "control_limit_source": "fixed_baseline",
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "effective_from": effective_from.isoformat(),
    }


@pytest.mark.anyio
async def test_fixed_baseline_limits_are_shared_without_future_data_leakage_and_prior_uses_submitted_sigma(
    client: httpx.AsyncClient,
) -> None:
    start = datetime.now(timezone.utc)
    first = start + timedelta(seconds=1)
    second = start + timedelta(seconds=2)
    outside_baseline = start + timedelta(seconds=3)
    effective = start + timedelta(seconds=4)
    baseline_record_ids: list[int] = []
    for timestamp, value in [(first, 5.0), (second, 5.4), (outside_baseline, 50.0)]:
        response = await client.post("/qc/records", json=record(timestamp, value), headers=AUTH)
        assert response.status_code == 200
        if timestamp <= second:
            baseline_record_ids.append(response.json()["qc"]["id"])

    config = await client.post(
        "/streams/hba1c-arch/configs",
        json=fixed_config(
            baseline_start=start,
            baseline_end=second,
            effective_from=effective,
        ),
        headers=AUTH,
    )
    assert config.status_code == 200
    assert config.json()["control_limit_source"] == "fixed_baseline"
    assert config.json()["evaluation_reprocess_required"] is False

    prior = await client.post(
        "/streams/hba1c-arch/priors",
        json={
            "stream_id": "hba1c-arch",
            "mu0": 5.2,
            "kappa0": 1,
            "alpha0": 3,
            "effective_from": effective.isoformat(),
        },
        headers=AUTH,
    )
    assert prior.status_code == 200
    assert prior.json()["beta0"] == pytest.approx(0.5)

    evaluated = await client.post(
        "/qc/records",
        json=record(start + timedelta(seconds=5), 5.2),
        headers=AUTH,
    )
    assert evaluated.status_code == 200
    limits = evaluated.json()["qc"]["evaluation"]["limits"]
    assert limits["source"] == "fixed_baseline"
    assert limits["centerline"] == pytest.approx(5.2)
    assert limits["sigma"] == pytest.approx(0.2828427124746193)
    assert limits["baseline_count"] == 2
    assert limits["warning_lower"] == pytest.approx(5.2 - 2 * limits["sigma"])
    assert limits["action_upper"] == pytest.approx(5.2 + 3 * limits["sigma"])

    backdated = await client.post(
        "/qc/records",
        json=record(first + timedelta(milliseconds=500), 100.0),
        headers=AUTH,
    )
    assert backdated.status_code == 200
    chart = await client.get(
        "/streams/hba1c-arch/chart?include_evaluations=true",
        headers=AUTH,
    )
    evaluated_record = next(
        item for item in chart.json()["records"] if item["id"] == evaluated.json()["qc"]["id"]
    )
    assert evaluated_record["evaluation"]["limits"] == limits

    excluded = await client.patch(
        f"/qc/records/{baseline_record_ids[0]}/resolution",
        json={"include_in_stats": False, "resolved_reason": "baseline exclusion freeze check"},
        headers=AUTH,
    )
    assert excluded.status_code == 200
    chart = await client.get(
        "/streams/hba1c-arch/chart?include_evaluations=true",
        headers=AUTH,
    )
    evaluated_record = next(
        item for item in chart.json()["records"] if item["id"] == evaluated.json()["qc"]["id"]
    )
    assert evaluated_record["evaluation"]["limits"] == limits


@pytest.mark.anyio
async def test_fixed_baseline_rejects_insufficient_history(client: httpx.AsyncClient) -> None:
    start = datetime.now(timezone.utc)
    only = start + timedelta(seconds=1)
    assert (await client.post("/qc/records", json=record(only, 5.2), headers=AUTH)).status_code == 200
    response = await client.post(
        "/streams/hba1c-arch/configs",
        json=fixed_config(
            baseline_start=start,
            baseline_end=only,
            effective_from=start + timedelta(seconds=2),
        ),
        headers=AUTH,
    )
    assert response.status_code == 422
    assert "at least two" in response.json()["detail"]
