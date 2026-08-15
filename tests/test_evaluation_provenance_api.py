from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, func, select

from app.db import get_engine
from app.db_models import AlertRecord, ApiKey, QCRecord
from app.evaluation_db_models import EvaluationRun, QCRecordEvaluation
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key

AUTH = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def record_payload(timestamp: datetime, result: float = 5.2) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": result,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "control_material_lot": "LOT-001",
        "units": "%",
        "entry_source": "manual",
    }


def config_payload(effective_from: datetime, *, target: float, sigma: float = 0.25) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "analyte": "HbA1c",
        "method": "HPLC",
        "instrument": "Architect",
        "site": "Main Lab",
        "qc_level": "Level 1",
        "control_material_lot": "LOT-001",
        "units": "%",
        "target_value": target,
        "sigma": sigma,
        "warning_limit_sd": 2,
        "action_limit_sd": 3,
        "bayes_warn_prob_threshold": 1,
        "bayes_warn_consecutive": 1,
        "bayes_hold_prob_threshold": 1,
        "bayes_hold_consecutive": 1,
        "control_limit_source": "configured",
        "effective_from": effective_from.isoformat(),
    }


def role_headers(role: Role) -> dict[str, str]:
    raw = f"{role.value}-evaluation-key"
    with Session(get_engine()) as session:
        session.add(
            ApiKey(
                key_hash=hash_api_key(raw),
                key_lookup_hash=api_key_lookup_hash(raw),
                role=role,
                description="evaluation provenance test",
            )
        )
        session.commit()
    return {"X-API-Key": raw}


@pytest.mark.anyio
async def test_ingestion_snapshot_pointer_cache_and_chart_provenance_match(
    client: httpx.AsyncClient,
) -> None:
    at = datetime.now(timezone.utc) + timedelta(seconds=1)
    response = await client.post("/qc/records", json=record_payload(at), headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    provenance = body["qc"]["evaluation"]
    assert provenance["engine_version"] == "qc-evaluation-v2"
    assert provenance["frequentist_method"] == "single-level-westgard-like-v2"
    assert provenance["bayesian_method"] == "nig-student-t-v1"
    assert provenance["risk_semantics"] == "post-update-next-observation-v1"
    assert provenance["limits"]["centerline"] == 5.2
    assert body["qc"]["bayesian_risk"]["probability_outside_warning"] >= body["qc"]["bayesian_risk"]["probability_outside_limits"]

    with Session(get_engine()) as session:
        record = session.get(QCRecord, body["qc"]["id"])
        assert record is not None and record.current_evaluation_id == provenance["evaluation_id"]
        snapshot = session.get(QCRecordEvaluation, record.current_evaluation_id)
        assert snapshot is not None
        assert record.signals == snapshot.signals
        assert record.bayesian_risk == snapshot.bayesian_risk
        assert record.disposition == snapshot.disposition

    chart = await client.get("/streams/hba1c-arch/chart", headers=AUTH)
    assert chart.status_code == 200
    assert chart.json()["records"][0]["evaluation"] == provenance


@pytest.mark.anyio
async def test_backdated_config_requires_admin_preview_apply_and_preview_is_read_only(
    client: httpx.AsyncClient,
) -> None:
    at = datetime.now(timezone.utc) + timedelta(seconds=2)
    ingested = await client.post("/qc/records", json=record_payload(at), headers=AUTH)
    assert ingested.status_code == 200
    created = await client.post(
        "/streams/hba1c-arch/configs",
        json=config_payload(at - timedelta(seconds=1), target=8),
        headers=AUTH,
    )
    assert created.status_code == 200
    assert created.json()["evaluation_reprocess_required"] is True

    blocked = await client.post(
        "/qc/records",
        json=record_payload(at + timedelta(seconds=1)),
        headers=AUTH,
    )
    assert blocked.status_code == 409

    qa_preview = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/preview",
        json={},
        headers=role_headers(Role.QA_MANAGER),
    )
    assert qa_preview.status_code == 403
    with Session(get_engine()) as session:
        snapshot_count = session.exec(select(func.count()).select_from(QCRecordEvaluation)).one()
        run_count = session.exec(select(func.count()).select_from(EvaluationRun)).one()
        pointer = session.exec(select(QCRecord.current_evaluation_id)).one()

    preview = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/preview?limit=10",
        json={},
        headers=AUTH,
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["records_changed"] == 1
    assert preview_body["changes"][0]["new_disposition"] == "reject"
    with Session(get_engine()) as session:
        assert session.exec(select(func.count()).select_from(QCRecordEvaluation)).one() == snapshot_count
        assert session.exec(select(func.count()).select_from(EvaluationRun)).one() == run_count
        assert session.exec(select(QCRecord.current_evaluation_id)).one() == pointer

    applied = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/apply",
        json={
            "preview_fingerprint": preview_body["preview_fingerprint"],
            "reason": "Approved backdated target correction",
        },
        headers=AUTH,
    )
    assert applied.status_code == 200
    assert applied.json()["records_evaluated"] == 1
    versions = await client.get("/streams/hba1c-arch/configs", headers=AUTH)
    assert versions.status_code == 200
    assert versions.json()[0]["evaluation_reprocess_required"] is False


@pytest.mark.anyio
async def test_stale_preview_is_rejected(client: httpx.AsyncClient) -> None:
    at = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert (await client.post("/qc/records", json=record_payload(at), headers=AUTH)).status_code == 200
    assert (
        await client.post(
            "/streams/hba1c-arch/configs",
            json=config_payload(at - timedelta(seconds=1), target=7),
            headers=AUTH,
        )
    ).status_code == 200
    preview = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/preview",
        json={},
        headers=AUTH,
    )
    fingerprint = preview.json()["preview_fingerprint"]
    prior = await client.post(
        "/streams/hba1c-arch/priors",
        json={
            "stream_id": "hba1c-arch",
            "mu0": 5.2,
            "kappa0": 1,
            "alpha0": 2,
            "beta0": 0.0625,
            "effective_from": (at - timedelta(seconds=1)).isoformat(),
        },
        headers=AUTH,
    )
    assert prior.status_code == 200
    stale = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/apply",
        json={"preview_fingerprint": fingerprint, "reason": "stale test"},
        headers=AUTH,
    )
    assert stale.status_code == 409


@pytest.mark.anyio
async def test_superseded_alert_preserves_acknowledgement_without_replacement_when_accepting(
    client: httpx.AsyncClient,
) -> None:
    at = datetime.now(timezone.utc) + timedelta(seconds=2)
    ingested = await client.post("/qc/records", json=record_payload(at, 6.2), headers=AUTH)
    assert ingested.status_code == 200
    alert = ingested.json()["alert_created"]
    assert alert is not None
    acknowledged = await client.patch(
        f"/alerts/{alert['id']}",
        json={"status": "acknowledged", "reason": "investigation opened"},
        headers=AUTH,
    )
    assert acknowledged.status_code == 200
    assert (
        await client.post(
            "/streams/hba1c-arch/configs",
            json=config_payload(at - timedelta(seconds=1), target=6.2, sigma=10),
            headers=AUTH,
        )
    ).status_code == 200
    preview = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/preview",
        json={},
        headers=AUTH,
    )
    assert preview.json()["alerts_superseded"] == 1
    assert preview.json()["alerts_to_create"] == 0, preview.json()
    applied = await client.post(
        "/streams/hba1c-arch/evaluation-reprocess/apply",
        json={
            "preview_fingerprint": preview.json()["preview_fingerprint"],
            "reason": "Correct control-limit basis",
        },
        headers=AUTH,
    )
    assert applied.status_code == 200
    alerts = await client.get("/alerts", headers=AUTH)
    original = next(row for row in alerts.json() if row["id"] == alert["id"])
    assert original["status"] == "acknowledged"
    assert original["evaluation_status"] == "superseded"
    assert original["source_evaluation_id"] == alert["source_evaluation_id"]
    assert original["current_evaluation_id"] != original["source_evaluation_id"]
    assert original["replacement_alert_id"] is None
    with Session(get_engine()) as session:
        assert session.exec(select(func.count()).select_from(AlertRecord)).one() == 1
