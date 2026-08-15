"""Initial SQLModel schema.

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlmodel import SQLModel

import app.db_models  # noqa: F401

revision = "20260703_0001"
down_revision = None
branch_labels = None
depends_on = None

_INITIAL_TABLE_NAMES = (
    "method",
    "analyte",
    "streamconfig",
    "priorconfig",
    "posteriorstate",
    "qcrecord",
    "qcrecordquarantine",
    "qcevent",
    "alertrecord",
    "investigation",
    "investigationalertlink",
    "capa",
    "capalink",
    "auditentry",
    "ingestionreceipt",
    "apikey",
)


def _initial_tables():
    return [SQLModel.metadata.tables[name] for name in _INITIAL_TABLE_NAMES]


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_initial_instrument() -> None:
    if "instrument" in _tables():
        return
    op.create_table(
        "instrument",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("site", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
    )
    op.create_index("ix_instrument_name", "instrument", ["name"])


def upgrade() -> None:
    _create_initial_instrument()
    SQLModel.metadata.create_all(bind=op.get_bind(), tables=_initial_tables())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables())
    if "instrument" in _tables():
        op.drop_table("instrument")
