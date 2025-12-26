from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status

from app import bayesian, frequentist
from app.models import AuditEntry, DuplicateStatus, IngestionResult, QCRecordIn, QCRecordOut
from app.rbac import require_permission
from app.storage import storage
from app.models import Permission, FrequentistSignal, BayesianRisk, Alert

app = FastAPI(title="Bayesian QC Prototype", version="0.1.0")


@app.post("/qc/records", response_model=IngestionResult)
async def ingest_qc_record(
    payload: QCRecordIn,
    user=Depends(require_permission(Permission.INGEST_QC)),
):
    stream = storage.get_stream(payload.stream_id)
    if not stream:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not configured")

    if payload.units != stream.units:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Units do not match stream configuration")

    if payload.qc_level != stream.qc_level:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="QC level does not match stream configuration")

    duplicate_status = storage.add_record(payload)

    signals = frequentist.evaluate_rules(payload)
    risk = bayesian.infer_risk(payload)
    disposition = determine_disposition(signals, risk)

    qc_out = QCRecordOut(record=payload, signals=signals, bayesian_risk=risk, disposition=disposition)

    audit_entry = AuditEntry(
        timestamp=datetime.now(timezone.utc),
        actor=user.role.value,
        action="ingest_qc",
        before=None,
        after=qc_out.model_dump(),
        reason=payload.comments,
    )
    storage.add_audit_entry(audit_entry)

    alert = None
    if signals or risk.risk_score >= 50:
        alert = Alert(
            id=str(uuid4()),
            stream_id=payload.stream_id,
            created_at=datetime.now(timezone.utc),
            signals=signals,
            bayesian_risk=risk,
            disposition=disposition,
        )

    return IngestionResult(
        status="accepted",
        duplicate=duplicate_status,
        qc=qc_out,
        alert_created=alert,
        audit_entry=audit_entry,
    )


def determine_disposition(signals: list[FrequentistSignal], risk: BayesianRisk) -> str:
    if any(s.severity == "action" for s in signals):
        return "reject"
    if risk.risk_score >= 80:
        return "hold-for-review"
    if signals or risk.risk_score >= 50:
        return "monitor"
    return "accept"


@app.get("/streams")
async def list_streams():
    return list(storage.streams.values())


@app.get("/audit")
async def list_audit():
    return storage.audit_log
