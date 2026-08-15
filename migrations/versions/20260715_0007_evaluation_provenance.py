"""Add control-limit source and immutable evaluation provenance.

Revision ID: 20260715_0007
Revises: 20260704_0006
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "20260715_0007"
down_revision = "20260704_0006"


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _foreign_keys(table: str) -> set[str]:
    return {key["name"] for key in sa.inspect(op.get_bind()).get_foreign_keys(table) if key["name"]}


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def _validate_legacy_baselines() -> None:
    bind = op.get_bind()
    partial = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM streamconfig "
            "WHERE (baseline_start IS NULL) <> (baseline_end IS NULL)"
        )
    ).scalar_one()
    if partial:
        raise RuntimeError("streamconfig contains a partial legacy baseline range")
    future = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM streamconfig "
            "WHERE baseline_end IS NOT NULL AND baseline_end > effective_from"
        )
    ).scalar_one()
    if future:
        raise RuntimeError("streamconfig baseline_end must not exceed effective_from")


def _add_control_limit_source() -> None:
    if "control_limit_source" in _columns("streamconfig"):
        return
    _validate_legacy_baselines()
    op.add_column(
        "streamconfig",
        sa.Column("control_limit_source", sa.String(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE streamconfig SET control_limit_source = "
            "CASE WHEN baseline_start IS NOT NULL AND baseline_end IS NOT NULL "
            "THEN 'fixed_baseline' ELSE 'configured' END"
        )
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("streamconfig") as batch:
            batch.alter_column(
                "control_limit_source",
                existing_type=sa.String(),
                nullable=False,
            )
    else:
        op.alter_column("streamconfig", "control_limit_source", nullable=False)


def _create_provenance_tables() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "evaluationrun" not in tables:
        op.create_table(
            "evaluationrun",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.String(), nullable=False),
            sa.Column("stream_id", sa.String(), nullable=False),
            sa.Column("trigger", sa.String(), nullable=False),
            sa.Column("engine_version", sa.String(), nullable=False),
            sa.Column("frequentist_method", sa.String(), nullable=False),
            sa.Column("bayesian_method", sa.String(), nullable=False),
            sa.Column("risk_semantics", sa.String(), nullable=False),
            sa.Column("actor", sa.String(), nullable=False),
            sa.Column("reason", sa.String(), nullable=False),
            sa.Column("input_fingerprint", sa.String(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("record_count", sa.Integer(), nullable=False),
            sa.Column("changed_record_count", sa.Integer(), nullable=False),
            sa.Column("alerts_confirmed", sa.Integer(), nullable=False),
            sa.Column("alerts_superseded", sa.Integer(), nullable=False),
            sa.Column("alerts_created", sa.Integer(), nullable=False),
            sa.UniqueConstraint("run_id", name="uq_evaluationrun_run_id"),
        )
        for name, columns, unique in [
            ("ix_evaluationrun_run_id", ["run_id"], True),
            ("ix_evaluationrun_stream_id", ["stream_id"], False),
            ("ix_evaluationrun_input_fingerprint", ["input_fingerprint"], False),
            ("ix_evaluationrun_stream_started", ["stream_id", "started_at"], False),
        ]:
            _create_index(name, "evaluationrun", columns, unique=unique)

    if "qcrecordevaluation" not in tables:
        op.create_table(
            "qcrecordevaluation",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.String(), nullable=False),
            sa.Column("qc_record_id", sa.Integer(), nullable=False),
            sa.Column("evaluated_at", sa.DateTime(), nullable=False),
            sa.Column("engine_version", sa.String(), nullable=False),
            sa.Column("frequentist_method", sa.String(), nullable=False),
            sa.Column("bayesian_method", sa.String(), nullable=False),
            sa.Column("risk_semantics", sa.String(), nullable=False),
            sa.Column("stream_config_id", sa.Integer(), nullable=False),
            sa.Column("stream_config_version", sa.Integer(), nullable=False),
            sa.Column("prior_config_id", sa.Integer(), nullable=True),
            sa.Column("prior_config_version", sa.Integer(), nullable=True),
            sa.Column("threshold_mode", sa.String(), nullable=False),
            sa.Column("control_limit_source", sa.String(), nullable=False),
            sa.Column("applied_centerline", sa.Float(), nullable=False),
            sa.Column("applied_sigma", sa.Float(), nullable=False),
            sa.Column("warning_limit_sd", sa.Float(), nullable=False),
            sa.Column("action_limit_sd", sa.Float(), nullable=False),
            sa.Column("warning_lower", sa.Float(), nullable=False),
            sa.Column("warning_upper", sa.Float(), nullable=False),
            sa.Column("action_lower", sa.Float(), nullable=False),
            sa.Column("action_upper", sa.Float(), nullable=False),
            sa.Column("baseline_start", sa.DateTime(), nullable=True),
            sa.Column("baseline_end", sa.DateTime(), nullable=True),
            sa.Column("baseline_count", sa.Integer(), nullable=True),
            sa.Column("signals", sa.JSON(), nullable=False),
            sa.Column("bayesian_risk", sa.JSON(), nullable=True),
            sa.Column("disposition", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(
                ["run_id"], ["evaluationrun.run_id"], name="fk_qcrecordevaluation_run_id"
            ),
            sa.ForeignKeyConstraint(
                ["qc_record_id"], ["qcrecord.id"], name="fk_qcrecordevaluation_qc_record_id"
            ),
            sa.ForeignKeyConstraint(
                ["stream_config_id"], ["streamconfig.id"], name="fk_qcrecordevaluation_config_id"
            ),
            sa.ForeignKeyConstraint(
                ["prior_config_id"], ["priorconfig.id"], name="fk_qcrecordevaluation_prior_id"
            ),
            sa.UniqueConstraint(
                "run_id", "qc_record_id", name="uq_qcrecordevaluation_run_record"
            ),
        )
        for name, columns in [
            ("ix_qcrecordevaluation_run_id", ["run_id"]),
            ("ix_qcrecordevaluation_qc_record_id", ["qc_record_id"]),
            ("ix_qcrecordevaluation_stream_config_id", ["stream_config_id"]),
            ("ix_qcrecordevaluation_prior_config_id", ["prior_config_id"]),
            ("ix_qcrecordevaluation_record_time", ["qc_record_id", "evaluated_at"]),
        ]:
            _create_index(name, "qcrecordevaluation", columns)


def _ensure_pointer(table: str, column: str, index: str, constraint: str) -> None:
    add_column = column not in _columns(table)
    add_constraint = constraint not in _foreign_keys(table)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            if add_column:
                batch.add_column(sa.Column(column, sa.Integer(), nullable=True))
            if add_constraint:
                batch.create_foreign_key(
                    constraint,
                    "qcrecordevaluation",
                    [column],
                    ["id"],
                    ondelete="SET NULL",
                    deferrable=True,
                    initially="DEFERRED",
                )
    else:
        if add_column:
            op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
        if add_constraint:
            op.create_foreign_key(
                constraint,
                table,
                "qcrecordevaluation",
                [column],
                ["id"],
                ondelete="SET NULL",
                deferrable=True,
                initially="DEFERRED",
            )
    _create_index(index, table, [column])


def _add_current_pointers() -> None:
    _ensure_pointer(
        "qcrecord",
        "current_evaluation_id",
        "ix_qcrecord_current_evaluation_id",
        "fk_qcrecord_current_evaluation_id",
    )
    _ensure_pointer(
        "alertrecord",
        "source_evaluation_id",
        "ix_alertrecord_source_evaluation_id",
        "fk_alertrecord_source_evaluation_id",
    )


def _create_reconciliation_table() -> None:
    if "alertevaluationreconciliation" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "alertevaluationreconciliation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("alert_record_id", sa.Integer(), nullable=False),
        sa.Column("previous_evaluation_id", sa.Integer(), nullable=True),
        sa.Column("current_evaluation_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("replacement_alert_record_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluationrun.run_id"]),
        sa.ForeignKeyConstraint(["alert_record_id"], ["alertrecord.id"]),
        sa.ForeignKeyConstraint(["previous_evaluation_id"], ["qcrecordevaluation.id"]),
        sa.ForeignKeyConstraint(["current_evaluation_id"], ["qcrecordevaluation.id"]),
        sa.ForeignKeyConstraint(["replacement_alert_record_id"], ["alertrecord.id"]),
        sa.UniqueConstraint(
            "run_id", "alert_record_id", name="uq_alertevaluationreconciliation_run_alert"
        ),
    )
    for name, columns in [
        ("ix_alertevaluationreconciliation_run_id", ["run_id"]),
        ("ix_alertevaluationreconciliation_alert_record_id", ["alert_record_id"]),
        ("ix_alertevaluationreconciliation_previous_evaluation_id", ["previous_evaluation_id"]),
        ("ix_alertevaluationreconciliation_current_evaluation_id", ["current_evaluation_id"]),
        ("ix_alertevaluationreconciliation_replacement_alert_record_id", ["replacement_alert_record_id"]),
    ]:
        _create_index(name, "alertevaluationreconciliation", columns)


def upgrade() -> None:
    _add_control_limit_source()
    _create_provenance_tables()
    _add_current_pointers()
    _create_reconciliation_table()


def _drop_pointer(table: str, column: str, index: str, constraint: str) -> None:
    if column not in _columns(table):
        return
    if index in _indexes(table):
        op.drop_index(index, table_name=table)
    has_constraint = constraint in _foreign_keys(table)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            if has_constraint:
                batch.drop_constraint(constraint, type_="foreignkey")
            batch.drop_column(column)
    else:
        if has_constraint:
            op.drop_constraint(constraint, table, type_="foreignkey")
        op.drop_column(table, column)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "alertevaluationreconciliation" in tables:
        op.drop_table("alertevaluationreconciliation")
    _drop_pointer(
        "alertrecord",
        "source_evaluation_id",
        "ix_alertrecord_source_evaluation_id",
        "fk_alertrecord_source_evaluation_id",
    )
    _drop_pointer(
        "qcrecord",
        "current_evaluation_id",
        "ix_qcrecord_current_evaluation_id",
        "fk_qcrecord_current_evaluation_id",
    )
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "qcrecordevaluation" in tables:
        op.drop_table("qcrecordevaluation")
    if "evaluationrun" in tables:
        op.drop_table("evaluationrun")
    if "control_limit_source" in _columns("streamconfig"):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("streamconfig") as batch:
                batch.drop_column("control_limit_source")
        else:
            op.drop_column("streamconfig", "control_limit_source")
