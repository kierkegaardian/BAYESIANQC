from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.models import Permission
from app.rbac import UserContext, require_permission
from app.services.kiosks import append_kiosk_panel, create_kiosk, get_kiosk, kiosk_layout_out, list_kiosks
from app.stream_setup_models import KioskLayoutIn, KioskLayoutOut, KioskPanelIn

router = APIRouter(prefix="/kiosks", tags=["kiosks"])


@router.get("", response_model=list[KioskLayoutOut])
def list_kiosk_layouts(
    active: Optional[bool] = None,
    site: Optional[str] = None,
    lab_bench: Optional[str] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[KioskLayoutOut]:
    del user
    return list_kiosks(session, active=active, site=site, lab_bench=lab_bench)


@router.post("", response_model=KioskLayoutOut)
def create_kiosk_layout(
    payload: KioskLayoutIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> KioskLayoutOut:
    return create_kiosk(session, payload, user)


@router.get("/{slug}", response_model=KioskLayoutOut)
def get_kiosk_layout(
    slug: str,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> KioskLayoutOut:
    del user
    return kiosk_layout_out(session, get_kiosk(session, slug))


@router.post("/{slug}/panels", response_model=KioskLayoutOut)
def append_panel(
    slug: str,
    payload: KioskPanelIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> KioskLayoutOut:
    return append_kiosk_panel(session, slug, payload, user)
