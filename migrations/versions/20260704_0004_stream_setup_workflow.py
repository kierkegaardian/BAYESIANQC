"""Add datastream setup, control materials, and saved kiosks.

Revision ID: 20260704_0004
Revises: 20260704_0003
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_0004"
down_revision = "20260704_0003"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_index_if_missing(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    tables = _tables()
    if "controlmaterial" not in tables:
        op.create_table(
            "controlmaterial",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("lot", sa.String(), nullable=False),
            sa.Column("qc_level", sa.String(), nullable=False),
            sa.Column("matrix", sa.String(), nullable=True),
            sa.Column("manufacturer", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.UniqueConstraint("name", "lot", "qc_level", "matrix", name="uq_controlmaterial_identity"),
        )
    for name, columns in [
        ("ix_controlmaterial_name", ["name"]),
        ("ix_controlmaterial_lot", ["lot"]),
        ("ix_controlmaterial_qc_level", ["qc_level"]),
    ]:
        _create_index_if_missing(name, "controlmaterial", columns)

    instrument_columns = _columns("instrument")
    if "lab_bench" not in instrument_columns:
        op.add_column("instrument", sa.Column("lab_bench", sa.String(), nullable=True))
    _create_index_if_missing("ix_instrument_lab_bench", "instrument", ["lab_bench"])

    stream_columns = _columns("streamconfig")
    if "lab_bench" not in stream_columns:
        op.add_column("streamconfig", sa.Column("lab_bench", sa.String(), nullable=True))
    if "control_material_id" not in stream_columns:
        op.add_column("streamconfig", sa.Column("control_material_id", sa.Integer(), nullable=True))
    _create_index_if_missing("ix_streamconfig_lab_bench", "streamconfig", ["lab_bench"])
    _create_index_if_missing("ix_streamconfig_control_material_id", "streamconfig", ["control_material_id"])

    tables = _tables()
    if "kiosklayout" not in tables:
        op.create_table(
            "kiosklayout",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("site", sa.String(), nullable=True),
            sa.Column("lab_bench", sa.String(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
        )
    for name, columns, unique in [
        ("ix_kiosklayout_slug", ["slug"], True),
        ("ix_kiosklayout_id", ["id"], False),
    ]:
        _create_index_if_missing(name, "kiosklayout", columns, unique=unique)

    tables = _tables()
    if "kioskpanel" not in tables:
        op.create_table(
            "kioskpanel",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kiosk_id", sa.Integer(), nullable=False),
            sa.Column("stream_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("start", sa.String(), nullable=True),
            sa.Column("end", sa.String(), nullable=True),
            sa.Column("window_label", sa.String(), nullable=True),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
        )
    for name, columns in [
        ("ix_kioskpanel_kiosk_id", ["kiosk_id"]),
        ("ix_kioskpanel_display_order", ["display_order"]),
        ("ix_kioskpanel_stream_id", ["stream_id"]),
        ("ix_kioskpanel_kiosk_order", ["kiosk_id", "display_order"]),
        ("ix_kioskpanel_stream", ["stream_id"]),
    ]:
        _create_index_if_missing(name, "kioskpanel", columns)


def downgrade() -> None:
    for name in [
        "ix_kioskpanel_stream",
        "ix_kioskpanel_kiosk_order",
        "ix_kioskpanel_stream_id",
        "ix_kioskpanel_display_order",
        "ix_kioskpanel_kiosk_id",
    ]:
        if "kioskpanel" in _tables() and name in _indexes("kioskpanel"):
            op.drop_index(name, table_name="kioskpanel")
    if "kioskpanel" in _tables():
        op.drop_table("kioskpanel")
    for name in ["ix_kiosklayout_id", "ix_kiosklayout_slug"]:
        if "kiosklayout" in _tables() and name in _indexes("kiosklayout"):
            op.drop_index(name, table_name="kiosklayout")
    if "kiosklayout" in _tables():
        op.drop_table("kiosklayout")
    if "streamconfig" in _tables():
        for name in ["ix_streamconfig_control_material_id", "ix_streamconfig_lab_bench"]:
            if name in _indexes("streamconfig"):
                op.drop_index(name, table_name="streamconfig")
        stream_columns = _columns("streamconfig")
        if "control_material_id" in stream_columns:
            op.drop_column("streamconfig", "control_material_id")
        if "lab_bench" in stream_columns:
            op.drop_column("streamconfig", "lab_bench")
    if "instrument" in _tables():
        if "ix_instrument_lab_bench" in _indexes("instrument"):
            op.drop_index("ix_instrument_lab_bench", table_name="instrument")
        if "lab_bench" in _columns("instrument"):
            op.drop_column("instrument", "lab_bench")
    if "controlmaterial" in _tables():
        for name in ["ix_controlmaterial_qc_level", "ix_controlmaterial_lot", "ix_controlmaterial_name"]:
            if name in _indexes("controlmaterial"):
                op.drop_index(name, table_name="controlmaterial")
        op.drop_table("controlmaterial")
