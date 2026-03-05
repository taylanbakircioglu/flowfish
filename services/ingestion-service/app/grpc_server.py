"""gRPC Server for Ingestion Service"""

import grpc
from concurrent import futures
import logging
import sys
import os
import asyncio

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proto import ingestion_service_pb2
from proto import ingestion_service_pb2_grpc
from proto import common_pb2
from app.config import settings
from app.trace_manager import TraceManager
from app.rabbitmq_client import RabbitMQPublisher
from datetime import datetime

logger = logging.getLogger(__name__)


async def log_startup_info(trace_manager: TraceManager):
    """
    Log startup information.
    
    NOTE: Reconciliation of orphaned analyses is handled by analysis-orchestrator,
    not by ingestion-service. The orchestrator will detect running analyses
    without active sessions and mark them as 'interrupted'.
    """
    logger.info("✅ Ingestion service ready to accept collection requests")
    logger.info(f"   Active sessions: {len(trace_manager.active_sessions)}")


class DataIngestionService(ingestion_service_pb2_grpc.DataIngestionServicer):
    """gRPC Service implementation"""
    
    def __init__(self):
        # Initialize RabbitMQ client
        self.rabbitmq = RabbitMQPublisher()
        
        # Initialize TraceManager
        self.trace_manager = TraceManager(self.rabbitmq)
        logger.info("DataIngestionService initialized with TraceManager")
    
    def HealthCheck(self, request, context):
        """Health check endpoint"""
        return common_pb2.HealthStatus(
            healthy=True,
            message="Ingestion service is healthy"
        )
    
    async def StartCollection(self, request, context):
        """Start eBPF trace collection"""
        try:
            logger.info(f"StartCollection request received: task_id={request.task_id}, "
                       f"analysis_id={request.analysis_id}, cluster_id={request.cluster_id}")
            
            # Start collection session
            session = await self.trace_manager.start_collection(request)
            
            return ingestion_service_pb2.CollectionSession(
                session_id=session.session_id,
                task_id=session.task_id,
                worker_id=0,  # Deprecated, using session_id now
                status=session.status,
                started_at=common_pb2.Timestamp(
                    seconds=int(session.started_at.timestamp())
                )
            )
        
        except Exception as e:
            logger.error(f"Failed to start collection: task_id={request.task_id}, error={str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to start collection: {str(e)}")
            return ingestion_service_pb2.CollectionSession()
    
    async def StopCollection(self, request, context):
        """Stop eBPF trace collection"""
        try:
            logger.info(f"StopCollection request received: session_id={request.session_id}")
            
            stopped = await self.trace_manager.stop_collection(request.session_id)
            
            if not stopped:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Session {request.session_id} not found")
            
            return common_pb2.Empty()
        
        except Exception as e:
            logger.error("Failed to stop collection", 
                        session_id=request.session_id,
                        error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to stop collection: {str(e)}")
            return common_pb2.Empty()
    
    async def GetCollectionStatus(self, request, context):
        """Get collection session status"""
        try:
            status = await self.trace_manager.get_session_status(request.session_id)
            
            if not status:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Session {request.session_id} not found")
                return ingestion_service_pb2.CollectionStatus()
            
            # Build gadget errors list
            gadget_errors = []
            for err in status.get("gadget_errors", []):
                gadget_errors.append(ingestion_service_pb2.GadgetError(
                    gadget=err.get("gadget", ""),
                    error=err.get("error", ""),
                    trace_id=err.get("trace_id", "")
                ))
            
            return ingestion_service_pb2.CollectionStatus(
                session_id=status["session_id"],
                task_id=status["task_id"],
                status=status["status"],
                events_collected=status["events_collected"],
                bytes_written=0,  # TODO: Track bytes
                errors_count=status["errors_count"],
                started_at=common_pb2.Timestamp(
                    seconds=int(datetime.fromisoformat(status["started_at"]).timestamp())
                ),
                gadget_errors=gadget_errors
            )
        
        except Exception as e:
            logger.error("Failed to get collection status", 
                        session_id=request.session_id,
                        error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_service_pb2.CollectionStatus()
    
    def RegisterWorker(self, request, context):
        """Register a worker"""
        # For future distributed worker registration
        return ingestion_service_pb2.WorkerRegistration(
            worker_id=0,
            assigned_tasks=[]
        )
    
    def HeartBeat(self, request, context):
        """Worker heartbeat"""
        # Update worker last_seen
        self.worker_manager.update_heartbeat(request.worker_id)
        return common_pb2.Empty()
    
    def GetWorkerStats(self, request, context):
        """Get worker statistics"""
        stats = self.worker_manager.get_worker_stats(request.worker_id)
        
        return ingestion_service_pb2.WorkerStats(
            worker_id=request.worker_id,
            worker_name=stats.get("worker_name", "unknown"),
            active_tasks=stats.get("active_tasks", 0),
            total_events_processed=stats.get("total_events_processed", 0),
            total_messages_sent=stats.get("total_messages_sent", 0),
            errors_count=stats.get("errors_count", 0)
        )


async def serve():
    """Start async gRPC server"""
    server = grpc.aio.server()
    
    # Create service instance
    service = DataIngestionService()
    
    ingestion_service_pb2_grpc.add_DataIngestionServicer_to_server(
        service,
        server
    )
    
    server.add_insecure_port(f'[::]:{settings.grpc_port}')
    await server.start()
    
    logger.info(f"🐟 Ingestion Service started on port {settings.grpc_port}")
    
    # Log startup info (non-blocking)
    asyncio.create_task(log_startup_info(service.trace_manager))
    
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        server = await serve()
        await server.wait_for_termination()
    
    asyncio.run(main())

