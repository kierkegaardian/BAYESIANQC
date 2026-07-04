"""Add QC backlog work items.

Revision ID: 20260703_0002
Revises: 20260703_0001
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    qcrecord_columns = {column["name"] for column in inspector.get_columns("qcrecord")}
    qcrecord_indexes = {index["name"] for index in inspector.get_indexes("qcrecord")}
    if "qc_backlog_item_id" not in qcrecord_columns:
        op.add_column("qcrecord", sa.Column("qc_backlog_item_id", sa.Integer(), nullable=True))
    if "ix_qcrecord_qc_backlog_item_id" not in qcrecord_indexes:
        op.create_index("ix_qcrecord_qc_backlog_item_id", "qcrecord", ["qc_backlog_item_id"])
    op.create_table(
        "qcbacklogitem",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("stream_id", sa.String(), nullable=False),
        sa.Column("analyte", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("site", sa.String(), nullable=True),
        sa.Column("qc_level", sa.String(), nullable=False),
        sa.Column("units", sa.String(), nullable=False),
        sa.Column("reference_material_lot", sa.String(), nullable=False),
        sa.Column("reference_material_label", sa.String(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("lab_bench", sa.String(), nullable=True),
        sa.Column("assignment_group", sa.String(), nullable=True),
        sa.Column("assigned_to", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.String(), nullable=True),
        sa.Column("completed_qc_record_id", sa.Integer(), nullable=True),
        sa.Column("last_quarantine_id", sa.Integer(), nullable=True),
    )
    for name, columns in [
        ("ix_qcbacklogitem_stream_id", ["stream_id"]),
        ("ix_qcbacklogitem_instrument", ["instrument"]),
        ("ix_qcbacklogitem_due_at", ["due_at"]),
        ("ix_qcbacklogitem_lab_bench", ["lab_bench"]),
        ("ix_qcbacklogitem_assignment_group", ["assignment_group"]),
        ("ix_qcbacklogitem_assigned_to", ["assigned_to"]),
        ("ix_qcbacklogitem_completed_qc_record_id", ["completed_qc_record_id"]),
        ("ix_qcbacklogitem_last_quarantine_id", ["last_quarantine_id"]),
        ("ix_qcbacklogitem_status_due", ["status", "due_at"]),
        ("ix_qcbacklogitem_instrument_due", ["instrument", "due_at"]),
        ("ix_qcbacklogitem_bench_due", ["lab_bench", "due_at"]),
        ("ix_qcbacklogitem_group_due", ["assignment_group", "due_at"]),
        ("ix_qcbacklogitem_assignee_due", ["assigned_to", "due_at"]),
        ("ix_qcbacklogitem_stream_due", ["stream_id", "due_at"]),
    ]:
        op.create_index(name, "qcbacklogitem", columns)


def downgrade() -> None:
    for name in [
        "ix_qcbacklogitem_stream_due",
        "ix_qcbacklogitem_assignee_due",
        "ix_qcbacklogitem_group_due",
        "ix_qcbacklogitem_bench_due",
        "ix_qcbacklogitem_instrument_due",
        "ix_qcbacklogitem_status_due",
        "ix_qcbacklogitem_last_quarantine_id",
        "ix_qcbacklogitem_completed_qc_record_id",
        "ix_qcbacklogitem_assigned_to",
        "ix_qcbacklogitem_assignment_group",
        "ix_qcbacklogitem_lab_bench",
        "ix_qcbacklogitem_due_at",
        "ix_qcbacklogitem_instrument",
        "ix_qcbacklogitem_stream_id",
    ]:
        op.drop_index(name, table_name="qcbacklogitem")
    op.drop_table("qcbacklogitem")
    op.drop_index("ix_qcrecord_qc_backlog_item_id", table_name="qcrecord")
    op.drop_column("qcrecord", "qc_backlog_item_id")
