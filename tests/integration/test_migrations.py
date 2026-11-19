"""Alembic upgrade, check and downgrade on an empty database (AC9, AC10).

Plain sync tests, because env.py calls `asyncio.run` itself. They use their own
database, recreated for each test, and inspect it with psycopg's sync mode.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import produce_migrations
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.db.autogenerate import CHECKPOINT_TABLES, include_name
from app.db.base import Base
from tests.db_support import TEST_SUFFIX, derived_url, ensure_database

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.db


@pytest.fixture
def migrations_url(test_database_url: URL) -> URL:
    """`<name>_migrations_test`, dropped and recreated so every test starts empty."""
    base = test_database_url.set(database=(test_database_url.database or "")[: -len(TEST_SUFFIX)])
    url = derived_url(base, f"_migrations{TEST_SUFFIX}")
    asyncio.run(ensure_database(url, recreate=True))
    return url


@pytest.fixture
def alembic_config(migrations_url: URL) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = migrations_url.render_as_string(hide_password=False)
    return config


@pytest.fixture
def sync_engine(migrations_url: URL) -> Iterator[Engine]:
    engine = create_engine(migrations_url, poolclass=NullPool)
    yield engine
    engine.dispose()


def public_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def autogenerate_ops(engine: Engine) -> list[object]:
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"include_name": include_name, "target_metadata": Base.metadata}
        )
        return list(produce_migrations(context, Base.metadata).upgrade_ops.ops)  # type: ignore[union-attr]


def create_checkpoint_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA langgraph"))
        for schema in ("public", "langgraph"):
            for table in sorted(CHECKPOINT_TABLES):
                connection.execute(text(f"CREATE TABLE {schema}.{table} (id integer)"))


def checkpoint_tables_present(engine: Engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        schema: set(inspector.get_table_names(schema=schema)) & CHECKPOINT_TABLES
        for schema in ("public", "langgraph")
    }


def test_upgrade_check_and_downgrade_on_an_empty_database(
    alembic_config: Config, sync_engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")
    assert public_tables(sync_engine) == {"alembic_version"}
    command.check(alembic_config)
    command.downgrade(alembic_config, "base")
    with sync_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0


def test_checkpoint_tables_are_ignored_and_survive(
    alembic_config: Config, sync_engine: Engine
) -> None:
    create_checkpoint_tables(sync_engine)
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
    assert autogenerate_ops(sync_engine) == []
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    assert checkpoint_tables_present(sync_engine) == {
        "public": set(CHECKPOINT_TABLES),
        "langgraph": set(CHECKPOINT_TABLES),
    }
