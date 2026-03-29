"""Database operations for Cluster Manager"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, DateTime, Text

from app.config import settings

logger = logging.getLogger(__name__)


# SQLAlchemy Base
class Base(DeclarativeBase):
    pass


# Cluster Model
class Cluster(Base):
    __tablename__ = "clusters"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cluster_type: Mapped[str] = mapped_column(String(20), nullable=False)  # kubernetes, openshift
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)
    kubeconfig: Mapped[Optional[str]] = mapped_column(Text)  # Base64 encoded
    service_account_token: Mapped[Optional[str]] = mapped_column(Text)  # Base64 encoded
    inspektor_gadget_grpc_endpoint: Mapped[Optional[str]] = mapped_column(String(500))
    inspektor_gadget_token: Mapped[Optional[str]] = mapped_column(String(500))
    ssl_verify: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    pod_count: Mapped[int] = mapped_column(Integer, default=0)
    namespace_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database Manager
class DatabaseManager:
    """Async database manager"""
    
    def __init__(self):
        # Convert postgresql:// to postgresql+asyncpg:// for async driver
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        self.engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info(f"Database manager initialized")
    
    async def create_tables(self):
        """Create tables if they don't exist"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    
    async def get_cluster(self, cluster_id: int) -> Optional[Cluster]:
        """Get cluster by ID"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Cluster).where(Cluster.id == cluster_id)
            )
            return result.scalar_one_or_none()
    
    async def list_clusters(self) -> List[Cluster]:
        """List all clusters"""
        async with self.async_session() as session:
            result = await session.execute(select(Cluster))
            return list(result.scalars().all())
    
    async def create_cluster(self, cluster_data: Dict[str, Any]) -> Cluster:
        """Create new cluster"""
        async with self.async_session() as session:
            cluster = Cluster(**cluster_data)
            session.add(cluster)
            await session.commit()
            await session.refresh(cluster)
            logger.info(f"Created cluster: {cluster.name}")
            return cluster
    
    async def update_cluster(self, cluster_id: int, cluster_data: Dict[str, Any]) -> Optional[Cluster]:
        """Update cluster"""
        async with self.async_session() as session:
            cluster = await session.get(Cluster, cluster_id)
            if not cluster:
                return None
            
            for key, value in cluster_data.items():
                setattr(cluster, key, value)
            
            cluster.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(cluster)
            logger.info(f"Updated cluster: {cluster.name}")
            return cluster
    
    async def delete_cluster(self, cluster_id: int) -> bool:
        """Delete cluster"""
        async with self.async_session() as session:
            cluster = await session.get(Cluster, cluster_id)
            if not cluster:
                return False
            
            await session.delete(cluster)
            await session.commit()
            logger.info(f"Deleted cluster: {cluster.name}")
            return True
    
    async def update_cluster_health(
        self,
        cluster_id: int,
        health_status: str,
        node_count: int,
        pod_count: int,
        namespace_count: int
    ) -> bool:
        """Update cluster health status"""
        async with self.async_session() as session:
            cluster = await session.get(Cluster, cluster_id)
            if not cluster:
                return False
            
            cluster.health_status = health_status
            cluster.node_count = node_count
            cluster.pod_count = pod_count
            cluster.namespace_count = namespace_count
            cluster.last_sync_at = datetime.utcnow()
            
            await session.commit()
            return True
    
    async def close(self):
        """Close database connection"""
        await self.engine.dispose()
        logger.info("Database connection closed")
    
    async def get_cluster_credentials(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cluster credentials from backend's clusters table.
        
        This method accesses the backend's clusters table (not cluster-manager's)
        to retrieve encrypted credentials for remote cluster connections.
        
        The gateway architecture requires cluster-manager to:
        1. Receive cluster_id from gRPC request
        2. Fetch encrypted credentials from database
        3. Decrypt and create appropriate K8s client
        
        Returns:
            Dict with cluster config including encrypted credentials, or None if not found
        """
        # Use raw SQL to access backend's clusters table with correct column names
        # Note: Live database uses api_server_url (not api_url) and status='active' (not is_active)
        # This is due to migration job schema differing from postgresql-schema.sql
        query = """
            SELECT 
                id,
                name,
                connection_type,
                api_server_url,
                token_encrypted,
                ca_cert_encrypted,
                kubeconfig_encrypted,
                skip_tls_verify,
                gadget_namespace,
                status
            FROM clusters 
            WHERE id = :cluster_id AND status = 'active'
        """
        
        try:
            async with self.engine.connect() as conn:
                from sqlalchemy import text
                result = await conn.execute(text(query), {"cluster_id": cluster_id})
                row = result.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "name": row[1],
                        "connection_type": row[2],
                        "api_server_url": row[3],  # Key name kept for compatibility with grpc_server.py
                        "token_encrypted": row[4],
                        "ca_cert_encrypted": row[5],
                        "kubeconfig_encrypted": row[6],
                        "skip_tls_verify": row[7],
                        "gadget_namespace": row[8],
                        "status": row[9]  # Live DB uses status='active' not is_active boolean
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get cluster credentials for cluster {cluster_id}: {e}")
            return None


# Global database instance
db_manager = DatabaseManager()

