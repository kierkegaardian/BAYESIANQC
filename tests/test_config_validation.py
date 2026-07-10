from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.main import app

AUTH_HEADERS = {"X-API-Key": "local-dev-key", "Content-Type": "application/json"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        yield api


def _stream_payload(stream_id: str) -> dict[str, object]:
    return {
        "stream_id": stream_id,
        "analyte": "Synthetic control",
        "method": "Synthetic method",
        "instrument": "Synthetic instrument",
        "qc_level": "L1",
        "control_material_lot": "SYN-1",
        "units": "u",
        "target_value": 10.0,
        "sigma": 1.0,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_value", float("nan")),
        ("sigma", float("inf")),
        ("warning_limit_sd", float("-inf")),
        ("action_limit_sd", float("nan")),
        ("min_value", float("inf")),
        ("max_value", float("nan")),
    ],
)
async def test_nonfinite_statistical_config_returns_422(
    client: httpx.AsyncClient,
    field: str,
    value: float,
) -> None:
    payload = _stream_payload(f"finite-{field}")
    payload[field] = value
    response = await client.post("/streams", content=json.dumps(payload), headers=AUTH_HEADERS)
    assert response.status_code == 422, response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "conversion",
    [
        {"other": float("nan")},
        {"other": {"factor": float("inf"), "offset": 0.0}},
        {"other": {"factor": 1.0, "offset": float("-inf")}},
    ],
)
async def test_nonfinite_unit_conversion_returns_422(
    client: httpx.AsyncClient,
    conversion: dict[str, object],
) -> None:
    payload = _stream_payload("finite-conversion")
    payload["unit_conversions"] = conversion
    response = await client.post("/streams", content=json.dumps(payload), headers=AUTH_HEADERS)
    assert response.status_code == 422, response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mu0", float("nan")),
        ("kappa0", float("inf")),
        ("alpha0", float("-inf")),
        ("beta0", float("nan")),
    ],
)
async def test_nonfinite_prior_config_returns_422(
    client: httpx.AsyncClient,
    field: str,
    value: float,
) -> None:
    payload = {"stream_id": "hba1c-arch", "mu0": 5.2, "kappa0": 1.0, "alpha0": 2.0, "beta0": 0.0625}
    payload[field] = value
    response = await client.post(
        "/streams/hba1c-arch/priors",
        content=json.dumps(payload),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_ordering_and_positive_prior_contracts_return_422(client: httpx.AsyncClient) -> None:
    reversed_bounds = _stream_payload("reversed-bounds") | {"min_value": 12.0, "max_value": 8.0}
    reversed_limits = _stream_payload("reversed-limits") | {"warning_limit_sd": 4.0, "action_limit_sd": 3.0}
    for payload in (reversed_bounds, reversed_limits):
        response = await client.post("/streams", json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 422, response.text

    for field, value in (("kappa0", 0.0), ("alpha0", 1.0), ("beta0", 0.0)):
        prior = {"stream_id": "hba1c-arch", "mu0": 5.2, "kappa0": 1.0, "alpha0": 2.0, "beta0": 0.0625}
        prior[field] = value
        response = await client.post("/streams/hba1c-arch/priors", json=prior, headers=AUTH_HEADERS)
        assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_r4s_is_rejected_and_omitted_beta_is_derived(client: httpx.AsyncClient) -> None:
    r4s = _stream_payload("unsupported-r4s") | {"rule_set": {"rules": ["1-3s", "R-4s"]}}
    response = await client.post("/streams", json=r4s, headers=AUTH_HEADERS)
    assert response.status_code == 422, response.text

    prior = {"stream_id": "hba1c-arch", "mu0": 5.2, "kappa0": 1.0, "alpha0": 3.0}
    response = await client.post("/streams/hba1c-arch/priors", json=prior, headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["beta0"] == pytest.approx((3.0 - 1.0) * 0.25**2)
