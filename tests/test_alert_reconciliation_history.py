from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, func, select

from app.db import get_engine
from app.db_models import AlertRecord, CapaLink, InvestigationAlertLink
from app.main import app

AUTH = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def record_payload(timestamp: datetime) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": 6.2,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "control_material_lot": "LOT-001",
        "units": "%",
        "entry_source": "manual",
    }


def replacement_config(effective_from: datetime) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "analyte": "HbA1c",
        "method": "HPLC",
        "instrument": "Architect",
        "site": "Main Lab",
        "qc_level": "Level 1",
        "control_material_lot": "LOT-001",
        "units": "%",
        "target_value": 6.2,
        "sigma": 10,
        "warning_limit_sd": 2,
        "action_limit_sd": 3,
        "risk_threshold_warn": 0,
        "risk_threshold_hold": 100,
        "control_limit_source": "configured",
        "effective_from": effective_from.isoformat(),
    }


@pytest.mark.anyio
async def test_replacement_preserves_original_alert_workflow_links(
    client: httpx.AsyncClient,
) -> None:
    at = datetime.now(timezone.utc) + timedelta(seconds=2)
    ingested = await client.post("/qc/records", json=record_payload(at), headers=AUTH)
    assert ingested.status_code == 200
    alert = ingested.json()["alert_created"]
    assert alert is not None
    updated = await client.patch(
        f"/alerts/{alert['id']}",
        json={
            "status": "acknowledged",
            "assigned_to": "qc-lead",
            "reason": "Open linked investigation",
        },
        headers=AUTH,
    )
    assert updated.status_code == 200
    investigation = await client.post(
        "/investigations",
        json={"problem_statement": "Review original action alert", "alert_id": alert["id"]},
        headers=AUTH,
    )
    assert investigation.status_code == 200
    capa = await client.post(
        "/capas",
        json={
            "root_cause_category": "method",
            "alert_id": alert["id"],
            "investigation_id": investigation.json()["id"],
        },
        headers=AUTH,
    )
    assert capa.status_code == 200

    config = await client.post(
        "/streams/hba1c-arch/configs",
        json=replacement_config(at - timedelta(seconds=1)),
        headers=AUTH,
    )
    assert config.status_code == 200
    preview = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/preview",
        headers=AUTH,
    )
    assert preview.json()["alerts_superseded"] == 1
    assert preview.json()["alerts_to_create"] == 1
    applied = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/apply",
        json={
            "preview_fingerprint": preview.json()["preview_fingerprint"],
            "reason": "Approve changed alert semantics",
        },
        headers=AUTH,
    )
    assert applied.status_code == 200
    assert applied.json()["alerts_created"] == 1

    alerts = (await client.get("/alerts", headers=AUTH)).json()
    original = next(item for item in alerts if item["id"] == alert["id"])
    replacement = next(item for item in alerts if item["id"] == original["replacement_alert_id"])
    assert original["status"] == "acknowledged"
    assert original["assigned_to"] == "qc-lead"
    assert original["evaluation_status"] == "superseded"
    assert replacement["evaluation_status"] == "current"

    with Session(get_engine()) as session:
        original_row = session.exec(
            select(AlertRecord).where(AlertRecord.alert_id == alert["id"])
        ).one()
        assert original_row.id is not None
        investigation_links = session.exec(
            select(func.count())
            .select_from(InvestigationAlertLink)
            .where(InvestigationAlertLink.alert_id == original_row.id)
        ).one()
        capa_links = session.exec(
            select(func.count())
            .select_from(CapaLink)
            .where(CapaLink.alert_id == original_row.id)
        ).one()
        assert investigation_links == 1
        assert capa_links == 1
