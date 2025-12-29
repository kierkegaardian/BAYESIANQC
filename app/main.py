from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app import bayesian, frequentist
from app.db import get_engine, get_session, init_db
from app.db_models import (
    AlertRecord,
    Analyte,
    AuditEntry,
    Capa,
    CapaLink,
    Instrument,
    Investigation,
    InvestigationAlertLink,
    Method,
    PriorConfig,
    QCEvent,
    QCRecord,
    StreamConfig,
)
from app.models import (
    AnalyteIn,
    AnalyteOut,
    AnalyteUpdate,
    AlertOut,
    AlertStatus,
    AlertUpdate,
    AuditEntryOut,
    CapaIn,
    CapaOut,
    CapaStatus,
    DuplicateStatus,
    IngestionResult,
    InstrumentIn,
    InstrumentOut,
    InstrumentUpdate,
    InvestigationIn,
    InvestigationOut,
    InvestigationStatus,
    MethodIn,
    MethodOut,
    MethodUpdate,
    Permission,
    PriorConfigIn,
    PriorConfigOut,
    QCEventIn,
    QCEventOut,
    QCRecordIn,
    QCRecordOut,
    StreamConfigIn,
    StreamConfigOut,
)
from app.rbac import UserContext, require_permission
from app.storage import (
    create_alert,
    create_capa,
    create_event,
    create_investigation,
    create_prior_config,
    create_stream_config,
    detect_duplicate,
    get_active_stream_config,
    get_idempotent_response,
    list_stream_configs,
    record_audit,
    seed_defaults,
    store_receipt,
    update_alert,
    update_capa,
    update_investigation,
)

app = FastAPI(title="Bayesian QC Prototype", version="0.2.0", docs_url=None, redoc_url=None)

cors_origins = [
    origin.strip()
    for origin in os.getenv("BAYESIANQC_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    with Session(get_engine()) as session:
        seed_defaults(session)


def _help_button(content: str) -> str:
    return f"""
<style>
  #bayesianqc-help-button {{
    position: fixed;
    right: 16px;
    bottom: 16px;
    z-index: 9999;
    padding: 10px 14px;
    border-radius: 999px;
    border: 1px solid #1f2937;
    background: #111827;
    color: #f9fafb;
    font: 600 14px/1.2 ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
    cursor: pointer;
  }}
  #bayesianqc-help-panel {{
    position: fixed;
    right: 16px;
    bottom: 64px;
    z-index: 9999;
    max-width: 360px;
    padding: 14px 16px;
    border-radius: 12px;
    border: 1px solid #1f2937;
    background: #f9fafb;
    color: #111827;
    font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    display: none;
  }}
  #bayesianqc-help-panel h3 {{
    margin: 0 0 6px 0;
    font-size: 15px;
  }}
  #bayesianqc-help-panel p {{
    margin: 0;
  }}
</style>
<button id="bayesianqc-help-button" type="button">Help</button>
<div id="bayesianqc-help-panel" role="dialog" aria-live="polite">
  <h3>What this page does</h3>
  <p>{content}</p>
</div>
<script>
  (function() {{
    var button = document.getElementById('bayesianqc-help-button');
    var panel = document.getElementById('bayesianqc-help-panel');
    if (!button || !panel) return;
    button.addEventListener('click', function() {{
      panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
    }});
  }})();
</script>
"""


def _inject_help(html: str, content: str) -> str:
    snippet = _help_button(content)
    marker = "</body>"
    if marker in html:
        return html.replace(marker, f"{snippet}\n{marker}")
    return html + snippet


@app.get("/", include_in_schema=False)
async def root_page():
    content = (
        "This is the BayesianQC API landing page. Use the links below to open the "
        "interactive docs and remember to send an X-API-Key header (default: local-dev-key) "
        "when calling endpoints."
    )
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>BayesianQC API</title>
  </head>
  <body style="font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif; padding: 24px;">
    <h1>BayesianQC API</h1>
    <p>Prototype QC ingestion + decisioning API with persistent storage.</p>
    <ul>
      <li><a href="/docs">Swagger UI</a> for interactive requests</li>
      <li><a href="/redoc">ReDoc</a> for reference docs</li>
      <li><a href="/openapi.json">OpenAPI JSON</a></li>
    </ul>
    <p>All API calls require <code>X-API-Key</code> (default: <code>local-dev-key</code>).</p>
  </body>
</html>
"""
    return HTMLResponse(_inject_help(html, content))


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    content = (
        "Use Swagger UI to explore endpoints and send requests. Click a route, choose "
        "'Try it out', and add the X-API-Key header (default: local-dev-key) before executing."
    )
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="BayesianQC API Docs",
    ).body.decode("utf-8")
    return HTMLResponse(_inject_help(html, content))


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    content = (
        "Use this page for read-only reference of schemas, endpoints, and models. "
        "All API calls still require X-API-Key when sent from your client."
    )
    html = get_redoc_html(
        openapi_url=app.openapi_url,
        title="BayesianQC API Reference",
    ).body.decode("utf-8")
    return HTMLResponse(_inject_help(html, content))


def normalize_units(value: float, units: str, config: StreamConfig) -> tuple[float, str]:
    if units == config.units:
        return value, units
    if config.unit_conversions and units in config.unit_conversions:
        conversion = config.unit_conversions[units]
        if isinstance(conversion, dict):
            factor = float(conversion.get("factor", 1.0))
            offset = float(conversion.get("offset", 0.0))
        else:
            factor = float(conversion)
            offset = 0.0
        return value * factor + offset, config.units
    if config.allowed_units and units in config.allowed_units and units == config.units:
        return value, units
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Units do not match stream configuration")


def parse_csv_row(row: dict) -> QCRecordIn:
    cleaned = {key: value for key, value in row.items() if value not in ("", None)}
    if "flags" in cleaned:
        try:
            cleaned["flags"] = json.loads(cleaned["flags"])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid flags JSON: {cleaned['flags']}") from exc
    return QCRecordIn.model_validate(cleaned)


def validate_bounds(value: float, config: StreamConfig) -> None:
    if config.min_value is not None and value < config.min_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Result below configured minimum")
    if config.max_value is not None and value > config.max_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Result above configured maximum")


def determine_disposition(signals: list, risk_score: int, config: StreamConfig) -> str:
    if any(s.severity == "action" for s in signals):
        return "reject"
    if risk_score >= config.risk_threshold_hold:
        return "hold-for-review"
    if signals or risk_score >= config.risk_threshold_warn:
        return "monitor"
    return "accept"


def alert_severity(signals: list, risk_score: int, config: StreamConfig) -> str:
    if any(s.severity == "action" for s in signals) or risk_score >= config.risk_threshold_hold:
        return "action"
    if signals or risk_score >= config.risk_threshold_warn:
        return "warn"
    return "info"


def _audit_out(entry) -> AuditEntryOut:
    return AuditEntryOut(
        timestamp=entry.timestamp,
        actor=entry.actor,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=entry.after,
        reason=entry.reason,
    )


def _alert_out(alert: AlertRecord) -> AlertOut:
    acknowledged = alert.status in {AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED}
    return AlertOut(
        id=alert.alert_id,
        stream_id=alert.stream_id,
        created_at=alert.created_at,
        signals=alert.signals,
        bayesian_risk=alert.bayesian_risk,
        disposition=alert.disposition,
        acknowledged=acknowledged,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        due_at=alert.due_at,
    )


def _stream_out(config: StreamConfig) -> StreamConfigOut:
    return StreamConfigOut(**config.model_dump())


def _instrument_out(instrument: Instrument) -> InstrumentOut:
    return InstrumentOut(**instrument.model_dump())


def _method_out(method: Method) -> MethodOut:
    return MethodOut(**method.model_dump())


def _analyte_out(analyte: Analyte) -> AnalyteOut:
    return AnalyteOut(**analyte.model_dump())


def _prior_out(config) -> PriorConfigOut:
    return PriorConfigOut(**config.model_dump())


def _event_out(event: QCEvent) -> QCEventOut:
    return QCEventOut(
        id=event.id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        stream_id=event.stream_id,
        instrument_id=event.instrument_id,
        analyte=event.analyte,
        method_id=event.method_id,
        metadata=event.event_metadata,
        created_at=event.created_at,
        created_by=event.created_by,
    )


def _investigation_out(investigation: Investigation, alert_id: Optional[str] = None) -> InvestigationOut:
    return InvestigationOut(
        id=investigation.id,
        status=investigation.status,
        problem_statement=investigation.problem_statement,
        suspected_cause=investigation.suspected_cause,
        containment=investigation.containment,
        data_reviewed=investigation.data_reviewed,
        outcome=investigation.outcome,
        decision=investigation.decision,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
        created_by=investigation.created_by,
        alert_id=alert_id,
    )


def _capa_out(capa: Capa, alert_id: Optional[str] = None, investigation_id: Optional[int] = None) -> CapaOut:
    return CapaOut(
        id=capa.id,
        status=capa.status,
        root_cause_category=capa.root_cause_category,
        corrective_actions=capa.corrective_actions,
        preventive_actions=capa.preventive_actions,
        owners=capa.owners,
        due_at=capa.due_at,
        verification_plan=capa.verification_plan,
        effectiveness_criteria=capa.effectiveness_criteria,
        created_at=capa.created_at,
        updated_at=capa.updated_at,
        created_by=capa.created_by,
        alert_id=alert_id,
        investigation_id=investigation_id,
    )


def _investigation_alert_id(session: Session, investigation_id: int) -> Optional[str]:
    link = session.exec(
        select(InvestigationAlertLink).where(InvestigationAlertLink.investigation_id == investigation_id)
    ).first()
    if not link:
        return None
    alert = session.exec(select(AlertRecord).where(AlertRecord.id == link.alert_id)).first()
    return alert.alert_id if alert else None


def _capa_links(session: Session, capa_id: int) -> tuple[Optional[str], Optional[int]]:
    link = session.exec(select(CapaLink).where(CapaLink.capa_id == capa_id)).first()
    if not link:
        return None, None
    alert_id = None
    if link.alert_id:
        alert = session.exec(select(AlertRecord).where(AlertRecord.id == link.alert_id)).first()
        alert_id = alert.alert_id if alert else None
    return alert_id, link.investigation_id


def validate_capa_fields(payload: CapaIn) -> None:
    if payload.root_cause_category is None:
        raise HTTPException(status_code=422, detail="root_cause_category is required for CAPA approval")
    if not payload.corrective_actions:
        raise HTTPException(status_code=422, detail="corrective_actions are required for CAPA approval")
    if not payload.preventive_actions:
        raise HTTPException(status_code=422, detail="preventive_actions are required for CAPA approval")
    if not payload.owners:
        raise HTTPException(status_code=422, detail="owners are required for CAPA approval")
    if payload.due_at is None:
        raise HTTPException(status_code=422, detail="due_at is required for CAPA approval")
    if payload.verification_plan is None:
        raise HTTPException(status_code=422, detail="verification_plan is required for CAPA approval")


def process_ingestion(
    payload: QCRecordIn,
    session: Session,
    user: UserContext,
    idempotency_key: Optional[str],
) -> IngestionResult:
    record_time = payload.timestamp
    config = get_active_stream_config(session, payload.stream_id, record_time)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not configured")

    if payload.qc_level != config.qc_level:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="QC level does not match stream configuration")

    normalized_value, normalized_units = normalize_units(payload.result_value, payload.units, config)
    validate_bounds(normalized_value, config)

    record = QCRecord(
        stream_id=payload.stream_id,
        timestamp=payload.timestamp,
        result_value=normalized_value,
        analyte=payload.analyte,
        qc_level=payload.qc_level,
        instrument_id=payload.instrument_id,
        method_id=payload.method_id,
        operator_id=payload.operator_id,
        reagent_lot=payload.reagent_lot,
        control_material_lot=payload.control_material_lot,
        calibration_status=payload.calibration_status,
        run_id=payload.run_id,
        units=normalized_units,
        flags=payload.flags,
        entry_source=payload.entry_source,
        comments=payload.comments,
        raw_payload=payload.model_dump(mode="json"),
        duplicate_status=DuplicateStatus.UNIQUE,
        idempotency_key=idempotency_key,
    )

    duplicate_status = detect_duplicate(session, record)
    record.duplicate_status = duplicate_status
    session.add(record)
    session.commit()
    session.refresh(record)

    signals = frequentist.evaluate_rules(
        session,
        record.result_value,
        record.timestamp,
        record.stream_id,
        config,
    )
    risk = bayesian.infer_risk(
        session,
        record.result_value,
        record.timestamp,
        record.stream_id,
        config,
    )
    disposition = determine_disposition(signals, risk.risk_score, config)

    record_payload = payload.model_copy(update={"result_value": normalized_value, "units": normalized_units})
    qc_out = QCRecordOut(record=record_payload, signals=signals, bayesian_risk=risk, disposition=disposition)

    audit_entry = record_audit(
        session=session,
        actor=user.role.value,
        action="ingest_qc",
        entity_type="qc_record",
        entity_id=str(record.id),
        before=None,
        after=qc_out.model_dump(mode="json"),
        reason=payload.comments,
    )

    alert_out = None
    if signals or risk.risk_score >= config.risk_threshold_warn:
        alert_record = create_alert(
            session,
            AlertRecord(
                alert_id=str(uuid4()),
                stream_id=record.stream_id,
                qc_record_id=record.id,
                severity=alert_severity(signals, risk.risk_score, config),
                disposition=disposition,
                signals=[s.model_dump(mode="json") for s in signals],
                bayesian_risk=risk.model_dump(mode="json"),
            ),
        )
        alert_out = _alert_out(alert_record)

    result = IngestionResult(
        status="accepted",
        duplicate=duplicate_status,
        qc=qc_out,
        alert_created=alert_out,
        audit_entry=_audit_out(audit_entry),
        idempotency_key=idempotency_key,
    )
    store_receipt(session, idempotency_key, result.model_dump(mode="json"), record.id)
    return result


@app.post("/qc/records", response_model=IngestionResult)
async def ingest_qc_record(
    payload: QCRecordIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    if idempotency_key:
        receipt = get_idempotent_response(session, idempotency_key)
        if receipt:
            return receipt.response
    return process_ingestion(payload, session, user, idempotency_key)


@app.post("/qc/records/csv")
async def ingest_qc_records_csv(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    results = []
    errors = []
    for idx, row in enumerate(reader, start=1):
        try:
            payload = parse_csv_row(row)
            results.append(process_ingestion(payload, session, user, idempotency_key=None).model_dump())
        except Exception as exc:  # noqa: BLE001 - report row-level errors
            errors.append({"row": idx, "error": str(exc)})
    return {"accepted": len(results), "errors": errors, "results": results}


@app.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(Instrument).order_by(Instrument.name.asc())
    if active is not None:
        query = query.where(Instrument.active == active)
    instruments = session.exec(query).all()
    return [_instrument_out(instrument) for instrument in instruments]


@app.post("/instruments", response_model=InstrumentOut)
async def create_instrument(
    payload: InstrumentIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    instrument = Instrument(**payload.model_dump(), created_by=user.role.value)
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    record_audit(
        session,
        actor=user.role.value,
        action="create_instrument",
        entity_type="instrument",
        entity_id=str(instrument.id),
        before=None,
        after=instrument.model_dump(mode="json"),
        reason=None,
    )
    return _instrument_out(instrument)


@app.patch("/instruments/{instrument_id}", response_model=InstrumentOut)
async def update_instrument(
    instrument_id: int,
    payload: InstrumentUpdate,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    instrument = session.exec(select(Instrument).where(Instrument.id == instrument_id)).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    before = instrument.model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(instrument, field, value)
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    record_audit(
        session,
        actor=user.role.value,
        action="update_instrument",
        entity_type="instrument",
        entity_id=str(instrument.id),
        before=before,
        after=instrument.model_dump(mode="json"),
        reason=None,
    )
    return _instrument_out(instrument)


@app.get("/methods", response_model=list[MethodOut])
async def list_methods(
    instrument_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(Method).order_by(Method.name.asc())
    if instrument_id is not None:
        query = query.where(Method.instrument_id == instrument_id)
    if active is not None:
        query = query.where(Method.active == active)
    methods = session.exec(query).all()
    return [_method_out(method) for method in methods]


@app.post("/methods", response_model=MethodOut)
async def create_method(
    payload: MethodIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    instrument = session.exec(select(Instrument).where(Instrument.id == payload.instrument_id)).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    method = Method(**payload.model_dump(), created_by=user.role.value)
    session.add(method)
    session.commit()
    session.refresh(method)
    record_audit(
        session,
        actor=user.role.value,
        action="create_method",
        entity_type="method",
        entity_id=str(method.id),
        before=None,
        after=method.model_dump(mode="json"),
        reason=None,
    )
    return _method_out(method)


@app.patch("/methods/{method_id}", response_model=MethodOut)
async def update_method(
    method_id: int,
    payload: MethodUpdate,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    method = session.exec(select(Method).where(Method.id == method_id)).first()
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    if payload.instrument_id is not None:
        instrument = session.exec(select(Instrument).where(Instrument.id == payload.instrument_id)).first()
        if not instrument:
            raise HTTPException(status_code=404, detail="Instrument not found")
    before = method.model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(method, field, value)
    session.add(method)
    session.commit()
    session.refresh(method)
    record_audit(
        session,
        actor=user.role.value,
        action="update_method",
        entity_type="method",
        entity_id=str(method.id),
        before=before,
        after=method.model_dump(mode="json"),
        reason=None,
    )
    return _method_out(method)


@app.get("/analytes", response_model=list[AnalyteOut])
async def list_analytes(
    method_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(Analyte).order_by(Analyte.name.asc())
    if method_id is not None:
        query = query.where(Analyte.method_id == method_id)
    if active is not None:
        query = query.where(Analyte.active == active)
    analytes = session.exec(query).all()
    return [_analyte_out(analyte) for analyte in analytes]


@app.post("/analytes", response_model=AnalyteOut)
async def create_analyte(
    payload: AnalyteIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    method = session.exec(select(Method).where(Method.id == payload.method_id)).first()
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    analyte = Analyte(**payload.model_dump(), created_by=user.role.value)
    session.add(analyte)
    session.commit()
    session.refresh(analyte)
    record_audit(
        session,
        actor=user.role.value,
        action="create_analyte",
        entity_type="analyte",
        entity_id=str(analyte.id),
        before=None,
        after=analyte.model_dump(mode="json"),
        reason=None,
    )
    return _analyte_out(analyte)


@app.patch("/analytes/{analyte_id}", response_model=AnalyteOut)
async def update_analyte(
    analyte_id: int,
    payload: AnalyteUpdate,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    analyte = session.exec(select(Analyte).where(Analyte.id == analyte_id)).first()
    if not analyte:
        raise HTTPException(status_code=404, detail="Analyte not found")
    if payload.method_id is not None:
        method = session.exec(select(Method).where(Method.id == payload.method_id)).first()
        if not method:
            raise HTTPException(status_code=404, detail="Method not found")
    before = analyte.model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(analyte, field, value)
    session.add(analyte)
    session.commit()
    session.refresh(analyte)
    record_audit(
        session,
        actor=user.role.value,
        action="update_analyte",
        entity_type="analyte",
        entity_id=str(analyte.id),
        before=before,
        after=analyte.model_dump(mode="json"),
        reason=None,
    )
    return _analyte_out(analyte)


@app.get("/streams", response_model=list[StreamConfigOut])
async def list_streams(
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    configs = session.exec(
        select(StreamConfig).order_by(StreamConfig.stream_id, StreamConfig.effective_from.desc(), StreamConfig.version.desc())
    ).all()
    latest = {}
    for cfg in configs:
        if cfg.stream_id not in latest:
            latest[cfg.stream_id] = cfg
    return [_stream_out(cfg) for cfg in latest.values()]


@app.get("/streams/{stream_id}/configs", response_model=list[StreamConfigOut])
async def list_stream_versions(
    stream_id: str,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    return [_stream_out(cfg) for cfg in list_stream_configs(session, stream_id)]


@app.post("/streams", response_model=StreamConfigOut)
async def create_stream(
    payload: StreamConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    config = create_stream_config(session, payload, user.role.value)
    record_audit(
        session,
        actor=user.role.value,
        action="create_stream",
        entity_type="stream_config",
        entity_id=str(config.id),
        before=None,
        after=config.model_dump(mode="json"),
        reason=None,
    )
    return _stream_out(config)


@app.post("/streams/{stream_id}/configs", response_model=StreamConfigOut)
async def create_stream_version(
    stream_id: str,
    payload: StreamConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    payload = payload.model_copy(update={"stream_id": stream_id})
    config = create_stream_config(session, payload, user.role.value)
    record_audit(
        session,
        actor=user.role.value,
        action="create_stream_version",
        entity_type="stream_config",
        entity_id=str(config.id),
        before=None,
        after=config.model_dump(mode="json"),
        reason=None,
    )
    return _stream_out(config)


@app.post("/streams/{stream_id}/priors", response_model=PriorConfigOut)
async def create_prior(
    stream_id: str,
    payload: PriorConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    payload = payload.model_copy(update={"stream_id": stream_id})
    config = create_prior_config(session, stream_id, payload, user.role.value)
    record_audit(
        session,
        actor=user.role.value,
        action="create_prior",
        entity_type="prior_config",
        entity_id=str(config.id),
        before=None,
        after=config.model_dump(mode="json"),
        reason=None,
    )
    return _prior_out(config)


@app.get("/streams/{stream_id}/priors", response_model=list[PriorConfigOut])
async def list_priors(
    stream_id: str,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    priors = session.exec(
        select(PriorConfig).where(PriorConfig.stream_id == stream_id).order_by(PriorConfig.version.desc())
    ).all()
    return [_prior_out(prior) for prior in priors]


@app.post("/qc/events", response_model=QCEventOut)
async def ingest_event(
    payload: QCEventIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    event = create_event(
        session,
        QCEvent(
            stream_id=payload.stream_id,
            event_type=payload.event_type,
            timestamp=payload.timestamp,
            instrument_id=payload.instrument_id,
            analyte=payload.analyte,
            method_id=payload.method_id,
            event_metadata=payload.metadata,
            created_by=user.role.value,
        ),
    )
    record_audit(
        session,
        actor=user.role.value,
        action="ingest_event",
        entity_type="qc_event",
        entity_id=str(event.id),
        before=None,
        after=event.model_dump(mode="json"),
        reason=None,
    )
    return _event_out(event)


@app.get("/qc/events", response_model=list[QCEventOut])
async def list_events(
    stream_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(QCEvent).order_by(QCEvent.timestamp.desc())
    if stream_id:
        query = query.where(QCEvent.stream_id == stream_id)
    if event_type:
        query = query.where(QCEvent.event_type == event_type)
    events = session.exec(query.limit(limit)).all()
    return [_event_out(event) for event in events]


@app.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    alerts = session.exec(select(AlertRecord).order_by(AlertRecord.created_at.desc())).all()
    return [_alert_out(alert) for alert in alerts]


@app.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert_status(
    alert_id: str,
    payload: AlertUpdate,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == alert_id)).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    before = alert.model_dump(mode="json")
    if payload.status:
        alert.status = payload.status
    if payload.acknowledged_by:
        alert.acknowledged_by = payload.acknowledged_by
        alert.acknowledged_at = datetime.now(timezone.utc)
    if payload.assigned_to:
        alert.assigned_to = payload.assigned_to
    if payload.due_at:
        alert.due_at = payload.due_at
    alert = update_alert(session, alert)
    record_audit(
        session,
        actor=user.role.value,
        action="update_alert",
        entity_type="alert",
        entity_id=alert.alert_id,
        before=before,
        after=alert.model_dump(mode="json"),
        reason=None,
    )
    return _alert_out(alert)


@app.get("/investigations", response_model=list[InvestigationOut])
async def list_investigations(
    status_filter: Optional[str] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(Investigation).order_by(Investigation.created_at.desc())
    if status_filter:
        query = query.where(Investigation.status == status_filter)
    investigations = session.exec(query).all()
    results = []
    for investigation in investigations:
        alert_id = _investigation_alert_id(session, investigation.id)
        results.append(_investigation_out(investigation, alert_id=alert_id))
    return results


@app.post("/investigations", response_model=InvestigationOut)
async def create_investigation_record(
    payload: InvestigationIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    alert_id = None
    alert_id_str = None
    if payload.alert_id:
        alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == payload.alert_id)).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert_id = alert.id
        alert_id_str = alert.alert_id
    investigation = create_investigation(
        session,
        Investigation(
            problem_statement=payload.problem_statement,
            suspected_cause=payload.suspected_cause,
            containment=payload.containment,
            data_reviewed=payload.data_reviewed,
            outcome=payload.outcome,
            decision=payload.decision,
            status=payload.status or InvestigationStatus.OPEN,
            created_by=user.role.value,
        ),
        alert_id=alert_id,
    )
    record_audit(
        session,
        actor=user.role.value,
        action="create_investigation",
        entity_type="investigation",
        entity_id=str(investigation.id),
        before=None,
        after=investigation.model_dump(mode="json"),
        reason=None,
    )
    return _investigation_out(investigation, alert_id=alert_id_str)


@app.patch("/investigations/{investigation_id}", response_model=InvestigationOut)
async def update_investigation_record(
    investigation_id: int,
    payload: InvestigationIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    investigation = session.exec(select(Investigation).where(Investigation.id == investigation_id)).first()
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    before = investigation.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id"})
    for field, value in updates.items():
        setattr(investigation, field, value)
    investigation = update_investigation(session, investigation)
    record_audit(
        session,
        actor=user.role.value,
        action="update_investigation",
        entity_type="investigation",
        entity_id=str(investigation.id),
        before=before,
        after=investigation.model_dump(mode="json"),
        reason=None,
    )
    alert_id_str = _investigation_alert_id(session, investigation.id)
    return _investigation_out(investigation, alert_id=alert_id_str)


@app.post("/capas", response_model=CapaOut)
async def create_capa_record(
    payload: CapaIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    if payload.status and payload.status != CapaStatus.DRAFT:
        validate_capa_fields(payload)
    alert_id = None
    alert_id_str = None
    if payload.alert_id:
        alert = session.exec(select(AlertRecord).where(AlertRecord.alert_id == payload.alert_id)).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert_id = alert.id
        alert_id_str = alert.alert_id
    investigation_id = payload.investigation_id
    if investigation_id:
        existing = session.exec(select(Investigation).where(Investigation.id == investigation_id)).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Investigation not found")
    capa = create_capa(
        session,
        Capa(
            status=payload.status or CapaStatus.DRAFT,
            root_cause_category=payload.root_cause_category,
            corrective_actions=payload.corrective_actions,
            preventive_actions=payload.preventive_actions,
            owners=payload.owners,
            due_at=payload.due_at,
            verification_plan=payload.verification_plan,
            effectiveness_criteria=payload.effectiveness_criteria,
            created_by=user.role.value,
        ),
        alert_id=alert_id,
        investigation_id=investigation_id,
    )
    record_audit(
        session,
        actor=user.role.value,
        action="create_capa",
        entity_type="capa",
        entity_id=str(capa.id),
        before=None,
        after=capa.model_dump(mode="json"),
        reason=None,
    )
    return _capa_out(capa, alert_id=alert_id_str, investigation_id=investigation_id)


@app.patch("/capas/{capa_id}", response_model=CapaOut)
async def update_capa_record(
    capa_id: int,
    payload: CapaIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    capa = session.exec(select(Capa).where(Capa.id == capa_id)).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    before = capa.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id", "investigation_id"})
    for field, value in updates.items():
        setattr(capa, field, value)
    merged = capa.model_dump()
    if merged.get("status") != CapaStatus.DRAFT:
        payload_data = {key: merged.get(key) for key in CapaIn.model_fields.keys()}
        validate_capa_fields(CapaIn(**payload_data))
    capa = update_capa(session, capa)
    record_audit(
        session,
        actor=user.role.value,
        action="update_capa",
        entity_type="capa",
        entity_id=str(capa.id),
        before=before,
        after=capa.model_dump(mode="json"),
        reason=None,
    )
    alert_id_str, investigation_id = _capa_links(session, capa.id)
    return _capa_out(capa, alert_id=alert_id_str, investigation_id=investigation_id)


@app.get("/capas", response_model=list[CapaOut])
async def list_capas(
    status_filter: Optional[str] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    query = select(Capa).order_by(Capa.created_at.desc())
    if status_filter:
        query = query.where(Capa.status == status_filter)
    capas = session.exec(query).all()
    results = []
    for capa in capas:
        alert_id, investigation_id = _capa_links(session, capa.id)
        results.append(_capa_out(capa, alert_id=alert_id, investigation_id=investigation_id))
    return results


@app.get("/audit", response_model=list[AuditEntryOut])
async def list_audit(
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    entries = session.exec(select(AuditEntry).order_by(AuditEntry.timestamp.desc())).all()
    return [_audit_out(entry) for entry in entries]


@app.get("/reports/summary")
async def report_summary(
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    alert_counts = session.exec(select(AlertRecord)).all()
    investigation_counts = session.exec(select(Investigation)).all()
    capa_counts = session.exec(select(Capa)).all()
    return {
        "alerts": {
            "total": len(alert_counts),
            "open": len([a for a in alert_counts if a.status == AlertStatus.OPEN]),
            "acknowledged": len([a for a in alert_counts if a.status == AlertStatus.ACKNOWLEDGED]),
        },
        "investigations": {
            "total": len(investigation_counts),
            "open": len([i for i in investigation_counts if i.status != InvestigationStatus.CLOSED]),
        },
        "capas": {
            "total": len(capa_counts),
            "open": len([c for c in capa_counts if c.status not in {CapaStatus.CLOSED, CapaStatus.DRAFT}]),
        },
    }


@app.get("/streams/{stream_id}/chart")
async def stream_chart(
    stream_id: str,
    limit: int = 200,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    record_query = select(QCRecord).where(QCRecord.stream_id == stream_id)
    if start:
        record_query = record_query.where(QCRecord.timestamp >= start)
    if end:
        record_query = record_query.where(QCRecord.timestamp <= end)
    records = session.exec(record_query.order_by(QCRecord.timestamp.desc()).limit(limit)).all()

    event_query = select(QCEvent).where(QCEvent.stream_id == stream_id)
    if start:
        event_query = event_query.where(QCEvent.timestamp >= start)
    if end:
        event_query = event_query.where(QCEvent.timestamp <= end)
    events = session.exec(event_query.order_by(QCEvent.timestamp.desc()).limit(limit)).all()

    alert_query = select(AlertRecord).where(AlertRecord.stream_id == stream_id)
    if start:
        alert_query = alert_query.where(AlertRecord.created_at >= start)
    if end:
        alert_query = alert_query.where(AlertRecord.created_at <= end)
    alerts = session.exec(alert_query.order_by(AlertRecord.created_at.desc()).limit(limit)).all()
    return {
        "records": [r.model_dump(mode="json") for r in records[::-1]],
        "events": [e.model_dump(mode="json") for e in events[::-1]],
        "alerts": [a.model_dump(mode="json") for a in alerts[::-1]],
    }
