from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.db_models import EnterpriseSite, LabArea
from app.models import EnterpriseSiteOut, LabAreaOut
from app.services.access_scopes import AccessScope, effective_scope
from app.rbac import UserContext


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def same_text(left: Optional[str], right: Optional[str]) -> bool:
    return (left or "").strip().casefold() == (right or "").strip().casefold()


def site_out(row: EnterpriseSite) -> EnterpriseSiteOut:
    if row.id is None:
        raise RuntimeError("Enterprise site missing id")
    return EnterpriseSiteOut(**row.model_dump())


def lab_area_out(session: Session, row: LabArea) -> LabAreaOut:
    if row.id is None:
        raise RuntimeError("Lab area missing id")
    site = get_site(session, row.site_id)
    return LabAreaOut(**row.model_dump(), site_name=site.name)


def get_site(session: Session, site_id: int) -> EnterpriseSite:
    row = session.get(EnterpriseSite, site_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enterprise site not found")
    return row


def get_lab_area(session: Session, area_id: int) -> LabArea:
    row = session.get(LabArea, area_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab area not found")
    return row


def find_site_by_name(session: Session, name: str) -> EnterpriseSite | None:
    rows = session.exec(select(EnterpriseSite)).all()
    return next((row for row in rows if same_text(row.name, name)), None)


def find_lab_area_by_name(session: Session, site_id: int, name: str) -> LabArea | None:
    rows = session.exec(select(LabArea).where(LabArea.site_id == site_id)).all()
    return next((row for row in rows if same_text(row.name, name)), None)


def site_is_allowed(scope: AccessScope, site_name: Optional[str]) -> bool:
    if scope.unrestricted:
        return True
    return any(grant.site and same_text(grant.site, site_name) for grant in scope.grants)


def area_is_allowed(scope: AccessScope, site_name: Optional[str], area_name: Optional[str]) -> bool:
    if scope.unrestricted:
        return True
    for grant in scope.grants:
        if grant.site and not same_text(grant.site, site_name):
            continue
        if grant.lab_bench and not same_text(grant.lab_bench, area_name):
            continue
        if grant.site or grant.lab_bench:
            return True
    return False


def require_site_create_access(session: Session, user: UserContext) -> None:
    if effective_scope(session, user).unrestricted:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creating a new site requires unrestricted scope")


def require_area_create_access(session: Session, user: UserContext, site: EnterpriseSite) -> None:
    scope = effective_scope(session, user)
    if site_is_allowed(scope, site.name):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target site scope is not allowed")


def accessible_sites(session: Session, user: UserContext, *, active: Optional[bool]) -> list[EnterpriseSite]:
    scope = effective_scope(session, user)
    query = select(EnterpriseSite).order_by(col(EnterpriseSite.name).asc())
    if active is not None:
        query = query.where(EnterpriseSite.active == active)
    rows = list(session.exec(query).all())
    if scope.unrestricted:
        return rows
    allowed_area_sites = {
        area.site_id
        for area in session.exec(select(LabArea)).all()
        if any(grant.lab_bench and same_text(grant.lab_bench, area.name) for grant in scope.grants)
    }
    return [
        row
        for row in rows
        if site_is_allowed(scope, row.name) or (row.id is not None and row.id in allowed_area_sites)
    ]


def accessible_lab_areas(
    session: Session,
    user: UserContext,
    *,
    site_id: Optional[int],
    active: Optional[bool],
) -> list[LabArea]:
    scope = effective_scope(session, user)
    query = select(LabArea).order_by(col(LabArea.name).asc())
    if site_id is not None:
        query = query.where(LabArea.site_id == site_id)
    if active is not None:
        query = query.where(LabArea.active == active)
    rows = list(session.exec(query).all())
    if scope.unrestricted:
        return rows
    sites = {row.id: row.name for row in session.exec(select(EnterpriseSite)).all() if row.id is not None}
    return [row for row in rows if area_is_allowed(scope, sites.get(row.site_id), row.name)]
