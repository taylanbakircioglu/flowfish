"""
Change Detection Module

Provides hybrid change detection using:
- K8s API Detector: Infrastructure changes (replicas, configs, labels)
- eBPF Detector: Behavioral changes (connections, ports, traffic)

Both detectors are independent and trustworthy - changes from either source
are valid and written to ClickHouse.
"""

from .base_detector import BaseDetector, Change, ChangeSource
from .k8s_detector import K8sDetector
from .ebpf_detector import eBPFDetector
from .strategies import (
    DetectionStrategy,
    BaselineStrategy,
    RollingWindowStrategy,
    RunComparisonStrategy,
    get_strategy
)
from .service_port_registry import (
    ServicePortRegistry,
    ServiceConnection,
    get_service_port_registry,
    WELL_KNOWN_SERVICE_PORTS,
    EPHEMERAL_PORT_START
)

# Change types by source
K8S_CHANGE_TYPES = [
    # Workload lifecycle
    'workload_added',
    'workload_removed',
    'namespace_changed',
    # Workload infrastructure
    'replica_changed',
    'config_changed',
    'image_changed',
    'label_changed',
    'resource_changed',
    'env_changed',
    'spec_changed',
    # Service changes
    'service_port_changed',
    'service_selector_changed',
    'service_type_changed',
    'service_added',
    'service_removed',
    # Network / Ingress / Route
    'network_policy_added',
    'network_policy_removed',
    'network_policy_changed',
    'ingress_added',
    'ingress_removed',
    'ingress_changed',
    'route_added',
    'route_removed',
    'route_changed',
]

EBPF_CHANGE_TYPES = [
    # Connection changes (deterministic)
    'port_changed',
    # Anomalies (statistical/observational)
    'connection_added',
    'connection_removed',
    'traffic_anomaly',
    'dns_anomaly',
    'process_anomaly',
    'error_anomaly',
]

ALL_CHANGE_TYPES = K8S_CHANGE_TYPES + EBPF_CHANGE_TYPES

__all__ = [
    # Base classes
    'BaseDetector',
    'Change',
    'ChangeSource',
    
    # Detectors
    'K8sDetector',
    'eBPFDetector',
    
    # Service Port Registry
    'ServicePortRegistry',
    'ServiceConnection',
    'get_service_port_registry',
    'WELL_KNOWN_SERVICE_PORTS',
    'EPHEMERAL_PORT_START',
    
    # Strategies
    'DetectionStrategy',
    'BaselineStrategy',
    'RollingWindowStrategy',
    'RunComparisonStrategy',
    'get_strategy',
    
    # Constants
    'K8S_CHANGE_TYPES',
    'EBPF_CHANGE_TYPES',
    'ALL_CHANGE_TYPES',
]
