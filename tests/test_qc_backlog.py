from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import ApiKey, AuditEntry, QCRecord
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _add_api_key(raw_key: str, role: Role) -> dict[str, str]:
    with Session(get_engine()) as session:
        session.add(
            ApiKey(
                key_hash=hash_api_key(raw_key),
                key_lookup_hash=api_key_lookup_hash(raw_key),
                role=role,
                description=f"test {role.value}",
            )
        )
        session.commit()
    return {"X-API-Key": raw_key}


def _backlog_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "requested",
        "stream_id": "hba1c-arch",
        "due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "priority": "soon",
        "lab_bench": "Chem Bench 1",
        "assignment_group": "day-shift",
        "assigned_to": "tech1",
        "reference_material_label": "HbA1c control",
        "notes": "morning setup",
        "requested_by": "supervisor1",
    }
    payload.update(overrides)
    return payload


def _qc_payload(item_id: int | None = None, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": "hba1c-arch",
        "result_value": 5.2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "operator_id": "tech1",
        "reagent_lot": "RL-001",
        "control_material_lot": "LOT-001",
        "calibration_status": "ok",
        "run_id": "backlog-run-1",
        "units": "%",
        "flags": [],
        "entry_source": "manual",
        "comments": "completed from backlog",
    }
    if item_id is not None:
        payload["qc_backlog_item_id"] = item_id
    payload.update(overrides)
    return payload


async def _create_item(client: httpx.AsyncClient, **overrides: object) -> dict[str, object]:
    response = await client.post("/qc/backlog", json=_backlog_payload(**overrides), headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _item_id(item: dict[str, object]) -> int:
    item_id = item["id"]
    assert isinstance(item_id, int)
    return item_id


@pytest.mark.anyio
async def test_backlog_create_list_filter_and_audit(client: httpx.AsyncClient) -> None:
    later_due = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    first = await _create_item(client, due_at=later_due, assignment_group="night-shift", assigned_to="tech2")
    second = await _create_item(client)

    response = await client.get(
        "/qc/backlog?assignment_group=day-shift&instrument=Architect&lab_bench=Chem%20Bench%201",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == [second["id"]]
    assert rows[0]["reference_material_lot"] == "LOT-001"
    assert rows[0]["analyte"] == "HbA1c"
    assert rows[0]["qc_level"] == "Level 1"

    all_rows = (await client.get("/qc/backlog", headers=AUTH_HEADERS)).json()
    assert [row["id"] for row in all_rows][:2] == [second["id"], first["id"]]

    with Session(get_engine()) as session:
        audit = session.exec(
            select(AuditEntry).where(AuditEntry.action == "create_qc_backlog_item").order_by(col(AuditEntry.id).desc())
        ).first()
        assert audit is not None
        assert audit.entity_type == "qc_backlog_item"


@pytest.mark.anyio
async def test_backlog_status_update_and_cancel_permission(client: httpx.AsyncClient) -> None:
    analyst_headers = _add_api_key("backlog-analyst-key", Role.QC_ANALYST)
    item = await _create_item(client)

    denied = await client.patch(
        f"/qc/backlog/{item['id']}",
        json={"status": "canceled", "reason": "cannot run"},
        headers=analyst_headers,
    )
    assert denied.status_code == 403

    started = await client.patch(
        f"/qc/backlog/{item['id']}",
        json={"status": "in_progress", "assigned_to": "tech2", "reason": "claimed"},
        headers=analyst_headers,
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["assigned_to"] == "tech2"

    canceled = await client.patch(
        f"/qc/backlog/{item['id']}",
        json={"status": "canceled", "reason": "instrument down"},
        headers=AUTH_HEADERS,
    )
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


@pytest.mark.anyio
async def test_backlog_ingestion_completion_and_idempotent_retry(client: httpx.AsyncClient) -> None:
    item = await _create_item(client)
    item_id = _item_id(item)
    headers = {**AUTH_HEADERS, "Idempotency-Key": "backlog-idempotent-1"}

    accepted = await client.post("/qc/records", json=_qc_payload(item_id), headers=headers)
    retry = await client.post("/qc/records", json=_qc_payload(item_id), headers=headers)

    assert accepted.status_code == 200
    assert retry.status_code == 200
    backlog = (await client.get(f"/qc/backlog/{item_id}", headers=AUTH_HEADERS)).json()
    assert backlog["status"] == "completed"
    assert backlog["completed_qc_record_id"] is not None
    assert retry.json()["idempotency_key"] == "backlog-idempotent-1"

    blocked = await client.post(
        "/qc/records",
        json=_qc_payload(item_id, timestamp=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()),
        headers=AUTH_HEADERS,
    )
    assert blocked.status_code == 409

    with Session(get_engine()) as session:
        rows = session.exec(select(QCRecord).where(QCRecord.qc_backlog_item_id == item_id)).all()
        assert len(rows) == 1


@pytest.mark.anyio
async def test_backlog_ingestion_mismatch_rejected_before_record_insert(client: httpx.AsyncClient) -> None:
    item = await _create_item(client)
    item_id = _item_id(item)

    response = await client.post(
        "/qc/records",
        json=_qc_payload(item_id, control_material_lot="LOT-WRONG"),
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    with Session(get_engine()) as session:
        rows = session.exec(select(QCRecord).where(QCRecord.qc_backlog_item_id == item_id)).all()
        assert rows == []


@pytest.mark.anyio
async def test_backlog_quarantined_attempt_stays_open_with_link(client: httpx.AsyncClient) -> None:
    item = await _create_item(client)
    item_id = _item_id(item)
    future_ts = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    response = await client.post(
        "/qc/records",
        json=_qc_payload(item_id, timestamp=future_ts),
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "quarantined"
    backlog = (await client.get(f"/qc/backlog/{item_id}", headers=AUTH_HEADERS)).json()
    assert backlog["status"] == "open"
    assert backlog["last_quarantine_id"] == body["quarantine"]["id"]
