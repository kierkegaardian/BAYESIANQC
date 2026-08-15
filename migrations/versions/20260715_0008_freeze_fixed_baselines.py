"""Freeze established fixed-baseline statistics on each config version."""

from __future__ import annotations

import math
from statistics import fmean, stdev

import sqlalchemy as sa
from alembic import op

revision = "20260715_0008"
down_revision = "20260715_0007"

_COLUMNS = (
    ("baseline_centerline", sa.Float()),
    ("baseline_sigma", sa.Float()),
    ("baseline_count", sa.Integer()),
)


def _column_names() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("streamconfig")
    }


def _freeze_fixed_baselines() -> None:
    bind = op.get_bind()
    configs = bind.execute(
        sa.text(
            "SELECT id, stream_id, baseline_start, baseline_end, baseline_centerline, "
            "baseline_sigma, baseline_count FROM streamconfig "
            "WHERE control_limit_source = 'fixed_baseline'"
        )
    ).mappings()
    for config in configs:
        frozen = (
            config["baseline_centerline"],
            config["baseline_sigma"],
            config["baseline_count"],
        )
        if all(value is not None for value in frozen):
            continue
        if any(value is not None for value in frozen):
            raise RuntimeError("fixed-baseline frozen statistics are incomplete")
        values = [
            float(row[0])
            for row in bind.execute(
                sa.text(
                    "SELECT result_value FROM qcrecord WHERE stream_id = :stream_id "
                    "AND include_in_stats = :included AND timestamp >= :baseline_start "
                    "AND timestamp <= :baseline_end"
                ),
                {
                    "stream_id": config["stream_id"],
                    "included": True,
                    "baseline_start": config["baseline_start"],
                    "baseline_end": config["baseline_end"],
                },
            )
        ]
        if len(values) < 2 or any(not math.isfinite(value) for value in values):
            raise RuntimeError("fixed baseline requires at least two finite included results")
        sigma = stdev(values)
        if not math.isfinite(sigma) or sigma <= 0:
            raise RuntimeError("fixed baseline requires positive sample SD")
        bind.execute(
            sa.text(
                "UPDATE streamconfig SET baseline_centerline = :centerline, "
                "baseline_sigma = :sigma, baseline_count = :count WHERE id = :id"
            ),
            {"centerline": fmean(values), "sigma": sigma, "count": len(values), "id": config["id"]},
        )


def upgrade() -> None:
    existing = _column_names()
    for name, column_type in _COLUMNS:
        if name not in existing:
            op.add_column("streamconfig", sa.Column(name, column_type, nullable=True))
    _freeze_fixed_baselines()


def downgrade() -> None:
    existing = _column_names()
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("streamconfig") as batch:
            for name, _ in reversed(_COLUMNS):
                if name in existing:
                    batch.drop_column(name)
    else:
        for name, _ in reversed(_COLUMNS):
            if name in existing:
                op.drop_column("streamconfig", name)
