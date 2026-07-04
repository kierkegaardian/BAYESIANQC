"""Add import ingestion batches and parser profiles.

Revision ID: 20260704_0005
Revises: 20260704_0004
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_0005"
down_revision = "20260704_0004"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if table in _tables() and name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    tables = _tables()
    if "qcbacklogitem" in tables:
        columns = _columns("qcbacklogitem")
        if "started_at" not in columns:
            op.add_column("qcbacklogitem", sa.Column("started_at", sa.DateTime(), nullable=True))
        if "started_by" not in columns:
            op.add_column("qcbacklogitem", sa.Column("started_by", sa.String(), nullable=True))

    if "parserprofile" not in tables:
        op.create_table(
            "parserprofile",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("profile_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=True),
            sa.Column("instrument", sa.String(), nullable=True),
            sa.Column("file_extensions", sa.JSON(), nullable=True),
            sa.Column("filename_patterns", sa.JSON(), nullable=True),
            sa.Column("signature", sa.String(), nullable=True),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.UniqueConstraint("name", "version", name="uq_parserprofile_name_version"),
        )
    for name, columns, unique in [
        ("ix_parserprofile_name", ["name"], False),
        ("ix_parserprofile_version", ["version"], False),
        ("ix_parserprofile_source_id", ["source_id"], False),
        ("ix_parserprofile_instrument", ["instrument"], False),
        ("ix_parserprofile_status_type", ["status", "profile_type"], False),
    ]:
        _create_index(name, "parserprofile", columns, unique=unique)

    if "importbatch" not in tables:
        op.create_table(
            "importbatch",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=True),
            sa.Column("source_path", sa.String(), nullable=True),
            sa.Column("file_hash", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("archived_path", sa.String(), nullable=False),
            sa.Column("parser_profile_id", sa.Integer(), nullable=True),
            sa.Column("parser_profile_version", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("failure_reason", sa.String(), nullable=True),
            sa.Column("collector_action", sa.String(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False),
            sa.Column("ready_rows", sa.Integer(), nullable=False),
            sa.Column("exception_rows", sa.Integer(), nullable=False),
            sa.Column("applied_rows", sa.Integer(), nullable=False),
            sa.Column("artifact_count", sa.Integer(), nullable=False),
        )
    for name, columns in [
        ("ix_importbatch_filename", ["filename"]),
        ("ix_importbatch_source_id", ["source_id"]),
        ("ix_importbatch_parser_profile_id", ["parser_profile_id"]),
        ("ix_importbatch_file_hash", ["file_hash"]),
        ("ix_importbatch_hash", ["file_hash"]),
        ("ix_importbatch_received_at", ["received_at"]),
        ("ix_importbatch_status_received", ["status", "received_at"]),
    ]:
        _create_index(name, "importbatch", columns)

    if "instrumentrun" not in tables:
        op.create_table(
            "instrumentrun",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_key", sa.String(), nullable=False),
            sa.Column("instrument", sa.String(), nullable=True),
            sa.Column("source_id", sa.String(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("qc_backlog_item_id", sa.Integer(), nullable=True),
            sa.Column("import_batch_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    for name, columns, unique in [
        ("ix_instrumentrun_run_key", ["run_key"], True),
        ("ix_instrumentrun_key", ["run_key"], False),
        ("ix_instrumentrun_instrument", ["instrument"], False),
        ("ix_instrumentrun_source_id", ["source_id"], False),
        ("ix_instrumentrun_started_at", ["started_at"], False),
        ("ix_instrumentrun_qc_backlog_item_id", ["qc_backlog_item_id"], False),
        ("ix_instrumentrun_import_batch_id", ["import_batch_id"], False),
        ("ix_instrumentrun_status", ["status"], False),
    ]:
        _create_index(name, "instrumentrun", columns, unique=unique)

    if "importrow" not in tables:
        op.create_table(
            "importrow",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("row_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("raw", sa.JSON(), nullable=True),
            sa.Column("parsed_fields", sa.JSON(), nullable=True),
            sa.Column("warnings", sa.JSON(), nullable=True),
            sa.Column("errors", sa.JSON(), nullable=True),
            sa.Column("stream_id", sa.String(), nullable=True),
            sa.Column("instrument_run_id", sa.Integer(), nullable=True),
            sa.Column("qc_backlog_item_id", sa.Integer(), nullable=True),
            sa.Column("qc_record_id", sa.Integer(), nullable=True),
            sa.Column("quarantine_id", sa.Integer(), nullable=True),
            sa.Column("idempotency_key", sa.String(), nullable=False),
        )
    for name, columns in [
        ("ix_importrow_batch_id", ["batch_id"]),
        ("ix_importrow_stream_id", ["stream_id"]),
        ("ix_importrow_instrument_run_id", ["instrument_run_id"]),
        ("ix_importrow_qc_backlog_item_id", ["qc_backlog_item_id"]),
        ("ix_importrow_qc_record_id", ["qc_record_id"]),
        ("ix_importrow_quarantine_id", ["quarantine_id"]),
        ("ix_importrow_idempotency_key", ["idempotency_key"]),
        ("ix_importrow_batch_status", ["batch_id", "status"]),
    ]:
        _create_index(name, "importrow", columns)

    if "importartifact" not in tables:
        op.create_table(
            "importartifact",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("file_hash", sa.String(), nullable=False),
            sa.Column("archived_path", sa.String(), nullable=False),
            sa.Column("linked_import_row_id", sa.Integer(), nullable=True),
            sa.Column("instrument_run_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    for name, columns in [
        ("ix_importartifact_batch_id", ["batch_id"]),
        ("ix_importartifact_file_hash", ["file_hash"]),
        ("ix_importartifact_linked_import_row_id", ["linked_import_row_id"]),
        ("ix_importartifact_instrument_run_id", ["instrument_run_id"]),
        ("ix_importartifact_batch_role", ["batch_id", "role"]),
    ]:
        _create_index(name, "importartifact", columns)

    if "instrumentpeak" not in tables:
        op.create_table(
            "instrumentpeak",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=True),
            sa.Column("import_row_id", sa.Integer(), nullable=True),
            sa.Column("analyte", sa.String(), nullable=True),
            sa.Column("peak_name", sa.String(), nullable=True),
            sa.Column("retention_time", sa.Float(), nullable=True),
            sa.Column("area", sa.Float(), nullable=True),
            sa.Column("height", sa.Float(), nullable=True),
            sa.Column("raw", sa.JSON(), nullable=True),
        )
    for name, columns in [
        ("ix_instrumentpeak_batch_id", ["batch_id"]),
        ("ix_instrumentpeak_artifact_id", ["artifact_id"]),
        ("ix_instrumentpeak_import_row_id", ["import_row_id"]),
        ("ix_instrumentpeak_analyte", ["analyte"]),
    ]:
        _create_index(name, "instrumentpeak", columns)

    if "collectortransferevent" not in tables:
        op.create_table(
            "collectortransferevent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("transfer_id", sa.String(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("source_path", sa.String(), nullable=True),
            sa.Column("message", sa.String(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
        )
    for name, columns in [
        ("ix_collectortransferevent_transfer_id", ["transfer_id"]),
        ("ix_collectortransferevent_status", ["status"]),
        ("ix_collectortransferevent_created_at", ["created_at"]),
        ("ix_collectortransfer_transfer_created", ["transfer_id", "created_at"]),
    ]:
        _create_index(name, "collectortransferevent", columns)


def downgrade() -> None:
    for table in [
        "collectortransferevent",
        "instrumentpeak",
        "importartifact",
        "importrow",
        "instrumentrun",
        "importbatch",
        "parserprofile",
    ]:
        if table in _tables():
            op.drop_table(table)
    if "qcbacklogitem" in _tables():
        columns = _columns("qcbacklogitem")
        if "started_by" in columns:
            op.drop_column("qcbacklogitem", "started_by")
        if "started_at" in columns:
            op.drop_column("qcbacklogitem", "started_at")
