"""Engine, session dependency and lifespan (AC5, AC6, AC7, AC8, AC11)."""

import io
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import MetaData, String, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import Settings
from app.db.base import NAMING_CONVENTION, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import SessionDep, build_engine, build_session_factory
from tests.conftest import AppFactory
from tests.settings_support import make_settings

SENTINEL = "zq7-sentinel-parameter-value"


class _TestBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Widget(UUIDPrimaryKeyMixin, TimestampMixin, _TestBase):
    """A test-only table; it never exists outside these tests."""

    __tablename__ = "spec002_widget"

    code: Mapped[str] = mapped_column(String(40), unique=True)


def database_settings(url: URL, **overrides: Any) -> Settings:
    return make_settings(
        app_env="test", database_url=url.render_as_string(hide_password=False), **overrides
    )


@pytest.fixture
async def widget_table(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Create the test table for tests that need real commits; drop it afterwards."""
    async with db_engine.begin() as connection:
        await connection.run_sync(_TestBase.metadata.drop_all)
        await connection.run_sync(_TestBase.metadata.create_all)
    yield db_engine
    async with db_engine.begin() as connection:
        await connection.run_sync(_TestBase.metadata.drop_all)


async def stored_codes(engine: AsyncEngine) -> list[str]:
    async with AsyncSession(engine) as session:
        return list(await session.scalars(select(Widget.code)))


# ---- AC5: mixin values ----


@pytest.mark.db
async def test_insert_gets_uuid_and_utc_timestamps(db_session: AsyncSession) -> None:
    await db_session.run_sync(lambda sync: _TestBase.metadata.create_all(sync.connection()))
    widget = Widget(code="a")
    db_session.add(widget)
    await db_session.flush()
    await db_session.refresh(widget)
    assert isinstance(widget.id, uuid.UUID)
    assert widget.created_at.utcoffset() == timedelta(0)
    assert widget.updated_at.utcoffset() == timedelta(0)


@pytest.mark.db
async def test_each_row_gets_its_own_random_uuid(db_session: AsyncSession) -> None:
    await db_session.run_sync(lambda sync: _TestBase.metadata.create_all(sync.connection()))
    first, second = Widget(code="x1"), Widget(code="x2")
    db_session.add_all([first, second])
    await db_session.flush()
    assert first.id != second.id
    assert first.id.version == 4


@pytest.mark.db
async def test_app_engine_returns_timestamps_in_utc(test_database_url: URL) -> None:
    """`build_engine` sets the session time zone, so timestamptz comes back with offset 0."""
    engine = build_engine(database_settings(test_database_url))
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SHOW timezone")) == "UTC"
            moment = await connection.scalar(text("SELECT now()"))
    finally:
        await engine.dispose()
    assert moment.utcoffset() == timedelta(0)


@pytest.mark.db
async def test_update_moves_updated_at_and_keeps_created_at(widget_table: AsyncEngine) -> None:
    # now() is fixed for a transaction, so the insert and the update commit separately.
    factory = async_sessionmaker(widget_table, expire_on_commit=False)
    async with factory() as session:
        widget = Widget(code="b")
        session.add(widget)
        await session.commit()
        await session.refresh(widget)
        created, updated = widget.created_at, widget.updated_at
    async with factory() as session:
        await session.execute(text("SELECT pg_sleep(0.01)"))
        stored = await session.get_one(Widget, widget.id)
        stored.code = "b2"
        await session.commit()
        await session.refresh(stored)
    assert stored.created_at == created
    assert stored.updated_at > updated


# ---- AC6, AC7: commit and rollback through SessionDep ----


def add_widget_routes(application: FastAPI) -> None:
    async def create_ok(session: SessionDep, code: str) -> dict[str, str]:
        session.add(Widget(code=code))
        return {"status": "ok"}

    async def create_then_fail(session: SessionDep, code: str) -> dict[str, str]:
        session.add(Widget(code=code))
        await session.flush()
        raise RuntimeError("handler failed")

    async def create_then_http_error(session: SessionDep, code: str) -> dict[str, str]:
        session.add(Widget(code=code))
        await session.flush()
        raise HTTPException(status_code=409, detail="conflict")

    application.add_api_route("/test/widgets/conflict", create_then_http_error, methods=["POST"])
    application.add_api_route("/test/widgets", create_ok, methods=["POST"])
    application.add_api_route("/test/widgets/fail", create_then_fail, methods=["POST"])


@pytest.fixture
async def widget_client(
    widget_table: AsyncEngine, test_database_url: URL, make_app: AppFactory
) -> AsyncIterator[httpx.AsyncClient]:
    application = make_app(database_settings(test_database_url))
    add_widget_routes(application)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.db
async def test_route_that_returns_commits(
    widget_client: httpx.AsyncClient, widget_table: AsyncEngine
) -> None:
    response = await widget_client.post("/test/widgets", params={"code": "c"})
    assert response.status_code == 200
    assert await stored_codes(widget_table) == ["c"]


@pytest.mark.db
async def test_route_that_raises_rolls_back(
    widget_client: httpx.AsyncClient, widget_table: AsyncEngine
) -> None:
    response = await widget_client.post("/test/widgets/fail", params={"code": "d"})
    assert response.status_code == 500
    assert await stored_codes(widget_table) == []


@pytest.mark.db
async def test_route_that_raises_an_http_error_rolls_back_and_keeps_its_status(
    widget_client: httpx.AsyncClient, widget_table: AsyncEngine
) -> None:
    response = await widget_client.post("/test/widgets/conflict", params={"code": "h"})
    assert response.status_code == 409
    assert await stored_codes(widget_table) == []


@pytest.mark.db
async def test_each_request_gets_its_own_session(
    widget_client: httpx.AsyncClient, widget_table: AsyncEngine
) -> None:
    """A rolled-back request leaves nothing behind for the next one to commit."""
    await widget_client.post("/test/widgets/fail", params={"code": "f1"})
    assert (await widget_client.post("/test/widgets", params={"code": "f2"})).status_code == 200
    assert await stored_codes(widget_table) == ["f2"]


@pytest.mark.db
async def test_failed_commit_returns_500_not_200(
    widget_client: httpx.AsyncClient, widget_table: AsyncEngine
) -> None:
    assert (await widget_client.post("/test/widgets", params={"code": "e"})).status_code == 200
    # The handler only adds; the unique violation is raised by the commit after it returns.
    response = await widget_client.post("/test/widgets", params={"code": "e"})
    assert response.status_code == 500
    assert await stored_codes(widget_table) == ["e"]


# ---- AC8: lifespan without Postgres ----


async def test_app_serves_health_with_postgres_unreachable_and_disposes_engine(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed: list[AsyncEngine] = []
    original_dispose = AsyncEngine.dispose

    async def spy_dispose(self: AsyncEngine, close: bool = True) -> None:
        disposed.append(self)
        await original_dispose(self, close)

    monkeypatch.setattr(AsyncEngine, "dispose", spy_dispose)
    application = make_app(make_settings(app_env="test"))
    transport = httpx.ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        engine = application.state.engine
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert disposed == []
    assert disposed == [engine]


def test_engine_uses_the_pool_settings() -> None:
    settings = make_settings(
        db_pool_size=3, db_max_overflow=2, db_pool_timeout_seconds=4, db_pool_recycle_seconds=90
    )
    engine = build_engine(settings)
    pool = engine.sync_engine.pool
    assert (pool.size(), pool._max_overflow, pool._timeout, pool._recycle) == (3, 2, 4, 90)  # type: ignore[attr-defined]
    assert pool._pre_ping is True  # type: ignore[attr-defined]


def test_engine_creation_opens_no_connection_and_uses_the_psycopg_driver() -> None:
    engine = build_engine(make_settings())
    assert engine.dialect.driver == "psycopg"
    assert engine.sync_engine.pool.checkedout() == 0


def test_session_factory_keeps_objects_usable_after_commit() -> None:
    factory = build_session_factory(build_engine(make_settings()))
    assert factory.kw["expire_on_commit"] is False


def test_engine_hides_parameters_and_does_not_echo() -> None:
    engine = build_engine(make_settings())
    assert engine.sync_engine.hide_parameters is True
    assert engine.echo is False


# ---- AC11: no parameter values or SQL text in logs or errors ----


@pytest.mark.db
async def test_failed_statement_leaks_no_parameter_or_sql(
    test_database_url: URL, make_app: AppFactory, log_stream: io.StringIO
) -> None:
    settings = database_settings(test_database_url, log_level="DEBUG")
    make_app(settings)  # configures logging at DEBUG into log_stream
    engine = build_engine(settings)
    try:
        with pytest.raises(Exception) as caught:
            async with engine.connect() as connection:
                await connection.execute(
                    text("SELECT CAST(:value AS integer)"), {"value": SENTINEL}
                )
    finally:
        await engine.dispose()
    # Postgres's own message may quote the bad value, so only SQLAlchemy's dump is checked
    # here; exception text must never reach a log line or a response (AC11, amended).
    assert "[SQL parameters hidden due to hide_parameters=True]" in str(caught.value)
    logged = log_stream.getvalue()
    assert SENTINEL not in logged
    assert "SELECT" not in logged
