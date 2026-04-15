from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# SQLite file in the working directory; suitable for local/dev and tests.
DATABASE_URL = "sqlite+aiosqlite:///./payments.db"


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session per request.
    The caller is responsible for commit/rollback.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Create all tables. Import models before calling so metadata is populated.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the connection pool (e.g. on shutdown)."""
    await engine.dispose()
