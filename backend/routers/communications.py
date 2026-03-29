"""
Communications router - Query workload communication graph
Sprint 5-6: Communication Discovery & Dependency Mapping
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import structlog
import httpx
import re

from utils.jwt_utils import get_current_user
from config import settings

logger = structlog.get_logger()
router = APIRouter()


# Known valid error type keywords (whitelist approach for safety)
# Only these keywords are recognized as meaningful error qualifiers
VALID_ERROR_KEYWORDS = {
    # TCP Retransmit types (from trace_tcpretrans gadget)
    'LOSS', 'RETRANS', 'TIMEOUT', 'SPURIOUS', 'FAST', 'RTO', 'TLP',
    'SYNACK', 'SYN', 'FIN', 'PROBE', 'KEEPALIVE',
    # TCP states
    'ESTABLISHED', 'SYN_SENT', 'SYN_RECV', 'FIN_WAIT1', 'FIN_WAIT2',
    'TIME_WAIT', 'CLOSE', 'CLOSE_WAIT', 'LAST_ACK', 'LISTEN', 'CLOSING',
    # Critical error types
    'RESET', 'REFUSED', 'UNREACHABLE', 'ERROR', 'SOCKET', 'ABORT',
    'REJECTED', 'DROPPED', 'FAILED', 'DENIED',
}


def _clean_error_type(error_type: str) -> str:
    """Clean error type using whitelist approach - only keeps known valid keywords.
    
    Handles cases like:
    - "RETRANSMIT_1761607791" -> "RETRANSMIT"
    - "RETRANSMIT_28271" -> "RETRANSMIT"
    - "RETRANSMIT_LOSS" -> "RETRANSMIT LOSS"  
    - "RETRANSMIT_unknown_value" -> "RETRANSMIT"
    - "CONNECTION_RESET" -> "CONNECTION RESET"
    
    Uses whitelist approach: only known valid keywords are kept, everything else
    (timestamps, sequence numbers, unknown values) is automatically filtered out.
    This is safer than regex-based cleanup as it handles any unexpected input.
    """
    if not error_type:
        return ""
    
    # Extract all words from the error type (split by _, /, space)
    words = re.split(r'[_/\s]+', error_type.upper())
    
    # Keep only known valid keywords
    valid_words = []
    has_retransmit = False
    has_connection = False
    
    for word in words:
        word = word.strip()
        if not word:
            continue
        
        # Track base types
        if word == 'RETRANSMIT':
            has_retransmit = True
        elif word == 'CONNECTION':
            has_connection = True
        # Check if word is a known valid keyword
        elif word in VALID_ERROR_KEYWORDS:
            valid_words.append(word)
    
    # Build result
    if valid_words:
        # Add prefix if we have qualifiers
        if has_connection:
            return f"CONNECTION {' '.join(valid_words)}"
        elif has_retransmit:
            return f"RETRANSMIT {' '.join(valid_words)}"
        else:
            return ' '.join(valid_words)
    
    # Default fallback based on base type
    if has_connection:
        return "CONNECTION ERROR"
    return "RETRANSMIT"


# Response Models
class WorkloadInfo(BaseModel):
    """Workload information in communication"""
    id: str = ""  # Default to empty string to prevent validation errors
    name: str = "unknown"
    kind: Optional[str] = "unknown"  # Made optional with default
    namespace: str = "unknown"
    cluster_id: Optional[str] = None


class CommunicationEdge(BaseModel):
    """Communication edge between workloads"""
    source: WorkloadInfo
    destination: WorkloadInfo
    protocol: Optional[str] = "TCP"  # Made optional with default
    port: Optional[int] = 0  # Made optional with default
    request_count: Optional[int] = 0  # Made optional with default
    bytes_transferred: Optional[int] = 0  # Made optional with default
    avg_latency_ms: Optional[float] = 0.0  # Made optional with default
    risk_level: Optional[str] = None
    risk_score: Optional[float] = 0.0  # Made optional with default
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class CommunicationsResponse(BaseModel):
    """Communications query response"""
    communications: List[CommunicationEdge]
    total: int
    analysis_id: Optional[int] = None


class DependencyNode(BaseModel):
    """Node in dependency graph"""
    id: str = ""  # Default to empty string to prevent validation errors
    name: str = "unknown"
    kind: str = "Pod"
    namespace: str = "unknown"
    cluster_id: str = ""
    status: str = "active"
    labels: dict = {}
    annotations: dict = {}
    ip: Optional[str] = None
    node: Optional[str] = None
    owner_kind: Optional[str] = None  # Deployment, StatefulSet, DaemonSet, etc.
    owner_name: Optional[str] = None  # Name of the owner resource
    # Extended metadata
    pod_uid: Optional[str] = None
    host_ip: Optional[str] = None
    container: Optional[str] = None
    image: Optional[str] = None
    service_account: Optional[str] = None
    phase: Optional[str] = None  # Running, Pending, etc.


class DependencyEdge(BaseModel):
    """Edge in dependency graph"""
    source_id: str = ""  # Default to empty string to prevent validation errors
    target_id: str = ""
    edge_type: str = "COMMUNICATES_WITH"
    protocol: Optional[str] = None
    port: Optional[int] = None
    request_count: int = 0
    # Error fields - from ClickHouse aggregation or Neo4j
    error_count: int = 0
    retransmit_count: int = 0
    last_error_type: Optional[str] = None


class DependencyGraphResponse(BaseModel):
    """Full dependency graph response"""
    nodes: List[DependencyNode]
    edges: List[DependencyEdge]
    total_nodes: int
    total_edges: int


# Helper function to convert timestamp to ISO string
def _normalize_timestamp(value) -> Optional[str]:
    """Convert various timestamp formats to ISO string"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # Check if it's in milliseconds (> year 2100 in seconds)
        if value > 4102444800:
            value = value / 1000
        try:
            return datetime.utcfromtimestamp(value).isoformat() + "Z"
        except (ValueError, OSError):
            return None
    return None


# HTTP Client for Graph Query Service
class GraphQueryClient:
    """HTTP client for Graph Query service"""
    
    def __init__(self):
        self.base_url = settings.GRAPH_QUERY_URL
        self.timeout = 30.0
        self._fallback_enabled = True  # Enable fallback to sample data if service unavailable
    
    async def _call_graph_query(self, endpoint: str, params: dict = None, json_body: dict = None) -> Optional[dict]:
        """Make HTTP call to graph-query service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.base_url}{endpoint}"
                
                if json_body:
                    response = await client.post(url, json=json_body)
                else:
                    response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "text/plain" in content_type:
                        return {"content": response.text, "format": "text"}
                    return response.json()
                else:
                    logger.warning(f"Graph query service returned {response.status_code}", 
                                 endpoint=endpoint, status=response.status_code)
                    return None
                    
        except httpx.ConnectError as e:
            logger.warning(f"Cannot connect to graph-query service: {e}", base_url=self.base_url)
            return None
        except Exception as e:
            logger.error(f"Error calling graph-query service: {e}")
            return None
    
    def _get_fallback_communications(
        self,
        cluster_id: Optional[int] = None,
        namespace: Optional[str] = None,
        protocol: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Return sample data when graph-query service is unavailable"""
        sample_communications = [
            {
                "source": {
                    "id": f"{cluster_id}:frontend:nginx",
                    "name": "nginx",
                    "kind": "Deployment",
                    "namespace": "frontend",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "destination": {
                    "id": f"{cluster_id}:backend:api-gateway",
                    "name": "api-gateway",
                    "kind": "Deployment",
                    "namespace": "backend",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "protocol": "HTTP",
                "port": 8080,
                "request_count": 15420,
                "bytes_transferred": 52428800,
                "avg_latency_ms": 12.5,
                "risk_level": "low",
                "risk_score": 0.1,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat()
            },
            {
                "source": {
                    "id": f"{cluster_id}:backend:api-gateway",
                    "name": "api-gateway",
                    "kind": "Deployment",
                    "namespace": "backend",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "destination": {
                    "id": f"{cluster_id}:backend:user-service",
                    "name": "user-service",
                    "kind": "Deployment",
                    "namespace": "backend",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "protocol": "gRPC",
                "port": 5000,
                "request_count": 8750,
                "bytes_transferred": 10485760,
                "avg_latency_ms": 5.2,
                "risk_level": "low",
                "risk_score": 0.05,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat()
            },
            {
                "source": {
                    "id": f"{cluster_id}:backend:user-service",
                    "name": "user-service",
                    "kind": "Deployment",
                    "namespace": "backend",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "destination": {
                    "id": f"{cluster_id}:database:postgresql",
                    "name": "postgresql",
                    "kind": "StatefulSet",
                    "namespace": "database",
                    "cluster_id": str(cluster_id) if cluster_id else "1"
                },
                "protocol": "TCP",
                "port": 5432,
                "request_count": 45200,
                "bytes_transferred": 209715200,
                "avg_latency_ms": 2.1,
                "risk_level": "medium",
                "risk_score": 0.3,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat()
            }
        ]
        
        # Apply filters
        if namespace:
            sample_communications = [
                c for c in sample_communications
                if c["source"]["namespace"] == namespace or c["destination"]["namespace"] == namespace
            ]
        
        if protocol:
            sample_communications = [
                c for c in sample_communications
                if c["protocol"].upper() == protocol.upper()
            ]
        
        return sample_communications[:limit]
    
    def _get_fallback_graph(
        self,
        cluster_id: int,
        namespace: Optional[str] = None
    ) -> dict:
        """Return sample graph data when graph-query service is unavailable"""
        nodes = [
            {"id": "nginx", "name": "nginx", "kind": "Deployment", "namespace": "frontend", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "nginx"}, "annotations": {}},
            {"id": "api-gateway", "name": "api-gateway", "kind": "Deployment", "namespace": "backend", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "api-gateway"}, "annotations": {}},
            {"id": "user-service", "name": "user-service", "kind": "Deployment", "namespace": "backend", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "user-service"}, "annotations": {}},
            {"id": "order-service", "name": "order-service", "kind": "Deployment", "namespace": "backend", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "order-service"}, "annotations": {}},
            {"id": "postgresql", "name": "postgresql", "kind": "StatefulSet", "namespace": "database", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "postgresql"}, "annotations": {}},
            {"id": "redis", "name": "redis", "kind": "StatefulSet", "namespace": "database", "cluster_id": str(cluster_id), "status": "active", "labels": {"app": "redis"}, "annotations": {}},
        ]
        
        edges = [
            {"source_id": "nginx", "target_id": "api-gateway", "edge_type": "COMMUNICATES_WITH", "protocol": "HTTP", "port": 8080, "request_count": 15420},
            {"source_id": "api-gateway", "target_id": "user-service", "edge_type": "COMMUNICATES_WITH", "protocol": "gRPC", "port": 5000, "request_count": 8750},
            {"source_id": "api-gateway", "target_id": "order-service", "edge_type": "COMMUNICATES_WITH", "protocol": "gRPC", "port": 5001, "request_count": 6230},
            {"source_id": "user-service", "target_id": "postgresql", "edge_type": "COMMUNICATES_WITH", "protocol": "TCP", "port": 5432, "request_count": 45200},
            {"source_id": "order-service", "target_id": "postgresql", "edge_type": "COMMUNICATES_WITH", "protocol": "TCP", "port": 5432, "request_count": 32100},
            {"source_id": "user-service", "target_id": "redis", "edge_type": "COMMUNICATES_WITH", "protocol": "TCP", "port": 6379, "request_count": 125000},
            {"source_id": "order-service", "target_id": "redis", "edge_type": "COMMUNICATES_WITH", "protocol": "TCP", "port": 6379, "request_count": 98000},
        ]
        
        # Apply namespace filter
        if namespace:
            nodes = [n for n in nodes if n["namespace"] == namespace]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source_id"] in node_ids and e["target_id"] in node_ids]
        
        return {"nodes": nodes, "edges": edges}
    
    async def get_communications(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        source_workload: Optional[str] = None,
        destination_workload: Optional[str] = None,
        protocol: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get communications from graph database"""
        logger.info("Fetching communications from graph",
                   cluster_id=cluster_id,
                   analysis_id=analysis_id,
                   namespace=namespace)
        
        # Build query parameters for graph-query service
        params = {"limit": limit}
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if namespace:
            params["namespace"] = namespace
        if protocol:
            params["protocol"] = protocol
        if source_workload:
            params["source_id"] = source_workload
        if destination_workload:
            params["destination_id"] = destination_workload
        
        # Try to call graph-query service
        result = await self._call_graph_query("/communications", params=params)
        
        if result and result.get("success"):
            # Transform Neo4j result to API format
            communications = []
            for record in result.get("data", []):
                comm = {
                    "source": {
                        "id": record.get("source_id", ""),
                        "name": record.get("source_name", ""),
                        "kind": record.get("source_kind", "Pod"),
                        "namespace": record.get("source_namespace", ""),
                        "cluster_id": str(cluster_id) if cluster_id else "1"
                    },
                    "destination": {
                        "id": record.get("destination_id", ""),
                        "name": record.get("destination_name", ""),
                        "kind": record.get("destination_kind", "Pod"),
                        "namespace": record.get("destination_namespace", ""),
                        "cluster_id": str(cluster_id) if cluster_id else "1"
                    },
                    "protocol": record.get("protocol", "TCP"),
                    "port": record.get("destination_port") or 0,
                    "request_count": record.get("request_count") or 0,
                    "bytes_transferred": record.get("bytes_transferred") or 0,
                    "avg_latency_ms": record.get("avg_latency_ms") or 0.0,
                    "risk_level": record.get("risk_level", "low"),
                    "risk_score": record.get("risk_score") or 0.0,
                    "first_seen": _normalize_timestamp(record.get("first_seen")),
                    "last_seen": _normalize_timestamp(record.get("last_seen"))
                }
                communications.append(comm)
            return communications
        
        # Fallback to sample data if graph-query service is unavailable
        if self._fallback_enabled:
            logger.info("Using fallback sample data for communications")
            return self._get_fallback_communications(cluster_id, namespace, protocol, limit)
        
        return []
    
    async def get_communication_count(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> int:
        """Get total count of communications (for smart edge limit calculation)"""
        params = {}
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if namespace:
            params["namespace"] = namespace
        
        result = await self._call_graph_query("/communications/count", params=params)
        
        if result:
            return result.get("total_count", 0)
        
        # Fallback: return 0 (will use default smart limit)
        return 0
    
    async def get_dependency_graph(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        depth: int = 2,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        search: Optional[str] = None
    ) -> dict:
        """Get full dependency graph
        
        Args:
            cluster_id: Optional cluster ID. For multi-cluster analyses, omit this
                        and only pass analysis_id to get graph from all clusters.
            search: Optional search term (min 3 chars) to filter nodes in Neo4j.
                    When provided, limit is increased to get all matching results.
        """
        logger.info("Fetching dependency graph",
                   cluster_id=cluster_id,
                   analysis_id=analysis_id,
                   namespace=namespace,
                   depth=depth,
                   start_time=start_time,
                   end_time=end_time,
                   search=search)
        
        # Try to call graph-query service for workloads
        workloads_result = None
        if namespace:
            workloads_result = await self._call_graph_query(
                "/workloads", 
                params={"namespace": namespace}
            )
        
        # Try to get communications to build graph
        # NOTE: Balanced limit - enough for search to work, not too much to freeze browser
        # 500 was too low (search failed), 50000 was too high (browser froze)
        params = {"limit": 5000}
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if namespace:
            params["namespace"] = namespace
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        
        # SERVER-SIDE SEARCH: When search term is provided (min 3 chars),
        # call /dependencies/graph endpoint which supports search in Neo4j
        # This allows finding nodes that would otherwise be cut off by the limit
        if search and len(search) >= 3:
            search_params = {
                "analysis_id": str(analysis_id) if analysis_id else None,
                "namespace": namespace,
                "search": search
            }
            if cluster_id:
                search_params["cluster_id"] = str(cluster_id)
            # Remove None values
            search_params = {k: v for k, v in search_params.items() if v is not None}
            
            logger.info("Using server-side search via /dependencies/graph", search=search, params=search_params)
            graph_result = await self._call_graph_query("/dependencies/graph", params=search_params)
            
            if graph_result and "nodes" in graph_result:
                return {
                    "nodes": graph_result.get("nodes", []),
                    "edges": graph_result.get("edges", [])
                }
            # Fall through to normal flow if search fails
            logger.warning("Server-side search failed, falling back to normal flow", search=search)
        
        comms_result = await self._call_graph_query("/communications", params=params)
        
        logger.info("[GET_DEP_GRAPH] Graph-query /communications result",
                   success=comms_result.get("success") if comms_result else None,
                   data_count=len(comms_result.get("data", [])) if comms_result else 0,
                   has_result=comms_result is not None)
        
        if comms_result and comms_result.get("success"):
            # Build graph from communications
            nodes_map = {}
            edges = []
            
            def parse_cluster_id_from_node_id(node_id: str) -> str:
                """Parse cluster_id from node ID format: {analysis_id}-{cluster_id}:{cluster_id}:{namespace}:{workload}
                Example: 101-12:12:openshift-ingress:router-default -> cluster_id = 12
                """
                if not node_id:
                    return ""
                try:
                    # Format: {analysis_id}-{cluster_id}:{cluster_id}:{namespace}:{workload}
                    # Split by colon, second part should be cluster_id
                    parts = node_id.split(":")
                    if len(parts) >= 2:
                        return parts[1]  # cluster_id is the second colon-separated part
                except:
                    pass
                return ""
            
            for record in comms_result.get("data", []):
                # Source node
                src_id = record.get("source_id", "")
                if src_id and src_id not in nodes_map:
                    # Parse labels from JSON string if needed
                    src_labels = record.get("source_labels", {})
                    if isinstance(src_labels, str):
                        try:
                            src_labels = json.loads(src_labels)
                        except (json.JSONDecodeError, TypeError):
                            src_labels = {}
                    
                    # Parse annotations from JSON string if needed
                    src_annotations = record.get("source_annotations", {})
                    if isinstance(src_annotations, str):
                        try:
                            src_annotations = json.loads(src_annotations)
                        except (json.JSONDecodeError, TypeError):
                            src_annotations = {}
                    
                    # Multi-cluster: parse cluster_id from node ID, fallback to record or passed cluster_id
                    src_cluster_id = (
                        record.get("source_cluster_id") or 
                        record.get("cluster_id") or 
                        parse_cluster_id_from_node_id(src_id) or 
                        cluster_id or 
                        ""
                    )
                    
                    nodes_map[src_id] = {
                        "id": src_id,
                        "name": record.get("source_name") or src_id.split(":")[-1] or "unknown",
                        "kind": record.get("source_kind") or "Pod",
                        "namespace": record.get("source_namespace") or "unknown",
                        "cluster_id": str(src_cluster_id),
                        "status": "active",
                        "labels": src_labels or {},
                        "annotations": src_annotations or {},
                        "ip": record.get("source_ip"),
                        "node": record.get("source_node"),
                        "owner_kind": record.get("source_owner_kind"),
                        "owner_name": record.get("source_owner_name"),
                        # Extended metadata
                        "pod_uid": record.get("source_pod_uid"),
                        "host_ip": record.get("source_host_ip"),
                        "container": record.get("source_container"),
                        "image": record.get("source_image"),
                        "service_account": record.get("source_service_account"),
                        "phase": record.get("source_phase"),
                    }
                
                # Destination node
                dst_id = record.get("destination_id", "")
                if dst_id and dst_id not in nodes_map:
                    # Parse labels from JSON string if needed
                    dst_labels = record.get("destination_labels", {})
                    if isinstance(dst_labels, str):
                        try:
                            dst_labels = json.loads(dst_labels)
                        except (json.JSONDecodeError, TypeError):
                            dst_labels = {}
                    
                    # Parse annotations from JSON string if needed
                    dst_annotations = record.get("destination_annotations", {})
                    if isinstance(dst_annotations, str):
                        try:
                            dst_annotations = json.loads(dst_annotations)
                        except (json.JSONDecodeError, TypeError):
                            dst_annotations = {}
                    
                    # Multi-cluster: parse cluster_id from node ID, fallback to record or passed cluster_id
                    dst_cluster_id = (
                        record.get("destination_cluster_id") or 
                        record.get("cluster_id") or 
                        parse_cluster_id_from_node_id(dst_id) or 
                        cluster_id or 
                        ""
                    )
                    
                    nodes_map[dst_id] = {
                        "id": dst_id,
                        "name": record.get("destination_name") or dst_id.split(":")[-1] or "unknown",
                        "kind": record.get("destination_kind") or "Pod",
                        "namespace": record.get("destination_namespace") or "external",
                        "cluster_id": str(dst_cluster_id),
                        "status": "active",
                        "labels": dst_labels or {},
                        "annotations": dst_annotations or {},
                        "ip": record.get("destination_ip"),
                        "node": record.get("destination_node"),
                        "owner_kind": record.get("destination_owner_kind"),
                        "owner_name": record.get("destination_owner_name"),
                        # Extended metadata
                        "pod_uid": record.get("destination_pod_uid"),
                        "host_ip": record.get("destination_host_ip"),
                        "container": record.get("destination_container"),
                        "image": record.get("destination_image"),
                        "service_account": record.get("destination_service_account"),
                        "phase": record.get("destination_phase"),
                    }
                
                # Edge - include error fields if available
                edges.append({
                    "source_id": src_id,
                    "target_id": dst_id,
                    "edge_type": "COMMUNICATES_WITH",
                    "protocol": record.get("protocol") or "TCP",
                    "port": record.get("destination_port") or record.get("port") or 0,
                    "request_count": record.get("request_count") or 0,
                    # Error fields - from Neo4j or ClickHouse aggregation
                    "error_count": record.get("error_count") or 0,
                    "retransmit_count": record.get("retransmit_count") or 0,
                    "last_error_type": record.get("last_error_type") or record.get("error_type") or ""
                })
            
            logger.info("[GET_DEP_GRAPH] Built graph from communications",
                       nodes_count=len(nodes_map),
                       edges_count=len(edges))
            
            return {
                "nodes": list(nodes_map.values()),
                "edges": edges
            }
        
        # Fallback to sample data if graph-query service is unavailable
        logger.warning("[GET_DEP_GRAPH] No valid result from graph-query, checking fallback",
                      comms_result_is_none=comms_result is None,
                      success=comms_result.get("success") if comms_result else None)
        
        if self._fallback_enabled:
            logger.info("[GET_DEP_GRAPH] Using fallback sample data for dependency graph")
            return self._get_fallback_graph(cluster_id, namespace)
        
        logger.warning("[GET_DEP_GRAPH] Returning empty graph - no data and fallback disabled")
        return {"nodes": [], "edges": []}


# Singleton client
graph_query_client = GraphQueryClient()


# API Endpoints

@router.get("", response_model=CommunicationsResponse)
async def get_communications(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    source_workload: Optional[str] = Query(None, description="Filter by source workload"),
    destination_workload: Optional[str] = Query(None, description="Filter by destination workload"),
    protocol: Optional[str] = Query(None, description="Filter by protocol (TCP, UDP, HTTP, gRPC)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get workload communications discovered through eBPF analysis.
    
    **Sprint 5-6 Feature**
    
    Returns communication edges between workloads including:
    - Source and destination workload info
    - Protocol and port
    - Request count and bytes transferred
    - Latency metrics
    - Risk assessment
    """
    try:
        communications = await graph_query_client.get_communications(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            source_workload=source_workload,
            destination_workload=destination_workload,
            protocol=protocol,
            limit=limit
        )
        
        return CommunicationsResponse(
            communications=[CommunicationEdge(**c) for c in communications],
            total=len(communications),
            analysis_id=analysis_id
        )
        
    except Exception as e:
        logger.error("Failed to get communications", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve communications: {str(e)}"
        )


@router.get("/graph", response_model=DependencyGraphResponse)
async def get_dependency_graph(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    depth: int = Query(2, ge=1, le=5, description="Graph traversal depth"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    search: Optional[str] = Query(None, min_length=3, description="Search term (min 3 chars) to filter nodes by name, namespace, or id"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get full dependency graph for visualization.
    
    **Sprint 5-6 Feature, Multi-Cluster Support (Sprint 7), Server-Side Search (Sprint 8)**
    
    Returns nodes and edges for rendering in Cytoscape.js or similar.
    
    For multi-cluster analysis, pass only analysis_id to get graph from all clusters.
    
    When search is provided (min 3 chars), the query limit is increased to 50000
    and results are filtered to edges where at least one endpoint matches the search term.
    """
    logger.info("[GRAPH_ENDPOINT] Request received",
               cluster_id=cluster_id,
               analysis_id=analysis_id,
               namespace=namespace,
               depth=depth,
               search=search)
    
    try:
        graph = await graph_query_client.get_dependency_graph(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            depth=depth,
            start_time=start_time,
            end_time=end_time,
            search=search
        )
        
        logger.info("[GRAPH_ENDPOINT] Graph result",
                   nodes_count=len(graph.get("nodes", [])),
                   edges_count=len(graph.get("edges", [])))
        
        return DependencyGraphResponse(
            nodes=[DependencyNode(**n) for n in graph["nodes"]],
            edges=[DependencyEdge(**e) for e in graph["edges"]],
            total_nodes=len(graph["nodes"]),
            total_edges=len(graph["edges"])
        )
        
    except Exception as e:
        logger.error("[GRAPH_ENDPOINT] Failed to get dependency graph", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve dependency graph: {str(e)}"
        )


@router.get("/cross-namespace", response_model=List[CommunicationEdge])
async def get_cross_namespace_communications(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cross-namespace communications (potential security concern).
    
    **Sprint 5-6 Feature**
    
    Returns communications that cross namespace boundaries, excluding system namespaces.
    """
    try:
        communications = await graph_query_client.get_communications(
            cluster_id=cluster_id,
            limit=limit
        )
        
        # Filter to only cross-namespace
        cross_ns = [
            c for c in communications
            if c["source"]["namespace"] != c["destination"]["namespace"]
            and c["source"]["namespace"] not in ["kube-system", "kube-public"]
            and c["destination"]["namespace"] not in ["kube-system", "kube-public"]
        ]
        
        return [CommunicationEdge(**c) for c in cross_ns]
        
    except Exception as e:
        logger.error("Failed to get cross-namespace communications", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve cross-namespace communications: {str(e)}"
        )


@router.get("/high-risk", response_model=List[CommunicationEdge])
async def get_high_risk_communications(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    risk_threshold: float = Query(0.5, ge=0, le=1, description="Minimum risk score"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get high-risk communications based on risk score.
    
    **Sprint 5-6 Feature**
    """
    try:
        communications = await graph_query_client.get_communications(
            cluster_id=cluster_id,
            limit=limit * 2  # Get more to filter
        )
        
        # Filter by risk score (handle None values)
        high_risk = [
            c for c in communications
            if (c.get("risk_score") or 0) >= risk_threshold
        ]
        
        # Sort by risk score descending (handle None values)
        high_risk.sort(key=lambda x: x.get("risk_score") or 0, reverse=True)
        
        return [CommunicationEdge(**c) for c in high_risk[:limit]]
        
    except Exception as e:
        logger.error("Failed to get high-risk communications", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve high-risk communications: {str(e)}"
        )


@router.get("/stats")
async def get_communication_stats(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get communication statistics for dashboard.
    
    **Sprint 5-6 Feature**
    
    Note: total_communications is fetched via separate COUNT query (no limit)
    to ensure accurate count for smart edge limit calculation.
    """
    try:
        # Get REAL total count (no limit) - critical for smart edge limit calculation
        total_communications = await graph_query_client.get_communication_count(
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        
        # Get sample communications for other stats (limited for performance)
        communications = await graph_query_client.get_communications(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            limit=1000
        )
        
        # Calculate statistics from sample (use 'or 0' to handle None values)
        total_request_count = sum((c.get("request_count") or 0) for c in communications)
        total_bytes = sum((c.get("bytes_transferred") or 0) for c in communications)
        
        # Error statistics with categorization
        from schemas.events import get_error_category, ErrorCategory
        
        total_errors = 0
        total_critical = 0
        total_warnings = 0
        errors_by_type = {}
        critical_by_type = {}
        warnings_by_type = {}
        
        for c in communications:
            error_count = c.get("error_count") or 0
            retransmit_count = c.get("retransmit_count") or 0
            raw_error_type = c.get("last_error_type") or c.get("error_type") or ""
            
            combined_count = error_count + retransmit_count
            if combined_count == 0:
                continue
            
            total_errors += combined_count
            
            # Clean error type (remove timestamps, normalize format)
            cleaned_type = _clean_error_type(raw_error_type) if raw_error_type else ""
            
            # Legacy: keep errors_by_type for backward compatibility (use cleaned type)
            if cleaned_type:
                errors_by_type[cleaned_type] = errors_by_type.get(cleaned_type, 0) + combined_count
            
            # New: categorized errors (use raw type for pattern matching, cleaned for display)
            category = get_error_category(raw_error_type)
            if category == ErrorCategory.CRITICAL:
                total_critical += combined_count
                if cleaned_type:
                    critical_by_type[cleaned_type] = critical_by_type.get(cleaned_type, 0) + combined_count
            else:
                total_warnings += combined_count
                if cleaned_type:
                    warnings_by_type[cleaned_type] = warnings_by_type.get(cleaned_type, 0) + combined_count
        
        total_retransmits = total_warnings  # Retransmits are typically warnings
        
        # Calculate health status
        total_flows = len(communications)
        critical_rate = (total_critical / total_flows * 100) if total_flows > 0 else 0
        
        if critical_rate == 0:
            error_health_status = "healthy"
        elif critical_rate < 0.1:
            error_health_status = "good"
        elif critical_rate < 1:
            error_health_status = "warning"
        elif critical_rate < 5:
            error_health_status = "degraded"
        else:
            error_health_status = "critical"
        
        # Unique namespaces
        namespaces = set()
        for c in communications:
            namespaces.add(c["source"]["namespace"])
            namespaces.add(c["destination"]["namespace"])
        
        # Protocol distribution
        protocols = {}
        for c in communications:
            proto = c.get("protocol", "UNKNOWN")
            protocols[proto] = protocols.get(proto, 0) + 1
        
        # Risk distribution
        risk_levels = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for c in communications:
            level = c.get("risk_level", "low")
            if level in risk_levels:
                risk_levels[level] += 1
        
        return {
            "total_communications": total_communications,
            "total_request_count": total_request_count,
            "total_bytes_transferred": total_bytes,
            # Legacy error fields (backward compatible)
            "total_errors": total_errors,
            "total_retransmits": total_retransmits,
            "errors_by_type": errors_by_type,
            # New categorized error fields
            "total_critical": total_critical,
            "total_warnings": total_warnings,
            "critical_by_type": critical_by_type,
            "warnings_by_type": warnings_by_type,
            "error_health_status": error_health_status,
            # Other stats
            "unique_namespaces": len(namespaces),
            "protocol_distribution": protocols,
            "risk_distribution": risk_levels,
            "cluster_id": cluster_id,
            "analysis_id": analysis_id
        }
        
    except Exception as e:
        logger.error("Failed to get communication stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve communication statistics: {str(e)}"
        )


@router.get("/error-stats")
async def get_error_stats(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get categorized network error statistics with NO LIMIT.
    
    Returns accurate error counts by querying ClickHouse directly with aggregation.
    Separates critical errors (connection failures) from warnings (retransmissions).
    
    **Error Categories:**
    - CRITICAL: CONNECTION_RESET, CONNECTION_REFUSED, TIMEOUT, etc. (real problems)
    - WARNING: RETRANSMIT_*, etc. (normal TCP behavior)
    
    **Health Status:**
    - healthy: 0% critical error rate
    - good: <0.1% critical error rate
    - warning: 0.1-1% critical error rate
    - degraded: 1-5% critical error rate
    - critical: >5% critical error rate
    """
    from schemas.events import ErrorStatsResponse, get_error_category, ErrorCategory
    
    try:
        # Try to get error stats from ClickHouse (primary source)
        error_stats = await _get_clickhouse_error_stats(cluster_id, analysis_id, namespace)
        
        if error_stats:
            return error_stats
        
        # Fallback to Neo4j data via graph_query_client
        logger.info("ClickHouse error stats not available, falling back to Neo4j")
        return await _get_neo4j_error_stats(cluster_id, analysis_id, namespace)
        
    except Exception as e:
        logger.error("Failed to get error stats", error=str(e))
        # Return empty stats on error instead of failing
        return ErrorStatsResponse(
            total_errors=0,
            total_critical=0,
            total_warnings=0,
            health_status="healthy",
            health_message="Unable to retrieve error statistics",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace
        )


async def _get_clickhouse_error_stats(
    cluster_id: Optional[int],
    analysis_id: Optional[int],
    namespace: Optional[str]
) -> Optional[dict]:
    """
    Query ClickHouse for accurate error statistics (NO LIMIT).
    
    Uses aggregation query to get total counts grouped by error_type.
    Uses asyncio.to_thread to avoid blocking the event loop.
    """
    import asyncio
    from schemas.events import ErrorStatsResponse, get_error_category, ErrorCategory
    
    def _sync_query():
        """Synchronous ClickHouse query - run in thread pool
        
        IMPORTANT: Creates a NEW client per query to avoid concurrent connection issues.
        The clickhouse_driver Client is NOT thread-safe, so we cannot share a global
        singleton across multiple concurrent async requests.
        """
        try:
            from database.clickhouse import create_clickhouse_client, CLICKHOUSE_ENABLED
            
            if not CLICKHOUSE_ENABLED:
                return None
            
            # Create a NEW client for this thread to avoid "Simultaneous queries on single connection"
            client = create_clickhouse_client()
            if client is None:
                return None
            
            # Build WHERE clause
            conditions = []
            params = {}
            
            if analysis_id:
                # Support both single and multi-cluster analysis_id formats
                conditions.append("(analysis_id = %(analysis_id)s OR analysis_id LIKE %(analysis_id_prefix)s)")
                params["analysis_id"] = str(analysis_id)
                params["analysis_id_prefix"] = f"{analysis_id}-%"
            
            if cluster_id:
                conditions.append("cluster_id = %(cluster_id)s")
                params["cluster_id"] = str(cluster_id)
            
            if namespace:
                conditions.append("(source_namespace = %(namespace)s OR dest_namespace = %(namespace)s)")
                params["namespace"] = namespace
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Query 1: Get error counts grouped by error_type (NO LIMIT)
            error_query = f"""
            SELECT 
                error_type,
                sum(error_count) as total_errors,
                sum(retransmit_count) as total_retransmits,
                count(*) as flow_count
            FROM network_flows
            WHERE {where_clause}
              AND (error_count > 0 OR retransmit_count > 0 OR error_type != '')
            GROUP BY error_type
            """
            
            error_result = client.execute(error_query, params)
            
            # Query 2: Get total flow count for error rate calculation
            total_query = f"""
            SELECT count(*) as total_flows
            FROM network_flows
            WHERE {where_clause}
            """
            
            total_result = client.execute(total_query, params)
            total_flows = total_result[0][0] if total_result else 0
            
            # Process results and categorize errors
            total_errors = 0
            total_critical = 0
            total_warnings = 0
            critical_by_type = {}
            warnings_by_type = {}
            
            for row in error_result:
                raw_error_type = row[0] or "UNKNOWN"
                error_count = row[1] or 0
                retransmit_count = row[2] or 0
                
                # Total errors includes both error_count and retransmit_count
                combined_count = error_count + retransmit_count
                total_errors += combined_count
                
                # Clean error type (remove timestamps, normalize format)
                cleaned_type = _clean_error_type(raw_error_type)
                
                # Categorize by error type (use raw for pattern matching)
                category = get_error_category(raw_error_type)
                
                if category == ErrorCategory.CRITICAL:
                    total_critical += combined_count
                    if cleaned_type and combined_count > 0:
                        critical_by_type[cleaned_type] = critical_by_type.get(cleaned_type, 0) + combined_count
                else:
                    total_warnings += combined_count
                    if cleaned_type and combined_count > 0:
                        warnings_by_type[cleaned_type] = warnings_by_type.get(cleaned_type, 0) + combined_count
            
            # Calculate rates
            error_rate = (total_errors / total_flows * 100) if total_flows > 0 else 0
            critical_rate = (total_critical / total_flows * 100) if total_flows > 0 else 0
            
            # Determine health status based on critical error rate
            if critical_rate == 0:
                health_status = "healthy"
                health_message = "No critical errors detected."
            elif critical_rate < 0.1:
                health_status = "good"
                health_message = f"{total_critical} critical errors detected ({critical_rate:.2f}% rate)."
            elif critical_rate < 1:
                health_status = "warning"
                health_message = f"{total_critical} critical errors detected ({critical_rate:.2f}% rate) - investigate connection failures."
            elif critical_rate < 5:
                health_status = "degraded"
                health_message = f"{total_critical} critical errors ({critical_rate:.2f}% rate) - service health may be impacted."
            else:
                health_status = "critical"
                health_message = f"{total_critical} critical errors ({critical_rate:.2f}% rate) - immediate attention required!"
            
            # Add retransmit context if warnings exist
            if total_warnings > 0 and total_flows > 0:
                retransmit_rate = total_warnings / total_flows * 100
                if retransmit_rate < 1:
                    health_message += f" Retransmit rate ({retransmit_rate:.2f}%) is within normal range."
                elif retransmit_rate < 5:
                    health_message += f" Retransmit rate ({retransmit_rate:.2f}%) is slightly elevated."
                else:
                    health_message += f" Retransmit rate ({retransmit_rate:.2f}%) is high - check network conditions."
            
            return {
                "total_errors": total_errors,
                "total_critical": total_critical,
                "total_warnings": total_warnings,
                "critical_by_type": critical_by_type,
                "warnings_by_type": warnings_by_type,
                "total_flows": total_flows,
                "error_rate_percent": round(error_rate, 2),
                "critical_rate_percent": round(critical_rate, 2),
                "health_status": health_status,
                "health_message": health_message,
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace
            }
            
        except ImportError:
            logger.warning("ClickHouse database module not available")
            return None
        except Exception as e:
            logger.warning(f"ClickHouse error stats query failed: {e}")
            return None
    
    # Run synchronous ClickHouse query in thread pool to avoid blocking
    try:
        result = await asyncio.to_thread(_sync_query)
        if result:
            return ErrorStatsResponse(**result)
        return None
    except Exception as e:
        logger.warning(f"Error running ClickHouse query in thread: {e}")
        return None


async def _get_neo4j_error_stats(
    cluster_id: Optional[int],
    analysis_id: Optional[int],
    namespace: Optional[str]
) -> dict:
    """
    Fallback: Get error stats from Neo4j via graph_query_client.
    
    Less accurate than ClickHouse but provides basic error information.
    """
    from schemas.events import ErrorStatsResponse, get_error_category, ErrorCategory
    
    try:
        # Get communications from Neo4j (limited)
        communications = await graph_query_client.get_communications(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=1000
        )
        
        total_errors = 0
        total_critical = 0
        total_warnings = 0
        critical_by_type = {}
        warnings_by_type = {}
        
        for c in communications:
            error_count = c.get("error_count") or 0
            retransmit_count = c.get("retransmit_count") or 0
            raw_error_type = c.get("last_error_type") or c.get("error_type") or ""
            
            combined_count = error_count + retransmit_count
            if combined_count == 0:
                continue
            
            total_errors += combined_count
            
            # Clean error type (remove timestamps, normalize format)
            cleaned_type = _clean_error_type(raw_error_type) if raw_error_type else ""
            
            # Use raw type for pattern matching, cleaned for display
            category = get_error_category(raw_error_type)
            
            if category == ErrorCategory.CRITICAL:
                total_critical += combined_count
                if cleaned_type:
                    critical_by_type[cleaned_type] = critical_by_type.get(cleaned_type, 0) + combined_count
            else:
                total_warnings += combined_count
                if cleaned_type:
                    warnings_by_type[cleaned_type] = warnings_by_type.get(cleaned_type, 0) + combined_count
        
        total_flows = len(communications)
        error_rate = (total_errors / total_flows * 100) if total_flows > 0 else 0
        critical_rate = (total_critical / total_flows * 100) if total_flows > 0 else 0
        
        # Determine health status
        if critical_rate == 0:
            health_status = "healthy"
            health_message = "No critical errors detected."
        elif critical_rate < 0.1:
            health_status = "good"
            health_message = f"{total_critical} critical errors detected."
        elif critical_rate < 1:
            health_status = "warning"
            health_message = f"{total_critical} critical errors - investigate connection failures."
        elif critical_rate < 5:
            health_status = "degraded"
            health_message = f"{total_critical} critical errors - service health may be impacted."
        else:
            health_status = "critical"
            health_message = f"{total_critical} critical errors - immediate attention required!"
        
        # Note: This is from limited sample
        if len(communications) >= 1000:
            health_message += " (Note: Based on sample of 1000 connections)"
        
        return ErrorStatsResponse(
            total_errors=total_errors,
            total_critical=total_critical,
            total_warnings=total_warnings,
            critical_by_type=critical_by_type,
            warnings_by_type=warnings_by_type,
            total_flows=total_flows,
            error_rate_percent=round(error_rate, 2),
            critical_rate_percent=round(critical_rate, 2),
            health_status=health_status,
            health_message=health_message,
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace
        )
        
    except Exception as e:
        logger.error(f"Neo4j error stats fallback failed: {e}")
        return ErrorStatsResponse(
            total_errors=0,
            total_critical=0,
            total_warnings=0,
            health_status="healthy",
            health_message="Unable to retrieve error statistics",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace
        )


@router.get("/dependencies/stream", tags=["Integration"])
async def find_pod_dependencies(
    analysis_id: Optional[int] = Query(None, description="Analysis ID for scope"),
    cluster_id: Optional[int] = Query(None, description="Cluster ID for scope"),
    pod_name: Optional[str] = Query(None, description="Pod/workload name to search"),
    namespace: Optional[str] = Query(None, description="Namespace to narrow search"),
    owner_name: Optional[str] = Query(None, description="Deployment/StatefulSet/DaemonSet name to search"),
    label_key: Optional[str] = Query(None, description="Label key to match"),
    label_value: Optional[str] = Query(None, description="Label value to match"),
    annotation_key: Optional[str] = Query(None, description="Annotation key to match"),
    annotation_value: Optional[str] = Query(None, description="Annotation value to match"),
    ip: Optional[str] = Query(None, description="Pod IP to search"),
    depth: int = Query(1, ge=1, le=5, description="Traversal depth"),
    format: Optional[str] = Query("json", description="Response format: json, mermaid, dot"),
    current_user: dict = Depends(get_current_user)
):
    """
    Find a pod by any metadata and return upstream/downstream dependencies.
    
    The matched pod is the **upstream**. All pods it connects to are **downstream**.
    All pods that connect TO it are **callers**.
    
    Search by any combination: pod_name, namespace, owner_name, annotation_key/value, label_key/value, ip.
    Use format=mermaid or format=dot for text-based graph output.
    """
    try:
        params = {}
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if pod_name:
            params["pod_name"] = pod_name
        if namespace:
            params["namespace"] = namespace
        if owner_name:
            params["owner_name"] = owner_name
        if label_key:
            params["label_key"] = label_key
        if label_value:
            params["label_value"] = label_value
        if annotation_key:
            params["annotation_key"] = annotation_key
        if annotation_value:
            params["annotation_value"] = annotation_value
        if ip:
            params["ip"] = ip
        params["depth"] = depth
        if format and format in ("mermaid", "dot"):
            params["format"] = format
        
        result = await graph_query_client._call_graph_query(
            "/dependencies/stream",
            params=params
        )
        
        if result:
            if isinstance(result, dict) and result.get("format") == "text":
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse(
                    content=result.get("content", ""),
                    media_type="text/plain"
                )
            return result
        
        raise HTTPException(
            status_code=503,
            detail="Graph query service unavailable"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to find pod dependencies", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find pod dependencies: {str(e)}"
        )


@router.post("/dependencies/batch", tags=["Integration"])
async def batch_find_dependencies(
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """Batch find dependencies for multiple services in one request."""
    try:
        result = await graph_query_client._call_graph_query(
            "/dependencies/batch",
            json_body=request
        )
        if result:
            return result
        raise HTTPException(status_code=503, detail="Graph query service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to batch find dependencies", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dependencies/diff", tags=["Integration"])
async def diff_dependencies(
    analysis_id_before: str = Query(..., description="Analysis ID before"),
    analysis_id_after: str = Query(..., description="Analysis ID after"),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    cluster_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """Compare dependencies between two analysis runs."""
    try:
        params = {
            "analysis_id_before": analysis_id_before,
            "analysis_id_after": analysis_id_after,
        }
        if pod_name:
            params["pod_name"] = pod_name
        if namespace:
            params["namespace"] = namespace
        if owner_name:
            params["owner_name"] = owner_name
        if cluster_id:
            params["cluster_id"] = str(cluster_id)

        result = await graph_query_client._call_graph_query(
            "/dependencies/diff",
            params=params
        )
        if result:
            return result
        raise HTTPException(status_code=503, detail="Graph query service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to diff dependencies", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dependencies/summary", tags=["Integration"])
async def get_dependency_summary(
    analysis_ids: List[int] = Query(..., description="Analysis IDs (required, at least one)"),
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    label_key: Optional[str] = Query(None),
    label_value: Optional[str] = Query(None),
    annotation_key: Optional[str] = Query(None),
    annotation_value: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=5),
    current_user: dict = Depends(get_current_user)
):
    """
    AI-agent-friendly dependency summary grouped by service category.
    Designed for CI/CD pipelines and AI code agents.
    Requires at least one analysis_id and one search parameter.
    """
    try:
        params = {
            "analysis_ids": [str(a) for a in analysis_ids],
            "depth": depth,
        }
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if pod_name:
            params["pod_name"] = pod_name
        if namespace:
            params["namespace"] = namespace
        if owner_name:
            params["owner_name"] = owner_name
        if label_key:
            params["label_key"] = label_key
        if label_value:
            params["label_value"] = label_value
        if annotation_key:
            params["annotation_key"] = annotation_key
        if annotation_value:
            params["annotation_value"] = annotation_value
        if ip:
            params["ip"] = ip

        result = await graph_query_client._call_graph_query(
            "/dependencies/summary",
            params=params
        )
        if result:
            return result
        raise HTTPException(status_code=503, detail="Graph query service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dependency summary", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dependencies/impact", tags=["Integration"])
async def get_dependency_impact(
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    label_key: Optional[str] = Query(None),
    label_value: Optional[str] = Query(None),
    annotation_key: Optional[str] = Query(None),
    annotation_value: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=5),
    change_type: str = Query("image_update", description="Change type: image_update, config_change, scale_change, delete"),
    current_user: dict = Depends(get_current_user)
):
    """
    Combined dependency lookup + impact/risk assessment in a single response.
    AI Agent one-stop-shop endpoint.
    """
    try:
        params = {}
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if pod_name:
            params["pod_name"] = pod_name
        if namespace:
            params["namespace"] = namespace
        if owner_name:
            params["owner_name"] = owner_name
        if label_key:
            params["label_key"] = label_key
        if label_value:
            params["label_value"] = label_value
        if annotation_key:
            params["annotation_key"] = annotation_key
        if annotation_value:
            params["annotation_value"] = annotation_value
        if ip:
            params["ip"] = ip
        params["depth"] = depth

        dep_result = await graph_query_client._call_graph_query(
            "/dependencies/stream",
            params=params
        )

        if not dep_result or not dep_result.get("success"):
            detail = dep_result.get("error", "No matching pod found") if isinstance(dep_result, dict) else "No matching pod found"
            raise HTTPException(status_code=404, detail=detail)

        first = dep_result.get("results", [{}])[0] if dep_result.get("results") else {}
        upstream = first.get("upstream", {})
        downstream = first.get("downstream", [])
        callers = first.get("callers", [])

        direct_count = len(downstream) + len(callers)
        indirect_count = sum(1 for d in downstream if d.get("hop_count", 1) > 1)
        indirect_count += sum(1 for c in callers if c.get("hop_count", 1) > 1)

        critical_deps = []
        for d in downstream:
            comm = d.get("communication") or {}
            if comm.get("is_critical"):
                critical_deps.append(comm.get("service_type") or comm.get("service_category") or d.get("pod_name", "unknown"))

        now = datetime.utcnow()
        is_business_hours = 9 <= now.hour <= 18 and now.weekday() < 5

        from routers.blast_radius import calculate_risk_score, generate_suggested_actions
        risk_score, risk_level, _confidence = calculate_risk_score(
            change_type=change_type,
            direct_count=direct_count,
            indirect_count=indirect_count,
            critical_services=sorted(set(critical_deps)),
            is_business_hours=is_business_hours,
        )
        suggested_actions = generate_suggested_actions(
            risk_level=risk_level,
            direct_count=direct_count,
            indirect_count=indirect_count,
            critical_services=sorted(set(critical_deps)),
            change_type=change_type,
            is_business_hours=is_business_hours,
        )

        recommendation = "proceed"
        if risk_score >= 70:
            recommendation = "block"
        elif risk_score >= 40:
            recommendation = "caution"

        return {
            "success": True,
            "service": upstream,
            "dependencies": {
                "downstream": downstream,
                "callers": callers,
                "downstream_count": len(downstream),
                "callers_count": len(callers),
            },
            "impact_assessment": {
                "risk_score": risk_score,
                "risk_level": risk_level.value if hasattr(risk_level, 'value') else str(risk_level),
                "blast_radius": direct_count,
                "critical_dependencies": sorted(set(critical_deps)),
                "recommendation": recommendation,
                "suggested_actions": [a.model_dump() if hasattr(a, 'model_dump') else (a.dict() if hasattr(a, 'dict') else a) for a in suggested_actions],
                "change_type": change_type,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dependency impact", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
