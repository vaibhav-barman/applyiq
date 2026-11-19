"""Async engine, session factory and the request-scoped session dependency.

Background graph runs build their own sessions from `app.state.session_factory`;
they never use `get_session`, which belongs to one HTTP request.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the engine. No connection is opened until the first query."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        echo=False,
        # Keeps parameter values (user data) out of exception messages.
        hide_parameters=True,
        # timestamptz values come back in UTC.
        connect_args={"options": "-c timezone=utc"},
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session; commit when the handler returns, roll back if it raises."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# scope="function" runs the commit before the response is sent, so a failed commit
# becomes a 500 instead of following a 200 the client already has. A yield dependency
# that depends on SessionDep must use scope="function" too.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
