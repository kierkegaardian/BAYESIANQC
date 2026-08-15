from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.db_models import Analyte, Instrument, Method
from app.models import AnalyteOut, MethodOut, Permission, TestCreateIn, TestCreateOut
from app.rbac import UserContext, require_permission
from app.services.access_scopes import stream_context_is_accessible
from app.services.locations import same_text
from app.storage import record_audit

router = APIRouter(prefix="/tests", tags=["tests"])


def _method_out(row: Method) -> MethodOut:
    if row.id is None:
        raise RuntimeError("Method missing id")
    return MethodOut(**row.model_dump())


def _analyte_out(row: Analyte) -> AnalyteOut:
    if row.id is None:
        raise RuntimeError("Analyte missing id")
    return AnalyteOut(**row.model_dump())


def _require_instrument_scope(session: Session, user: UserContext, instrument: Instrument) -> None:
    if stream_context_is_accessible(
        session,
        user,
        stream_id="",
        site=instrument.site,
        lab_bench=instrument.lab_bench,
    ):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target instrument scope is not allowed")


@router.post("", response_model=TestCreateOut)
def create_test(
    payload: TestCreateIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> TestCreateOut:
    instrument = session.get(Instrument, payload.instrument_id)
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")
    _require_instrument_scope(session, user, instrument)
    method = next(
        (
            row
            for row in session.exec(select(Method).where(Method.instrument_id == payload.instrument_id)).all()
            if same_text(row.name, payload.name)
        ),
        None,
    )
    if method is None:
        method = Method(
            instrument_id=payload.instrument_id,
            name=payload.name,
            technique=payload.technique,
            description=payload.description,
            active=payload.active,
            created_by=user.actor,
        )
        session.add(method)
        session.flush()
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="create_method",
            entity_type="method",
            entity_id=str(method.id),
            before=None,
            after=method.model_dump(mode="json"),
            reason=None,
            commit=False,
        )
    if method.id is None:
        raise RuntimeError("Method missing id")
    analyte = next(
        (
            row
            for row in session.exec(select(Analyte).where(Analyte.method_id == method.id)).all()
            if same_text(row.name, payload.analyte_name)
        ),
        None,
    )
    if analyte is not None:
        if not same_text(analyte.units, payload.analyte_units) or analyte.result_resolution != payload.analyte_result_resolution:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Analyte exists with different UOM or resolution")
    else:
        analyte = Analyte(
            method_id=method.id,
            name=payload.analyte_name,
            units=payload.analyte_units,
            result_resolution=payload.analyte_result_resolution,
            description=payload.analyte_description,
            active=payload.active,
            created_by=user.actor,
        )
        session.add(analyte)
        session.flush()
        record_audit(
            session,
            actor=user.actor,
            actor_role=user.role,
            api_key_id=user.api_key_id,
            action="create_analyte",
            entity_type="analyte",
            entity_id=str(analyte.id),
            before=None,
            after=analyte.model_dump(mode="json"),
            reason=None,
            commit=False,
        )
    session.commit()
    session.refresh(method)
    session.refresh(analyte)
    return TestCreateOut(method=_method_out(method), analyte=_analyte_out(analyte))
