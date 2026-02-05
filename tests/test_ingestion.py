from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import PosteriorState, PriorConfig
from app.main import app

client = TestClient(app)
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


def test_ingestion_rejects_missing_stream():
    payload = _base_payload()
    payload["stream_id"] = "unknown"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_units_mismatch_rejected():
    payload = _base_payload()
    payload["units"] = "mmol/L"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_action_signal_and_alert_created():
    payload = _base_payload()
    payload["result_value"] = 6.0
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["qc"]["signals"][0]["rule"] == "1-3s"
    assert body["alert_created"] is not None
    assert body["qc"]["disposition"] == "reject"

    alerts_response = client.get("/alerts", headers=AUTH_HEADERS)
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert alerts
    assert alerts[0]["qc_record_id"] is not None
    assert alerts[0]["qc_record_timestamp"] is not None

    chart_response = client.get(
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


def test_duplicate_detection():
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    response_first = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_first.status_code == 200

    response_second = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_second.status_code == 200
    assert response_second.json()["duplicate"] == "duplicate"


def test_manual_entry_audited():
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    payload["comments"] = "entered offline"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    audit_response = client.get("/audit", headers=AUTH_HEADERS)
    assert audit_response.status_code == 200
    audit_entries = audit_response.json()
    assert any(entry["reason"] == "entered offline" for entry in audit_entries)


def test_bayesian_state_rebuilds_on_out_of_order_ingestion():
    now = datetime.now(timezone.utc)
    payload_late = _base_payload()
    payload_late["timestamp"] = (now + timedelta(seconds=10)).isoformat()
    payload_late["result_value"] = 5.0
    response_late = client.post("/qc/records", json=payload_late, headers=AUTH_HEADERS)
    assert response_late.status_code == 200

    payload_early = _base_payload()
    payload_early["timestamp"] = (now + timedelta(seconds=5)).isoformat()
    payload_early["result_value"] = 5.5
    response_early = client.post("/qc/records", json=payload_early, headers=AUTH_HEADERS)
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


def test_bayesian_state_resets_on_prior_change():
    now = datetime.now(timezone.utc)
    payload_early = _base_payload()
    payload_early["timestamp"] = (now + timedelta(seconds=5)).isoformat()
    payload_early["result_value"] = 5.5
    response_early = client.post("/qc/records", json=payload_early, headers=AUTH_HEADERS)
    assert response_early.status_code == 200

    prior_payload = {
        "mu0": 5.2,
        "kappa0": 1.0,
        "alpha0": 2.0,
        "beta0": 0.25**2,
        "effective_from": (now + timedelta(seconds=7)).isoformat(),
        "stream_id": "hba1c-arch",
    }
    prior_response = client.post(
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
    response_late = client.post("/qc/records", json=payload_late, headers=AUTH_HEADERS)
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
