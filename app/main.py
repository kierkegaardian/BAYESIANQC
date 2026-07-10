from __future__ import annotations

import csv
import json
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import StringIO
from typing import Any, NoReturn, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.api_models import CsvIngestResult, CsvRowError, LotSegmentOut, QCRecordChartOut, StreamChartOut
from app.db import get_engine, get_session, init_db
from app.db_models import (
    AlertRecord,
    Analyte,
    Instrument,
    Method,
    PriorConfig,
    QCEvent,
    QCRecord,
    QCRecordQuarantine,
    StreamConfig,
)
from app.domain import Disposition
from app.error_handlers import install_error_handlers
from app.evaluations import reprocess_stream_evaluations
from app.math.nig import beta_from_expected_sigma
from app.models import (
    AnalyteIn,
    AnalyteOut,
    AnalyteUpdate,
    BayesianRisk,
    CurrentUserOut,
    EventType,
    IngestionResult,
    InstrumentIn,
    InstrumentOut,
    InstrumentUpdate,
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
from app.rbac import ROLE_PERMISSIONS, UserContext, require_operator_read, require_permission
from app.routers.control_materials import router as control_materials_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router
from app.routers.kiosks import router as kiosks_router
from app.routers.locations import router as locations_router
from app.routers.qc_backlog import router as qc_backlog_router
from app.routers.qc_comments import router as qc_comments_router
from app.routers.stream_setups import router as stream_setups_router
from app.routers.stream_catalog import router as stream_catalog_router
from app.routers.tests import router as tests_router
from app.routers.workflow_reporting import router as workflow_reporting_router
from app.routers.workflows import router as workflows_router
from app.services.ingestion import process_ingestion
from app.services.ingestion_support import alert_out as _alert_out
from app.services.access_scopes import (
    effective_scope,
    require_record_access,
    require_stream_access,
    require_stream_context_access,
    scope_summary_for_me,
    stream_context_is_accessible,
    stream_id_scope_predicate,
    stream_scope_predicate,
)
from app.services.locations import area_is_allowed, get_lab_area, get_site
from app.services.locks import stream_write_lock
from app.services.quarantine import quarantine_out
from app.storage import (
    create_event,
    create_prior_config,
    create_stream_config,
    get_active_stream_config,
    list_stream_configs,
    record_audit,
    seed_defaults,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    with Session(get_engine()) as session:
        seed_defaults(session)
    yield


app = FastAPI(
    title="Bayesian QC Prototype",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
install_error_handlers(app)

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
    expose_headers=["X-Total-Count"],
)
app.include_router(control_materials_router)
app.include_router(health_router)
app.include_router(imports_router)
app.include_router(kiosks_router)
app.include_router(locations_router)
app.include_router(qc_backlog_router)
app.include_router(qc_comments_router)
app.include_router(stream_setups_router)
app.include_router(stream_catalog_router)
app.include_router(tests_router)
app.include_router(workflows_router)
app.include_router(workflow_reporting_router)


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
async def root_page(_: UserContext = Depends(require_operator_read)):
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
async def custom_docs(_: UserContext = Depends(require_operator_read)):
    content = (
        "Use Swagger UI to explore endpoints and send requests. Click a route, choose "
        "'Try it out', and add the X-API-Key header before executing."
    )
    html = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="BayesianQC API Docs",
    )
    body = bytes(html.body).decode("utf-8")
    return HTMLResponse(_inject_help(body, content))


@app.get("/redoc", include_in_schema=False)
async def custom_redoc(_: UserContext = Depends(require_operator_read)):
    content = (
        "Use this page for read-only reference of schemas, endpoints, and models. "
        "All API calls still require X-API-Key when sent from your client."
    )
    html = get_redoc_html(
        openapi_url="/openapi.json",
        title="BayesianQC API Reference",
    )
    body = bytes(html.body).decode("utf-8")
    return HTMLResponse(_inject_help(body, content))


@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi(_: UserContext = Depends(require_operator_read)) -> JSONResponse:
    return JSONResponse(app.openapi())


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


def _stream_out(config: StreamConfig) -> StreamConfigOut:
    return StreamConfigOut(**config.model_dump())


def _instrument_out(instrument: Instrument) -> InstrumentOut:
    return InstrumentOut(**instrument.model_dump())


def _normalize_instrument_location(session: Session, data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    area_id = normalized.get("lab_area_id")
    site_id = normalized.get("site_id")
    if area_id is not None:
        area = get_lab_area(session, int(area_id))
        if site_id is not None and int(site_id) != area.site_id:
            raise HTTPException(status_code=422, detail="lab_area_id does not belong to site_id")
        site = get_site(session, area.site_id)
        normalized["site_id"] = area.site_id
        normalized["lab_area_id"] = area.id
        normalized["site"] = site.name
        normalized["lab_bench"] = area.name
    elif site_id is not None:
        site = get_site(session, int(site_id))
        normalized["site_id"] = site.id
        normalized["site"] = site.name
    return normalized


def _require_instrument_context_access(session: Session, user: UserContext, data: dict[str, Any]) -> None:
    site = data.get("site")
    lab_bench = data.get("lab_bench")
    if stream_context_is_accessible(
        session,
        user,
        stream_id="",
        site=str(site) if site is not None else None,
        lab_bench=str(lab_bench) if lab_bench is not None else None,
    ):
        return
    raise HTTPException(status_code=403, detail="Target instrument scope is not allowed")


def _method_out(method: Method) -> MethodOut:
    return MethodOut(**method.model_dump())


def _analyte_out(analyte: Analyte) -> AnalyteOut:
    return AnalyteOut(**analyte.model_dump())


def _prior_out(config: PriorConfig) -> PriorConfigOut:
    return PriorConfigOut(**config.model_dump())


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
        .where(
            QCRecordQuarantine.status == status_filter,
            stream_id_scope_predicate(session, user, col(QCRecordQuarantine.stream_id)),
        )
        .order_by(col(QCRecordQuarantine.created_at).desc())
        .limit(limit)
    )
    rows = session.exec(query).all()
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
    user: UserContext = Depends(require_permission(Permission.RESOLVE_QC)),
    session: Session = Depends(get_session),
):
    record = require_record_access(session, user, record_id)
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
                commit=False,
                actor=user.actor,
                actor_role=user.role,
                api_key_id=user.api_key_id,
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
    site_id: Optional[int] = None,
    lab_area_id: Optional[int] = None,
    site: Optional[str] = None,
    lab_bench: Optional[str] = None,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
):
    query = select(Instrument).order_by(col(Instrument.name).asc())
    if active is not None:
        query = query.where(Instrument.active == active)
    if site_id is not None:
        query = query.where(Instrument.site_id == site_id)
    if lab_area_id is not None:
        query = query.where(Instrument.lab_area_id == lab_area_id)
    if site:
        query = query.where(Instrument.site == site)
    if lab_bench:
        query = query.where(Instrument.lab_bench == lab_bench)
    scope = effective_scope(session, user)
    instruments = [
        instrument
        for instrument in session.exec(query).all()
        if area_is_allowed(scope, instrument.site, instrument.lab_bench)
    ]
    return [_instrument_out(instrument) for instrument in instruments]


@app.post("/instruments", response_model=InstrumentOut)
def create_instrument(
    payload: InstrumentIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
):
    data = _normalize_instrument_location(session, payload.model_dump())
    _require_instrument_context_access(session, user, data)
    instrument = Instrument(**data, created_by=user.actor)
    session.add(instrument)
    session.flush()
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
    session.commit()
    session.refresh(instrument)
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
    data = _normalize_instrument_location(session, payload.model_dump(exclude_unset=True))
    _require_instrument_context_access(session, user, {**instrument.model_dump(), **data})
    for field, value in data.items():
        setattr(instrument, field, value)
    session.add(instrument)
    session.flush()
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
    session.commit()
    session.refresh(instrument)
    return _instrument_out(instrument)


@app.get("/methods", response_model=list[MethodOut])
def list_methods(
    instrument_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_operator_read),
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
    session.flush()
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
    session.commit()
    session.refresh(method)
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
    session.flush()
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
    session.commit()
    session.refresh(method)
    return _method_out(method)


@app.get("/analytes", response_model=list[AnalyteOut])
def list_analytes(
    method_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_operator_read),
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
    session.flush()
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
    session.commit()
    session.refresh(analyte)
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
    session.flush()
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
    session.commit()
    session.refresh(analyte)
    return _analyte_out(analyte)


@app.get("/streams", response_model=list[StreamConfigOut])
def list_streams(
    site: Optional[str] = None,
    lab_bench: Optional[str] = None,
    include_scheduled: bool = Query(default=False),
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
):
    scope = effective_scope(session, user)
    query = select(StreamConfig).where(stream_scope_predicate(scope))
    if not include_scheduled:
        query = query.where(StreamConfig.effective_from <= datetime.now(timezone.utc))
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
    return [_stream_out(cfg) for cfg in latest.values()]


@app.get("/streams/{stream_id}/configs", response_model=list[StreamConfigOut])
def list_stream_versions(
    stream_id: str,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id)
    return [_stream_out(cfg) for cfg in list_stream_configs(session, stream_id)]


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
            return _stream_out(config)
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
            latest_ts = session.exec(
                select(QCRecord.timestamp)
                .where(QCRecord.stream_id == stream_id)
                .order_by(col(QCRecord.timestamp).desc())
                .limit(1)
            ).first()
            if latest_ts is not None and config.effective_from <= latest_ts:
                reprocess_stream_evaluations(
                    session,
                    stream_id,
                    commit=False,
                    actor=user.actor,
                    actor_role=user.role,
                    api_key_id=user.api_key_id,
                )
            session.commit()
            session.refresh(config)
            return _stream_out(config)
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
    if payload.beta0 is None:
        effective_from = payload.effective_from or datetime.now(timezone.utc)
        stream_config = get_active_stream_config(session, stream_id, effective_from)
        if stream_config is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="beta0 cannot be derived without an effective stream sigma",
            )
        payload = payload.model_copy(
            update={"beta0": beta_from_expected_sigma(payload.alpha0, stream_config.sigma)}
        )
    with stream_write_lock(session, stream_id):
        try:
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
            latest_ts = session.exec(
                select(QCRecord.timestamp)
                .where(QCRecord.stream_id == stream_id)
                .order_by(col(QCRecord.timestamp).desc())
                .limit(1)
            ).first()
            if latest_ts is not None and config.effective_from <= latest_ts:
                reprocess_stream_evaluations(
                    session,
                    stream_id,
                    commit=False,
                    actor=user.actor,
                    actor_role=user.role,
                    api_key_id=user.api_key_id,
                )
            session.commit()
            session.refresh(config)
            return _prior_out(config)
        except IntegrityError as exc:
            session.rollback()
            raise_config_version_conflict(exc)
        except Exception:
            session.rollback()
            raise


@app.get("/streams/{stream_id}/priors", response_model=list[PriorConfigOut])
def list_priors(
    stream_id: str,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
):
    require_stream_access(session, user, stream_id)
    priors = session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(col(PriorConfig.version).desc())
    ).all()
    return [_prior_out(prior) for prior in priors]


@app.post("/qc/events", response_model=QCEventOut)
def ingest_event(
    payload: QCEventIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
):
    if payload.stream_id is not None:
        require_stream_access(session, user, payload.stream_id, hide=False)
    try:
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
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(event)
    return _event_out(event)


@app.get("/qc/events", response_model=list[QCEventOut])
def list_events(
    stream_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    limit: int = 200,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
):
    query = select(QCEvent).order_by(col(QCEvent.timestamp).desc())
    if stream_id:
        require_stream_access(session, user, stream_id)
        query = query.where(QCEvent.stream_id == stream_id)
    if event_type:
        query = query.where(QCEvent.event_type == event_type)
    query = query.where(stream_id_scope_predicate(session, user, col(QCEvent.stream_id)))
    events = session.exec(query.limit(limit)).all()
    return [_event_out(event) for event in events]


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
        alerts=[_alert_out(alert, qc_record_timestamp=qc_timestamp) for alert, qc_timestamp in alert_rows[::-1]],
        lot_segments=lot_segments,
    )
