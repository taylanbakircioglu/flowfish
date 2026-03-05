"""Database operations for Analysis Orchestrator"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, select, update, delete, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from sqlalchemy import Integer, String, Boolean, DateTime, Text, JSON, Enum as SQLEnum

from app.config import settings

logger = logging.getLogger(__name__)


# SQLAlchemy Base
class Base(DeclarativeBase):
    pass


# Analysis Status Enum
class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # Collection was interrupted (e.g., ingestion-service restart)


# Analysis Type Enum
class AnalysisType(str, Enum):
    DEPENDENCY_MAPPING = "dependency_mapping"
    CHANGE_DETECTION = "change_detection"
    ANOMALY_DETECTION = "anomaly_detection"
    BASELINE_CREATION = "baseline_creation"
    RISK_ASSESSMENT = "risk_assessment"
    CUSTOM = "custom"


# Analysis Model - Must match backend schema exactly!
# NOTE: This model reads from the same 'analyses' table created by the backend.
# All columns must be defined here even if not used by orchestrator.
class Analysis(Base):
    __tablename__ = "analyses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Cluster configuration
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_ids: Mapped[Optional[str]] = mapped_column(JSON, default=[])  # Multi-cluster: JSONB array
    is_multi_cluster: Mapped[bool] = mapped_column(Boolean, default=False)  # Multi-cluster flag
    
    # Scope configuration
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, default="cluster")
    scope_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    
    # Gadget configuration
    gadget_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    gadget_modules: Mapped[Optional[dict]] = mapped_column(JSON, default=[])  # Legacy column from backend
    
    # Time & output configuration
    time_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    output_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    
    # Status fields
    status: Mapped[str] = mapped_column(String(50), default="draft")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # From backend model
    
    # Audit fields
    created_by: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Execution timing - for auto-stop monitoring
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Metadata (from backend) - 'metadata' is reserved in SQLAlchemy, use different name
    analysis_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default={})


# Analysis Run Model (execution history)
# NOTE: Column names MUST match the database schema in 03-migrations-job.yaml (Migration 007)
class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(Integer, nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), default="running")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime)  # Was: started_at (WRONG)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime)    # Was: completed_at (WRONG)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    events_collected: Mapped[int] = mapped_column(Integer, default=0)
    workloads_discovered: Mapped[int] = mapped_column(Integer, default=0)
    communications_discovered: Mapped[int] = mapped_column(Integer, default=0)
    anomalies_detected: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    logs: Mapped[Optional[dict]] = mapped_column(JSON, default=[])
    run_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default={})  # 'metadata' is reserved in SQLAlchemy
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database Manager
class DatabaseManager:
    """Async and Sync database manager"""
    
    def __init__(self):
        # Async engine for async methods
        self.engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Sync engine for gRPC sync methods (avoids event loop issues)
        sync_db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.sync_engine = create_engine(
            sync_db_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.sync_session = sessionmaker(
            self.sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
        logger.info(f"Database manager initialized: {settings.postgres_host}")
    
    async def create_tables(self):
        """
        Create tables if they don't exist.
        
        NOTE: The 'analyses' table is created by the Backend service.
        We only create 'analysis_runs' table here for execution history.
        The Analysis model must match the backend's schema exactly.
        """
        async with self.engine.begin() as conn:
            # Only create analysis_runs table, not analyses (managed by backend)
            await conn.run_sync(
                lambda sync_conn: AnalysisRun.__table__.create(sync_conn, checkfirst=True)
            )
        logger.info("Database tables verified (analysis_runs)")
    
    # Analysis CRUD
    async def create_analysis(self, analysis_data: Dict[str, Any]) -> Analysis:
        """Create new analysis"""
        async with self.async_session() as session:
            analysis = Analysis(**analysis_data)
            session.add(analysis)
            await session.commit()
            await session.refresh(analysis)
            logger.info(f"Created analysis: {analysis.name}")
            return analysis
    
    async def get_analysis(self, analysis_id: int) -> Optional[Analysis]:
        """Get analysis by ID"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )
            return result.scalar_one_or_none()
    
    async def list_analyses(
        self,
        cluster_id: Optional[int] = None,
        scope_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Analysis]:
        """List analyses with filters"""
        async with self.async_session() as session:
            query = select(Analysis)
            
            if cluster_id:
                query = query.where(Analysis.cluster_id == cluster_id)
            if scope_type:
                query = query.where(Analysis.scope_type == scope_type)
            if status:
                query = query.where(Analysis.status == status)
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def update_analysis(
        self,
        analysis_id: int,
        analysis_data: Dict[str, Any]
    ) -> Optional[Analysis]:
        """Update analysis"""
        async with self.async_session() as session:
            analysis = await session.get(Analysis, analysis_id)
            if not analysis:
                return None
            
            now = datetime.utcnow()
            
            for key, value in analysis_data.items():
                setattr(analysis, key, value)
            
            analysis.updated_at = now
            
            # Check if status is being updated and set timing fields
            new_status = analysis_data.get('status')
            if new_status:
                if new_status == "running":
                    # Always update started_at on every Start (for auto-stop timing on restart)
                    analysis.started_at = now
                    logger.info(f"Analysis {analysis_id} started at {now}")
                elif new_status in ("stopped", "completed", "failed"):
                    analysis.stopped_at = now
                    logger.info(f"Analysis {analysis_id} stopped at {now}")
            
            await session.commit()
            await session.refresh(analysis)
            logger.info(f"Updated analysis: {analysis.name}")
            return analysis
    
    async def delete_analysis(self, analysis_id: int) -> bool:
        """Delete analysis (async version)"""
        async with self.async_session() as session:
            analysis = await session.get(Analysis, analysis_id)
            if not analysis:
                return False
            
            await session.delete(analysis)
            await session.commit()
            logger.info(f"Deleted analysis: {analysis.name}")
            return True
    
    def delete_analysis_sync(self, analysis_id: int) -> bool:
        """Delete analysis (sync version for gRPC)"""
        try:
            with self.sync_session() as session:
                analysis = session.get(Analysis, analysis_id)
                if not analysis:
                    return False
                
                session.delete(analysis)
                session.commit()
                logger.info(f"Deleted analysis: {analysis.name}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete analysis: {e}")
            return False
    
    def update_analysis_sync(
        self,
        analysis_id: int,
        analysis_data: Dict[str, Any]
    ) -> bool:
        """Update analysis (sync version for gRPC)"""
        try:
            with self.sync_session() as session:
                analysis = session.get(Analysis, analysis_id)
                if not analysis:
                    return False
                
                now = datetime.utcnow()
                
                for key, value in analysis_data.items():
                    setattr(analysis, key, value)
                
                analysis.updated_at = now
                session.commit()
                logger.info(f"Updated analysis {analysis_id} (sync)")
                return True
        except Exception as e:
            logger.error(f"Failed to update analysis (sync): {e}")
            return False
    
    async def update_analysis_status(
        self,
        analysis_id: int,
        status: AnalysisStatus
    ) -> bool:
        """Update analysis status (async version)"""
        async with self.async_session() as session:
            analysis = await session.get(Analysis, analysis_id)
            if not analysis:
                return False
            
            now = datetime.utcnow()
            status_value = status.value if hasattr(status, 'value') else status
            
            analysis.status = status_value
            analysis.updated_at = now
            
            # Set started_at when analysis starts running
            if status_value == "running":
                analysis.started_at = now
                logger.info(f"Analysis {analysis_id} started at {now}")
            
            # Set stopped_at when analysis stops
            if status_value in ("stopped", "completed", "failed"):
                analysis.stopped_at = now
                logger.info(f"Analysis {analysis_id} stopped at {now}")
            
            await session.commit()
            logger.info(f"Updated analysis {analysis_id} status to {status}")
            return True
    
    def update_analysis_status_sync(
        self,
        analysis_id: int,
        status: AnalysisStatus
    ) -> bool:
        """Update analysis status (sync version for gRPC)"""
        try:
            with self.sync_session() as session:
                analysis = session.get(Analysis, analysis_id)
                if not analysis:
                    return False
                
                now = datetime.utcnow()
                status_value = status.value if hasattr(status, 'value') else status
                
                analysis.status = status_value
                analysis.updated_at = now
                
                # Set started_at when analysis starts running
                if status_value == "running":
                    analysis.started_at = now
                    logger.info(f"Analysis {analysis_id} started at {now}")
                
                # Set stopped_at when analysis stops
                if status_value in ("stopped", "completed", "failed"):
                    analysis.stopped_at = now
                    logger.info(f"Analysis {analysis_id} stopped at {now}")
                
                session.commit()
                logger.info(f"Updated analysis {analysis_id} status to {status}")
                return True
        except Exception as e:
            logger.error(f"Failed to update analysis status: {e}")
            return False
    
    def get_analysis_sync(self, analysis_id: int) -> Optional[Analysis]:
        """Get analysis by ID (sync version for gRPC)"""
        try:
            with self.sync_session() as session:
                analysis = session.get(Analysis, analysis_id)
                if analysis:
                    logger.info(f"Found analysis {analysis_id}: {analysis.name}, status={analysis.status}")
                else:
                    # Debug: try raw SQL to see if data exists
                    from sqlalchemy import text
                    result = session.execute(text(f"SELECT id, name, status FROM analyses WHERE id = {analysis_id}"))
                    row = result.fetchone()
                    if row:
                        logger.error(f"Analysis {analysis_id} exists in DB but SQLAlchemy can't load it! Row: {row}")
                    else:
                        logger.warning(f"Analysis {analysis_id} not found in database (raw SQL confirms)")
                return analysis
        except Exception as e:
            logger.error(f"Failed to get analysis {analysis_id}: {e}", exc_info=True)
            return None
    
    def get_running_analyses_sync(self) -> List[Dict[str, Any]]:
        """Get all analyses with status 'running' (sync version)"""
        try:
            with self.sync_session() as session:
                result = session.execute(
                    select(Analysis).where(Analysis.status == "running")
                )
                analyses = result.scalars().all()
                return [
                    {
                        "id": a.id,
                        "name": a.name,
                        "cluster_id": a.cluster_id,
                        "status": a.status
                    }
                    for a in analyses
                ]
        except Exception as e:
            logger.error(f"Failed to get running analyses: {e}")
            return []
    
    def get_cluster_sync(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Get cluster by ID (sync version for gRPC) - includes credentials for remote clusters"""
        try:
            with self.sync_session() as session:
                result = session.execute(
                    text("""
                        SELECT id, name, gadget_endpoint, connection_type, api_server_url,
                               token_encrypted, ca_cert_encrypted, 
                               kubeconfig_encrypted, skip_tls_verify, gadget_namespace
                        FROM clusters WHERE id = :id
                    """),
                    {"id": cluster_id}
                )
                row = result.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "name": row[1],
                        "gadget_endpoint": row[2],
                        "connection_type": row[3],
                        "api_server_url": row[4],
                        "token_encrypted": row[5],
                        "ca_cert_encrypted": row[6],
                        "kubeconfig_encrypted": row[7],
                        "skip_tls_verify": row[8] or False,
                        "gadget_namespace": row[9]
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get cluster: {e}")
            return None
    
    # Cluster lookup (read-only, uses raw SQL since clusters table is managed by backend)
    async def get_cluster(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Get cluster by ID from shared database - includes credentials for remote clusters"""
        from sqlalchemy import text
        async with self.async_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, name, gadget_endpoint, connection_type, api_server_url,
                           token_encrypted, ca_cert_encrypted,
                           kubeconfig_encrypted, skip_tls_verify, gadget_namespace
                    FROM clusters WHERE id = :id
                """),
                {"id": cluster_id}
            )
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "gadget_endpoint": row[2],
                    "connection_type": row[3],
                    "api_server_url": row[4],
                    "token_encrypted": row[5],
                    "ca_cert_encrypted": row[6],
                    "kubeconfig_encrypted": row[7],
                    "skip_tls_verify": row[8] or False,
                    "gadget_namespace": row[9]  # From UI, no fallback
                }
            return None
    
    # Analysis Run CRUD
    async def create_analysis_run(self, run_data: Dict[str, Any]) -> AnalysisRun:
        """Create new analysis run"""
        async with self.async_session() as session:
            run = AnalysisRun(**run_data)
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run
    
    async def update_analysis_run(
        self,
        run_id: int,
        run_data: Dict[str, Any]
    ) -> Optional[AnalysisRun]:
        """Update analysis run"""
        async with self.async_session() as session:
            run = await session.get(AnalysisRun, run_id)
            if not run:
                return None
            
            for key, value in run_data.items():
                setattr(run, key, value)
            
            await session.commit()
            await session.refresh(run)
            return run
    
    async def list_analysis_runs(
        self,
        analysis_id: int,
        limit: int = 10
    ) -> List[AnalysisRun]:
        """List analysis runs for an analysis"""
        async with self.async_session() as session:
            query = (
                select(AnalysisRun)
                .where(AnalysisRun.analysis_id == analysis_id)
                .order_by(AnalysisRun.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_running_run_for_analysis(self, analysis_id: int) -> Optional[AnalysisRun]:
        """Get the currently running run for an analysis (if any)"""
        async with self.async_session() as session:
            query = (
                select(AnalysisRun)
                .where(AnalysisRun.analysis_id == analysis_id)
                .where(AnalysisRun.status == "running")
                .order_by(AnalysisRun.created_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalars().first()
    
    async def close(self):
        """Close database connection"""
        await self.engine.dispose()
        logger.info("Database connection closed")


# Global database instance
db_manager = DatabaseManager()

