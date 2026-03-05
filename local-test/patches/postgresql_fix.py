"""
PostgreSQL database connection and session management
"""

import asyncpg
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
import structlog

from config import settings

logger = structlog.get_logger()

# Convert postgres:// to postgresql:// for async
async_database_url = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')

# Async SQLAlchemy engine (SQLAlchemy 2.0)
async_engine = create_async_engine(
    async_database_url,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=20,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=3600,
    echo=settings.DEBUG
)

# Sync engine for migrations
sync_engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,
    echo=settings.DEBUG
)

# Session for sync operations (migrations, etc.)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# Async session factory
async_session = AsyncSession(async_engine)

# Base class for models
Base = declarative_base()
metadata = MetaData()

# Simple database operations
class DatabaseService:
    @staticmethod
    async def execute(query: str, values: dict = None):
        """Execute raw SQL query"""
        async with AsyncSession(async_engine) as session:
            result = await session.execute(text(query), values or {})
            await session.commit()
            return result
    
    @staticmethod 
    async def fetch_one(query: str, values: dict = None):
        """Fetch single row - commits if query modifies data (INSERT/UPDATE/DELETE with RETURNING)"""
        async with AsyncSession(async_engine) as session:
            result = await session.execute(text(query), values or {})
            row = result.fetchone()
            # Commit for write operations (INSERT/UPDATE/DELETE with RETURNING)
            await session.commit()
            if row:
                return dict(row._mapping)
            return None
    
    @staticmethod
    async def fetch_all(query: str, values: dict = None):
        """Fetch all rows - commits if query modifies data"""
        async with AsyncSession(async_engine) as session:
            result = await session.execute(text(query), values or {})
            rows = result.fetchall()
            # Commit for write operations
            await session.commit()
            return [dict(row._mapping) for row in rows]

# Create database instance
database = DatabaseService()

def get_db_session():
    """Get sync database session for migrations/admin tasks"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Connection test function
async def test_connection():
    """Test PostgreSQL connection"""
    try:
        result = await database.fetch_one("SELECT 1 as test")
        logger.info("PostgreSQL connection test successful")
        return True
    except Exception as e:
        logger.error("PostgreSQL connection test failed", error=str(e))
        return False
