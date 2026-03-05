"""
Blast Radius Router - Pre-deployment impact assessment API
Provides risk scoring and blast radius analysis for CI/CD pipeline integration

Inspired by:
- Google/Baidu Blast Radius methodology
- Gremlin Reliability Score
- Netflix ChAP (Chaos Automation Platform)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from enum import Enum
import structlog
import uuid
import json

from utils.jwt_utils import get_current_user
from database.postgresql import database

logger = structlog.get_logger(__name__)
router = APIRouter()


# =============================================================================
# Enums and Models
# =============================================================================

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationType(str, Enum):
    PROCEED = "proceed"
    REVIEW_REQUIRED = "review_required"
    DELAY_SUGGESTED = "delay_suggested"


class ChangeType(str, Enum):
    IMAGE_UPDATE = "image_update"
    CONFIG_CHANGE = "config_change"
    SCALE_CHANGE = "scale_change"
    RESOURCE_CHANGE = "resource_change"
    DELETE = "delete"
    NETWORK_POLICY = "network_policy"
    OTHER = "other"


# Request/Response Models
class BlastRadiusChangeInfo(BaseModel):
    """Information about the change being assessed"""
    type: str = Field(description="Type of change (image_update, config_change, etc.)")
    target: str = Field(description="Target service/deployment name")
    namespace: str = Field(default="default", description="Kubernetes namespace")
    image: Optional[str] = Field(default=None, description="New image tag if applicable")
    triggered_by: Optional[str] = Field(default=None, description="User/system that triggered the change")
    pipeline: Optional[str] = Field(default=None, description="CI/CD pipeline name")
    commit: Optional[str] = Field(default=None, description="Git commit SHA")


class BlastRadiusAssessRequest(BaseModel):
    """Request for blast radius assessment"""
    cluster_id: int = Field(description="Cluster ID to assess")
    analysis_id: Optional[int] = Field(default=None, description="Analysis ID (uses latest if not provided)")
    change: BlastRadiusChangeInfo = Field(description="Change information")
    same_namespace_only: bool = Field(default=True, description="Only include dependencies in the same namespace (recommended for pipeline deployments)")


class BlastRadiusInfo(BaseModel):
    """Blast radius details"""
    total_affected: int
    direct_dependencies: int
    indirect_dependencies: int
    critical_services: List[str]
    namespaces_affected: List[str]
    services_by_impact: Dict[str, List[str]]  # high, medium, low


class SuggestedAction(BaseModel):
    """A suggested action for the deployment"""
    priority: str  # critical, high, medium, low
    action: str
    reason: str
    automatable: bool = False


class BlastRadiusAssessResponse(BaseModel):
    """Response from blast radius assessment"""
    assessment_id: str
    timestamp: str
    
    # Scores
    risk_score: int = Field(ge=0, le=100, description="Risk score 0-100")
    risk_level: RiskLevel
    confidence: float = Field(ge=0, le=1, description="Confidence in assessment")
    
    # Blast radius details
    blast_radius: BlastRadiusInfo
    
    # Recommendations
    recommendation: RecommendationType
    suggested_actions: List[SuggestedAction]
    
    # Pipeline integration fields
    advisory_only: bool = True  # Always true - Flowfish never blocks
    decision: str = "pipeline_owner"  # Decision is always with pipeline owner
    
    # Metadata
    assessment_duration_ms: int
    flowfish_version: str = "1.0.0"


class AssessmentHistoryItem(BaseModel):
    """Historical assessment record"""
    assessment_id: str
    timestamp: str
    cluster_id: int
    target: str
    namespace: str
    change_type: str
    risk_score: int
    risk_level: str
    affected_count: int
    triggered_by: Optional[str]
    pipeline: Optional[str]


# =============================================================================
# Namespace-based Blast Radius Models (for CI/CD pipelines)
# =============================================================================

class NamespaceBlastRadiusRequest(BaseModel):
    """Simple request for namespace-based blast radius (CI/CD optimized)"""
    cluster_id: int = Field(description="Cluster ID to assess")
    namespace: str = Field(description="Namespace being deployed")
    analysis_id: Optional[int] = Field(default=None, description="Analysis ID (uses latest if not provided)")
    triggered_by: Optional[str] = Field(default=None, description="User/system that triggered (for logging)")
    pipeline: Optional[str] = Field(default=None, description="Pipeline name (for logging)")


class ServiceDependency(BaseModel):
    """A service and its dependencies"""
    service: str
    dependencies: List[str]
    dependency_count: int


class NamespaceBlastRadiusResponse(BaseModel):
    """Response for namespace blast radius assessment"""
    assessment_id: str
    timestamp: str
    
    # Basic info
    cluster_id: int
    namespace: str
    
    # Services in namespace
    services: List[str]
    service_count: int
    
    # Dependencies
    internal_dependencies: int  # Dependencies within namespace
    external_dependencies: int  # Dependencies to other namespaces
    total_dependencies: int
    
    # Risk assessment
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    
    # Dependency map
    dependency_map: Dict[str, List[str]]  # service -> [dependencies]
    external_dependency_map: Dict[str, List[str]]  # service -> [external dependencies]
    
    # For pipeline integration
    recommendation: RecommendationType
    suggested_actions: List[SuggestedAction]
    advisory_only: bool = True
    
    # Metadata
    assessment_duration_ms: int
    flowfish_version: str = "1.0.0"


# =============================================================================
# Helper Functions
# =============================================================================

async def get_latest_analysis_id(cluster_id: int) -> Optional[int]:
    """Get the latest completed analysis for a cluster"""
    query = """
        SELECT id FROM analyses 
        WHERE cluster_id = :cluster_id 
        AND status IN ('completed', 'running', 'stopped')
        ORDER BY created_at DESC 
        LIMIT 1
    """
    result = await database.fetch_one(query, {"cluster_id": cluster_id})
    return result["id"] if result else None


async def get_service_dependencies(cluster_id: int, analysis_id: int, target: str, namespace: str, same_namespace_only: bool = True) -> Dict[str, Any]:
    """
    Get dependencies for a target service from the Neo4j dependency graph.
    Returns both direct and indirect dependencies with impact levels.
    
    Blast radius includes:
    - Services that the target CALLS (outgoing - they will lose access)
    - Services that CALL the target (incoming - they will be affected!)
    
    Args:
        same_namespace_only: If True, only include dependencies in the same namespace (default for pipelines)
    """
    try:
        # Import graph_query_client from communications (same source as Impact Simulation)
        from routers.communications import graph_query_client
        
        logger.info(
            "Fetching blast radius from Neo4j",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            target=target,
            namespace=namespace
        )
        
        # Get dependency graph from Neo4j via graph-query service
        full_graph = await graph_query_client.get_dependency_graph(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=None,  # Get all namespaces to find cross-namespace dependencies
            depth=2,
            search=target  # Search for target and its connections
        )
        
        if not full_graph:
            logger.warning("No graph data returned", cluster_id=cluster_id, target=target)
            return _empty_dependencies()
        
        nodes = full_graph.get("nodes", [])
        edges = full_graph.get("edges", [])
        
        logger.info(
            "Graph data received",
            nodes_count=len(nodes),
            edges_count=len(edges)
        )
        
        if not nodes or not edges:
            return _empty_dependencies()
        
        # Build node lookup
        node_map = {n.get("id"): n for n in nodes}
        
        # Find target node(s) - flexible matching
        target_lower = target.lower()
        namespace_lower = namespace.lower()
        target_ids = set()
        
        for node in nodes:
            node_name = node.get("name", "").lower()
            node_ns = node.get("namespace", "").lower()
            
            # Match by name containing target or target containing name
            name_match = (
                target_lower in node_name or 
                node_name in target_lower or
                node_name.startswith(target_lower + "-") or
                node_name == target_lower
            )
            
            # Namespace match (flexible)
            ns_match = (
                namespace_lower == node_ns or
                namespace_lower in node_ns or
                node_ns in namespace_lower or
                not namespace_lower  # If no namespace provided, match any
            )
            
            if name_match and ns_match:
                target_ids.add(node.get("id"))
        
        if not target_ids:
            # Fallback: just match by name
            for node in nodes:
                node_name = node.get("name", "").lower()
                if target_lower in node_name or node_name.startswith(target_lower):
                    target_ids.add(node.get("id"))
        
        logger.info(f"Found {len(target_ids)} target nodes for {namespace}/{target}")
        
        dependencies = {
            "direct": [],
            "indirect": [],
            "all": []
        }
        namespaces_set = set()
        seen = set()
        
        # Find direct dependencies
        direct_neighbor_ids = set()
        for edge in edges:
            source_id = edge.get("source_id") or edge.get("source", {}).get("id")
            target_id = edge.get("target_id") or edge.get("target", {}).get("id")
            
            # Outgoing: target -> other (services the target calls)
            if source_id in target_ids and target_id not in target_ids:
                direct_neighbor_ids.add(target_id)
                _add_dependency(node_map, target_id, dependencies, namespaces_set, seen, "direct", namespace, same_namespace_only)
            
            # Incoming: other -> target (services that call the target - AFFECTED!)
            if target_id in target_ids and source_id not in target_ids:
                direct_neighbor_ids.add(source_id)
                _add_dependency(node_map, source_id, dependencies, namespaces_set, seen, "direct", namespace, same_namespace_only)
        
        # Find indirect dependencies (2-hop) - only if not filtering to same namespace
        if not same_namespace_only:
            for edge in edges:
                source_id = edge.get("source_id") or edge.get("source", {}).get("id")
                target_id = edge.get("target_id") or edge.get("target", {}).get("id")
                
                # 2-hop from direct neighbors
                if source_id in direct_neighbor_ids and target_id not in target_ids and target_id not in direct_neighbor_ids:
                    _add_dependency(node_map, target_id, dependencies, namespaces_set, seen, "indirect", namespace, same_namespace_only)
                if target_id in direct_neighbor_ids and source_id not in target_ids and source_id not in direct_neighbor_ids:
                    _add_dependency(node_map, source_id, dependencies, namespaces_set, seen, "indirect", namespace, same_namespace_only)
        
        result = {
            "dependencies": dependencies,
            "namespaces": list(namespaces_set),
            "total": len(dependencies["all"]),
            "direct_count": len(dependencies["direct"]),
            "indirect_count": len(dependencies["indirect"])
        }
        
        logger.info(
            "Blast radius calculated",
            target=f"{namespace}/{target}",
            direct=result["direct_count"],
            indirect=result["indirect_count"],
            total=result["total"]
        )
        
        return result
        
    except Exception as e:
        logger.error("Error fetching dependencies from Neo4j", error=str(e), target=target, namespace=namespace)
        return _empty_dependencies()


def _is_ip_address(name: str) -> bool:
    """Check if name is an IP address (with optional port)"""
    import re
    # Match IP address with optional :port suffix
    # Examples: 10.0.0.1, 10.0.0.1:8080, 0.0.0.0:0
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}(:\d+)?$'
    return bool(re.match(ip_pattern, name))


def _normalize_service_name(name: str) -> str:
    """
    Normalize service name:
    - Remove DNS suffixes (.svc.cluster.local., etc.)
    - Extract deployment name from pod name (remove replica hash)
    """
    import re
    
    # Remove trailing dot
    name = name.rstrip('.')
    
    # Remove DNS suffixes
    dns_suffixes = [
        '.svc.cluster.local',
        '.cluster.local',
        '.svc',
    ]
    for suffix in dns_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    # Extract deployment name from pod name
    # Pattern: <deployment>-<replicaset-hash>-<pod-hash>
    # Example: backend-647d796686-qxvnt -> backend
    # Example: timeseries-query-6d88cfdb7c-fshz5 -> timeseries-query
    pod_pattern = r'^(.+)-[a-f0-9]{8,10}-[a-z0-9]{5}$'
    match = re.match(pod_pattern, name)
    if match:
        return match.group(1)
    
    # Pattern for StatefulSet: <name>-<ordinal>
    # Example: clickhouse-0 -> clickhouse
    statefulset_pattern = r'^(.+)-\d+$'
    match = re.match(statefulset_pattern, name)
    if match:
        return match.group(1)
    
    return name


def _is_infrastructure_component(name: str, namespace: str) -> bool:
    """Check if this is an infrastructure component that should be excluded"""
    name_lower = name.lower()
    ns_lower = namespace.lower() if namespace else ""
    
    # Infrastructure namespace prefixes (using startswith for broader matching)
    infra_namespace_prefixes = [
        "openshift-",       # All OpenShift system namespaces
        "kube-",            # Kubernetes system namespaces
        "sdn-",             # SDN infrastructure
        "external",         # External DNS names namespace
        "ibm",              # IBM infrastructure (ibmblockstorage, etc.)
    ]
    
    # Exact infrastructure namespaces
    infra_namespaces_exact = [
        "external",
        "sdn-infrastructure",
        "kasten-io",        # Backup infrastructure
        "tankie",           # Internal tooling
        "kubecomp",         # Internal tooling
    ]
    
    # Infrastructure component name patterns
    infra_patterns = [
        "kube-",
        "calico-",
        "coredns",
        "etcd",
        "metrics-server",
        "router-default",
        "haproxy",
        "ingress-controller",
        "dns-default",
        "oauth-",
        "console-",
        "prometheus-",      # Monitoring
        "alertmanager",     # Monitoring
        "thanos-",          # Monitoring
        "node-exporter",    # Monitoring
        "kube-state-metrics",
        "kanister",         # Backup
        "external-secrets", # Secret management infra
        "gitops-operator",  # GitOps infra
        "inspektor-gadget", # Flowfish tracing infrastructure
    ]
    
    # Check namespace prefix
    if any(ns_lower.startswith(prefix) for prefix in infra_namespace_prefixes):
        return True
    
    # Check exact namespace match
    if ns_lower in infra_namespaces_exact:
        return True
    
    # Check name patterns
    if any(pattern in name_lower for pattern in infra_patterns):
        return True
    
    return False


def _add_dependency(node_map: dict, node_id: str, dependencies: dict, namespaces: set, seen: set, dep_type: str, target_namespace: str = "", same_namespace_only: bool = True):
    """Helper to add a dependency to the result"""
    if node_id in seen:
        return
    
    node = node_map.get(node_id, {})
    if not node:
        return
    
    name = node.get("name", "")
    ns = node.get("namespace", "")
    
    # Skip IP addresses
    if _is_ip_address(name):
        seen.add(node_id)
        return
    
    # Skip infrastructure components
    if _is_infrastructure_component(name, ns):
        seen.add(node_id)
        return
    
    # Filter by namespace if same_namespace_only is True
    if same_namespace_only and target_namespace:
        if ns.lower() != target_namespace.lower():
            seen.add(node_id)
            return
    
    # Normalize the service name (dedupe pods, remove DNS suffixes)
    normalized_name = _normalize_service_name(name)
    
    # Use normalized name for deduplication
    key = f"{ns}/{normalized_name}"
    if key in seen:
        seen.add(node_id)
        return
    seen.add(key)
    seen.add(node_id)
    
    dep = {
        "name": normalized_name,
        "namespace": ns,
        "kind": node.get("kind", "Pod"),
        "protocol": "TCP",
        "port": 0,
        "request_count": 0,
        "dependency_type": dep_type
    }
    
    dependencies["all"].append(dep)
    if ns:
        namespaces.add(ns)
    
    if dep_type == "direct":
        dependencies["direct"].append(dep)
    else:
        dependencies["indirect"].append(dep)


def _empty_dependencies() -> Dict[str, Any]:
    """Return empty dependencies structure"""
    return {
        "dependencies": {"direct": [], "indirect": [], "all": []},
        "namespaces": [],
        "total": 0,
        "direct_count": 0,
        "indirect_count": 0
    }


def calculate_risk_score(
    change_type: str,
    direct_count: int,
    indirect_count: int,
    critical_services: List[str],
    is_business_hours: bool
) -> tuple[int, RiskLevel, float]:
    """
    Calculate risk score based on multiple factors.
    Returns (score, level, confidence)
    """
    score = 0
    total_deps = direct_count + indirect_count
    
    # Factor 1: Change type severity (0-25)
    change_severity = {
        "delete": 25,
        "network_policy": 20,
        "scale_change": 10,
        "image_update": 10,
        "config_change": 8,
        "resource_change": 5,
        "other": 5
    }
    base_severity = change_severity.get(change_type, 5)
    
    # If no dependencies found, don't add full severity
    # (might be isolated service or missing data)
    if total_deps == 0:
        score += base_severity // 2  # Half severity when isolated
    else:
        score += base_severity
    
    # Factor 2: Direct dependencies (0-30)
    score += min(30, direct_count * 6)
    
    # Factor 3: Indirect dependencies (0-20)
    score += min(20, indirect_count * 2)
    
    # Factor 4: Critical services (0-15)
    score += min(15, len(critical_services) * 5)
    
    # Factor 5: Business hours (0-10)
    if is_business_hours and direct_count > 0:
        score += 10
    
    # Normalize to 0-100
    score = min(100, score)
    
    # Determine risk level
    if score >= 75:
        level = RiskLevel.CRITICAL
    elif score >= 50:
        level = RiskLevel.HIGH
    elif score >= 25:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW
    
    # Confidence based on data availability
    # Low confidence when no dependencies found (could be isolated or missing data)
    if direct_count > 3 or indirect_count > 5:
        confidence = 0.9
    elif direct_count > 0 or indirect_count > 0:
        confidence = 0.75
    else:
        confidence = 0.3  # Very low confidence - likely missing data
    
    return score, level, confidence


def generate_suggested_actions(
    risk_level: RiskLevel,
    direct_count: int,
    indirect_count: int,
    critical_services: List[str],
    change_type: str,
    is_business_hours: bool
) -> List[SuggestedAction]:
    """Generate contextual suggestions based on assessment"""
    actions = []
    
    # Critical/High risk suggestions
    if risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
        actions.append(SuggestedAction(
            priority="critical",
            action="Test in staging environment first",
            reason=f"{direct_count} direct dependencies affected - validate in non-production",
            automatable=True
        ))
        
        if len(critical_services) > 0:
            actions.append(SuggestedAction(
                priority="critical",
                action=f"Notify teams: {', '.join(critical_services[:3])}",
                reason="Critical services in blast radius require team awareness",
                automatable=True
            ))
    
    # Business hours suggestion
    if is_business_hours and risk_level != RiskLevel.LOW:
        actions.append(SuggestedAction(
            priority="high",
            action="Schedule for low-traffic window (02:00-06:00)",
            reason="Executing during business hours increases user impact",
            automatable=True
        ))
    
    # Canary deployment suggestion
    if direct_count >= 3:
        actions.append(SuggestedAction(
            priority="high",
            action="Use canary deployment (10% traffic first)",
            reason=f"Wide blast radius ({direct_count} services) - limit initial exposure",
            automatable=True
        ))
    
    # Rollback readiness
    if change_type in ["image_update", "config_change", "delete"]:
        actions.append(SuggestedAction(
            priority="medium",
            action="Verify rollback procedure is ready",
            reason=f"{change_type} changes require tested rollback plan",
            automatable=False
        ))
    
    # Monitoring suggestion
    actions.append(SuggestedAction(
        priority="medium",
        action="Enable enhanced monitoring during deployment",
        reason="Track error rates and latency for early detection",
        automatable=True
    ))
    
    # If low risk, give green light
    if risk_level == RiskLevel.LOW:
        actions.insert(0, SuggestedAction(
            priority="low",
            action="Safe to proceed with standard monitoring",
            reason="Low blast radius and impact detected",
            automatable=False
        ))
    
    return actions


async def save_assessment(assessment: BlastRadiusAssessResponse, request: BlastRadiusAssessRequest):
    """Save assessment to database for history tracking"""
    try:
        # First try with response_json column
        query = """
            INSERT INTO blast_radius_assessments 
            (assessment_id, cluster_id, analysis_id, target, namespace, change_type,
             risk_score, risk_level, affected_count, triggered_by, pipeline, created_at, response_json)
            VALUES (:assessment_id, :cluster_id, :analysis_id, :target, :namespace, :change_type,
                    :risk_score, :risk_level, :affected_count, :triggered_by, :pipeline, :created_at, :response_json::jsonb)
        """
        await database.execute(query, {
            "assessment_id": assessment.assessment_id,
            "cluster_id": request.cluster_id,
            "analysis_id": request.analysis_id,
            "target": request.change.target,
            "namespace": request.change.namespace,
            "change_type": request.change.type,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level.value,
            "affected_count": assessment.blast_radius.total_affected,
            "triggered_by": request.change.triggered_by,
            "pipeline": request.change.pipeline,
            "created_at": datetime.utcnow(),
            "response_json": json.dumps(assessment.dict())
        })
    except Exception as e:
        # If response_json column doesn't exist, try without it
        if "response_json" in str(e):
            try:
                query_fallback = """
                    INSERT INTO blast_radius_assessments 
                    (assessment_id, cluster_id, analysis_id, target, namespace, change_type,
                     risk_score, risk_level, affected_count, triggered_by, pipeline, created_at)
                    VALUES (:assessment_id, :cluster_id, :analysis_id, :target, :namespace, :change_type,
                            :risk_score, :risk_level, :affected_count, :triggered_by, :pipeline, :created_at)
                """
                await database.execute(query_fallback, {
                    "assessment_id": assessment.assessment_id,
                    "cluster_id": request.cluster_id,
                    "analysis_id": request.analysis_id,
                    "target": request.change.target,
                    "namespace": request.change.namespace,
                    "change_type": request.change.type,
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level.value,
                    "affected_count": assessment.blast_radius.total_affected,
                    "triggered_by": request.change.triggered_by,
                    "pipeline": request.change.pipeline,
                    "created_at": datetime.utcnow()
                })
            except Exception as e2:
                logger.warning("Failed to save assessment history (fallback)", error=str(e2))
        else:
            logger.warning("Failed to save assessment history", error=str(e))


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/blast-radius/assess", response_model=BlastRadiusAssessResponse)
async def assess_blast_radius(
    request: BlastRadiusAssessRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Assess the blast radius and risk of a proposed change.
    
    This endpoint is designed for CI/CD pipeline integration. It provides:
    - Risk score (0-100) with level classification
    - List of affected services (direct and indirect)
    - Actionable recommendations
    
    **Important**: This is advisory only. Flowfish never blocks deployments.
    The decision to proceed is always with the pipeline owner.
    
    Example Azure DevOps integration:
    ```bash
    curl -X POST "https://flowfish/api/v1/blast-radius/assess" \\
      -H "Authorization: Bearer $TOKEN" \\
      -d '{"cluster_id": 1, "change": {"target": "my-service", "type": "image_update"}}'
    ```
    """
    start_time = datetime.utcnow()
    assessment_id = f"br-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    
    logger.info(
        "Blast radius assessment requested",
        assessment_id=assessment_id,
        cluster_id=request.cluster_id,
        target=request.change.target,
        change_type=request.change.type
    )
    
    # Get analysis ID
    analysis_id = request.analysis_id
    if not analysis_id:
        analysis_id = await get_latest_analysis_id(request.cluster_id)
        if not analysis_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analysis found for this cluster. Run an analysis first."
            )
    
    # Get dependencies
    dep_data = await get_service_dependencies(
        request.cluster_id,
        analysis_id,
        request.change.target,
        request.change.namespace,
        request.same_namespace_only
    )
    
    # Identify critical services (heuristic: high request count or known patterns)
    critical_services = []
    for dep in dep_data["dependencies"]["direct"]:
        # Consider high-traffic services as critical
        if dep.get("request_count", 0) > 1000:
            critical_services.append(dep["name"])
        # Common critical service patterns
        if any(pattern in dep["name"].lower() for pattern in ["payment", "auth", "order", "checkout", "gateway"]):
            if dep["name"] not in critical_services:
                critical_services.append(dep["name"])
    
    # Check business hours
    now = datetime.utcnow()
    # Assuming UTC, business hours 9-18
    is_business_hours = 9 <= now.hour <= 18 and now.weekday() < 5
    
    # Calculate risk
    risk_score, risk_level, confidence = calculate_risk_score(
        request.change.type,
        dep_data["direct_count"],
        dep_data["indirect_count"],
        critical_services,
        is_business_hours
    )
    
    # Determine recommendation
    if risk_level == RiskLevel.CRITICAL:
        recommendation = RecommendationType.DELAY_SUGGESTED
    elif risk_level == RiskLevel.HIGH:
        recommendation = RecommendationType.REVIEW_REQUIRED
    else:
        recommendation = RecommendationType.PROCEED
    
    # Generate suggestions
    suggested_actions = generate_suggested_actions(
        risk_level,
        dep_data["direct_count"],
        dep_data["indirect_count"],
        critical_services,
        request.change.type,
        is_business_hours
    )
    
    # Organize services by impact
    services_by_impact = {
        "high": [d["name"] for d in dep_data["dependencies"]["direct"]],
        "medium": [d["name"] for d in dep_data["dependencies"]["indirect"][:10]],
        "low": [d["name"] for d in dep_data["dependencies"]["indirect"][10:20]]
    }
    
    # Build response
    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    response = BlastRadiusAssessResponse(
        assessment_id=assessment_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        risk_score=risk_score,
        risk_level=risk_level,
        confidence=confidence,
        blast_radius=BlastRadiusInfo(
            total_affected=dep_data["total"],
            direct_dependencies=dep_data["direct_count"],
            indirect_dependencies=dep_data["indirect_count"],
            critical_services=critical_services[:5],  # Top 5
            namespaces_affected=dep_data["namespaces"],
            services_by_impact=services_by_impact
        ),
        recommendation=recommendation,
        suggested_actions=suggested_actions,
        advisory_only=True,
        decision="pipeline_owner",
        assessment_duration_ms=duration_ms
    )
    
    # Save to history (async, don't wait)
    await save_assessment(response, request)
    
    logger.info(
        "Blast radius assessment completed",
        assessment_id=assessment_id,
        risk_score=risk_score,
        risk_level=risk_level.value,
        affected_count=dep_data["total"],
        duration_ms=duration_ms
    )
    
    return response


@router.post("/blast-radius/namespace", response_model=NamespaceBlastRadiusResponse)
async def assess_namespace_blast_radius(
    request: NamespaceBlastRadiusRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Assess blast radius for an entire namespace - optimized for CI/CD pipelines.
    
    This endpoint analyzes all services in a namespace and their dependencies.
    Perfect for pipeline integration where you deploy a namespace and want to
    understand the impact.
    
    Example usage:
    ```bash
    curl -X POST "https://flowfish/api/v1/blast-radius/namespace" \\
      -H "X-API-Key: fk_xxx" \\
      -d '{"cluster_id": 2, "namespace": "my-namespace"}'
    ```
    
    Returns:
    - All services in the namespace
    - Internal dependencies (within namespace)
    - External dependencies (to other namespaces)
    - Risk score and recommendations
    """
    import re
    start_time = datetime.utcnow()
    assessment_id = f"ns-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    
    logger.info(
        "Namespace blast radius assessment requested",
        assessment_id=assessment_id,
        cluster_id=request.cluster_id,
        namespace=request.namespace
    )
    
    # Get analysis ID
    analysis_id = request.analysis_id
    if not analysis_id:
        analysis_id = await get_latest_analysis_id(request.cluster_id)
        if not analysis_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analysis found for this cluster. Run an analysis first."
            )
    
    # Get full graph for the namespace
    try:
        from routers.communications import graph_query_client
        
        full_graph = await graph_query_client.get_dependency_graph(
            cluster_id=request.cluster_id,
            analysis_id=analysis_id,
            namespace=request.namespace,
            depth=2,
            search=None
        )
        
        if not full_graph:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data found for namespace {request.namespace}"
            )
        
        nodes = full_graph.get("nodes", [])
        edges = full_graph.get("edges", [])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch graph data", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dependency data"
        )
    
    # Build node map
    node_map = {n.get("id"): n for n in nodes}
    
    # Find all services in the target namespace (deduplicated)
    namespace_services = {}
    for node in nodes:
        ns = node.get("namespace", "")
        name = node.get("name", "")
        
        if ns.lower() != request.namespace.lower():
            continue
        
        # Skip IPs
        if _is_ip_address(name):
            continue
        
        # Skip infrastructure
        if _is_infrastructure_component(name, ns):
            continue
        
        # Normalize name
        normalized = _normalize_service_name(name)
        if normalized and normalized not in namespace_services:
            namespace_services[normalized] = node.get("id")
    
    services = sorted(namespace_services.keys())
    
    # Build dependency map
    dependency_map = {svc: set() for svc in services}
    external_dependency_map = {svc: set() for svc in services}
    
    # Get IDs for namespace services
    namespace_service_ids = set()
    for node in nodes:
        ns = node.get("namespace", "")
        name = node.get("name", "")
        if ns.lower() == request.namespace.lower():
            normalized = _normalize_service_name(name)
            if normalized in services:
                namespace_service_ids.add(node.get("id"))
    
    # Analyze edges
    for edge in edges:
        source_id = edge.get("source_id") or edge.get("source", {}).get("id")
        target_id = edge.get("target_id") or edge.get("target", {}).get("id")
        
        source_node = node_map.get(source_id, {})
        target_node = node_map.get(target_id, {})
        
        source_name = _normalize_service_name(source_node.get("name", ""))
        target_name = _normalize_service_name(target_node.get("name", ""))
        source_ns = source_node.get("namespace", "")
        target_ns = target_node.get("namespace", "")
        
        # Skip IPs and infrastructure
        if _is_ip_address(source_node.get("name", "")) or _is_ip_address(target_node.get("name", "")):
            continue
        if _is_infrastructure_component(source_node.get("name", ""), source_ns):
            continue
        if _is_infrastructure_component(target_node.get("name", ""), target_ns):
            continue
        
        # Source is in our namespace
        if source_ns.lower() == request.namespace.lower() and source_name in dependency_map:
            if target_ns.lower() == request.namespace.lower():
                # Internal dependency
                if target_name != source_name and target_name:
                    dependency_map[source_name].add(target_name)
            else:
                # External dependency
                if target_name and target_ns:
                    external_dependency_map[source_name].add(f"{target_ns}/{target_name}")
        
        # Target is in our namespace (incoming)
        if target_ns.lower() == request.namespace.lower() and target_name in dependency_map:
            if source_ns.lower() == request.namespace.lower():
                # Internal - already handled above
                pass
            else:
                # External service calling into our namespace
                if source_name and source_ns:
                    external_dependency_map[target_name].add(f"{source_ns}/{source_name} (incoming)")
    
    # Convert sets to sorted lists
    dependency_map_final = {k: sorted(v) for k, v in dependency_map.items()}
    external_dependency_map_final = {k: sorted(v) for k, v in external_dependency_map.items() if v}
    
    # Count dependencies
    internal_deps = sum(len(v) for v in dependency_map_final.values())
    external_deps = sum(len(v) for v in external_dependency_map_final.values())
    
    # Calculate risk score
    service_count = len(services)
    
    # Risk factors
    risk_score = 0
    risk_score += min(30, service_count * 3)  # More services = more risk
    risk_score += min(30, internal_deps * 2)  # Internal complexity
    risk_score += min(30, external_deps * 5)  # External dependencies are riskier
    
    # Business hours
    now = datetime.utcnow()
    is_business_hours = 9 <= now.hour <= 18 and now.weekday() < 5
    if is_business_hours:
        risk_score += 10
    
    risk_score = min(100, risk_score)
    
    # Determine risk level
    if risk_score >= 75:
        risk_level = RiskLevel.CRITICAL
    elif risk_score >= 50:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 25:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW
    
    # Recommendation
    if risk_level == RiskLevel.CRITICAL:
        recommendation = RecommendationType.DELAY_SUGGESTED
    elif risk_level == RiskLevel.HIGH:
        recommendation = RecommendationType.REVIEW_REQUIRED
    else:
        recommendation = RecommendationType.PROCEED
    
    # Generate actions
    actions = []
    
    if external_deps > 0:
        actions.append(SuggestedAction(
            priority="high",
            action=f"Verify {external_deps} external dependencies are stable",
            reason="External services may be affected by this deployment",
            automatable=False
        ))
    
    if service_count > 5:
        actions.append(SuggestedAction(
            priority="medium",
            action="Consider rolling deployment strategy",
            reason=f"{service_count} services in namespace - deploy incrementally",
            automatable=True
        ))
    
    if is_business_hours and risk_level != RiskLevel.LOW:
        actions.append(SuggestedAction(
            priority="medium",
            action="Schedule for low-traffic window (02:00-06:00)",
            reason="Deploying during business hours increases user impact",
            automatable=True
        ))
    
    actions.append(SuggestedAction(
        priority="low",
        action="Enable enhanced monitoring during deployment",
        reason="Track error rates and latency for early detection",
        automatable=True
    ))
    
    if risk_level == RiskLevel.LOW and not actions:
        actions.append(SuggestedAction(
            priority="low",
            action="Safe to proceed with standard monitoring",
            reason="Low risk namespace with minimal dependencies",
            automatable=False
        ))
    
    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    response = NamespaceBlastRadiusResponse(
        assessment_id=assessment_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        cluster_id=request.cluster_id,
        namespace=request.namespace,
        services=services,
        service_count=service_count,
        internal_dependencies=internal_deps,
        external_dependencies=external_deps,
        total_dependencies=internal_deps + external_deps,
        risk_score=risk_score,
        risk_level=risk_level,
        dependency_map=dependency_map_final,
        external_dependency_map=external_dependency_map_final,
        recommendation=recommendation,
        suggested_actions=actions,
        advisory_only=True,
        assessment_duration_ms=duration_ms
    )
    
    logger.info(
        "Namespace blast radius assessment completed",
        assessment_id=assessment_id,
        namespace=request.namespace,
        service_count=service_count,
        internal_deps=internal_deps,
        external_deps=external_deps,
        risk_score=risk_score,
        duration_ms=duration_ms
    )
    
    return response


@router.get("/blast-radius/assessments", response_model=List[AssessmentHistoryItem])
async def get_assessment_history(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
    current_user: dict = Depends(get_current_user)
):
    """Get history of blast radius assessments"""
    try:
        # Build query dynamically to avoid asyncpg NULL parameter issues
        if cluster_id is not None:
            query = """
                SELECT assessment_id, created_at as timestamp, cluster_id, target, namespace,
                       change_type, risk_score, risk_level, affected_count, triggered_by, pipeline
                FROM blast_radius_assessments
                WHERE cluster_id = :cluster_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            results = await database.fetch_all(query, {"cluster_id": cluster_id, "limit": limit})
        else:
            query = """
                SELECT assessment_id, created_at as timestamp, cluster_id, target, namespace,
                       change_type, risk_score, risk_level, affected_count, triggered_by, pipeline
                FROM blast_radius_assessments
                ORDER BY created_at DESC
                LIMIT :limit
            """
            results = await database.fetch_all(query, {"limit": limit})
        
        return [
            AssessmentHistoryItem(
                assessment_id=row["assessment_id"],
                timestamp=row["timestamp"].isoformat() if row["timestamp"] else "",
                cluster_id=row["cluster_id"],
                target=row["target"],
                namespace=row["namespace"],
                change_type=row["change_type"],
                risk_score=row["risk_score"],
                risk_level=row["risk_level"],
                affected_count=row["affected_count"],
                triggered_by=row["triggered_by"],
                pipeline=row["pipeline"]
            )
            for row in results
        ]
    except Exception as e:
        logger.error("Error fetching assessment history", error=str(e))
        return []


@router.get("/blast-radius/stats")
async def get_blast_radius_stats(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster"),
    days: int = Query(7, ge=1, le=90, description="Days to analyze"),
    current_user: dict = Depends(get_current_user)
):
    """Get blast radius assessment statistics"""
    try:
        since = datetime.utcnow() - timedelta(days=days)
        
        # Build query dynamically to avoid asyncpg NULL parameter issues
        if cluster_id is not None:
            query = """
                SELECT 
                    COUNT(*) as total_assessments,
                    AVG(risk_score) as avg_risk_score,
                    COUNT(CASE WHEN risk_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN risk_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN risk_level = 'medium' THEN 1 END) as medium_count,
                    COUNT(CASE WHEN risk_level = 'low' THEN 1 END) as low_count,
                    AVG(affected_count) as avg_affected_services
                FROM blast_radius_assessments
                WHERE created_at >= :since
                AND cluster_id = :cluster_id
            """
            result = await database.fetch_one(query, {"since": since, "cluster_id": cluster_id})
        else:
            query = """
                SELECT 
                    COUNT(*) as total_assessments,
                    AVG(risk_score) as avg_risk_score,
                    COUNT(CASE WHEN risk_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN risk_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN risk_level = 'medium' THEN 1 END) as medium_count,
                    COUNT(CASE WHEN risk_level = 'low' THEN 1 END) as low_count,
                    AVG(affected_count) as avg_affected_services
                FROM blast_radius_assessments
                WHERE created_at >= :since
            """
            result = await database.fetch_one(query, {"since": since})
        
        if not result:
            return {
                "period_days": days,
                "total_assessments": 0,
                "avg_risk_score": 0,
                "risk_distribution": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "avg_affected_services": 0
            }
        
        return {
            "period_days": days,
            "total_assessments": result["total_assessments"] or 0,
            "avg_risk_score": round(result["avg_risk_score"] or 0, 1),
            "risk_distribution": {
                "critical": result["critical_count"] or 0,
                "high": result["high_count"] or 0,
                "medium": result["medium_count"] or 0,
                "low": result["low_count"] or 0
            },
            "avg_affected_services": round(result["avg_affected_services"] or 0, 1)
        }
    except Exception as e:
        logger.error("Error fetching stats", error=str(e))
        return {
            "period_days": days,
            "total_assessments": 0,
            "avg_risk_score": 0,
            "risk_distribution": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "avg_affected_services": 0,
            "error": str(e)
        }


@router.get("/blast-radius/assessment/{assessment_id}")
async def get_assessment_detail(
    assessment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed assessment by ID"""
    try:
        # First try with response_json
        try:
            query = """
                SELECT response_json FROM blast_radius_assessments
                WHERE assessment_id = :assessment_id
            """
            result = await database.fetch_one(query, {"assessment_id": assessment_id})
            
            if result and result["response_json"]:
                return json.loads(result["response_json"]) if isinstance(result["response_json"], str) else result["response_json"]
        except Exception:
            pass  # Column might not exist, try fallback
        
        # Fallback: return basic assessment info
        query_fallback = """
            SELECT assessment_id, created_at as timestamp, cluster_id, target, namespace,
                   change_type, risk_score, risk_level, affected_count, triggered_by, pipeline
            FROM blast_radius_assessments
            WHERE assessment_id = :assessment_id
        """
        result = await database.fetch_one(query_fallback, {"assessment_id": assessment_id})
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment {assessment_id} not found"
            )
        
        # Build response from basic fields
        risk_level = result["risk_level"]
        return {
            "assessment_id": result["assessment_id"],
            "timestamp": result["timestamp"].isoformat() if result["timestamp"] else "",
            "risk_score": result["risk_score"],
            "risk_level": risk_level,
            "confidence": 0.5,
            "blast_radius": {
                "total_affected": result["affected_count"],
                "direct_dependencies": result["affected_count"],
                "indirect_dependencies": 0,
                "critical_services": [],
                "namespaces_affected": [result["namespace"]],
                "services_by_impact": {"high": [], "medium": [], "low": []}
            },
            "recommendation": "proceed" if risk_level == "low" else "review_required",
            "suggested_actions": [],
            "advisory_only": True,
            "decision": "pipeline_owner",
            "assessment_duration_ms": 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching assessment detail", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch assessment"
        )
