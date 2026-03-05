"""
Base classes for cluster connections
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class ConnectionConfig:
    """Configuration for cluster connection"""
    cluster_id: int
    name: str
    connection_type: str  # 'in-cluster', 'token', 'kubeconfig'
    api_server_url: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None
    kubeconfig: Optional[str] = None
    skip_tls_verify: bool = False
    gadget_namespace: Optional[str] = None  # Namespace where gadget is deployed (from UI)
    gadget_endpoint: Optional[str] = None  # Deprecated - not used anymore
    
    @property
    def is_remote(self) -> bool:
        """Check if this is a remote cluster connection"""
        return self.connection_type.lower().replace('_', '-') in ['token', 'kubeconfig']


@dataclass
class ClusterInfo:
    """Cluster information"""
    k8s_version: Optional[str] = None
    platform: Optional[str] = None
    total_nodes: int = 0
    total_pods: int = 0
    total_namespaces: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "k8s_version": self.k8s_version,
            "platform": self.platform,
            "total_nodes": self.total_nodes,
            "total_pods": self.total_pods,
            "total_namespaces": self.total_namespaces,
            "error": self.error
        }


@dataclass
class GadgetHealth:
    """Inspector Gadget health status"""
    health_status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    version: Optional[str] = None
    pods_ready: int = 0
    pods_total: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_status": self.health_status,
            "version": self.version,
            "pods_ready": self.pods_ready,
            "pods_total": self.pods_total,
            "error": self.error,
            "details": self.details
        }


@dataclass
class Namespace:
    """Namespace information"""
    name: str
    uid: Optional[str] = None
    status: str = "Active"
    labels: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "uid": self.uid,
            "status": self.status,
            "labels": self.labels,
            "created_at": self.created_at
        }


@dataclass
class Deployment:
    """Deployment information"""
    name: str
    namespace: str
    uid: Optional[str] = None
    replicas: int = 0
    available_replicas: int = 0
    labels: Dict[str, str] = field(default_factory=dict)
    image: Optional[str] = None
    created_at: Optional[str] = None
    spec_hash: str = ""
    containers: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "replicas": self.replicas,
            "available_replicas": self.available_replicas,
            "labels": self.labels,
            "image": self.image,
            "created_at": self.created_at,
            "workload_type": "deployment",
            "spec_hash": self.spec_hash,
            "containers": self.containers,
        }


@dataclass
class Pod:
    """Pod information"""
    name: str
    namespace: str
    uid: Optional[str] = None
    status: str = "Unknown"
    node_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    ip: Optional[str] = None
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "status": self.status,
            "node_name": self.node_name,
            "labels": self.labels,
            "ip": self.ip,
            "created_at": self.created_at
        }


@dataclass
class Service:
    """Service information"""
    name: str
    namespace: str
    uid: Optional[str] = None
    type: str = "ClusterIP"
    cluster_ip: Optional[str] = None
    ports: List[Dict[str, Any]] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    selector: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "type": self.type,
            "cluster_ip": self.cluster_ip,
            "ports": self.ports,
            "labels": self.labels,
            "selector": self.selector,
            "created_at": self.created_at
        }


@dataclass
class ConfigMap:
    """ConfigMap information with data hash (not raw data)"""
    name: str
    namespace: str
    uid: Optional[str] = None
    data_hash: str = "empty"
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "data_hash": self.data_hash,
            "workload_type": "configmap",
            "created_at": self.created_at
        }


@dataclass
class Secret:
    """Secret information with data hash (not raw data)"""
    name: str
    namespace: str
    uid: Optional[str] = None
    data_hash: str = "empty"
    type: str = "Opaque"
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "data_hash": self.data_hash,
            "type": self.type,
            "workload_type": "secret",
            "created_at": self.created_at
        }


@dataclass
class StatefulSet:
    """StatefulSet information"""
    name: str
    namespace: str
    uid: Optional[str] = None
    replicas: int = 0
    ready_replicas: int = 0
    labels: Dict[str, str] = field(default_factory=dict)
    image: Optional[str] = None
    created_at: Optional[str] = None
    spec_hash: str = ""
    containers: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "uid": self.uid,
            "replicas": self.replicas,
            "ready_replicas": self.ready_replicas,
            "labels": self.labels,
            "workload_type": "statefulset",
            "image": self.image,
            "created_at": self.created_at,
            "spec_hash": self.spec_hash,
            "containers": self.containers,
        }


class ClusterConnection(ABC):
    """
    Abstract base class for cluster connections.
    
    Each connection type (in-cluster, token, kubeconfig) implements this interface.
    The ClusterConnectionManager uses these connections to interact with clusters.
    """
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.cluster_id = config.cluster_id
        self._connected = False
        self._last_used: Optional[datetime] = None
        self._error_count = 0
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def connection_type(self) -> str:
        return self.config.connection_type
    
    async def connect(self) -> bool:
        """
        Establish connection to the cluster.
        Returns True if successful, False otherwise.
        """
        try:
            await self._do_connect()
            self._connected = True
            self._error_count = 0
            logger.info("Connected to cluster", cluster_id=self.cluster_id, type=self.connection_type)
            return True
        except Exception as e:
            self._connected = False
            self._error_count += 1
            logger.error("Failed to connect to cluster", cluster_id=self.cluster_id, error=str(e))
            return False
    
    async def disconnect(self) -> None:
        """Close connection and cleanup resources"""
        try:
            await self._do_disconnect()
            self._connected = False
            logger.info("Disconnected from cluster", cluster_id=self.cluster_id)
        except Exception as e:
            logger.warning("Error during disconnect", cluster_id=self.cluster_id, error=str(e))
    
    def mark_used(self) -> None:
        """Mark this connection as recently used"""
        self._last_used = datetime.utcnow()
    
    # Abstract methods to be implemented by subclasses
    
    @abstractmethod
    async def _do_connect(self) -> None:
        """Internal connect implementation"""
        pass
    
    @abstractmethod
    async def _do_disconnect(self) -> None:
        """Internal disconnect implementation"""
        pass
    
    @abstractmethod
    async def get_cluster_info(self) -> ClusterInfo:
        """Get cluster information (nodes, pods, namespaces count)"""
        pass
    
    @abstractmethod
    async def check_gadget_health(self) -> GadgetHealth:
        """Check Inspector Gadget health status"""
        pass
    
    @abstractmethod
    async def get_namespaces(self) -> List[Namespace]:
        """Get list of namespaces"""
        pass
    
    @abstractmethod
    async def get_deployments(self, namespace: Optional[str] = None) -> List[Deployment]:
        """Get list of deployments"""
        pass
    
    @abstractmethod
    async def get_pods(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Pod]:
        """Get list of pods"""
        pass
    
    @abstractmethod
    async def get_services(self, namespace: Optional[str] = None) -> List[Service]:
        """Get list of services"""
        pass

    @abstractmethod
    async def get_statefulsets(self, namespace: Optional[str] = None) -> List[StatefulSet]:
        """Get list of statefulsets"""
        pass

    @abstractmethod
    async def get_configmaps(self, namespace: Optional[str] = None) -> List[ConfigMap]:
        """Get list of configmaps with data hash"""
        pass

    @abstractmethod
    async def get_secrets(self, namespace: Optional[str] = None) -> List[Secret]:
        """Get list of secrets with data hash"""
        pass
    
    @abstractmethod
    async def get_network_policies(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of network policies with spec hash"""
        pass

    @abstractmethod
    async def get_ingresses(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of ingresses with spec hash"""
        pass

    @abstractmethod
    async def get_routes(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of OpenShift routes with spec hash"""
        pass

    @abstractmethod
    async def get_labels(self, namespace: Optional[str] = None) -> List[str]:
        """Get unique labels from resources"""
        pass

