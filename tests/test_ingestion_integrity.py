from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import AlertRecord, AuditEntry, PosteriorState, PriorConfig, QCRecord
from app.main import app
from app.models import AlertStatus

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


def _payload(*, timestamp: datetime, value: float = 5.2, run_id: str = "integrity-run") -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": value,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "operator_id": "integrity-test",
        "control_material_lot": "LOT-001",
        "run_id": run_id,
        "units": "%",
        "flags": [],
        "entry_source": "manual",
    }


def _config_payload(*, effective_from: datetime) -> dict[str, object]:
    return {
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
        "effective_from": effective_from.isoformat(),
    }


@pytest.mark.anyio
async def test_concurrent_exact_duplicate_creates_one_record_and_one_observation(
    client: httpx.AsyncClient,
) -> None:
    payload = _payload(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1))

    first, second = await asyncio.gather(
        client.post("/qc/records", json=payload, headers=AUTH_HEADERS),
        client.post("/qc/records", json=payload, headers=AUTH_HEADERS),
    )

    assert first.status_code == second.status_code == 200
    bodies = [first.json(), second.json()]
    assert {body["status"] for body in bodies} == {"accepted", "duplicate"}
    assert bodies[0]["qc"]["id"] == bodies[1]["qc"]["id"]
    with Session(get_engine()) as session:
        records = session.exec(select(QCRecord).where(QCRecord.stream_id == "hba1c-arch")).all()
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == "hba1c-arch")).one()
        actions = [entry.action for entry in session.exec(select(AuditEntry)).all()]
        assert len(records) == 1
        assert state.n_obs == 1
        assert actions.count("ingest_qc") == 1
        assert actions.count("duplicate_qc_attempt") == 1


@pytest.mark.anyio
async def test_possible_duplicate_returns_conflict_without_mutating_statistics(client: httpx.AsyncClient) -> None:
    timestamp = datetime.now(timezone.utc) + timedelta(seconds=1)
    first = await client.post("/qc/records", json=_payload(timestamp=timestamp), headers=AUTH_HEADERS)
    assert first.status_code == 200

    possible = await client.post(
        "/qc/records",
        json=_payload(timestamp=timestamp, value=5.3, run_id="different-run"),
        headers=AUTH_HEADERS,
    )

    assert possible.status_code == 409
    assert possible.json()["detail"] == "possible_duplicate_requires_review"
    with Session(get_engine()) as session:
        assert len(session.exec(select(QCRecord)).all()) == 1
        assert session.exec(select(PosteriorState)).one().n_obs == 1


@pytest.mark.anyio
async def test_missing_prior_is_null_risk_and_holds_unless_action_rule_rejects(client: httpx.AsyncClient) -> None:
    with Session(get_engine()) as session:
        session.execute(delete(PriorConfig).where(col(PriorConfig.stream_id) == "hba1c-arch"))
        session.commit()
    now = datetime.now(timezone.utc)

    held = await client.post(
        "/qc/records",
        json=_payload(timestamp=now + timedelta(seconds=1), run_id="missing-prior-hold"),
        headers=AUTH_HEADERS,
    )
    rejected = await client.post(
        "/qc/records",
        json=_payload(timestamp=now + timedelta(seconds=2), value=6.0, run_id="missing-prior-reject"),
        headers=AUTH_HEADERS,
    )

    assert held.status_code == rejected.status_code == 200
    assert held.json()["qc"]["disposition"] == "hold-for-review"
    assert rejected.json()["qc"]["disposition"] == "reject"
    for response in (held, rejected):
        risk = response.json()["qc"]["bayesian_risk"]
        assert risk["status"] == "unavailable"
        assert risk["unavailable_reason"] == "missing_effective_prior"
        for field in (
            "probability_outside_limits",
            "probability_outside_warning",
            "risk_score",
            "posterior_mean",
            "posterior_sigma",
            "predictive_sigma",
            "credible_interval",
            "predictive_interval",
        ):
            assert risk[field] is None
    with Session(get_engine()) as session:
        assert session.exec(select(PosteriorState)).first() is None


@pytest.mark.anyio
async def test_model_evaluation_failure_rolls_back_partial_state_and_quarantines(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_after_partial_writes(session: Session, *_args: object, **_kwargs: object) -> None:
        prior = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).one()
        session.add(
            PosteriorState(
                stream_id="hba1c-arch",
                prior_id=prior.id,
                mu_n=5.2,
                kappa_n=2.0,
                alpha_n=2.5,
                beta_n=0.1,
                n_obs=1,
            )
        )
        session.add(
            AuditEntry(
                actor="failure-injection",
                action="partial_model_write",
                entity_type="posterior_state",
                after={"persisted": False},
            )
        )
        session.flush()
        raise ArithmeticError("injected numerical failure")

    monkeypatch.setattr("app.services.ingestion_evaluation.bayesian.infer_risk", fail_after_partial_writes)
    response = await client.post(
        "/qc/records",
        json=_payload(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1)),
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["quarantine"]["reason"] == "model_evaluation_failure"
    with Session(get_engine()) as session:
        assert session.exec(select(QCRecord)).first() is None
        assert session.exec(select(PosteriorState)).first() is None
        assert session.exec(select(AlertRecord)).first() is None
        actions = [entry.action for entry in session.exec(select(AuditEntry)).all()]
        assert actions == ["quarantine_qc"]


@pytest.mark.anyio
async def test_frequentist_history_resets_at_configuration_boundary(client: httpx.AsyncClient) -> None:
    now = datetime.now(timezone.utc)
    first = await client.post(
        "/qc/records",
        json=_payload(timestamp=now + timedelta(seconds=1), value=5.75, run_id="before-boundary"),
        headers=AUTH_HEADERS,
    )
    assert first.status_code == 200
    config = await client.post(
        "/streams/hba1c-arch/configs",
        json=_config_payload(effective_from=now + timedelta(seconds=2)),
        headers=AUTH_HEADERS,
    )
    assert config.status_code == 200, config.text

    second = await client.post(
        "/qc/records",
        json=_payload(timestamp=now + timedelta(seconds=3), value=5.75, run_id="after-boundary"),
        headers=AUTH_HEADERS,
    )

    assert second.status_code == 200
    assert "2-2s" not in {signal["rule"] for signal in second.json()["qc"]["signals"]}


@pytest.mark.anyio
async def test_reprocess_closes_and_recreates_active_alert_with_audit(client: httpx.AsyncClient) -> None:
    ingested = await client.post(
        "/qc/records",
        json=_payload(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1), value=6.0),
        headers=AUTH_HEADERS,
    )
    assert ingested.status_code == 200
    record_id = ingested.json()["qc"]["id"]
    original_alert_id = ingested.json()["alert_created"]["id"]

    excluded = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": False, "resolved_reason": "known synthetic outlier"},
        headers=AUTH_HEADERS,
    )
    assert excluded.status_code == 200
    with Session(get_engine()) as session:
        original = session.exec(select(AlertRecord).where(AlertRecord.alert_id == original_alert_id)).one()
        assert original.status == AlertStatus.CLOSED
        assert original.acknowledged_by is not None

    reinstated = await client.patch(
        f"/qc/records/{record_id}/resolution",
        json={"include_in_stats": True, "resolved_reason": "retest confirmed value"},
        headers=AUTH_HEADERS,
    )
    assert reinstated.status_code == 200
    with Session(get_engine()) as session:
        alerts = session.exec(select(AlertRecord).where(AlertRecord.qc_record_id == record_id)).all()
        active = [alert for alert in alerts if alert.status in {AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED}]
        audits = session.exec(select(AuditEntry).where(AuditEntry.action == "reconcile_alert")).all()
        assert len(active) == 1
        assert active[0].alert_id != original_alert_id
        assert active[0].disposition == "reject"
        assert len(audits) >= 2
        assert all(audit.reason == "evaluation superseded by reprocess" for audit in audits)


@pytest.mark.anyio
async def test_reconciliation_failure_rolls_back_record_alert_state_and_audits(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingested = await client.post(
        "/qc/records",
        json=_payload(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1), value=6.0),
        headers=AUTH_HEADERS,
    )
    assert ingested.status_code == 200
    record_id = ingested.json()["qc"]["id"]
    alert_id = ingested.json()["alert_created"]["id"]

    from app.services.alert_reconciliation import reconcile_stream_alerts as original_reconcile

    def reconcile_then_fail(*args: object, **kwargs: object) -> None:
        original_reconcile(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("injected after reconciliation writes")

    monkeypatch.setattr("app.evaluations.reconcile_stream_alerts", reconcile_then_fail)
    with pytest.raises(RuntimeError, match="injected after reconciliation writes"):
        await client.patch(
            f"/qc/records/{record_id}/resolution",
            json={"include_in_stats": False, "resolved_reason": "failure injection"},
            headers=AUTH_HEADERS,
        )

    with Session(get_engine()) as session:
        record = session.exec(select(QCRecord).where(QCRecord.id == record_id)).one()
        alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == alert_id)).one()
        assert record.include_in_stats is True
        assert alert.status == AlertStatus.OPEN
        assert session.exec(select(PosteriorState)).one().n_obs == 1
        actions = [entry.action for entry in session.exec(select(AuditEntry)).all()]
        assert "resolve_qc_record" not in actions
        assert "reconcile_alert" not in actions
