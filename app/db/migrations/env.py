"""Alembic environment, from Alembic's async template. Online mode only.

The URL comes from `config.attributes["database_url"]` when a test sets it, otherwise
from DATABASE_URL in the settings. A command-line run sends Alembic's log lines through
our JSON logging; a programmatic run (tests) leaves logging alone.
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.autogenerate import include_name
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    url = config.attributes.get("database_url")
    if isinstance(url, str):
        return url
    return get_settings().database_url.get_secret_value()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported in ApplyIQ.")

# cmd_opts is set only when Alembic runs from the command line.
if config.cmd_opts is not None:
    configure_logging(get_settings().log_level)

asyncio.run(run_async_migrations())
