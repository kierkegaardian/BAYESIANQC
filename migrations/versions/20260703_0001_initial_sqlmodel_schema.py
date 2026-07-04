"""Initial SQLModel schema.

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

import app.db_models  # noqa: F401

revision = "20260703_0001"
down_revision = None
branch_labels = None
depends_on = None

_INITIAL_TABLE_NAMES = (
    "instrument",
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


def upgrade() -> None:
    SQLModel.metadata.create_all(bind=op.get_bind(), tables=_initial_tables())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables())
