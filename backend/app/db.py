"""Async SQLAlchemy engine and session dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

_connect_args: dict[str, object] = {}
if "pooler.supabase.com" in settings.DATABASE_URL or "pgbouncer" in settings.DATABASE_URL:
    # Poolers do not support asyncpg's prepared statement cache.
    _connect_args = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
    **({"poolclass": NullPool} if settings.APP_ENV == "test" else {"pool_size": 5, "max_overflow": 5}),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
