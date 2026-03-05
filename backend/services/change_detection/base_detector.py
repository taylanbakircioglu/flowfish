"""
Base Detector Module

Provides abstract base class for change detectors and the Change data model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid


class ChangeSource(str, Enum):
    """Source of the change detection"""
    K8S_API = "k8s_api"
    EBPF_EVENTS = "ebpf_events"


class ChangeType(str, Enum):
    """Types of changes that can be detected"""
    # K8s API based (infrastructure) - Workloads
    REPLICA_CHANGED = "replica_changed"
    CONFIG_CHANGED = "config_changed"
    IMAGE_CHANGED = "image_changed"
    LABEL_CHANGED = "label_changed"
    RESOURCE_CHANGED = "resource_changed"
    ENV_CHANGED = "env_changed"
    SPEC_CHANGED = "spec_changed"

    # K8s API based (infrastructure) - Services
    SERVICE_PORT_CHANGED = "service_port_changed"
    SERVICE_SELECTOR_CHANGED = "service_selector_changed"
    SERVICE_TYPE_CHANGED = "service_type_changed"
    SERVICE_ADDED = "service_added"
    SERVICE_REMOVED = "service_removed"

    # K8s API based (infrastructure) - Network/Ingress
    NETWORK_POLICY_ADDED = "network_policy_added"
    NETWORK_POLICY_REMOVED = "network_policy_removed"
    NETWORK_POLICY_CHANGED = "network_policy_changed"
    INGRESS_ADDED = "ingress_added"
    INGRESS_REMOVED = "ingress_removed"
    INGRESS_CHANGED = "ingress_changed"
    ROUTE_ADDED = "route_added"
    ROUTE_REMOVED = "route_removed"
    ROUTE_CHANGED = "route_changed"

    # eBPF based - Connection changes
    CONNECTION_ADDED = "connection_added"
    CONNECTION_REMOVED = "connection_removed"
    PORT_CHANGED = "port_changed"
    
    # eBPF based - Anomalies
    TRAFFIC_ANOMALY = "traffic_anomaly"
    DNS_ANOMALY = "dns_anomaly"
    PROCESS_ANOMALY = "process_anomaly"
    ERROR_ANOMALY = "error_anomaly"

    # Legacy types (for compatibility)
    WORKLOAD_ADDED = "workload_added"
    WORKLOAD_REMOVED = "workload_removed"
    NAMESPACE_CHANGED = "namespace_changed"


class RiskLevel(str, Enum):
    """Risk level of the change"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Change:
    """
    Represents a detected change.
    
    This is the core data structure used by all detectors.
    It maps directly to the ClickHouse change_events table.
    """
    # Required fields
    change_type: str
    target: str
    namespace: str
    details: str
    
    # Auto-generated fields
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    # Context fields
    cluster_id: Optional[int] = None
    analysis_id: Optional[str] = None
    run_id: Optional[int] = None
    run_number: Optional[int] = None
    
    # Source tracking
    source: str = ChangeSource.K8S_API.value
    
    # Risk assessment
    risk_level: str = RiskLevel.MEDIUM.value
    affected_services: int = 0
    blast_radius: int = 0
    
    # State tracking
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    entity_type: str = "workload"
    entity_id: Optional[int] = None
    namespace_id: Optional[int] = None
    changed_by: str = "auto-discovery"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ClickHouse insertion"""
        return {
            "event_id": self.event_id,
            "timestamp": self.detected_at.isoformat(),
            "detected_at": self.detected_at.isoformat(),
            "cluster_id": self.cluster_id,
            "analysis_id": self.analysis_id,
            "run_id": self.run_id or 0,
            "run_number": self.run_number or 1,
            "change_type": self.change_type,
            "risk_level": self.risk_level,
            "target_name": self.target,
            "target_namespace": self.namespace,
            "target_type": self.entity_type,
            "entity_id": self.entity_id or 0,
            "namespace_id": self.namespace_id,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "affected_services": self.affected_services,
            "blast_radius": self.blast_radius,
            "changed_by": self.changed_by,
            "details": self.details,
            "metadata": {
                **self.metadata,
                "source": self.source
            }
        }
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to API response format (for /changes endpoint)"""
        return {
            "id": hash(self.event_id) % (10 ** 9),  # Generate numeric ID from UUID
            "cluster_id": self.cluster_id,
            "analysis_id": self.analysis_id,
            "timestamp": self.detected_at.isoformat(),
            "change_type": self.change_type,
            "target": self.target,
            "namespace": self.namespace,
            "details": self.details,
            "risk": self.risk_level,
            "affected_services": self.affected_services,
            "changed_by": self.changed_by,
            "status": "detected",
            "metadata": self.metadata
        }


class BaseDetector(ABC):
    """
    Abstract base class for change detectors.
    
    All detectors must implement the detect() method which returns
    a list of Change objects.
    """
    
    def __init__(self):
        self.source: ChangeSource = ChangeSource.K8S_API
    
    @abstractmethod
    async def detect(
        self,
        cluster_id: int,
        analysis_id: str,
        **kwargs
    ) -> List[Change]:
        """
        Detect changes for the given cluster and analysis.
        
        Args:
            cluster_id: The cluster to analyze
            analysis_id: The analysis ID for context
            **kwargs: Additional detector-specific parameters
            
        Returns:
            List of detected Change objects
        """
        pass
    
    def assess_risk(self, change: Change) -> str:
        """
        Assess the risk level of a change.
        
        Can be overridden by subclasses for custom risk assessment.
        
        Args:
            change: The change to assess
            
        Returns:
            Risk level string (critical, high, medium, low)
        """
        # Default risk assessment based on change type and affected services
        if change.affected_services > 10:
            return RiskLevel.CRITICAL.value
        elif change.affected_services > 5:
            return RiskLevel.HIGH.value
        elif change.affected_services > 2:
            return RiskLevel.MEDIUM.value
        else:
            return RiskLevel.LOW.value
    
    def filter_by_types(
        self,
        changes: List[Change],
        enabled_types: List[str]
    ) -> List[Change]:
        """
        Filter changes by enabled types.
        
        Args:
            changes: List of changes to filter
            enabled_types: List of enabled change types (or ['all'])
            
        Returns:
            Filtered list of changes
        """
        if 'all' in enabled_types:
            return changes
        return [c for c in changes if c.change_type in enabled_types]
