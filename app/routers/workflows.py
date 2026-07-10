from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session, select

from app.db import get_session
from app.db_models import QCRecord
from app.models import (
    AlertOut,
    AlertStatus,
    AlertUpdate,
    CapaIn,
    CapaOut,
    CapaStatus,
    InvestigationIn,
    InvestigationOut,
    InvestigationStatus,
    Permission,
)
from app.rbac import UserContext, require_permission
from app.services.access_scopes import (
    require_alert_access,
    require_capa_access,
    require_investigation_access,
)
from app.services.ingestion_support import alert_out
from app.services.workflow_alerts import update_alert_workflow
from app.services.workflow_capas import (
    capa_link_ids,
    create_capa_workflow,
    update_capa_workflow,
)
from app.services.workflow_investigations import (
    create_investigation_workflow,
    investigation_alert_id,
    update_investigation_workflow,
)
from app.services.workflow_queries import (
    list_alert_page,
    list_capa_views,
    list_investigation_views,
)
from app.services.workflow_responses import capa_out, investigation_out

router = APIRouter()


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[AlertStatus] = Query(default=None, alias="status"),
    stream_id: Optional[str] = Query(default=None, alias="stream"),
    severity: Optional[str] = None,
    disposition: Optional[str] = None,
    assigned_to: Optional[str] = None,
    from_time: Optional[datetime] = Query(default=None, alias="from"),
    to_time: Optional[datetime] = Query(default=None, alias="to"),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[AlertOut]:
    page = list_alert_page(
        session,
        user=user,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        stream_id=stream_id,
        severity=severity,
        disposition=disposition,
        assigned_to=assigned_to,
        from_time=from_time,
        to_time=to_time,
    )
    response.headers["X-Total-Count"] = str(page.total)
    return [alert_out(alert, qc_record_timestamp=timestamp) for alert, timestamp in page.rows]


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: str,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> AlertOut:
    alert = require_alert_access(session, user, alert_id)
    qc_timestamp = None
    if alert.qc_record_id is not None:
        qc_timestamp = session.exec(
            select(QCRecord.timestamp).where(QCRecord.id == alert.qc_record_id)
        ).first()
    return alert_out(alert, qc_record_timestamp=qc_timestamp)


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def update_alert_status(
    alert_id: str,
    payload: AlertUpdate,
    user: UserContext = Depends(require_permission(Permission.MANAGE_ALERTS)),
    session: Session = Depends(get_session),
) -> AlertOut:
    alert = update_alert_workflow(session, alert_id=alert_id, payload=payload, user=user)
    return alert_out(alert)


@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(
    status_filter: Optional[InvestigationStatus] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[InvestigationOut]:
    views = list_investigation_views(session, user=user, status_filter=status_filter)
    return [investigation_out(view.row, alert_id=view.alert_id) for view in views]


@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
def get_investigation(
    investigation_id: int,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> InvestigationOut:
    row = require_investigation_access(session, user, investigation_id)
    return investigation_out(row, alert_id=investigation_alert_id(session, investigation_id))


@router.post("/investigations", response_model=InvestigationOut)
def create_investigation_record(
    payload: InvestigationIn,
    user: UserContext = Depends(require_permission(Permission.MANAGE_INVESTIGATIONS)),
    session: Session = Depends(get_session),
) -> InvestigationOut:
    result = create_investigation_workflow(session, payload=payload, user=user)
    return investigation_out(result.row, alert_id=result.alert_id)


@router.patch("/investigations/{investigation_id}", response_model=InvestigationOut)
def update_investigation_record(
    investigation_id: int,
    payload: InvestigationIn,
    user: UserContext = Depends(require_permission(Permission.MANAGE_INVESTIGATIONS)),
    session: Session = Depends(get_session),
) -> InvestigationOut:
    result = update_investigation_workflow(
        session,
        investigation_id=investigation_id,
        payload=payload,
        user=user,
    )
    return investigation_out(result.row, alert_id=result.alert_id)


@router.post("/capas", response_model=CapaOut)
def create_capa_record(
    payload: CapaIn,
    user: UserContext = Depends(require_permission(Permission.MANAGE_CAPAS)),
    session: Session = Depends(get_session),
) -> CapaOut:
    result = create_capa_workflow(session, payload=payload, user=user)
    return capa_out(result.row, alert_id=result.alert_id, investigation_id=result.investigation_id)


@router.patch("/capas/{capa_id}", response_model=CapaOut)
def update_capa_record(
    capa_id: int,
    payload: CapaIn,
    user: UserContext = Depends(require_permission(Permission.MANAGE_CAPAS)),
    session: Session = Depends(get_session),
) -> CapaOut:
    result = update_capa_workflow(session, capa_id=capa_id, payload=payload, user=user)
    return capa_out(result.row, alert_id=result.alert_id, investigation_id=result.investigation_id)


@router.get("/capas", response_model=list[CapaOut])
def list_capas(
    status_filter: Optional[CapaStatus] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[CapaOut]:
    views = list_capa_views(session, user=user, status_filter=status_filter)
    return [
        capa_out(view.row, alert_id=view.alert_id, investigation_id=view.investigation_id)
        for view in views
    ]


@router.get("/capas/{capa_id}", response_model=CapaOut)
def get_capa(
    capa_id: int,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> CapaOut:
    row = require_capa_access(session, user, capa_id)
    alert_id, investigation_id = capa_link_ids(session, capa_id)
    return capa_out(row, alert_id=alert_id, investigation_id=investigation_id)
