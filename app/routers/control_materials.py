from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.db_models import ControlMaterial
from app.models import Permission
from app.rbac import UserContext, require_permission
from app.services.stream_setup_assets import control_material_out
from app.storage import record_audit
from app.stream_setup_models import ControlMaterialIn, ControlMaterialOut

router = APIRouter(prefix="/control-materials", tags=["control-materials"])


@router.get("", response_model=list[ControlMaterialOut])
def list_control_materials(
    active: Optional[bool] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[ControlMaterialOut]:
    del user
    query = select(ControlMaterial).order_by(col(ControlMaterial.name).asc(), col(ControlMaterial.lot).asc())
    if active is not None:
        query = query.where(ControlMaterial.active == active)
    return [control_material_out(row) for row in session.exec(query).all()]


@router.post("", response_model=ControlMaterialOut)
def create_control_material(
    payload: ControlMaterialIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> ControlMaterialOut:
    row = ControlMaterial(**payload.model_dump(), created_by=user.actor)
    session.add(row)
    session.flush()
    out = control_material_out(row)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_control_material",
        entity_type="control_material",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return control_material_out(row)
