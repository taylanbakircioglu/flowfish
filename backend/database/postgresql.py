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
        
        # Run auto-migrations for new tables
        await run_auto_migrations()
        
        return True
    except Exception as e:
        logger.error("PostgreSQL connection test failed", error=str(e))
        return False


async def run_auto_migrations():
    """Run auto-migrations to ensure required tables exist"""
    try:
        # Check and create api_keys table if not exists
        await create_api_keys_table_if_not_exists()
        logger.info("Auto-migrations completed successfully")
    except Exception as e:
        import traceback
        logger.error("Auto-migration FAILED", error=str(e), traceback=traceback.format_exc())
        # Don't raise - let the app continue but log the error prominently


async def create_api_keys_table_if_not_exists():
    """Create api_keys table if it doesn't exist"""
    try:
        # Check if table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'api_keys'
            );
        """
        result = await database.fetch_one(check_query)
        
        if result and result.get('exists'):
            logger.debug("api_keys table already exists, checking for schema updates")
            # Fix key_prefix column size if needed (was VARCHAR(10), should be VARCHAR(12))
            try:
                await database.execute(
                    "ALTER TABLE api_keys ALTER COLUMN key_prefix TYPE VARCHAR(12)"
                )
                logger.info("Updated key_prefix column to VARCHAR(12)")
            except Exception:
                pass  # Column might already be correct size
            return
        
        # Create the table (asyncpg requires separate statements)
        create_table_query = """
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                key_id VARCHAR(50) UNIQUE NOT NULL,
                key_hash VARCHAR(255) NOT NULL,
                key_prefix VARCHAR(12) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                scopes TEXT[] DEFAULT ARRAY['blast-radius'],
                cluster_ids INTEGER[],
                is_active BOOLEAN DEFAULT TRUE,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                last_used_ip VARCHAR(45),
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revoked_at TIMESTAMP,
                revoked_by INTEGER REFERENCES users(id),
                revoke_reason TEXT,
                metadata JSONB DEFAULT '{}'::jsonb
            )
        """
        await database.execute(create_table_query)
        
        # Create indexes separately (asyncpg cannot execute multiple statements at once)
        index_queries = [
            "CREATE INDEX IF NOT EXISTS idx_api_keys_key_id ON api_keys(key_id)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active)",
        ]
        for index_query in index_queries:
            await database.execute(index_query)
        logger.info("api_keys table created successfully")
        
    except Exception as e:
        import traceback
        logger.error("Failed to create api_keys table", error=str(e), traceback=traceback.format_exc())
