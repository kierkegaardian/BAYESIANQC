from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.db_models import ControlMaterial, KioskLayout, KioskPanel, PriorConfig, StreamConfig
from app.math.prior import prior_beta_from_sigma
from app.models import PriorConfigIn, PriorConfigOut, StreamConfigIn, StreamConfigOut
from app.rbac import UserContext
from app.services.kiosks import kiosk_layout_out
from app.services.evaluation_pending import historical_reprocess_required
from app.services.locks import stream_write_lock
from app.services.stream_setup_assets import (
    audit_create,
    control_material_out,
    ensure_assets,
    match_analyte,
    match_instrument,
    match_material,
    match_method,
    persisted_id,
)
from app.storage import (
    create_prior_config,
    create_stream_config,
    record_audit,
    validate_stream_control_limits,
)
from app.stream_setup_models import (
    KioskLayoutOut,
    StreamSetupAction,
    StreamSetupApplyOut,
    StreamSetupApplyRow,
    StreamSetupBatchIn,
    StreamSetupIn,
    StreamSetupPreviewOut,
    StreamSetupPreviewRow,
)


def stream_out(session: Session, row: StreamConfig) -> StreamConfigOut:
    return StreamConfigOut(
        **row.model_dump(),
        evaluation_reprocess_required=historical_reprocess_required(session, row.stream_id),
    )


def prior_out(session: Session, row: PriorConfig) -> PriorConfigOut:
    return PriorConfigOut(
        **row.model_dump(),
        evaluation_reprocess_required=historical_reprocess_required(session, row.stream_id),
    )


def _latest_stream(session: Session, stream_id: str) -> StreamConfig | None:
    return session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id)
        .order_by(col(StreamConfig.version).desc())
        .limit(1)
    ).first()


def _latest_prior(session: Session, stream_id: str) -> PriorConfig | None:
    return session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(col(PriorConfig.version).desc())
        .limit(1)
    ).first()


def _stream_payload(setup: StreamSetupIn, material_id: int | None) -> StreamConfigIn:
    return StreamConfigIn(
        stream_id=setup.stream_id,
        analyte=setup.parameter_name,
        method=setup.method_name,
        instrument=setup.instrument_name,
        site=setup.site,
        lab_bench=setup.lab_bench,
        matrix=setup.matrix,
        qc_level=setup.qc_level,
        control_material_lot=setup.control_material_lot,
        control_material_id=material_id,
        units=setup.units,
        target_value=setup.target_value,
        sigma=setup.sigma,
        warning_limit_sd=setup.warning_limit_sd,
        action_limit_sd=setup.action_limit_sd,
        min_value=setup.min_value,
        max_value=setup.max_value,
        control_limit_source=setup.control_limit_source,
        baseline_start=setup.baseline_start,
        baseline_end=setup.baseline_end,
        risk_threshold_warn=setup.risk_threshold_warn,
        risk_threshold_hold=setup.risk_threshold_hold,
        bayes_warn_prob_threshold=setup.bayes_warn_prob_threshold,
        bayes_warn_consecutive=setup.bayes_warn_consecutive,
        bayes_hold_prob_threshold=setup.bayes_hold_prob_threshold,
        bayes_hold_consecutive=setup.bayes_hold_consecutive,
        effective_from=setup.effective_from,
    )


def _prior_payload(setup: StreamSetupIn) -> PriorConfigIn:
    return PriorConfigIn(
        stream_id=setup.stream_id,
        mu0=setup.prior_mu0 if setup.prior_mu0 is not None else setup.target_value,
        kappa0=setup.prior_kappa0,
        alpha0=setup.prior_alpha0,
        beta0=(
            setup.prior_beta0
            if setup.prior_beta0 is not None
            else prior_beta_from_sigma(setup.prior_alpha0, setup.sigma)
        ),
        effective_from=setup.prior_effective_from or setup.effective_from,
    )


def _stream_matches(existing: StreamConfig, payload: StreamConfigIn) -> bool:
    data = payload.model_dump(exclude={"effective_from", "control_material_id"})
    current = existing.model_dump()
    return all(current.get(key) == value for key, value in data.items())


def _prior_matches(existing: PriorConfig, payload: PriorConfigIn) -> bool:
    return (
        existing.stream_id == payload.stream_id
        and existing.mu0 == payload.mu0
        and existing.kappa0 == payload.kappa0
        and existing.alpha0 == payload.alpha0
        and existing.beta0 == payload.beta0
    )


def _preview_one(session: Session, setup: StreamSetupIn, row_number: int) -> StreamSetupPreviewRow:
    errors: list[str] = []
    actions: list[StreamSetupAction] = []
    instrument = match_instrument(session, setup)
    actions.append(StreamSetupAction(entity="instrument", action="reuse" if instrument else "create", detail=setup.instrument_name))
    method = match_method(session, instrument.id, setup) if instrument and instrument.id else None
    actions.append(StreamSetupAction(entity="method", action="reuse" if method else "create", detail=setup.method_name))
    analyte = match_analyte(session, method.id, setup) if method and method.id else None
    actions.append(StreamSetupAction(entity="parameter", action="reuse" if analyte else "create", detail=setup.parameter_name))
    material = match_material(session, setup)
    actions.append(StreamSetupAction(entity="control_material", action="reuse" if material else "create", detail=setup.control_material_lot))

    stream_payload = _stream_payload(setup, material.id if material else None)
    try:
        validate_stream_control_limits(session, stream_payload)
    except ValueError as exc:
        errors.append(str(exc))
    stream = _latest_stream(session, setup.stream_id)
    if stream is None:
        actions.append(StreamSetupAction(entity="stream", action="create", detail=setup.stream_id))
    elif _stream_matches(stream, stream_payload):
        actions.append(StreamSetupAction(entity="stream", action="reuse", detail=setup.stream_id))
    elif setup.config_reason:
        actions.append(StreamSetupAction(entity="stream", action="version", detail=setup.config_reason))
    else:
        errors.append("Existing stream differs; config_reason is required to create a new version")

    prior_payload = _prior_payload(setup)
    prior = _latest_prior(session, setup.stream_id)
    prior_action = "create" if prior is None else "reuse" if _prior_matches(prior, prior_payload) else "version"
    actions.append(StreamSetupAction(entity="prior", action=prior_action, detail=setup.stream_id))
    if setup.kiosk and setup.kiosk.kiosk_slug:
        kiosk = session.exec(select(KioskLayout).where(KioskLayout.slug == setup.kiosk.kiosk_slug)).first()
        actions.append(
            StreamSetupAction(
                entity="kiosk",
                action="append" if kiosk else "create",
                detail=setup.kiosk.kiosk_slug,
            )
        )
    return StreamSetupPreviewRow(
        row=row_number,
        stream_id=setup.stream_id,
        valid=not errors,
        errors=errors,
        actions=actions,
        canonical=setup,
    )


def preview_stream_setups(session: Session, payload: StreamSetupBatchIn) -> StreamSetupPreviewOut:
    rows = [_preview_one(session, setup, index) for index, setup in enumerate(payload.rows, start=1)]
    return StreamSetupPreviewOut(
        valid=sum(1 for row in rows if row.valid),
        invalid=sum(1 for row in rows if not row.valid),
        rows=rows,
    )


def _ensure_stream(session: Session, setup: StreamSetupIn, material: ControlMaterial, user: UserContext) -> StreamConfig:
    payload = _stream_payload(setup, material.id)
    existing = _latest_stream(session, setup.stream_id)
    if existing and _stream_matches(existing, payload):
        return existing
    if existing and not setup.config_reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="config_reason is required for changed streams")
    config = create_stream_config(session, payload, user.actor, commit=False)
    record_audit(
        session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_stream" if existing is None else "create_stream_version",
        entity_type="stream_config",
        entity_id=str(config.id),
        before=existing.model_dump(mode="json") if existing else None,
        after=config.model_dump(mode="json"),
        reason=setup.config_reason,
        commit=False,
    )
    return config


def _ensure_prior(session: Session, setup: StreamSetupIn, user: UserContext) -> PriorConfig:
    payload = _prior_payload(setup)
    existing = _latest_prior(session, setup.stream_id)
    if existing and _prior_matches(existing, payload):
        return existing
    config = create_prior_config(session, setup.stream_id, payload, user.actor, commit=False)
    audit_create(session, user, "prior", config.id, config, reason=setup.config_reason)
    return config


def _ensure_kiosk(session: Session, setup: StreamSetupIn, user: UserContext) -> KioskLayoutOut | None:
    if not setup.kiosk or not setup.kiosk.kiosk_slug:
        return None
    layout = session.exec(select(KioskLayout).where(KioskLayout.slug == setup.kiosk.kiosk_slug)).first()
    if layout is None:
        layout = KioskLayout(
            slug=setup.kiosk.kiosk_slug,
            label=setup.kiosk.kiosk_label or setup.kiosk.kiosk_slug,
            site=setup.site,
            lab_bench=setup.lab_bench,
            created_by=user.actor,
        )
        session.add(layout)
        session.flush()
        audit_create(session, user, "kiosk_layout", layout.id, layout)
    next_order = session.exec(
        select(KioskPanel.display_order)
        .where(KioskPanel.kiosk_id == layout.id)
        .order_by(col(KioskPanel.display_order).desc())
        .limit(1)
    ).first()
    title = setup.kiosk.panel_title or f"{setup.parameter_name} - {setup.instrument_name}"
    panel = KioskPanel(
        kiosk_id=persisted_id(layout.id, "Kiosk layout"),
        stream_id=setup.stream_id,
        title=title,
        display_order=int(next_order or 0) + 1,
        start=setup.kiosk.panel_start,
        end=setup.kiosk.panel_end,
        window_label=setup.kiosk.panel_window_label,
        mode=setup.kiosk.mode,
        created_by=user.actor,
    )
    session.add(panel)
    session.flush()
    audit_create(session, user, "kiosk_panel", panel.id, panel, reason=title)
    return kiosk_layout_out(session, layout)


def apply_stream_setups(session: Session, payload: StreamSetupBatchIn, user: UserContext) -> StreamSetupApplyOut:
    preview = preview_stream_setups(session, payload)
    invalid = [row for row in preview.rows if not row.valid]
    if invalid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[row.model_dump() for row in invalid])
    applied: list[StreamSetupApplyRow] = []
    try:
        for row_number, setup in enumerate(payload.rows, start=1):
            preview_actions = preview.rows[row_number - 1].actions
            with stream_write_lock(session, setup.stream_id):
                _, _, _, material = ensure_assets(session, setup, user)
                stream = _ensure_stream(session, setup, material, user)
                prior = _ensure_prior(session, setup, user)
                kiosk = _ensure_kiosk(session, setup, user)
                applied.append(
                    StreamSetupApplyRow(
                        row=row_number,
                        stream_id=setup.stream_id,
                        stream=stream_out(session, stream),
                        prior=prior_out(session, prior),
                        control_material=control_material_out(material),
                        kiosk=kiosk,
                        actions=preview_actions,
                    )
                )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return StreamSetupApplyOut(applied=len(applied), rows=applied)
