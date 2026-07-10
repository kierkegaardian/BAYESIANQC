from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import AuditEntry, IngestionReceipt, QCBacklogItem, QCRecord, QCRecordQuarantine
from app.main import app
from app.services import ingestion_duplicates, qc_backlog, quarantine

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


def _raise_after(call: Callable[..., object], message: str) -> Callable[..., None]:
    def wrapper(*args: Any, **kwargs: Any) -> None:
        call(*args, **kwargs)
        raise RuntimeError(message)

    return wrapper


def _qc_payload(*, timestamp: datetime, backlog_id: int | None = None) -> dict[str, object]:
    return {
        "stream_id": "hba1c-arch",
        "result_value": 5.2,
        "timestamp": timestamp.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "operator_id": "atomicity-test",
        "control_material_lot": "LOT-001",
        "run_id": "atomicity-run",
        "units": "%",
        "flags": [],
        "entry_source": "manual",
        "qc_backlog_item_id": backlog_id,
    }


async def _create_backlog(client: httpx.AsyncClient) -> int:
    response = await client.post(
        "/qc/backlog",
        headers=AUTH_HEADERS,
        json={
            "source": "requested",
            "stream_id": "hba1c-arch",
            "due_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure_stage",
    ["quarantine_row", "quarantine_audit", "receipt", "backlog_linkage", "backlog_audit"],
)
async def test_quarantine_backlog_transaction_rolls_back_each_stage_and_idempotent_retry_is_clean(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    backlog_id = await _create_backlog(client)
    idempotency_key = f"quarantine-atomic-{failure_stage}"
    headers = AUTH_HEADERS | {"Idempotency-Key": idempotency_key}
    payload = _qc_payload(
        timestamp=datetime.now(timezone.utc) + timedelta(minutes=10),
        backlog_id=backlog_id,
    )
    original_audit = quarantine.record_audit
    original_receipt = quarantine.store_receipt
    original_backlog_audit = qc_backlog.record_audit

    with monkeypatch.context() as patch:
        if failure_stage == "quarantine_row":
            def fail_before_audit(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after quarantine row")

            patch.setattr(quarantine, "record_audit", fail_before_audit)
        elif failure_stage == "quarantine_audit":
            patch.setattr(
                quarantine,
                "record_audit",
                _raise_after(original_audit, "injected after quarantine audit"),
            )
        elif failure_stage == "receipt":
            patch.setattr(
                quarantine,
                "store_receipt",
                _raise_after(original_receipt, "injected after quarantine receipt"),
            )
        elif failure_stage == "backlog_linkage":
            def fail_before_backlog_audit(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("injected after backlog linkage")

            patch.setattr(qc_backlog, "record_audit", fail_before_backlog_audit)
        else:
            patch.setattr(
                qc_backlog,
                "record_audit",
                _raise_after(original_backlog_audit, "injected after backlog audit"),
            )

        with pytest.raises(RuntimeError, match="injected after"):
            await client.post("/qc/records", headers=headers, json=payload)

    with Session(get_engine()) as session:
        backlog = session.get(QCBacklogItem, backlog_id)
        assert backlog is not None and backlog.last_quarantine_id is None
        assert session.exec(select(QCRecordQuarantine)).all() == []
        assert session.exec(
            select(IngestionReceipt).where(IngestionReceipt.idempotency_key == idempotency_key)
        ).all() == []
        targeted = session.exec(
            select(AuditEntry).where(
                col(AuditEntry.action).in_(["quarantine_qc", "qc_backlog_quarantine_attempt"])
            )
        ).all()
        assert targeted == []

    retried = await client.post("/qc/records", headers=headers, json=payload)
    assert retried.status_code == 202, retried.text
    quarantine_id = retried.json()["quarantine"]["id"]
    repeated = await client.post("/qc/records", headers=headers, json=payload)
    assert repeated.status_code == 202
    assert repeated.json()["quarantine"]["id"] == quarantine_id

    with Session(get_engine()) as session:
        backlog = session.get(QCBacklogItem, backlog_id)
        receipts = session.exec(
            select(IngestionReceipt).where(IngestionReceipt.idempotency_key == idempotency_key)
        ).all()
        actions = [
            row.action
            for row in session.exec(
                select(AuditEntry).where(
                    col(AuditEntry.action).in_(["quarantine_qc", "qc_backlog_quarantine_attempt"])
                )
            ).all()
        ]
        assert backlog is not None and backlog.last_quarantine_id == quarantine_id
        assert len(session.exec(select(QCRecordQuarantine)).all()) == 1
        assert len(receipts) == 1
        assert actions.count("quarantine_qc") == 1
        assert actions.count("qc_backlog_quarantine_attempt") == 1


@pytest.mark.anyio
@pytest.mark.parametrize("failure_stage", ["duplicate_audit", "duplicate_receipt"])
async def test_exact_duplicate_failure_rolls_back_evidence_and_idempotent_retry_is_clean(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    payload = _qc_payload(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1))
    original = await client.post("/qc/records", headers=AUTH_HEADERS, json=payload)
    assert original.status_code == 200, original.text
    original_id = original.json()["qc"]["id"]
    idempotency_key = f"duplicate-atomic-{failure_stage}"
    headers = AUTH_HEADERS | {"Idempotency-Key": idempotency_key}
    original_audit = ingestion_duplicates.record_audit
    original_receipt = ingestion_duplicates.store_receipt

    with monkeypatch.context() as patch:
        if failure_stage == "duplicate_audit":
            patch.setattr(
                ingestion_duplicates,
                "record_audit",
                _raise_after(original_audit, "injected after duplicate audit"),
            )
        else:
            patch.setattr(
                ingestion_duplicates,
                "store_receipt",
                _raise_after(original_receipt, "injected after duplicate receipt"),
            )

        with pytest.raises(RuntimeError, match="injected after duplicate"):
            await client.post("/qc/records", headers=headers, json=payload)

    with Session(get_engine()) as session:
        assert len(session.exec(select(QCRecord)).all()) == 1
        assert session.exec(
            select(AuditEntry).where(AuditEntry.action == "duplicate_qc_attempt")
        ).all() == []
        assert session.exec(
            select(IngestionReceipt).where(IngestionReceipt.idempotency_key == idempotency_key)
        ).all() == []

    retried = await client.post("/qc/records", headers=headers, json=payload)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "duplicate"
    assert retried.json()["qc"]["id"] == original_id
    repeated = await client.post("/qc/records", headers=headers, json=payload)
    assert repeated.status_code == 200
    assert repeated.json() == retried.json()

    with Session(get_engine()) as session:
        assert len(session.exec(select(QCRecord)).all()) == 1
        assert len(session.exec(select(AuditEntry).where(AuditEntry.action == "duplicate_qc_attempt")).all()) == 1
        assert len(
            session.exec(
                select(IngestionReceipt).where(IngestionReceipt.idempotency_key == idempotency_key)
            ).all()
        ) == 1
