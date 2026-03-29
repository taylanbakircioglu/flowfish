"""
Simulation Router - Impact simulation and network policy endpoints
Provides APIs for simulating changes and generating network policies
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime
import structlog
import json
import csv
import io
import uuid

from utils.jwt_utils import get_current_user
from services.network_policy_service import get_network_policy_service, NetworkPolicyService
from schemas.simulation import (
    NetworkPolicyPreviewRequest,
    NetworkPolicyPreviewResponse,
    NetworkPolicyGenerateRequest,
    NetworkPolicyGenerateResponse,
    ImpactSimulationRequest,
    ImpactSimulationResponse,
    ImpactSimulationExportReport,
    ExportMetadata,
    SimulationExportData,
    ImpactSummary,
    AffectedService,
    SimulationDetails,
    NoDependencyInfo,
    ImpactLevel,
    ImpactCategory,
    DependencyType,
    ChangeType,
    ChangeTypeCharacteristics,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_service() -> NetworkPolicyService:
    """Dependency provider for NetworkPolicyService"""
    return get_network_policy_service()


# =============================================================================
# Helper Functions for Impact Simulation
# =============================================================================

def is_infrastructure_endpoint(name: str, namespace: str) -> bool:
    """
    Check if an endpoint is infrastructure (SDN, cluster network) that should be
    de-prioritized or filtered from impact reports.
    
    These are typically:
    - SDN infrastructure IPs (10.128.x.x - 10.131.x.x with random ports)
    - Cluster network IPs that are not actual services
    - Health check endpoints
    """
    import re
    
    # Infrastructure namespaces
    infra_namespaces = {
        'sdn-infrastructure', 'cluster-network', 'internal-network',
        'openshift-sdn', 'openshift-ovn-kubernetes'
    }
    
    if namespace in infra_namespaces:
        # Check if it's just an IP (not a real service name)
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if re.match(ip_pattern, name):
            return True
    
    return False


def is_real_service_dependency(dep: dict) -> bool:
    """
    Determine if a dependency is a real service vs infrastructure noise.
    
    Real services:
    - Have meaningful names (not just IPs)
    - Are in application namespaces
    - Use well-known ports
    - Have significant request counts
    
    Infrastructure noise:
    - Raw IP addresses in sdn-infrastructure namespace
    - Random high ports (ephemeral ports > 32000)
    - Very low request counts on random ports
    """
    name = dep.get("name", "")
    namespace = dep.get("namespace", "")
    port = dep.get("port", 0)
    request_count = dep.get("request_count", 0)
    
    # Always include if it's in an application namespace
    app_namespace_patterns = ['internal-', 'prod-', 'dev-', 'staging-', 'test-']
    is_app_namespace = any(namespace.startswith(p) for p in app_namespace_patterns)
    
    # Exclude infrastructure IPs with random ports
    if is_infrastructure_endpoint(name, namespace):
        # Unless it's a well-known port with traffic
        well_known_ports = {22, 80, 443, 3306, 5432, 6379, 6443, 8080, 8443, 9090, 9200, 27017}
        if port not in well_known_ports:
            return False
    
    # Include if it has a real service name (not just an IP)
    import re
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    has_real_name = not re.match(ip_pattern, name)
    
    # Include if it's a well-known port
    well_known_ports = {
        22, 25, 53, 80, 443, 3306, 5432, 5433, 6379, 6443, 
        8000, 8080, 8443, 9090, 9200, 9300, 27017, 5672, 15672
    }
    is_well_known_port = port in well_known_ports
    
    # Include if it has significant traffic
    has_significant_traffic = request_count >= 5
    
    # Decision logic
    if has_real_name:
        return True
    if is_well_known_port:
        return True
    if is_app_namespace and has_significant_traffic:
        return True
    
    return False


def extract_target_dependencies(graph_data: dict, target_name: str, target_namespace: str) -> dict:
    """
    Extract direct and indirect dependencies for a target from the full graph.
    
    Args:
        graph_data: Full graph response from graph-query service with nodes and edges
        target_name: Name of the target workload
        target_namespace: Namespace of the target workload
        
    Returns:
        Dictionary with direct_dependencies, indirect_dependencies, node_matches
    """
    if not graph_data:
        return {
            "direct_dependencies": [],
            "indirect_dependencies": [],
            "node_matches": 0,
            "has_external_connections": False,
            "confidence": 0.0
        }
    
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    
    # Build node lookup
    node_map = {n.get("id"): n for n in nodes}
    
    # Extract actual workload name from target_name
    # target_name can be in format: "{kind}-{namespace}-{name}" (e.g., "deployment-flowfish-prod-frontend")
    # or just the workload name (e.g., "frontend")
    target_name_lower = target_name.lower()
    target_ns_lower = target_namespace.lower()
    
    # Try to extract the actual workload name if target_name is in kind-namespace-name format
    workload_name = target_name_lower
    kind_prefixes = ['deployment-', 'statefulset-', 'daemonset-', 'replicaset-', 'pod-', 'service-']
    for prefix in kind_prefixes:
        if target_name_lower.startswith(prefix):
            # Remove kind prefix
            remaining = target_name_lower[len(prefix):]
            # Check if namespace is also in the name
            if remaining.startswith(target_ns_lower + '-'):
                workload_name = remaining[len(target_ns_lower) + 1:]
            elif '-' in remaining:
                # Try to find namespace in the remaining string
                parts = remaining.split('-')
                # Find where namespace ends and workload name begins
                for i in range(len(parts)):
                    potential_ns = '-'.join(parts[:i+1])
                    if potential_ns == target_ns_lower:
                        workload_name = '-'.join(parts[i+1:])
                        break
            break
    
    logger.info(f"Target matching: original='{target_name}', extracted_workload='{workload_name}', namespace='{target_namespace}'")
    
    # Find target node(s) - match by name containing target_name and namespace
    target_ids = set()
    for node in nodes:
        node_name = node.get("name", "").lower()
        node_ns = node.get("namespace", "").lower()
        
        # Check namespace match first
        ns_match = (target_ns_lower == node_ns or target_ns_lower in node_ns or node_ns in target_ns_lower)
        if not ns_match:
            continue
        
        # Match strategies:
        # 1. Exact workload name match (node starts with workload name)
        # 2. Original target_name in node_name or vice versa
        # 3. Workload name in node_name
        if node_name.startswith(workload_name + '-') or node_name == workload_name:
            target_ids.add(node.get("id"))
        elif target_name_lower in node_name or node_name in target_name_lower:
            target_ids.add(node.get("id"))
        elif workload_name in node_name:
            target_ids.add(node.get("id"))
    
    if not target_ids:
        # Fallback: try matching just by workload name across all namespaces
        for node in nodes:
            node_name = node.get("name", "").lower()
            if node_name.startswith(workload_name + '-') or workload_name in node_name:
                target_ids.add(node.get("id"))
    
    logger.info(f"Found {len(target_ids)} target nodes for {target_namespace}/{target_name} (workload: {workload_name})")
    
    # Find direct dependencies (1-hop)
    direct_deps = []
    direct_ids = set()
    
    for edge in edges:
        source_id = edge.get("source_id") or edge.get("source", {}).get("id")
        target_id = edge.get("target_id") or edge.get("target", {}).get("id")
        
        # Check if this edge connects to target
        if source_id in target_ids and target_id not in target_ids:
            dep_node = node_map.get(target_id, {})
            direct_deps.append({
                "id": target_id,
                "name": dep_node.get("name", "unknown"),
                "namespace": dep_node.get("namespace", "default"),
                "kind": dep_node.get("kind", "Pod"),
                "port": edge.get("port", 0),
                "protocol": edge.get("protocol", "TCP"),
                "request_count": edge.get("request_count", 0),
                "direction": "outgoing"
            })
            direct_ids.add(target_id)
        elif target_id in target_ids and source_id not in target_ids:
            dep_node = node_map.get(source_id, {})
            direct_deps.append({
                "id": source_id,
                "name": dep_node.get("name", "unknown"),
                "namespace": dep_node.get("namespace", "default"),
                "kind": dep_node.get("kind", "Pod"),
                "port": edge.get("port", 0),
                "protocol": edge.get("protocol", "TCP"),
                "request_count": edge.get("request_count", 0),
                "direction": "incoming"
            })
            direct_ids.add(source_id)
    
    # Find indirect dependencies (2-hop)
    indirect_deps = []
    
    for edge in edges:
        source_id = edge.get("source_id") or edge.get("source", {}).get("id")
        target_id = edge.get("target_id") or edge.get("target", {}).get("id")
        
        # Check if this edge connects from a direct dependency to something else
        if source_id in direct_ids and target_id not in target_ids and target_id not in direct_ids:
            dep_node = node_map.get(target_id, {})
            indirect_deps.append({
                "id": target_id,
                "name": dep_node.get("name", "unknown"),
                "namespace": dep_node.get("namespace", "default"),
                "kind": dep_node.get("kind", "Pod"),
                "port": edge.get("port", 0),
                "protocol": edge.get("protocol", "TCP"),
                "request_count": edge.get("request_count", 0)
            })
        elif target_id in direct_ids and source_id not in target_ids and source_id not in direct_ids:
            dep_node = node_map.get(source_id, {})
            indirect_deps.append({
                "id": source_id,
                "name": dep_node.get("name", "unknown"),
                "namespace": dep_node.get("namespace", "default"),
                "kind": dep_node.get("kind", "Pod"),
                "port": edge.get("port", 0),
                "protocol": edge.get("protocol", "TCP"),
                "request_count": edge.get("request_count", 0)
            })
    
    # Deduplicate and filter infrastructure noise
    seen_direct = set()
    unique_direct = []
    filtered_infra_count = 0
    
    for d in direct_deps:
        key = f"{d['namespace']}/{d['name']}"
        if key not in seen_direct:
            seen_direct.add(key)
            # Filter out infrastructure noise but keep real services
            if is_real_service_dependency(d):
                unique_direct.append(d)
            else:
                filtered_infra_count += 1
    
    seen_indirect = set()
    unique_indirect = []
    
    for d in indirect_deps:
        key = f"{d['namespace']}/{d['name']}"
        if key not in seen_indirect and key not in seen_direct:
            seen_indirect.add(key)
            if is_real_service_dependency(d):
                unique_indirect.append(d)
            else:
                filtered_infra_count += 1
    
    if filtered_infra_count > 0:
        logger.info(f"Filtered {filtered_infra_count} infrastructure endpoints from impact report")
    
    # Check for external connections
    has_external = any(
        d.get("namespace") in ["external"] or "." in d.get("name", "")
        for d in unique_direct + unique_indirect
    )
    
    # Sort by importance: real services first, then by request count
    unique_direct.sort(key=lambda x: (-x.get("request_count", 0)))
    unique_indirect.sort(key=lambda x: (-x.get("request_count", 0)))
    
    return {
        "direct_dependencies": unique_direct,
        "indirect_dependencies": unique_indirect,
        "node_matches": len(target_ids),
        "has_external_connections": has_external,
        "confidence": min(1.0, 0.5 + (len(unique_direct) * 0.1)) if unique_direct else 0.3,
        "filtered_infrastructure_count": filtered_infra_count
    }


def classify_endpoint_kind(name: str, namespace: str, original_kind: str) -> str:
    """
    Properly classify the kind of an endpoint based on its name and namespace.
    
    Returns:
        - "Pod" for actual Kubernetes pods (e.g., backend-7686dccc6b-x8bqm)
        - "Service" for Kubernetes services
        - "ExternalIP" for external IP addresses (10.180.x.x, 192.168.x.x)
        - "ClusterIP" for cluster-internal IPs (10.128.x.x, 10.129.x.x, 10.130.x.x, 10.131.x.x)
        - "ExternalDNS" for external DNS names (*.bank, api.*, etc.)
        - "ClusterService" for internal cluster services (*.svc.cluster.local)
        - "Localhost" for localhost
    """
    import re
    
    # Check for localhost first
    if name.lower() == 'localhost' or name == '127.0.0.1':
        return "Localhost"
    
    # Check if it's an IP address
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ip_pattern, name):
        # Parse IP to determine type
        parts = name.split('.')
        first_octet = int(parts[0])
        second_octet = int(parts[1])
        
        # Kubernetes pod network IPs (typically 10.128.x.x - 10.131.x.x in OpenShift)
        if first_octet == 10 and 128 <= second_octet <= 131:
            # These are pod IPs within the cluster
            if namespace in ['sdn-infrastructure']:
                return "SDN-IP"
            return "ClusterIP"
        
        # Service network IPs (typically 10.96.x.x or 10.106.x.x)
        if first_octet == 10 and (96 <= second_octet <= 111 or 104 <= second_octet <= 111):
            return "ServiceIP"
        
        # External/infrastructure IPs
        if first_octet == 10 and second_octet == 180:
            return "ExternalIP"
        if first_octet == 192 and second_octet == 168:
            return "ExternalIP"
        
        # Default IP classification based on namespace
        if namespace in ['external', 'sdn-infrastructure', 'internal-network', 'cluster-network']:
            return "ExternalIP"
        
        return "ClusterIP"
    
    # Check if it's a DNS-style name with IP prefix (e.g., 10-128-22-163.harbor-core...)
    ip_dns_pattern = r'^\d+-\d+-\d+-\d+\.'
    if re.match(ip_dns_pattern, name):
        if '.svc.cluster.local' in name:
            return "ClusterService"
        return "ClusterIP"
    
    # Check if it's a cluster service DNS name
    if '.svc.cluster.local' in name:
        return "ClusterService"
    
    # Check if it's an external DNS name
    if '.' in name and name.count('.') >= 2:
        # Common external DNS patterns
        if any(ext in name.lower() for ext in ['.bank', '.com', '.net', '.org', '.io', '.local']):
            if '.svc.cluster.local' not in name:
                return "ExternalDNS"
    
    # Check if it looks like a pod name (has random suffix like -7686dccc6b-x8bqm)
    pod_pattern = r'-[a-z0-9]{6,10}-[a-z0-9]{5}$'
    if re.search(pod_pattern, name):
        return "Pod"
    
    # Check if it looks like a StatefulSet pod (ends with -0, -1, etc.)
    statefulset_pattern = r'-\d+$'
    if re.search(statefulset_pattern, name):
        return "Pod"
    
    # Default to original kind or Pod
    return original_kind if original_kind else "Pod"


def calculate_dynamic_risk_score(
    dependency_type: str,
    request_count: int,
    is_critical_namespace: bool,
    port: int,
    change_type: ChangeType
) -> tuple:
    """
    Calculate a dynamic risk score based on multiple factors.
    
    Returns:
        tuple: (risk_score: float, risk_factors: list[str])
    
    Factors:
    - Dependency type (direct = higher risk)
    - Request count (more traffic = higher risk)
    - Critical namespace (system namespaces = higher risk)
    - Port (well-known ports = higher risk)
    - Change type severity
    """
    import math
    
    base_score = 0.3
    risk_factors = []
    
    # Dependency type factor
    if dependency_type == "direct":
        base_score += 0.3
        risk_factors.append("Direct dependency")
    else:
        base_score += 0.1
    
    # Request count factor (logarithmic scale)
    if request_count > 0:
        traffic_factor = min(0.2, math.log10(request_count + 1) * 0.05)
        base_score += traffic_factor
        if request_count >= 100:
            risk_factors.append(f"High traffic ({request_count} requests)")
        elif request_count >= 10:
            risk_factors.append(f"Moderate traffic ({request_count} requests)")
    
    # Critical namespace factor
    if is_critical_namespace:
        base_score += 0.15
        risk_factors.append("System namespace")
    
    # Well-known port factor
    critical_ports = {
        443: "HTTPS",
        6443: "Kubernetes API",
        8443: "Secure HTTP",
        53: "DNS",
        5432: "PostgreSQL",
        3306: "MySQL",
        6379: "Redis",
        9090: "Prometheus",
        9091: "Prometheus Pushgateway",
        8080: "HTTP Alt",
        8000: "HTTP Alt",
        3000: "Dev Server",
    }
    if port in critical_ports:
        base_score += 0.1
        risk_factors.append(f"Critical port ({critical_ports[port]})")
    
    # Change type severity factor
    severity_map = {
        ChangeType.DELETE: (0.15, "Destructive change"),
        ChangeType.SCALE_DOWN: (0.12, "Service unavailability"),
        ChangeType.NETWORK_ISOLATE: (0.12, "Network isolation"),
        ChangeType.NETWORK_POLICY_APPLY: (0.1, "Traffic filtering"),
        ChangeType.PORT_CHANGE: (0.1, "Port configuration change"),
        ChangeType.IMAGE_UPDATE: (0.08, "Image update"),
        ChangeType.CONFIG_CHANGE: (0.05, "Configuration change"),
        ChangeType.RESOURCE_CHANGE: (0.05, "Resource adjustment"),
        ChangeType.NETWORK_POLICY_REMOVE: (0.02, "Policy removal"),
    }
    
    if change_type in severity_map:
        score_add, factor = severity_map[change_type]
        base_score += score_add
        if score_add >= 0.1:
            risk_factors.append(factor)
    
    final_score = min(1.0, max(0.0, round(base_score, 2)))
    
    return final_score, risk_factors


def generate_specific_recommendation(
    endpoint_kind: str,
    namespace: str,
    impact_level: ImpactLevel,
    change_type: ChangeType,
    request_count: int
) -> str:
    """
    Generate specific recommendations based on endpoint characteristics.
    """
    recommendations = []
    
    # Kind-specific recommendations
    if endpoint_kind == "ExternalIP":
        recommendations.append("Verify external IP connectivity requirements")
    elif endpoint_kind == "ExternalDNS":
        recommendations.append("Check DNS resolution and external service availability")
    elif endpoint_kind == "ClusterService":
        recommendations.append("Review internal service mesh configuration")
    elif endpoint_kind == "Localhost":
        recommendations.append("Localhost connections typically indicate local processes")
    
    # Namespace-specific recommendations
    if 'openshift-' in namespace:
        recommendations.append("⚠️ OpenShift system component - proceed with caution")
    elif 'kube-system' in namespace:
        recommendations.append("⚠️ Kubernetes system component - may affect cluster stability")
    elif namespace == 'default':
        recommendations.append("Consider moving workloads out of default namespace")
    
    # Change-type specific recommendations
    change_recommendations = {
        ChangeType.DELETE: "Ensure graceful shutdown and data backup before deletion",
        ChangeType.SCALE_DOWN: "Verify HPA/VPA policies and set up alerts for scale-up",
        ChangeType.NETWORK_ISOLATE: "Test network policy in audit mode first",
        ChangeType.NETWORK_POLICY_APPLY: "Validate policy rules against observed traffic patterns",
        ChangeType.PORT_CHANGE: "Update all client configurations and service discovery",
        ChangeType.CONFIG_CHANGE: "Test configuration changes in staging environment",
        ChangeType.IMAGE_UPDATE: "Verify image compatibility and rollback strategy",
        ChangeType.RESOURCE_CHANGE: "Monitor resource utilization after change",
        ChangeType.NETWORK_POLICY_REMOVE: "Review security implications of removing policy",
    }
    if change_type in change_recommendations:
        recommendations.append(change_recommendations[change_type])
    
    # Traffic-based recommendations
    if request_count > 100:
        recommendations.append(f"High traffic endpoint ({request_count} requests) - consider gradual rollout")
    elif request_count == 0:
        recommendations.append("No recent traffic observed - verify if endpoint is still in use")
    
    # Impact-level recommendations
    if impact_level == ImpactLevel.HIGH:
        recommendations.insert(0, "🔴 HIGH IMPACT: Coordinate with dependent teams before proceeding")
    elif impact_level == ImpactLevel.MEDIUM:
        recommendations.insert(0, "🟠 Monitor for cascading effects after change")
    
    return " | ".join(recommendations[:3]) if recommendations else "Review impact carefully before proceeding"


def deduplicate_services(services: list) -> list:
    """
    Remove duplicate services based on normalized endpoint identification.
    Keeps the entry with more information (e.g., pod name over IP, pod over DNS).
    
    Priority order (highest to lowest):
    1. Pod names (e.g., backend-7686dccc6b-x8bqm) - priority 5
    2. StatefulSet pods (e.g., postgresql-0) - priority 5
    3. Service names (e.g., backend) - priority 4
    4. External DNS (e.g., api.external-service.com) - priority 3
    5. DNS names with IP prefix (e.g., 10-128-22-163.harbor-core...) - priority 2
    6. IP addresses (e.g., 10.128.16.2) - priority 1
    """
    import re
    
    def get_name_priority(name: str) -> int:
        """Return priority score - higher is better"""
        # IP address - lowest priority
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', name):
            return 1
        # DNS-style with IP prefix (e.g., 10-128-22-163.harbor-core...)
        if re.match(r'^\d+-\d+-\d+-\d+\.', name):
            return 2
        # External DNS (e.g., api.external-service.com)
        if '.' in name and name.count('.') >= 2:
            return 3
        # Pod name with hash suffix
        if re.search(r'-[a-z0-9]{5,10}-[a-z0-9]{5}$', name):
            return 5
        # StatefulSet pod (e.g., postgresql-0)
        if re.search(r'-\d+$', name):
            return 5
        # Service name (no suffix)
        return 4
    
    def extract_service_identifier(name: str, namespace: str, port: int) -> str:
        """Extract the base service name for deduplication"""
        import re
        
        # Handle DNS-style names like 10-128-22-163.harbor-core.prod-harbor-ha.svc.cluster.local
        if '.svc.cluster.local' in name:
            parts = name.split('.')
            if len(parts) >= 2:
                # Extract service name and namespace from DNS
                service_name = parts[1]
                dns_namespace = parts[2] if len(parts) > 2 else namespace
                return f"svc:{service_name}:{dns_namespace}:{port}"
        
        # Handle external DNS - keep unique by hostname
        if '.' in name and any(ext in name.lower() for ext in ['.bank', '.com', '.net', '.org', '.io']):
            return f"dns:{name}:{port}"
        
        # Handle IP addresses
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', name):
            # For cluster IPs (10.128-131.x.x), try to group by service
            parts = name.split('.')
            if parts[0] == '10' and 128 <= int(parts[1]) <= 131:
                # These are likely pod IPs - group by namespace and port
                # They'll be deduplicated with their pod names
                return f"podip:{namespace}:{port}"
            # External IPs - keep as unique
            return f"extip:{name}:{port}"
        
        # Handle DNS with IP prefix (e.g., 10-128-22-163.harbor-core...)
        if re.match(r'^\d+-\d+-\d+-\d+\.', name):
            parts = name.split('.')
            if len(parts) >= 2:
                service_name = parts[1]
                dns_namespace = parts[2] if len(parts) > 2 else namespace
                return f"svc:{service_name}:{dns_namespace}:{port}"
        
        # Handle localhost
        if name.lower() == 'localhost':
            return f"localhost:{port}"
        
        # Handle pod names - extract base service name
        base_name = re.sub(r'-[a-z0-9]{5,10}-[a-z0-9]{5}$', '', name)
        base_name = re.sub(r'-\d+$', '', base_name)  # Remove StatefulSet index
        
        return f"pod:{base_name}:{namespace}:{port}"
    
    seen = {}
    
    for svc in services:
        name = svc.get("name", "")
        namespace = svc.get("namespace", "")
        port = svc.get("connection_details", {}).get("port", 0)
        
        # Create a normalized key
        service_id = extract_service_identifier(name, namespace, port)
        
        current_priority = get_name_priority(name)
        
        if service_id in seen:
            existing = seen[service_id]
            existing_priority = get_name_priority(existing.get("name", ""))
            
            # Keep the one with higher priority (better name)
            if current_priority > existing_priority:
                seen[service_id] = svc
            # If same priority, keep the one with more request count
            elif current_priority == existing_priority:
                current_count = svc.get("connection_details", {}).get("request_count", 0)
                existing_count = existing.get("connection_details", {}).get("request_count", 0)
                if current_count > existing_count:
                    seen[service_id] = svc
        else:
            seen[service_id] = svc
    
    return list(seen.values())


def filter_indirect_dependencies(
    indirect_deps: list,
    direct_deps: list,
    change_type: ChangeType,
    max_indirect: int = 50
) -> list:
    """
    Filter and limit indirect dependencies to meaningful ones.
    
    Rules:
    - Exclude infrastructure services (ingress, DNS, monitoring) unless directly relevant
    - Remove duplicate entries (same service via different paths)
    - Limit total indirect dependencies to max_indirect
    - Prioritize by request count and criticality
    """
    import re
    
    # Get direct dependency names for reference
    direct_names = {d.get("name") for d in direct_deps}
    
    # Infrastructure namespaces to de-prioritize for most changes
    infra_namespaces = [
        'openshift-ingress', 'openshift-ingress-canary', 'openshift-dns',
        'openshift-monitoring', 'openshift-network-diagnostics',
        'kube-system', 'openshift-operators', 'openshift-authentication',
        'openshift-console', 'openshift-ovn-kubernetes', 'openshift-migration'
    ]
    
    # For network policy changes, infrastructure IS relevant
    if change_type in [ChangeType.NETWORK_ISOLATE, ChangeType.NETWORK_POLICY_APPLY]:
        infra_namespaces = []  # Don't filter infrastructure
    
    # First pass: deduplicate by base service name
    seen_services = {}
    
    def get_base_service_name(name: str, namespace: str) -> str:
        """Extract base service name for deduplication"""
        # Handle DNS-style names
        if '.svc.cluster.local' in name:
            parts = name.split('.')
            return f"{parts[1]}:{parts[2] if len(parts) > 2 else namespace}"
        
        # Handle IP-prefixed DNS
        if re.match(r'^\d+-\d+-\d+-\d+\.', name):
            parts = name.split('.')
            if len(parts) >= 2:
                return f"{parts[1]}:{parts[2] if len(parts) > 2 else namespace}"
        
        # Handle IP addresses - group by namespace
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', name):
            return f"ip:{namespace}"
        
        # Handle pod names
        base = re.sub(r'-[a-z0-9]{5,10}-[a-z0-9]{5}$', '', name)
        base = re.sub(r'-\d+$', '', base)
        return f"{base}:{namespace}"
    
    for dep in indirect_deps:
        name = dep.get("name", "")
        namespace = dep.get("namespace", "")
        
        # Skip if it's actually a direct dependency
        if name in direct_names:
            continue
        
        # Skip localhost and loopback
        if name.lower() == 'localhost' or name == '127.0.0.1':
            continue
        
        base_key = get_base_service_name(name, namespace)
        
        if base_key in seen_services:
            # Keep the one with higher request count
            existing = seen_services[base_key]
            if dep.get("request_count", 0) > existing.get("request_count", 0):
                seen_services[base_key] = dep
        else:
            seen_services[base_key] = dep
    
    # Second pass: separate infrastructure from application dependencies
    filtered = []
    infra_deps = []
    
    for dep in seen_services.values():
        namespace = dep.get("namespace", "")
        is_infra = any(ns in namespace for ns in infra_namespaces)
        
        if is_infra:
            infra_deps.append(dep)
        else:
            filtered.append(dep)
    
    # Sort by request count (descending) to prioritize high-traffic dependencies
    filtered.sort(key=lambda x: x.get("request_count", 0), reverse=True)
    
    # Limit application dependencies
    app_limit = min(len(filtered), max_indirect - 5)  # Reserve 5 slots for infra
    result = filtered[:app_limit]
    
    # Add a few infrastructure deps if we have room
    remaining_slots = max_indirect - len(result)
    if remaining_slots > 0 and infra_deps:
        infra_deps.sort(key=lambda x: x.get("request_count", 0), reverse=True)
        result.extend(infra_deps[:remaining_slots])
    
    return result


# =============================================================================
# Network Policy Endpoints
# =============================================================================

@router.post(
    "/network-policy/generate",
    response_model=NetworkPolicyGenerateResponse,
    summary="Generate Network Policy",
    description="Generate a Kubernetes NetworkPolicy based on observed traffic patterns. "
                "Creates a least-privilege policy that allows only observed connections."
)
async def generate_network_policy(
    request: NetworkPolicyGenerateRequest,
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """
    Generate a NetworkPolicy YAML based on observed traffic.
    
    The generated policy will:
    - Allow only traffic that was observed during the analysis period
    - Include DNS egress rules by default
    - Use namespace and pod selectors for internal traffic
    - Use IP blocks for external traffic
    """
    try:
        logger.info(
            "Network policy generation requested",
            user=current_user.get("username"),
            cluster_id=request.cluster_id,
            target=f"{request.target_namespace}/{request.target_workload}"
        )
        
        response = await service.generate_network_policy(request)
        
        logger.info(
            "Network policy generated successfully",
            policy_name=response.policy_name,
            ingress_sources=response.observed_ingress_sources,
            egress_destinations=response.observed_egress_destinations
        )
        
        return response
        
    except Exception as e:
        logger.error("Network policy generation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate network policy: {str(e)}"
        )


@router.post(
    "/network-policy/preview",
    response_model=NetworkPolicyPreviewResponse,
    summary="Preview Network Policy Impact",
    description="Preview which existing connections would be affected by applying a network policy."
)
async def preview_network_policy_impact(
    request: NetworkPolicyPreviewRequest,
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """
    Preview the impact of applying a network policy.
    
    Returns:
    - List of connections that would be blocked
    - List of connections that would be allowed
    - Warnings and recommendations
    """
    try:
        logger.info(
            "Network policy preview requested",
            user=current_user.get("username"),
            cluster_id=request.cluster_id,
            target=f"{request.target_namespace}/{request.target_workload}"
        )
        
        response = await service.preview_network_policy_impact(request)
        
        logger.info(
            "Network policy preview completed",
            policy_name=response.policy_name,
            blocked=response.blocked_connections,
            allowed=response.allowed_connections
        )
        
        return response
        
    except Exception as e:
        logger.error("Network policy preview failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview network policy: {str(e)}"
        )


# =============================================================================
# Impact Simulation Endpoints
# =============================================================================

@router.post(
    "/impact",
    response_model=ImpactSimulationResponse,
    summary="Run Impact Simulation",
    description="Simulate the impact of a change on the target resource and its dependencies."
)
async def run_impact_simulation(
    request: ImpactSimulationRequest,
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """
    Run an impact simulation for a proposed change.
    
    Analyzes:
    - Direct dependencies (1-hop)
    - Indirect dependencies (2-hop)
    - Impact severity for each affected service
    - Recommendations for safe change execution
    """
    try:
        logger.info(
            "Impact simulation requested",
            user=current_user.get("username"),
            cluster_id=request.cluster_id,
            analysis_id=request.analysis_id,
            target=f"{request.target_namespace}/{request.target_name}",
            change_type=request.change_type.value
        )
        
        # ========== DEBUG: IMPACT SIMULATION START ==========
        logger.warning("IMPACT_SIM_START",
            user=current_user.get('username'),
            cluster_id=request.cluster_id,
            analysis_id=request.analysis_id,
            target=f"{request.target_namespace}/{request.target_name}",
            target_kind=request.target_kind,
            change_type=request.change_type.value
        )
        
        # Use graph-query service (same as communications endpoint) for dependency data
        # This ensures we use the same data source that powers the visualization
        from routers.communications import graph_query_client
        
        # Get full dependency graph from graph-query service
        logger.warning("IMPACT_SIM_GRAPH_FETCH: fetching graph from service")
        full_graph = await graph_query_client.get_dependency_graph(
            cluster_id=request.cluster_id,
            analysis_id=request.analysis_id,
            namespace=None,  # Get all namespaces to find dependencies
            depth=2,
            search=request.target_name  # Filter to target and its connections
        )
        
        # DEBUG: Log full graph summary
        nodes_count = len(full_graph.get("nodes", [])) if full_graph else 0
        edges_count = len(full_graph.get("edges", [])) if full_graph else 0
        
        namespaces_in_graph = []
        sample_nodes = []
        if full_graph and full_graph.get("nodes"):
            namespaces_in_graph = sorted(set(n.get("namespace", "unknown") for n in full_graph["nodes"]))
            sample_nodes = [f"{n.get('namespace', '?')}/{n.get('name', '?')}" for n in full_graph["nodes"][:10]]
        
        logger.warning("IMPACT_SIM_GRAPH_RESPONSE: graph data received",
            total_nodes=nodes_count,
            total_edges=edges_count,
            namespaces=namespaces_in_graph,
            sample_nodes=sample_nodes
        )
        
        # Extract dependencies for the target from the full graph
        graph_data = extract_target_dependencies(
            full_graph,
            request.target_name,
            request.target_namespace
        )
        
        # DEBUG: Log extracted dependencies
        direct_deps_summary = [
            f"{d.get('namespace', '?')}/{d.get('name', '?')}:{d.get('port', '?')}"
            for d in graph_data.get("direct_dependencies", [])[:10]
        ]
        indirect_deps_summary = [
            f"{d.get('namespace', '?')}/{d.get('name', '?')}:{d.get('port', '?')}"
            for d in graph_data.get("indirect_dependencies", [])[:5]
        ]
        
        logger.warning("IMPACT_SIM_DEPENDENCIES: dependencies extracted",
            target=f"{request.target_namespace}/{request.target_name}",
            node_matches=graph_data.get('node_matches', 0),
            direct_count=len(graph_data.get('direct_dependencies', [])),
            indirect_count=len(graph_data.get('indirect_dependencies', [])),
            has_external=graph_data.get('has_external_connections', False),
            filtered_infra=graph_data.get('filtered_infrastructure_count', 0),
            direct_deps=direct_deps_summary,
            indirect_deps=indirect_deps_summary
        )
        
        logger.info(
            "Graph data extracted",
            direct_count=len(graph_data.get("direct_dependencies", [])),
            indirect_count=len(graph_data.get("indirect_dependencies", [])),
            node_matches=graph_data.get("node_matches", 0)
        )
        
        # Get change type characteristics
        change_chars = ChangeTypeCharacteristics.get(request.change_type)
        
        # Calculate affected services with change-type aware impact
        affected_services = []
        direct_deps = graph_data.get("direct_dependencies", [])
        indirect_deps_raw = graph_data.get("indirect_dependencies", [])
        
        # Filter and limit indirect dependencies to prevent explosion
        indirect_deps = filter_indirect_dependencies(
            indirect_deps_raw, 
            direct_deps, 
            request.change_type,
            max_indirect=50  # Reasonable limit
        )
        
        # Process direct dependencies
        for dep in direct_deps:
            dep_name = dep.get("name", "unknown")
            dep_namespace = dep.get("namespace", "default")
            dep_port = dep.get("port", 0)
            request_count = dep.get("request_count", 0)
            
            # Properly classify the endpoint kind
            original_kind = dep.get("kind", "Pod")
            endpoint_kind = classify_endpoint_kind(dep_name, dep_namespace, original_kind)
            
            # Use new change-type aware calculation
            impact, impact_category, impact_desc, risk_factors = service.calculate_impact_for_change_type(
                request.change_type,
                DependencyType.DIRECT,
                request_count,
                dep.get("is_critical", False)
            )
            
            # Skip if this change type doesn't affect direct dependencies
            if impact == ImpactLevel.NONE and not change_chars["affects_direct"]:
                continue
            
            # Downgrade impact for infrastructure endpoints (SDN-IP, ExternalIP with random ports)
            is_infra_endpoint = endpoint_kind in ['SDN-IP', 'ServiceIP'] or \
                (endpoint_kind == 'ExternalIP' and dep_port > 32000)
            
            if is_infra_endpoint and impact == ImpactLevel.HIGH:
                # Infrastructure endpoints are less critical for application impact
                impact = ImpactLevel.MEDIUM
                impact_desc = f"Infrastructure connectivity may be affected. {impact_desc}"
            
            # Calculate dynamic risk score and risk factors
            risk_score, calculated_risk_factors = calculate_dynamic_risk_score(
                "direct",
                request_count,
                'openshift-' in dep_namespace or 'kube-system' in dep_namespace,
                dep_port,
                request.change_type
            )
            
            # Reduce risk score for infrastructure endpoints
            if is_infra_endpoint:
                risk_score = min(risk_score, 0.5)
            # Merge calculated risk factors with change-type risk factors
            all_risk_factors = list(set(risk_factors + calculated_risk_factors))
            
            # Generate specific recommendation
            recommendation = generate_specific_recommendation(
                endpoint_kind,
                dep_namespace,
                impact,
                request.change_type,
                request_count
            )
            
            affected_services.append(AffectedService(
                id=dep.get("id", str(uuid.uuid4())),
                name=dep_name,
                namespace=dep_namespace,
                kind=endpoint_kind,
                impact=impact,
                impact_category=impact_category,
                impact_description=impact_desc,
                dependency=DependencyType.DIRECT,
                recommendation=recommendation,
                connection_details={
                    "protocol": dep.get("protocol", "TCP"),
                    "port": dep_port,
                    "request_count": request_count,
                    "last_seen": dep.get("last_seen")
                },
                risk_score=risk_score,
                risk_factors=all_risk_factors,
                recovery_info={
                    "recovery_time": change_chars["recovery_time"],
                    "reversible": change_chars["reversible"]
                }
            ))
        
        # Process indirect dependencies
        for dep in indirect_deps:
            dep_name = dep.get("name", "unknown")
            dep_namespace = dep.get("namespace", "default")
            dep_port = dep.get("port", 0)
            request_count = dep.get("request_count", 0)
            hop_distance = dep.get("hop_distance", 2)
            
            # Properly classify the endpoint kind
            original_kind = dep.get("kind", "Pod")
            endpoint_kind = classify_endpoint_kind(dep_name, dep_namespace, original_kind)
            
            # Use new change-type aware calculation
            impact, impact_category, impact_desc, risk_factors = service.calculate_impact_for_change_type(
                request.change_type,
                DependencyType.INDIRECT,
                request_count,
                False
            )
            
            # Skip if this change type doesn't affect indirect dependencies
            if impact == ImpactLevel.NONE and not change_chars["affects_indirect"]:
                continue
            
            # Downgrade impact for infrastructure endpoints
            is_infra_endpoint = endpoint_kind in ['SDN-IP', 'ServiceIP'] or \
                (endpoint_kind == 'ExternalIP' and dep_port > 32000)
            
            if is_infra_endpoint and impact in [ImpactLevel.HIGH, ImpactLevel.MEDIUM]:
                impact = ImpactLevel.LOW
                impact_desc = f"Infrastructure connectivity may be affected. {impact_desc}"
            
            # Calculate dynamic risk score (reduced for indirect)
            risk_score, calculated_risk_factors = calculate_dynamic_risk_score(
                "indirect",
                request_count,
                'openshift-' in dep_namespace or 'kube-system' in dep_namespace,
                dep_port,
                request.change_type
            )
            risk_score = risk_score * 0.7  # 30% reduction for indirect
            
            # Further reduce risk score for infrastructure endpoints
            if is_infra_endpoint:
                risk_score = min(risk_score, 0.3)
            # Merge calculated risk factors with change-type risk factors
            all_risk_factors = list(set(risk_factors + calculated_risk_factors))
            
            # Generate specific recommendation
            recommendation = generate_specific_recommendation(
                endpoint_kind,
                dep_namespace,
                impact,
                request.change_type,
                request_count
            )
            
            affected_services.append(AffectedService(
                id=dep.get("id", str(uuid.uuid4())),
                name=dep_name,
                namespace=dep_namespace,
                kind=endpoint_kind,
                impact=impact,
                impact_category=impact_category,
                impact_description=impact_desc,
                dependency=DependencyType.INDIRECT,
                recommendation=recommendation,
                connection_details={
                    "protocol": dep.get("protocol", "TCP"),
                    "port": dep_port,
                    "request_count": request_count,
                    "hop_distance": hop_distance
                },
                risk_score=round(risk_score, 2),
                risk_factors=all_risk_factors,
                recovery_info={
                    "recovery_time": change_chars["recovery_time"],
                    "reversible": change_chars["reversible"]
                }
            ))
        
        # Deduplicate services (remove duplicate IPs that map to same service)
        affected_services_dicts = [
            {
                "id": s.id,
                "name": s.name,
                "namespace": s.namespace,
                "kind": s.kind,
                "impact": s.impact,
                "impact_category": s.impact_category,
                "impact_description": s.impact_description,
                "dependency": s.dependency,
                "recommendation": s.recommendation,
                "connection_details": s.connection_details,
                "risk_score": s.risk_score,
                "risk_factors": s.risk_factors,
                "recovery_info": s.recovery_info
            }
            for s in affected_services
        ]
        deduped_dicts = deduplicate_services(affected_services_dicts)
        
        # Rebuild affected_services from deduplicated list
        affected_services = [
            AffectedService(
                id=d["id"],
                name=d["name"],
                namespace=d["namespace"],
                kind=d["kind"],
                impact=d["impact"],
                impact_category=d["impact_category"],
                impact_description=d["impact_description"],
                dependency=d["dependency"],
                recommendation=d["recommendation"],
                connection_details=d["connection_details"],
                risk_score=d["risk_score"],
                risk_factors=d["risk_factors"],
                recovery_info=d["recovery_info"]
            )
            for d in deduped_dicts
        ]
        
        # Calculate summary with change-type specific information
        high_count = sum(1 for s in affected_services if s.impact == ImpactLevel.HIGH)
        medium_count = sum(1 for s in affected_services if s.impact == ImpactLevel.MEDIUM)
        low_count = sum(1 for s in affected_services if s.impact == ImpactLevel.LOW)
        
        # Generate expected behavior description based on change type
        expected_behaviors = {
            ChangeType.DELETE: f"Service will be completely removed. {high_count} services will lose connectivity immediately.",
            ChangeType.SCALE_DOWN: f"Service will be unavailable until scaled back. {high_count} services will experience connection failures.",
            ChangeType.NETWORK_ISOLATE: f"Network traffic will be blocked. {high_count} direct connections will be severed.",
            ChangeType.RESOURCE_CHANGE: f"Performance may degrade. {medium_count} services may experience slower responses.",
            ChangeType.PORT_CHANGE: f"Port change will break existing connections. {high_count} clients need configuration update.",
            ChangeType.CONFIG_CHANGE: f"Behavior may change. {medium_count} services may need to adapt to new configuration.",
            ChangeType.IMAGE_UPDATE: f"Brief disruption during rollout. {medium_count} services may experience temporary errors.",
            ChangeType.NETWORK_POLICY_APPLY: f"Traffic filtering active. {high_count} connections may be blocked if not in allow list.",
            ChangeType.NETWORK_POLICY_REMOVE: f"Security policy removed. No connectivity impact, but security posture changed.",
        }
        
        summary = ImpactSummary(
            total_affected=len(affected_services),
            high_impact=high_count,
            medium_impact=medium_count,
            low_impact=low_count,
            blast_radius=len(direct_deps) + len(indirect_deps),
            confidence_score=min(1.0, graph_data.get("confidence", 0.8)),
            # Change-type specific fields
            primary_impact_category=change_chars["primary_impact"],
            impact_description=change_chars["description"],
            expected_behavior=expected_behaviors.get(request.change_type, "Review impact carefully."),
            recovery_time=change_chars["recovery_time"],
            is_reversible=change_chars["reversible"]
        )
        
        # Determine no-dependency scenario if applicable
        no_dep_info = None
        if len(affected_services) == 0:
            graph_matches = graph_data.get("node_matches", 0)
            has_external = graph_data.get("has_external_connections", False)
            no_dep_info = service.determine_no_dependency_scenario(
                graph_matches, has_external, request.target_kind
            )
        
        # Generate network policy suggestion for network-related changes
        network_policy_suggestion = None
        if request.change_type in [ChangeType.NETWORK_ISOLATE, ChangeType.NETWORK_POLICY_APPLY]:
            try:
                policy_request = NetworkPolicyGenerateRequest(
                    cluster_id=request.cluster_id,
                    analysis_id=request.analysis_id,
                    target_namespace=request.target_namespace,
                    target_workload=request.target_name,
                    target_kind=request.target_kind,
                    policy_types=[],
                    include_dns=True,
                    strict_mode=False
                )
                network_policy_suggestion = await service.generate_network_policy(policy_request)
            except Exception as e:
                logger.warning("Failed to generate network policy suggestion", error=str(e))
        
        # Build simulation details
        change_descriptions = {
            ChangeType.DELETE: "Complete removal of the resource from the cluster",
            ChangeType.SCALE_DOWN: "Scale deployment replicas to zero",
            ChangeType.NETWORK_ISOLATE: "Apply network policy to isolate the target",
            ChangeType.RESOURCE_CHANGE: "Modify CPU/Memory resource limits",
            ChangeType.PORT_CHANGE: "Change exposed service ports",
            ChangeType.CONFIG_CHANGE: "Modify ConfigMap/Secret/Environment variables",
            ChangeType.IMAGE_UPDATE: "Update container image version",
            ChangeType.NETWORK_POLICY_APPLY: "Apply a new network policy",
            ChangeType.NETWORK_POLICY_REMOVE: "Remove an existing network policy"
        }
        
        details = SimulationDetails(
            target_name=request.target_name,
            target_namespace=request.target_namespace,
            target_kind=request.target_kind,
            change_type=request.change_type.value,
            change_description=change_descriptions.get(request.change_type, "Unknown change type"),
            graph_matches=graph_data.get("node_matches", 0),
            simulation_timestamp=datetime.utcnow()
        )
        
        # Build timeline projection based on change type characteristics
        timeline_descriptions = {
            ChangeType.DELETE: {
                "immediate": "Services lose connectivity immediately upon deletion",
                "short_term": "Dependent services may fail health checks and restart",
                "long_term": "System stabilizes after failover or manual intervention"
            },
            ChangeType.SCALE_DOWN: {
                "immediate": "Existing connections drain, new connections fail",
                "short_term": "Queued requests may timeout, clients retry",
                "long_term": "System stable once scaled back up"
            },
            ChangeType.NETWORK_ISOLATE: {
                "immediate": "Network traffic blocked, connections timeout",
                "short_term": "Health checks may fail, pods may restart",
                "long_term": "System adapts to new network topology"
            },
            ChangeType.RESOURCE_CHANGE: {
                "immediate": "Pod may restart if limits reduced significantly",
                "short_term": "Response times may increase, throttling possible",
                "long_term": "System adapts to new resource allocation"
            },
            ChangeType.PORT_CHANGE: {
                "immediate": "Connections to old port fail immediately",
                "short_term": "Clients with cached port info continue failing",
                "long_term": "Stable after all clients update configuration"
            },
            ChangeType.CONFIG_CHANGE: {
                "immediate": "New config takes effect (may require pod restart)",
                "short_term": "Behavior changes propagate through system",
                "long_term": "System operates with new configuration"
            },
            ChangeType.IMAGE_UPDATE: {
                "immediate": "Rolling update begins, brief connection disruption",
                "short_term": "Old and new versions may coexist during rollout",
                "long_term": "All pods running new version, system stable"
            },
            ChangeType.NETWORK_POLICY_APPLY: {
                "immediate": "Policy enforced, non-matching traffic blocked",
                "short_term": "Blocked services may fail health checks",
                "long_term": "System operates within policy constraints"
            },
            ChangeType.NETWORK_POLICY_REMOVE: {
                "immediate": "Policy removed, all traffic allowed",
                "short_term": "No operational impact expected",
                "long_term": "Security posture changed, monitor for anomalies"
            },
        }
        
        change_timeline = timeline_descriptions.get(request.change_type, {
            "immediate": "Immediate effects upon change application",
            "short_term": "Short-term cascading effects",
            "long_term": "Long-term system adaptation"
        })
        
        timeline_projection = {
            "immediate": {
                "description": change_timeline["immediate"],
                "affected_count": high_count,
                "expected_duration": "0-5 minutes",
                "impact_category": change_chars["primary_impact"].value if hasattr(change_chars["primary_impact"], 'value') else str(change_chars["primary_impact"])
            },
            "short_term": {
                "description": change_timeline["short_term"],
                "affected_count": medium_count,
                "expected_duration": "5-30 minutes",
                "secondary_impacts": [imp.value if hasattr(imp, 'value') else str(imp) for imp in change_chars["secondary_impacts"]]
            },
            "long_term": {
                "description": change_timeline["long_term"],
                "affected_count": low_count,
                "expected_duration": "30+ minutes",
                "recovery_time": change_chars["recovery_time"]
            }
        }
        
        # Build rollback scenario based on change type
        rollback_steps = {
            ChangeType.DELETE: [
                "Restore from backup or redeploy from manifest",
                "Verify all ConfigMaps and Secrets are present",
                "Wait for pods to become ready",
                "Verify connectivity from dependent services"
            ],
            ChangeType.SCALE_DOWN: [
                "Scale deployment back to original replica count",
                "Wait for pods to become ready",
                "Verify load balancing is working",
                "Check for any queued request backlog"
            ],
            ChangeType.NETWORK_ISOLATE: [
                "Remove or modify network policy",
                "Verify traffic flow is restored",
                "Check health checks are passing",
                "Monitor for connection timeouts"
            ],
            ChangeType.RESOURCE_CHANGE: [
                "Revert resource limits to previous values",
                "Pod will restart with new limits",
                "Monitor resource utilization",
                "Verify performance is restored"
            ],
            ChangeType.PORT_CHANGE: [
                "Revert port configuration",
                "Update service selector if needed",
                "Notify dependent teams of port reversion",
                "Verify client connections restored"
            ],
            ChangeType.CONFIG_CHANGE: [
                "Revert ConfigMap/Secret to previous version",
                "Restart pods to pick up old config",
                "Verify application behavior",
                "Check for cached configuration issues"
            ],
            ChangeType.IMAGE_UPDATE: [
                "Rollback deployment to previous revision",
                "kubectl rollout undo deployment/<name>",
                "Wait for rollout to complete",
                "Verify application functionality"
            ],
            ChangeType.NETWORK_POLICY_APPLY: [
                "Delete the applied network policy",
                "Verify traffic flow is restored",
                "Review security implications",
                "Update documentation"
            ],
            ChangeType.NETWORK_POLICY_REMOVE: [
                "Reapply the network policy",
                "Verify policy is enforced",
                "Check no legitimate traffic is blocked",
                "Update security documentation"
            ],
        }
        
        rollback_risks = {
            ChangeType.DELETE: ["Data loss if not backed up", "State inconsistency", "Dependency ordering issues"],
            ChangeType.SCALE_DOWN: ["Request queue overflow", "Brief unavailability during scale-up"],
            ChangeType.NETWORK_ISOLATE: ["Security exposure during rollback"],
            ChangeType.RESOURCE_CHANGE: ["Pod restart required", "Brief unavailability"],
            ChangeType.PORT_CHANGE: ["Client configuration sync issues"],
            ChangeType.CONFIG_CHANGE: ["Config cache invalidation", "Restart required"],
            ChangeType.IMAGE_UPDATE: ["Data migration issues if schema changed"],
            ChangeType.NETWORK_POLICY_APPLY: ["Security exposure"],
            ChangeType.NETWORK_POLICY_REMOVE: ["Traffic may be blocked again"],
        }
        
        rollback_times = {
            ChangeType.DELETE: "15-60 minutes (requires redeployment)",
            ChangeType.SCALE_DOWN: "1-5 minutes",
            ChangeType.NETWORK_ISOLATE: "< 1 minute",
            ChangeType.RESOURCE_CHANGE: "1-5 minutes (pod restart)",
            ChangeType.PORT_CHANGE: "1-5 minutes + client updates",
            ChangeType.CONFIG_CHANGE: "1-5 minutes",
            ChangeType.IMAGE_UPDATE: "5-15 minutes",
            ChangeType.NETWORK_POLICY_APPLY: "< 1 minute",
            ChangeType.NETWORK_POLICY_REMOVE: "< 1 minute",
        }
        
        rollback_scenario = {
            "feasibility": "high" if change_chars["reversible"] else "medium",
            "estimated_time": rollback_times.get(request.change_type, "5-15 minutes"),
            "steps": rollback_steps.get(request.change_type, [
                "Identify affected services from this simulation",
                "Prepare rollback configuration/manifest",
                "Execute rollback in reverse order",
                "Verify service health and connectivity"
            ]),
            "risks": rollback_risks.get(request.change_type, []),
            "reversible": change_chars["reversible"]
        }
        
        response = ImpactSimulationResponse(
            success=True,
            simulation_id=str(uuid.uuid4()),
            details=details,
            summary=summary,
            affected_services=affected_services,
            no_dependency_info=no_dep_info,
            network_policy_suggestion=network_policy_suggestion,
            timeline_projection=timeline_projection,
            rollback_scenario=rollback_scenario
        )
        
        # ========== DEBUG: IMPACT SIMULATION RESULTS ==========
        affected_services_summary = [
            {
                "name": f"{svc.namespace}/{svc.name}",
                "kind": svc.kind,
                "impact": svc.impact.value,
                "port": svc.connection_details.get('port', 0),
                "requests": svc.connection_details.get('request_count', 0),
                "risk": svc.risk_score
            }
            for svc in affected_services[:15]
        ]
        
        logger.warning("IMPACT_SIM_RESULTS: simulation completed",
            simulation_id=response.simulation_id,
            total_affected=summary.total_affected,
            high_impact=summary.high_impact,
            medium_impact=summary.medium_impact,
            low_impact=summary.low_impact,
            blast_radius=summary.blast_radius,
            affected_services=affected_services_summary,
            no_dependency_scenario=no_dep_info.scenario if no_dep_info else None
        )
        # ========== DEBUG END ==========
        
        logger.info(
            "Impact simulation completed",
            simulation_id=response.simulation_id,
            total_affected=summary.total_affected,
            high_impact=summary.high_impact
        )
        
        # Save simulation to history (non-blocking)
        try:
            import time
            start_time = time.time()
            await save_simulation_to_history(
                response,
                request,
                current_user.get('username', 'unknown'),
                duration_ms=int((time.time() - start_time) * 1000)
            )
        except Exception as hist_err:
            logger.warning("Failed to save simulation to history", error=str(hist_err))
        
        return response
        
    except Exception as e:
        logger.error("Impact simulation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run impact simulation: {str(e)}"
        )


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post(
    "/impact/export/json",
    summary="Export Impact Simulation to JSON",
    description="Export impact simulation results to JSON format."
)
async def export_impact_simulation_json(
    request: ImpactSimulationRequest,
    cluster_name: Optional[str] = Query(None, description="Cluster name for report"),
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """Export impact simulation results to JSON"""
    try:
        # Run simulation first
        simulation_response = await run_impact_simulation(request, current_user, service)
        
        # Build export report
        export_report = ImpactSimulationExportReport(
            metadata=ExportMetadata(
                generated_at=datetime.utcnow(),
                analysis_id=request.analysis_id,
                cluster_id=request.cluster_id,
                cluster_name=cluster_name,
                export_format="json"
            ),
            simulation=SimulationExportData(
                target_name=request.target_name,
                target_namespace=request.target_namespace,
                target_kind=request.target_kind,
                change_type=request.change_type.value,
                graph_matches=simulation_response.details.graph_matches
            ),
            impact_summary=simulation_response.summary,
            affected_services=simulation_response.affected_services,
            network_policy_suggestion=simulation_response.network_policy_suggestion.model_dump() if simulation_response.network_policy_suggestion else None,
            recommendations=[s.recommendation for s in simulation_response.affected_services]
        )
        
        # Convert to JSON
        output = json.dumps(export_report.model_dump(), indent=2, default=str)
        
        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_safe = request.target_name.replace("/", "-").replace(":", "-")
        filename = f"impact_simulation_{target_safe}_{timestamp}.json"
        
        logger.info("Impact simulation exported to JSON", filename=filename)
        
        return StreamingResponse(
            iter([output]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Impact simulation JSON export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.post(
    "/impact/export/csv",
    summary="Export Impact Simulation to CSV",
    description="Export impact simulation results to CSV format."
)
async def export_impact_simulation_csv(
    request: ImpactSimulationRequest,
    cluster_name: Optional[str] = Query(None, description="Cluster name for report"),
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """Export impact simulation results to CSV"""
    try:
        # Run simulation first
        simulation_response = await run_impact_simulation(request, current_user, service)
        
        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Metadata section
        writer.writerow(["# Impact Simulation Report"])
        writer.writerow(["Generated At", datetime.utcnow().isoformat()])
        writer.writerow(["Cluster ID", request.cluster_id])
        writer.writerow(["Cluster Name", cluster_name or ""])
        writer.writerow(["Analysis ID", request.analysis_id or ""])
        writer.writerow([])
        
        # Target section
        writer.writerow(["# Simulation Target"])
        writer.writerow(["Target Name", request.target_name])
        writer.writerow(["Target Namespace", request.target_namespace])
        writer.writerow(["Target Kind", request.target_kind])
        writer.writerow(["Change Type", request.change_type.value])
        writer.writerow(["Graph Matches", simulation_response.details.graph_matches])
        writer.writerow([])
        
        # Summary section
        writer.writerow(["# Impact Summary"])
        writer.writerow(["Total Affected", simulation_response.summary.total_affected])
        writer.writerow(["High Impact", simulation_response.summary.high_impact])
        writer.writerow(["Medium Impact", simulation_response.summary.medium_impact])
        writer.writerow(["Low Impact", simulation_response.summary.low_impact])
        writer.writerow(["Blast Radius", simulation_response.summary.blast_radius])
        writer.writerow(["Confidence Score", simulation_response.summary.confidence_score])
        writer.writerow([])
        
        # Affected services section
        writer.writerow(["# Affected Services"])
        writer.writerow([
            "Name", "Namespace", "Kind", "Impact", "Dependency Type",
            "Protocol", "Port", "Request Count", "Risk Score", "Recommendation"
        ])
        
        for svc in simulation_response.affected_services:
            conn = svc.connection_details or {}
            writer.writerow([
                svc.name,
                svc.namespace,
                svc.kind,
                svc.impact.value,
                svc.dependency.value,
                conn.get("protocol", ""),
                conn.get("port", ""),
                conn.get("request_count", ""),
                svc.risk_score,
                svc.recommendation
            ])
        
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_safe = request.target_name.replace("/", "-").replace(":", "-")
        filename = f"impact_simulation_{target_safe}_{timestamp}.csv"
        
        logger.info("Impact simulation exported to CSV", filename=filename)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Impact simulation CSV export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# =============================================================================
# Utility Endpoints
# =============================================================================

@router.get(
    "/change-types",
    summary="Get Available Change Types",
    description="Get list of available change types for simulation."
)
async def get_change_types(
    current_user: dict = Depends(get_current_user)
):
    """Get available simulation change types"""
    return {
        "change_types": [
            {
                "key": "delete",
                "label": "Delete / Remove",
                "description": "Completely remove the target from cluster",
                "icon": "delete",
                "category": "destructive"
            },
            {
                "key": "scale_down",
                "label": "Scale Down (replicas: 0)",
                "description": "Scale deployment to zero replicas",
                "icon": "arrow-down",
                "category": "scaling"
            },
            {
                "key": "network_isolate",
                "label": "Network Isolation",
                "description": "Apply network policy to isolate target",
                "icon": "lock",
                "category": "network"
            },
            {
                "key": "resource_change",
                "label": "Resource Limit Change",
                "description": "Modify CPU/Memory limits",
                "icon": "dashboard",
                "category": "resource"
            },
            {
                "key": "port_change",
                "label": "Port Change",
                "description": "Change exposed ports",
                "icon": "api",
                "category": "network"
            },
            {
                "key": "config_change",
                "label": "Configuration Change",
                "description": "Modify ConfigMap/Secret/Environment",
                "icon": "setting",
                "category": "configuration"
            },
            {
                "key": "image_update",
                "label": "Image Update",
                "description": "Update container image version",
                "icon": "cloud-upload",
                "category": "deployment"
            },
            {
                "key": "network_policy_apply",
                "label": "Apply Network Policy",
                "description": "Simulate applying a new network policy",
                "icon": "safety",
                "category": "network",
                "advanced": True
            },
            {
                "key": "network_policy_remove",
                "label": "Remove Network Policy",
                "description": "Simulate removing an existing network policy",
                "icon": "unlock",
                "category": "network",
                "advanced": True
            }
        ]
    }


# =============================================================================
# Scheduled Simulations Endpoints
# =============================================================================

from pydantic import BaseModel, Field
from typing import List, Optional as OptionalType
from datetime import datetime as dt

class ScheduledSimulationCreate(BaseModel):
    """Request to create a scheduled simulation"""
    name: str = Field(..., description="Name of the scheduled simulation")
    description: OptionalType[str] = None
    cluster_id: str
    analysis_id: OptionalType[str] = None
    target_name: str
    target_namespace: str
    target_kind: str = "Deployment"
    change_type: str
    schedule_type: str = Field("once", description="once, daily, weekly")
    scheduled_time: str = Field(..., description="ISO format datetime")
    notify_before_minutes: int = 15
    auto_rollback: bool = False
    rollback_on_failure: bool = True


class ScheduledSimulationResponse(BaseModel):
    """Response for a scheduled simulation"""
    id: str
    name: str
    description: OptionalType[str] = None
    cluster_id: str
    analysis_id: OptionalType[str] = None
    target_name: str
    target_namespace: str
    target_kind: str
    change_type: str
    schedule_type: str
    scheduled_time: str
    notify_before_minutes: int
    auto_rollback: bool
    rollback_on_failure: bool
    status: str = "scheduled"
    created_at: str
    created_by: OptionalType[str] = None
    last_run_at: OptionalType[str] = None
    last_run_result: OptionalType[str] = None


class ScheduledSimulationListResponse(BaseModel):
    """Response for listing scheduled simulations"""
    simulations: List[ScheduledSimulationResponse]
    total: int


@router.get(
    "/scheduled",
    response_model=ScheduledSimulationListResponse,
    summary="List Scheduled Simulations",
    description="Get all scheduled simulations for the current user"
)
async def list_scheduled_simulations(
    cluster_id: OptionalType[str] = Query(None, description="Filter by cluster"),
    status: OptionalType[str] = Query(None, description="Filter by status"),
    current_user: dict = Depends(get_current_user)
):
    """List all scheduled simulations"""
    try:
        from database.postgresql import database
        
        # Check if table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'scheduled_simulations'
            ) as exists
        """
        exists = await database.fetch_one(check_query)
        
        if not exists or not exists.get('exists'):
            # Create table if it doesn't exist
            create_table = """
                CREATE TABLE IF NOT EXISTS scheduled_simulations (
                    id VARCHAR(50) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    cluster_id VARCHAR(50) NOT NULL,
                    analysis_id VARCHAR(50),
                    target_name VARCHAR(255) NOT NULL,
                    target_namespace VARCHAR(255) NOT NULL,
                    target_kind VARCHAR(50) DEFAULT 'Deployment',
                    change_type VARCHAR(50) NOT NULL,
                    schedule_type VARCHAR(20) DEFAULT 'once',
                    scheduled_time TIMESTAMP NOT NULL,
                    notify_before_minutes INT DEFAULT 15,
                    auto_rollback BOOLEAN DEFAULT FALSE,
                    rollback_on_failure BOOLEAN DEFAULT TRUE,
                    status VARCHAR(20) DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(100),
                    last_run_at TIMESTAMP,
                    last_run_result TEXT
                )
            """
            await database.execute(create_table)
            return ScheduledSimulationListResponse(simulations=[], total=0)
        
        # Build query
        query = """
            SELECT * FROM scheduled_simulations
            WHERE 1=1
        """
        params = {}
        
        if cluster_id:
            query += " AND cluster_id = :cluster_id"
            params['cluster_id'] = cluster_id
        
        if status:
            query += " AND status = :status"
            params['status'] = status
        
        query += " ORDER BY scheduled_time ASC"
        
        rows = await database.fetch_all(query, params)
        
        simulations = [
            ScheduledSimulationResponse(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                cluster_id=row['cluster_id'],
                analysis_id=row['analysis_id'],
                target_name=row['target_name'],
                target_namespace=row['target_namespace'],
                target_kind=row['target_kind'],
                change_type=row['change_type'],
                schedule_type=row['schedule_type'],
                scheduled_time=row['scheduled_time'].isoformat() if row['scheduled_time'] else '',
                notify_before_minutes=row['notify_before_minutes'] or 15,
                auto_rollback=row['auto_rollback'] or False,
                rollback_on_failure=row['rollback_on_failure'] if row['rollback_on_failure'] is not None else True,
                status=row['status'],
                created_at=row['created_at'].isoformat() if row['created_at'] else '',
                created_by=row['created_by'],
                last_run_at=row['last_run_at'].isoformat() if row['last_run_at'] else None,
                last_run_result=row['last_run_result']
            )
            for row in rows
        ]
        
        return ScheduledSimulationListResponse(simulations=simulations, total=len(simulations))
        
    except Exception as e:
        logger.error("Failed to list scheduled simulations", error=str(e))
        return ScheduledSimulationListResponse(simulations=[], total=0)


@router.post(
    "/scheduled",
    response_model=ScheduledSimulationResponse,
    summary="Create Scheduled Simulation",
    description="Create a new scheduled simulation"
)
async def create_scheduled_simulation(
    request: ScheduledSimulationCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new scheduled simulation"""
    try:
        from database.postgresql import database
        
        # Ensure table exists
        create_table = """
            CREATE TABLE IF NOT EXISTS scheduled_simulations (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                cluster_id VARCHAR(50) NOT NULL,
                analysis_id VARCHAR(50),
                target_name VARCHAR(255) NOT NULL,
                target_namespace VARCHAR(255) NOT NULL,
                target_kind VARCHAR(50) DEFAULT 'Deployment',
                change_type VARCHAR(50) NOT NULL,
                schedule_type VARCHAR(20) DEFAULT 'once',
                scheduled_time TIMESTAMP NOT NULL,
                notify_before_minutes INT DEFAULT 15,
                auto_rollback BOOLEAN DEFAULT FALSE,
                rollback_on_failure BOOLEAN DEFAULT TRUE,
                status VARCHAR(20) DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                last_run_at TIMESTAMP,
                last_run_result TEXT
            )
        """
        await database.execute(create_table)
        
        simulation_id = f"sched-{str(uuid.uuid4())[:8]}"
        
        insert_query = """
            INSERT INTO scheduled_simulations (
                id, name, description, cluster_id, analysis_id,
                target_name, target_namespace, target_kind, change_type,
                schedule_type, scheduled_time, notify_before_minutes,
                auto_rollback, rollback_on_failure, status, created_by
            ) VALUES (
                :id, :name, :description, :cluster_id, :analysis_id,
                :target_name, :target_namespace, :target_kind, :change_type,
                :schedule_type, :scheduled_time, :notify_before_minutes,
                :auto_rollback, :rollback_on_failure, 'scheduled', :created_by
            )
            RETURNING *
        """
        
        # Parse scheduled_time from ISO string to datetime (naive, without timezone)
        from dateutil.parser import parse as parse_datetime
        from datetime import timezone
        try:
            scheduled_time_dt = parse_datetime(request.scheduled_time)
            # Convert timezone-aware datetime to UTC, then make naive for PostgreSQL TIMESTAMP column
            if scheduled_time_dt.tzinfo is not None:
                # Convert to UTC first to preserve the actual moment in time
                scheduled_time_dt = scheduled_time_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception as e:
            logger.error("Invalid scheduled_time format", error=str(e), scheduled_time=request.scheduled_time)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scheduled_time format: {request.scheduled_time}"
            )
        
        row = await database.fetch_one(insert_query, {
            'id': simulation_id,
            'name': request.name,
            'description': request.description,
            'cluster_id': request.cluster_id,
            'analysis_id': request.analysis_id,
            'target_name': request.target_name,
            'target_namespace': request.target_namespace,
            'target_kind': request.target_kind,
            'change_type': request.change_type,
            'schedule_type': request.schedule_type,
            'scheduled_time': scheduled_time_dt,
            'notify_before_minutes': request.notify_before_minutes,
            'auto_rollback': request.auto_rollback,
            'rollback_on_failure': request.rollback_on_failure,
            'created_by': current_user.get('username', 'unknown')
        })
        
        logger.info(
            "Scheduled simulation created",
            simulation_id=simulation_id,
            name=request.name,
            user=current_user.get('username')
        )
        
        return ScheduledSimulationResponse(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            cluster_id=row['cluster_id'],
            analysis_id=row['analysis_id'],
            target_name=row['target_name'],
            target_namespace=row['target_namespace'],
            target_kind=row['target_kind'],
            change_type=row['change_type'],
            schedule_type=row['schedule_type'],
            scheduled_time=row['scheduled_time'].isoformat() if row['scheduled_time'] else '',
            notify_before_minutes=row['notify_before_minutes'] or 15,
            auto_rollback=row['auto_rollback'] or False,
            rollback_on_failure=row['rollback_on_failure'] if row['rollback_on_failure'] is not None else True,
            status=row['status'],
            created_at=row['created_at'].isoformat() if row['created_at'] else '',
            created_by=row['created_by']
        )
        
    except Exception as e:
        logger.error("Failed to create scheduled simulation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scheduled simulation: {str(e)}"
        )


@router.delete(
    "/scheduled/{simulation_id}",
    summary="Cancel Scheduled Simulation",
    description="Cancel a scheduled simulation"
)
async def cancel_scheduled_simulation(
    simulation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel a scheduled simulation"""
    try:
        from database.postgresql import database
        
        # Check if simulation exists
        query = "SELECT * FROM scheduled_simulations WHERE id = :id"
        simulation = await database.fetch_one(query, {'id': simulation_id})
        
        if not simulation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled simulation not found"
            )
        
        # Delete the simulation
        delete_query = "DELETE FROM scheduled_simulations WHERE id = :id"
        await database.execute(delete_query, {'id': simulation_id})
        
        logger.info(
            "Scheduled simulation cancelled",
            simulation_id=simulation_id,
            user=current_user.get('username')
        )
        
        return {"message": "Scheduled simulation cancelled", "id": simulation_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel scheduled simulation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel scheduled simulation: {str(e)}"
        )


@router.post(
    "/scheduled/{simulation_id}/run",
    summary="Run Scheduled Simulation Now",
    description="Execute a scheduled simulation immediately"
)
async def run_scheduled_simulation_now(
    simulation_id: str,
    current_user: dict = Depends(get_current_user),
    service: NetworkPolicyService = Depends(get_service)
):
    """Run a scheduled simulation immediately"""
    try:
        from database.postgresql import database
        
        # Get simulation details
        query = "SELECT * FROM scheduled_simulations WHERE id = :id"
        simulation = await database.fetch_one(query, {'id': simulation_id})
        
        if not simulation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled simulation not found"
            )
        
        # Run the impact simulation
        # Construct target_id from stored fields (format: kind-namespace-name or just target_name)
        target_id = simulation['target_name']
        
        request = ImpactSimulationRequest(
            cluster_id=simulation['cluster_id'],
            analysis_id=simulation['analysis_id'],
            target_id=target_id,
            target_name=simulation['target_name'],
            target_namespace=simulation['target_namespace'],
            target_kind=simulation['target_kind'],
            change_type=ChangeType(simulation['change_type'])
        )
        
        result = await run_impact_simulation(request, current_user, service)
        
        # Update simulation status
        update_query = """
            UPDATE scheduled_simulations 
            SET last_run_at = NOW(), 
                last_run_result = :result,
                status = CASE WHEN schedule_type = 'once' THEN 'completed' ELSE status END
            WHERE id = :id
        """
        await database.execute(update_query, {
            'id': simulation_id,
            'result': 'success' if result.success else 'failed'
        })
        
        logger.info(
            "Scheduled simulation executed",
            simulation_id=simulation_id,
            user=current_user.get('username')
        )
        
        return {
            "message": "Simulation executed",
            "id": simulation_id,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to run scheduled simulation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run scheduled simulation: {str(e)}"
        )


@router.get(
    "/scheduled/worker/status",
    summary="Get Scheduler Worker Status",
    description="Get the status of the scheduled simulation worker"
)
async def get_scheduler_status(
    current_user: dict = Depends(get_current_user)
):
    """Get the status of the scheduled simulation worker"""
    try:
        from workers.scheduled_simulation_worker import scheduled_simulation_worker
        
        status_info = await scheduled_simulation_worker.get_status()
        
        return {
            "worker": "scheduled_simulation_worker",
            **status_info
        }
        
    except Exception as e:
        logger.error("Failed to get scheduler status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduler status: {str(e)}"
        )


# =============================================================================
# Simulation History Endpoints
# =============================================================================

class SimulationHistoryResponse(BaseModel):
    """Response for a simulation history entry"""
    id: str
    simulation_id: str
    cluster_id: str
    analysis_id: OptionalType[str] = None
    target_name: str
    target_namespace: str
    target_kind: str
    change_type: str
    total_affected: int
    high_impact: int
    medium_impact: int
    low_impact: int
    blast_radius: int
    confidence_score: float
    status: str
    created_at: str
    created_by: OptionalType[str] = None
    duration_ms: OptionalType[int] = None
    result_summary: OptionalType[dict] = None


class SimulationHistoryListResponse(BaseModel):
    """Response for listing simulation history"""
    history: List[SimulationHistoryResponse]
    total: int


async def save_simulation_to_history(
    simulation_response: ImpactSimulationResponse,
    request: ImpactSimulationRequest,
    user: str,
    duration_ms: int = 0
):
    """Save a simulation result to history"""
    try:
        from database.postgresql import database
        
        # Ensure table exists
        create_table = """
            CREATE TABLE IF NOT EXISTS simulation_history (
                id VARCHAR(50) PRIMARY KEY,
                simulation_id VARCHAR(50) NOT NULL,
                cluster_id VARCHAR(50) NOT NULL,
                analysis_id VARCHAR(50),
                target_name VARCHAR(255) NOT NULL,
                target_namespace VARCHAR(255) NOT NULL,
                target_kind VARCHAR(50) DEFAULT 'Deployment',
                change_type VARCHAR(50) NOT NULL,
                total_affected INT DEFAULT 0,
                high_impact INT DEFAULT 0,
                medium_impact INT DEFAULT 0,
                low_impact INT DEFAULT 0,
                blast_radius INT DEFAULT 0,
                confidence_score DECIMAL(5,4) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                duration_ms INT,
                result_summary JSONB
            )
        """
        await database.execute(create_table)
        
        # Create index if not exists
        try:
            await database.execute("""
                CREATE INDEX IF NOT EXISTS idx_simulation_history_created 
                ON simulation_history(created_at DESC)
            """)
            await database.execute("""
                CREATE INDEX IF NOT EXISTS idx_simulation_history_cluster 
                ON simulation_history(cluster_id)
            """)
        except:
            pass  # Index might already exist
        
        history_id = f"hist-{str(uuid.uuid4())[:8]}"
        
        # Prepare result summary
        result_summary = {
            "affected_services": [
                {
                    "name": s.name,
                    "namespace": s.namespace,
                    "kind": s.kind,
                    "impact": s.impact.value if hasattr(s.impact, 'value') else s.impact,
                    "dependency": s.dependency.value if hasattr(s.dependency, 'value') else s.dependency,
                    "risk_score": s.risk_score
                }
                for s in simulation_response.affected_services[:20]  # Limit to first 20
            ],
            "timeline_projection": simulation_response.timeline_projection,
            "rollback_scenario": simulation_response.rollback_scenario
        }
        
        insert_query = """
            INSERT INTO simulation_history (
                id, simulation_id, cluster_id, analysis_id,
                target_name, target_namespace, target_kind, change_type,
                total_affected, high_impact, medium_impact, low_impact,
                blast_radius, confidence_score, status, created_by,
                duration_ms, result_summary
            ) VALUES (
                :id, :simulation_id, :cluster_id, :analysis_id,
                :target_name, :target_namespace, :target_kind, :change_type,
                :total_affected, :high_impact, :medium_impact, :low_impact,
                :blast_radius, :confidence_score, :status, :created_by,
                :duration_ms, :result_summary
            )
        """
        
        await database.execute(insert_query, {
            'id': history_id,
            'simulation_id': simulation_response.simulation_id,
            'cluster_id': str(request.cluster_id),
            'analysis_id': str(request.analysis_id) if request.analysis_id else None,
            'target_name': request.target_name,
            'target_namespace': request.target_namespace,
            'target_kind': request.target_kind,
            'change_type': request.change_type.value if hasattr(request.change_type, 'value') else request.change_type,
            'total_affected': simulation_response.summary.total_affected,
            'high_impact': simulation_response.summary.high_impact,
            'medium_impact': simulation_response.summary.medium_impact,
            'low_impact': simulation_response.summary.low_impact,
            'blast_radius': simulation_response.summary.blast_radius,
            'confidence_score': simulation_response.summary.confidence_score,
            'status': 'completed' if simulation_response.success else 'failed',
            'created_by': user,
            'duration_ms': duration_ms,
            'result_summary': json.dumps(result_summary, default=str)
        })
        
        logger.info(
            "Simulation saved to history",
            history_id=history_id,
            simulation_id=simulation_response.simulation_id
        )
        
    except Exception as e:
        logger.warning("Failed to save simulation to history", error=str(e))
        # Don't raise - history save failure shouldn't fail the simulation


@router.get(
    "/history",
    response_model=SimulationHistoryListResponse,
    summary="List Simulation History",
    description="Get simulation history for the current user"
)
async def list_simulation_history(
    cluster_id: OptionalType[str] = Query(None, description="Filter by cluster"),
    analysis_id: OptionalType[str] = Query(None, description="Filter by analysis"),
    limit: int = Query(50, description="Maximum number of results"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_user)
):
    """List simulation history"""
    try:
        from database.postgresql import database
        
        # Check if table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'simulation_history'
            ) as exists
        """
        exists = await database.fetch_one(check_query)
        
        if not exists or not exists.get('exists'):
            # Create table if it doesn't exist
            create_table = """
                CREATE TABLE IF NOT EXISTS simulation_history (
                    id VARCHAR(50) PRIMARY KEY,
                    simulation_id VARCHAR(50) NOT NULL,
                    cluster_id VARCHAR(50) NOT NULL,
                    analysis_id VARCHAR(50),
                    target_name VARCHAR(255) NOT NULL,
                    target_namespace VARCHAR(255) NOT NULL,
                    target_kind VARCHAR(50) DEFAULT 'Deployment',
                    change_type VARCHAR(50) NOT NULL,
                    total_affected INT DEFAULT 0,
                    high_impact INT DEFAULT 0,
                    medium_impact INT DEFAULT 0,
                    low_impact INT DEFAULT 0,
                    blast_radius INT DEFAULT 0,
                    confidence_score DECIMAL(5,4) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(100),
                    duration_ms INT,
                    result_summary JSONB
                )
            """
            await database.execute(create_table)
            return SimulationHistoryListResponse(history=[], total=0)
        
        # Build query
        query = """
            SELECT * FROM simulation_history
            WHERE 1=1
        """
        count_query = """
            SELECT COUNT(*) as total FROM simulation_history
            WHERE 1=1
        """
        params = {}
        
        if cluster_id:
            query += " AND cluster_id = :cluster_id"
            count_query += " AND cluster_id = :cluster_id"
            params['cluster_id'] = cluster_id
        
        if analysis_id:
            query += " AND analysis_id = :analysis_id"
            count_query += " AND analysis_id = :analysis_id"
            params['analysis_id'] = analysis_id
        
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params['limit'] = limit
        params['offset'] = offset
        
        rows = await database.fetch_all(query, params)
        total_row = await database.fetch_one(count_query, {k: v for k, v in params.items() if k not in ['limit', 'offset']})
        total = total_row.get('total', 0) if total_row else 0
        
        history = []
        for row in rows:
            result_summary = None
            if row['result_summary']:
                try:
                    result_summary = json.loads(row['result_summary']) if isinstance(row['result_summary'], str) else row['result_summary']
                except:
                    result_summary = None
            
            history.append(SimulationHistoryResponse(
                id=row['id'],
                simulation_id=row['simulation_id'],
                cluster_id=row['cluster_id'],
                analysis_id=row['analysis_id'],
                target_name=row['target_name'],
                target_namespace=row['target_namespace'],
                target_kind=row['target_kind'],
                change_type=row['change_type'],
                total_affected=row['total_affected'] or 0,
                high_impact=row['high_impact'] or 0,
                medium_impact=row['medium_impact'] or 0,
                low_impact=row['low_impact'] or 0,
                blast_radius=row['blast_radius'] or 0,
                confidence_score=float(row['confidence_score']) if row['confidence_score'] else 0.0,
                status=row['status'],
                created_at=row['created_at'].isoformat() if row['created_at'] else '',
                created_by=row['created_by'],
                duration_ms=row['duration_ms'],
                result_summary=result_summary
            ))
        
        return SimulationHistoryListResponse(history=history, total=total)
        
    except Exception as e:
        logger.error("Failed to list simulation history", error=str(e))
        return SimulationHistoryListResponse(history=[], total=0)


@router.get(
    "/history/{history_id}",
    response_model=SimulationHistoryResponse,
    summary="Get Simulation History Entry",
    description="Get a specific simulation history entry"
)
async def get_simulation_history_entry(
    history_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific simulation history entry"""
    try:
        from database.postgresql import database
        
        query = "SELECT * FROM simulation_history WHERE id = :id"
        row = await database.fetch_one(query, {'id': history_id})
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Simulation history entry not found"
            )
        
        result_summary = None
        if row['result_summary']:
            try:
                result_summary = json.loads(row['result_summary']) if isinstance(row['result_summary'], str) else row['result_summary']
            except:
                result_summary = None
        
        return SimulationHistoryResponse(
            id=row['id'],
            simulation_id=row['simulation_id'],
            cluster_id=row['cluster_id'],
            analysis_id=row['analysis_id'],
            target_name=row['target_name'],
            target_namespace=row['target_namespace'],
            target_kind=row['target_kind'],
            change_type=row['change_type'],
            total_affected=row['total_affected'] or 0,
            high_impact=row['high_impact'] or 0,
            medium_impact=row['medium_impact'] or 0,
            low_impact=row['low_impact'] or 0,
            blast_radius=row['blast_radius'] or 0,
            confidence_score=float(row['confidence_score']) if row['confidence_score'] else 0.0,
            status=row['status'],
            created_at=row['created_at'].isoformat() if row['created_at'] else '',
            created_by=row['created_by'],
            duration_ms=row['duration_ms'],
            result_summary=result_summary
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get simulation history entry", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get simulation history entry: {str(e)}"
        )


@router.delete(
    "/history/{history_id}",
    summary="Delete Simulation History Entry",
    description="Delete a simulation history entry"
)
async def delete_simulation_history_entry(
    history_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a simulation history entry"""
    try:
        from database.postgresql import database
        
        # Check if entry exists
        query = "SELECT * FROM simulation_history WHERE id = :id"
        entry = await database.fetch_one(query, {'id': history_id})
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Simulation history entry not found"
            )
        
        # Delete the entry
        delete_query = "DELETE FROM simulation_history WHERE id = :id"
        await database.execute(delete_query, {'id': history_id})
        
        logger.info(
            "Simulation history entry deleted",
            history_id=history_id,
            user=current_user.get('username')
        )
        
        return {"message": "History entry deleted", "id": history_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete simulation history entry", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete simulation history entry: {str(e)}"
        )

