"""
Flowfish Analysis Orchestrator - Inspector Gadget Client
Manages Inspector Gadget lifecycle (start/stop traces)
"""

import logging
import httpx
from typing import Dict, List, Optional, Any
from app.config import settings

logger = logging.getLogger(__name__)


class GadgetClient:
    """
    Inspector Gadget API client for managing eBPF traces
    
    Responsibilities:
    - Start trace streams (network, dns, tcp)
    - Stop trace streams
    - Configure trace scope (namespace, labels, pods)
    - Health checks
    """
    
    def __init__(self, gadget_endpoint: Optional[str] = None):
        """
        Initialize Gadget client
        
        Args:
            gadget_endpoint: Inspector Gadget gRPC endpoint
                           Format: gadget-service:16060 (no http:// prefix for gRPC)
                           Falls back to settings.gadget_endpoint if not provided
        """
        self.endpoint = gadget_endpoint or getattr(settings, 'gadget_endpoint', 'inspektor-gadget:16060')
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"GadgetClient initialized with endpoint: {self.endpoint}")
    
    async def start_trace(
        self,
        analysis_id: str,
        cluster_id: str,
        namespace: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        pods: Optional[List[str]] = None,
        gadgets: List[str] = ["network"],
        stream_destination: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start an Inspector Gadget trace
        
        Args:
            analysis_id: Unique analysis identifier
            cluster_id: Target Kubernetes cluster ID
            namespace: Kubernetes namespace to trace (optional, all namespaces if None)
            labels: Label selector (e.g., {"app": "payment", "tier": "backend"})
            pods: Specific pod names to trace (optional)
            gadgets: List of gadget types ["network", "dns", "tcp", "process"]
            stream_destination: gRPC endpoint for streaming data
                              Default: ingestion-service:5000
        
        Returns:
            Dict with trace information:
            {
                "trace_id": "trace-xyz",
                "status": "started",
                "gadgets": ["network"],
                "scope": {...}
            }
        
        Raises:
            httpx.HTTPError: If Gadget API request fails
        """
        if not stream_destination:
            stream_destination = getattr(settings, 'ingestion_service_endpoint', 'ingestion-service:5000')
        
        # Build trace configuration
        trace_config = {
            "trace_id": f"analysis-{analysis_id}",
            "cluster_id": cluster_id,
            "scope": {},
            "gadgets": gadgets,
            "output": {
                "type": "grpc_stream",
                "endpoint": stream_destination
            }
        }
        
        # Add scope filters
        if namespace:
            trace_config["scope"]["namespace"] = namespace
        if labels:
            trace_config["scope"]["labels"] = labels
        if pods:
            trace_config["scope"]["pods"] = pods
        
        logger.info(f"Starting Gadget trace for analysis {analysis_id}")
        logger.debug(f"Trace config: {trace_config}")
        
        try:
            # POST to Gadget API
            response = await self.client.post(
                f"{self.endpoint}/api/v1/traces",
                json=trace_config
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Gadget trace started: {result.get('trace_id')}")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to start Gadget trace: {e}")
            logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            raise
    
    async def stop_trace(self, analysis_id: str) -> Dict[str, Any]:
        """
        Stop an Inspector Gadget trace
        
        Args:
            analysis_id: Analysis identifier used when starting trace
        
        Returns:
            Dict with stop confirmation:
            {
                "trace_id": "trace-xyz",
                "status": "stopped",
                "events_collected": 12345
            }
        
        Raises:
            httpx.HTTPError: If Gadget API request fails
        """
        trace_id = f"analysis-{analysis_id}"
        
        logger.info(f"Stopping Gadget trace for analysis {analysis_id}")
        
        try:
            # DELETE to Gadget API
            response = await self.client.delete(
                f"{self.endpoint}/api/v1/traces/{trace_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Gadget trace stopped: {trace_id}")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to stop Gadget trace: {e}")
            logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            raise
    
    async def get_trace_status(self, analysis_id: str) -> Dict[str, Any]:
        """
        Get current status of a trace
        
        Args:
            analysis_id: Analysis identifier
        
        Returns:
            Dict with trace status:
            {
                "trace_id": "trace-xyz",
                "status": "running" | "stopped",
                "events_count": 1234,
                "started_at": "2024-01-20T10:00:00Z",
                "uptime_seconds": 120
            }
        """
        trace_id = f"analysis-{analysis_id}"
        
        try:
            response = await self.client.get(
                f"{self.endpoint}/api/v1/traces/{trace_id}"
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to get trace status: {e}")
            raise
    
    async def list_active_traces(self) -> List[Dict[str, Any]]:
        """
        List all active traces
        
        Returns:
            List of active trace information
        """
        try:
            response = await self.client.get(
                f"{self.endpoint}/api/v1/traces"
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            logger.error(f"❌ Failed to list traces: {e}")
            raise
    
    async def health_check(self) -> bool:
        """
        Check if Inspector Gadget is reachable and healthy
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get(
                f"{self.endpoint}/health",
                timeout=5.0
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Gadget health check failed: {e}")
            return False
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global singleton instance
_gadget_client: Optional[GadgetClient] = None


def get_gadget_client() -> GadgetClient:
    """
    Get or create global GadgetClient instance
    
    Returns:
        GadgetClient singleton
    """
    global _gadget_client
    if _gadget_client is None:
        _gadget_client = GadgetClient()
    return _gadget_client

