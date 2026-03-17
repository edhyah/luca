"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from luca.utils.config import get_settings
from luca.utils.logging import get_logger

logger = get_logger("persistence.database")


class Database:
    """Async database connection manager."""

    def __init__(self, database_url: str | None = None) -> None:
        settings = get_settings()
        self.database_url = database_url or settings.database_url

        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,
        )

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def init_db(self) -> None:
        """Initialize database tables."""
        from luca.persistence.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized")

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()


# Global database instance
_db: Database | None = None


def get_database() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
