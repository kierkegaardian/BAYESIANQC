from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.db_models import KioskLayout, KioskPanel, StreamConfig
from app.rbac import UserContext
from app.storage import record_audit
from app.stream_setup_models import KioskLayoutIn, KioskLayoutOut, KioskPanelIn, KioskPanelOut


def kiosk_panel_out(panel: KioskPanel) -> KioskPanelOut:
    if panel.id is None:
        raise RuntimeError("Kiosk panel missing id")
    return KioskPanelOut(**panel.model_dump())


def kiosk_layout_out(session: Session, layout: KioskLayout) -> KioskLayoutOut:
    if layout.id is None:
        raise RuntimeError("Kiosk layout missing id")
    panels = session.exec(
        select(KioskPanel)
        .where(KioskPanel.kiosk_id == layout.id, KioskPanel.active == True)  # noqa: E712
        .order_by(col(KioskPanel.display_order).asc(), col(KioskPanel.id).asc())
    ).all()
    return KioskLayoutOut(**layout.model_dump(), panels=[kiosk_panel_out(panel) for panel in panels])


def list_kiosks(
    session: Session,
    *,
    active: Optional[bool] = None,
    site: Optional[str] = None,
    lab_bench: Optional[str] = None,
) -> list[KioskLayoutOut]:
    query = select(KioskLayout).order_by(col(KioskLayout.label).asc())
    if active is not None:
        query = query.where(KioskLayout.active == active)
    if site:
        query = query.where(KioskLayout.site == site)
    if lab_bench:
        query = query.where(KioskLayout.lab_bench == lab_bench)
    return [kiosk_layout_out(session, layout) for layout in session.exec(query).all()]


def get_kiosk(session: Session, slug: str) -> KioskLayout:
    layout = session.exec(select(KioskLayout).where(KioskLayout.slug == slug)).first()
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kiosk layout not found")
    return layout


def ensure_stream_exists(session: Session, stream_id: str) -> None:
    exists = session.exec(select(StreamConfig.stream_id).where(StreamConfig.stream_id == stream_id).limit(1)).first()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stream is not configured")


def create_kiosk(session: Session, payload: KioskLayoutIn, user: UserContext) -> KioskLayoutOut:
    existing = session.exec(select(KioskLayout).where(KioskLayout.slug == payload.slug)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kiosk slug already exists")
    layout = KioskLayout(**payload.model_dump(), created_by=user.actor)
    session.add(layout)
    session.flush()
    out = kiosk_layout_out(session, layout)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_kiosk_layout",
        entity_type="kiosk_layout",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(layout)
    return kiosk_layout_out(session, layout)


def _next_display_order(session: Session, kiosk_id: int) -> int:
    current = session.exec(
        select(KioskPanel.display_order)
        .where(KioskPanel.kiosk_id == kiosk_id)
        .order_by(col(KioskPanel.display_order).desc())
        .limit(1)
    ).first()
    return int(current or 0) + 1


def append_kiosk_panel(session: Session, slug: str, payload: KioskPanelIn, user: UserContext) -> KioskLayoutOut:
    layout = get_kiosk(session, slug)
    if layout.id is None:
        raise RuntimeError("Kiosk layout missing id")
    ensure_stream_exists(session, payload.stream_id)
    panel_data = payload.model_dump()
    if panel_data.get("display_order") is None:
        panel_data["display_order"] = _next_display_order(session, layout.id)
    panel = KioskPanel(**panel_data, kiosk_id=layout.id, created_by=user.actor)
    session.add(panel)
    session.flush()
    out = kiosk_layout_out(session, layout)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="append_kiosk_panel",
        entity_type="kiosk_layout",
        entity_id=str(layout.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=payload.title,
        commit=False,
    )
    session.commit()
    return kiosk_layout_out(session, layout)
