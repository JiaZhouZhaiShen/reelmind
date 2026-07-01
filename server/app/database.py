"""Database engine & session management.""" 

from __future__ import annotations 

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine 
from sqlalchemy import create_engine 
from sqlalchemy.orm import sessionmaker 
from sqlalchemy.orm import DeclarativeBase 

from .config import settings 

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DEBUG or settings.DB_ECHO,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all tables (dev/test convenience – use Alembic in prod)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose of the engine."""
    await engine.dispose()
 
# ── Sync engine (for Celery workers / non-async contexts) ────────────── 
sync_engine = create_engine( 
    settings.DATABASE_URL_SYNC, 
    pool_size=20, 
    max_overflow=10, 
    pool_pre_ping=True, 
    echo=settings.DEBUG or settings.DB_ECHO, 
) 
 
sync_session_factory = sessionmaker( 
    sync_engine, 
    expire_on_commit=False, 
) 
 
 
def get_sync_session(): 
    """Return a sync session for Celery workers.""" 
    session = sync_session_factory() 
    try: 
        return session 
    except Exception: 
        session.rollback() 
        raise 
 
 
