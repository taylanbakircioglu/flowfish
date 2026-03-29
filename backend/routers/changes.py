"""
Changes Router - Change Detection and Tracking API

Version: 2.0.0
Last Updated: 2026-01-08

This router provides endpoints for:
- Tracking infrastructure changes over time
- Comparing analysis snapshots
- Detecting workload and connection changes

ARCHITECTURE NOTE:
- Change events are stored ONLY in ClickHouse (PostgreSQL change_events table removed)
- All queries go directly to ClickHouse for better performance
- Run-based filtering supported for multi-cycle analyses
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from enum import Enum
import structlog
import os
import json

from utils.jwt_utils import require_permissions, get_current_user
from services.change_detection_service import (
    ChangeDetectionService, 
    get_change_detection_service,
    ChangeType as ServiceChangeType,
    RiskLevel as ServiceRiskLevel
)

logger = structlog.get_logger()

router = APIRouter()

# Feature flags
RUN_BASED_FILTERING = os.getenv("RUN_BASED_FILTERING_ENABLED", "true").lower() == "true"


async def _get_ch_analysis_id(analysis_id: int, cluster_id: Optional[int] = None) -> str:
    """Format analysis_id for ClickHouse queries.

    The change-detection worker stores analysis_id as '{id}-{cluster_id}'
    in ClickHouse. This helper resolves the cluster_id when not provided.
    """
    if cluster_id:
        return f"{analysis_id}-{cluster_id}"
    from database.postgresql import database
    row = await database.fetch_one(
        "SELECT cluster_id FROM analyses WHERE id = :aid",
        {"aid": analysis_id},
    )
    if row:
        return f"{analysis_id}-{row['cluster_id']}"
    return str(analysis_id)


# ============ Enums ============

class ChangeType(str, Enum):
    # Legacy types (backward compatibility)
    WORKLOAD_ADDED = "workload_added"
    WORKLOAD_REMOVED = "workload_removed"
    NAMESPACE_CHANGED = "namespace_changed"
    # Infrastructure changes (K8s API) - Workloads
    REPLICA_CHANGED = "replica_changed"
    CONFIG_CHANGED = "config_changed"
    IMAGE_CHANGED = "image_changed"
    LABEL_CHANGED = "label_changed"
    RESOURCE_CHANGED = "resource_changed"
    ENV_CHANGED = "env_changed"
    SPEC_CHANGED = "spec_changed"
    # Infrastructure changes (K8s API) - Services
    SERVICE_PORT_CHANGED = "service_port_changed"
    SERVICE_SELECTOR_CHANGED = "service_selector_changed"
    SERVICE_TYPE_CHANGED = "service_type_changed"
    SERVICE_ADDED = "service_added"
    SERVICE_REMOVED = "service_removed"
    # Infrastructure changes (K8s API) - Network / Ingress / Route
    NETWORK_POLICY_ADDED = "network_policy_added"
    NETWORK_POLICY_REMOVED = "network_policy_removed"
    NETWORK_POLICY_CHANGED = "network_policy_changed"
    INGRESS_ADDED = "ingress_added"
    INGRESS_REMOVED = "ingress_removed"
    INGRESS_CHANGED = "ingress_changed"
    ROUTE_ADDED = "route_added"
    ROUTE_REMOVED = "route_removed"
    ROUTE_CHANGED = "route_changed"
    # Behavioral changes (eBPF) - Connections
    CONNECTION_ADDED = "connection_added"
    CONNECTION_REMOVED = "connection_removed"
    PORT_CHANGED = "port_changed"
    # Behavioral changes (eBPF) - Anomalies
    TRAFFIC_ANOMALY = "traffic_anomaly"
    DNS_ANOMALY = "dns_anomaly"
    PROCESS_ANOMALY = "process_anomaly"
    ERROR_ANOMALY = "error_anomaly"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ============ Schemas ============

class Change(BaseModel):
    id: str  # UUID from ClickHouse
    timestamp: datetime
    change_type: ChangeType
    target: str
    namespace: str
    details: str
    risk: RiskLevel
    affected_services: int = 0
    changed_by: str = "auto-discovery"
    metadata: Optional[Dict[str, Any]] = None


class ChangeStats(BaseModel):
    total_changes: int
    by_type: Dict[str, int]
    by_risk: Dict[str, int]
    by_namespace: Dict[str, int]


class SnapshotComparison(BaseModel):
    before: Dict[str, int]
    after: Dict[str, int]
    summary: Dict[str, int]


class ChangesResponse(BaseModel):
    changes: List[Change]
    total: int
    stats: ChangeStats
    comparison: SnapshotComparison


# ============ Risk Assessment ============

def assess_change_risk(change_type: ChangeType, affected_count: int = 0) -> RiskLevel:
    """Determine risk level based on change type and impact"""
    
    # Critical-potential changes (routing/connectivity disruption)
    if change_type in [
        ChangeType.WORKLOAD_REMOVED, ChangeType.SERVICE_REMOVED,
        ChangeType.SERVICE_SELECTOR_CHANGED, ChangeType.NETWORK_POLICY_CHANGED,
        ChangeType.NETWORK_POLICY_REMOVED, ChangeType.PORT_CHANGED,
    ]:
        if affected_count > 5:
            return RiskLevel.CRITICAL
        elif affected_count > 2:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    
    # High-potential changes (service behavior modification)
    if change_type in [
        ChangeType.SERVICE_PORT_CHANGED, ChangeType.SERVICE_TYPE_CHANGED,
        ChangeType.IMAGE_CHANGED, ChangeType.INGRESS_CHANGED,
        ChangeType.INGRESS_REMOVED, ChangeType.ROUTE_CHANGED,
        ChangeType.ROUTE_REMOVED, ChangeType.ENV_CHANGED,
    ]:
        if affected_count > 5:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    
    # Medium risk changes (configuration/operational)
    if change_type in [
        ChangeType.CONNECTION_REMOVED, ChangeType.CONFIG_CHANGED,
        ChangeType.RESOURCE_CHANGED, ChangeType.SPEC_CHANGED,
        ChangeType.NETWORK_POLICY_ADDED,
    ]:
        if affected_count > 5:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    
    # Low risk changes (additive / informational)
    if change_type in [
        ChangeType.WORKLOAD_ADDED, ChangeType.CONNECTION_ADDED,
        ChangeType.REPLICA_CHANGED, ChangeType.LABEL_CHANGED,
        ChangeType.SERVICE_ADDED, ChangeType.INGRESS_ADDED,
        ChangeType.ROUTE_ADDED, ChangeType.NAMESPACE_CHANGED,
    ]:
        return RiskLevel.LOW
    
    # Anomalies — severity depends on type and blast radius
    if change_type in [
        ChangeType.ERROR_ANOMALY, ChangeType.PROCESS_ANOMALY,
    ]:
        if affected_count > 5:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    
    if change_type in [
        ChangeType.TRAFFIC_ANOMALY, ChangeType.DNS_ANOMALY,
    ]:
        if affected_count > 5:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    
    return RiskLevel.MEDIUM


# ============ Mock Data Generation ============

def generate_mock_changes(
    cluster_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    change_types: Optional[List[str]] = None,
    risk_levels: Optional[List[str]] = None
) -> List[Change]:
    """Generate realistic mock change data for MVP"""
    
    if not end_time:
        end_time = datetime.utcnow()
    if not start_time:
        start_time = end_time - timedelta(hours=24)
    
    # Sample changes with realistic data
    mock_data = [
        {
            "id": 1,
            "timestamp": end_time - timedelta(minutes=30),
            "change_type": ChangeType.WORKLOAD_ADDED,
            "target": "payment-service",
            "namespace": "production",
            "details": "New deployment created with 3 replicas",
            "affected_services": 5,
            "changed_by": "deploy-bot",
        },
        {
            "id": 2,
            "timestamp": end_time - timedelta(minutes=45),
            "change_type": ChangeType.CONNECTION_ADDED,
            "target": "api-gateway → payment-service",
            "namespace": "production",
            "details": "New TCP connection on port 8080",
            "affected_services": 2,
            "changed_by": "auto-discovery",
        },
        {
            "id": 3,
            "timestamp": end_time - timedelta(hours=1),
            "change_type": ChangeType.WORKLOAD_REMOVED,
            "target": "legacy-auth-service",
            "namespace": "production",
            "details": "Deployment deleted, 0 replicas remaining",
            "affected_services": 8,
            "changed_by": "admin@company.com",
        },
        {
            "id": 4,
            "timestamp": end_time - timedelta(hours=1, minutes=30),
            "change_type": ChangeType.PORT_CHANGED,
            "target": "database-primary",
            "namespace": "data",
            "details": "Port changed from 5432 to 5433",
            "affected_services": 12,
            "changed_by": "dba@company.com",
        },
        {
            "id": 5,
            "timestamp": end_time - timedelta(hours=2),
            "change_type": ChangeType.CONFIG_CHANGED,
            "target": "redis-cache",
            "namespace": "cache",
            "details": "ConfigMap updated: max_connections increased to 10000",
            "affected_services": 3,
            "changed_by": "ops-team",
        },
        {
            "id": 6,
            "timestamp": end_time - timedelta(hours=3),
            "change_type": ChangeType.CONNECTION_REMOVED,
            "target": "frontend → legacy-auth-service",
            "namespace": "production",
            "details": "Connection no longer observed after service removal",
            "affected_services": 1,
            "changed_by": "auto-discovery",
        },
        {
            "id": 7,
            "timestamp": end_time - timedelta(hours=4),
            "change_type": ChangeType.REPLICA_CHANGED,
            "target": "worker-service",
            "namespace": "jobs",
            "details": "Replicas scaled from 2 to 5 by HPA",
            "affected_services": 0,
            "changed_by": "hpa-controller",
        },
        {
            "id": 8,
            "timestamp": end_time - timedelta(hours=5),
            "change_type": ChangeType.WORKLOAD_ADDED,
            "target": "notification-service",
            "namespace": "messaging",
            "details": "New microservice deployed with 2 replicas",
            "affected_services": 3,
            "changed_by": "ci-pipeline",
        },
        {
            "id": 9,
            "timestamp": end_time - timedelta(hours=6),
            "change_type": ChangeType.CONNECTION_ADDED,
            "target": "notification-service → kafka-broker",
            "namespace": "messaging",
            "details": "New Kafka producer connection on port 9092",
            "affected_services": 1,
            "changed_by": "auto-discovery",
        },
        {
            "id": 10,
            "timestamp": end_time - timedelta(hours=8),
            "change_type": ChangeType.NAMESPACE_CHANGED,
            "target": "monitoring-agent",
            "namespace": "observability",
            "details": "Moved from 'kube-system' to 'observability' namespace",
            "affected_services": 4,
            "changed_by": "platform-team",
        },
    ]
    
    changes = []
    for data in mock_data:
        change = Change(
            id=str(data["id"]),  # Convert to string
            timestamp=data["timestamp"],
            change_type=data["change_type"],
            target=data["target"],
            namespace=data["namespace"],
            details=data["details"],
            risk=assess_change_risk(data["change_type"], data["affected_services"]),
            affected_services=data["affected_services"],
            changed_by=data["changed_by"],
        )
        
        # Filter by time range
        if change.timestamp < start_time or change.timestamp > end_time:
            continue
        
        # Filter by change types
        if change_types and change.change_type.value not in change_types:
            continue
        
        # Filter by risk levels
        if risk_levels and change.risk.value not in risk_levels:
            continue
        
        changes.append(change)
    
    return sorted(changes, key=lambda x: x.timestamp, reverse=True)


def calculate_stats(changes: List[Change]) -> ChangeStats:
    """Calculate statistics from changes"""
    by_type: Dict[str, int] = {}
    by_risk: Dict[str, int] = {}
    by_namespace: Dict[str, int] = {}
    
    for change in changes:
        by_type[change.change_type.value] = by_type.get(change.change_type.value, 0) + 1
        by_risk[change.risk.value] = by_risk.get(change.risk.value, 0) + 1
        by_namespace[change.namespace] = by_namespace.get(change.namespace, 0) + 1
    
    return ChangeStats(
        total_changes=len(changes),
        by_type=by_type,
        by_risk=by_risk,
        by_namespace=by_namespace,
    )


# Helper functions for change detail enrichment
def _get_severity_indicator(risk_level: str, affected_services: int, blast_radius: int) -> dict:
    """Calculate severity indicator for UI display"""
    score = 0
    factors = []
    
    # Risk level contribution
    risk_scores = {"critical": 40, "high": 30, "medium": 15, "low": 5}
    score += risk_scores.get(risk_level, 10)
    if risk_level in ["critical", "high"]:
        factors.append(f"Risk level: {risk_level}")
    
    # Affected services contribution
    if affected_services > 10:
        score += 30
        factors.append(f"High impact: {affected_services} services affected")
    elif affected_services > 5:
        score += 20
        factors.append(f"Medium impact: {affected_services} services affected")
    elif affected_services > 0:
        score += 10
        factors.append(f"Low impact: {affected_services} services affected")
    
    # Blast radius contribution
    if blast_radius > 20:
        score += 30
        factors.append(f"Large blast radius: {blast_radius}")
    elif blast_radius > 10:
        score += 15
        factors.append(f"Medium blast radius: {blast_radius}")
    
    # Determine level
    if score >= 70:
        level = "critical"
        color = "#cf1322"
    elif score >= 50:
        level = "high"
        color = "#c75450"
    elif score >= 30:
        level = "medium"
        color = "#b89b5d"
    else:
        level = "low"
        color = "#4d9f7c"
    
    return {
        "score": min(score, 100),
        "level": level,
        "color": color,
        "factors": factors
    }


def _get_change_category(change_type: str) -> dict:
    """Categorize change type for UI grouping"""
    categories = {
        "infrastructure": {
            "types": [
                "replica_changed", "config_changed", "image_changed", "label_changed",
                "workload_added", "workload_removed", "namespace_changed",
                "resource_changed", "env_changed", "spec_changed",
                "service_port_changed", "service_selector_changed", "service_type_changed",
                "service_added", "service_removed",
                "network_policy_added", "network_policy_removed", "network_policy_changed",
                "ingress_added", "ingress_removed", "ingress_changed",
                "route_added", "route_removed", "route_changed",
            ],
            "icon": "CloudServerOutlined",
            "color": "#0891b2",
            "description": "Infrastructure changes affect workload configurations and deployments"
        },
        "network": {
            "types": ["connection_added", "connection_removed", "port_changed"],
            "icon": "ApiOutlined",
            "color": "#4d9f7c",
            "description": "Network changes affect service-to-service communications"
        },
        "behavioral": {
            "types": ["traffic_anomaly", "dns_anomaly", "process_anomaly", "error_anomaly"],
            "icon": "AlertOutlined",
            "color": "#d4756a",
            "description": "Behavioral anomalies detected through eBPF monitoring"
        }
    }
    
    for category, info in categories.items():
        if change_type in info["types"]:
            return {
                "name": category,
                "icon": info["icon"],
                "color": info["color"],
                "description": info["description"]
            }
    
    return {
        "name": "other",
        "icon": "QuestionCircleOutlined",
        "color": "#8c8c8c",
        "description": "Other changes"
    }


def _get_recommended_actions(change_type: str, risk_level: str) -> list:
    """Get recommended actions based on change type and risk"""
    actions = []
    
    # Type-specific recommendations
    type_actions = {
        "replica_changed": [
            {"action": "Verify pod health", "priority": "high", "automated": True},
            {"action": "Check resource utilization", "priority": "medium", "automated": True},
        ],
        "config_changed": [
            {"action": "Review configuration diff", "priority": "high", "automated": False},
            {"action": "Validate application behavior", "priority": "high", "automated": False},
        ],
        "image_changed": [
            {"action": "Verify image version compatibility", "priority": "high", "automated": False},
            {"action": "Check for vulnerability reports", "priority": "medium", "automated": True},
        ],
        "resource_changed": [
            {"action": "Monitor resource utilization post-change", "priority": "medium", "automated": True},
            {"action": "Verify no OOMKill events", "priority": "high", "automated": True},
        ],
        "env_changed": [
            {"action": "Validate environment configuration", "priority": "high", "automated": False},
            {"action": "Check for secret exposure", "priority": "critical", "automated": False},
        ],
        "service_port_changed": [
            {"action": "Verify client connectivity", "priority": "high", "automated": True},
            {"action": "Update dependent configurations", "priority": "high", "automated": False},
        ],
        "service_selector_changed": [
            {"action": "Verify pod selection is correct", "priority": "critical", "automated": False},
            {"action": "Check for traffic routing issues", "priority": "high", "automated": True},
        ],
        "service_removed": [
            {"action": "Verify removal is intentional", "priority": "critical", "automated": False},
            {"action": "Check for dependent services", "priority": "high", "automated": True},
        ],
        "network_policy_changed": [
            {"action": "Verify network connectivity", "priority": "high", "automated": True},
            {"action": "Review policy rules", "priority": "high", "automated": False},
        ],
        "network_policy_removed": [
            {"action": "Assess security implications", "priority": "critical", "automated": False},
            {"action": "Check for unauthorized access", "priority": "high", "automated": True},
        ],
        "ingress_changed": [
            {"action": "Verify external access", "priority": "high", "automated": True},
            {"action": "Check TLS certificate validity", "priority": "medium", "automated": True},
        ],
        "route_changed": [
            {"action": "Verify route accessibility", "priority": "high", "automated": True},
            {"action": "Check TLS configuration", "priority": "medium", "automated": True},
        ],
        "connection_added": [
            {"action": "Verify connection is expected", "priority": "medium", "automated": False},
            {"action": "Check network policies", "priority": "medium", "automated": True},
        ],
        "connection_removed": [
            {"action": "Verify removal is intentional", "priority": "high", "automated": False},
            {"action": "Check for service disruption", "priority": "high", "automated": True},
        ],
        "dns_anomaly": [
            {"action": "Review DNS query patterns", "priority": "medium", "automated": False},
            {"action": "Check for unauthorized domains", "priority": "high", "automated": True},
        ],
        "process_anomaly": [
            {"action": "Review process execution context", "priority": "high", "automated": False},
            {"action": "Check for security implications", "priority": "critical", "automated": False},
        ],
        "traffic_anomaly": [
            {"action": "Analyze traffic patterns", "priority": "medium", "automated": True},
            {"action": "Check for DDoS indicators", "priority": "high", "automated": True},
        ],
        "error_anomaly": [
            {"action": "Review error logs", "priority": "high", "automated": False},
            {"action": "Check service health", "priority": "high", "automated": True},
        ],
        "spec_changed": [
            {"action": "Review pod spec diff", "priority": "medium", "automated": False},
            {"action": "Verify rollout status", "priority": "medium", "automated": True},
        ],
        "label_changed": [
            {"action": "Check label selector impact on services", "priority": "medium", "automated": True},
            {"action": "Verify network policy selectors", "priority": "medium", "automated": False},
        ],
        "service_added": [
            {"action": "Verify service endpoint readiness", "priority": "medium", "automated": True},
        ],
        "service_type_changed": [
            {"action": "Verify external access implications", "priority": "high", "automated": False},
            {"action": "Check load balancer provisioning", "priority": "medium", "automated": True},
        ],
        "network_policy_added": [
            {"action": "Verify policy does not block required traffic", "priority": "high", "automated": True},
        ],
        "ingress_added": [
            {"action": "Verify external DNS and TLS configuration", "priority": "medium", "automated": True},
        ],
        "ingress_removed": [
            {"action": "Verify external access is no longer needed", "priority": "high", "automated": False},
        ],
        "route_added": [
            {"action": "Verify route DNS and TLS configuration", "priority": "medium", "automated": True},
        ],
        "route_removed": [
            {"action": "Verify route removal is intentional", "priority": "high", "automated": False},
        ],
        "workload_added": [
            {"action": "Verify resource allocation and limits", "priority": "medium", "automated": True},
        ],
        "workload_removed": [
            {"action": "Verify removal is intentional", "priority": "high", "automated": False},
            {"action": "Check for dependent services", "priority": "high", "automated": True},
        ],
        "port_changed": [
            {"action": "Verify service port mapping consistency", "priority": "high", "automated": True},
            {"action": "Check client connectivity", "priority": "high", "automated": False},
        ],
        "namespace_changed": [
            {"action": "Review namespace configuration changes", "priority": "medium", "automated": False},
        ],
    }
    
    actions = type_actions.get(change_type, [
        {"action": "Review change details", "priority": "medium", "automated": False}
    ])
    
    # Add risk-based actions
    if risk_level == "critical":
        actions.insert(0, {"action": "Immediate investigation required", "priority": "critical", "automated": False})
    elif risk_level == "high":
        actions.insert(0, {"action": "Prioritize review", "priority": "high", "automated": False})
    
    return actions


def calculate_comparison(changes: List[Change]) -> SnapshotComparison:
    """Calculate before/after comparison from changes"""
    
    # Baseline counts (mock)
    before = {
        "workloads": 45,
        "connections": 128,
        "namespaces": 8,
    }
    
    # Calculate deltas
    workload_delta = 0
    connection_delta = 0
    
    _added_types = {
        ChangeType.WORKLOAD_ADDED, ChangeType.SERVICE_ADDED,
        ChangeType.NETWORK_POLICY_ADDED, ChangeType.INGRESS_ADDED,
        ChangeType.ROUTE_ADDED, ChangeType.CONNECTION_ADDED,
    }
    _removed_types = {
        ChangeType.WORKLOAD_REMOVED, ChangeType.SERVICE_REMOVED,
        ChangeType.NETWORK_POLICY_REMOVED, ChangeType.INGRESS_REMOVED,
        ChangeType.ROUTE_REMOVED, ChangeType.CONNECTION_REMOVED,
    }
    _modified_types = {
        ChangeType.REPLICA_CHANGED, ChangeType.CONFIG_CHANGED,
        ChangeType.IMAGE_CHANGED, ChangeType.LABEL_CHANGED,
        ChangeType.RESOURCE_CHANGED, ChangeType.ENV_CHANGED,
        ChangeType.SPEC_CHANGED, ChangeType.PORT_CHANGED,
        ChangeType.SERVICE_PORT_CHANGED, ChangeType.SERVICE_SELECTOR_CHANGED,
        ChangeType.SERVICE_TYPE_CHANGED, ChangeType.NETWORK_POLICY_CHANGED,
        ChangeType.INGRESS_CHANGED, ChangeType.ROUTE_CHANGED,
        ChangeType.NAMESPACE_CHANGED,
    }
    _anomaly_types = {
        ChangeType.TRAFFIC_ANOMALY, ChangeType.DNS_ANOMALY,
        ChangeType.PROCESS_ANOMALY, ChangeType.ERROR_ANOMALY,
    }
    
    for change in changes:
        if change.change_type == ChangeType.WORKLOAD_ADDED:
            workload_delta += 1
        elif change.change_type == ChangeType.WORKLOAD_REMOVED:
            workload_delta -= 1
        elif change.change_type == ChangeType.CONNECTION_ADDED:
            connection_delta += 1
        elif change.change_type == ChangeType.CONNECTION_REMOVED:
            connection_delta -= 1
    
    after = {
        "workloads": before["workloads"] + workload_delta,
        "connections": before["connections"] + connection_delta,
        "namespaces": before["namespaces"],
    }
    
    # Summary
    added = sum(1 for c in changes if c.change_type in _added_types)
    removed = sum(1 for c in changes if c.change_type in _removed_types)
    modified = sum(1 for c in changes if c.change_type in _modified_types)
    anomalies = sum(1 for c in changes if c.change_type in _anomaly_types)
    
    return SnapshotComparison(
        before=before,
        after=after,
        summary={
            "added": added,
            "removed": removed,
            "modified": modified + anomalies,
        }
    )


# ============ Endpoints ============

@router.get("/changes", response_model=ChangesResponse)
async def get_changes(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    run_id: Optional[int] = Query(None, description="Filter by specific run ID (requires RUN_BASED_FILTERING feature)"),
    run_ids: Optional[str] = Query(None, description="Comma-separated run IDs to filter by"),
    start_time: Optional[datetime] = Query(None, description="Start of time range"),
    end_time: Optional[datetime] = Query(None, description="End of time range"),
    change_types: Optional[str] = Query(None, description="Comma-separated change types"),
    risk_levels: Optional[str] = Query(None, description="Comma-separated risk levels"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of changes"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Get infrastructure changes for a cluster.
    
    Returns a list of detected changes including:
    - Workload additions/removals
    - Connection changes
    - Configuration updates
    - Port changes
    
    Each change includes:
    - Timestamp
    - Change type
    - Risk assessment
    - Affected services count
    
    NOTE: Change events stored ONLY in ClickHouse. PostgreSQL change_events table removed.
    """
    logger.info(
        "Getting changes from ClickHouse",
        cluster_id=cluster_id,
        analysis_id=analysis_id,
        start_time=start_time,
        end_time=end_time
    )
    
    # Parse filter parameters
    type_filter = change_types.split(",") if change_types else None
    risk_filter = risk_levels.split(",") if risk_levels else None
    
    # Parse run_ids if provided
    run_id_list = None
    if run_id:
        run_id_list = [run_id]
    elif run_ids and RUN_BASED_FILTERING:
        try:
            run_id_list = [int(r.strip()) for r in run_ids.split(",")]
        except ValueError:
            pass
    
    # Require cluster_id for ClickHouse query
    if not cluster_id:
        logger.warning("No cluster_id provided, returning empty result")
        return ChangesResponse(
            changes=[],
            total=0,
            stats=ChangeStats(
                total_changes=0,
                by_type={},
                by_risk={},
                by_namespace={}
            ),
            comparison=SnapshotComparison(
                before={"workloads": 0, "connections": 0, "namespaces": 0},
                after={"workloads": 0, "connections": 0, "namespaces": 0},
                summary={"added": 0, "removed": 0, "changed": 0}
            )
        )
    
    # Query ClickHouse (ONLY storage for change events)
    try:
        result = await get_changes_from_clickhouse(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            run_ids=run_id_list,
            start_time=start_time,
            end_time=end_time,
            change_types=type_filter,
            risk_levels=risk_filter,
            limit=limit,
            offset=offset
        )
        logger.info(
            "ClickHouse data returned",
            total_changes=result.total,
            changes_count=len(result.changes)
        )
        return result
    except Exception as e:
        logger.error(
            "ClickHouse query failed",
            cluster_id=cluster_id,
            error=str(e)
        )
        # Return empty result on error (no fallback)
        return ChangesResponse(
            changes=[],
            total=0,
            stats=ChangeStats(
                total_changes=0,
                by_type={},
                by_risk={},
                by_namespace={}
            ),
            comparison=SnapshotComparison(
                before={"workloads": 0, "connections": 0, "namespaces": 0},
                after={"workloads": 0, "connections": 0, "namespaces": 0},
                summary={"added": 0, "removed": 0, "changed": 0}
            )
        )
    
    # NOTE: Mock data path removed. All data comes from ClickHouse.


async def get_changes_real_data(
    change_service: ChangeDetectionService,
    cluster_id: int,
    analysis_id: Optional[int],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    change_types: Optional[List[str]],
    risk_levels: Optional[List[str]],
    limit: int,
    offset: int
) -> ChangesResponse:
    """
    Get changes from real database data
    
    Queries PostgreSQL change_events table for recorded changes.
    """
    # Fetch changes from database
    changes_data, total = await change_service.get_changes_from_database(
        cluster_id=cluster_id,
        analysis_id=analysis_id,
        start_time=start_time,
        end_time=end_time,
        change_types=change_types,
        risk_levels=risk_levels,
        limit=limit,
        offset=offset
    )
    
    # Convert to response model
    changes = []
    for data in changes_data:
        try:
            change = Change(
                id=data["id"],
                timestamp=data["timestamp"],
                change_type=ChangeType(data["change_type"]),
                target=data["target"],
                namespace=data.get("namespace", "unknown"),
                details=data.get("details", ""),
                risk=RiskLevel(data.get("risk", "medium")),
                affected_services=data.get("affected_services", 0),
                changed_by=data.get("changed_by", "auto-discovery"),
                metadata=data.get("metadata")
            )
            changes.append(change)
        except Exception as e:
            logger.warning("Failed to parse change record", error=str(e), data=data)
    
    # Get stats from database
    stats_data = await change_service.get_change_stats(
        cluster_id=cluster_id,
        analysis_id=analysis_id,
        start_time=start_time,
        end_time=end_time
    )
    
    stats = ChangeStats(
        total_changes=stats_data.get("total_changes", 0),
        by_type=stats_data.get("by_type", {}),
        by_risk=stats_data.get("by_risk", {}),
        by_namespace=stats_data.get("by_namespace", {})
    )
    
    # Get comparison from database
    comparison_data = await change_service.get_snapshot_comparison(
        cluster_id=cluster_id,
        analysis_id=analysis_id,
        start_time=start_time,
        end_time=end_time
    )
    
    comparison = SnapshotComparison(
        before=comparison_data.get("before", {}),
        after=comparison_data.get("after", {}),
        summary=comparison_data.get("summary", {})
    )
    
    logger.info(
        "Real data changes retrieved",
        cluster_id=cluster_id,
        total=total,
        returned=len(changes)
    )
    
    return ChangesResponse(
        changes=changes,
        total=total,
        stats=stats,
        comparison=comparison,
    )


async def _get_comparison_data(cluster_id: int, analysis_id: Optional[int] = None) -> dict:
    """Get workload/connection/namespace counts for comparison cards.
    Uses Neo4j for analysis-specific data when analysis_id is provided.
    """
    from database.postgresql import database
    from database.neo4j import neo4j_service
    
    try:
        # When analysis_id is provided, use Neo4j for analysis-specific counts
        if analysis_id:
            try:
                neo4j_workloads = neo4j_service.get_workloads(cluster_id=cluster_id, analysis_id=analysis_id)
                neo4j_communications = neo4j_service.get_communications(cluster_id=cluster_id, analysis_id=analysis_id)
                
                # Always use Neo4j results when analysis_id is provided (even if empty)
                # This ensures users see analysis-specific data, not cluster-wide fallback
                workload_count = len(neo4j_workloads) if neo4j_workloads is not None else 0
                connection_count = len(neo4j_communications) if neo4j_communications is not None else 0
                
                # Get unique namespaces from workloads
                namespaces = set()
                if neo4j_workloads:
                    for w in neo4j_workloads:
                        ns = w.get('namespace')
                        if ns:
                            namespaces.add(ns)
                namespace_count = len(namespaces)
                
                logger.debug(
                    "Got analysis-specific counts from Neo4j",
                    analysis_id=analysis_id,
                    workloads=workload_count,
                    connections=connection_count,
                    namespaces=namespace_count
                )
                
                return {
                    "before": {
                        "workloads": workload_count,
                        "connections": connection_count,
                        "namespaces": namespace_count
                    },
                    "after": {
                        "workloads": workload_count,
                        "connections": connection_count,
                        "namespaces": namespace_count
                    },
                    "added": 0,
                    "removed": 0,
                    "modified": 0
                }
            except Exception as neo4j_err:
                logger.warning("Neo4j query failed, falling back to PostgreSQL", error=str(neo4j_err))
        
        # Fallback: cluster-wide counts from PostgreSQL
        workload_result = await database.fetch_one(
            "SELECT COUNT(*) as count FROM workloads WHERE cluster_id = :cluster_id AND is_active = true",
            {"cluster_id": cluster_id}
        )
        workload_count = workload_result["count"] if workload_result else 0
        
        # Connection count  
        connection_result = await database.fetch_one(
            "SELECT COUNT(*) as count FROM communications WHERE cluster_id = :cluster_id AND is_active = true",
            {"cluster_id": cluster_id}
        )
        connection_count = connection_result["count"] if connection_result else 0
        
        # Namespace count
        namespace_result = await database.fetch_one(
            "SELECT COUNT(DISTINCT name) as count FROM namespaces WHERE cluster_id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        namespace_count = namespace_result["count"] if namespace_result else 0
        
        return {
            "before": {
                "workloads": workload_count,
                "connections": connection_count,
                "namespaces": namespace_count
            },
            "after": {
                "workloads": workload_count,
                "connections": connection_count,
                "namespaces": namespace_count
            },
            "added": 0,
            "removed": 0,
            "modified": 0
        }
    except Exception as e:
        logger.warning("Comparison data fetch failed", error=str(e))
        return {"before": {}, "after": {}}


async def get_changes_from_clickhouse(
    cluster_id: int,
    analysis_id: Optional[int],
    run_ids: Optional[List[int]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    change_types: Optional[List[str]],
    risk_levels: Optional[List[str]],
    limit: int,
    offset: int
) -> ChangesResponse:
    """
    Get changes from ClickHouse (ONLY storage for change events)
    
    This provides better performance for large datasets and run-based filtering.
    PostgreSQL change_events table has been removed.
    
    Uses the ClickHouseService from database.clickhouse module.
    """
    from database.clickhouse import get_clickhouse_client
    
    try:
        client = get_clickhouse_client()
        
        # Build WHERE clauses:
        # - base_where: cluster/analysis/time scoping (used for stats - always unfiltered)
        # - filtered_where: base + change_type/risk_level filters (used for paginated results)
        base_parts = [f"cluster_id = {cluster_id}"]
        
        if analysis_id:
            ch_aid = await _get_ch_analysis_id(analysis_id, cluster_id)
            base_parts.append(f"analysis_id = '{ch_aid}'")
        
        if run_ids:
            run_ids_str = ",".join(str(r) for r in run_ids)
            base_parts.append(f"run_id IN ({run_ids_str})")
        
        if start_time:
            base_parts.append(f"timestamp >= '{start_time.isoformat()}'")
        
        if end_time:
            base_parts.append(f"timestamp <= '{end_time.isoformat()}'")
        
        base_where = " AND ".join(base_parts)
        
        filter_parts = list(base_parts)
        if change_types:
            valid_types = {ct.value for ct in ChangeType}
            safe_types = [t for t in change_types if t in valid_types]
            if safe_types:
                types_str = ",".join(f"'{t}'" for t in safe_types)
                filter_parts.append(f"change_type IN ({types_str})")
        
        if risk_levels:
            valid_risks = {rl.value for rl in RiskLevel}
            safe_risks = [r for r in risk_levels if r in valid_risks]
            if safe_risks:
                risks_str = ",".join(f"'{r}'" for r in safe_risks)
                filter_parts.append(f"risk_level IN ({risks_str})")
        
        where_clause = " AND ".join(filter_parts)
        
        # Query changes
        query = f"""
        SELECT 
            event_id,
            timestamp,
            detected_at,
            change_type,
            risk_level,
            target_name,
            target_namespace,
            affected_services,
            changed_by,
            details,
            metadata,
            run_id,
            run_number
        FROM change_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        rows = client.execute(query)
        
        # Query total count
        count_query = f"SELECT count() FROM change_events WHERE {where_clause}"
        total = client.execute(count_query)[0][0]
        
        # Debug logging - critical for diagnosing data issues
        logger.info(
            "ClickHouse query results",
            where_clause=where_clause,
            rows_returned=len(rows),
            total_count=total,
            limit=limit,
            offset=offset
        )
        
        # Log sample row structure if data exists but might have parse issues
        if rows and len(rows) > 0 and total > 0:
            sample_row = rows[0]
            logger.debug(
                "Sample row structure",
                row_length=len(sample_row) if sample_row else 0,
                change_type_value=sample_row[3] if len(sample_row) > 3 else None,
                risk_level_value=sample_row[4] if len(sample_row) > 4 else None
            )
        
        # Convert to response model
        changes = []
        parse_errors = 0
        for idx, row in enumerate(rows):
            try:
                # Use actual event_id (UUID) as the change ID for detail lookups
                event_id = str(row[0]) if row[0] else str(idx + offset + 1)
                
                # Safely parse change_type - handle unknown types gracefully
                raw_change_type = row[3] if len(row) > 3 else None
                valid_change_types = [e.value for e in ChangeType]
                if raw_change_type in valid_change_types:
                    change_type = ChangeType(raw_change_type)
                else:
                    # Map unknown types or skip
                    logger.debug(f"Unknown change_type: {raw_change_type}, mapping to CONFIG_CHANGED")
                    change_type = ChangeType.CONFIG_CHANGED
                
                # Safely parse risk_level
                raw_risk_level = row[4] if len(row) > 4 else None
                valid_risk_levels = [e.value for e in RiskLevel]
                if raw_risk_level in valid_risk_levels:
                    risk_level = RiskLevel(raw_risk_level)
                else:
                    risk_level = RiskLevel.MEDIUM
                
                change = Change(
                    id=event_id,  # Use real event_id (UUID) for proper detail lookups
                    timestamp=row[1] if row[1] else row[2],  # timestamp or detected_at
                    change_type=change_type,
                    target=row[5] or "unknown",
                    namespace=row[6] or "unknown",
                    details=row[9] or "",
                    risk=risk_level,
                    affected_services=row[7] or 0,
                    changed_by=row[8] or "auto-discovery",
                    metadata={"run_id": row[11] if len(row) > 11 else None, "run_number": row[12] if len(row) > 12 else None}
                )
                changes.append(change)
            except Exception as e:
                parse_errors += 1
                if parse_errors <= 5:  # Only log first 5 errors to avoid spam
                    logger.warning(
                        "Failed to parse ClickHouse change record",
                        error=str(e),
                        row_index=idx,
                        row_data=str(row)[:500] if row else None  # Truncate for logging
                    )
        
        # Log parse summary
        if parse_errors > 0:
            logger.warning(
                "Change record parse errors",
                total_rows=len(rows),
                successful_parses=len(changes),
                parse_errors=parse_errors
            )
        
        # Query stats from UNFILTERED data (base_where) so summary cards
        # always reflect the full analysis picture regardless of type/risk filters.
        stats_query = f"""
        SELECT 
            change_type,
            risk_level,
            count() as cnt
        FROM change_events
        WHERE {base_where}
        GROUP BY change_type, risk_level
        """
        
        try:
            stats_rows = client.execute(stats_query)
            by_type = {}
            by_risk = {}
            for stat_row in stats_rows:
                by_type[stat_row[0]] = by_type.get(stat_row[0], 0) + stat_row[2]
                by_risk[stat_row[1]] = by_risk.get(stat_row[1], 0) + stat_row[2]
        except Exception as e:
            logger.warning("Stats query failed, using empty stats", error=str(e))
            by_type = {}
            by_risk = {}
        
        by_namespace = {}
        try:
            ns_query = f"""
            SELECT target_namespace, count() as cnt
            FROM change_events
            WHERE {base_where}
            GROUP BY target_namespace
            """
            ns_rows = client.execute(ns_query)
            by_namespace = {str(r[0]): r[1] for r in ns_rows if r[0]}
        except Exception as e:
            logger.warning("Namespace stats query failed", error=str(e))
        
        stats = ChangeStats(
            total_changes=total,
            by_type=by_type,
            by_risk=by_risk,
            by_namespace=by_namespace
        )
        
        # Get comparison data - uses Neo4j for analysis-specific counts when analysis_id is provided
        comparison_data = await _get_comparison_data(cluster_id, analysis_id)
        
        comparison = SnapshotComparison(
            before=comparison_data.get("before", {}),
            after=comparison_data.get("after", {}),
            summary={
                "total_changes": total,
                "added": comparison_data.get("added", 0),
                "removed": comparison_data.get("removed", 0),
                "modified": comparison_data.get("modified", 0)
            }
        )
        
        logger.info(
            "ClickHouse changes retrieved",
            cluster_id=cluster_id,
            total=total,
            returned=len(changes)
        )
        
        return ChangesResponse(
            changes=changes,
            total=total,
            stats=stats,
            comparison=comparison
        )
        
    except Exception as e:
        logger.error("ClickHouse query failed", error=str(e))
        raise


@router.get("/changes/{change_id}")
async def get_change_details(
    change_id: str,
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """Get detailed information about a specific change from ClickHouse"""
    
    try:
        from database.clickhouse import get_clickhouse_client
        
        client = get_clickhouse_client()
        
        # Query with all available columns for rich detail view
        query = """
        SELECT 
            event_id,
            cluster_id,
            cluster_name,
            analysis_id,
            detected_at,
            timestamp,
            change_type,
            target_name,
            target_namespace,
            target_type,
            details,
            risk_level,
            affected_services,
            blast_radius,
            changed_by,
            before_state,
            after_state,
            metadata,
            run_id,
            run_number
        FROM change_events
        WHERE event_id = %(change_id)s
        LIMIT 1
        """
        
        result = client.execute(query, {"change_id": change_id})
        
        if result:
            row = result[0]
            # Parse metadata JSON if present
            metadata = {}
            if row[17]:
                try:
                    import json
                    metadata = json.loads(row[17]) if isinstance(row[17], str) else row[17]
                except:
                    metadata = {}
            
            # Parse before/after states
            before_state = None
            after_state = None
            try:
                import json
                if row[15]:
                    before_state = json.loads(row[15]) if isinstance(row[15], str) else row[15]
                if row[16]:
                    after_state = json.loads(row[16]) if isinstance(row[16], str) else row[16]
            except:
                before_state = row[15]
                after_state = row[16]
            
            change_type = row[6]
            
            return {
                "id": str(row[0]),  # event_id (UUID)
                "cluster_id": row[1],
                "cluster_name": row[2] or "",
                "analysis_id": row[3],
                "detected_at": row[4].isoformat() if row[4] else None,
                "timestamp": row[5].isoformat() if row[5] else None,
                "change_type": change_type,
                "target": row[7] or "unknown",
                "namespace": row[8] or "unknown",
                "target_type": row[9] or "workload",
                "details": row[10] or "",
                "risk": row[11] or "medium",
                "affected_services": row[12] or 0,
                "blast_radius": row[13] or 0,
                "changed_by": row[14] or "auto-discovery",
                "before_state": before_state,
                "after_state": after_state,
                "metadata": metadata,
                "run_id": row[18],
                "run_number": row[19],
                "status": "detected",
                "rollback_available": change_type in [
                    ChangeType.CONFIG_CHANGED.value,
                    ChangeType.REPLICA_CHANGED.value,
                    ChangeType.IMAGE_CHANGED.value
                ],
                # Computed fields for UI
                "severity_indicator": _get_severity_indicator(row[11], row[12], row[13]),
                "change_category": _get_change_category(change_type),
                "recommended_actions": _get_recommended_actions(change_type, row[11]),
                "audit_trail": [
                    {
                        "action": "detected",
                        "timestamp": row[4].isoformat() if row[4] else None,
                        "actor": row[14] or "auto-discovery",
                        "details": f"Change detected during analysis run #{row[19] or 1}"
                    }
                ]
            }
        else:
            raise HTTPException(status_code=404, detail=f"Change not found: {change_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("ClickHouse lookup failed", error=str(e), change_id=change_id)
        raise HTTPException(status_code=500, detail=f"Failed to fetch change details: {str(e)}")
    
    # Fallback to mock implementation
    changes = generate_mock_changes(cluster_id=1)
    
    for change in changes:
        if change.id == change_id:
            return {
                **change.model_dump(),
                "related_changes": [],
                "rollback_available": change.change_type in [
                    ChangeType.CONFIG_CHANGED,
                    ChangeType.REPLICA_CHANGED
                ],
                "audit_trail": [
                    {
                        "action": "detected",
                        "timestamp": change.timestamp.isoformat(),
                        "actor": "auto-discovery"
                    }
                ]
            }
    
    raise HTTPException(status_code=404, detail="Change not found")


@router.get("/changes/stats/summary")
async def get_change_stats_summary(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """Get summary statistics of changes over time from ClickHouse"""
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    if cluster_id:
        try:
            from database.clickhouse import get_clickhouse_client
            
            client = get_clickhouse_client()
            
            # Build WHERE clause
            where_parts = ["detected_at >= %(start_time)s", "detected_at <= %(end_time)s"]
            params = {"start_time": start_time, "end_time": end_time}
            
            if cluster_id:
                where_parts.append("cluster_id = %(cluster_id)s")
                params["cluster_id"] = cluster_id
            if analysis_id:
                ch_aid = await _get_ch_analysis_id(analysis_id, cluster_id)
                where_parts.append("analysis_id = %(analysis_id)s")
                params["analysis_id"] = ch_aid
            
            where_clause = " AND ".join(where_parts)
            
            # Get total and by_type
            type_query = f"""
            SELECT change_type, count() as cnt
            FROM change_events
            WHERE {where_clause}
            GROUP BY change_type
            """
            type_results = client.execute(type_query, params)
            by_type = {str(r[0]): r[1] for r in type_results}
            total_changes = sum(by_type.values())
            
            # Get by_risk
            risk_query = f"""
            SELECT risk_level, count() as cnt
            FROM change_events
            WHERE {where_clause}
            GROUP BY risk_level
            """
            risk_results = client.execute(risk_query, params)
            by_risk = {str(r[0]): r[1] for r in risk_results}
            
            # Get by_namespace
            ns_query = f"""
            SELECT target_namespace, count() as cnt
            FROM change_events
            WHERE {where_clause}
            GROUP BY target_namespace
            """
            ns_results = client.execute(ns_query, params)
            by_namespace = {r[0] if r[0] else "unknown": r[1] for r in ns_results}
            
            # Get daily breakdown
            daily_query = f"""
            SELECT toDate(detected_at) as day, count() as cnt
            FROM change_events
            WHERE {where_clause}
            GROUP BY day
            ORDER BY day
            """
            daily_results = client.execute(daily_query, params)
            daily_counts = {str(r[0]): r[1] for r in daily_results}
            
            return {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": days,
                },
                "stats": {
                    "total_changes": total_changes,
                    "by_type": by_type,
                    "by_risk": by_risk,
                    "by_namespace": by_namespace
                },
                "daily_breakdown": daily_counts,
                "trends": {
                    "avg_changes_per_day": total_changes / days if days > 0 else 0,
                    "high_risk_ratio": (
                        (by_risk.get("critical", 0) + by_risk.get("high", 0)) / 
                        total_changes if total_changes > 0 else 0
                    ),
                },
                "data_source": "clickhouse"
            }
        except Exception as e:
            logger.warning("ClickHouse stats failed", error=str(e))
    
    # Fallback to mock data
    changes = generate_mock_changes(
        cluster_id=cluster_id,
        start_time=start_time,
        end_time=end_time,
    )
    
    stats = calculate_stats(changes)
    
    # Calculate daily breakdown
    daily_counts = {}
    for change in changes:
        day_key = change.timestamp.strftime("%Y-%m-%d")
        daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
    
    return {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id,
        "period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "days": days,
        },
        "stats": stats.model_dump(),
        "daily_breakdown": daily_counts,
        "trends": {
            "avg_changes_per_day": len(changes) / days if days > 0 else 0,
            "high_risk_ratio": (
                (stats.by_risk.get("critical", 0) + stats.by_risk.get("high", 0)) / 
                stats.total_changes if stats.total_changes > 0 else 0
            ),
        },
        "data_source": "mock"
    }


@router.get("/changes/compare")
async def compare_snapshots(
    cluster_id: int = Query(..., description="Cluster ID"),
    analysis_id_before: int = Query(..., description="Earlier analysis ID"),
    analysis_id_after: int = Query(..., description="Later analysis ID"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Compare two analysis snapshots to identify differences.
    
    Useful for:
    - Before/after deployment comparisons
    - Drift detection
    - Change validation
    
    NOTE: This function queries PostgreSQL for workloads/communications 
    (these tables remain in PostgreSQL - only change_events moved to ClickHouse)
    """
    
    if True:  # Always use real data (PostgreSQL for workloads/communications)
        try:
            from database.postgresql import database
            
            # Get workloads for both analyses
            workloads_query = """
            SELECT DISTINCT w.name, n.name as namespace
            FROM workloads w
            JOIN namespaces n ON w.namespace_id = n.id
            JOIN analysis_runs ar ON ar.analysis_id = :analysis_id
            WHERE w.cluster_id = :cluster_id
              AND w.is_active = true
            """
            
            # Get workloads for "before" analysis
            before_workloads = await database.fetch_all(workloads_query, {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id_before
            })
            
            # Get workloads for "after" analysis
            after_workloads = await database.fetch_all(workloads_query, {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id_after
            })
            
            before_names = set(w["name"] for w in before_workloads)
            after_names = set(w["name"] for w in after_workloads)
            
            workloads_added = list(after_names - before_names)
            workloads_removed = list(before_names - after_names)
            
            # Get connections count
            connections_query = """
            SELECT COUNT(*) as count
            FROM communications c
            WHERE c.cluster_id = :cluster_id AND c.is_active = true
            """
            
            before_connections = await database.fetch_one(connections_query, {
                "cluster_id": cluster_id
            })
            after_connections = await database.fetch_one(connections_query, {
                "cluster_id": cluster_id
            })
            
            # Get namespaces
            namespaces_query = """
            SELECT name FROM namespaces WHERE cluster_id = :cluster_id
            """
            namespaces = await database.fetch_all(namespaces_query, {"cluster_id": cluster_id})
            namespace_names = [n["name"] for n in namespaces]
            
            return {
                "cluster_id": cluster_id,
                "analysis_before": {
                    "id": analysis_id_before,
                    "workloads": len(before_workloads),
                    "connections": before_connections.get("count", 0) if before_connections else 0,
                    "namespaces": namespace_names,
                },
                "analysis_after": {
                    "id": analysis_id_after,
                    "workloads": len(after_workloads),
                    "connections": after_connections.get("count", 0) if after_connections else 0,
                    "namespaces": namespace_names,
                },
                "diff": {
                    "workloads_added": workloads_added,
                    "workloads_removed": workloads_removed,
                    "connections_added": [],
                    "connections_removed": [],
                    "namespaces_added": [],
                    "namespaces_removed": [],
                },
                "summary": {
                    "total_changes": len(workloads_added) + len(workloads_removed),
                    "workload_changes": len(workloads_added) + len(workloads_removed),
                    "connection_changes": 0,
                    "namespace_changes": 0,
                },
                "data_source": "real"
            }
        except Exception as e:
            logger.warning("Real data comparison failed, falling back to mock", error=str(e))
    
    # Mock comparison result (fallback)
    return {
        "cluster_id": cluster_id,
        "analysis_before": {
            "id": analysis_id_before,
            "workloads": 45,
            "connections": 128,
            "namespaces": ["default", "production", "staging"],
        },
        "analysis_after": {
            "id": analysis_id_after,
            "workloads": 47,
            "connections": 132,
            "namespaces": ["default", "production", "staging", "monitoring"],
        },
        "diff": {
            "workloads_added": ["payment-service", "notification-service"],
            "workloads_removed": [],
            "connections_added": [
                {"source": "api-gateway", "target": "payment-service", "port": 8080},
                {"source": "notification-service", "target": "kafka-broker", "port": 9092},
            ],
            "connections_removed": [],
            "namespaces_added": ["monitoring"],
            "namespaces_removed": [],
        },
        "summary": {
            "total_changes": 6,
            "workload_changes": 2,
            "connection_changes": 4,
            "namespace_changes": 1,
        },
        "data_source": "mock"
    }


# ============ Worker Management Endpoints ============

@router.get("/changes/worker/status")
async def get_worker_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get the status of the change detection background worker.
    
    Returns:
    - running: Whether the worker is currently running
    - enabled: Whether the worker is enabled
    - config: Worker configuration (intervals, circuit breaker settings)
    - last_detections: Last detection times per analysis
    - circuits_open: Currently open circuit breakers
    """
    try:
        from workers.change_detection_worker import change_detection_worker
        return change_detection_worker.get_status()
    except ImportError:
        return {
            "error": "Change detection worker module not available",
            "running": False,
            "enabled": False
        }


@router.get("/changes/diagnose/{analysis_id}")
async def diagnose_change_detection(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Diagnose change detection issues for a specific analysis.
    
    Checks:
    - Analysis configuration (change detection enabled, strategy)
    - Stored workloads in PostgreSQL for the analysis cluster
    - Worker status and last detection times
    - ClickHouse change_events count
    - K8s connection status
    
    Returns diagnostic information to help troubleshoot why changes aren't being detected.
    """
    from database.postgresql import database
    from database.clickhouse import get_clickhouse_client
    
    diagnostics = {
        "analysis_id": analysis_id,
        "checks": {},
        "issues": [],
        "recommendations": []
    }
    
    try:
        # Check 1: Get analysis info
        analysis_query = """
            SELECT a.id, a.name, a.status, a.cluster_id, a.namespaces,
                   a.change_detection_enabled, a.change_detection_strategy, a.change_detection_types,
                   a.started_at, a.stopped_at
            FROM analyses a
            WHERE a.id = :analysis_id
        """
        analysis = await database.fetch_one(analysis_query, {"analysis_id": analysis_id})
        
        if not analysis:
            diagnostics["issues"].append("Analysis not found")
            return diagnostics
        
        diagnostics["checks"]["analysis"] = {
            "name": analysis["name"],
            "status": analysis["status"],
            "cluster_id": analysis["cluster_id"],
            "namespaces": analysis["namespaces"],
            "change_detection_enabled": analysis["change_detection_enabled"],
            "change_detection_strategy": analysis["change_detection_strategy"],
            "started_at": str(analysis["started_at"]) if analysis["started_at"] else None,
            "stopped_at": str(analysis["stopped_at"]) if analysis["stopped_at"] else None
        }
        
        if not analysis["change_detection_enabled"]:
            diagnostics["issues"].append("Change detection is DISABLED for this analysis")
            diagnostics["recommendations"].append("Enable change detection when creating the analysis")
        
        # Check 2: Count stored workloads for the cluster
        cluster_id = analysis["cluster_id"]
        workloads_query = """
            SELECT workload_type, COUNT(*) as count, 
                   COUNT(*) FILTER (WHERE is_active = true) as active_count
            FROM workloads
            WHERE cluster_id = :cluster_id
            GROUP BY workload_type
        """
        workloads = await database.fetch_all(workloads_query, {"cluster_id": cluster_id})
        
        workload_summary = {}
        total_workloads = 0
        total_active = 0
        for w in workloads:
            workload_summary[w["workload_type"]] = {
                "total": w["count"],
                "active": w["active_count"]
            }
            total_workloads += w["count"]
            total_active += w["active_count"]
        
        diagnostics["checks"]["workloads"] = {
            "cluster_id": cluster_id,
            "by_type": workload_summary,
            "total": total_workloads,
            "active": total_active
        }
        
        if total_workloads == 0:
            diagnostics["issues"].append("No workloads stored in PostgreSQL for this cluster")
            diagnostics["recommendations"].append("Run workload discovery first - workloads must be stored before changes can be detected")
        elif total_active == 0:
            diagnostics["issues"].append("All workloads are marked as inactive - no changes will be detected")
        
        # Check 3: Check if specific namespace workloads exist (if analysis has namespace scope)
        if analysis["namespaces"]:
            import json
            namespaces = json.loads(analysis["namespaces"]) if isinstance(analysis["namespaces"], str) else analysis["namespaces"]
            if namespaces:
                ns_workloads_query = """
                    SELECT n.name as namespace, COUNT(w.id) as workload_count
                    FROM namespaces n
                    LEFT JOIN workloads w ON w.namespace_id = n.id AND w.is_active = true
                    WHERE n.cluster_id = :cluster_id AND n.name = ANY(:namespaces)
                    GROUP BY n.name
                """
                ns_workloads = await database.fetch_all(ns_workloads_query, {
                    "cluster_id": cluster_id,
                    "namespaces": namespaces
                })
                
                diagnostics["checks"]["namespace_scope"] = {
                    "analysis_namespaces": namespaces,
                    "workloads_per_namespace": {row["namespace"]: row["workload_count"] for row in ns_workloads}
                }
                
                for ns in namespaces:
                    ns_count = next((row["workload_count"] for row in ns_workloads if row["namespace"] == ns), 0)
                    if ns_count == 0:
                        diagnostics["issues"].append(f"Namespace '{ns}' has no active workloads stored")
        
        # Check 4: ClickHouse change_events count
        try:
            ch_client = get_clickhouse_client()
            ch_aid = await _get_ch_analysis_id(analysis_id, cluster_id)
            ch_query = f"""
                SELECT count() as total,
                       countIf(change_type = 'replica_changed') as replica_changes,
                       min(timestamp) as first_change,
                       max(timestamp) as last_change
                FROM change_events
                WHERE analysis_id = '{ch_aid}'
            """
            ch_result = ch_client.execute(ch_query)
            if ch_result:
                row = ch_result[0]
                diagnostics["checks"]["clickhouse"] = {
                    "total_changes": row[0],
                    "replica_changes": row[1],
                    "first_change": str(row[2]) if row[2] else None,
                    "last_change": str(row[3]) if row[3] else None
                }
                
                if row[0] == 0:
                    diagnostics["issues"].append("No change events recorded in ClickHouse for this analysis")
                    diagnostics["recommendations"].append("Check if Change Detection Worker is running and RabbitMQ is operational")
        except Exception as e:
            diagnostics["checks"]["clickhouse"] = {"error": str(e)}
            diagnostics["issues"].append(f"ClickHouse query failed: {str(e)}")
        
        # Check 5: Worker status
        try:
            from workers.change_detection_worker import change_detection_worker
            worker_status = change_detection_worker.get_status()
            diagnostics["checks"]["worker"] = worker_status
            
            if not worker_status.get("enabled"):
                diagnostics["issues"].append("Change Detection Worker is DISABLED")
                diagnostics["recommendations"].append("Set CHANGE_DETECTION_ENABLED=true environment variable")
            
            if not worker_status.get("running"):
                diagnostics["issues"].append("Change Detection Worker is not running")
                diagnostics["recommendations"].append("Deploy the change-detection-worker or enable embedded mode")
        except Exception as e:
            diagnostics["checks"]["worker"] = {"error": str(e), "available": False}
        
        # Summary
        diagnostics["summary"] = {
            "total_issues": len(diagnostics["issues"]),
            "healthy": len(diagnostics["issues"]) == 0
        }
        
    except Exception as e:
        diagnostics["error"] = str(e)
    
    return diagnostics


@router.post("/changes/worker/trigger/{analysis_id}")
async def trigger_change_detection(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger change detection for a specific analysis.
    
    Useful for:
    - On-demand change detection outside regular schedule
    - Testing the change detection pipeline
    - Immediate detection after a known deployment
    
    Returns:
    - analysis_id: The analysis that was checked
    - cluster_id: The cluster for the analysis
    - changes_detected: Number of changes found
    - changes: Preview of detected changes (first 10)
    """
    try:
        from workers.change_detection_worker import change_detection_worker
        result = await change_detection_worker.trigger_detection(analysis_id)
        return result
    except ImportError:
        return {
            "error": "Change detection worker module not available"
        }
    except Exception as e:
        logger.error("Manual change detection failed", analysis_id=analysis_id, error=str(e))
        return {
            "error": str(e),
            "analysis_id": analysis_id
        }


@router.post("/changes/worker/enable")
async def enable_worker(
    current_user: dict = Depends(get_current_user)
):
    """
    Enable and start the change detection background worker.
    
    Note: This requires appropriate permissions (admin or operator role).
    """
    try:
        from workers.change_detection_worker import change_detection_worker
        result = await change_detection_worker.enable()
        logger.info("Change detection worker enabled", user=current_user.get("username"))
        return result
    except ImportError:
        return {
            "error": "Change detection worker module not available"
        }


@router.post("/changes/worker/disable")
async def disable_worker(
    current_user: dict = Depends(get_current_user)
):
    """
    Disable and stop the change detection background worker.
    
    Note: This requires appropriate permissions (admin or operator role).
    """
    try:
        from workers.change_detection_worker import change_detection_worker
        result = await change_detection_worker.disable()
        logger.info("Change detection worker disabled", user=current_user.get("username"))
        return result
    except ImportError:
        return {
            "error": "Change detection worker module not available"
        }


# ============ Run-Based Filtering Endpoints (Phase 6) ============

@router.get("/changes/runs/{analysis_id}")
async def get_analysis_runs(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all runs for an analysis.
    
    Returns list of run information including:
    - run_id: Unique run identifier
    - run_number: Sequential run number (1, 2, 3...)
    - started_at: When the run started
    - completed_at: When the run completed (null if still running)
    - status: running, completed, stopped, failed
    - changes_detected: Number of changes detected in this run
    
    Requires RUN_BASED_FILTERING_ENABLED=true for full functionality.
    """
    from database.postgresql import database
    
    query = """
    SELECT 
        id as run_id,
        run_number,
        status,
        start_time,
        end_time,
        duration_seconds,
        events_collected,
        workloads_discovered,
        communications_discovered,
        anomalies_detected,
        changes_detected,
        error_message,
        metadata
    FROM analysis_runs
    WHERE analysis_id = :analysis_id
    ORDER BY run_number DESC
    """
    
    try:
        runs = await database.fetch_all(query, {"analysis_id": analysis_id})
        
        return {
            "analysis_id": analysis_id,
            "total_runs": len(runs),
            "run_based_filtering_enabled": RUN_BASED_FILTERING,
            "runs": [dict(r) for r in runs]
        }
    except Exception as e:
        logger.error("Failed to fetch analysis runs", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/runs/{analysis_id}/stats")
async def get_run_stats(
    analysis_id: int,
    run_id: Optional[int] = Query(None, description="Specific run ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get change statistics per run from ClickHouse.
    
    Queries the base change_events table directly so all change types
    (including newly added ones) are automatically included.
    """
    try:
        from database.clickhouse import get_clickhouse_client
        
        client = get_clickhouse_client()
        
        ch_aid = await _get_ch_analysis_id(analysis_id)
        where_clause = f"analysis_id = '{ch_aid}'"
        if run_id:
            where_clause += f" AND run_id = {run_id}"
        
        query = f"""
        SELECT 
            run_id,
            max(run_number) AS run_number,
            count() AS total_changes,
            countIf(risk_level = 'critical') AS critical_count,
            countIf(risk_level = 'high') AS high_count,
            countIf(risk_level = 'medium') AS medium_count,
            countIf(risk_level = 'low') AS low_count,
            min(timestamp) AS first_change_at,
            max(timestamp) AS last_change_at
        FROM change_events
        WHERE {where_clause}
        GROUP BY run_id
        ORDER BY run_id DESC
        """
        
        rows = client.execute(query)
        
        # Fetch per-type breakdown for each run
        type_query = f"""
        SELECT 
            run_id,
            change_type,
            count() AS cnt
        FROM change_events
        WHERE {where_clause}
        GROUP BY run_id, change_type
        """
        type_rows = client.execute(type_query)
        
        # Build run_id -> {type: count} mapping
        type_map: Dict[int, Dict[str, int]] = {}
        for tr in type_rows:
            rid = tr[0]
            if rid not in type_map:
                type_map[rid] = {}
            type_map[rid][tr[1]] = tr[2]
        
        return {
            "analysis_id": analysis_id,
            "source": "clickhouse",
            "stats": [
                {
                    "run_id": r[0],
                    "run_number": r[1],
                    "total_changes": r[2],
                    "by_risk": {
                        "critical": r[3],
                        "high": r[4],
                        "medium": r[5],
                        "low": r[6]
                    },
                    "by_type": type_map.get(r[0], {}),
                    "first_change_at": r[7].isoformat() if r[7] else None,
                    "last_change_at": r[8].isoformat() if r[8] else None
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Failed to fetch run stats from ClickHouse", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class RunComparisonResult(BaseModel):
    """Result of comparing two runs"""
    analysis_id: int
    run_a: Dict[str, Any]
    run_b: Dict[str, Any]
    comparison: Dict[str, Any]
    changes_only_in_a: List[Dict[str, Any]]
    changes_only_in_b: List[Dict[str, Any]]
    common_changes: List[Dict[str, Any]]


@router.get("/changes/runs/{analysis_id}/compare", response_model=RunComparisonResult)
async def compare_runs(
    analysis_id: int,
    run_a: int = Query(..., description="First run number to compare"),
    run_b: int = Query(..., description="Second run number to compare"),
    current_user: dict = Depends(get_current_user)
):
    """
    Compare changes between two runs of the same analysis.
    
    Returns:
    - run_a, run_b: Metadata about each run
    - comparison: Summary statistics (added, removed, common)
    - changes_only_in_a: Changes that only occurred in run A
    - changes_only_in_b: Changes that only occurred in run B (new in this run)
    - common_changes: Changes that occurred in both runs
    
    Use case: Compare what changed between deployments, config changes, etc.
    """
    # Validate run numbers are different
    if run_a == run_b:
        raise HTTPException(
            status_code=400,
            detail="run_a and run_b must be different run numbers"
        )
    
    # Validate run numbers are positive
    if run_a < 1 or run_b < 1:
        raise HTTPException(
            status_code=400,
            detail="Run numbers must be positive integers"
        )
    
    try:
        from database.clickhouse import get_clickhouse_client
        from database.postgresql import database
        
        client = get_clickhouse_client()
        
        # Get run metadata from PostgreSQL
        # Using explicit OR instead of IN for better compatibility with parameter binding
        run_query = """
            SELECT id, run_number, status, start_time, end_time, 
                   events_collected, communications_discovered
            FROM analysis_runs 
            WHERE analysis_id = :analysis_id 
              AND (run_number = :run_a OR run_number = :run_b)
            ORDER BY run_number
        """
        runs = await database.fetch_all(run_query, {
            "analysis_id": analysis_id,
            "run_a": run_a,
            "run_b": run_b
        })
        
        run_a_meta = None
        run_b_meta = None
        for r in runs:
            if r["run_number"] == run_a:
                run_a_meta = dict(r)
            elif r["run_number"] == run_b:
                run_b_meta = dict(r)
        
        if not run_a_meta or not run_b_meta:
            raise HTTPException(
                status_code=404, 
                detail=f"One or both runs not found. Run A: {run_a}, Run B: {run_b}"
            )
        
        ch_aid = await _get_ch_analysis_id(analysis_id)

        # Get changes from run A
        changes_a_query = f"""
            SELECT 
                change_type, target_name, target_namespace, risk_level,
                details, before_state, after_state, detected_at
            FROM change_events
            WHERE analysis_id = '{ch_aid}' AND run_number = {run_a}
            ORDER BY detected_at
        """
        changes_a_raw = client.execute(changes_a_query)
        
        # Get changes from run B
        changes_b_query = f"""
            SELECT 
                change_type, target_name, target_namespace, risk_level,
                details, before_state, after_state, detected_at
            FROM change_events
            WHERE analysis_id = '{ch_aid}' AND run_number = {run_b}
            ORDER BY detected_at
        """
        changes_b_raw = client.execute(changes_b_query)
        
        # Convert to dicts and create fingerprints for comparison
        def parse_json_field(value):
            """Parse JSON string to dict, return empty dict on failure"""
            if not value:
                return {}
            if isinstance(value, dict):
                return value
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        
        def change_to_dict(row):
            return {
                "change_type": row[0] or 'unknown',
                "target_name": row[1] or '',
                "target_namespace": row[2] or '',
                "risk_level": row[3] or 'medium',
                "details": row[4] or '',
                "before_state": parse_json_field(row[5]),
                "after_state": parse_json_field(row[6]),
                "detected_at": row[7].isoformat() if row[7] else None
            }
        
        def fingerprint(change):
            """Create a fingerprint for comparing changes (type + target)"""
            # Defensive: ensure no None values in fingerprint
            ct = change.get('change_type') or 'unknown'
            ns = change.get('target_namespace') or ''
            name = change.get('target_name') or ''
            return f"{ct}:{ns}/{name}"
        
        changes_a = [change_to_dict(r) for r in changes_a_raw]
        changes_b = [change_to_dict(r) for r in changes_b_raw]
        
        # Create fingerprint sets
        fps_a = {fingerprint(c): c for c in changes_a}
        fps_b = {fingerprint(c): c for c in changes_b}
        
        fps_a_set = set(fps_a.keys())
        fps_b_set = set(fps_b.keys())
        
        # Calculate differences
        only_in_a = fps_a_set - fps_b_set
        only_in_b = fps_b_set - fps_a_set
        in_both = fps_a_set & fps_b_set
        
        changes_only_in_a = [fps_a[fp] for fp in only_in_a]
        changes_only_in_b = [fps_b[fp] for fp in only_in_b]
        common_changes = [fps_b[fp] for fp in in_both]  # Use run B version
        
        # Calculate stats by type
        def count_by_type(changes):
            counts = {}
            for c in changes:
                t = c["change_type"]
                counts[t] = counts.get(t, 0) + 1
            return counts
        
        def count_by_risk(changes):
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for c in changes:
                r = c["risk_level"]
                if r in counts:
                    counts[r] += 1
            return counts
        
        # Format run metadata for response
        def format_run_meta(meta):
            # Use raw change count for consistency with comparison.total_in_run_X
            total = len(changes_a) if meta["run_number"] == run_a else len(changes_b)
            return {
                "run_id": meta["id"],
                "run_number": meta["run_number"],
                "status": meta["status"],
                "start_time": meta["start_time"].isoformat() if meta["start_time"] else None,
                "end_time": meta["end_time"].isoformat() if meta["end_time"] else None,
                "total_changes": total,
                "events_collected": meta["events_collected"],
                "communications_discovered": meta["communications_discovered"]
            }
        
        return RunComparisonResult(
            analysis_id=analysis_id,
            run_a=format_run_meta(run_a_meta),
            run_b=format_run_meta(run_b_meta),
            comparison={
                "total_in_run_a": len(changes_a),
                "total_in_run_b": len(changes_b),
                "only_in_run_a": len(changes_only_in_a),
                "only_in_run_b": len(changes_only_in_b),
                "common": len(common_changes),
                "by_type": {
                    "only_in_a": count_by_type(changes_only_in_a),
                    "only_in_b": count_by_type(changes_only_in_b),
                    "common": count_by_type(common_changes)
                },
                "by_risk": {
                    "only_in_a": count_by_risk(changes_only_in_a),
                    "only_in_b": count_by_risk(changes_only_in_b),
                    "common": count_by_risk(common_changes)
                },
                "summary": {
                    "new_in_b": f"{len(changes_only_in_b)} new changes in Run {run_b}",
                    "removed_from_a": f"{len(changes_only_in_a)} changes from Run {run_a} not in Run {run_b}",
                    "persistent": f"{len(common_changes)} changes in both runs"
                }
            },
            changes_only_in_a=changes_only_in_a,
            changes_only_in_b=changes_only_in_b,
            common_changes=common_changes
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compare runs", analysis_id=analysis_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/config")
async def get_change_detection_config(
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current change detection configuration.
    
    Returns:
    - storage: ClickHouse (PostgreSQL change_events table removed)
    - run_based_filtering: Whether run-based filtering is enabled
    - worker_enabled: Whether the background worker is enabled
    - detection_interval: How often detection runs
    - lookback_minutes: How far back detection looks
    """
    return {
        "storage": "clickhouse",
        "run_based_filtering": RUN_BASED_FILTERING,
        "architecture": "ClickHouse-only (PostgreSQL change_events removed)",
        "feature_flags": {
            "RUN_BASED_FILTERING_ENABLED": RUN_BASED_FILTERING
        },
        "worker_enabled_env": "CHANGE_DETECTION_ENABLED",
        "detection_interval_env": "CHANGE_DETECTION_INTERVAL",
        "lookback_minutes_env": "CHANGE_DETECTION_LOOKBACK_MINUTES",
        "documentation": {
            "storage_note": "Change events stored ONLY in ClickHouse. PostgreSQL table removed.",
            "enable_run_filtering": "Set RUN_BASED_FILTERING_ENABLED=true to enable run-based filtering UI",
            "enable_worker": "Set CHANGE_DETECTION_ENABLED=true to start the background detection worker",
            "adjust_interval": "Set CHANGE_DETECTION_INTERVAL=60 (seconds) to control detection frequency",
            "adjust_lookback": "Set CHANGE_DETECTION_LOOKBACK_MINUTES=5 to control detection window"
        }
    }


# ============ Sprint 5: Impact Analysis Endpoints ============

@router.get("/changes/impact/analyze")
async def analyze_change_impact(
    cluster_id: int = Query(..., description="Cluster ID"),
    change_id: Optional[str] = Query(None, description="Change event ID (UUID from ClickHouse)"),
    workload: Optional[str] = Query(None, description="Target workload name"),
    namespace: Optional[str] = Query(None, description="Target namespace"),
    change_type: Optional[str] = Query(None, description="Type of change"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Analyze the impact of a change on the infrastructure.
    
    This endpoint provides:
    - Blast radius calculation (direct, indirect, cascade)
    - Affected services list with impact categorization
    - Graph structure for visualization
    - Risk score and recommendations
    
    You can either:
    - Provide a change_id to analyze an existing change
    - Provide workload + namespace to analyze a hypothetical change
    """
    logger.info(
        "Impact analysis requested",
        cluster_id=cluster_id,
        change_id=change_id,
        workload=workload,
        namespace=namespace
    )
    
    try:
        result = await change_service.analyze_change_impact(
            cluster_id=cluster_id,
            change_id=change_id,
            workload_name=workload,
            namespace=namespace,
            change_type=change_type
        )
        
        return result
        
    except Exception as e:
        logger.error("Impact analysis failed", error=str(e))
        return {
            "error": str(e),
            "blast_radius": {"total": 0, "direct": 0, "indirect": 0, "cascade": 0},
            "affected_services": [],
            "impact_graph": {"nodes": [], "edges": []},
            "risk_score": 0
        }


@router.get("/changes/{change_id}/impact")
async def get_change_impact(
    change_id: str,
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Get impact analysis for a specific change event from ClickHouse.
    
    Shorthand endpoint that automatically fetches the change details
    and runs impact analysis.
    """
    try:
        from database.clickhouse import get_clickhouse_client
        
        client = get_clickhouse_client()
        
        query = """
        SELECT 
            event_id,
            cluster_id,
            change_type,
            target_name,
            target_namespace,
            risk_level,
            affected_services
        FROM change_events
        WHERE event_id = %(change_id)s
        LIMIT 1
        """
        
        result = client.execute(query, {"change_id": change_id})
        
        if not result:
            raise HTTPException(status_code=404, detail="Change not found")
        
        row = result[0]
        analysis_result = await change_service.analyze_change_impact(
            cluster_id=row[1],
            change_id=change_id,
            workload_name=row[3],
            namespace=row[4] or "unknown",
            change_type=row[2]
        )
        
        return analysis_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Impact analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/{change_id}/correlated")
async def get_correlated_changes(
    change_id: str,
    cluster_id: int = Query(..., description="Cluster ID"),
    time_window: int = Query(30, ge=5, le=120, description="Time window in minutes"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Find changes that are correlated with a given change from ClickHouse.
    
    Correlation is based on:
    - Time proximity (within the specified window)
    - Same source/actor (changed_by)
    - Same namespace
    - Related workload names
    
    This helps identify:
    - Deployment-related changes (multiple services deployed together)
    - Cascade effects (one change triggering others)
    - Configuration drift patterns
    """
    try:
        correlated = await change_service.get_correlated_changes(
            cluster_id=cluster_id,
            change_id=change_id,
            time_window_minutes=time_window
        )
        
        return {
            "reference_change_id": change_id,
            "time_window_minutes": time_window,
            "correlated_changes": correlated,
            "total_correlated": len(correlated),
            "correlation_types": {
                "same_source": sum(1 for c in correlated if c.get("correlation_type") == "same_source"),
                "same_namespace": sum(1 for c in correlated if c.get("correlation_type") == "same_namespace"),
                "time_proximity": sum(1 for c in correlated if c.get("correlation_type") == "time_proximity")
            }
        }
        
    except Exception as e:
        logger.error("Correlation analysis failed", error=str(e))
        return {
            "reference_change_id": change_id,
            "correlated_changes": [],
            "total_correlated": 0,
            "error": str(e)
        }


# ============ Sprint 6: Enterprise Features ============

# ------------ 6.1: Baseline & Drift Detection ------------

@router.post("/changes/baseline/{analysis_id}")
async def mark_as_baseline(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Mark an analysis as the baseline for drift detection.
    
    Only one analysis per cluster can be the baseline at a time.
    Marking a new baseline will unmark the previous one.
    """
    from database.postgresql import database
    
    try:
        # Get the analysis to find cluster_id
        analysis_query = "SELECT cluster_id FROM analyses WHERE id = :analysis_id"
        analysis = await database.fetch_one(analysis_query, {"analysis_id": analysis_id})
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        cluster_id = analysis["cluster_id"]
        username = current_user.get("username", "unknown")
        
        # Unmark any existing baseline for this cluster
        unmark_query = """
        UPDATE analyses 
        SET is_baseline = false, baseline_marked_at = NULL, baseline_marked_by = NULL
        WHERE cluster_id = :cluster_id AND is_baseline = true
        """
        await database.execute(unmark_query, {"cluster_id": cluster_id})
        
        # Mark the new baseline
        mark_query = """
        UPDATE analyses 
        SET is_baseline = true, baseline_marked_at = NOW(), baseline_marked_by = :marked_by
        WHERE id = :analysis_id
        """
        await database.execute(mark_query, {
            "analysis_id": analysis_id,
            "marked_by": username
        })
        
        logger.info("Analysis marked as baseline", analysis_id=analysis_id, by=username)
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "cluster_id": cluster_id,
            "marked_by": username,
            "message": f"Analysis #{analysis_id} is now the baseline for cluster #{cluster_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to mark baseline", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/changes/baseline/{cluster_id}")
async def unmark_baseline(
    cluster_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Remove the baseline marking for a cluster.
    """
    from database.postgresql import database
    
    try:
        query = """
        UPDATE analyses 
        SET is_baseline = false, baseline_marked_at = NULL, baseline_marked_by = NULL
        WHERE cluster_id = :cluster_id AND is_baseline = true
        RETURNING id
        """
        result = await database.fetch_one(query, {"cluster_id": cluster_id})
        
        if not result:
            return {"success": True, "message": "No baseline was set for this cluster"}
        
        return {
            "success": True,
            "previous_baseline_id": result["id"],
            "message": f"Baseline removed from cluster #{cluster_id}"
        }
        
    except Exception as e:
        logger.error("Failed to unmark baseline", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/baseline/{cluster_id}")
async def get_baseline(
    cluster_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current baseline analysis for a cluster.
    """
    from database.postgresql import database
    
    try:
        query = """
        SELECT id, name, status, baseline_marked_at, baseline_marked_by,
               (SELECT COUNT(*) FROM workloads WHERE cluster_id = :cluster_id AND is_active = true) as workload_count,
               (SELECT COUNT(*) FROM communications WHERE cluster_id = :cluster_id AND is_active = true) as connection_count
        FROM analyses
        WHERE cluster_id = :cluster_id AND is_baseline = true
        """
        result = await database.fetch_one(query, {"cluster_id": cluster_id})
        
        if not result:
            return {
                "has_baseline": False,
                "cluster_id": cluster_id,
                "message": "No baseline set for this cluster"
            }
        
        return {
            "has_baseline": True,
            "cluster_id": cluster_id,
            "baseline": {
                "analysis_id": result["id"],
                "name": result["name"],
                "status": result["status"],
                "marked_at": result["baseline_marked_at"].isoformat() if result["baseline_marked_at"] else None,
                "marked_by": result["baseline_marked_by"],
                "workload_count": result["workload_count"],
                "connection_count": result["connection_count"]
            }
        }
        
    except Exception as e:
        logger.error("Failed to get baseline", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/drift/{cluster_id}")
async def detect_drift(
    cluster_id: int,
    analysis_id: Optional[int] = Query(None, description="Analysis to compare (defaults to latest)"),
    current_user: dict = Depends(get_current_user),
    change_service: ChangeDetectionService = Depends(get_change_detection_service)
):
    """
    Detect drift between current state and baseline.
    
    Returns:
    - has_drift: Whether drift was detected
    - drift_summary: Summary of what changed
    - workloads_added/removed: Lists of workload changes
    - connections_added/removed: Lists of connection changes
    - drift_severity: low, medium, high based on change count
    """
    from database.postgresql import database
    
    try:
        # Get baseline
        baseline_query = """
        SELECT id, name, baseline_marked_at
        FROM analyses
        WHERE cluster_id = :cluster_id AND is_baseline = true
        """
        baseline = await database.fetch_one(baseline_query, {"cluster_id": cluster_id})
        
        if not baseline:
            return {
                "has_baseline": False,
                "error": "No baseline set for this cluster. Mark an analysis as baseline first."
            }
        
        # Get current analysis (latest or specified)
        if analysis_id:
            current_query = "SELECT id, name FROM analyses WHERE id = :analysis_id"
            current = await database.fetch_one(current_query, {"analysis_id": analysis_id})
        else:
            current_query = """
            SELECT id, name FROM analyses 
            WHERE cluster_id = :cluster_id AND status IN ('running', 'completed', 'stopped')
            ORDER BY created_at DESC LIMIT 1
            """
            current = await database.fetch_one(current_query, {"cluster_id": cluster_id})
        
        if not current:
            return {
                "has_baseline": True,
                "error": "No current analysis found for comparison"
            }
        
        # If comparing baseline to itself
        if baseline["id"] == current["id"]:
            return {
                "has_baseline": True,
                "has_drift": False,
                "baseline_analysis_id": baseline["id"],
                "current_analysis_id": current["id"],
                "message": "Current analysis is the baseline - no drift possible"
            }
        
        # Get workloads for baseline
        workloads_query = """
        SELECT DISTINCT w.name, n.name as namespace
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id AND w.is_active = true
        """
        
        # For drift detection, we compare current active workloads
        # In a more sophisticated implementation, we'd snapshot at baseline time
        baseline_workloads = await database.fetch_all(workloads_query, {"cluster_id": cluster_id})
        current_workloads = await database.fetch_all(workloads_query, {"cluster_id": cluster_id})
        
        baseline_names = set(f"{w['namespace']}/{w['name']}" for w in baseline_workloads)
        current_names = set(f"{w['namespace']}/{w['name']}" for w in current_workloads)
        
        workloads_added = list(current_names - baseline_names)
        workloads_removed = list(baseline_names - current_names)
        
        # Get connections
        connections_query = """
        SELECT COUNT(*) as count FROM communications 
        WHERE cluster_id = :cluster_id AND is_active = true
        """
        baseline_connections = await database.fetch_one(connections_query, {"cluster_id": cluster_id})
        current_connections = await database.fetch_one(connections_query, {"cluster_id": cluster_id})
        
        connection_delta = (current_connections["count"] if current_connections else 0) - \
                          (baseline_connections["count"] if baseline_connections else 0)
        
        # Calculate drift severity
        total_changes = len(workloads_added) + len(workloads_removed) + abs(connection_delta)
        if total_changes == 0:
            drift_severity = "none"
        elif total_changes <= 5:
            drift_severity = "low"
        elif total_changes <= 15:
            drift_severity = "medium"
        else:
            drift_severity = "high"
        
        has_drift = total_changes > 0
        
        return {
            "has_baseline": True,
            "has_drift": has_drift,
            "baseline_analysis_id": baseline["id"],
            "baseline_name": baseline["name"],
            "baseline_marked_at": baseline["baseline_marked_at"].isoformat() if baseline["baseline_marked_at"] else None,
            "current_analysis_id": current["id"],
            "current_name": current["name"],
            "drift_summary": {
                "total_changes": total_changes,
                "workloads_added": len(workloads_added),
                "workloads_removed": len(workloads_removed),
                "connection_delta": connection_delta
            },
            "drift_severity": drift_severity,
            "drift_details": {
                "workloads_added": workloads_added[:20],  # Limit to 20
                "workloads_removed": workloads_removed[:20],
            }
        }
        
    except Exception as e:
        logger.error("Drift detection failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ------------ 6.2: Change Review Workflow ------------

@router.post("/changes/{change_id}/acknowledge")
async def acknowledge_change(
    change_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Acknowledge a change (quick action to mark as seen).
    """
    from database.postgresql import database
    
    try:
        username = current_user.get("username", "unknown")
        
        query = """
        UPDATE change_events 
        SET status = 'acknowledged', acknowledged_at = NOW(), acknowledged_by = :username
        WHERE id = :change_id AND status = 'new'
        RETURNING id
        """
        result = await database.fetch_one(query, {
            "change_id": change_id,
            "username": username
        })
        
        if not result:
            # Check if already acknowledged
            check_query = "SELECT status FROM change_events WHERE id = :change_id"
            existing = await database.fetch_one(check_query, {"change_id": change_id})
            if existing:
                return {"success": True, "message": f"Change already in status: {existing['status']}"}
            raise HTTPException(status_code=404, detail="Change not found")
        
        return {
            "success": True,
            "change_id": change_id,
            "status": "acknowledged",
            "acknowledged_by": username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to acknowledge change", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/changes/{change_id}/review")
async def review_change(
    change_id: int,
    action: str = Query(..., description="Review action: approve, reject, resolve"),
    comment: Optional[str] = Query(None, description="Review comment"),
    current_user: dict = Depends(get_current_user)
):
    """
    Review a change (approve, reject, or resolve).
    """
    from database.postgresql import database
    
    if action not in ['approve', 'reject', 'resolve', 'reviewing']:
        raise HTTPException(status_code=400, detail="Invalid action. Use: approve, reject, resolve, reviewing")
    
    try:
        username = current_user.get("username", "unknown")
        
        # Map action to status
        status_map = {
            'approve': 'approved',
            'reject': 'rejected',
            'resolve': 'resolved',
            'reviewing': 'reviewing'
        }
        new_status = status_map[action]
        
        query = """
        UPDATE change_events 
        SET status = :status, 
            reviewed_at = NOW(), 
            reviewed_by = :username,
            review_comment = COALESCE(:comment, review_comment)
        WHERE id = :change_id
        RETURNING id, status
        """
        result = await database.fetch_one(query, {
            "change_id": change_id,
            "status": new_status,
            "username": username,
            "comment": comment
        })
        
        if not result:
            raise HTTPException(status_code=404, detail="Change not found")
        
        logger.info("Change reviewed", change_id=change_id, action=action, by=username)
        
        return {
            "success": True,
            "change_id": change_id,
            "status": new_status,
            "reviewed_by": username,
            "comment": comment
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to review change", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/workflow/pending")
async def get_pending_reviews(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user)
):
    """
    Get changes pending review.
    """
    from database.postgresql import database
    
    try:
        conditions = ["1=1"]
        params = {"limit": limit}
        
        if cluster_id:
            conditions.append("ce.cluster_id = :cluster_id")
            params["cluster_id"] = cluster_id
        
        if status:
            conditions.append("ce.status = :status")
            params["status"] = status
        else:
            conditions.append("ce.status IN ('new', 'acknowledged', 'reviewing')")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        SELECT 
            ce.id,
            ce.detected_at as timestamp,
            ce.change_type,
            ce.target,
            n.name as namespace,
            ce.risk_level as risk,
            ce.affected_services,
            ce.status,
            ce.acknowledged_at,
            ce.acknowledged_by,
            ce.reviewed_at,
            ce.reviewed_by,
            ce.review_comment
        FROM change_events ce
        LEFT JOIN namespaces n ON ce.namespace_id = n.id
        WHERE {where_clause}
        ORDER BY 
            CASE ce.risk_level 
                WHEN 'critical' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'medium' THEN 3 
                ELSE 4 
            END,
            ce.detected_at DESC
        LIMIT :limit
        """
        
        results = await database.fetch_all(query, params)
        
        return {
            "changes": [dict(r) for r in results],
            "total": len(results),
            "filters": {
                "cluster_id": cluster_id,
                "status": status
            }
        }
        
    except Exception as e:
        logger.error("Failed to get pending reviews", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ------------ 6.3: Notification Hooks ------------

@router.get("/changes/hooks/{cluster_id}")
async def get_notification_hooks(
    cluster_id: int,
    enabled_only: bool = Query(True, description="Only return enabled hooks"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get notification hooks configured for a cluster.
    """
    from services.notification_service import get_notification_service
    
    try:
        service = get_notification_service()
        hooks = await service.get_hooks_for_cluster(cluster_id, enabled_only)
        
        # Don't expose sensitive config details
        safe_hooks = []
        for hook in hooks:
            safe_hook = {
                "id": hook.get("id"),
                "name": hook.get("name"),
                "hook_type": hook.get("hook_type"),
                "is_enabled": hook.get("is_enabled"),
                "trigger_on_critical": hook.get("trigger_on_critical"),
                "trigger_on_high": hook.get("trigger_on_high"),
                "trigger_on_medium": hook.get("trigger_on_medium"),
                "trigger_on_low": hook.get("trigger_on_low"),
                "trigger_change_types": hook.get("trigger_change_types"),
                "rate_limit_per_hour": hook.get("rate_limit_per_hour"),
                "last_triggered_at": hook.get("last_triggered_at"),
                "created_at": hook.get("created_at"),
                "created_by": hook.get("created_by"),
            }
            safe_hooks.append(safe_hook)
        
        return {
            "cluster_id": cluster_id,
            "hooks": safe_hooks,
            "total": len(safe_hooks)
        }
        
    except Exception as e:
        logger.error("Failed to get notification hooks", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/changes/hooks/{cluster_id}")
async def create_notification_hook(
    cluster_id: int,
    name: str = Query(..., description="Hook name"),
    hook_type: str = Query(..., description="Hook type: slack, teams, email, webhook"),
    config: str = Query(..., description="JSON configuration for the hook"),
    trigger_on_critical: bool = Query(True),
    trigger_on_high: bool = Query(True),
    trigger_on_medium: bool = Query(False),
    trigger_on_low: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new notification hook.
    
    Config examples:
    - Slack: {"webhook_url": "https://hooks.slack.com/services/..."}
    - Teams: {"webhook_url": "https://outlook.office.com/webhook/..."}
    - Webhook: {"url": "https://...", "method": "POST", "headers": {}}
    - Email: {"recipients": ["email@example.com"]}
    """
    import json as json_lib
    from services.notification_service import get_notification_service, HookType
    
    # Validate hook type
    valid_types = [e.value for e in HookType]
    if hook_type not in valid_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid hook type. Valid types: {valid_types}"
        )
    
    # Parse config
    try:
        config_dict = json_lib.loads(config)
    except json_lib.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON config")
    
    try:
        service = get_notification_service()
        result = await service.create_hook(
            cluster_id=cluster_id,
            name=name,
            hook_type=hook_type,
            config=config_dict,
            trigger_on_critical=trigger_on_critical,
            trigger_on_high=trigger_on_high,
            trigger_on_medium=trigger_on_medium,
            trigger_on_low=trigger_on_low,
            created_by=current_user.get("username", "unknown")
        )
        
        return {
            "success": True,
            "hook": result
        }
        
    except Exception as e:
        logger.error("Failed to create notification hook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/changes/hooks/{hook_id}")
async def update_notification_hook(
    hook_id: int,
    name: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    trigger_on_critical: Optional[bool] = Query(None),
    trigger_on_high: Optional[bool] = Query(None),
    trigger_on_medium: Optional[bool] = Query(None),
    trigger_on_low: Optional[bool] = Query(None),
    rate_limit_per_hour: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a notification hook.
    """
    from services.notification_service import get_notification_service
    
    updates = {}
    if name is not None:
        updates["name"] = name
    if is_enabled is not None:
        updates["is_enabled"] = is_enabled
    if trigger_on_critical is not None:
        updates["trigger_on_critical"] = trigger_on_critical
    if trigger_on_high is not None:
        updates["trigger_on_high"] = trigger_on_high
    if trigger_on_medium is not None:
        updates["trigger_on_medium"] = trigger_on_medium
    if trigger_on_low is not None:
        updates["trigger_on_low"] = trigger_on_low
    if rate_limit_per_hour is not None:
        updates["rate_limit_per_hour"] = rate_limit_per_hour
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    try:
        service = get_notification_service()
        success = await service.update_hook(hook_id, updates)
        
        return {
            "success": success,
            "hook_id": hook_id,
            "updates": updates
        }
        
    except Exception as e:
        logger.error("Failed to update notification hook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/changes/hooks/{hook_id}")
async def delete_notification_hook(
    hook_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a notification hook.
    """
    from services.notification_service import get_notification_service
    
    try:
        service = get_notification_service()
        success = await service.delete_hook(hook_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Hook not found")
        
        return {
            "success": True,
            "hook_id": hook_id,
            "message": "Hook deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete notification hook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/changes/hooks/{hook_id}/test")
async def test_notification_hook(
    hook_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Test a notification hook with a sample change.
    """
    from services.notification_service import get_notification_service
    from database.postgresql import database
    
    try:
        # Get the hook
        query = "SELECT * FROM notification_hooks WHERE id = :hook_id"
        hook = await database.fetch_one(query, {"hook_id": hook_id})
        
        if not hook:
            raise HTTPException(status_code=404, detail="Hook not found")
        
        # Create test change
        test_change = {
            "id": 0,
            "change_type": "test_notification",
            "target": "test-workload",
            "namespace": "test-namespace",
            "risk_level": "high",
            "affected_services": 3,
            "details": "This is a test notification from Flowfish Change Detection.",
            "changed_by": current_user.get("username", "test-user")
        }
        
        service = get_notification_service()
        success = await service.send_notification(dict(hook), test_change)
        
        return {
            "success": success,
            "hook_id": hook_id,
            "hook_type": hook["hook_type"],
            "message": "Test notification sent" if success else "Failed to send test notification"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test notification hook", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Error Anomaly Summary API
# ============================================

class ErrorAnomalySummaryResponse(BaseModel):
    """Error anomaly summary for Network Explorer and Dashboard"""
    total_anomalies: int = 0
    by_error_type: dict = {}
    affected_connections: List[dict] = []
    trends: dict = {}
    cluster_id: Optional[int] = None
    analysis_id: Optional[int] = None


@router.get("/changes/errors/summary", response_model=ErrorAnomalySummaryResponse)
async def get_error_anomaly_summary(
    cluster_id: int = Query(..., description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    time_range: str = Query("24h", description="Time range: 1h, 6h, 24h, 7d"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get error anomaly summary from change_events table.
    
    This endpoint returns aggregated error anomaly data for display
    in Network Explorer, Dashboard, and Map pages.
    
    Time ranges:
    - 1h: Last hour
    - 6h: Last 6 hours
    - 24h: Last 24 hours (default)
    - 7d: Last 7 days
    """
    import asyncio
    
    # Resolve formatted analysis_id in async context before entering sync function
    _resolved_ch_aid = await _get_ch_analysis_id(analysis_id, cluster_id) if analysis_id else None

    def _sync_query():
        """Synchronous ClickHouse query - run in thread pool
        
        IMPORTANT: Creates a NEW client per query to avoid concurrent connection issues.
        The clickhouse_driver Client is NOT thread-safe.
        """
        import json
        from database.clickhouse import create_clickhouse_client
        
        client = create_clickhouse_client()
        if not client:
            return None
        
        # Calculate time range
        time_map = {
            "1h": "1 HOUR",
            "6h": "6 HOUR",
            "24h": "24 HOUR",
            "7d": "7 DAY"
        }
        interval = time_map.get(time_range, "24 HOUR")
        
        # Build WHERE clause
        where_parts = [
            "change_type = 'error_anomaly'",
            f"detected_at >= now() - INTERVAL {interval}",
            f"cluster_id = {cluster_id}"
        ]
        if _resolved_ch_aid:
            where_parts.append(f"analysis_id = '{_resolved_ch_aid}'")
        
        where_clause = " AND ".join(where_parts)
        
        # Query error anomalies
        query = f"""
        SELECT
            target_name,
            details,
            risk_level,
            detected_at,
            before_state,
            after_state,
            metadata
        FROM change_events
        WHERE {where_clause}
        ORDER BY detected_at DESC
        LIMIT 100
        """
        
        result = client.execute(query)
        
        # Process results
        total_anomalies = len(result) if result else 0
        by_error_type = {}
        affected_connections = []
        
        for row in (result or []):
            target_name = row[0] or ""
            details = row[1] or ""
            risk_level = row[2] or "medium"
            detected_at = row[3]
            before_state = row[4] or "{}"
            after_state = row[5] or "{}"
            metadata = row[6] or "{}"
            
            # Parse states
            try:
                before = json.loads(before_state) if isinstance(before_state, str) else before_state
                after = json.loads(after_state) if isinstance(after_state, str) else after_state
                meta = json.loads(metadata) if isinstance(metadata, str) else metadata
            except:
                before = {}
                after = {}
                meta = {}
            
            # Extract error type
            error_type = after.get("error_type") or meta.get("error_type") or "UNKNOWN"
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1
            
            # Parse source and target from target_name (format: "source → target")
            parts = target_name.split(" → ") if " → " in target_name else [target_name, ""]
            source = parts[0] if len(parts) > 0 else target_name
            target = parts[1] if len(parts) > 1 else ""
            
            affected_connections.append({
                "source": source,
                "target": target,
                "error_type": error_type,
                "current_error_count": after.get("error_count", 0),
                "previous_error_count": before.get("error_count", 0),
                "risk_level": risk_level,
                "detected_at": detected_at.isoformat() if hasattr(detected_at, 'isoformat') else str(detected_at)
            })
        
        # Calculate trends (last hour vs last 24 hours)
        trend_aid_clause = f"AND analysis_id = '{_resolved_ch_aid}'" if _resolved_ch_aid else ""
        trend_query = f"""
        SELECT
            countIf(detected_at >= now() - INTERVAL 1 HOUR) as last_hour,
            countIf(detected_at >= now() - INTERVAL 24 HOUR) as last_24h
        FROM change_events
        WHERE change_type = 'error_anomaly'
          AND cluster_id = {cluster_id}
          {trend_aid_clause}
        """
        
        trend_result = client.execute(trend_query)
        last_hour = trend_result[0][0] if trend_result else 0
        last_24h = trend_result[0][1] if trend_result else 0
        
        # Determine trend direction
        if last_hour > 0 and last_24h > 0:
            hour_rate = last_hour
            day_rate = last_24h / 24
            if hour_rate > day_rate * 1.5:
                trend = "increasing"
            elif hour_rate < day_rate * 0.5:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return {
            "total_anomalies": total_anomalies,
            "by_error_type": by_error_type,
            "affected_connections": affected_connections,
            "trends": {
                "last_hour": last_hour,
                "last_24h": last_24h,
                "trend": trend
            }
        }
    
    try:
        # Run synchronous ClickHouse query in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(_sync_query)
        
        if result is None:
            return ErrorAnomalySummaryResponse(
                cluster_id=cluster_id,
                analysis_id=analysis_id
            )
        
        return ErrorAnomalySummaryResponse(
            total_anomalies=result["total_anomalies"],
            by_error_type=result["by_error_type"],
            affected_connections=result["affected_connections"],
            trends=result["trends"],
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        
    except Exception as e:
        logger.error("Failed to get error anomaly summary", error=str(e))
        return ErrorAnomalySummaryResponse(
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
