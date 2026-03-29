"""gRPC Clients for microservices"""

import grpc
import logging
import sys
import os
from typing import Optional

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proto import cluster_manager_pb2_grpc
from proto import analysis_orchestrator_pb2_grpc
from app.config import settings

logger = logging.getLogger(__name__)


# Singleton instance
_grpc_clients_instance: Optional['GRPCClients'] = None


class GRPCClients:
    """Manages gRPC client connections to microservices"""
    
    def __init__(self):
        self._cluster_manager_channel: Optional[grpc.Channel] = None
        # Proto service name is ClusterManagerService -> stub is ClusterManagerServiceStub
        self._cluster_manager_stub: Optional[cluster_manager_pb2_grpc.ClusterManagerServiceStub] = None
        
        self._analysis_orchestrator_channel: Optional[grpc.Channel] = None
        self._analysis_orchestrator_stub: Optional[analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub] = None
        
        logger.info("GRPCClients initialized")
    
    def connect(self):
        """Establish gRPC connections"""
        # Cluster Manager
        cluster_manager_address = f"{settings.cluster_manager_host}:{settings.cluster_manager_port}"
        self._cluster_manager_channel = grpc.insecure_channel(cluster_manager_address)
        self._cluster_manager_stub = cluster_manager_pb2_grpc.ClusterManagerServiceStub(
            self._cluster_manager_channel
        )
        logger.info(f"✅ Connected to Cluster Manager: {cluster_manager_address}")
        
        # Analysis Orchestrator
        analysis_orchestrator_address = f"{settings.analysis_orchestrator_host}:{settings.analysis_orchestrator_port}"
        self._analysis_orchestrator_channel = grpc.insecure_channel(analysis_orchestrator_address)
        self._analysis_orchestrator_stub = analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub(
            self._analysis_orchestrator_channel
        )
        logger.info(f"✅ Connected to Analysis Orchestrator: {analysis_orchestrator_address}")
    
    def close(self):
        """Close gRPC connections"""
        if self._cluster_manager_channel:
            self._cluster_manager_channel.close()
        if self._analysis_orchestrator_channel:
            self._analysis_orchestrator_channel.close()
        logger.info("gRPC connections closed")
    
    @property
    def cluster_manager(self) -> cluster_manager_pb2_grpc.ClusterManagerServiceStub:
        """Get Cluster Manager stub"""
        if not self._cluster_manager_stub:
            self.connect()
        return self._cluster_manager_stub
    
    @property
    def analysis_orchestrator(self) -> analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub:
        """Get Analysis Orchestrator stub"""
        if not self._analysis_orchestrator_stub:
            self.connect()
        return self._analysis_orchestrator_stub


# Global gRPC clients instance
grpc_clients = GRPCClients()


def get_cluster_manager_client() -> cluster_manager_pb2_grpc.ClusterManagerServiceStub:
    """Get Cluster Manager gRPC client stub"""
    return grpc_clients.cluster_manager


def get_analysis_orchestrator_client() -> analysis_orchestrator_pb2_grpc.AnalysisOrchestratorStub:
    """Get Analysis Orchestrator gRPC client stub"""
    return grpc_clients.analysis_orchestrator
