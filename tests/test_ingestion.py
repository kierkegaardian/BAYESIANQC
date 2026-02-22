from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import PosteriorState, PriorConfig, QCRecord
from app.main import app

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

@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_ingestion_rejects_missing_stream(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["stream_id"] = "unknown"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_units_mismatch_rejected(client: httpx.AsyncClient):
    payload = _base_payload()
    payload["units"] = "mmol/L"
    response = await client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


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
