from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.main import app

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}
JSON_HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def _stream_payload(stream_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": stream_id,
        "analyte": "Sulfur",
        "method": "ASTM D7039",
        "instrument": "Sindie",
        "site": "Refinery",
        "lab_bench": "Bench A",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "ppm",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
    }
    payload.update(overrides)
    return payload


def _setup_payload(stream_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": stream_id,
        "site": "Refinery",
        "lab_bench": "Bench A",
        "instrument_name": "Sindie",
        "method_name": "ASTM D7039",
        "parameter_name": "Sulfur",
        "units": "ppm",
        "material_name": "Sulfur QC",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
        "prior_mu0": 10.0,
        "prior_kappa0": 1.0,
        "prior_alpha0": 5.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_direct_prior_derives_omitted_beta_from_effective_stream_config(client: httpx.AsyncClient) -> None:
    effective_from = datetime.now(timezone.utc) - timedelta(minutes=1)
    stream = await client.post(
        "/streams",
        json=_stream_payload("derived-prior", effective_from=effective_from.isoformat()),
        headers=AUTH_HEADERS,
    )
    assert stream.status_code == 200, stream.text

    prior = await client.post(
        "/streams/derived-prior/priors",
        json={
            "stream_id": "ignored-path-wins",
            "mu0": 10.0,
            "kappa0": 1.0,
            "alpha0": 5.0,
            "effective_from": effective_from.isoformat(),
        },
        headers=AUTH_HEADERS,
    )
    assert prior.status_code == 200, prior.text
    assert prior.json()["beta0"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_omitted_beta_requires_an_effective_config_but_explicit_beta_is_preserved(
    client: httpx.AsyncClient,
) -> None:
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=1)
    stream = await client.post(
        "/streams",
        json=_stream_payload("future-config", effective_from=future.isoformat()),
        headers=AUTH_HEADERS,
    )
    assert stream.status_code == 200, stream.text

    omitted = await client.post(
        "/streams/future-config/priors",
        json={"stream_id": "future-config", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0, "effective_from": now.isoformat()},
        headers=AUTH_HEADERS,
    )
    assert omitted.status_code == 422
    assert "beta0 is required" in omitted.json()["detail"]

    explicit = await client.post(
        "/streams/future-config/priors",
        json={
            "stream_id": "future-config",
            "mu0": 10.0,
            "kappa0": 1.0,
            "alpha0": 2.0,
            "beta0": 0.75,
            "effective_from": now.isoformat(),
        },
        headers=AUTH_HEADERS,
    )
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["beta0"] == pytest.approx(0.75)


@pytest.mark.anyio
async def test_stream_setup_apply_derives_omitted_beta(client: httpx.AsyncClient) -> None:
    payload = {"rows": [_setup_payload("setup-derived-prior")]}
    preview = await client.post("/stream-setups/preview", json=payload, headers=AUTH_HEADERS)
    assert preview.status_code == 200, preview.text
    assert preview.json()["invalid"] == 0

    applied = await client.post("/stream-setups/apply", json=payload, headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["rows"][0]["prior"]["beta0"] == pytest.approx(1.0)

    explicit_payload = {"rows": [_setup_payload("setup-explicit-prior", prior_beta0=0.75)]}
    explicit_preview = await client.post("/stream-setups/preview", json=explicit_payload, headers=AUTH_HEADERS)
    assert explicit_preview.status_code == 200, explicit_preview.text
    explicit_applied = await client.post("/stream-setups/apply", json=explicit_payload, headers=AUTH_HEADERS)
    assert explicit_applied.status_code == 200, explicit_applied.text
    assert explicit_applied.json()["rows"][0]["prior"]["beta0"] == pytest.approx(0.75)


@pytest.mark.anyio
async def test_statistical_configuration_failures_return_422(client: httpx.AsyncClient) -> None:
    for stream_id, overrides in [
        ("nan-target", {"target_value": float("nan")}),
        ("positive-infinity-sigma", {"sigma": float("inf")}),
        ("negative-infinity-limit", {"warning_limit_sd": float("-inf")}),
        ("zero-sigma", {"sigma": 0.0}),
        ("negative-sigma", {"sigma": -0.5}),
    ]:
        response = await client.post(
            "/streams",
            content=json.dumps(_stream_payload(stream_id, **overrides)),
            headers=JSON_HEADERS,
        )
        assert response.status_code == 422, response.text

    bounds_response = await client.post(
        "/streams",
        json=_stream_payload("reversed-bounds", min_value=12.0, max_value=11.0),
        headers=AUTH_HEADERS,
    )
    assert bounds_response.status_code == 422

    conversion_response = await client.post(
        "/streams",
        json=_stream_payload(
            "bad-conversion",
            unit_conversions={"mg/L": {"factor": 1.0, "unexpected": 2.0}},
        ),
        headers=AUTH_HEADERS,
    )
    assert conversion_response.status_code == 422


@pytest.mark.anyio
async def test_stream_setup_preview_and_apply_reject_invalid_statistics(client: httpx.AsyncClient) -> None:
    invalid_setups = [
        _setup_payload("setup-nan", target_value=float("nan")),
        _setup_payload("setup-infinity", sigma=float("inf")),
        _setup_payload("setup-zero-scale", sigma=0.0),
        _setup_payload("setup-negative-kappa", prior_kappa0=-1.0),
        _setup_payload("setup-reversed-bounds", min_value=12.0, max_value=11.0),
    ]
    for index, setup in enumerate(invalid_setups):
        body = json.dumps({"rows": [setup]})
        for endpoint in ("preview", "apply"):
            response = await client.post(
                f"/stream-setups/{endpoint}",
                content=body,
                headers=JSON_HEADERS,
            )
            assert response.status_code == 422, f"case {index} {endpoint}: {response.text}"


@pytest.mark.anyio
async def test_valid_unit_conversion_shape_round_trips(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/streams",
        json=_stream_payload(
            "typed-conversion",
            unit_conversions={"mg/L": {"factor": 2.0, "offset": 1.0}, "ug/mL": 0.5},
        ),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["unit_conversions"] == {"mg/L": {"factor": 2.0, "offset": 1.0}, "ug/mL": 0.5}
