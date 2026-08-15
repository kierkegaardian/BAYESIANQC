"""Add governed location config and test metadata.

Revision ID: 20260704_0007
Revises: 20260704_0006
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_0007"
down_revision = "20260704_0006"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if table in _tables() and name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def _add_column(table: str, column: sa.Column) -> None:
    if table in _tables() and column.name not in _columns(table):
        op.add_column(table, column)


def _backfill_locations() -> None:
    bind = op.get_bind()
    sources = []
    for table in ["instrument", "streamconfig", "kiosklayout", "qcbacklogitem", "accessgrant"]:
        columns = _columns(table)
        if "site" in columns:
            sources.append(f"SELECT site, {'lab_bench' if 'lab_bench' in columns else 'NULL'} AS lab_bench FROM {table}")
    if not sources or "enterprisesite" not in _tables() or "labarea" not in _tables():
        return
    union_sql = " UNION ALL ".join(sources)
    bind.execute(
        sa.text(
            f"""
            WITH candidates AS (
                SELECT MIN(TRIM(site)) AS name
                FROM ({union_sql}) AS source_rows
                WHERE site IS NOT NULL AND TRIM(site) <> ''
                GROUP BY LOWER(TRIM(site))
            )
            INSERT INTO enterprisesite (name, code, description, active, created_at, created_by)
            SELECT candidates.name, NULL, NULL, TRUE, CURRENT_TIMESTAMP, 'migration'
            FROM candidates
            WHERE NOT EXISTS (
                SELECT 1 FROM enterprisesite existing
                WHERE LOWER(existing.name) = LOWER(candidates.name)
            )
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            WITH pairs AS (
                SELECT MIN(TRIM(site)) AS site_name, MIN(TRIM(lab_bench)) AS area_name
                FROM ({union_sql}) AS source_rows
                WHERE site IS NOT NULL
                  AND lab_bench IS NOT NULL
                  AND TRIM(site) <> ''
                  AND TRIM(lab_bench) <> ''
                GROUP BY LOWER(TRIM(site)), LOWER(TRIM(lab_bench))
            )
            INSERT INTO labarea (site_id, name, description, active, created_at, created_by)
            SELECT site.id, pairs.area_name, NULL, TRUE, CURRENT_TIMESTAMP, 'migration'
            FROM pairs
            JOIN enterprisesite site ON LOWER(site.name) = LOWER(pairs.site_name)
            WHERE NOT EXISTS (
                SELECT 1 FROM labarea existing
                WHERE existing.site_id = site.id
                  AND LOWER(existing.name) = LOWER(pairs.area_name)
            )
            """
        )
    )
    if {"site", "site_id"} <= _columns("instrument"):
        bind.execute(
            sa.text(
                """
                UPDATE instrument
                SET site_id = site.id
                FROM enterprisesite site
                WHERE instrument.site_id IS NULL
                  AND instrument.site IS NOT NULL
                  AND LOWER(TRIM(instrument.site)) = LOWER(site.name)
                """
            )
        )
    if {"site", "lab_bench", "lab_area_id"} <= _columns("instrument"):
        bind.execute(
            sa.text(
                """
                UPDATE instrument
                SET lab_area_id = area.id
                FROM enterprisesite site
                JOIN labarea area ON area.site_id = site.id
                WHERE instrument.lab_area_id IS NULL
                  AND instrument.site IS NOT NULL
                  AND instrument.lab_bench IS NOT NULL
                  AND LOWER(TRIM(instrument.site)) = LOWER(site.name)
                  AND LOWER(TRIM(instrument.lab_bench)) = LOWER(area.name)
                """
            )
        )


def upgrade() -> None:
    if "enterprisesite" not in _tables():
        op.create_table(
            "enterprisesite",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("code", sa.String(), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
        )
    _create_index("ix_enterprisesite_id", "enterprisesite", ["id"])
    _create_index("ix_enterprisesite_name", "enterprisesite", ["name"], unique=True)
    _create_index("ix_enterprisesite_code", "enterprisesite", ["code"], unique=True)

    if "labarea" not in _tables():
        op.create_table(
            "labarea",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["site_id"], ["enterprisesite.id"]),
            sa.UniqueConstraint("site_id", "name", name="uq_labarea_site_name"),
        )
    _create_index("ix_labarea_id", "labarea", ["id"])
    _create_index("ix_labarea_site_id", "labarea", ["site_id"])
    _create_index("ix_labarea_name", "labarea", ["name"])

    _add_column("instrument", sa.Column("site_id", sa.Integer(), nullable=True))
    _add_column("instrument", sa.Column("lab_area_id", sa.Integer(), nullable=True))
    _create_index("ix_instrument_site_id", "instrument", ["site_id"])
    _create_index("ix_instrument_lab_area_id", "instrument", ["lab_area_id"])

    _add_column("method", sa.Column("description", sa.String(), nullable=True))
    _add_column("analyte", sa.Column("result_resolution", sa.Float(), nullable=True))
    _add_column("analyte", sa.Column("description", sa.String(), nullable=True))

    _backfill_locations()


def downgrade() -> None:
    if "analyte" in _tables():
        for column in ["description", "result_resolution"]:
            if column in _columns("analyte"):
                op.drop_column("analyte", column)
    if "method" in _tables() and "description" in _columns("method"):
        op.drop_column("method", "description")
    if "instrument" in _tables():
        for name in ["ix_instrument_lab_area_id", "ix_instrument_site_id"]:
            if name in _indexes("instrument"):
                op.drop_index(name, table_name="instrument")
        for column in ["lab_area_id", "site_id"]:
            if column in _columns("instrument"):
                op.drop_column("instrument", column)
    if "labarea" in _tables():
        op.drop_table("labarea")
    if "enterprisesite" in _tables():
        op.drop_table("enterprisesite")
