"""
Analysis Orchestrator gRPC Client
Communicates with Analysis Orchestrator microservice
"""

import grpc
import structlog
from typing import Dict, Any, Optional
import sys
import os

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from proto import analysis_orchestrator_pb2
from proto import analysis_orchestrator_pb2_grpc
from proto import common_pb2

logger = structlog.get_logger()


class AnalysisOrchestratorClient:
    """
    gRPC client for Analysis Orchestrator service
    
    Responsibilities:
    - Start/stop analysis
    - Get analysis status
    - Coordinate analysis lifecycle
    """
    
    def __init__(self, host: str = "analysis-orchestrator", port: int = 5002):
        """
        Initialize client
        
        Args:
            host: Analysis Orchestrator hostname
            port: gRPC port (default: 5002)
        """
        self.endpoint = f"{host}:{port}"
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub] = None
        
        logger.info("AnalysisOrchestratorClient initialized", endpoint=self.endpoint)
    
    def connect(self):
        """Establish gRPC connection"""
        try:
            # In production, use secure channel with mTLS
            # For now, insecure channel within same cluster
            self.channel = grpc.insecure_channel(self.endpoint)
            self.stub = analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub(self.channel)
            
            logger.info("Connected to Analysis Orchestrator", endpoint=self.endpoint)
            
        except Exception as e:
            logger.error("Failed to connect to Analysis Orchestrator",
                        endpoint=self.endpoint,
                        error=str(e))
            raise
    
    def close(self):
        """Close gRPC connection"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Analysis Orchestrator connection closed")
    
    async def start_analysis(self, analysis_id: int) -> Dict[str, Any]:
        """
        Start analysis via Analysis Orchestrator
        
        Args:
            analysis_id: Analysis ID to start
        
        Returns:
            Dict with start response
        """
        try:
            if not self.stub:
                self.connect()
            
            logger.info("Requesting analysis start",
                       analysis_id=analysis_id,
                       service="analysis-orchestrator")
            
            request = analysis_orchestrator_pb2.StartAnalysisRequest(
                analysis_id=analysis_id
            )
            
            # Timeout of 120 seconds - gadget startup can take 60+ seconds for 11 modules
            response = self.stub.StartAnalysis(request, timeout=120)
            
            logger.info("Analysis start response received",
                       analysis_id=analysis_id,
                       message=response.message)
            
            return {
                "analysis_id": response.analysis_id,
                "task_assignments": [
                    {
                        "task_id": task.task_id,
                        "cluster_id": task.cluster_id,
                        "worker_address": task.worker_address
                    }
                    for task in response.task_assignments
                ],
                "message": response.message,
                "started_at": response.started_at.seconds if response.started_at else None
            }
            
        except grpc.RpcError as e:
            logger.error("gRPC error starting analysis",
                        analysis_id=analysis_id,
                        code=e.code(),
                        details=e.details())
            raise
        except Exception as e:
            logger.error("Failed to start analysis",
                        analysis_id=analysis_id,
                        error=str(e))
            raise
    
    async def stop_analysis(self, analysis_id: int) -> bool:
        """
        Stop analysis via Analysis Orchestrator
        
        Args:
            analysis_id: Analysis ID to stop
        
        Returns:
            True if stopped successfully
        """
        try:
            if not self.stub:
                self.connect()
            
            logger.info("Requesting analysis stop",
                       analysis_id=analysis_id,
                       service="analysis-orchestrator")
            
            request = analysis_orchestrator_pb2.StopAnalysisRequest(
                analysis_id=analysis_id
            )
            
            # Timeout of 90 seconds - parallel stops should complete in ~60s
            self.stub.StopAnalysis(request, timeout=90)
            
            logger.info("Analysis stopped successfully",
                       analysis_id=analysis_id)
            
            return True
            
        except grpc.RpcError as e:
            logger.error("gRPC error stopping analysis",
                        analysis_id=analysis_id,
                        code=e.code(),
                        details=e.details())
            return False
        except Exception as e:
            logger.error("Failed to stop analysis",
                        analysis_id=analysis_id,
                        error=str(e))
            return False
    
    async def get_analysis_status(self, analysis_id: int) -> Optional[Dict[str, Any]]:
        """
        Get analysis status
        
        Args:
            analysis_id: Analysis ID
        
        Returns:
            Dict with status information
        """
        try:
            if not self.stub:
                self.connect()
            
            request = analysis_orchestrator_pb2.GetStatusRequest(
                analysis_id=analysis_id
            )
            
            # Timeout of 10 seconds for status queries
            response = self.stub.GetAnalysisStatus(request, timeout=10)
            
            return {
                "analysis_id": response.analysis_id,
                "status": response.status,
                "events_collected": response.events_collected,
                "bytes_written": response.bytes_written,
                "task_statuses": [
                    {
                        "task_id": task.task_id,
                        "cluster_id": task.cluster_id,
                        "cluster_name": task.cluster_name,
                        "status": task.status,
                        "events_collected": task.events_collected,
                        "error_message": task.error_message
                    }
                    for task in response.task_statuses
                ]
            }
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error("gRPC error getting analysis status",
                        analysis_id=analysis_id,
                        code=e.code(),
                        details=e.details())
            return None
        except Exception as e:
            logger.error("Failed to get analysis status",
                        analysis_id=analysis_id,
                        error=str(e))
            return None


# Global singleton instance
analysis_orchestrator_client = AnalysisOrchestratorClient()

