from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlmodel import Session, select

from app.db import get_engine
from app.db_models import AccessGrant, AlertRecord, ApiKey, AuditEntry, StreamConfig
from app.main import app
from app.models import AlertStatus, Role
from app.security import api_key_lookup_hash, hash_api_key

ADMIN = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        yield api


def _add_key(raw_key: str, role: Role, *, stream_id: str | None = None) -> dict[str, str]:
    with Session(get_engine()) as session:
        key = ApiKey(
            key_hash=hash_api_key(raw_key),
            key_lookup_hash=api_key_lookup_hash(raw_key),
            role=role,
            description=f"workflow {role.value}",
        )
        session.add(key)
        session.flush()
        if stream_id is not None:
            assert key.id is not None
            session.add(AccessGrant(api_key_id=key.id, stream_id=stream_id, reason="workflow scope test"))
        session.commit()
    return {"X-API-Key": raw_key}


def _add_second_stream() -> None:
    with Session(get_engine()) as session:
        session.add(
            StreamConfig(
                stream_id="other-stream",
                analyte="Other",
                method="HPLC",
                instrument="Architect",
                site="Other Lab",
                qc_level="Level 1",
                control_material_lot="OTHER-1",
                units="%",
                target_value=4.0,
                sigma=0.2,
            )
        )
        session.commit()


def _add_alert(alert_id: str, stream_id: str, *, status: AlertStatus = AlertStatus.OPEN) -> None:
    with Session(get_engine()) as session:
        session.add(
            AlertRecord(
                alert_id=alert_id,
                stream_id=stream_id,
                status=status,
                severity="high",
                disposition="reject",
                signals=[],
                bayesian_risk={
                    "status": "unavailable",
                    "unavailable_reason": "missing_effective_prior",
                },
            )
        )
        session.commit()


@pytest.mark.anyio
async def test_stakeholder_has_demo_workflow_permissions_but_cannot_ingest(client: httpx.AsyncClient) -> None:
    headers = _add_key("stakeholder-key", Role.STAKEHOLDER)
    _add_alert("stakeholder-alert", "hba1c-arch")

    me = await client.get("/me", headers=headers)
    assert me.status_code == 200
    assert set(me.json()["permissions"]) == {
        "read",
        "comment_qc",
        "resolve_qc",
        "manage_alerts",
        "manage_investigations",
        "manage_capas",
    }
    comment = await client.post(
        "/qc/comments",
        headers=headers,
        json={"target_type": "alert", "target_id": "stakeholder-alert", "body": "Useful demo note."},
    )
    assert comment.status_code == 200

    assert (await client.post("/qc/records", headers=headers, json={})).status_code == 403
    alert_update = await client.patch(
        "/alerts/stakeholder-alert",
        headers=headers,
        json={"status": "acknowledged", "reason": "demo review"},
    )
    investigation = await client.post(
        "/investigations",
        headers=headers,
        json={"alert_id": "stakeholder-alert", "problem_statement": "demo investigation"},
    )
    capa = await client.post(
        "/capas",
        headers=headers,
        json={"alert_id": "stakeholder-alert", "investigation_id": investigation.json()["id"]},
    )
    assert alert_update.status_code == investigation.status_code == capa.status_code == 200

    with Session(get_engine()) as session:
        audit_count_before = len(
            session.exec(select(AuditEntry).where(AuditEntry.action == "update_alert")).all()
        )
    no_op = await client.patch("/alerts/stakeholder-alert", headers=headers, json={})
    assert no_op.status_code == 200
    with Session(get_engine()) as session:
        audit_count_after = len(
            session.exec(select(AuditEntry).where(AuditEntry.action == "update_alert")).all()
        )
    assert audit_count_after == audit_count_before

    allowed_reads = [
        "/me",
        "/stream-catalog",
        "/streams/hba1c-arch/chart",
        "/kiosks",
        "/qc/backlog",
        "/qc/quarantine",
        "/qc/comments",
        "/alerts",
        "/investigations",
        "/capas",
        "/reports/summary",
    ]
    for path in allowed_reads:
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)

    forbidden_reads = [
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/audit",
        "/qc/events",
        "/qc/import-profiles",
        "/qc/imports",
        "/qc/imports/1",
        "/stream-setups/template.xlsx",
        "/instruments",
        "/methods",
        "/analytes",
        "/control-materials",
        "/enterprise-sites",
        "/lab-areas",
        "/streams",
        "/streams/hba1c-arch/configs",
        "/streams/hba1c-arch/priors",
    ]
    for path in forbidden_reads:
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.status_code, response.text)

    catalog = (await client.get("/stream-catalog", headers=headers)).json()
    assert catalog
    assert "unit_conversions" not in catalog[0]
    assert "rule_set" not in catalog[0]
    assert "created_by" not in catalog[0]
    assert "effective_from" not in catalog[0]


@pytest.mark.anyio
async def test_workflow_lists_updates_and_summary_obey_stream_scope(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "1")
    headers = _add_key("scoped-qa-key", Role.QA_MANAGER, stream_id="hba1c-arch")
    _add_second_stream()
    _add_alert("in-scope-alert", "hba1c-arch")
    _add_alert("out-scope-alert", "other-stream")

    in_inv = await client.post(
        "/investigations",
        headers=ADMIN,
        json={"alert_id": "in-scope-alert", "problem_statement": "in scope"},
    )
    out_inv = await client.post(
        "/investigations",
        headers=ADMIN,
        json={"alert_id": "out-scope-alert", "problem_statement": "out of scope"},
    )
    null_inv = await client.post(
        "/investigations",
        headers=ADMIN,
        json={"problem_statement": "admin-only legacy-compatible row"},
    )
    assert {in_inv.status_code, out_inv.status_code, null_inv.status_code} == {200}
    in_capa = await client.post(
        "/capas",
        headers=ADMIN,
        json={"alert_id": "in-scope-alert", "investigation_id": in_inv.json()["id"]},
    )
    out_capa = await client.post(
        "/capas",
        headers=ADMIN,
        json={"alert_id": "out-scope-alert", "investigation_id": out_inv.json()["id"]},
    )
    assert in_capa.status_code == out_capa.status_code == 200

    alerts = await client.get("/alerts", headers=headers)
    investigations = await client.get("/investigations", headers=headers)
    capas = await client.get("/capas", headers=headers)
    summary = await client.get("/reports/summary", headers=headers)
    assert alerts.headers["X-Total-Count"] == "1"
    assert [row["id"] for row in alerts.json()] == ["in-scope-alert"]
    assert [row["id"] for row in investigations.json()] == [in_inv.json()["id"]]
    assert [row["id"] for row in capas.json()] == [in_capa.json()["id"]]
    assert summary.json()["alerts"]["total"] == 1
    assert summary.json()["investigations"]["total"] == 1
    assert summary.json()["capas"]["total"] == 1
    assert (await client.get("/alerts/in-scope-alert", headers=headers)).status_code == 200
    assert (await client.get("/alerts/out-scope-alert", headers=headers)).status_code == 404
    assert (await client.get(f"/investigations/{in_inv.json()['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/investigations/{out_inv.json()['id']}", headers=headers)).status_code == 404
    assert (await client.get(f"/investigations/{null_inv.json()['id']}", headers=headers)).status_code == 404
    assert (await client.get(f"/capas/{in_capa.json()['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/capas/{out_capa.json()['id']}", headers=headers)).status_code == 404

    restricted_admin = _add_key("restricted-admin-key", Role.ADMIN, stream_id="hba1c-arch")
    restricted_rows = await client.get("/investigations", headers=restricted_admin)
    assert restricted_rows.status_code == 200
    assert null_inv.json()["id"] not in {row["id"] for row in restricted_rows.json()}
    assert (
        await client.get(f"/investigations/{null_inv.json()['id']}", headers=restricted_admin)
    ).status_code == 404

    cross_alert = await client.patch(
        "/alerts/out-scope-alert",
        headers=headers,
        json={"status": "acknowledged", "reason": "cross scope"},
    )
    cross_inv = await client.patch(
        f"/investigations/{out_inv.json()['id']}",
        headers=headers,
        json={"problem_statement": "cross scope", "reason": "cross scope"},
    )
    cross_capa = await client.patch(
        f"/capas/{out_capa.json()['id']}",
        headers=headers,
        json={"status": "draft", "reason": "cross scope"},
    )
    assert cross_alert.status_code == cross_inv.status_code == cross_capa.status_code == 404
    unlinked = await client.post(
        "/investigations",
        headers=headers,
        json={"problem_statement": "scoped unlinked row"},
    )
    assert unlinked.status_code == 403


@pytest.mark.anyio
async def test_alert_and_audit_pagination_expose_filtered_totals(client: httpx.AsyncClient) -> None:
    for index in range(5):
        _add_alert(f"page-alert-{index}", "hba1c-arch")
    _add_alert("closed-alert", "hba1c-arch", status=AlertStatus.CLOSED)
    with Session(get_engine()) as session:
        for index in range(5):
            session.add(
                AuditEntry(
                    actor="admin:key-1",
                    actor_role=Role.ADMIN,
                    action="page_action",
                    entity_type="alert",
                    entity_id=str(index),
                    after={"index": index},
                )
            )
        session.add(AuditEntry(actor="admin:key-1", action="other_action", entity_type="alert", after={}))
        session.commit()

    alerts = await client.get("/alerts?status=open&severity=high&limit=2&offset=1", headers=ADMIN)
    audit = await client.get("/audit?action=page_action&entity_type=alert&limit=2&offset=1", headers=ADMIN)
    assert alerts.status_code == audit.status_code == 200
    assert alerts.headers["X-Total-Count"] == "5"
    assert audit.headers["X-Total-Count"] == "5"
    assert len(alerts.json()) == len(audit.json()) == 2
