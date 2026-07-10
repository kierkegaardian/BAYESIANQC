from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.db_models import EnterpriseSite, LabArea
from app.models import EnterpriseSiteIn, EnterpriseSiteOut, EnterpriseSiteUpdate, LabAreaIn, LabAreaOut, LabAreaUpdate, Permission
from app.rbac import UserContext, require_operator_read, require_permission
from app.services.locations import (
    accessible_lab_areas,
    accessible_sites,
    clean_text,
    find_lab_area_by_name,
    find_site_by_name,
    get_site,
    lab_area_out,
    require_area_create_access,
    require_site_create_access,
    site_out,
    same_text,
)
from app.storage import record_audit

router = APIRouter(tags=["locations"])


def _site_code_conflict(session: Session, code: Optional[str], *, exclude_id: Optional[int] = None) -> bool:
    if not code:
        return False
    rows = session.exec(select(EnterpriseSite)).all()
    return any(row.id != exclude_id and same_text(row.code, code) for row in rows)


@router.get("/enterprise-sites", response_model=list[EnterpriseSiteOut])
def list_enterprise_sites(
    active: Optional[bool] = None,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
) -> list[EnterpriseSiteOut]:
    return [site_out(row) for row in accessible_sites(session, user, active=active)]


@router.post("/enterprise-sites", response_model=EnterpriseSiteOut)
def create_enterprise_site(
    payload: EnterpriseSiteIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> EnterpriseSiteOut:
    require_site_create_access(session, user)
    if find_site_by_name(session, payload.name) or _site_code_conflict(session, payload.code):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Enterprise site already exists")
    row = EnterpriseSite(**payload.model_dump(), created_by=user.actor)
    session.add(row)
    session.flush()
    out = site_out(row)
    record_audit(
        session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_enterprise_site",
        entity_type="enterprise_site",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return site_out(row)


@router.patch("/enterprise-sites/{site_id}", response_model=EnterpriseSiteOut)
def update_enterprise_site(
    site_id: int,
    payload: EnterpriseSiteUpdate,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> EnterpriseSiteOut:
    row = get_site(session, site_id)
    require_site_create_access(session, user)
    data = payload.model_dump(exclude_unset=True)
    next_name = data.get("name")
    if isinstance(next_name, str):
        existing = find_site_by_name(session, next_name)
        if existing and existing.id != site_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Enterprise site already exists")
    next_code = clean_text(data.get("code")) if "code" in data else row.code
    if _site_code_conflict(session, next_code, exclude_id=site_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Enterprise site code already exists")
    before = row.model_dump(mode="json")
    for field, value in data.items():
        setattr(row, field, clean_text(value) if field in {"code", "description"} else value)
    session.add(row)
    session.flush()
    out = site_out(row)
    record_audit(
        session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="update_enterprise_site",
        entity_type="enterprise_site",
        entity_id=str(out.id),
        before=before,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return site_out(row)


@router.get("/lab-areas", response_model=list[LabAreaOut])
def list_lab_areas(
    site_id: Optional[int] = None,
    active: Optional[bool] = None,
    user: UserContext = Depends(require_operator_read),
    session: Session = Depends(get_session),
) -> list[LabAreaOut]:
    return [lab_area_out(session, row) for row in accessible_lab_areas(session, user, site_id=site_id, active=active)]


@router.post("/lab-areas", response_model=LabAreaOut)
def create_lab_area(
    payload: LabAreaIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> LabAreaOut:
    site = get_site(session, payload.site_id)
    require_area_create_access(session, user, site)
    if find_lab_area_by_name(session, payload.site_id, payload.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lab area already exists for this site")
    row = LabArea(**payload.model_dump(), created_by=user.actor)
    session.add(row)
    session.flush()
    out = lab_area_out(session, row)
    record_audit(
        session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_lab_area",
        entity_type="lab_area",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return lab_area_out(session, row)


@router.patch("/lab-areas/{area_id}", response_model=LabAreaOut)
def update_lab_area(
    area_id: int,
    payload: LabAreaUpdate,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> LabAreaOut:
    row = session.get(LabArea, area_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab area not found")
    target_site = get_site(session, payload.site_id if payload.site_id is not None else row.site_id)
    require_area_create_access(session, user, target_site)
    data = payload.model_dump(exclude_unset=True)
    next_name = data.get("name", row.name)
    next_site_id = data.get("site_id", row.site_id)
    existing = find_lab_area_by_name(session, int(next_site_id), str(next_name))
    if existing and existing.id != area_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lab area already exists for this site")
    before = row.model_dump(mode="json")
    for field, value in data.items():
        setattr(row, field, clean_text(value) if field == "description" else value)
    session.add(row)
    session.flush()
    out = lab_area_out(session, row)
    record_audit(
        session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="update_lab_area",
        entity_type="lab_area",
        entity_id=str(out.id),
        before=before,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return lab_area_out(session, row)
