from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session

from app.evaluation_models import (
    EvaluationRecordDiffOut,
    EvaluationReprocessPreviewOut,
    EvaluationTrigger,
)
from app.math.evaluation_engine import EVALUATION_ENGINE_VERSION
from app.services.evaluation_persistence import PersistedEvaluationRun, persist_replay
from app.services.evaluation_state import (
    alert_plan,
    changed_records,
    load_evaluation_state,
    replay_state,
    state_fingerprint,
)


def preview_stream_evaluations(
    session: Session,
    stream_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> EvaluationReprocessPreviewOut:
    state = load_evaluation_state(session, stream_id)
    replay = replay_state(state)
    changes = changed_records(state, replay)
    plans = alert_plan(state, replay)
    page = changes[offset : offset + limit]
    return EvaluationReprocessPreviewOut(
        stream_id=stream_id,
        preview_fingerprint=state_fingerprint(state),
        engine_version=EVALUATION_ENGINE_VERSION,
        records_scanned=len(replay.evaluations),
        records_changed=len(changes),
        alerts_confirmed=sum(plan.outcome == "confirm" for plan in plans),
        alerts_superseded=sum(plan.outcome == "supersede" for plan in plans),
        alerts_to_create=sum(plan.outcome == "create" for plan in plans),
        offset=offset,
        limit=limit,
        truncated=offset + limit < len(changes),
        changes=[
            EvaluationRecordDiffOut(
                record_id=change.evaluation.record_id,
                timestamp=change.evaluation.timestamp,
                old_disposition=change.old_disposition,
                new_disposition=change.evaluation.disposition.value,
                old_rule_ids=list(change.old_rule_ids),
                new_rule_ids=[signal.rule for signal in change.evaluation.signals],
                old_risk_score=change.old_risk_score,
                new_risk_score=(
                    change.evaluation.risk.risk_score
                    if change.evaluation.risk is not None
                    else 0
                ),
            )
            for change in page
        ],
    )


def reprocess_stream_evaluations(
    session: Session,
    stream_id: str,
    *,
    trigger: EvaluationTrigger,
    actor: str,
    reason: str,
    record_ids: set[int] | None = None,
    commit: bool = True,
) -> PersistedEvaluationRun:
    state = load_evaluation_state(session, stream_id)
    replay = replay_state(state)
    persisted = persist_replay(
        session,
        stream_id=stream_id,
        state=state,
        replay=replay,
        trigger=trigger,
        actor=actor,
        reason=reason,
        input_fingerprint=state_fingerprint(state),
        record_ids=record_ids,
    )
    if commit:
        session.commit()
    return persisted


def apply_stream_reprocessing(
    session: Session,
    stream_id: str,
    *,
    preview_fingerprint: str,
    actor: str,
    reason: str,
    commit: bool = True,
) -> PersistedEvaluationRun:
    state = load_evaluation_state(session, stream_id)
    current_fingerprint = state_fingerprint(state)
    if current_fingerprint != preview_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation preview is stale; generate a new preview before applying",
        )
    replay = replay_state(state)
    persisted = persist_replay(
        session,
        stream_id=stream_id,
        state=state,
        replay=replay,
        trigger=EvaluationTrigger.MANUAL_REPROCESS,
        actor=actor,
        reason=reason,
        input_fingerprint=current_fingerprint,
    )
    if commit:
        session.commit()
    return persisted
