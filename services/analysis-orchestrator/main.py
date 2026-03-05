"""
Flowfish Analysis Orchestrator Service
Main entry point
"""

import logging
import signal
import sys
import threading
import time
from app.grpc_server import serve
from app.config import settings
from app.scheduler import scheduler
from app.database import db_manager, AnalysisStatus
from app.ingestion_client import ingestion_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Track if reconciliation has run (only run once on startup)
_reconciliation_done = False


def reconcile_orphaned_analyses():
    """
    ONE-TIME Startup Reconciliation: Mark orphaned running analyses as 'interrupted'.
    
    When ingestion-service restarts, it loses all in-memory session state.
    This function detects such orphaned analyses and marks them as 'interrupted'
    so users can see the correct status in the UI and manually restart if needed.
    
    NOTE: This does NOT auto-restart analyses to avoid infinite loops.
    """
    global _reconciliation_done
    
    if _reconciliation_done:
        return
    
    try:
        # Get all analyses with status 'running' from PostgreSQL
        running_analyses = db_manager.get_running_analyses_sync()
        
        if not running_analyses:
            logger.info("✅ No orphaned running analyses found")
            _reconciliation_done = True
            return
        
        logger.warning(
            f"⚠️  Found {len(running_analyses)} analyses with status 'running'. "
            f"Checking if their collection sessions are still active..."
        )
        
        orphaned_count = 0
        for analysis in running_analyses:
            analysis_id = analysis.get('id')
            analysis_name = analysis.get('name', 'unknown')
            
            # Try to find if there's an active session for this analysis
            # Since we just started, we have no active sessions - all are orphaned
            logger.warning(
                f"   - Analysis {analysis_id} ({analysis_name}): "
                f"Marking as 'interrupted' (no active collection session)"
            )
            
            # Mark as interrupted - user can restart from UI
            db_manager.update_analysis_status_sync(analysis_id, AnalysisStatus.INTERRUPTED)
            orphaned_count += 1
        
        if orphaned_count > 0:
            logger.warning(
                f"⚠️  Reconciliation complete: {orphaned_count} analyses marked as 'interrupted'. "
                f"Please restart them manually from the UI if needed."
            )
        
        _reconciliation_done = True
            
    except Exception as e:
        logger.error(f"Reconciliation error: {e}")
        _reconciliation_done = True  # Don't retry on error


def delayed_reconciliation():
    """Run reconciliation after a delay to let services stabilize"""
    time.sleep(15)  # Wait for ingestion-service to be ready
    reconcile_orphaned_analyses()


def main():
    """Main function"""
    logger.info("🐟 Starting Flowfish Analysis Orchestrator Service...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"gRPC Port: {settings.grpc_port}")
    logger.info(f"PostgreSQL: {settings.postgres_host}:{settings.postgres_port}")
    logger.info(f"Neo4j: {settings.neo4j_bolt_uri}")
    logger.info(f"ClickHouse: {settings.clickhouse_host}:{settings.clickhouse_port}")
    
    # Start gRPC server (this also starts the scheduler)
    server = serve()
    
    # Start ONE-TIME reconciliation in background (marks orphaned analyses as interrupted)
    reconciliation_thread = threading.Thread(target=delayed_reconciliation, daemon=True)
    reconciliation_thread.start()
    logger.info("🔄 Startup reconciliation scheduled (will run in 15s)")
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutting down gracefully...")
        scheduler.shutdown()
        server.stop(grace=5)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        scheduler.shutdown()
        server.stop(grace=5)


if __name__ == '__main__':
    main()

