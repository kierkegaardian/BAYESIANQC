from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.db_models import AlertRecord, QCRecord
from app.evaluation_db_models import AlertEvaluationReconciliation, QCRecordEvaluation
from app.evaluation_models import (
    AlertEvaluationStatus,
    EvaluationProvenanceOut,
    ResolvedControlLimits,
)


def evaluation_provenance(evaluation: QCRecordEvaluation) -> EvaluationProvenanceOut:
    if evaluation.id is None:
        raise RuntimeError("Evaluation snapshot missing id")
    return EvaluationProvenanceOut(
        evaluation_id=evaluation.id,
        run_id=evaluation.run_id,
        evaluated_at=evaluation.evaluated_at,
        engine_version=evaluation.engine_version,
        frequentist_method=evaluation.frequentist_method,
        bayesian_method=evaluation.bayesian_method,
        risk_semantics=evaluation.risk_semantics,
        stream_config_id=evaluation.stream_config_id,
        stream_config_version=evaluation.stream_config_version,
        prior_config_id=evaluation.prior_config_id,
        prior_config_version=evaluation.prior_config_version,
        threshold_mode=evaluation.threshold_mode,
        limits=ResolvedControlLimits(
            source=evaluation.control_limit_source,
            centerline=evaluation.applied_centerline,
            sigma=evaluation.applied_sigma,
            warning_limit_sd=evaluation.warning_limit_sd,
            action_limit_sd=evaluation.action_limit_sd,
            warning_lower=evaluation.warning_lower,
            warning_upper=evaluation.warning_upper,
            action_lower=evaluation.action_lower,
            action_upper=evaluation.action_upper,
            baseline_start=evaluation.baseline_start,
            baseline_end=evaluation.baseline_end,
            baseline_count=evaluation.baseline_count,
        ),
    )


def record_evaluation_provenance(
    session: Session,
    record: QCRecord,
) -> EvaluationProvenanceOut | None:
    if record.current_evaluation_id is None:
        return None
    evaluation = session.get(QCRecordEvaluation, record.current_evaluation_id)
    return evaluation_provenance(evaluation) if evaluation is not None else None


@dataclass(frozen=True)
class AlertEvaluationView:
    evaluation: EvaluationProvenanceOut | None
    status: AlertEvaluationStatus
    current_evaluation_id: int | None
    source_evaluation_id: int | None
    replacement_alert_id: str | None


def alert_evaluation_view(session: Session, alert: AlertRecord) -> AlertEvaluationView:
    record = session.get(QCRecord, alert.qc_record_id) if alert.qc_record_id is not None else None
    current_id = record.current_evaluation_id if record is not None else None
    source = (
        session.get(QCRecordEvaluation, alert.source_evaluation_id)
        if alert.source_evaluation_id is not None
        else None
    )
    latest = None
    if alert.id is not None:
        latest = session.exec(
            select(AlertEvaluationReconciliation)
            .where(AlertEvaluationReconciliation.alert_record_id == alert.id)
            .order_by(col(AlertEvaluationReconciliation.created_at).desc())
        ).first()
    replacement_alert_id = None
    if latest is not None and latest.replacement_alert_record_id is not None:
        replacement = session.get(AlertRecord, latest.replacement_alert_record_id)
        replacement_alert_id = replacement.alert_id if replacement is not None else None

    if latest is not None:
        status = AlertEvaluationStatus(latest.outcome.value)
    elif alert.source_evaluation_id is None:
        status = AlertEvaluationStatus.LEGACY_UNVERIFIED
    else:
        status = AlertEvaluationStatus.CURRENT
    return AlertEvaluationView(
        evaluation=evaluation_provenance(source) if source is not None else None,
        status=status,
        current_evaluation_id=current_id,
        source_evaluation_id=alert.source_evaluation_id,
        replacement_alert_id=replacement_alert_id,
    )
