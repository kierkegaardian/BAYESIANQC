from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def run_alembic_migrations(engine: Engine, *, revision: str = "head") -> None:
    config = _alembic_config(engine.url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
