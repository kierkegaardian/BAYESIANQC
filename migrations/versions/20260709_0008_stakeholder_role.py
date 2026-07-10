"""Add the stakeholder API-key role.

Revision ID: 20260709_0008
Revises: 20260704_0007
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op

revision = "20260709_0008"
down_revision = "20260704_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'stakeholder'")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained on downgrade.
    pass
