from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session

from app.api_models import (
    AlertSummary,
    CapaSummary,
    InvestigationSummary,
    ReportSummaryOut,
)
from app.db import get_session
from app.models import AuditEntryOut, Permission, Role
from app.rbac import UserContext, require_operator_read, require_permission
from app.services.ingestion_support import audit_out
from app.services.workflow_queries import list_audit_page, workflow_summary

router = APIRouter()


@router.get("/audit", response_model=list[AuditEntryOut])
def list_audit(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_role: Optional[Role] = None,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
) -> list[AuditEntryOut]:
    page = list_audit_page(
        session,
        user=user,
        limit=limit,
        offset=offset,
        action=action,
        entity_type=entity_type,
        actor_role=actor_role,
    )
    response.headers["X-Total-Count"] = str(page.total)
    return [audit_out(entry) for entry in page.rows]


@router.get("/reports/summary", response_model=ReportSummaryOut)
def report_summary(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> ReportSummaryOut:
    summary = workflow_summary(session, user=user)
    return ReportSummaryOut(
        alerts=AlertSummary(
            total=summary.alert_total,
            open=summary.alert_open,
            acknowledged=summary.alert_acknowledged,
            closed=summary.alert_closed,
        ),
        investigations=InvestigationSummary(
            total=summary.investigation_total,
            open=summary.investigation_open,
        ),
        capas=CapaSummary(
            total=summary.capa_total,
            open=summary.capa_open,
        ),
    )
