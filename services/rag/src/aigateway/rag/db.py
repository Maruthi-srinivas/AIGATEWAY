from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def sqlalchemy_url(dsn: str) -> str:
    if dsn.startswith("postgresql+"):
        return dsn
    return dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def init_engine(dsn: str) -> None:
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(sqlalchemy_url(dsn), pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def session_scope() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("database engine is not initialized")
    return _session_factory()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session
