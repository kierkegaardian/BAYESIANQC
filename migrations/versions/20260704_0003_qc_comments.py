"""Add contextual QC comments.

Revision ID: 20260704_0003
Revises: 20260703_0002
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_0003"
down_revision = "20260703_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qccomment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("stream_id", sa.String(), nullable=True),
        sa.Column("qc_record_id", sa.Integer(), nullable=True),
        sa.Column("alert_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for name, columns in [
        ("ix_qccomment_target_id", ["target_id"]),
        ("ix_qccomment_stream_id", ["stream_id"]),
        ("ix_qccomment_qc_record_id", ["qc_record_id"]),
        ("ix_qccomment_alert_id", ["alert_id"]),
        ("ix_qccomment_run_id", ["run_id"]),
        ("ix_qccomment_api_key_id", ["api_key_id"]),
        ("ix_qccomment_created_at", ["created_at"]),
        ("ix_qccomment_target_created", ["target_type", "target_id", "created_at"]),
        ("ix_qccomment_stream_created", ["stream_id", "created_at"]),
        ("ix_qccomment_qc_record_created", ["qc_record_id", "created_at"]),
        ("ix_qccomment_alert_created", ["alert_id", "created_at"]),
        ("ix_qccomment_run_created", ["run_id", "created_at"]),
    ]:
        op.create_index(name, "qccomment", columns)


def downgrade() -> None:
    for name in [
        "ix_qccomment_run_created",
        "ix_qccomment_alert_created",
        "ix_qccomment_qc_record_created",
        "ix_qccomment_stream_created",
        "ix_qccomment_target_created",
        "ix_qccomment_created_at",
        "ix_qccomment_api_key_id",
        "ix_qccomment_run_id",
        "ix_qccomment_alert_id",
        "ix_qccomment_qc_record_id",
        "ix_qccomment_stream_id",
        "ix_qccomment_target_id",
    ]:
        op.drop_index(name, table_name="qccomment")
    op.drop_table("qccomment")
