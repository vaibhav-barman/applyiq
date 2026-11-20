"""Alembic upgrade, check and downgrade on an empty database (AC9, AC10).

Plain sync tests, because env.py calls `asyncio.run` itself. They use their own
database, recreated for each test, and inspect it with psycopg's sync mode.
"""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import produce_migrations
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, column, create_engine, func, insert, inspect, select, table, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.expression import TableClause

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


def checkpoint_table(schema: str, name: str) -> TableClause:
    return table(name, column("id"), schema=schema)


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


def test_upgrade_records_the_single_baseline_head(
    alembic_config: Config, sync_engine: Engine
) -> None:
    script = ScriptDirectory.from_config(alembic_config)
    heads = script.get_heads()
    assert len(heads) == 1
    command.upgrade(alembic_config, "head")
    with sync_engine.connect() as connection:
        assert connection.scalars(text("SELECT version_num FROM alembic_version")).all() == heads
    # Running it again changes nothing.
    command.upgrade(alembic_config, "head")
    assert public_tables(sync_engine) == {"alembic_version"}


def test_downgrade_then_upgrade_again_works(alembic_config: Config, sync_engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
    assert public_tables(sync_engine) == {"alembic_version"}


def test_without_the_filter_autogenerate_would_drop_the_checkpoint_tables(
    alembic_config: Config, sync_engine: Engine
) -> None:
    """Control for AC10: the ignore test above is only meaningful if the tables are visible."""
    create_checkpoint_tables(sync_engine)
    command.upgrade(alembic_config, "head")
    with sync_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
        ops = produce_migrations(context, Base.metadata).upgrade_ops.ops  # type: ignore[union-attr]
    dropped = {op.table_name for op in ops if op.__class__.__name__ == "DropTableOp"}  # type: ignore[attr-defined]
    assert dropped == set(CHECKPOINT_TABLES)


def test_checkpoint_rows_survive_upgrade_and_downgrade(
    alembic_config: Config, sync_engine: Engine
) -> None:
    create_checkpoint_tables(sync_engine)
    with sync_engine.begin() as connection:
        for schema in ("public", "langgraph"):
            for table in sorted(CHECKPOINT_TABLES):
                connection.execute(insert(checkpoint_table(schema, table)).values(id=42))
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    with sync_engine.connect() as connection:
        for schema in ("public", "langgraph"):
            for table in sorted(CHECKPOINT_TABLES):
                count = connection.scalar(
                    select(func.count()).select_from(checkpoint_table(schema, table))
                )
                assert count == 1, f"{schema}.{table}"


def test_alembic_does_not_create_the_langgraph_schema(
    alembic_config: Config, sync_engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")
    with sync_engine.connect() as connection:
        found = connection.scalar(
            text("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'langgraph'")
        )
    assert found == 0


def run_alembic_cli(migrations_url: URL, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the real command line, which reads DATABASE_URL through the settings."""
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "APP_ENV"}}
    env["DATABASE_URL"] = migrations_url.render_as_string(hide_password=False)
    env["APP_ENV"] = "test"
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_command_line_upgrade_downgrade_uses_settings_and_json_logs(
    migrations_url: URL, sync_engine: Engine
) -> None:
    password = migrations_url.password or ""
    up = run_alembic_cli(migrations_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-500:]
    assert public_tables(sync_engine) == {"alembic_version"}
    check = run_alembic_cli(migrations_url, "check")
    assert check.returncode == 0, check.stderr[-500:]
    down = run_alembic_cli(migrations_url, "downgrade", "base")
    assert down.returncode == 0, down.stderr[-500:]
    for output in (up, check, down):
        assert password not in output.stdout + output.stderr
    for output in (up, down):
        lines = [line for line in (output.stdout + output.stderr).splitlines() if line.strip()]
        records = [json.loads(line) for line in lines]  # a non-JSON line fails here
        assert any(record["logger"].startswith("alembic") for record in records)


def test_offline_sql_mode_is_refused(migrations_url: URL) -> None:
    result = run_alembic_cli(migrations_url, "upgrade", "head", "--sql")
    assert result.returncode != 0
    assert "Offline (--sql) migrations are not supported" in result.stdout + result.stderr
