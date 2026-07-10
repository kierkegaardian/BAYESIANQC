from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db_models import Analyte, ControlMaterial, EnterpriseSite, Instrument, LabArea, Method
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


def _site_by_name(session: Session, name: Optional[str]) -> EnterpriseSite | None:
    if not name:
        return None
    return next((row for row in session.exec(select(EnterpriseSite)).all() if same_text(row.name, name)), None)


def _area_by_name(session: Session, site_id: int, name: Optional[str]) -> LabArea | None:
    if not name:
        return None
    rows = session.exec(select(LabArea).where(LabArea.site_id == site_id)).all()
    return next((row for row in rows if same_text(row.name, name)), None)


def _location_labels(session: Session, setup: StreamSetupIn) -> tuple[Optional[int], Optional[int], Optional[str], Optional[str]]:
    if setup.lab_area_id is not None:
        area = session.get(LabArea, setup.lab_area_id)
        if area is None:
            raise HTTPException(status_code=422, detail="lab_area_id not found")
        if setup.site_id is not None and setup.site_id != area.site_id:
            raise HTTPException(status_code=422, detail="lab_area_id does not belong to site_id")
        site = session.get(EnterpriseSite, area.site_id)
        if site is None:
            raise HTTPException(status_code=422, detail="site_id not found")
        return site.id, area.id, site.name, area.name
    if setup.site_id is not None:
        site = session.get(EnterpriseSite, setup.site_id)
        if site is None:
            raise HTTPException(status_code=422, detail="site_id not found")
        return site.id, None, site.name, setup.lab_bench
    return None, None, setup.site, setup.lab_bench


def canonicalize_setup(session: Session, setup: StreamSetupIn) -> StreamSetupIn:
    site_id, lab_area_id, site, lab_bench = _location_labels(session, setup)
    updates: dict[str, object] = {
        "site_id": site_id,
        "lab_area_id": lab_area_id,
        "site": site,
        "lab_bench": lab_bench,
    }
    if setup.instrument_id is not None:
        instrument = session.get(Instrument, setup.instrument_id)
        if instrument is None:
            raise HTTPException(status_code=422, detail="instrument_id not found")
        updates.update(
            {
                "instrument_name": instrument.name,
                "instrument_manufacturer": instrument.manufacturer,
                "instrument_model": instrument.model,
                "site_id": instrument.site_id or site_id,
                "lab_area_id": instrument.lab_area_id or lab_area_id,
                "site": instrument.site or site,
                "lab_bench": instrument.lab_bench or lab_bench,
            }
        )
    if setup.method_id is not None:
        method = session.get(Method, setup.method_id)
        if method is None:
            raise HTTPException(status_code=422, detail="method_id not found")
        if setup.instrument_id is not None and method.instrument_id != setup.instrument_id:
            raise HTTPException(status_code=422, detail="method_id does not belong to instrument_id")
        updates.update({"method_name": method.name, "method_technique": method.technique})
    if setup.analyte_id is not None:
        analyte = session.get(Analyte, setup.analyte_id)
        if analyte is None:
            raise HTTPException(status_code=422, detail="analyte_id not found")
        if setup.method_id is not None and analyte.method_id != setup.method_id:
            raise HTTPException(status_code=422, detail="analyte_id does not belong to method_id")
        updates.update({"parameter_name": analyte.name, "units": analyte.units or setup.units})
    if setup.control_material_id is not None:
        material = session.get(ControlMaterial, setup.control_material_id)
        if material is None:
            raise HTTPException(status_code=422, detail="control_material_id not found")
        updates.update(
            {
                "material_name": material.name,
                "material_manufacturer": material.manufacturer,
                "matrix": material.matrix,
                "qc_level": material.qc_level,
                "control_material_lot": material.lot,
            }
        )
    return setup.model_copy(update=updates)


def match_instrument(session: Session, setup: StreamSetupIn) -> Optional[Instrument]:
    if setup.instrument_id is not None:
        row = session.get(Instrument, setup.instrument_id)
        return row if row and row.active else None
    _, _, site, lab_bench = _location_labels(session, setup)
    for row in session.exec(select(Instrument).where(Instrument.active == True)).all():  # noqa: E712
        if (
            same_text(row.name, setup.instrument_name)
            and same_text(row.site, site)
            and same_text(row.lab_bench, lab_bench)
        ):
            return row
    return None


def match_method(session: Session, instrument_id: int, setup: StreamSetupIn) -> Optional[Method]:
    if setup.method_id is not None:
        row = session.get(Method, setup.method_id)
        return row if row and row.active and row.instrument_id == instrument_id else None
    rows = session.exec(select(Method).where(Method.instrument_id == instrument_id, Method.active == True)).all()  # noqa: E712
    for row in rows:
        if same_text(row.name, setup.method_name):
            return row
    return None


def match_analyte(session: Session, method_id: int, setup: StreamSetupIn) -> Optional[Analyte]:
    if setup.analyte_id is not None:
        row = session.get(Analyte, setup.analyte_id)
        return row if row and row.active and row.method_id == method_id else None
    rows = session.exec(select(Analyte).where(Analyte.method_id == method_id, Analyte.active == True)).all()  # noqa: E712
    for row in rows:
        if same_text(row.name, setup.parameter_name):
            return row
    return None


def match_material(session: Session, setup: StreamSetupIn) -> Optional[ControlMaterial]:
    if setup.control_material_id is not None:
        row = session.get(ControlMaterial, setup.control_material_id)
        return row if row and row.active else None
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


def _ensure_location(session: Session, setup: StreamSetupIn, user: UserContext) -> tuple[Optional[int], Optional[int], Optional[str], Optional[str]]:
    if setup.lab_area_id is not None or setup.site_id is not None:
        return _location_labels(session, setup)
    if not setup.site:
        return None, None, setup.site, setup.lab_bench
    site = _site_by_name(session, setup.site)
    if site is None:
        site = EnterpriseSite(name=setup.site, created_by=user.actor)
        session.add(site)
        session.flush()
        audit_create(session, user, "enterprise_site", site.id, site)
    if site.id is None:
        raise RuntimeError("Enterprise site missing id")
    area_id: Optional[int] = None
    if setup.lab_bench:
        area = _area_by_name(session, site.id, setup.lab_bench)
        if area is None:
            area = LabArea(site_id=site.id, name=setup.lab_bench, created_by=user.actor)
            session.add(area)
            session.flush()
            audit_create(session, user, "lab_area", area.id, area)
        area_id = area.id
    return site.id, area_id, site.name, setup.lab_bench


def ensure_assets(session: Session, setup: StreamSetupIn, user: UserContext) -> tuple[Instrument, Method, Analyte, ControlMaterial]:
    setup = canonicalize_setup(session, setup)
    site_id, lab_area_id, site, lab_bench = _ensure_location(session, setup, user)
    instrument = match_instrument(session, setup)
    if instrument is None:
        instrument = Instrument(
            name=setup.instrument_name,
            manufacturer=setup.instrument_manufacturer,
            model=setup.instrument_model,
            site_id=site_id,
            lab_area_id=lab_area_id,
            site=site,
            lab_bench=lab_bench,
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
