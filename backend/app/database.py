"""
Async SQLAlchemy engine and session factory.
Single _engine + sessionmaker for the entire application.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.config import settings

logger = logging.getLogger(__name__)

def _create_engine(db_url: str):
    engine_kwargs = {"echo": settings.DEBUG}
    if not db_url.startswith("sqlite"):
        engine_kwargs.update({
            "pool_size": 5,
            "max_overflow": 10,
            "pool_pre_ping": True,
        })
    return create_async_engine(db_url, **engine_kwargs)

# Create async engine — single instance
target_url = settings.DATABASE_URL_ASYNC
engine = _create_engine(target_url)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass

async def get_db() -> AsyncSession:
    """
    Dependency that yields an async database session.
    Usage in FastAPI: db: AsyncSession = Depends(get_db)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db() -> None:
    """Create all tables. If PostgreSQL is unreachable, seamlessly fall back to local SQLite in development."""
    global engine, async_session_factory
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(f"Database connection verified and tables initialized on {engine.url}")
    except Exception as e:
        err_msg = str(e).lower()
        is_connection_error = any(
            term in err_msg
            for term in ("connect", "refused", "timeout", "is the server running", "10061")
        )
        
        if is_connection_error and not settings.is_production:
            # Only fall back to SQLite in development mode
            fallback_url = "sqlite+aiosqlite:///backend_local.db"
            logger.warning(
                f"Could not connect to database ({engine.url}); falling back to local SQLite: {fallback_url}"
            )
            engine = _create_engine(fallback_url)
            async_session_factory = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Local SQLite database initialized with all tables successfully.")
        elif is_connection_error and settings.is_production:
            logger.error(
                f"FATAL: Cannot connect to database in production mode ({engine.url}). "
                f"SQLite fallback is disabled in production to prevent data loss."
            )
            raise
        else:
            raise

async def close_db() -> None:
    """Dispose engine on shutdown."""
    await engine.dispose()
