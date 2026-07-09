from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import AccessGrant, ApiKey
from app.import_db_models import ImportRow
from app.import_models import ImportRowStatus
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _add_scoped_key(
    raw_key: str,
    role: Role,
    *,
    site: str | None = None,
    lab_bench: str | None = None,
    stream_id: str | None = None,
    assignment_group: str | None = None,
) -> dict[str, str]:
    with Session(get_engine()) as session:
        key = ApiKey(
            key_hash=hash_api_key(raw_key),
            key_lookup_hash=api_key_lookup_hash(raw_key),
            role=role,
            description=f"scoped {role.value}",
        )
        session.add(key)
        session.flush()
        if key.id is None:
            raise RuntimeError("API key missing id")
        session.add(
            AccessGrant(
                api_key_id=key.id,
                site=site,
                lab_bench=lab_bench,
                stream_id=stream_id,
                assignment_group=assignment_group,
                created_by="test",
                reason="scope test",
            )
        )
        session.commit()
    return {"X-API-Key": raw_key}


def _stream_payload(stream_id: str, *, site: str, lab_bench: str, analyte: str = "Glucose") -> dict[str, object]:
    return {
        "stream_id": stream_id,
        "analyte": analyte,
        "method": "Hexokinase",
        "instrument": "Cobas",
        "site": site,
        "lab_bench": lab_bench,
        "qc_level": "Level 1",
        "control_material_lot": "GLU-LOT",
        "units": "mg/dL",
        "target_value": 95.0,
        "sigma": 4.0,
        "action_limit_sd": 3.0,
        "warning_limit_sd": 2.0,
        "risk_threshold_warn": 50,
        "risk_threshold_hold": 80,
    }


def _backlog_payload(stream_id: str, *, lab_bench: str, assignment_group: str) -> dict[str, object]:
    return {
        "source": "requested",
        "stream_id": stream_id,
        "due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "priority": "soon",
        "lab_bench": lab_bench,
        "assignment_group": assignment_group,
    }


def _qc_payload(stream_id: str = "hba1c-arch", **overrides: object) -> dict[str, object]:
    if stream_id == "hba1c-arch":
        payload: dict[str, object] = {
            "stream_id": "hba1c-arch",
            "result_value": 5.2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analyte": "HbA1c",
            "qc_level": "Level 1",
            "instrument_id": "Architect",
            "method_id": "HPLC",
            "control_material_lot": "LOT-001",
            "units": "%",
            "entry_source": "manual",
        }
    else:
        payload = {
            "stream_id": stream_id,
            "result_value": 96.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analyte": "Glucose",
            "qc_level": "Level 1",
            "instrument_id": "Cobas",
            "method_id": "Hexokinase",
            "control_material_lot": "GLU-LOT",
            "units": "mg/dL",
            "entry_source": "manual",
        }
    payload.update(overrides)
    return payload


async def _create_cross_scope_stream(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/streams",
        json=_stream_payload("glucose-west", site="West Lab", lab_bench="Chem Bench 2"),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


async def _create_import_profile(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/qc/import-profiles",
        json={
            "name": "Scoped CSV",
            "profile_type": "delimited_direct",
            "status": "active",
            "file_extensions": [".csv"],
            "filename_patterns": ["*.csv"],
            "config": {
                "delimiter": ",",
                "run_context_policy": "allow_provisional",
                "columns": {"stream_id": "Stream", "timestamp": "Timestamp", "result_value": "Result"},
            },
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_scoped_user_sees_effective_scope_and_cross_scope_access_is_denied(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "1")
    await _create_cross_scope_stream(client)
    restricted = _add_scoped_key("hba-scope-key", Role.QC_ANALYST, stream_id="hba1c-arch")

    me = await client.get("/me", headers=restricted)
    assert me.status_code == 200
    assert me.json()["effective_scope"] == {
        "unrestricted": False,
        "enforced": True,
        "sites": [],
        "lab_benches": [],
        "stream_ids": ["hba1c-arch"],
        "assignment_groups": [],
    }

    streams = await client.get("/streams", headers=restricted)
    assert streams.status_code == 200
    assert [row["stream_id"] for row in streams.json()] == ["hba1c-arch"]

    chart = await client.get("/streams/glucose-west/chart", headers=restricted)
    assert chart.status_code == 404

    other_backlog = await client.post(
        "/qc/backlog",
        json=_backlog_payload("glucose-west", lab_bench="Chem Bench 2", assignment_group="night-shift"),
        headers=AUTH_HEADERS,
    )
    assert other_backlog.status_code == 200, other_backlog.text
    other_backlog_id = other_backlog.json()["id"]

    backlog_rows = await client.get("/qc/backlog", headers=restricted)
    assert backlog_rows.status_code == 200
    assert all(row["id"] != other_backlog_id for row in backlog_rows.json())

    direct_backlog = await client.get(f"/qc/backlog/{other_backlog_id}", headers=restricted)
    assert direct_backlog.status_code == 404

    denied_backlog_create = await client.post(
        "/qc/backlog",
        json=_backlog_payload("glucose-west", lab_bench="Chem Bench 2", assignment_group="night-shift"),
        headers=restricted,
    )
    assert denied_backlog_create.status_code == 403

    denied_ingest = await client.post("/qc/records", json=_qc_payload("glucose-west"), headers=restricted)
    assert denied_ingest.status_code == 404

    denied_backlog_ingest = await client.post(
        "/qc/records",
        json=_qc_payload("glucose-west", qc_backlog_item_id=other_backlog_id),
        headers=restricted,
    )
    assert denied_backlog_ingest.status_code == 404


@pytest.mark.anyio
async def test_enforcement_flag_disables_grant_filtering(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "0")
    await _create_cross_scope_stream(client)
    restricted = _add_scoped_key("bypass-scope-key", Role.QC_ANALYST, stream_id="hba1c-arch")

    me = await client.get("/me", headers=restricted)
    assert me.status_code == 200
    assert me.json()["effective_scope"]["unrestricted"] is True
    assert me.json()["effective_scope"]["enforced"] is False

    streams = await client.get("/streams", headers=restricted)
    assert streams.status_code == 200
    assert {row["stream_id"] for row in streams.json()} == {"hba1c-arch", "glucose-west"}


@pytest.mark.anyio
async def test_location_config_respects_scoped_edit_grants(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "1")
    west = (
        await client.post(
            "/enterprise-sites",
            json={"name": "West Lab", "code": "WEST", "active": True},
            headers=AUTH_HEADERS,
        )
    ).json()
    east = (
        await client.post(
            "/enterprise-sites",
            json={"name": "East Lab", "code": "EAST", "active": True},
            headers=AUTH_HEADERS,
        )
    ).json()
    west_area = (
        await client.post(
            "/lab-areas",
            json={"site_id": west["id"], "name": "Chem Bench 1", "active": True},
            headers=AUTH_HEADERS,
        )
    ).json()
    east_area = (
        await client.post(
            "/lab-areas",
            json={"site_id": east["id"], "name": "Heme Bench 1", "active": True},
            headers=AUTH_HEADERS,
        )
    ).json()
    restricted = _add_scoped_key("location-steward-key", Role.DATA_STEWARD, site="West Lab", lab_bench="Chem Bench 1")

    sites = await client.get("/enterprise-sites?active=true", headers=restricted)
    assert sites.status_code == 200
    assert [row["name"] for row in sites.json()] == ["West Lab"]

    areas = await client.get(f"/lab-areas?site_id={west['id']}&active=true", headers=restricted)
    assert areas.status_code == 200
    assert [row["id"] for row in areas.json()] == [west_area["id"]]

    east_areas = await client.get(f"/lab-areas?site_id={east['id']}&active=true", headers=restricted)
    assert east_areas.status_code == 200
    assert east_areas.json() == []

    denied_site = await client.post(
        "/enterprise-sites",
        json={"name": "North Lab", "active": True},
        headers=restricted,
    )
    assert denied_site.status_code == 403

    allowed_area = await client.post(
        "/lab-areas",
        json={"site_id": west["id"], "name": "Chem Bench 2", "active": True},
        headers=restricted,
    )
    assert allowed_area.status_code == 200

    denied_area = await client.post(
        "/lab-areas",
        json={"site_id": east["id"], "name": "Heme Bench 2", "active": True},
        headers=restricted,
    )
    assert denied_area.status_code == 403
    assert east_area["name"] == "Heme Bench 1"


@pytest.mark.anyio
async def test_import_apply_marks_cross_scope_rows_ignored(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "1")
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path / "import-archive"))
    await _create_cross_scope_stream(client)
    await _create_import_profile(client)
    restricted = _add_scoped_key("import-scope-key", Role.QC_ANALYST, stream_id="hba1c-arch")
    timestamp = datetime.now(timezone.utc).isoformat()
    data = (
        "Stream,Timestamp,Result\n"
        f"hba1c-arch,{timestamp},5.1\n"
        f"glucose-west,{timestamp},97.0\n"
    ).encode()

    upload = await client.post(
        "/qc/imports",
        files={"file": ("scoped.csv", data, "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["id"]
    assert [row["stream_id"] for row in upload.json()["batch"]["rows"]] == ["hba1c-arch", "glucose-west"]

    applied = await client.post(f"/qc/imports/{batch_id}/apply", headers=restricted)
    assert applied.status_code == 200, applied.text
    assert [row["stream_id"] for row in applied.json()["rows"]] == ["hba1c-arch"]
    assert applied.json()["rows"][0]["status"] == "applied"

    with Session(get_engine()) as session:
        rows = session.exec(select(ImportRow).order_by(col(ImportRow.row_number))).all()
        assert [row.status for row in rows] == [ImportRowStatus.APPLIED, ImportRowStatus.IGNORED]
        assert rows[1].errors == ["out of scope for current API key"]
