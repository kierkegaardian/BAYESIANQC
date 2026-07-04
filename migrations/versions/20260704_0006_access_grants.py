"""Add API key access grants and scoped ingestion receipts.

Revision ID: 20260704_0006
Revises: 20260704_0005
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_0006"
down_revision = "20260704_0005"
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
    if "accessgrant" not in tables:
        op.create_table(
            "accessgrant",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("api_key_id", sa.Integer(), nullable=False),
            sa.Column("site", sa.String(), nullable=True),
            sa.Column("lab_bench", sa.String(), nullable=True),
            sa.Column("stream_id", sa.String(), nullable=True),
            sa.Column("assignment_group", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("reason", sa.String(), nullable=True),
        )
    for name, columns in [
        ("ix_accessgrant_api_key_id", ["api_key_id"]),
        ("ix_accessgrant_stream_id", ["stream_id"]),
        ("ix_accessgrant_assignment_group", ["assignment_group"]),
        ("ix_accessgrant_api_key_active", ["api_key_id", "active"]),
        ("ix_accessgrant_site_bench", ["site", "lab_bench"]),
    ]:
        _create_index(name, "accessgrant", columns)

    if "ingestionreceipt" in tables:
        columns = _columns("ingestionreceipt")
        if "stream_id" not in columns:
            op.add_column("ingestionreceipt", sa.Column("stream_id", sa.String(), nullable=True))
        if "api_key_id" not in columns:
            op.add_column("ingestionreceipt", sa.Column("api_key_id", sa.Integer(), nullable=True))
        _create_index("ix_ingestionreceipt_stream_id", "ingestionreceipt", ["stream_id"])
        _create_index("ix_ingestionreceipt_api_key_id", "ingestionreceipt", ["api_key_id"])


def downgrade() -> None:
    if "ingestionreceipt" in _tables():
        for name in ["ix_ingestionreceipt_api_key_id", "ix_ingestionreceipt_stream_id"]:
            if name in _indexes("ingestionreceipt"):
                op.drop_index(name, table_name="ingestionreceipt")
        columns = _columns("ingestionreceipt")
        if "api_key_id" in columns:
            op.drop_column("ingestionreceipt", "api_key_id")
        if "stream_id" in columns:
            op.drop_column("ingestionreceipt", "stream_id")
    if "accessgrant" in _tables():
        op.drop_table("accessgrant")
