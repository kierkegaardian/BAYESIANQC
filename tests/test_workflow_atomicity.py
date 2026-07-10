from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from sqlmodel import Session, select

from app.db import get_engine
from app.db_models import AlertRecord, AuditEntry, Capa, CapaLink, QCComment, QCEvent
from app.main import app
from app.models import AlertStatus
from app.services import qc_comments, workflow_capas

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


def _add_alert(alert_id: str) -> None:
    with Session(get_engine()) as session:
        session.add(
            AlertRecord(
                alert_id=alert_id,
                stream_id="hba1c-arch",
                status=AlertStatus.OPEN,
                severity="high",
                disposition="reject",
                signals=[],
                bayesian_risk={"status": "unavailable", "unavailable_reason": "missing_effective_prior"},
            )
        )
        session.commit()


def _raise_after(call: Callable[..., object], message: str) -> Callable[..., None]:
    def wrapper(*args: Any, **kwargs: Any) -> None:
        call(*args, **kwargs)
        raise RuntimeError(message)

    return wrapper


@pytest.mark.anyio
@pytest.mark.parametrize("failure_stage", ["capa_row", "capa_link", "capa_audit"])
async def test_capa_create_rolls_back_every_flushed_stage_and_retries_cleanly(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    alert_id = f"capa-atomic-{failure_stage}"
    _add_alert(alert_id)
    payload = {"alert_id": alert_id}
    original_audit = workflow_capas.record_audit

    with monkeypatch.context() as patch:
        if failure_stage == "capa_row":
            def fail_before_link(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after CAPA row")

            patch.setattr(workflow_capas, "CapaLink", fail_before_link)
        elif failure_stage == "capa_link":
            def fail_before_audit(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after CAPA link")

            patch.setattr(workflow_capas, "record_audit", fail_before_audit)
        else:
            patch.setattr(
                workflow_capas,
                "record_audit",
                _raise_after(original_audit, "injected after CAPA audit"),
            )

        with pytest.raises(RuntimeError, match="injected after CAPA"):
            await client.post("/capas", headers=AUTH_HEADERS, json=payload)

    with Session(get_engine()) as session:
        assert session.exec(select(Capa)).all() == []
        assert session.exec(select(CapaLink)).all() == []
        assert session.exec(select(AuditEntry).where(AuditEntry.action == "create_capa")).all() == []

    retried = await client.post("/capas", headers=AUTH_HEADERS, json=payload)
    assert retried.status_code == 200, retried.text
    with Session(get_engine()) as session:
        capas = session.exec(select(Capa)).all()
        links = session.exec(select(CapaLink)).all()
        audits = session.exec(select(AuditEntry).where(AuditEntry.action == "create_capa")).all()
        assert len(capas) == len(links) == len(audits) == 1
        assert links[0].capa_id == capas[0].id == retried.json()["id"]


@pytest.mark.anyio
@pytest.mark.parametrize("failure_stage", ["comment_row", "comment_audit"])
async def test_comment_create_rolls_back_row_and_audit_then_retries_cleanly(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    alert_id = f"comment-atomic-{failure_stage}"
    _add_alert(alert_id)
    payload = {"target_type": "alert", "target_id": alert_id, "body": "Atomic stakeholder note"}
    original_audit = qc_comments.record_audit

    with monkeypatch.context() as patch:
        if failure_stage == "comment_row":
            def fail_before_audit(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after comment row")

            patch.setattr(qc_comments, "record_audit", fail_before_audit)
        else:
            patch.setattr(
                qc_comments,
                "record_audit",
                _raise_after(original_audit, "injected after comment audit"),
            )

        with pytest.raises(RuntimeError, match="injected after comment"):
            await client.post("/qc/comments", headers=AUTH_HEADERS, json=payload)

    with Session(get_engine()) as session:
        assert session.exec(select(QCComment)).all() == []
        assert session.exec(select(AuditEntry).where(AuditEntry.action == "create_qc_comment")).all() == []

    retried = await client.post("/qc/comments", headers=AUTH_HEADERS, json=payload)
    assert retried.status_code == 200, retried.text
    with Session(get_engine()) as session:
        assert len(session.exec(select(QCComment)).all()) == 1
        assert len(session.exec(select(AuditEntry).where(AuditEntry.action == "create_qc_comment")).all()) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("failure_stage", ["event_row", "event_audit"])
async def test_event_create_rolls_back_row_and_audit_then_retries_cleanly(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    import app.main as main_module

    payload = {
        "event_type": "maintenance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stream_id": "hba1c-arch",
        "metadata": {"note": failure_stage},
    }
    original_audit = main_module.record_audit

    with monkeypatch.context() as patch:
        if failure_stage == "event_row":
            def fail_before_audit(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after event row")

            patch.setattr(main_module, "record_audit", fail_before_audit)
        else:
            patch.setattr(
                main_module,
                "record_audit",
                _raise_after(original_audit, "injected after event audit"),
            )

        with pytest.raises(RuntimeError, match="injected after event"):
            await client.post("/qc/events", headers=AUTH_HEADERS, json=payload)

    with Session(get_engine()) as session:
        assert session.exec(select(QCEvent)).all() == []
        assert session.exec(select(AuditEntry).where(AuditEntry.action == "ingest_event")).all() == []

    retried = await client.post("/qc/events", headers=AUTH_HEADERS, json=payload)
    assert retried.status_code == 200, retried.text
    with Session(get_engine()) as session:
        assert len(session.exec(select(QCEvent)).all()) == 1
        assert len(session.exec(select(AuditEntry).where(AuditEntry.action == "ingest_event")).all()) == 1
