"""
Ingestion Service gRPC Client  
Direct communication with Ingestion Service (if needed)
"""

import grpc
import structlog
from typing import Dict, Any, Optional
import sys
import os

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from proto import ingestion_service_pb2
from proto import ingestion_service_pb2_grpc
from proto import common_pb2

logger = structlog.get_logger()


class IngestionServiceClient:
    """
    gRPC client for Ingestion Service
    
    Note: Normally Backend → Analysis Orchestrator → Ingestion Service
    This client is for direct queries if needed (health check, stats, etc.)
    """
    
    def __init__(self, host: str = "ingestion-service", port: int = 5000):
        """
        Initialize client
        
        Args:
            host: Ingestion Service hostname
            port: gRPC port (default: 5000)
        """
        self.endpoint = f"{host}:{port}"
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[ingestion_service_pb2_grpc.DataIngestionStub] = None
        
        logger.info("IngestionServiceClient initialized", endpoint=self.endpoint)
    
    def connect(self):
        """Establish gRPC connection"""
        try:
            self.channel = grpc.insecure_channel(self.endpoint)
            self.stub = ingestion_service_pb2_grpc.DataIngestionStub(self.channel)
            
            logger.info("Connected to Ingestion Service", endpoint=self.endpoint)
            
        except Exception as e:
            logger.error("Failed to connect to Ingestion Service",
                        endpoint=self.endpoint,
                        error=str(e))
            raise
    
    def close(self):
        """Close gRPC connection"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Ingestion Service connection closed")
    
    async def health_check(self) -> bool:
        """
        Health check
        
        Returns:
            True if healthy
        """
        try:
            if not self.stub:
                self.connect()
            
            request = common_pb2.Empty()
            # Short timeout for health check - don't block event loop
            response = self.stub.HealthCheck(request, timeout=5)
            
            return response.healthy
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return False
    
    async def get_collection_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get collection session status
        
        Args:
            session_id: Session ID
        
        Returns:
            Status dict (includes gadget_errors if any)
        """
        try:
            if not self.stub:
                self.connect()
            
            request = ingestion_service_pb2.GetCollectionStatusRequest(
                session_id=session_id
            )
            
            # Timeout of 10 seconds for status queries
            response = self.stub.GetCollectionStatus(request, timeout=10)
            
            # Parse gadget errors from response
            gadget_errors = []
            if hasattr(response, 'gadget_errors') and response.gadget_errors:
                for err in response.gadget_errors:
                    gadget_errors.append({
                        "gadget": err.gadget,
                        "error": err.error,
                        "trace_id": err.trace_id
                    })
            
            return {
                "session_id": response.session_id,
                "task_id": response.task_id,
                "status": response.status,
                "events_collected": response.events_collected,
                "bytes_written": response.bytes_written,
                "errors_count": response.errors_count,
                "error_message": response.error_message,
                "gadget_errors": gadget_errors
            }
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error("Failed to get collection status",
                        session_id=session_id,
                        error=str(e))
            return None


# Global singleton instance  
ingestion_service_client = IngestionServiceClient()

