"""Add workflow scope and enforce link integrity.

Revision ID: 20260709_0009
Revises: 20260709_0008
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260709_0009"
down_revision = "20260709_0008"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_scope_column(table: str, composite_index: str) -> None:
    if "stream_id" not in _columns(table):
        op.add_column(table, sa.Column("stream_id", sa.String(), nullable=True))
    indexes = _indexes(table)
    single_index = f"ix_{table}_stream_id"
    if single_index not in indexes:
        op.create_index(single_index, table, ["stream_id"])
    if composite_index not in indexes:
        op.create_index(composite_index, table, ["stream_id", "created_at"])


def _preflight_scope_conflicts() -> None:
    bind = op.get_bind()
    conflicting_investigation = bind.execute(
        sa.text(
            """
            SELECT link.investigation_id
            FROM investigationalertlink link JOIN alertrecord alert ON alert.id = link.alert_id
            GROUP BY link.investigation_id HAVING COUNT(DISTINCT alert.stream_id) > 1 LIMIT 1
            """
        )
    ).first()
    if conflicting_investigation is not None:
        raise RuntimeError("Cannot backfill an investigation linked to alerts from multiple streams")
    conflicting_capa = bind.execute(
        sa.text(
            """
            WITH linked_streams AS (
                SELECT link.capa_id, alert.stream_id
                FROM capalink link JOIN alertrecord alert ON alert.id = link.alert_id
                UNION ALL
                SELECT link.capa_id, alert.stream_id
                FROM capalink link
                JOIN investigationalertlink investigation_link
                  ON investigation_link.investigation_id = link.investigation_id
                JOIN alertrecord alert ON alert.id = investigation_link.alert_id
            )
            SELECT capa_id FROM linked_streams
            GROUP BY capa_id HAVING COUNT(DISTINCT stream_id) > 1 LIMIT 1
            """
        )
    ).first()
    if conflicting_capa is not None:
        raise RuntimeError("Cannot backfill a CAPA linked to workflow records from multiple streams")


def _backfill_scope() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE investigation SET stream_id = source.stream_id
            FROM (
                SELECT link.investigation_id, MIN(alert.stream_id) AS stream_id
                FROM investigationalertlink link JOIN alertrecord alert ON alert.id = link.alert_id
                GROUP BY link.investigation_id
            ) source
            WHERE investigation.id = source.investigation_id AND investigation.stream_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            WITH linked_streams AS (
                SELECT link.capa_id, alert.stream_id
                FROM capalink link JOIN alertrecord alert ON alert.id = link.alert_id
                UNION ALL
                SELECT link.capa_id, investigation.stream_id
                FROM capalink link JOIN investigation ON investigation.id = link.investigation_id
                WHERE investigation.stream_id IS NOT NULL
            ), scope AS (
                SELECT capa_id, MIN(stream_id) AS stream_id FROM linked_streams GROUP BY capa_id
            )
            UPDATE capa SET stream_id = scope.stream_id
            FROM scope WHERE capa.id = scope.capa_id AND capa.stream_id IS NULL
            """
        )
    )


def _foreign_keys(table: str) -> list[dict[str, object]]:
    return list(sa.inspect(op.get_bind()).get_foreign_keys(table))


def _uniques(table: str) -> list[dict[str, object]]:
    return list(sa.inspect(op.get_bind()).get_unique_constraints(table))


def _has_fk(table: str, column: str, target: str) -> bool:
    return any(
        fk.get("constrained_columns") == [column] and fk.get("referred_table") == target
        for fk in _foreign_keys(table)
    )


def _has_unique(table: str, columns: list[str]) -> bool:
    return any(constraint.get("column_names") == columns for constraint in _uniques(table))


def _preflight() -> None:
    bind = op.get_bind()
    checks = {
        "orphan investigation link": """
            SELECT 1 FROM investigationalertlink link
            LEFT JOIN investigation row ON row.id = link.investigation_id WHERE row.id IS NULL LIMIT 1
        """,
        "orphan investigation alert": """
            SELECT 1 FROM investigationalertlink link
            LEFT JOIN alertrecord row ON row.id = link.alert_id WHERE row.id IS NULL LIMIT 1
        """,
        "duplicate investigation-alert link": """
            SELECT 1 FROM investigationalertlink GROUP BY investigation_id, alert_id HAVING COUNT(*) > 1 LIMIT 1
        """,
        "orphan CAPA link": """
            SELECT 1 FROM capalink link LEFT JOIN capa row ON row.id = link.capa_id WHERE row.id IS NULL LIMIT 1
        """,
        "orphan CAPA alert": """
            SELECT 1 FROM capalink link LEFT JOIN alertrecord row ON row.id = link.alert_id
            WHERE link.alert_id IS NOT NULL AND row.id IS NULL LIMIT 1
        """,
        "orphan CAPA investigation": """
            SELECT 1 FROM capalink link LEFT JOIN investigation row ON row.id = link.investigation_id
            WHERE link.investigation_id IS NOT NULL AND row.id IS NULL LIMIT 1
        """,
        "duplicate CAPA link": "SELECT 1 FROM capalink GROUP BY capa_id HAVING COUNT(*) > 1 LIMIT 1",
    }
    for label, statement in checks.items():
        if bind.execute(sa.text(statement)).first() is not None:
            raise RuntimeError(f"Cannot enforce workflow integrity: {label}")


def upgrade() -> None:
    _preflight()
    _preflight_scope_conflicts()
    _add_scope_column("investigation", "ix_investigation_stream_created")
    _add_scope_column("capa", "ix_capa_stream_created")
    _backfill_scope()
    foreign_keys = [
        ("investigationalertlink", "investigation_id", "investigation", "id", "CASCADE"),
        ("investigationalertlink", "alert_id", "alertrecord", "id", "RESTRICT"),
        ("capalink", "capa_id", "capa", "id", "CASCADE"),
        ("capalink", "alert_id", "alertrecord", "id", "RESTRICT"),
        ("capalink", "investigation_id", "investigation", "id", "RESTRICT"),
    ]
    for table, column, target, target_column, ondelete in foreign_keys:
        if not _has_fk(table, column, target):
            op.create_foreign_key(
                f"fk_{table}_{column}_{target}",
                table,
                target,
                [column],
                [target_column],
                ondelete=ondelete,
            )
    if not _has_unique("investigationalertlink", ["investigation_id", "alert_id"]):
        op.create_unique_constraint(
            "uq_investigationalertlink_pair",
            "investigationalertlink",
            ["investigation_id", "alert_id"],
        )
    if not _has_unique("capalink", ["capa_id"]):
        op.create_unique_constraint("uq_capalink_capa", "capalink", ["capa_id"])


def downgrade() -> None:
    for table, columns in [
        ("capalink", ["capa_id"]),
        ("investigationalertlink", ["investigation_id", "alert_id"]),
    ]:
        for constraint in _uniques(table):
            if constraint.get("column_names") == columns and constraint.get("name"):
                op.drop_constraint(str(constraint["name"]), table, type_="unique")
    for table in ["capalink", "investigationalertlink"]:
        for constraint in _foreign_keys(table):
            if constraint.get("name"):
                op.drop_constraint(str(constraint["name"]), table, type_="foreignkey")
    for table, composite in [
        ("capa", "ix_capa_stream_created"),
        ("investigation", "ix_investigation_stream_created"),
    ]:
        for index in [composite, f"ix_{table}_stream_id"]:
            if index in _indexes(table):
                op.drop_index(index, table_name=table)
        op.drop_column(table, "stream_id")
