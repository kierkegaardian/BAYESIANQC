from __future__ import annotations

import csv
import json
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import StringIO
from typing import NoReturn, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.api_models import (
    AlertSummary,
    CapaSummary,
    CsvIngestResult,
    CsvRowError,
    InvestigationSummary,
    LotSegmentOut,
    QCRecordChartOut,
    ReportSummaryOut,
    StreamChartOut,
)
from app.api_errors import json_safe_request_validation_handler
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
    QCRecordQuarantine,
    StreamConfig,
)
from app.domain import Disposition
from app.evaluation_models import EvaluationTrigger
from app.evaluations import reprocess_stream_evaluations
from app.math.prior import prior_beta_from_sigma
from app.models import (
    AnalyteIn,
    AnalyteOut,
    AnalyteUpdate,
    AlertOut,
    AlertStatus,
    AlertUpdate,
    AuditEntryOut,
    BayesianRisk,
    CapaIn,
    CapaOut,
    CapaStatus,
    CurrentUserOut,
    EventType,
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
    QCRecordResolutionIn,
    QCRecordResolutionOut,
    QCRecordQuarantineOut,
    FrequentistSignal,
    QuarantineResult,
    QuarantineReviewIn,
    QuarantineStatus,
    StreamConfigIn,
    StreamConfigOut,
)
from app.rbac import ROLE_PERMISSIONS, UserContext, require_permission
from app.routers.control_materials import router as control_materials_router
from app.routers.evaluation_reprocess import router as evaluation_reprocess_router
from app.routers.imports import router as imports_router
from app.routers.kiosks import router as kiosks_router
from app.routers.qc_backlog import router as qc_backlog_router
from app.routers.qc_comments import router as qc_comments_router
from app.routers.stream_setups import router as stream_setups_router
from app.services.ingestion import audit_out as _audit_out
from app.services.ingestion import alert_out as _alert_out
from app.services.ingestion import process_ingestion
from app.services.access_scopes import (
    effective_scope,
    require_alert_access,
    require_record_access,
    require_stream_access,
    require_stream_context_access,
    scope_summary_for_me,
    stream_is_accessible,
    stream_scope_predicate,
)
from app.services.locks import stream_write_lock
from app.services.evaluation_provenance import record_evaluation_provenance
from app.services.evaluation_pending import historical_reprocess_required
from app.services.quarantine import quarantine_out
from app.storage import (
    create_capa,
    create_event,
    create_investigation,
    create_prior_config,
    create_stream_config,
    list_stream_configs,
    record_audit,
    seed_defaults,
    update_alert,
    update_capa,
    update_investigation,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    with Session(get_engine()) as session:
        seed_defaults(session)
    yield


app = FastAPI(title="Bayesian QC Prototype", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_exception_handler(RequestValidationError, json_safe_request_validation_handler)

cors_origins = [
    origin.strip()
    for origin in os.getenv("BAYESIANQC_CORS_ORIGINS", "http://localhost:5177,http://127.0.0.1:5177").split(",")
    if origin.strip()
]
cors_origin_regex = os.getenv("BAYESIANQC_CORS_ORIGIN_REGEX")
if cors_origin_regex is None:
    cors_origin_regex = (
        r"^http://(localhost|127\.0\.0\.1|"
        r"10\.\d+\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+|"
        r"172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+):5177$"
    )
elif not cors_origin_regex.strip():
    cors_origin_regex = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(control_materials_router)
app.include_router(evaluation_reprocess_router)
app.include_router(imports_router)
app.include_router(kiosks_router)
app.include_router(qc_backlog_router)
app.include_router(qc_comments_router)
app.include_router(stream_setups_router)


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
        "interactive docs and remember to send an X-API-Key header. Local demos can seed local-dev-key "
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
    <p>All API calls require <code>X-API-Key</code>. Local demos can seed <code>local-dev-key</code>.</p>
  </body>
</html>
"""
    return HTMLResponse(_inject_help(html, content))


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    content = (
        "Use Swagger UI to explore endpoints and send requests. Click a route, choose "
        "'Try it out', and add the X-API-Key header before executing."
    )
    openapi_url = app.openapi_url
    if openapi_url is None:
        raise RuntimeError("OpenAPI URL is not configured")
    html = get_swagger_ui_html(
        openapi_url=openapi_url,
        title="BayesianQC API Docs",
    ).body.decode("utf-8")
    return HTMLResponse(_inject_help(html, content))


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    content = (
        "Use this page for read-only reference of schemas, endpoints, and models. "
        "All API calls still require X-API-Key when sent from your client."
    )
    openapi_url = app.openapi_url
    if openapi_url is None:
        raise RuntimeError("OpenAPI URL is not configured")
    html = get_redoc_html(
        openapi_url=openapi_url,
        title="BayesianQC API Reference",
    ).body.decode("utf-8")
    return HTMLResponse(_inject_help(html, content))


@app.get("/me", response_model=CurrentUserOut)
def current_user(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> CurrentUserOut:
    return CurrentUserOut(
        role=user.role,
        api_key_id=user.api_key_id,
        permissions=ROLE_PERMISSIONS.get(user.role, []),
        effective_scope=scope_summary_for_me(session, user),
    )


def parse_csv_row(row: dict[str, str | None]) -> QCRecordIn:
    cleaned = {key: value for key, value in row.items() if value not in ("", None)}
    if "flags" in cleaned:
        try:
            cleaned["flags"] = json.loads(cleaned["flags"])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid flags JSON: {cleaned['flags']}") from exc
    return QCRecordIn.model_validate(cleaned)


def _lot_segments(records: Sequence[QCRecord]) -> list[LotSegmentOut]:
    if not records:
        return []
    segments: list[LotSegmentOut] = []
    current_lot = records[0].control_material_lot or "unknown"
    start_time = records[0].timestamp
    last_time = records[0].timestamp
    count = 0
    for record in records:
        lot = record.control_material_lot or "unknown"
        if lot != current_lot:
            segments.append(LotSegmentOut(control_material_lot=current_lot, start=start_time, end=last_time, count=count))
            current_lot = lot
            start_time = record.timestamp
            count = 0
        count += 1
        last_time = record.timestamp
    segments.append(LotSegmentOut(control_material_lot=current_lot, start=start_time, end=last_time, count=count))
    return segments


def _stream_out(config: StreamConfig, *, reprocess_required: bool = False) -> StreamConfigOut:
    return StreamConfigOut(
        **config.model_dump(),
        evaluation_reprocess_required=reprocess_required,
    )


def _instrument_out(instrument: Instrument) -> InstrumentOut:
    return InstrumentOut(**instrument.model_dump())


def _method_out(method: Method) -> MethodOut:
    return MethodOut(**method.model_dump())


def _analyte_out(analyte: Analyte) -> AnalyteOut:
    return AnalyteOut(**analyte.model_dump())


def _prior_out(config: PriorConfig, *, reprocess_required: bool = False) -> PriorConfigOut:
    return PriorConfigOut(
        **config.model_dump(),
        evaluation_reprocess_required=reprocess_required,
    )


def _event_out(event: QCEvent) -> QCEventOut:
    if event.id is None:
        raise RuntimeError("QC event missing id")
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


def _qc_record_resolution_out(record: QCRecord) -> QCRecordResolutionOut:
    if record.id is None:
        raise RuntimeError("QC record missing id")
    return QCRecordResolutionOut(
        id=record.id,
        stream_id=record.stream_id,
        timestamp=record.timestamp,
        result_value=record.result_value,
        include_in_stats=record.include_in_stats,
        resolved_at=record.resolved_at,
        resolved_by=record.resolved_by,
        resolved_reason=record.resolved_reason,
    )


def _investigation_out(investigation: Investigation, alert_id: Optional[str] = None) -> InvestigationOut:
    if investigation.id is None:
        raise RuntimeError("Investigation missing id")
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
    if capa.id is None:
        raise RuntimeError("CAPA missing id")
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


def require_reason(value: Optional[str], detail: str) -> str:
    reason = value.strip() if value else ""
    if not reason:
        raise HTTPException(status_code=422, detail=detail)
    return reason


def raise_config_version_conflict(exc: IntegrityError) -> NoReturn:
    raise HTTPException(status_code=409, detail="Configuration version conflict; retry the request") from exc


@app.get("/qc/quarantine", response_model=list[QCRecordQuarantineOut])
def list_qc_quarantine(
    status_filter: QuarantineStatus = Query(default=QuarantineStatus.OPEN, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[QCRecordQuarantineOut]:
    query = (
        select(QCRecordQuarantine)
        .where(QCRecordQuarantine.status == status_filter)
        .order_by(col(QCRecordQuarantine.created_at).desc())
        .limit(limit)
    )
    rows = [row for row in session.exec(query).all() if stream_is_accessible(session, user, row.stream_id)]
    return [quarantine_out(row) for row in rows]


@app.patch("/qc/quarantine/{quarantine_id}", response_model=QCRecordQuarantineOut)
def review_qc_quarantine(
    quarantine_id: int,
    payload: QuarantineReviewIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
) -> QCRecordQuarantineOut:
    row = session.exec(select(QCRecordQuarantine).where(QCRecordQuarantine.id == quarantine_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Quarantine record not found")
    require_stream_access(session, user, row.stream_id)
    before = row.model_dump(mode="json")
    row.status = payload.status
    row.reviewed_at = datetime.now(timezone.utc)
    row.reviewed_by = user.actor
    row.review_reason = payload.review_reason
    session.add(row)
    session.flush()
    out = quarantine_out(row)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="review_qc_quarantine",
        entity_type="qc_quarantine",
        entity_id=str(out.id),
        before=before,
        after=out.model_dump(mode="json"),
        reason=payload.review_reason,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return quarantine_out(row)


@app.post("/qc/records", response_model=IngestionResult | QuarantineResult)
def ingest_qc_record(
    payload: QCRecordIn,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> IngestionResult | QuarantineResult:
    result = process_ingestion(payload, session, user, idempotency_key)
    if isinstance(result, QuarantineResult):
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@app.post("/qc/records/csv", response_model=CsvIngestResult)
def ingest_qc_records_csv(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> CsvIngestResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    results: list[IngestionResult | QuarantineResult] = []
    errors: list[CsvRowError] = []
    accepted = 0
    quarantined = 0
    for idx, row in enumerate(reader, start=1):
        try:
            payload = parse_csv_row(row)
            result = process_ingestion(payload, session, user, idempotency_key=None)
            results.append(result)
            if isinstance(result, QuarantineResult):
                quarantined += 1
            else:
                accepted += 1
        except Exception as exc:  # noqa: BLE001 - report row-level errors
            session.rollback()
            errors.append(CsvRowError(row=idx, error=str(exc)))
    return CsvIngestResult(accepted=accepted, quarantined=quarantined, errors=errors, results=results)


@app.patch("/qc/records/{record_id}/resolution", response_model=QCRecordResolutionOut)
def resolve_qc_record(
    record_id: int,
    payload: QCRecordResolutionIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    record = require_record_access(session, user, record_id)
    if historical_reprocess_required(session, record.stream_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A backdated configuration or prior requires administrator "
                "evaluation preview/apply before changing statistical inclusion"
            ),
        )
    with stream_write_lock(session, record.stream_id):
        try:
            session.refresh(record)
            before = record.model_dump(mode="json")
            reason = payload.resolved_reason
            if payload.include_in_stats != record.include_in_stats:
                reason = require_reason(
                    payload.resolved_reason,
                    "resolved_reason is required when changing statistical inclusion",
                )
            if payload.include_in_stats:
                record.include_in_stats = True
                record.resolved_at = None
                record.resolved_by = None
                record.resolved_reason = None
            else:
                record.include_in_stats = False
                record.resolved_at = datetime.now(timezone.utc)
                record.resolved_by = user.actor
                record.resolved_reason = reason
            session.add(record)
            session.flush()
            record_audit(
                session=session,
                actor=user.actor,
                action="resolve_qc_record",
                entity_type="qc_record",
                entity_id=str(record.id),
                before=before,
                after=record.model_dump(mode="json"),
                reason=reason,
                commit=False,
            )
            reprocess_stream_evaluations(
                session,
                record.stream_id,
                trigger=EvaluationTrigger.RECORD_RESOLUTION,
                actor=user.actor,
                reason=reason or f"Resolution update for QC record {record.id}",
                commit=False,
            )
            session.commit()
            session.refresh(record)
            return _qc_record_resolution_out(record)
        except Exception:
            session.rollback()
            raise


@app.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(Instrument).order_by(col(Instrument.name).asc())
    if active is not None:
        query = query.where(Instrument.active == active)
    instruments = session.exec(query).all()
    return [_instrument_out(instrument) for instrument in instruments]


@app.post("/instruments", response_model=InstrumentOut)
def create_instrument(
    payload: InstrumentIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    instrument = Instrument(**payload.model_dump(), created_by=user.actor)
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    record_audit(
        session,
        actor=user.actor,
        action="create_instrument",
        entity_type="instrument",
        entity_id=str(instrument.id),
        before=None,
        after=instrument.model_dump(mode="json"),
        reason=None,
    )
    return _instrument_out(instrument)


@app.patch("/instruments/{instrument_id}", response_model=InstrumentOut)
def update_instrument(
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
        actor=user.actor,
        action="update_instrument",
        entity_type="instrument",
        entity_id=str(instrument.id),
        before=before,
        after=instrument.model_dump(mode="json"),
        reason=None,
    )
    return _instrument_out(instrument)


@app.get("/methods", response_model=list[MethodOut])
def list_methods(
    instrument_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(Method).order_by(col(Method.name).asc())
    if instrument_id is not None:
        query = query.where(Method.instrument_id == instrument_id)
    if active is not None:
        query = query.where(Method.active == active)
    methods = session.exec(query).all()
    return [_method_out(method) for method in methods]


@app.post("/methods", response_model=MethodOut)
def create_method(
    payload: MethodIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    instrument = session.exec(select(Instrument).where(Instrument.id == payload.instrument_id)).first()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    method = Method(**payload.model_dump(), created_by=user.actor)
    session.add(method)
    session.commit()
    session.refresh(method)
    record_audit(
        session,
        actor=user.actor,
        action="create_method",
        entity_type="method",
        entity_id=str(method.id),
        before=None,
        after=method.model_dump(mode="json"),
        reason=None,
    )
    return _method_out(method)


@app.patch("/methods/{method_id}", response_model=MethodOut)
def update_method(
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
        actor=user.actor,
        action="update_method",
        entity_type="method",
        entity_id=str(method.id),
        before=before,
        after=method.model_dump(mode="json"),
        reason=None,
    )
    return _method_out(method)


@app.get("/analytes", response_model=list[AnalyteOut])
def list_analytes(
    method_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(Analyte).order_by(col(Analyte.name).asc())
    if method_id is not None:
        query = query.where(Analyte.method_id == method_id)
    if active is not None:
        query = query.where(Analyte.active == active)
    analytes = session.exec(query).all()
    return [_analyte_out(analyte) for analyte in analytes]


@app.post("/analytes", response_model=AnalyteOut)
def create_analyte(
    payload: AnalyteIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    method = session.exec(select(Method).where(Method.id == payload.method_id)).first()
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    analyte = Analyte(**payload.model_dump(), created_by=user.actor)
    session.add(analyte)
    session.commit()
    session.refresh(analyte)
    record_audit(
        session,
        actor=user.actor,
        action="create_analyte",
        entity_type="analyte",
        entity_id=str(analyte.id),
        before=None,
        after=analyte.model_dump(mode="json"),
        reason=None,
    )
    return _analyte_out(analyte)


@app.patch("/analytes/{analyte_id}", response_model=AnalyteOut)
def update_analyte(
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
        actor=user.actor,
        action="update_analyte",
        entity_type="analyte",
        entity_id=str(analyte.id),
        before=before,
        after=analyte.model_dump(mode="json"),
        reason=None,
    )
    return _analyte_out(analyte)


@app.get("/streams", response_model=list[StreamConfigOut])
def list_streams(
    site: Optional[str] = None,
    lab_bench: Optional[str] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    scope = effective_scope(session, user)
    query = select(StreamConfig).where(stream_scope_predicate(scope))
    if site:
        query = query.where(StreamConfig.site == site)
    if lab_bench:
        query = query.where(StreamConfig.lab_bench == lab_bench)
    configs = session.exec(
        query.order_by(
            col(StreamConfig.stream_id),
            col(StreamConfig.effective_from).desc(),
            col(StreamConfig.version).desc(),
        )
    ).all()
    latest = {}
    for cfg in configs:
        if cfg.stream_id not in latest:
            latest[cfg.stream_id] = cfg
    return [
        _stream_out(
            cfg,
            reprocess_required=historical_reprocess_required(session, cfg.stream_id),
        )
        for cfg in latest.values()
    ]


@app.get("/streams/{stream_id}/configs", response_model=list[StreamConfigOut])
def list_stream_versions(
    stream_id: str,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id)
    required = historical_reprocess_required(session, stream_id)
    return [
        _stream_out(cfg, reprocess_required=required)
        for cfg in list_stream_configs(session, stream_id)
    ]


@app.post("/streams", response_model=StreamConfigOut)
def create_stream(
    payload: StreamConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    require_stream_context_access(
        session,
        user,
        stream_id=payload.stream_id,
        site=payload.site,
        lab_bench=payload.lab_bench,
    )
    with stream_write_lock(session, payload.stream_id):
        try:
            config = create_stream_config(session, payload, user.actor, commit=False)
            record_audit(
                session,
                actor=user.actor,
                action="create_stream",
                entity_type="stream_config",
                entity_id=str(config.id),
                before=None,
                after=config.model_dump(mode="json"),
                reason=None,
                commit=False,
            )
            session.commit()
            session.refresh(config)
            return _stream_out(
                config,
                reprocess_required=historical_reprocess_required(session, config.stream_id),
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except IntegrityError as exc:
            session.rollback()
            raise_config_version_conflict(exc)
        except Exception:
            session.rollback()
            raise


@app.post("/streams/{stream_id}/configs", response_model=StreamConfigOut)
def create_stream_version(
    stream_id: str,
    payload: StreamConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id, hide=False)
    payload = payload.model_copy(update={"stream_id": stream_id})
    require_stream_context_access(
        session,
        user,
        stream_id=payload.stream_id,
        site=payload.site,
        lab_bench=payload.lab_bench,
    )
    with stream_write_lock(session, stream_id):
        try:
            config = create_stream_config(session, payload, user.actor, commit=False)
            record_audit(
                session,
                actor=user.actor,
                action="create_stream_version",
                entity_type="stream_config",
                entity_id=str(config.id),
                before=None,
                after=config.model_dump(mode="json"),
                reason=None,
                commit=False,
            )
            session.commit()
            session.refresh(config)
            return _stream_out(
                config,
                reprocess_required=historical_reprocess_required(session, config.stream_id),
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except IntegrityError as exc:
            session.rollback()
            raise_config_version_conflict(exc)
        except Exception:
            session.rollback()
            raise


@app.post("/streams/{stream_id}/priors", response_model=PriorConfigOut)
def create_prior(
    stream_id: str,
    payload: PriorConfigIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id, hide=False)
    payload = payload.model_copy(update={"stream_id": stream_id})
    with stream_write_lock(session, stream_id):
        try:
            if payload.beta0 is None:
                effective_at = payload.effective_from or datetime.now(timezone.utc)
                effective_config = session.exec(
                    select(StreamConfig)
                    .where(StreamConfig.stream_id == stream_id, StreamConfig.effective_from <= effective_at)
                    .order_by(col(StreamConfig.effective_from).desc(), col(StreamConfig.version).desc())
                ).first()
                if effective_config is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="beta0 is required when no stream configuration is effective at the prior timestamp",
                    )
                payload = payload.model_copy(
                    update={"beta0": prior_beta_from_sigma(payload.alpha0, effective_config.sigma)}
                )
            config = create_prior_config(session, stream_id, payload, user.actor, commit=False)
            record_audit(
                session,
                actor=user.actor,
                action="create_prior",
                entity_type="prior_config",
                entity_id=str(config.id),
                before=None,
                after=config.model_dump(mode="json"),
                reason=None,
                commit=False,
            )
            session.commit()
            session.refresh(config)
            return _prior_out(
                config,
                reprocess_required=historical_reprocess_required(session, stream_id),
            )
        except IntegrityError as exc:
            session.rollback()
            raise_config_version_conflict(exc)
        except Exception:
            session.rollback()
            raise


@app.get("/streams/{stream_id}/priors", response_model=list[PriorConfigOut])
def list_priors(
    stream_id: str,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id)
    priors = session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(col(PriorConfig.version).desc())
    ).all()
    required = historical_reprocess_required(session, stream_id)
    return [_prior_out(prior, reprocess_required=required) for prior in priors]


@app.post("/qc/events", response_model=QCEventOut)
def ingest_event(
    payload: QCEventIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    if payload.stream_id is not None:
        require_stream_access(session, user, payload.stream_id, hide=False)
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
            created_by=user.actor,
        ),
    )
    record_audit(
        session,
        actor=user.actor,
        action="ingest_event",
        entity_type="qc_event",
        entity_id=str(event.id),
        before=None,
        after=event.model_dump(mode="json"),
        reason=None,
    )
    return _event_out(event)


@app.get("/qc/events", response_model=list[QCEventOut])
def list_events(
    stream_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    limit: int = 200,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(QCEvent).order_by(col(QCEvent.timestamp).desc())
    if stream_id:
        require_stream_access(session, user, stream_id)
        query = query.where(QCEvent.stream_id == stream_id)
    if event_type:
        query = query.where(QCEvent.event_type == event_type)
    events = [event for event in session.exec(query.limit(limit)).all() if stream_is_accessible(session, user, event.stream_id)]
    return [_event_out(event) for event in events]


@app.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(AlertRecord, QCRecord.timestamp)
        .join(QCRecord, col(QCRecord.id) == col(AlertRecord.qc_record_id), isouter=True)
        .order_by(col(AlertRecord.created_at).desc())
    ).all()
    return [
        _alert_out(alert, qc_record_timestamp=qc_timestamp, session=session)
        for alert, qc_timestamp in rows
        if stream_is_accessible(session, user, alert.stream_id)
    ]


@app.patch("/alerts/{alert_id}", response_model=AlertOut)
def update_alert_status(
    alert_id: str,
    payload: AlertUpdate,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    alert = require_alert_access(session, user, alert_id)
    before = alert.model_dump(mode="json")
    alert_changed = False
    if payload.status is not None and payload.status != alert.status:
        alert.status = payload.status
        alert_changed = True
        if payload.status in {AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED}:
            alert.acknowledged_by = user.actor
            alert.acknowledged_at = datetime.now(timezone.utc)
        elif payload.status == AlertStatus.OPEN:
            alert.acknowledged_by = None
            alert.acknowledged_at = None
    if payload.assigned_to is not None and payload.assigned_to != alert.assigned_to:
        alert.assigned_to = payload.assigned_to
        alert_changed = True
    if payload.due_at is not None and payload.due_at != alert.due_at:
        alert.due_at = payload.due_at
        alert_changed = True
    reason = require_reason(payload.reason, "reason is required when updating an alert") if alert_changed else payload.reason
    alert = update_alert(session, alert)
    record_audit(
        session,
        actor=user.actor,
        action="update_alert",
        entity_type="alert",
        entity_id=alert.alert_id,
        before=before,
        after=alert.model_dump(mode="json"),
        reason=reason,
    )
    return _alert_out(alert, session=session)


@app.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(
    status_filter: Optional[InvestigationStatus] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(Investigation).order_by(col(Investigation.created_at).desc())
    if status_filter:
        query = query.where(Investigation.status == status_filter)
    investigations = session.exec(query).all()
    results = []
    for investigation in investigations:
        if investigation.id is None:
            raise RuntimeError("Investigation missing id")
        alert_id = _investigation_alert_id(session, investigation.id)
        results.append(_investigation_out(investigation, alert_id=alert_id))
    return results


@app.post("/investigations", response_model=InvestigationOut)
def create_investigation_record(
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
            created_by=user.actor,
        ),
        alert_id=alert_id,
    )
    record_audit(
        session,
        actor=user.actor,
        action="create_investigation",
        entity_type="investigation",
        entity_id=str(investigation.id),
        before=None,
        after=investigation.model_dump(mode="json"),
        reason=None,
    )
    return _investigation_out(investigation, alert_id=alert_id_str)


@app.patch("/investigations/{investigation_id}", response_model=InvestigationOut)
def update_investigation_record(
    investigation_id: int,
    payload: InvestigationIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    investigation = session.exec(select(Investigation).where(Investigation.id == investigation_id)).first()
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    before = investigation.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id", "reason"})
    reason = require_reason(payload.reason, "reason is required when updating an investigation") if updates else payload.reason
    for field, value in updates.items():
        setattr(investigation, field, value)
    investigation = update_investigation(session, investigation)
    record_audit(
        session,
        actor=user.actor,
        action="update_investigation",
        entity_type="investigation",
        entity_id=str(investigation.id),
        before=before,
        after=investigation.model_dump(mode="json"),
        reason=reason,
    )
    if investigation.id is None:
        raise RuntimeError("Investigation missing id")
    alert_id_str = _investigation_alert_id(session, investigation.id)
    return _investigation_out(investigation, alert_id=alert_id_str)


@app.post("/capas", response_model=CapaOut)
def create_capa_record(
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
            created_by=user.actor,
        ),
        alert_id=alert_id,
        investigation_id=investigation_id,
    )
    record_audit(
        session,
        actor=user.actor,
        action="create_capa",
        entity_type="capa",
        entity_id=str(capa.id),
        before=None,
        after=capa.model_dump(mode="json"),
        reason=None,
    )
    return _capa_out(capa, alert_id=alert_id_str, investigation_id=investigation_id)


@app.patch("/capas/{capa_id}", response_model=CapaOut)
def update_capa_record(
    capa_id: int,
    payload: CapaIn,
    user: UserContext = Depends(require_permission(Permission.APPROVE)),
    session: Session = Depends(get_session),
):
    capa = session.exec(select(Capa).where(Capa.id == capa_id)).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    before = capa.model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"alert_id", "investigation_id", "reason"})
    reason = require_reason(payload.reason, "reason is required when updating a CAPA") if updates else payload.reason
    for field, value in updates.items():
        setattr(capa, field, value)
    merged = capa.model_dump()
    if merged.get("status") != CapaStatus.DRAFT:
        payload_data = {key: merged.get(key) for key in CapaIn.model_fields.keys()}
        validate_capa_fields(CapaIn(**payload_data))
    capa = update_capa(session, capa)
    record_audit(
        session,
        actor=user.actor,
        action="update_capa",
        entity_type="capa",
        entity_id=str(capa.id),
        before=before,
        after=capa.model_dump(mode="json"),
        reason=reason,
    )
    if capa.id is None:
        raise RuntimeError("CAPA missing id")
    alert_id_str, investigation_id = _capa_links(session, capa.id)
    return _capa_out(capa, alert_id=alert_id_str, investigation_id=investigation_id)


@app.get("/capas", response_model=list[CapaOut])
def list_capas(
    status_filter: Optional[CapaStatus] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    query = select(Capa).order_by(col(Capa.created_at).desc())
    if status_filter:
        query = query.where(Capa.status == status_filter)
    capas = session.exec(query).all()
    results = []
    for capa in capas:
        if capa.id is None:
            raise RuntimeError("CAPA missing id")
        alert_id, investigation_id = _capa_links(session, capa.id)
        results.append(_capa_out(capa, alert_id=alert_id, investigation_id=investigation_id))
    return results


@app.get("/audit", response_model=list[AuditEntryOut])
def list_audit(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
):
    scope = effective_scope(session, user)
    query = select(AuditEntry).order_by(col(AuditEntry.timestamp).desc())
    if not scope.unrestricted:
        query = query.where(AuditEntry.api_key_id == user.api_key_id)
    entries = session.exec(query).all()
    return [_audit_out(entry) for entry in entries]


@app.get("/reports/summary", response_model=ReportSummaryOut)
def report_summary(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> ReportSummaryOut:
    alert_rows = session.exec(select(AlertRecord)).all()
    investigation_rows = session.exec(select(Investigation)).all()
    capa_rows = session.exec(select(Capa)).all()
    return ReportSummaryOut(
        alerts=AlertSummary(
            total=len(alert_rows),
            open=len([a for a in alert_rows if a.status == AlertStatus.OPEN]),
            acknowledged=len([a for a in alert_rows if a.status == AlertStatus.ACKNOWLEDGED]),
        ),
        investigations=InvestigationSummary(
            total=len(investigation_rows),
            open=len([i for i in investigation_rows if i.status != InvestigationStatus.CLOSED]),
        ),
        capas=CapaSummary(
            total=len(capa_rows),
            open=len([c for c in capa_rows if c.status not in {CapaStatus.CLOSED, CapaStatus.DRAFT}]),
        ),
    )


@app.get("/streams/{stream_id}/chart", response_model=StreamChartOut)
def stream_chart(
    stream_id: str,
    limit: int = 200,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    include_evaluations: bool = True,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> StreamChartOut:
    require_stream_access(session, user, stream_id)
    record_query = select(QCRecord).where(QCRecord.stream_id == stream_id)
    if start:
        record_query = record_query.where(QCRecord.timestamp >= start)
    if end:
        record_query = record_query.where(QCRecord.timestamp <= end)
    records = session.exec(record_query.order_by(col(QCRecord.timestamp).desc()).limit(limit)).all()
    record_series = records[::-1]

    record_points: list[QCRecordChartOut] = []
    for record in record_series:
        if record.id is None:
            raise RuntimeError("QC record missing id")

        signals: Optional[list[FrequentistSignal]] = None
        disposition: Optional[Disposition] = None
        record_risk: Optional[BayesianRisk] = None
        if include_evaluations:
            if record.signals is not None:
                signals = [FrequentistSignal.model_validate(s) for s in record.signals]
            if record.bayesian_risk is not None:
                record_risk = BayesianRisk.model_validate(record.bayesian_risk)
            if record.disposition is not None:
                disposition = Disposition(record.disposition)
        record_points.append(
            QCRecordChartOut(
                id=record.id,
                timestamp=record.timestamp,
                result_value=record.result_value,
                control_material_lot=record.control_material_lot,
                include_in_stats=record.include_in_stats,
                resolved_reason=record.resolved_reason,
                resolved_at=record.resolved_at,
                signals=signals,
                bayesian_risk=record_risk,
                disposition=disposition,
                evaluation=(
                    record_evaluation_provenance(session, record)
                    if include_evaluations
                    else None
                ),
            )
        )
    lot_segments = _lot_segments(record_series)

    event_query = select(QCEvent).where(QCEvent.stream_id == stream_id)
    if start:
        event_query = event_query.where(QCEvent.timestamp >= start)
    if end:
        event_query = event_query.where(QCEvent.timestamp <= end)
    events = session.exec(event_query.order_by(col(QCEvent.timestamp).desc()).limit(limit)).all()

    alert_rows_query = (
        select(AlertRecord, QCRecord.timestamp)
        .join(QCRecord, col(QCRecord.id) == col(AlertRecord.qc_record_id), isouter=True)
        .where(AlertRecord.stream_id == stream_id)
    )
    if start:
        alert_rows_query = alert_rows_query.where(
            or_(
                and_(col(QCRecord.timestamp).is_not(None), col(QCRecord.timestamp) >= start),
                and_(col(QCRecord.timestamp).is_(None), col(AlertRecord.created_at) >= start),
            )
        )
    if end:
        alert_rows_query = alert_rows_query.where(
            or_(
                and_(col(QCRecord.timestamp).is_not(None), col(QCRecord.timestamp) <= end),
                and_(col(QCRecord.timestamp).is_(None), col(AlertRecord.created_at) <= end),
            )
        )
    alert_rows = session.exec(alert_rows_query.order_by(col(AlertRecord.created_at).desc()).limit(limit)).all()

    return StreamChartOut(
        records=record_points,
        events=[_event_out(event) for event in events[::-1]],
        alerts=[
            _alert_out(alert, qc_record_timestamp=qc_timestamp, session=session)
            for alert, qc_timestamp in alert_rows[::-1]
        ],
        lot_segments=lot_segments,
    )
