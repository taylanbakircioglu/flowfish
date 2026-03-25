"""
Abstract base class for Gadget clients
Enables protocol-agnostic communication with Inspektor Gadget
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from app.pod_discovery import PodIPCache


class Protocol(str, Enum):
    """Supported communication protocols"""
    GRPC = "grpc"
    HTTP = "http"
    WEBSOCKET = "websocket"
    AGENT = "agent"
    KUBECTL = "kubectl"  # kubectl-gadget CLI (v0.46.0+)


class AuthMethod(str, Enum):
    """Supported authentication methods"""
    TOKEN = "token"
    API_KEY = "api_key"
    MTLS = "mtls"
    KUBECONFIG = "kubeconfig"
    OAUTH = "oauth"


@dataclass
class TraceConfig:
    """Trace configuration"""
    analysis_id: str
    cluster_id: str
    trace_type: str  # network, dns, tcp, process, file
    namespace: Optional[str] = None  # Single namespace (deprecated, use namespaces)
    namespaces: Optional[List[str]] = None  # Multiple namespaces
    pod_name: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    filters: Optional[Dict[str, Any]] = None
    exclude_namespaces: Optional[List[str]] = None
    exclude_pod_patterns: Optional[List[str]] = None


@dataclass
class HealthStatus:
    """Health check result"""
    healthy: bool
    version: Optional[str] = None
    endpoint: Optional[str] = None
    protocol: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class Event:
    """eBPF event"""
    timestamp: str
    trace_id: str
    analysis_id: str
    cluster_id: str
    event_type: str
    data: Dict[str, Any]


class AbstractGadgetClient(ABC):
    """
    Abstract base class for Inspektor Gadget clients
    
    Implementations provide protocol-specific communication:
    - GRPCGadgetClient: Direct gRPC to Inspektor Gadget
    - HTTPGadgetClient: HTTP/REST API for remote clusters  
    - AgentGadgetClient: Agent-based for secure remote access
    - WebSocketGadgetClient: WebSocket for real-time streaming
    """
    
    def __init__(
        self,
        endpoint: str,
        protocol: Protocol,
        auth_method: Optional[AuthMethod] = None,
        use_tls: bool = True,
        verify_tls: bool = True,
        timeout_seconds: int = 30,
        **kwargs
    ):
        """
        Initialize client
        
        Args:
            endpoint: Server endpoint (e.g., "gadget.example.com:16060")
            protocol: Communication protocol
            auth_method: Authentication method
            use_tls: Enable TLS/SSL
            verify_tls: Verify TLS certificates
            timeout_seconds: Connection timeout
            **kwargs: Protocol-specific parameters
        """
        self.endpoint = endpoint
        self.protocol = protocol
        self.auth_method = auth_method
        self.use_tls = use_tls
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds
        self.extra_config = kwargs
        self.connected = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to Inspektor Gadget
        
        Returns:
            True if connected successfully
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection
        
        Returns:
            True if disconnected successfully
        """
        pass
    
    @abstractmethod
    async def start_trace(self, config: TraceConfig) -> str:
        """
        Start eBPF trace
        
        Args:
            config: Trace configuration
        
        Returns:
            trace_id: Unique trace identifier
        """
        pass
    
    @abstractmethod
    async def stream_events(
        self, 
        trace_id: str,
        pod_ip_cache: Optional["PodIPCache"] = None
    ) -> AsyncIterator[Event]:
        """
        Stream events from active trace
        
        Args:
            trace_id: Trace identifier
            pod_ip_cache: Optional PodIPCache for resolving destination IPs to namespaces.
                         Used for namespace-scoped analyses to include INCOMING traffic
                         from other namespaces targeting pods in the scoped namespace.
        
        Yields:
            Event objects
        """
        pass
    
    @abstractmethod
    async def stop_trace(self, trace_id: str) -> bool:
        """
        Stop active trace
        
        Args:
            trace_id: Trace identifier
        
        Returns:
            True if stopped successfully
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check if service is healthy
        
        Returns:
            HealthStatus object
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> List[str]:
        """
        Get supported trace types/capabilities
        
        Returns:
            List of supported trace types
        """
        pass
    
    async def test_connection(self) -> HealthStatus:
        """
        Test connection (convenience method)
        
        Returns:
            HealthStatus from health check
        """
        try:
            if not self.connected:
                await self.connect()
            return await self.health_check()
        except Exception as e:
            return HealthStatus(
                healthy=False,
                endpoint=self.endpoint,
                protocol=self.protocol.value,
                error=str(e)
            )

