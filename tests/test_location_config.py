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


async def _site(client: httpx.AsyncClient, name: str = "Refinery Site 1") -> dict[str, object]:
    response = await client.post(
        "/enterprise-sites",
        json={"name": name, "code": "REF-1", "description": "Refinery lab", "active": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _area(client: httpx.AsyncClient, site_id: int, name: str = "Bench A") -> dict[str, object]:
    response = await client.post(
        "/lab-areas",
        json={"site_id": site_id, "name": name, "description": "Primary fuel bench", "active": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _id(row: dict[str, object]) -> int:
    value = row["id"]
    assert isinstance(value, int)
    return value


@pytest.mark.anyio
async def test_location_crud_conflicts_and_filters(client: httpx.AsyncClient) -> None:
    seeded = await client.get("/enterprise-sites?active=true", headers=AUTH_HEADERS)
    assert seeded.status_code == 200
    assert "Main Lab" in {row["name"] for row in seeded.json()}

    site = await _site(client)
    duplicate = await client.post("/enterprise-sites", json={"name": "refinery site 1"}, headers=AUTH_HEADERS)
    assert duplicate.status_code == 409

    area = await _area(client, _id(site))
    duplicate_area = await client.post(
        "/lab-areas",
        json={"site_id": _id(site), "name": "bench a"},
        headers=AUTH_HEADERS,
    )
    assert duplicate_area.status_code == 409

    filtered = await client.get(f"/lab-areas?site_id={_id(site)}&active=true", headers=AUTH_HEADERS)
    assert filtered.status_code == 200
    assert filtered.json() == [area]


@pytest.mark.anyio
async def test_create_test_requires_analyte_uom_and_resolution(client: httpx.AsyncClient) -> None:
    site = await _site(client, "Clinical Site")
    area = await _area(client, _id(site), "Chemistry")
    instrument = await client.post(
        "/instruments",
        json={
            "name": "Cobas 8000",
            "manufacturer": "Roche",
            "model": "c702",
            "site_id": _id(site),
            "lab_area_id": _id(area),
            "active": True,
        },
        headers=AUTH_HEADERS,
    )
    assert instrument.status_code == 200, instrument.text
    assert instrument.json()["site"] == "Clinical Site"
    assert instrument.json()["lab_bench"] == "Chemistry"

    missing_resolution = await client.post(
        "/tests",
        json={
            "instrument_id": instrument.json()["id"],
            "name": "Glucose",
            "analyte_name": "Glucose",
            "analyte_units": "mg/dL",
        },
        headers=AUTH_HEADERS,
    )
    assert missing_resolution.status_code == 422

    created = await client.post(
        "/tests",
        json={
            "instrument_id": instrument.json()["id"],
            "name": "Glucose",
            "technique": "Hexokinase",
            "description": "Serum glucose method",
            "analyte_name": "Glucose",
            "analyte_units": "mg/dL",
            "analyte_result_resolution": 0.1,
            "analyte_description": "Glucose concentration",
        },
        headers=AUTH_HEADERS,
    )
    assert created.status_code == 200, created.text
    assert created.json()["method"]["name"] == "Glucose"
    assert created.json()["method"]["description"] == "Serum glucose method"
    assert created.json()["analyte"]["units"] == "mg/dL"
    assert created.json()["analyte"]["result_resolution"] == 0.1


@pytest.mark.anyio
async def test_stream_setup_with_config_ids_reuses_canonical_records(client: httpx.AsyncClient) -> None:
    site = await _site(client, "Metals Site")
    area = await _area(client, _id(site), "Metals Bench")
    instrument = (
        await client.post(
            "/instruments",
            json={"name": "Spark OES", "site_id": _id(site), "lab_area_id": _id(area)},
            headers=AUTH_HEADERS,
        )
    ).json()
    test = (
        await client.post(
            "/tests",
            json={
                "instrument_id": instrument["id"],
                "name": "Carbon",
                "analyte_name": "Carbon",
                "analyte_units": "%",
                "analyte_result_resolution": 0.001,
            },
            headers=AUTH_HEADERS,
        )
    ).json()
    material = (
        await client.post(
            "/control-materials",
            json={"name": "Steel CRM", "lot": "CRM-1", "qc_level": "Level 1", "matrix": "Steel"},
            headers=AUTH_HEADERS,
        )
    ).json()

    payload = {
        "rows": [
            {
                "stream_id": "metals-carbon-l1",
                "site_id": _id(site),
                "lab_area_id": _id(area),
                "site": "Wrong Site",
                "lab_bench": "Wrong Bench",
                "instrument_id": instrument["id"],
                "instrument_name": "Wrong Instrument",
                "method_id": test["method"]["id"],
                "method_name": "Wrong Method",
                "analyte_id": test["analyte"]["id"],
                "parameter_name": "Wrong Analyte",
                "units": "wrong",
                "control_material_id": material["id"],
                "material_name": "Wrong Material",
                "qc_level": "Wrong Level",
                "control_material_lot": "Wrong Lot",
                "target_value": 0.15,
                "sigma": 0.01,
            }
        ]
    }
    preview = await client.post("/stream-setups/preview", json=payload, headers=AUTH_HEADERS)
    assert preview.status_code == 200, preview.text
    canonical = preview.json()["rows"][0]["canonical"]
    assert canonical["site"] == "Metals Site"
    assert canonical["lab_bench"] == "Metals Bench"
    assert canonical["instrument_name"] == "Spark OES"
    assert canonical["method_name"] == "Carbon"
    assert canonical["parameter_name"] == "Carbon"
    assert canonical["material_name"] == "Steel CRM"

    applied = await client.post("/stream-setups/apply", json=payload, headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    stream = applied.json()["rows"][0]["stream"]
    assert stream["site"] == "Metals Site"
    assert stream["lab_bench"] == "Metals Bench"
    assert stream["instrument"] == "Spark OES"
    assert stream["method"] == "Carbon"
    assert stream["analyte"] == "Carbon"
