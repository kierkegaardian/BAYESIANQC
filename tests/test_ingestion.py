import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import ApiKey, PosteriorState, PriorConfig, QCRecord, QCRecordQuarantine
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key, legacy_sha256_hash

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


def _base_payload():
    now = datetime.now(timezone.utc)
    return {
        "stream_id": "hba1c-arch",
        "result_value": 6.0,
        "timestamp": now.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "operator_id": "tech1",
        "reagent_lot": "RL-001",
        "control_material_lot": "LOT-001",
        "calibration_status": "ok",
        "run_id": "run-123",
        "units": "%",
        "flags": [],
        "entry_source": "manual",
        "comments": "manual entry",
    }


def _stream_payload(stream_id: str) -> dict[str, object]:
    return {
        "stream_id": stream_id,
        "analyte": "HbA1c",
        "method": "HPLC",
        "instrument": "Architect",
        "site": "Main Lab",
        "matrix": None,
        "qc_level": "Level 1",
        "control_material_lot": "LOT-001",
        "units": "%",
        "target_value": 5.2,
        "sigma": 0.25,
        "action_limit_sd": 3.0,
        "warning_limit_sd": 2.0,
        "risk_threshold_warn": 50,
        "risk_threshold_hold": 80,
    }


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


def _expected_posterior(
    prior: PriorConfig,
    records: list[QCRecord],
) -> tuple[float, float, float, float]:
    mu_n = prior.mu0
    kappa_n = prior.kappa0
    alpha_n = prior.alpha0
    beta_n = prior.beta0
    for record in records:
        next_kappa = kappa_n + 1
        next_mu = (kappa_n * mu_n + record.result_value) / next_kappa
        next_alpha = alpha_n + 0.5
        next_beta = beta_n + 0.5 * kappa_n * ((record.result_value - mu_n) ** 2) / next_kappa
        mu_n, kappa_n, alpha_n, beta_n = next_mu, next_kappa, next_alpha, next_beta
    return mu_n, kappa_n, alpha_n, beta_n


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_ingestion_quarantines_missing_stream(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["stream_id"] = "unknown"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "quarantined"
    assert body["quarantine"]["reason"] == "mapping_failure"
    assert body["quarantine"]["payload"]["stream_id"] == "unknown"


@pytest.mark.anyio
async def test_units_mismatch_quarantined_without_qc_record(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["units"] = "mmol/L"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "quarantined"
    assert body["quarantine"]["reason"] == "unit_mismatch"
    assert body["quarantine"]["payload"]["units"] == "mmol/L"
    assert body["quarantine"]["qc_record_id"] is None

    with Session(get_engine()) as session:
        assert session.exec(select(QCRecord).where(QCRecord.run_id == "run-123")).first() is None
        queued = session.exec(select(QCRecordQuarantine)).one()
        assert queued.reason == "unit_mismatch"


@pytest.mark.anyio
async def test_future_timestamp_quarantined(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)

    assert response.status_code == 202
    body = response.json()
    assert body["quarantine"]["reason"] == "suspicious_timestamp"
    assert body["quarantine"]["failures"][0]["field"] == "timestamp"


@pytest.mark.anyio
async def test_out_of_bounds_value_quarantined(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    stream_payload = _stream_payload("hba1c-arch")
    stream_payload.update(
        {
            "effective_from": (now + timedelta(seconds=1)).isoformat(),
            "min_value": 4.0,
            "max_value": 6.0,
        }
    )
    config_response = await client.post("/streams/hba1c-arch/configs", json=stream_payload, headers=AUTH_HEADERS)
    assert config_response.status_code == 200

    payload = _base_payload()
    payload["timestamp"] = (now + timedelta(seconds=2)).isoformat()
    payload["result_value"] = 7.5
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)

    assert response.status_code == 202
    body = response.json()
    assert body["quarantine"]["reason"] == "out_of_bounds"
    assert body["quarantine"]["context"]["stream_config"]["max_value"] == 6.0
    with Session(get_engine()) as session:
        assert session.exec(select(QCRecord).where(QCRecord.run_id == "run-123")).first() is None


@pytest.mark.anyio
async def test_quarantine_queue_can_be_reviewed(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["units"] = "mmol/L"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 202
    quarantine_id = response.json()["quarantine"]["id"]

    queue_response = await client.get("/qc/quarantine", headers=AUTH_HEADERS)
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert [row["id"] for row in queue] == [quarantine_id]

    missing_reason = await client.patch(
        f"/qc/quarantine/{quarantine_id}",
        json={"status": "reviewed", "review_reason": ""},
        headers=AUTH_HEADERS,
    )
    assert missing_reason.status_code == 422

    reviewed = await client.patch(
        f"/qc/quarantine/{quarantine_id}",
        json={"status": "reviewed", "review_reason": "confirmed unit typo in source sheet"},
        headers=AUTH_HEADERS,
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["status"] == "reviewed"
    assert body["reviewed_by"].startswith("admin:key-")

    open_queue = await client.get("/qc/quarantine", headers=AUTH_HEADERS)
    assert open_queue.status_code == 200
    assert open_queue.json() == []


@pytest.mark.anyio
async def test_action_signal_and_alert_created(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["result_value"] = 6.0
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["qc"]["signals"][0]["rule"] == "1-3s"
    assert body["alert_created"] is not None
    assert body["qc"]["disposition"] == "reject"

    alerts_response = await client.get("/alerts", headers=AUTH_HEADERS)
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert alerts
    assert alerts[0]["qc_record_id"] is not None
    assert alerts[0]["qc_record_timestamp"] is not None

    chart_response = await client.get(
        "/streams/hba1c-arch/chart?limit=10&include_evaluations=true",
        headers=AUTH_HEADERS,
    )
    assert chart_response.status_code == 200
    chart = chart_response.json()
    assert chart["records"]
    last = chart["records"][-1]
    assert "signals" in last
    assert "bayesian_risk" in last
    assert "disposition" in last

    with Session(get_engine()) as session:
        row = session.exec(
            select(QCRecord)
            .where(QCRecord.stream_id == "hba1c-arch")
            .order_by(col(QCRecord.timestamp).desc())
            .limit(1)
        ).first()
        assert row is not None
        assert row.signals is not None
        assert row.signals and row.signals[0]["rule"] == "1-3s"
        assert row.bayesian_risk is not None
        assert row.disposition == "reject"


@pytest.mark.anyio
async def test_minimal_qc_payload_accepts_documented_optional_fields(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    for field in ["operator_id", "reagent_lot", "calibration_status", "run_id", "comments"]:
        del payload[field]

    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["qc"]["record"]["operator_id"] is None
    assert body["qc"]["record"]["comments"] is None


@pytest.mark.anyio
async def test_manual_batch_multi_level_records_use_qc_records_endpoint(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    level2_stream = _stream_payload("hba1c-arch-l2")
    level2_stream.update(
        {
            "qc_level": "Level 2",
            "control_material_lot": "LOT-002",
            "target_value": 6.2,
            "effective_from": now.isoformat(),
        }
    )
    stream_response = await client.post("/streams", json=level2_stream, headers=AUTH_HEADERS)
    assert stream_response.status_code == 200

    prior_response = await client.post(
        "/streams/hba1c-arch-l2/priors",
        json={
            "stream_id": "hba1c-arch-l2",
            "mu0": 6.2,
            "kappa0": 1.0,
            "alpha0": 2.0,
            "beta0": 0.25**2,
            "effective_from": now.isoformat(),
        },
        headers=AUTH_HEADERS,
    )
    assert prior_response.status_code == 200

    run_id = "manual-batch-run-1"
    payloads = []
    for stream_id, level, lot, value, offset in [
        ("hba1c-arch", "Level 1", "LOT-001", 5.2, 1),
        ("hba1c-arch-l2", "Level 2", "LOT-002", 6.2, 2),
    ]:
        payload = _base_payload()
        payload.update(
            {
                "stream_id": stream_id,
                "qc_level": level,
                "control_material_lot": lot,
                "result_value": value,
                "timestamp": (now + timedelta(seconds=offset)).isoformat(),
                "run_id": run_id,
                "comments": "batch manual entry",
            }
        )
        payloads.append(payload)

    responses = [await client.post("/qc/records", json=payload, headers=AUTH_HEADERS) for payload in payloads]
    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["qc"]["record"]["run_id"] for response in responses] == [run_id, run_id]
    assert [response.json()["qc"]["record"]["qc_level"] for response in responses] == ["Level 1", "Level 2"]

    with Session(get_engine()) as session:
        rows = session.exec(
            select(QCRecord).where(QCRecord.run_id == run_id).order_by(col(QCRecord.stream_id).asc())
        ).all()
        assert len(rows) == 2
        assert {row.stream_id for row in rows} == {"hba1c-arch", "hba1c-arch-l2"}
        assert all(row.entry_source == "manual" for row in rows)
        assert all(row.bayesian_risk is not None for row in rows)


@pytest.mark.anyio
async def test_read_roles_can_read_without_mutating(client: httpx.AsyncClient):
    auditor_headers = _add_api_key("auditor-key", Role.AUDITOR)
    steward_headers = _add_api_key("steward-key", Role.DATA_STEWARD)
    analyst_headers = _add_api_key("analyst-key", Role.QC_ANALYST)

    for endpoint in [
        "/me",
        "/streams",
        "/alerts",
        "/audit",
        "/qc/quarantine",
        "/reports/summary",
        "/streams/hba1c-arch/chart",
    ]:
        response = await client.get(endpoint, headers=auditor_headers)
        assert response.status_code == 200

    auditor_ingest = await client.post("/qc/records", json=_base_payload(), headers=auditor_headers)
    assert auditor_ingest.status_code == 403

    steward_create = await client.post("/streams", json=_stream_payload("steward-created"), headers=steward_headers)
    assert steward_create.status_code == 200
    steward_ingest = await client.post("/qc/records", json=_base_payload(), headers=steward_headers)
    assert steward_ingest.status_code == 403

    analyst_payload = _base_payload()
    analyst_payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    analyst_ingest = await client.post("/qc/records", json=analyst_payload, headers=analyst_headers)
    assert analyst_ingest.status_code == 200
    analyst_create_stream = await client.post("/streams", json=_stream_payload("analyst-created"), headers=analyst_headers)
    assert analyst_create_stream.status_code == 403

    with Session(get_engine()) as session:
        record = session.exec(select(QCRecord).where(QCRecord.stream_id == "hba1c-arch")).first()
        assert record is not None
        assert record.id is not None
        record_id = record.id
    analyst_resolution = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": False, "resolved_reason": "analyst cannot approve"},
        headers=analyst_headers,
    )
    assert analyst_resolution.status_code == 403


@pytest.mark.anyio
async def test_invalid_api_key_does_not_scan_pbkdf2_keys(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
    _add_api_key("valid-but-not-used", Role.QC_ANALYST)

    def fail_verify(_raw_key: str, _stored_hash: str) -> bool:
        raise AssertionError("request auth scanned PBKDF2 keys")

    monkeypatch.setattr("app.rbac.verify_api_key", fail_verify)
    response = await client.get("/me", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_legacy_api_key_migrates_without_active_key_scan(client: httpx.AsyncClient):
    raw_key = "legacy-key-for-migration"
    with Session(get_engine()) as session:
        session.add(
            ApiKey(
                key_hash=legacy_sha256_hash(raw_key),
                role=Role.QC_ANALYST,
                description="legacy test key",
            )
        )
        session.commit()

    response = await client.get("/me", headers={"X-API-Key": raw_key})
    assert response.status_code == 200

    with Session(get_engine()) as session:
        key = session.exec(select(ApiKey).where(ApiKey.description == "legacy test key")).one()
        assert key.key_hash.startswith("pbkdf2_sha256$")
        assert key.key_lookup_hash == api_key_lookup_hash(raw_key)


@pytest.mark.anyio
async def test_audit_entries_include_actor_role_and_key(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200

    audit_response = await client.get("/audit", headers=AUTH_HEADERS)
    assert audit_response.status_code == 200
    audit_entries = audit_response.json()
    ingest_entry = next(entry for entry in audit_entries if entry["action"] == "ingest_qc")
    assert ingest_entry["actor_role"] == "admin"
    assert ingest_entry["api_key_id"] is not None
    assert ingest_entry["after"]


@pytest.mark.anyio
async def test_resolution_reason_required_for_statistical_inclusion_changes(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    with Session(get_engine()) as session:
        record = session.exec(select(QCRecord).where(QCRecord.run_id == "run-123")).first()
        assert record is not None
        assert record.id is not None
        record_id = record.id

    missing_reason = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": False},
        headers=AUTH_HEADERS,
    )
    assert missing_reason.status_code == 422

    resolved = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": False, "resolved_reason": "known reagent issue"},
        headers=AUTH_HEADERS,
    )
    assert resolved.status_code == 200

    missing_reinclusion_reason = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": True},
        headers=AUTH_HEADERS,
    )
    assert missing_reinclusion_reason.status_code == 422


@pytest.mark.anyio
async def test_alert_update_requires_reason_and_uses_backend_actor(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    payload["result_value"] = 6.0
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    alert_id = response.json()["alert_created"]["id"]

    missing_reason = await client.patch(
        f"/alerts/{alert_id}",
        json={"status": "acknowledged", "acknowledged_by": "ui-user"},
        headers=AUTH_HEADERS,
    )
    assert missing_reason.status_code == 422

    updated = await client.patch(
        f"/alerts/{alert_id}",
        json={"status": "acknowledged", "acknowledged_by": "ui-user", "reason": "supervisor review"},
        headers=AUTH_HEADERS,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"].startswith("admin:key-")


@pytest.mark.anyio
async def test_concurrent_same_stream_ingestion_matches_posterior_history(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)

    async def post_record(index: int) -> httpx.Response:
        payload = _base_payload()
        payload["timestamp"] = (now + timedelta(seconds=index)).isoformat()
        payload["result_value"] = 5.1 + index * 0.01
        payload["run_id"] = f"concurrent-{index}"
        return await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)

    responses = await asyncio.gather(*(post_record(index) for index in range(1, 6)))
    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200]

    with Session(get_engine()) as session:
        records = list(
            session.exec(
                select(QCRecord)
                .where(QCRecord.stream_id == "hba1c-arch", QCRecord.include_in_stats == True)
                .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
            ).all()
        )
        prior = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).first()
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == "hba1c-arch")).first()
        assert prior is not None
        assert state is not None
        assert state.n_obs == len(records) == 5
        assert _as_utc(state.updated_at) == _as_utc(records[-1].timestamp)
        expected_mu, expected_kappa, expected_alpha, expected_beta = _expected_posterior(prior, records)
        assert state.mu_n == pytest.approx(expected_mu, abs=1e-12)
        assert state.kappa_n == pytest.approx(expected_kappa, abs=1e-12)
        assert state.alpha_n == pytest.approx(expected_alpha, abs=1e-12)
        assert state.beta_n == pytest.approx(expected_beta, abs=1e-12)


@pytest.mark.anyio
async def test_bayesian_risk_includes_intervals_and_policy_state(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
    payload["result_value"] = 5.2
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    risk = body["qc"]["bayesian_risk"]
    assert "probability_outside_warning" in risk
    assert "predictive_interval" in risk
    assert "warn_streak" in risk
    assert "hold_streak" in risk


@pytest.mark.anyio
async def test_bayesian_hold_requires_persistence(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    stream_payload = {
        "stream_id": "hba1c-arch",
        "analyte": "HbA1c",
        "method": "HPLC",
        "instrument": "Architect",
        "site": "Main Lab",
        "matrix": None,
        "qc_level": "Level 1",
        "control_material_lot": "LOT-001",
        "units": "%",
        "target_value": 5.2,
        "sigma": 0.25,
        "action_limit_sd": 3.0,
        "warning_limit_sd": 2.0,
        "risk_threshold_warn": 50,
        "risk_threshold_hold": 80,
        "bayes_warn_prob_threshold": 1.0,
        "bayes_warn_consecutive": 1,
        "bayes_hold_prob_threshold": 0.0,
        "bayes_hold_consecutive": 2,
        "min_value": None,
        "max_value": None,
        "effective_from": (now + timedelta(seconds=1)).isoformat(),
    }
    config_response = await client.post(
        "/streams/hba1c-arch/configs",
        json=stream_payload,
        headers=AUTH_HEADERS,
    )
    assert config_response.status_code == 200

    payload1 = _base_payload()
    payload1["timestamp"] = (now + timedelta(seconds=10)).isoformat()
    payload1["result_value"] = 5.2
    response1 = await client.post("/qc/records", json=payload1, headers=AUTH_HEADERS)
    assert response1.status_code == 200
    assert response1.json()["qc"]["disposition"] == "accept"

    payload2 = _base_payload()
    payload2["timestamp"] = (now + timedelta(seconds=11)).isoformat()
    payload2["result_value"] = 5.2
    response2 = await client.post("/qc/records", json=payload2, headers=AUTH_HEADERS)
    assert response2.status_code == 200
    assert response2.json()["qc"]["disposition"] == "hold-for-review"


@pytest.mark.anyio
async def test_duplicate_detection(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    response_first = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_first.status_code == 200

    response_second = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_second.status_code == 200
    assert response_second.json()["duplicate"] == "duplicate"


@pytest.mark.anyio
async def test_manual_entry_audited(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    payload["comments"] = "entered offline"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    audit_response = await client.get("/audit", headers=AUTH_HEADERS)
    assert audit_response.status_code == 200
    audit_entries = audit_response.json()
    assert any(entry["reason"] == "entered offline" for entry in audit_entries)


@pytest.mark.anyio
async def test_bayesian_state_rebuilds_on_out_of_order_ingestion(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    payload_late = _base_payload()
    payload_late["timestamp"] = (now + timedelta(seconds=10)).isoformat()
    payload_late["result_value"] = 5.0
    response_late = await client.post("/qc/records", json=payload_late, headers=AUTH_HEADERS)
    assert response_late.status_code == 200

    payload_early = _base_payload()
    payload_early["timestamp"] = (now + timedelta(seconds=5)).isoformat()
    payload_early["result_value"] = 5.5
    response_early = await client.post("/qc/records", json=payload_early, headers=AUTH_HEADERS)
    assert response_early.status_code == 200

    def as_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    with Session(get_engine()) as session:
        prior = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).first()
        assert prior is not None
        assert prior.id is not None
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == "hba1c-arch")).first()
        assert state is not None
        assert as_utc(state.updated_at) == datetime.fromisoformat(payload_late["timestamp"])
        assert state.prior_id == prior.id
        assert state.n_obs == 2

        def update(mu0: float, kappa0: float, alpha0: float, beta0: float, x: float):
            kappa_n = kappa0 + 1
            mu_n = (kappa0 * mu0 + x) / kappa_n
            alpha_n = alpha0 + 0.5
            beta_n = beta0 + 0.5 * kappa0 * ((x - mu0) ** 2) / kappa_n
            return mu_n, kappa_n, alpha_n, beta_n

        mu_n, kappa_n, alpha_n, beta_n = update(prior.mu0, prior.kappa0, prior.alpha0, prior.beta0, 5.5)
        mu_n, kappa_n, alpha_n, beta_n = update(mu_n, kappa_n, alpha_n, beta_n, 5.0)
        assert abs(state.mu_n - mu_n) < 1e-9
        assert abs(state.kappa_n - kappa_n) < 1e-9
        assert abs(state.alpha_n - alpha_n) < 1e-9
        assert abs(state.beta_n - beta_n) < 1e-9


@pytest.mark.anyio
async def test_bayesian_state_resets_on_prior_change(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    payload_early = _base_payload()
    payload_early["timestamp"] = (now + timedelta(seconds=5)).isoformat()
    payload_early["result_value"] = 5.5
    response_early = await client.post("/qc/records", json=payload_early, headers=AUTH_HEADERS)
    assert response_early.status_code == 200

    prior_payload = {
        "mu0": 5.2,
        "kappa0": 1.0,
        "alpha0": 2.0,
        "beta0": 0.25**2,
        "effective_from": (now + timedelta(seconds=7)).isoformat(),
        "stream_id": "hba1c-arch",
    }
    prior_response = await client.post(
        "/streams/hba1c-arch/priors",
        json=prior_payload,
        headers=AUTH_HEADERS,
    )
    assert prior_response.status_code == 200
    new_prior = prior_response.json()
    assert new_prior["version"] == 2

    payload_late = _base_payload()
    payload_late["timestamp"] = (now + timedelta(seconds=10)).isoformat()
    payload_late["result_value"] = 5.0
    response_late = await client.post("/qc/records", json=payload_late, headers=AUTH_HEADERS)
    assert response_late.status_code == 200

    def as_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    with Session(get_engine()) as session:
        priors = session.exec(
            select(PriorConfig)
            .where(PriorConfig.stream_id == "hba1c-arch")
            .order_by(col(PriorConfig.version).desc())
        ).all()
        assert len(priors) >= 2
        prior2 = priors[0]
        assert prior2.id is not None

        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == "hba1c-arch")).first()
        assert state is not None
        assert as_utc(state.updated_at) == datetime.fromisoformat(payload_late["timestamp"])
        assert state.prior_id == prior2.id
        assert state.n_obs == 1
