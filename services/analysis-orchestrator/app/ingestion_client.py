"""
Ingestion Service gRPC Client
Used by Analysis Orchestrator to start/stop eBPF collection
"""

import grpc
import logging
import sys
import os
from typing import Dict, Any, Optional

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proto import ingestion_service_pb2
from proto import ingestion_service_pb2_grpc
from proto import analysis_orchestrator_pb2
from proto import common_pb2

logger = logging.getLogger(__name__)


class IngestionServiceClient:
    """
    gRPC client for Ingestion Service
    
    Responsibilities:
    - Start eBPF trace collection
    - Stop trace collection
    - Get collection status
    """
    
    def __init__(self, host: str = "ingestion-service", port: int = 5000):
        """
        Initialize client
        
        Args:
            host: Ingestion Service hostname
            port: gRPC port
        """
        self.endpoint = f"{host}:{port}"
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[ingestion_service_pb2_grpc.DataIngestionStub] = None
        
        logger.info(f"IngestionServiceClient initialized: {self.endpoint}")
    
    def connect(self):
        """Establish gRPC connection"""
        try:
            self.channel = grpc.insecure_channel(self.endpoint)
            self.stub = ingestion_service_pb2_grpc.DataIngestionStub(self.channel)
            logger.info(f"Connected to Ingestion Service: {self.endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to Ingestion Service: {e}")
            raise
    
    def close(self):
        """Close connection"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.info("Ingestion Service connection closed")
    
    def start_collection(
        self,
        task_id: str,
        analysis_id: int,
        cluster_id: int,
        cluster_name: str,
        gadget_endpoint: str,
        gadget_protocol: str,
        gadget_auth_method: str,
        gadget_modules: list,
        scope: analysis_orchestrator_pb2.ScopeConfig,
        duration_seconds: int = 0,
        **auth_params
    ) -> Dict[str, Any]:
        """
        Start eBPF collection via Ingestion Service
        
        Args:
            task_id: Unique task ID
            analysis_id: Analysis ID
            cluster_id: Cluster ID
            cluster_name: Cluster name
            gadget_endpoint: Inspektor Gadget endpoint
            gadget_protocol: Protocol (grpc, http, agent, kubectl)
            gadget_auth_method: Auth method (token, incluster, api_key, mtls)
            gadget_modules: List of gadget modules
            scope: Scope configuration
            duration_seconds: Collection duration (0 = continuous)
            **auth_params: Additional auth parameters:
                - api_server_url: Remote cluster API server URL
                - token: ServiceAccount token (for remote clusters)
                - ca_cert: CA certificate (for TLS verification)
                - verify_ssl: Whether to verify SSL
                - is_remote_cluster: Boolean indicating remote cluster
        
        Returns:
            Dict with session information
        """
        try:
            if not self.stub:
                self.connect()
            
            # Extract remote cluster credentials from auth_params
            api_server_url = auth_params.get('api_server_url', '')
            cluster_token = auth_params.get('token', '')
            ca_cert = auth_params.get('ca_cert', '')
            verify_ssl = auth_params.get('verify_ssl', True)
            is_remote = auth_params.get('is_remote_cluster', False)
            
            logger.info(f"Starting collection: task_id={task_id}, analysis_id={analysis_id}, "
                       f"cluster_id={cluster_id}, is_remote={is_remote}, "
                       f"api_server={'***' if api_server_url else 'N/A'}")
            
            # Get gadget_namespace from auth_params (passed from grpc_server.py)
            gadget_namespace = auth_params.get('gadget_namespace')
            if not gadget_namespace:
                raise ValueError("gadget_namespace is required but not provided")
            
            # Dynamic OCI tag, rate limiting, and network config
            gadget_version = auth_params.get('gadget_version') or ''
            max_events_per_second = auth_params.get('max_events_per_second', 0)
            network_config_json = auth_params.get('network_config_json', '')
            
            request = ingestion_service_pb2.StartCollectionRequest(
                task_id=task_id,
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                analysis_name=f"analysis-{analysis_id}",
                cluster_name=cluster_name,
                # Remote cluster connection (proto fields 6, 7)
                cluster_api_url=api_server_url,
                cluster_token=cluster_token,
                # Gadget connection
                gadget_endpoint=gadget_endpoint,
                gadget_protocol=gadget_protocol,
                gadget_auth_method=gadget_auth_method,
                gadget_token=auth_params.get('gadget_token', ''),
                gadget_api_key=auth_params.get('api_key', ''),
                gadget_client_cert=auth_params.get('client_cert', ''),
                gadget_client_key=auth_params.get('client_key', ''),
                gadget_ca_cert=ca_cert,
                verify_ssl=verify_ssl,
                use_tls=auth_params.get('use_tls', True) if is_remote else False,
                gadget_modules=gadget_modules,
                scope=scope,
                duration_seconds=duration_seconds,
                gadget_namespace=gadget_namespace,  # CRITICAL: Pass namespace to ingestion service
                gadget_version=gadget_version,
                max_events_per_second=max_events_per_second,
                network_config_json=network_config_json
            )
            
            # 120 second timeout for start operation - gadget startup can take 60+ seconds
            response = self.stub.StartCollection(request, timeout=120)
            
            logger.info(f"Collection started: session_id={response.session_id}, status={response.status}")
            
            return {
                "session_id": response.session_id,
                "task_id": response.task_id,
                "worker_id": response.worker_id,
                "status": response.status
            }
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error starting collection: code={e.code()}, details={e.details()}")
            raise
        except Exception as e:
            logger.error(f"Failed to start collection: {e}")
            raise
    
    def stop_collection(self, session_id: str) -> bool:
        """
        Stop eBPF collection
        
        Args:
            session_id: Session ID to stop
        
        Returns:
            True if stopped successfully
        """
        try:
            if not self.stub:
                self.connect()
            
            logger.info(f"Stopping collection: session_id={session_id}")
            
            request = ingestion_service_pb2.StopCollectionRequest(
                session_id=session_id
            )
            
            # 60 second timeout for stop operation
            self.stub.StopCollection(request, timeout=60)
            
            logger.info(f"Collection stopped: session_id={session_id}")
            
            return True
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error stopping collection: code={e.code()}, details={e.details()}")
            return False
        except Exception as e:
            logger.error(f"Failed to stop collection: {e}")
            return False
    
    def get_collection_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get collection status
        
        Args:
            session_id: Session ID
        
        Returns:
            Status dict or None (includes gadget_errors if any)
        """
        try:
            if not self.stub:
                self.connect()
            
            request = ingestion_service_pb2.GetCollectionStatusRequest(
                session_id=session_id
            )
            
            # 10 second timeout for status check
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
                "gadget_errors": gadget_errors
            }
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"gRPC error getting status: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get collection status: {e}")
            return None


# Global singleton instance
ingestion_client = IngestionServiceClient()

