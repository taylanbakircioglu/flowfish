"""
Simulation Schemas - Network Policy and Impact Simulation
Defines request/response models for simulation endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class PolicyType(str, Enum):
    """Network policy type"""
    INGRESS = "ingress"
    EGRESS = "egress"
    BOTH = "both"


class PolicyAction(str, Enum):
    """Network policy action"""
    ALLOW = "allow"
    DENY = "deny"


class ImpactLevel(str, Enum):
    """Impact severity level"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ImpactCategory(str, Enum):
    """
    Category of impact - what kind of effect the change has.
    
    IMPORTANT: Impact Category and Level must be consistent:
    - SERVICE_OUTAGE, CONNECTIVITY_LOSS → Always HIGH
    - CASCADE_RISK → MEDIUM (potential future impact)
    - PERFORMANCE_DEGRADATION → MEDIUM or LOW
    - Others → Context dependent
    """
    SERVICE_OUTAGE = "service_outage"          # Complete service unavailability → HIGH
    CONNECTIVITY_LOSS = "connectivity_loss"    # Network connectivity issues → HIGH
    CASCADE_RISK = "cascade_risk"              # Potential cascade from upstream failure → MEDIUM
    PERFORMANCE_DEGRADATION = "performance_degradation"  # Slowdowns, resource constraints → MEDIUM/LOW
    CONFIGURATION_DRIFT = "configuration_drift"  # Config inconsistencies, env changes
    SECURITY_EXPOSURE = "security_exposure"    # Security posture changes
    COMPATIBILITY_RISK = "compatibility_risk"  # Version/API compatibility issues
    TRANSIENT_DISRUPTION = "transient_disruption"  # Temporary restart/rollout


class DependencyType(str, Enum):
    """Dependency relationship type"""
    DIRECT = "direct"
    INDIRECT = "indirect"


class ChangeType(str, Enum):
    """Simulation change types"""
    DELETE = "delete"
    SCALE_DOWN = "scale_down"
    NETWORK_ISOLATE = "network_isolate"
    RESOURCE_CHANGE = "resource_change"
    PORT_CHANGE = "port_change"
    CONFIG_CHANGE = "config_change"
    IMAGE_UPDATE = "image_update"
    NETWORK_POLICY_APPLY = "network_policy_apply"
    NETWORK_POLICY_REMOVE = "network_policy_remove"


# =============================================================================
# Change Type Characteristics - Each change type has different impact profiles
# =============================================================================

class ChangeTypeCharacteristics:
    """
    Defines how each change type affects services differently.
    This is the core logic that differentiates impact calculations.
    
    IMPORTANT: Impact Level and Impact Category must be consistent!
    - SERVICE_OUTAGE → Always HIGH (outage is critical by definition)
    - CONNECTIVITY_LOSS → Always HIGH (connection lost is critical)
    - PERFORMANCE_DEGRADATION → MEDIUM or LOW (degradation ≠ outage)
    - CASCADE_RISK → MEDIUM (potential future impact, not immediate outage)
    """
    
    CHARACTERISTICS = {
        ChangeType.DELETE: {
            "primary_impact": ImpactCategory.SERVICE_OUTAGE,
            "secondary_impacts": [ImpactCategory.CONNECTIVITY_LOSS],
            "severity_multiplier": 1.0,  # Full impact
            "recovery_time": "manual",   # Requires manual intervention
            "reversible": False,
            "affects_direct": True,
            "affects_indirect": True,
            "direct_impact_level": ImpactLevel.HIGH,      # SERVICE_OUTAGE = always HIGH
            "indirect_impact_level": ImpactLevel.MEDIUM,  # Indirect = CASCADE_RISK, not outage
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,  # Different category for indirect!
            "description": "Complete service removal - all connections will fail immediately",
            "risk_factors": ["data_loss", "cascade_failure", "no_auto_recovery"],
        },
        ChangeType.SCALE_DOWN: {
            "primary_impact": ImpactCategory.SERVICE_OUTAGE,
            "secondary_impacts": [ImpactCategory.TRANSIENT_DISRUPTION],
            "severity_multiplier": 0.9,
            "recovery_time": "fast",     # Can scale back up quickly
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": True,
            "direct_impact_level": ImpactLevel.HIGH,      # SERVICE_OUTAGE = always HIGH
            "indirect_impact_level": ImpactLevel.MEDIUM,  # Indirect = CASCADE_RISK
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,
            "description": "Service unavailable until scaled back up",
            "risk_factors": ["temporary_outage", "queue_buildup"],
        },
        ChangeType.NETWORK_ISOLATE: {
            "primary_impact": ImpactCategory.CONNECTIVITY_LOSS,
            "secondary_impacts": [ImpactCategory.SECURITY_EXPOSURE],
            "severity_multiplier": 0.85,
            "recovery_time": "fast",
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": False,   # Only direct connections affected
            "direct_impact_level": ImpactLevel.HIGH,
            "indirect_impact_level": ImpactLevel.LOW,
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,  # Not outage for indirect
            "description": "Network traffic blocked - service running but unreachable",
            "risk_factors": ["connection_timeout", "health_check_failure"],
        },
        ChangeType.RESOURCE_CHANGE: {
            "primary_impact": ImpactCategory.PERFORMANCE_DEGRADATION,
            "secondary_impacts": [ImpactCategory.TRANSIENT_DISRUPTION],
            "severity_multiplier": 0.5,   # Lower severity - usually not outage
            "recovery_time": "auto",      # Pod restarts automatically
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": False,    # Indirect services not affected
            "direct_impact_level": ImpactLevel.MEDIUM,  # NOT high - just performance
            "indirect_impact_level": ImpactLevel.LOW,
            "indirect_impact_category": ImpactCategory.PERFORMANCE_DEGRADATION,  # Same category, lower level
            "description": "Performance impact - slower responses, potential OOM kills",
            "risk_factors": ["latency_increase", "oom_kill", "cpu_throttling"],
        },
        ChangeType.PORT_CHANGE: {
            "primary_impact": ImpactCategory.CONNECTIVITY_LOSS,
            "secondary_impacts": [],
            "severity_multiplier": 0.8,
            "recovery_time": "config_update",
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": False,
            "direct_impact_level": ImpactLevel.HIGH,
            "indirect_impact_level": ImpactLevel.NONE,
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,
            "description": "Connection failure until clients update port configuration",
            "risk_factors": ["connection_refused", "service_discovery_lag"],
        },
        ChangeType.CONFIG_CHANGE: {
            "primary_impact": ImpactCategory.CONFIGURATION_DRIFT,
            "secondary_impacts": [ImpactCategory.TRANSIENT_DISRUPTION],
            "severity_multiplier": 0.6,
            "recovery_time": "varies",
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": False,
            "direct_impact_level": ImpactLevel.MEDIUM,
            "indirect_impact_level": ImpactLevel.LOW,
            "indirect_impact_category": ImpactCategory.CONFIGURATION_DRIFT,  # Same category
            "description": "Behavior change - may affect functionality without outage",
            "risk_factors": ["config_mismatch", "feature_toggle", "env_dependency"],
        },
        ChangeType.IMAGE_UPDATE: {
            "primary_impact": ImpactCategory.COMPATIBILITY_RISK,
            "secondary_impacts": [ImpactCategory.TRANSIENT_DISRUPTION],
            "severity_multiplier": 0.7,
            "recovery_time": "rollback",
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": True,
            "direct_impact_level": ImpactLevel.MEDIUM,
            "indirect_impact_level": ImpactLevel.LOW,
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,  # Cascade risk for indirect
            "description": "Version change - API compatibility and brief restart disruption",
            "risk_factors": ["api_breaking_change", "rolling_update_gap", "startup_time"],
        },
        ChangeType.NETWORK_POLICY_APPLY: {
            "primary_impact": ImpactCategory.CONNECTIVITY_LOSS,
            "secondary_impacts": [ImpactCategory.SECURITY_EXPOSURE],
            "severity_multiplier": 0.75,
            "recovery_time": "policy_update",
            "reversible": True,
            "affects_direct": True,
            "affects_indirect": False,
            "direct_impact_level": ImpactLevel.HIGH,
            "indirect_impact_level": ImpactLevel.NONE,
            "indirect_impact_category": ImpactCategory.CASCADE_RISK,
            "description": "Traffic filtering - unallowed connections will be blocked",
            "risk_factors": ["unintended_block", "policy_conflict"],
        },
        ChangeType.NETWORK_POLICY_REMOVE: {
            "primary_impact": ImpactCategory.SECURITY_EXPOSURE,
            "secondary_impacts": [],
            "severity_multiplier": 0.4,   # Low operational impact
            "recovery_time": "immediate",
            "reversible": True,
            "affects_direct": False,      # Removing policy doesn't break connections
            "affects_indirect": False,
            "direct_impact_level": ImpactLevel.LOW,
            "indirect_impact_level": ImpactLevel.NONE,
            "indirect_impact_category": ImpactCategory.SECURITY_EXPOSURE,  # Same category
            "description": "Security posture change - traffic allowed but no connectivity loss",
            "risk_factors": ["security_gap", "compliance_violation"],
        },
    }
    
    @classmethod
    def get(cls, change_type: ChangeType) -> dict:
        """Get characteristics for a change type"""
        return cls.CHARACTERISTICS.get(change_type, cls.CHARACTERISTICS[ChangeType.DELETE])


# =============================================================================
# Network Policy Models
# =============================================================================

class IPBlock(BaseModel):
    """IP block specification for network policy"""
    cidr: str = Field(..., description="CIDR notation (e.g., 10.0.0.0/24)")
    except_cidrs: Optional[List[str]] = Field(default=None, alias="except", description="Exception CIDRs")

    class Config:
        populate_by_name = True


class LabelSelector(BaseModel):
    """Label selector for pods/namespaces"""
    match_labels: Optional[Dict[str, str]] = Field(default=None, description="Exact label matches")
    match_expressions: Optional[List[Dict[str, Any]]] = Field(default=None, description="Label expressions")


class NetworkPolicyPeer(BaseModel):
    """Network policy peer (source or destination)"""
    namespace_selector: Optional[LabelSelector] = Field(default=None, description="Namespace selector")
    pod_selector: Optional[LabelSelector] = Field(default=None, description="Pod selector")
    ip_block: Optional[IPBlock] = Field(default=None, description="IP block")


class NetworkPolicyPort(BaseModel):
    """Network policy port specification"""
    protocol: str = Field(default="TCP", description="Protocol (TCP, UDP, SCTP)")
    port: Optional[int] = Field(default=None, description="Port number")
    end_port: Optional[int] = Field(default=None, description="End port for range")


class NetworkPolicyRule(BaseModel):
    """Single network policy rule"""
    rule_type: PolicyType = Field(..., description="Rule type (ingress/egress)")
    action: PolicyAction = Field(default=PolicyAction.ALLOW, description="Rule action")
    peers: Optional[List[NetworkPolicyPeer]] = Field(default=None, description="From/To peers")
    ports: Optional[List[NetworkPolicyPort]] = Field(default=None, description="Allowed ports")


class NetworkPolicySpec(BaseModel):
    """Network policy specification"""
    policy_name: str = Field(..., description="Policy name")
    target_namespace: str = Field(..., description="Target namespace")
    target_pod_selector: LabelSelector = Field(..., description="Target pod selector")
    policy_types: List[PolicyType] = Field(default=[PolicyType.INGRESS, PolicyType.EGRESS])
    ingress_rules: Optional[List[NetworkPolicyRule]] = Field(default=None)
    egress_rules: Optional[List[NetworkPolicyRule]] = Field(default=None)


# =============================================================================
# Request Models
# =============================================================================

class NetworkPolicyPreviewRequest(BaseModel):
    """Request for previewing network policy impact"""
    cluster_id: int = Field(..., description="Cluster ID")
    analysis_id: Optional[int] = Field(default=None, description="Analysis ID for scoped data")
    target_namespace: str = Field(..., description="Target namespace")
    target_workload: str = Field(..., description="Target workload name")
    target_kind: str = Field(default="Deployment", description="Target kind (Deployment, Pod, etc.)")
    policy_spec: NetworkPolicySpec = Field(..., description="Network policy specification")


class NetworkPolicyGenerateRequest(BaseModel):
    """Request for generating network policy from observed traffic"""
    cluster_id: int = Field(..., description="Cluster ID")
    analysis_id: Optional[int] = Field(default=None, description="Analysis ID")
    target_namespace: str = Field(..., description="Target namespace")
    target_workload: str = Field(..., description="Target workload name")
    target_kind: str = Field(default="Deployment", description="Target kind")
    policy_types: List[PolicyType] = Field(default=[PolicyType.BOTH], description="Policy types to generate")
    include_dns: bool = Field(default=True, description="Include DNS egress rules")
    strict_mode: bool = Field(default=False, description="Generate deny-all by default")


class ImpactSimulationRequest(BaseModel):
    """Request for running impact simulation"""
    cluster_id: int = Field(..., description="Cluster ID")
    analysis_id: Optional[int] = Field(default=None, description="Analysis ID")
    target_id: str = Field(..., description="Target resource identifier")
    target_name: str = Field(..., description="Target resource name")
    target_namespace: str = Field(..., description="Target namespace")
    target_kind: str = Field(..., description="Target kind (Deployment, Pod, Service, External)")
    change_type: ChangeType = Field(..., description="Type of change to simulate")
    network_policy_spec: Optional[NetworkPolicySpec] = Field(
        default=None, 
        description="Network policy spec for policy-related changes"
    )


# =============================================================================
# Response Models
# =============================================================================

class AffectedConnection(BaseModel):
    """Connection that would be affected by a policy"""
    source_name: str
    source_namespace: str
    source_kind: str
    target_name: str
    target_namespace: str
    target_kind: str
    protocol: str
    port: int
    request_count: int = 0
    would_be_blocked: bool = False
    rule_match: Optional[str] = None


class AffectedService(BaseModel):
    """Service affected by simulation"""
    id: str
    name: str
    namespace: str
    kind: str = "Pod"
    impact: ImpactLevel
    impact_category: Optional[ImpactCategory] = Field(
        default=None, 
        description="Category of impact: outage, performance, connectivity, etc."
    )
    impact_description: Optional[str] = Field(
        default=None,
        description="Human-readable description of expected impact"
    )
    dependency: DependencyType
    recommendation: str
    connection_details: Optional[Dict[str, Any]] = None
    risk_score: float = 0.0
    risk_factors: Optional[List[str]] = Field(
        default=None,
        description="Specific risk factors for this service"
    )
    recovery_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Information about recovery time and process"
    )


class NetworkPolicyPreviewResponse(BaseModel):
    """Response for network policy preview"""
    policy_name: str
    target_workload: str
    target_namespace: str
    total_connections: int
    blocked_connections: int
    allowed_connections: int
    affected_connections: List[AffectedConnection]
    generated_yaml: str
    warnings: List[str] = []
    recommendations: List[str] = []


class NetworkPolicyGenerateResponse(BaseModel):
    """Response for network policy generation"""
    policy_name: str
    target_workload: str
    target_namespace: str
    observed_ingress_sources: int
    observed_egress_destinations: int
    generated_yaml: str
    policy_spec: NetworkPolicySpec
    coverage_summary: Dict[str, Any]
    recommendations: List[str] = []


class ImpactSummary(BaseModel):
    """Summary of impact simulation results"""
    total_affected: int
    high_impact: int
    medium_impact: int
    low_impact: int
    blast_radius: int
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Change type specific summary
    primary_impact_category: Optional[ImpactCategory] = Field(
        default=None,
        description="Primary category of impact for this change type"
    )
    impact_description: Optional[str] = Field(
        default=None,
        description="Overall description of expected impact"
    )
    expected_behavior: Optional[str] = Field(
        default=None,
        description="What will happen when this change is applied"
    )
    recovery_time: Optional[str] = Field(
        default=None,
        description="Expected recovery time: immediate, fast, manual, etc."
    )
    is_reversible: bool = Field(
        default=True,
        description="Whether the change can be easily reversed"
    )


class NoDependencyInfo(BaseModel):
    """Information when no dependencies are detected"""
    scenario: str = Field(..., description="Scenario type: NO_GRAPH_MATCH, ISOLATED_WORKLOAD, EXTERNAL_ONLY")
    title: str
    description: str
    suggestions: List[str]
    alert_type: str = Field(default="info", description="Alert type: success, info, warning, error")


class SimulationDetails(BaseModel):
    """Detailed simulation information"""
    target_name: str
    target_namespace: str
    target_kind: str
    change_type: str
    change_description: str
    graph_matches: int
    simulation_timestamp: datetime


class ImpactSimulationResponse(BaseModel):
    """Response for impact simulation"""
    success: bool = True
    simulation_id: str
    details: SimulationDetails
    summary: ImpactSummary
    affected_services: List[AffectedService]
    no_dependency_info: Optional[NoDependencyInfo] = None
    network_policy_suggestion: Optional[NetworkPolicyGenerateResponse] = None
    timeline_projection: Optional[Dict[str, Any]] = None
    rollback_scenario: Optional[Dict[str, Any]] = None


# =============================================================================
# Export Report Models
# =============================================================================

class ExportMetadata(BaseModel):
    """Export report metadata"""
    generated_at: datetime
    analysis_id: Optional[int]
    cluster_id: int
    cluster_name: Optional[str]
    export_format: str


class SimulationExportData(BaseModel):
    """Simulation data for export"""
    target_name: str
    target_namespace: str
    target_kind: str
    change_type: str
    graph_matches: int


class ImpactSimulationExportReport(BaseModel):
    """Complete export report for impact simulation"""
    metadata: ExportMetadata
    simulation: SimulationExportData
    impact_summary: ImpactSummary
    affected_services: List[AffectedService]
    network_policy_suggestion: Optional[Dict[str, Any]] = None
    recommendations: List[str] = []

