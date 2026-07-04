from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from app.db_models import Analyte, ControlMaterial, Instrument, Method
from app.rbac import UserContext
from app.storage import record_audit
from app.stream_setup_models import ControlMaterialOut, StreamSetupIn


def normalize(value: object) -> str:
    return str(value or "").strip().casefold()


def same_text(left: Optional[str], right: Optional[str]) -> bool:
    return normalize(left) == normalize(right)


def control_material_out(row: ControlMaterial) -> ControlMaterialOut:
    if row.id is None:
        raise RuntimeError("Control material missing id")
    return ControlMaterialOut(**row.model_dump())


def persisted_id(value: Optional[int], label: str) -> int:
    if value is None:
        raise RuntimeError(f"{label} missing id")
    return value


def match_instrument(session: Session, setup: StreamSetupIn) -> Optional[Instrument]:
    for row in session.exec(select(Instrument).where(Instrument.active == True)).all():  # noqa: E712
        if (
            same_text(row.name, setup.instrument_name)
            and same_text(row.site, setup.site)
            and same_text(row.lab_bench, setup.lab_bench)
        ):
            return row
    return None


def match_method(session: Session, instrument_id: int, setup: StreamSetupIn) -> Optional[Method]:
    rows = session.exec(select(Method).where(Method.instrument_id == instrument_id, Method.active == True)).all()  # noqa: E712
    for row in rows:
        if same_text(row.name, setup.method_name):
            return row
    return None


def match_analyte(session: Session, method_id: int, setup: StreamSetupIn) -> Optional[Analyte]:
    rows = session.exec(select(Analyte).where(Analyte.method_id == method_id, Analyte.active == True)).all()  # noqa: E712
    for row in rows:
        if same_text(row.name, setup.parameter_name):
            return row
    return None


def match_material(session: Session, setup: StreamSetupIn) -> Optional[ControlMaterial]:
    rows = session.exec(select(ControlMaterial).where(ControlMaterial.active == True)).all()  # noqa: E712
    for row in rows:
        if (
            same_text(row.name, setup.material_name)
            and same_text(row.lot, setup.control_material_lot)
            and same_text(row.qc_level, setup.qc_level)
            and same_text(row.matrix, setup.matrix)
        ):
            return row
    return None


def audit_create(
    session: Session,
    user: UserContext,
    entity_type: str,
    entity_id: object,
    after: BaseModel | dict[str, Any],
    reason: Optional[str] = None,
) -> None:
    after_payload = after.model_dump(mode="json") if isinstance(after, BaseModel) else after
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action=f"create_{entity_type}",
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=None,
        after=after_payload,
        reason=reason,
        commit=False,
    )


def ensure_assets(session: Session, setup: StreamSetupIn, user: UserContext) -> tuple[Instrument, Method, Analyte, ControlMaterial]:
    instrument = match_instrument(session, setup)
    if instrument is None:
        instrument = Instrument(
            name=setup.instrument_name,
            manufacturer=setup.instrument_manufacturer,
            model=setup.instrument_model,
            site=setup.site,
            lab_bench=setup.lab_bench,
            created_by=user.actor,
        )
        session.add(instrument)
        session.flush()
        audit_create(session, user, "instrument", instrument.id, instrument)
    instrument_id = persisted_id(instrument.id, "Instrument")
    method = match_method(session, instrument_id, setup)
    if method is None:
        method = Method(
            name=setup.method_name,
            instrument_id=instrument_id,
            technique=setup.method_technique,
            created_by=user.actor,
        )
        session.add(method)
        session.flush()
        audit_create(session, user, "method", method.id, method)
    method_id = persisted_id(method.id, "Method")
    analyte = match_analyte(session, method_id, setup)
    if analyte is None:
        analyte = Analyte(name=setup.parameter_name, method_id=method_id, units=setup.units, created_by=user.actor)
        session.add(analyte)
        session.flush()
        audit_create(session, user, "analyte", analyte.id, analyte)
    material = match_material(session, setup)
    if material is None:
        material = ControlMaterial(
            name=setup.material_name,
            lot=setup.control_material_lot,
            qc_level=setup.qc_level,
            matrix=setup.matrix,
            manufacturer=setup.material_manufacturer,
            created_by=user.actor,
        )
        session.add(material)
        session.flush()
        audit_create(session, user, "control_material", material.id, material)
    return instrument, method, analyte, material
