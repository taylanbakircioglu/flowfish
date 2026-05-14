"""Graph Database Query Engine - Neo4j Implementation"""

import json
import logging
import re
from collections import defaultdict
from fnmatch import fnmatch
from typing import Dict, Any, List, Optional, Tuple
from neo4j import GraphDatabase, Driver, Session, Result
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import settings

logger = logging.getLogger(__name__)


# Module-level annotation noise filter helpers (audit v3 — extracted from nested
# scope so the same filter list is shared between the L4 dependency_summary path
# and the new L7 dependency_summary annotation filter. Pure functions, stateless.
# Audit B-22 / E-10).
_NOISE_ANNOTATION_PREFIXES: Tuple[str, ...] = (
    'kubectl.kubernetes.io/',
    'kubernetes.io/',
    'openshift.io/',
    'openshift.openshift.io/',
    'k8s.v1.cni.cncf.io/',
    'k8s.ovn.org/',
    'seccomp.security.alpha.kubernetes.io/',
)


def _filter_summary_annotations(ann: Optional[dict]) -> dict:
    """Drop infrastructure/noise annotations and oversize values (>=500 chars).

    Mirrors the previous nested helper inside the L4 dependency_summary
    aggregator so L4 and L7 summary responses agree on what counts as
    operator-visible annotation metadata.
    """
    if not ann or not isinstance(ann, dict):
        return ann or {}
    return {
        k: v for k, v in ann.items()
        if not any(k.startswith(p) for p in _NOISE_ANNOTATION_PREFIXES)
        and len(str(v)) < 500
    }


def _parse_metadata_field(raw) -> dict:
    """Parse a Neo4j-stored labels/annotations field (JSON string or dict).

    L7Workload nodes persist labels/annotations as JSON-encoded strings
    (services/graph-writer/app/l7_graph_builder.py json.dumps), but L4
    Workload nodes may already arrive as dicts. We tolerate both forms and
    fall back to {} on malformed JSON so a single corrupt row never breaks
    a filter sweep.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    return {}


def _glob_match_metadata(
    metadata: dict,
    key: Optional[str],
    value: Optional[str],
) -> bool:
    """Test whether ``metadata`` contains an entry matching key/value.

    Mirrors the L4 ``find_pod_dependencies`` post-filter semantics so the new
    L7 filter path behaves identically (audit B-2 / E-13):
      * No key      → match (filter inactive).
      * Key has glob (``*``/``?``) → fnmatch against every key.
      * Value empty or ``*`` → any value matches once key is found.
      * Value has glob → fnmatch against the stringified value.
      * Otherwise → exact equality.
    """
    if not key:
        return True
    key_has_glob = '*' in key or '?' in key
    if key_has_glob:
        hit_keys = [k for k in metadata if fnmatch(k, key)]
    else:
        hit_keys = [key] if key in metadata else []
    if not hit_keys:
        return False
    if not value or value == '*':
        return True
    value_has_glob = '*' in value or '?' in value
    for k in hit_keys:
        v = str(metadata[k])
        if value_has_glob:
            if fnmatch(v, value):
                return True
        elif v == value:
            return True
    return False


class GraphQueryEngine:
    """Neo4j graph database query engine"""
    
    def __init__(self):
        self.driver: Optional[Driver] = None
        self.database = settings.neo4j_database
        try:
            self._connect()
        except Exception as e:
            logger.warning(f"⚠️  Neo4j connection failed (will retry on first query): {e}")
    
    def _connect(self):
        """Connect to Neo4j database"""
        try:
            self.driver = GraphDatabase.driver(
                settings.neo4j_bolt_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                max_connection_pool_size=10,
                connection_timeout=settings.query_timeout,
                max_transaction_retry_time=settings.query_timeout
            )
            
            # Verify connectivity
            self.driver.verify_connectivity()
            
            logger.info(f"✅ Connected to Neo4j: {settings.neo4j_bolt_uri} (database: {self.database})")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Neo4j: {e}")
            raise
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Cypher query and return results"""
        if not self.driver:
            try:
                self._connect()
            except Exception as e:
                return {"success": False, "error": f"Connection failed: {str(e)}"}
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters or {})
                
                # Convert result to list of dictionaries
                records = []
                for record in result:
                    records.append(dict(record))
                
                return {
                    "success": True,
                    "data": records,
                    "count": len(records)
                }
                
        except Neo4jError as e:
            logger.error(f"❌ Neo4j query error: {e}")
            return {
                "success": False,
                "error": f"Query failed: {e.message}",
                "code": e.code
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_workload_dependencies(self, workload_id: str, depth: int = 1) -> Dict[str, Any]:
        """Get dependencies of a workload (downstream)"""
        query = """
        MATCH path = (w:Workload {id: $workload_id})-[r*1..$depth]->(dep)
        WHERE ALL(rel IN relationships(path) WHERE rel.is_active = true)
        RETURN 
            w.id AS source_id,
            w.name AS source_name,
            w.kind AS source_kind,
            [node IN nodes(path)[1..] | {
                id: node.id,
                name: node.name,
                kind: node.kind,
                namespace: node.namespace
            }] AS dependencies,
            [rel IN relationships(path) | type(rel)] AS relationship_types,
            length(path) AS path_length
        ORDER BY path_length
        LIMIT 100
        """
        
        return self.execute_query(query, {"workload_id": workload_id, "depth": depth})
    
    def get_workload_dependents(self, workload_id: str, depth: int = 1) -> Dict[str, Any]:
        """Get dependents of a workload (upstream)"""
        query = """
        MATCH path = (dep)-[r*1..$depth]->(w:Workload {id: $workload_id})
        WHERE ALL(rel IN relationships(path) WHERE rel.is_active = true)
        RETURN 
            w.id AS target_id,
            w.name AS target_name,
            w.kind AS target_kind,
            [node IN nodes(path)[..-1] | {
                id: node.id,
                name: node.name,
                kind: node.kind,
                namespace: node.namespace
            }] AS dependents,
            [rel IN relationships(path) | type(rel)] AS relationship_types,
            length(path) AS path_length
        ORDER BY path_length
        LIMIT 100
        """
        
        return self.execute_query(query, {"workload_id": workload_id, "depth": depth})
    
    def get_communications(
        self,
        source_id: Optional[str] = None,
        destination_id: Optional[str] = None,
        namespace: Optional[str] = None,
        protocol: Optional[str] = None,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get communications between workloads"""
        
        conditions = []
        params = {"limit": limit}
        
        # Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
        # Filter by analysis_id if provided - match both single and multi-cluster formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append(
                "(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix OR "
                "src.analysis_id = $analysis_id OR src.analysis_id STARTS WITH $analysis_id_prefix)"
            )
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        # Filter by cluster_id if provided (optional for multi-cluster)
        if cluster_id:
            conditions.append("(src.cluster_id = $cluster_id OR comm.cluster_id = $cluster_id)")
            params["cluster_id"] = str(cluster_id)
        
        if source_id:
            conditions.append("src.id = $source_id")
            params["source_id"] = source_id
        
        if destination_id:
            conditions.append("dst.id = $destination_id")
            params["destination_id"] = destination_id
        
        if namespace:
            # Include edges where source is in namespace, OR destination is in namespace,
            # OR source is in namespace AND destination is external (ExternalEndpoint)
            conditions.append(
                "(src.namespace = $namespace OR dst.namespace = $namespace OR "
                "(src.namespace = $namespace AND (dst:ExternalEndpoint OR dst.namespace = 'external')))"
            )
            params["namespace"] = namespace
        
        if protocol:
            conditions.append("comm.protocol = $protocol")
            params["protocol"] = protocol
        
        # Time range filtering - filter by last_seen timestamp
        # Note: last_seen is stored as epoch milliseconds (from Neo4j timestamp() function)
        # We need to convert ISO datetime string to epoch ms for comparison
        if start_time:
            conditions.append("comm.last_seen >= datetime($start_time).epochMillis")
            params["start_time"] = start_time
        
        if end_time:
            conditions.append("comm.last_seen <= datetime($end_time).epochMillis")
            params["end_time"] = end_time
        
        # Build WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        # Query ALL communications including to ExternalEndpoints
        # Note: Use same pattern as get_communication_stats (no label constraint)
        # This works for both single-cluster and multi-cluster analyses
        query = f"""
        MATCH (src)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE {where_clause}
        RETURN 
            src.id AS source_id,
            src.name AS source_name,
            src.kind AS source_kind,
            src.namespace AS source_namespace,
            src.ip AS source_ip,
            src.node AS source_node,
            src.labels AS source_labels,
            src.annotations AS source_annotations,
            src.owner_kind AS source_owner_kind,
            src.owner_name AS source_owner_name,
            src.network_type AS source_network_type,
            src.is_external AS source_is_external,
            src.resolution_source AS source_resolution_source,
            src.pod_uid AS source_pod_uid,
            src.host_ip AS source_host_ip,
            src.container AS source_container,
            src.image AS source_image,
            src.service_account AS source_service_account,
            src.phase AS source_phase,
            dst.id AS destination_id,
            dst.name AS destination_name,
            dst.kind AS destination_kind,
            dst.namespace AS destination_namespace,
            dst.ip AS destination_ip,
            dst.node AS destination_node,
            dst.labels AS destination_labels,
            dst.annotations AS destination_annotations,
            dst.owner_kind AS destination_owner_kind,
            dst.owner_name AS destination_owner_name,
            dst.network_type AS destination_network_type,
            dst.is_external AS destination_is_external,
            dst.resolution_source AS destination_resolution_source,
            dst.pod_uid AS destination_pod_uid,
            dst.host_ip AS destination_host_ip,
            dst.container AS destination_container,
            dst.image AS destination_image,
            dst.service_account AS destination_service_account,
            dst.phase AS destination_phase,
            // Per-node cluster_id projection. Without this the backend
            // transformer fell back to the request-level `cluster_id`
            // parameter, which is empty on multi-cluster queries -> every
            // edge then carried `cluster_id="1"` and the Network Map
            // collapsed all clusters into one. Coerce via toString in
            // case Neo4j stored it as integer in older datasets.
            toString(src.cluster_id) AS source_cluster_id,
            toString(dst.cluster_id) AS destination_cluster_id,
            comm.protocol AS protocol,
            comm.destination_port AS destination_port,
            comm.port AS port,
            comm.request_count AS request_count,
            comm.bytes_transferred AS bytes_transferred,
            comm.avg_latency_ms AS avg_latency_ms,
            comm.risk_level AS risk_level,
            comm.risk_score AS risk_score,
            comm.first_seen AS first_seen,
            comm.last_seen AS last_seen,
            comm.analysis_id AS analysis_id,
            comm.error_count AS error_count,
            comm.retransmit_count AS retransmit_count,
            comm.last_error_type AS last_error_type
        ORDER BY comm.last_seen DESC
        LIMIT $limit
        """
        
        logger.info(f"[GET_COMMS] Executing query with params: {params}")
        logger.info(f"[GET_COMMS] WHERE clause: {where_clause}")
        
        result = self.execute_query(query, params)
        
        data_count = len(result.get("data", [])) if result else 0
        logger.info(f"[GET_COMMS] Query result: success={result.get('success')}, data_count={data_count}")
        
        return result
    
    def get_communication_count(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None
    ) -> int:
        """Get total count of communications without limit (for smart edge limit calculation)"""
        
        conditions = []
        params = {}
        
        # Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append(
                "(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix OR "
                "src.analysis_id = $analysis_id OR src.analysis_id STARTS WITH $analysis_id_prefix)"
            )
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        # Filter by cluster_id if provided
        if cluster_id:
            conditions.append("(src.cluster_id = $cluster_id OR comm.cluster_id = $cluster_id)")
            params["cluster_id"] = str(cluster_id)
        
        if namespace:
            conditions.append(
                "(src.namespace = $namespace OR dst.namespace = $namespace OR "
                "(src.namespace = $namespace AND (dst:ExternalEndpoint OR dst.namespace = 'external')))"
            )
            params["namespace"] = namespace
        
        # Build WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        # COUNT query - no limit needed
        # Use same pattern as get_communication_stats (no label constraint)
        query = f"""
        MATCH (src)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE {where_clause}
        RETURN count(comm) AS total_count
        """
        
        result = self.execute_query(query, params)
        
        if result.get("success") and result.get("data"):
            return result["data"][0].get("total_count", 0)
        return 0
    
    def get_cross_namespace_communications(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get cross-namespace communications (potential security risk)"""
        
        conditions = [
            "src.namespace <> dst.namespace",
            "comm.is_active = true",
            "NOT src.namespace IN ['kube-system', 'kube-public']"
        ]
        params = {"limit": limit}
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("src.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE (dst:Workload OR dst:ExternalEndpoint) AND {where_clause}
        RETURN 
            src.namespace AS source_namespace,
            src.name AS source_name,
            COALESCE(dst.namespace, 'external') AS destination_namespace,
            dst.name AS destination_name,
            comm.protocol AS protocol,
            COALESCE(comm.destination_port, comm.port, 0) AS port,
            comm.risk_score AS risk_score,
            comm.analysis_id AS analysis_id
        ORDER BY comm.risk_score DESC
        LIMIT $limit
        """
        
        return self.execute_query(query, params)
    
    def get_external_communications(
        self,
        namespace: Optional[str] = None,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get external communications"""
        
        conditions = ["comm.is_active = true"]
        params = {"limit": limit}
        
        if namespace:
            conditions.append("src.namespace = $namespace")
            params["namespace"] = namespace
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("src.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(ext:ExternalEndpoint)
        WHERE {where_clause}
        RETURN 
            src.name AS source_name,
            src.namespace AS source_namespace,
            ext.ip_address AS external_ip,
            ext.hostname AS external_hostname,
            comm.destination_port AS port,
            comm.protocol AS protocol,
            comm.request_count AS request_count,
            comm.analysis_id AS analysis_id
        ORDER BY comm.last_seen DESC
        LIMIT $limit
        """
        
        return self.execute_query(query, params)
    
    def get_high_risk_communications(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get high-risk communications"""
        
        conditions = [
            "comm.risk_level IN ['high', 'critical']",
            "comm.is_active = true"
        ]
        params = {"limit": limit}
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("src.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE {where_clause}
        RETURN 
            src.name AS source_name,
            src.namespace AS source_namespace,
            dst.name AS destination_name,
            comm.protocol AS protocol,
            comm.destination_port AS port,
            comm.risk_level AS risk_level,
            comm.risk_score AS risk_score,
            comm.risk_factors AS risk_factors,
            comm.analysis_id AS analysis_id
        ORDER BY comm.risk_score DESC
        LIMIT $limit
        """
        
        return self.execute_query(query, params)
    
    def get_workload_by_id(self, workload_id: str) -> Dict[str, Any]:
        """Get workload details by ID"""
        query = """
        MATCH (w:Workload {id: $workload_id})
        RETURN w
        """
        
        return self.execute_query(query, {"workload_id": workload_id})
    
    def get_workloads_by_namespace(
        self,
        namespace: str,
        kind: Optional[str] = None,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all workloads in a namespace"""
        
        conditions = [
            "w.namespace = $namespace",
            "w.is_active = true"
        ]
        params = {"namespace": namespace}
        
        if kind:
            conditions.append("w.kind = $kind")
            params["kind"] = kind
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(w.analysis_id = $analysis_id OR w.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("w.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (w:Workload)
        WHERE {where_clause}
        RETURN w
        ORDER BY w.name
        """
        
        return self.execute_query(query, params)
    
    def get_workloads(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Get workloads with optional filters"""
        
        conditions = ["w.is_active = true"]
        params = {"limit": limit}
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(w.analysis_id = $analysis_id OR w.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("w.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        if namespace:
            conditions.append("w.namespace = $namespace")
            params["namespace"] = namespace
        
        if kind:
            conditions.append("w.kind = $kind")
            params["kind"] = kind
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (w:Workload)
        WHERE {where_clause}
        RETURN 
            w.id AS id,
            w.name AS name,
            w.namespace AS namespace,
            w.kind AS kind,
            w.cluster_id AS cluster_id,
            w.analysis_id AS analysis_id,
            w.ip AS ip,
            w.status AS status,
            w.labels AS labels,
            w.annotations AS annotations,
            w.created_at AS created_at
        ORDER BY w.namespace, w.name
        LIMIT $limit
        """
        
        result = self.execute_query(query, params)
        if result.get("success") and result.get("data"):
            for record in result["data"]:
                for field in ("labels", "annotations"):
                    raw = record.get(field)
                    if isinstance(raw, str):
                        try:
                            record[field] = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            record[field] = {}
                    elif not raw:
                        record[field] = {}
        return result
    
    def get_dependency_graph(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        depth: int = 2,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get dependency graph with nodes and edges for visualization
        
        Args:
            search: Optional search term (min 3 chars) to filter nodes by name, namespace,
                    id, ip, host_ip, or edge port.
                    When provided, limit is increased to ensure all matching results are returned.
        
        Returns:
            Dict with 'nodes' and 'edges' lists
        """
        conditions = []
        params = {}
        
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        
        # Multi-cluster support: set up both analysis_id and prefix for pattern matching
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if namespace:
            params["namespace"] = namespace
        
        # Server-side search: filter by node name, namespace, id, ip, or edge port
        # Only active for 3+ character searches to avoid overly broad matches
        search_condition = ""
        if search and len(search) >= 3:
            params["search"] = search.lower()
            search_condition = """
            AND (
                toLower(src.name) CONTAINS $search OR
                toLower(src.namespace) CONTAINS $search OR
                toLower(src.id) CONTAINS $search OR
                toLower(coalesce(src.ip, '')) CONTAINS $search OR
                toLower(coalesce(src.host_ip, '')) CONTAINS $search OR
                toLower(dst.name) CONTAINS $search OR
                toLower(dst.namespace) CONTAINS $search OR
                toLower(dst.id) CONTAINS $search OR
                toLower(coalesce(dst.ip, '')) CONTAINS $search OR
                toLower(coalesce(dst.host_ip, '')) CONTAINS $search OR
                toString(coalesce(r.port, 0)) CONTAINS $search
            )
            """
        
        # Build WHERE clause for edges
        edge_conditions = []
        if cluster_id:
            edge_conditions.append("(r.cluster_id = $cluster_id)")
        if analysis_id:
            # Multi-cluster support: match both single and multi-cluster analysis_id formats
            edge_conditions.append("(r.analysis_id = $analysis_id OR r.analysis_id STARTS WITH $analysis_id_prefix)")
        if namespace:
            # CRITICAL FIX: At least ONE endpoint must be in the selected namespace
            # This prevents external-to-external edges that have no connection to the filtered namespace
            # 
            # Edge is included if:
            # - At least one endpoint is in the selected namespace (src OR dst)
            # - AND both endpoints are either in namespace OR external (prevents cross-namespace leaks)
            #
            # Examples (namespace = 'flowfish'):
            # - flowfish → flowfish: OK (both in namespace)
            # - flowfish → external: OK (one in namespace)
            # - external → flowfish: OK (one in namespace)
            # - external → external: BLOCKED (neither in namespace - causes floating edges!)
            edge_conditions.append(
                "(src.namespace = $namespace OR dst.namespace = $namespace)"
            )
        
        edge_where = " AND ".join(edge_conditions) if edge_conditions else "true"
        
        # When search is active, increase limit to get all matching results
        # Normal: 5000 (performance), Search: 50000 (find all matches)
        effective_limit = 50000 if search and len(search) >= 3 else settings.max_results
        
        # ============================================================================
        # EDGE-FIRST APPROACH: Derive nodes FROM edges
        # ============================================================================
        # This ensures:
        # 1. Only pods with active communication in this analysis are shown
        # 2. No floating edges (every edge endpoint has a node by definition)
        # 3. No analysis_id filtering issues for nodes (pods from old analyses visible)
        #
        # Flow:
        # 1. Get all edges (filtered by analysis_id + namespace + search)
        # 2. Collect node IDs from edge endpoints
        # 3. Fetch node details for those IDs only
        # ============================================================================
        
        # Step 1: Get all edges first
        # Get COMMUNICATES_WITH edges
        comm_edges_query = f"""
        MATCH (src)-[r:COMMUNICATES_WITH]->(dst)
        WHERE {edge_where}
        {search_condition}
        RETURN DISTINCT
            src.id AS source_id,
            dst.id AS target_id,
            'COMMUNICATES_WITH' AS edge_type,
            COALESCE(r.protocol, 'TCP') AS protocol,
            COALESCE(r.app_protocol, r.protocol, 'TCP') AS app_protocol,
            COALESCE(r.port, r.destination_port, 0) AS port,
            COALESCE(r.request_count, 1) AS request_count,
            COALESCE(r.error_count, 0) AS error_count,
            COALESCE(r.retransmit_count, 0) AS retransmit_count,
            r.last_error_type AS last_error_type
        ORDER BY request_count DESC, source_id, target_id
        LIMIT {effective_limit}
        """
        
        comm_result = self.execute_query(comm_edges_query, params)
        edges = comm_result.get("data", []) if comm_result.get("success") else []
        
        logger.info(f"[EDGE_FETCH] COMMUNICATES_WITH: {len(edges)} edges")
        
        # Get DNS query edges (DNS targets are always external)
        # All DNS edges go to external endpoints, so fetch all with reasonable limit
        dns_edges_query = f"""
        MATCH (src)-[r:QUERIES_DNS]->(dst)
        WHERE {edge_where}
        {search_condition}
        RETURN DISTINCT
            src.id AS source_id,
            dst.id AS target_id,
            'QUERIES_DNS' AS edge_type,
            'DNS' AS protocol,
            'DNS' AS app_protocol,
            53 AS port,
            COALESCE(r.request_count, 1) AS request_count,
            0 AS error_count,
            0 AS retransmit_count,
            null AS last_error_type
        ORDER BY request_count DESC, source_id, target_id
        LIMIT {effective_limit}
        """
        
        dns_result = self.execute_query(dns_edges_query, params)
        dns_edges = dns_result.get("data", []) if dns_result.get("success") else []
        logger.info(f"[EDGE_FETCH] QUERIES_DNS: {len(dns_edges)} edges")
        
        # Get TLS connection edges
        tls_edges_query = f"""
        MATCH (src)-[r:TLS_CONNECTS]->(dst)
        WHERE {edge_where}
        {search_condition}
        RETURN DISTINCT
            src.id AS source_id,
            dst.id AS target_id,
            'TLS_CONNECTS' AS edge_type,
            'TLS' AS protocol,
            'TLS' AS app_protocol,
            COALESCE(r.port, r.destination_port, 443) AS port,
            COALESCE(r.request_count, 1) AS request_count,
            0 AS error_count,
            0 AS retransmit_count,
            null AS last_error_type
        ORDER BY request_count DESC, source_id, target_id
        LIMIT {effective_limit}
        """
        
        tls_result = self.execute_query(tls_edges_query, params)
        tls_edges = tls_result.get("data", []) if tls_result.get("success") else []
        
        logger.info(f"[EDGE_FETCH] TLS_CONNECTS: {len(tls_edges)} edges")
        
        # Get LISTENS_ON edges (service endpoints)
        listen_edges_query = f"""
        MATCH (src)-[r:LISTENS_ON]->(dst)
        WHERE {edge_where}
        {search_condition}
        RETURN DISTINCT
            src.id AS source_id,
            dst.id AS target_id,
            'LISTENS_ON' AS edge_type,
            COALESCE(r.protocol, 'TCP') AS protocol,
            COALESCE(r.app_protocol, r.protocol, 'TCP') AS app_protocol,
            COALESCE(r.port, r.bind_port, 0) AS port,
            COALESCE(r.request_count, 1) AS request_count,
            0 AS error_count,
            0 AS retransmit_count,
            null AS last_error_type
        ORDER BY request_count DESC, source_id, target_id
        LIMIT {effective_limit}
        """
        
        listen_result = self.execute_query(listen_edges_query, params)
        listen_edges = listen_result.get("data", []) if listen_result.get("success") else []
        logger.info(f"[EDGE_FETCH] LISTENS_ON: {len(listen_edges)} edges")
        
        # Combine all edges
        all_edges = edges + dns_edges + tls_edges + listen_edges
        
        # Step 2: Collect all node IDs from edges
        edge_source_ids = {e.get("source_id") for e in all_edges if e.get("source_id")}
        edge_target_ids = {e.get("target_id") for e in all_edges if e.get("target_id")}
        all_edge_node_ids = edge_source_ids | edge_target_ids
        
        logger.warning(f"[GRAPH_QUERY_DEBUG] Total edges: {len(all_edges)}, unique node IDs from edges: {len(all_edge_node_ids)}")
        logger.warning(f"[GRAPH_QUERY_DEBUG] Namespace filter: {namespace}, analysis_id: {analysis_id}, search: {search}, limit: {effective_limit}")
        
        # Step 3: Fetch node details for edge endpoints only
        # No analysis_id filter for nodes - we already filtered edges by analysis_id
        nodes = []
        if all_edge_node_ids:
            node_ids_list = list(all_edge_node_ids)
            nodes_query = """
            MATCH (w)
            WHERE w.id IN $node_ids
            RETURN DISTINCT
                w.id AS id,
                COALESCE(w.name, 'unknown') AS name,
                CASE WHEN w.owner_kind = 'Service' THEN 'Service' ELSE COALESCE(w.kind, labels(w)[0], 'Workload') END AS kind,
                COALESCE(w.namespace, 'external') AS namespace,
                COALESCE(w.cluster_id, '1') AS cluster_id,
                COALESCE(w.status, 'unknown') AS status,
                w.labels AS labels,
                w.annotations AS annotations,
                COALESCE(w.is_external, false) AS is_external,
                w.ip AS ip,
                w.host_ip AS host_ip,
                w.owner_kind AS owner_kind,
                w.owner_name AS owner_name,
                w.node AS node,
                w.network_type AS network_type,
                w.resolution_source AS resolution_source,
                w.pod_uid AS pod_uid,
                w.container AS container,
                w.image AS image,
                w.service_account AS service_account,
                w.phase AS phase
            """
            nodes_result = self.execute_query(nodes_query, {"node_ids": node_ids_list})
            nodes = nodes_result.get("data", []) if nodes_result.get("success") else []
            
            logger.warning(f"[GRAPH_QUERY_DEBUG] Fetched {len(nodes)} nodes for {len(node_ids_list)} edge endpoints")
        
        # Step 4: Create synthetic nodes for any missing endpoints (edge endpoints not in Neo4j)
        existing_node_ids = {n.get("id") for n in nodes if n.get("id")}
        missing_node_ids = all_edge_node_ids - existing_node_ids
        
        if missing_node_ids:
            logger.warning(f"[GRAPH_QUERY_DEBUG] Creating {len(missing_node_ids)} synthetic nodes for missing endpoints")
            # Create synthetic nodes for missing endpoints
            # Parse node ID format: analysis_id:cluster_id:namespace:workload (4-part)
            # or legacy: cluster_id:namespace:workload (3-part)
            for node_id in missing_node_ids:
                parts = node_id.split(":", 3)  # Split into max 4 parts
                if len(parts) >= 4:
                    # New format: analysis_id:cluster_id:namespace:workload
                    _, node_cluster, node_ns, node_name = parts[0], parts[1], parts[2], parts[3]
                elif len(parts) == 3:
                    node_cluster, node_ns, node_name = parts[0], parts[1], parts[2]
                elif len(parts) == 2:
                    node_cluster, node_ns, node_name = "1", parts[0], parts[1]
                else:
                    node_cluster, node_ns, node_name = "1", "external", node_id
                
                # Determine network_type based on namespace
                # Must match frontend NETWORK_TYPE_INFO keys exactly
                network_type = None
                if node_ns == "external":
                    network_type = "External-IP"
                elif node_ns == "cluster-network":
                    # Could be Pod-Network or Service-Network, default to Service
                    network_type = "Service-Network"
                elif node_ns == "internal-network":
                    network_type = "Internal-Network"
                elif node_ns == "sdn-infrastructure":
                    network_type = "SDN-Gateway"
                
                # Infer kind from namespace
                if node_ns == "external":
                    synth_kind = "External"
                elif node_ns in ("sdn-infrastructure", "cluster-network", "service-network"):
                    synth_kind = "Infrastructure"
                elif node_ns in ("internal-network", "datacenter"):
                    synth_kind = "DataCenter"
                else:
                    synth_kind = "Pod"

                synthetic_node = {
                    "id": node_id,
                    "name": node_name,
                    "kind": synth_kind,
                    "namespace": node_ns,
                    "cluster_id": node_cluster,
                    "status": "unknown",
                    "labels": {},
                    "is_external": node_ns == "external",
                    "ip": node_name if self._is_ip_address(node_name) else None,
                    "host_ip": None,
                    "owner_kind": None,
                    "owner_name": None,
                    "node": None,
                    "network_type": network_type,
                    "resolution_source": "synthetic"
                }
                nodes.append(synthetic_node)
            
            logger.warning(f"[GRAPH_QUERY_DEBUG] Created {len(missing_node_ids)} synthetic nodes")
        
        # Final verification - all edges should have valid endpoints now
        final_node_ids = {n.get("id") for n in nodes if n.get("id")}
        edges_before = len(all_edges)
        all_edges = [
            e for e in all_edges
            if e.get("source_id") in final_node_ids and e.get("target_id") in final_node_ids
        ]
        edges_after = len(all_edges)
        
        if edges_before != edges_after:
            # This should not happen with edge-first approach, but log if it does
            logger.error(f"[GRAPH_QUERY_ERROR] Filtered {edges_before - edges_after} edges - this should not happen!")
        
        logger.warning(f"[GRAPH_QUERY_DEBUG] Final result: {len(nodes)} nodes, {len(all_edges)} edges")
        
        # Post-process nodes: parse JSON string fields
        # Neo4j stores labels/annotations as JSON string, but frontend expects object
        for node in nodes:
            # Parse labels from JSON string to dict
            labels_raw = node.get("labels")
            if labels_raw:
                if isinstance(labels_raw, str):
                    try:
                        node["labels"] = json.loads(labels_raw)
                    except (json.JSONDecodeError, TypeError):
                        node["labels"] = {}
                elif not isinstance(labels_raw, dict):
                    node["labels"] = {}
            else:
                node["labels"] = {}
            
            # Parse annotations from JSON string to dict
            annotations_raw = node.get("annotations")
            if annotations_raw:
                if isinstance(annotations_raw, str):
                    try:
                        node["annotations"] = json.loads(annotations_raw)
                    except (json.JSONDecodeError, TypeError):
                        node["annotations"] = {}
                elif not isinstance(annotations_raw, dict):
                    node["annotations"] = {}
            else:
                node["annotations"] = {}
        
        return {
            "nodes": nodes,
            "edges": all_edges,
            "total_nodes": len(nodes),
            "total_edges": len(all_edges)
        }
    
    def get_communication_stats(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get communication statistics including both network and DNS communications
        
        Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
        """
        conditions = []
        params = {}
        
        if cluster_id:
            conditions.append("r.cluster_id = $cluster_id")
            params["cluster_id"] = str(cluster_id)
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(r.analysis_id = $analysis_id OR r.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        # Count COMMUNICATES_WITH edges
        comm_query = f"""
        MATCH (src)-[r:COMMUNICATES_WITH]->(dst)
        WHERE {where_clause}
        RETURN 
            count(r) AS comm_count,
            sum(COALESCE(r.request_count, 1)) AS comm_requests,
            sum(COALESCE(r.bytes_transferred, 0)) AS bytes_transferred,
            sum(COALESCE(r.error_count, 0)) AS total_errors,
            sum(COALESCE(r.retransmit_count, 0)) AS total_retransmits,
            count(DISTINCT src.namespace) AS src_namespaces,
            count(DISTINCT dst.namespace) AS dst_namespaces
        """
        
        comm_result = self.execute_query(comm_query, params)
        
        # Count QUERIES_DNS edges
        dns_query = f"""
        MATCH (src)-[r:QUERIES_DNS]->(dst)
        WHERE {where_clause}
        RETURN 
            count(r) AS dns_count,
            sum(COALESCE(r.request_count, 1)) AS dns_requests
        """
        
        dns_result = self.execute_query(dns_query, params)
        
        # Combine results
        comm_data = comm_result.get("data", [{}])[0] if comm_result.get("success") else {}
        dns_data = dns_result.get("data", [{}])[0] if dns_result.get("success") else {}
        
        total_communications = (comm_data.get("comm_count", 0) or 0) + (dns_data.get("dns_count", 0) or 0)
        total_requests = (comm_data.get("comm_requests", 0) or 0) + (dns_data.get("dns_requests", 0) or 0)
        
        return {
            "total_communications": total_communications,
            "total_request_count": total_requests,
            "total_bytes_transferred": comm_data.get("bytes_transferred", 0) or 0,
            "total_errors": comm_data.get("total_errors", 0) or 0,
            "total_retransmits": comm_data.get("total_retransmits", 0) or 0,
            "unique_namespaces": (comm_data.get("src_namespaces", 0) or 0) + (comm_data.get("dst_namespaces", 0) or 0),
            "network_communications": comm_data.get("comm_count", 0) or 0,
            "dns_queries": dns_data.get("dns_count", 0) or 0,
            "protocol_distribution": {
                "TCP": comm_data.get("comm_count", 0) or 0,
                "DNS": dns_data.get("dns_count", 0) or 0
            },
            "risk_distribution": {},
            "cluster_id": cluster_id,
            "analysis_id": analysis_id
        }
    
    def _l7_match_where(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        protocol: Optional[str] = None,
        protocols: Optional[str] = None,
        rel_alias: str = "r",
        src_alias: str = "src",
    ) -> Tuple[str, Dict[str, Any]]:
        """Build WHERE clause for L7_COMMUNICATES_WITH patterns (multi-cluster analysis_id)."""
        conditions = []
        params: Dict[str, Any] = {}
        aid = str(analysis_id)
        params["analysis_id"] = aid
        params["analysis_id_prefix"] = f"{aid}-"
        conditions.append(
            f"({rel_alias}.analysis_id = $analysis_id OR {rel_alias}.analysis_id STARTS WITH $analysis_id_prefix)"
        )
        if cluster_id:
            conditions.append(f"({src_alias}.cluster = $cluster_id OR dst.cluster = $cluster_id)")
            params["cluster_id"] = str(cluster_id)
        if namespace:
            conditions.append(
                f"({src_alias}.namespace = $namespace OR dst.namespace = $namespace)"
            )
            params["namespace"] = namespace
        # Multi-protocol support: `protocols` (comma-separated) takes priority over `protocol` (single)
        if protocols:
            proto_list = [p.strip().upper() for p in protocols.split(",") if p.strip()]
            if proto_list:
                conditions.append(f"toUpper({rel_alias}.protocol) IN $protocols_list")
                params["protocols_list"] = proto_list
        elif protocol:
            conditions.append(f"toUpper({rel_alias}.protocol) = toUpper($protocol)")
            params["protocol"] = protocol
        return " AND ".join(conditions), params

    def get_l7_dependency_graph(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        protocol: Optional[str] = None,
        protocols: Optional[str] = None,
        namespaces: Optional[str] = None,
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """
        L7 workload dependency graph from Neo4j L7Workload / L7_COMMUNICATES_WITH.
        Returns {"nodes": [...], "edges": [...]}.
        """
        where_clause, params = self._l7_match_where(
            analysis_id, cluster_id=cluster_id, namespace=namespace,
            protocol=protocol, protocols=protocols,
        )
        if namespaces:
            ns_list = [n.strip() for n in namespaces.split(",") if n.strip()]
            if ns_list:
                params["ns_list"] = ns_list
                where_clause += " AND (src.namespace IN $ns_list OR dst.namespace IN $ns_list)"
        meta_return = ""
        if include_metadata:
            meta_return = """,
            src.labels AS src_labels,
            src.annotations AS src_annotations,
            src.owner_kind AS src_owner_kind,
            dst.labels AS dst_labels,
            dst.annotations AS dst_annotations,
            dst.owner_kind AS dst_owner_kind"""
        query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN
            src.id AS src_id,
            src.name AS src_name,
            src.namespace AS src_namespace,
            src.cluster AS src_cluster,
            src.kind AS src_kind,
            src.analysis_id AS src_analysis_id,
            src.network_type AS src_network_type,
            src.is_external AS src_is_external,
            dst.id AS dst_id,
            dst.name AS dst_name,
            dst.namespace AS dst_namespace,
            dst.cluster AS dst_cluster,
            dst.kind AS dst_kind,
            dst.analysis_id AS dst_analysis_id,
            dst.network_type AS dst_network_type,
            dst.is_external AS dst_is_external,
            r.protocol AS protocol,
            r.http_method AS http_method,
            r.http_path AS http_path,
            r.request_count AS request_count,
            r.error_count AS error_count,
            r.avg_latency_ms AS avg_latency_ms,
            r.last_trace_id AS last_trace_id,
            r.last_span_id AS last_span_id,
            r.trace_count AS trace_count{meta_return}
        LIMIT {settings.max_results}
        """
        result = self.execute_query(query, params)
        if not result.get("success"):
            return {"nodes": [], "edges": [], "error": result.get("error")}

        nodes_map: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        def add_node(
            nid: Any,
            name: Any,
            ns: Any,
            cluster: Any,
            kind: Any,
            aid: Any,
            network_type: Any = None,
            is_external: Any = None,
            labels: Any = None,
            annotations: Any = None,
            owner_kind: Any = None,
        ) -> None:
            if not nid:
                return
            sid = str(nid)
            if sid not in nodes_map:
                node: Dict[str, Any] = {
                    "id": sid,
                    "name": name or "",
                    "namespace": ns or "",
                    "cluster": cluster or "",
                    "kind": kind or "",
                    "analysis_id": str(aid) if aid is not None else "",
                    "network_type": str(network_type or ""),
                    "is_external": bool(is_external) if is_external is not None else False,
                }
                if include_metadata:
                    node["labels"] = self._parse_json_field(labels)
                    node["annotations"] = self._parse_json_field(annotations)
                    node["owner_kind"] = str(owner_kind or "")
                nodes_map[sid] = node

        for row in result.get("data", []):
            add_node(
                row.get("src_id"),
                row.get("src_name"),
                row.get("src_namespace"),
                row.get("src_cluster"),
                row.get("src_kind"),
                row.get("src_analysis_id"),
                network_type=row.get("src_network_type"),
                is_external=row.get("src_is_external"),
                labels=row.get("src_labels"),
                annotations=row.get("src_annotations"),
                owner_kind=row.get("src_owner_kind"),
            )
            add_node(
                row.get("dst_id"),
                row.get("dst_name"),
                row.get("dst_namespace"),
                row.get("dst_cluster"),
                row.get("dst_kind"),
                row.get("dst_analysis_id"),
                network_type=row.get("dst_network_type"),
                is_external=row.get("dst_is_external"),
                labels=row.get("dst_labels"),
                annotations=row.get("dst_annotations"),
                owner_kind=row.get("dst_owner_kind"),
            )
            src_id = row.get("src_id")
            dst_id = row.get("dst_id")
            if not src_id or not dst_id:
                continue
            edges.append(
                {
                    "source_id": str(src_id),
                    "target_id": str(dst_id),
                    "protocol": row.get("protocol"),
                    "http_method": row.get("http_method"),
                    "http_path": row.get("http_path"),
                    "request_count": row.get("request_count") or 0,
                    "error_count": row.get("error_count") or 0,
                    "avg_latency_ms": row.get("avg_latency_ms"),
                    "last_trace_id": str(row.get("last_trace_id") or ""),
                    "last_span_id": str(row.get("last_span_id") or ""),
                    "trace_count": int(row.get("trace_count") or 0),
                }
            )

        # SAME_WORKLOAD bridges — surface cross-cluster equivalence to the UI
        # so it can collapse "external placeholder ↔ enriched node" pairs into
        # a single visual entity. Bridges are returned as a sibling list and
        # not embedded into edges so the existing render path stays unchanged.
        # Mirror `_l7_match_where` semantics: match either the parent
        # analysis_id exactly OR any sub-analysis with the "<parent>-..." prefix.
        # Without this, multi-cluster bridges (where each cluster carries a
        # different sub-analysis ID) would not appear in the graph response.
        same_workload_bridges: List[Dict[str, Any]] = []
        try:
            sw_query = """
            MATCH (a:L7Workload)-[sw:SAME_WORKLOAD]->(b:L7Workload)
            WHERE (a.analysis_id = $aid OR a.analysis_id STARTS WITH $aid_prefix)
              AND (b.analysis_id = $aid OR b.analysis_id STARTS WITH $aid_prefix)
            RETURN a.id AS a_id, b.id AS b_id,
                   sw.confidence AS confidence, sw.matched_by AS matched_by,
                   sw.last_trace_id AS last_trace_id
            """
            sw_result = self.execute_query(
                sw_query,
                {"aid": str(analysis_id), "aid_prefix": f"{analysis_id}-"},
            )
            if sw_result.get("success"):
                for sw_row in sw_result.get("data", []):
                    a_id, b_id = sw_row.get("a_id"), sw_row.get("b_id")
                    if not a_id or not b_id:
                        continue
                    # UI requires both endpoints to be in renderedNodeIds before
                    # drawing the dashed bridge edge, so bridges with only one
                    # endpoint visible would be dropped client-side anyway.
                    # Filtering server-side saves payload size on large graphs.
                    if str(a_id) in nodes_map and str(b_id) in nodes_map:
                        same_workload_bridges.append({
                            "a_id": str(a_id),
                            "b_id": str(b_id),
                            "confidence": str(sw_row.get("confidence") or ""),
                            "matched_by": str(sw_row.get("matched_by") or ""),
                            "last_trace_id": str(sw_row.get("last_trace_id") or ""),
                        })
        except Exception:
            logger.exception("SAME_WORKLOAD bridge query failed (non-fatal)")

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges,
            "same_workload_bridges": same_workload_bridges,
            "total_nodes": len(nodes_map),
            "total_edges": len(edges),
        }

    def get_l7_communication_stats(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregated L7 stats: workloads, edges, requests, errors, avg latency."""
        where_clause, params = self._l7_match_where(
            analysis_id, cluster_id=cluster_id, namespace=None, protocol=None
        )
        stats_query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN
            count(r) AS total_edges,
            sum(coalesce(r.request_count, 0)) AS total_request_count,
            sum(coalesce(r.error_count, 0)) AS total_error_count,
            avg(r.avg_latency_ms) AS avg_latency_ms
        """
        stats_result = self.execute_query(stats_query, params)
        if not stats_result.get("success") or not stats_result.get("data"):
            return {
                "success": False,
                "total_workloads": 0,
                "total_edges": 0,
                "total_request_count": 0,
                "total_error_count": 0,
                "avg_latency_ms": 0.0,
                "error": stats_result.get("error"),
            }
        row0 = stats_result["data"][0]
        ids_query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN collect(DISTINCT src.id) + collect(DISTINCT dst.id) AS node_ids
        """
        ids_result = self.execute_query(ids_query, params)
        node_ids = []
        if ids_result.get("success") and ids_result.get("data"):
            raw = ids_result["data"][0].get("node_ids") or []
            node_ids = list({str(x) for x in raw if x is not None})
        avg_lat = row0.get("avg_latency_ms")
        try:
            avg_lat_f = float(avg_lat) if avg_lat is not None else 0.0
        except (TypeError, ValueError):
            avg_lat_f = 0.0
        return {
            "success": True,
            "total_workloads": len(node_ids),
            "total_edges": int(row0.get("total_edges") or 0),
            "total_request_count": int(row0.get("total_request_count") or 0),
            "total_error_count": int(row0.get("total_error_count") or 0),
            "avg_latency_ms": round(avg_lat_f, 4),
            "analysis_id": str(analysis_id),
            "cluster_id": str(cluster_id) if cluster_id else None,
        }

    def get_l7_dependency_summary(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        include_metadata: bool = True,
        annotation_key: Optional[str] = None,
        annotation_value: Optional[str] = None,
        label_key: Optional[str] = None,
        label_value: Optional[str] = None,
        owner_name: Optional[str] = None,
        pod_name: Optional[str] = None,
        workload_name: Optional[str] = None,
        filter_noise_annotations: bool = False,
    ) -> Dict[str, Any]:
        """
        Per-workload L7 summary: inbound/outbound edge counts, requests, errors, error rate.

        Audit v3 (B-16, B-19, B-22, E-13): when any of ``annotation_*``/``label_*``/
        ``owner_name``/``pod_name``/``workload_name`` is supplied, the response
        includes both the *matched* workloads (``is_matched=True``) and their
        immediate neighbours (``is_matched=False``) so the operator gets the
        same dependency context the L4 path provides via ``find_pod_dependencies``.

        ``owner_name`` is accepted as a backend alias of ``workload_name``;
        if both are passed, ``workload_name`` wins. Both perform a
        case-insensitive substring match for L4 UX parity.

        ``filter_noise_annotations=True`` runs the shared module-level
        ``_filter_summary_annotations`` over each workload's annotations
        in the response so infrastructure-prefixed noise is stripped.
        Defaults to False (backward compat — audit G-8).

        ``include_metadata`` keeps its public contract: when False the
        response omits ``labels``/``annotations``/``owner_kind`` on each
        workload, but the engine still fetches those columns internally
        so server-side filters keep working (audit B-22).
        """
        # Normalise the workload-name alias up front so the rest of the
        # function only deals with `effective_workload_name`.
        effective_workload_name = workload_name or owner_name or None

        # Detect whether any filter is active. We use this to:
        #   * decide if we need to widen the Cypher LIMIT (filter passes drop
        #     rows, so we over-fetch and let Python post-filter narrow back),
        #   * decide whether to emit ``is_matched`` on workloads at all
        #     (avoid breaking the legacy response shape when nobody is
        #     filtering).
        filter_active = any(
            v for v in (
                annotation_key, label_key, label_value, effective_workload_name, pod_name,
            )
        )

        where_clause, params = self._l7_match_where(
            analysis_id, cluster_id=cluster_id, namespace=namespace, protocol=None
        )

        # Cypher CONTAINS prefilter — mirrors the L4 find_pod_dependencies
        # pattern (L7Workload labels/annotations are persisted as JSON
        # strings via graph-writer's json.dumps, so wrapping the key in
        # double quotes makes the prefilter exact-enough to discard rows
        # whose annotation map never references the key. Python post-filter
        # below does the precise glob match.)
        extra_clauses: List[str] = []
        if annotation_key:
            ann_key_prefix = annotation_key.split('*')[0].split('?')[0]
            if ann_key_prefix:
                extra_clauses.append(
                    "(src.annotations CONTAINS $annotation_key_search "
                    "OR dst.annotations CONTAINS $annotation_key_search)"
                )
                params["annotation_key_search"] = f'"{ann_key_prefix}'
        if label_key and label_value:
            extra_clauses.append(
                "(src.labels CONTAINS $label_key_search "
                "OR dst.labels CONTAINS $label_key_search)"
            )
            params["label_key_search"] = f'"{label_key}"'
        elif label_key:
            extra_clauses.append(
                "(src.labels CONTAINS $label_key_search "
                "OR dst.labels CONTAINS $label_key_search)"
            )
            params["label_key_search"] = f'"{label_key}"'
        if effective_workload_name:
            extra_clauses.append(
                "(toLower(src.name) CONTAINS toLower($workload_name) "
                "OR toLower(dst.name) CONTAINS toLower($workload_name))"
            )
            params["workload_name"] = effective_workload_name
        if pod_name:
            extra_clauses.append(
                "(toLower(src.name) CONTAINS toLower($pod_name) "
                "OR toLower(dst.name) CONTAINS toLower($pod_name))"
            )
            params["pod_name"] = pod_name

        if extra_clauses:
            where_clause = where_clause + " AND " + " AND ".join(extra_clauses)

        # We always pull metadata columns from Neo4j so the post-filter has
        # data to work with. The `include_metadata=False` request only
        # affects what we *return* to the caller.
        meta_return = """,
            src.labels AS src_labels, src.annotations AS src_annotations, src.owner_kind AS src_owner_kind,
            dst.labels AS dst_labels, dst.annotations AS dst_annotations, dst.owner_kind AS dst_owner_kind"""

        # Widen LIMIT when filter is active — the prefilter narrows the
        # Cypher result enough that 10x is still a small ceiling, but it
        # gives the Python post-filter room to drop rows without producing
        # a sparse final list. Capped at settings.max_results when no
        # filter is active to preserve historical performance budget.
        effective_limit = (settings.max_results * 10) if filter_active else settings.max_results

        query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN
            src.id AS src_id,
            src.name AS src_name,
            src.namespace AS src_namespace,
            src.cluster AS src_cluster,
            dst.id AS dst_id,
            dst.name AS dst_name,
            dst.namespace AS dst_namespace,
            dst.cluster AS dst_cluster,
            coalesce(r.request_count, 0) AS request_count,
            coalesce(r.error_count, 0) AS error_count{meta_return}
        LIMIT {effective_limit}
        """
        result = self.execute_query(query, params)
        if not result.get("success"):
            return {
                "success": False,
                "workloads": [],
                "error": result.get("error"),
            }

        by_id: Dict[str, Dict[str, Any]] = {}

        def touch(
            wid: Any,
            name: Any,
            ns: Any,
            cluster: Any,
            labels: Any = None,
            annotations: Any = None,
            owner_kind: Any = None,
        ) -> str:
            sid = str(wid) if wid else ""
            if not sid:
                return ""
            if sid not in by_id:
                entry: Dict[str, Any] = {
                    "id": sid,
                    "name": name or "",
                    "namespace": ns or "",
                    "cluster": cluster or "",
                    "inbound_count": 0,
                    "outbound_count": 0,
                    "request_count": 0,
                    "error_count": 0,
                    # Always parse metadata so server-side filters can run.
                    # We strip these from the response below when
                    # include_metadata=False.
                    "labels": _parse_metadata_field(labels),
                    "annotations": _parse_metadata_field(annotations),
                    "owner_kind": str(owner_kind or ""),
                }
                by_id[sid] = entry
            return sid

        for row in result.get("data", []):
            rc = int(row.get("request_count") or 0)
            ec = int(row.get("error_count") or 0)
            s = touch(
                row.get("src_id"), row.get("src_name"), row.get("src_namespace"), row.get("src_cluster"),
                row.get("src_labels"), row.get("src_annotations"), row.get("src_owner_kind"),
            )
            d = touch(
                row.get("dst_id"), row.get("dst_name"), row.get("dst_namespace"), row.get("dst_cluster"),
                row.get("dst_labels"), row.get("dst_annotations"), row.get("dst_owner_kind"),
            )
            if s:
                by_id[s]["outbound_count"] += 1
                by_id[s]["request_count"] += rc
                by_id[s]["error_count"] += ec
            if d:
                by_id[d]["inbound_count"] += 1
                by_id[d]["request_count"] += rc
                by_id[d]["error_count"] += ec

        # Python post-filter — decides which workloads count as ``matched``.
        # The Cypher prefilter is intentionally permissive (CONTAINS over the
        # JSON-encoded property) so the precise glob/equality check happens
        # here. We never drop *rows*; we only annotate workloads with the
        # ``is_matched`` flag so the operator can still see neighbours.
        def _matches(entry: Dict[str, Any]) -> bool:
            if not filter_active:
                return True
            wname = entry.get("name") or ""
            ns = entry.get("namespace") or ""
            ann = entry.get("annotations") or {}
            lbl = entry.get("labels") or {}
            if annotation_key and not _glob_match_metadata(ann, annotation_key, annotation_value):
                return False
            if label_key and not _glob_match_metadata(lbl, label_key, label_value):
                return False
            if effective_workload_name and effective_workload_name.lower() not in wname.lower():
                return False
            if pod_name and pod_name.lower() not in wname.lower():
                return False
            return True

        matched_ids: set = set()
        if filter_active:
            for sid, entry in by_id.items():
                if _matches(entry):
                    matched_ids.add(sid)

        workloads = []
        for w in by_id.values():
            req = w["request_count"]
            err = w["error_count"]
            rate = round((err / req) * 100.0, 4) if req > 0 else 0.0
            entry: Dict[str, Any] = {
                "id": w["id"],
                "name": w["name"],
                "namespace": w["namespace"],
                "cluster": w["cluster"],
                "inbound_count": w["inbound_count"],
                "outbound_count": w["outbound_count"],
                "request_count": req,
                "error_count": err,
                "error_rate_percent": rate,
            }
            if filter_active:
                entry["is_matched"] = w["id"] in matched_ids
            if include_metadata:
                annotations = w.get("annotations", {})
                if filter_noise_annotations:
                    annotations = _filter_summary_annotations(annotations)
                entry["labels"] = w.get("labels", {})
                entry["annotations"] = annotations
                entry["owner_kind"] = w.get("owner_kind", "")
            workloads.append(entry)
        workloads.sort(key=lambda x: (x["namespace"], x["name"]))

        # When a filter is active the operator usually only cares about
        # matched workloads plus their immediate neighbours. Anything else
        # in the Cypher edge sweep is unrelated namespace noise — drop it
        # so the workloads[] list doesn't balloon with edges that don't
        # touch the matched set.
        if filter_active and matched_ids:
            neighbour_ids: set = set()
            for row in result.get("data", []):
                s_id = str(row.get("src_id") or "")
                d_id = str(row.get("dst_id") or "")
                if s_id in matched_ids and d_id:
                    neighbour_ids.add(d_id)
                if d_id in matched_ids and s_id:
                    neighbour_ids.add(s_id)
            keep_ids = matched_ids | neighbour_ids
            workloads = [w for w in workloads if w["id"] in keep_ids]

        response: Dict[str, Any] = {
            "success": True,
            "analysis_id": str(analysis_id),
            "cluster_id": str(cluster_id) if cluster_id else None,
            "workloads": workloads,
        }
        if filter_active:
            response["summary"] = {
                "total_matched": sum(1 for w in workloads if w.get("is_matched")),
                "total_workloads": len(workloads),
            }
        return response

    def find_l7_workload_dependencies(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        workload_name: Optional[str] = None,
        namespace: Optional[str] = None,
        depth: int = 1,
        label_key: Optional[str] = None,
        label_value: Optional[str] = None,
        annotation_key: Optional[str] = None,
        annotation_value: Optional[str] = None,
        include_metadata: bool = True,
        workload_name_exact: bool = True,
    ) -> Dict[str, Any]:
        """L7 dependency tree rooted at a workload, mirroring L4's matched_services format.

        When workload_name is given, returns that workload as upstream with its
        downstream (outgoing) and callers (incoming) grouped by protocol.
        When workload_name is omitted, returns all workloads with their edges.

        ``workload_name_exact`` (default True) controls the matching semantics
        for ``workload_name`` so we preserve backward compatibility for
        external callers that depend on exact-equality matches. The Integration
        Hub frontend opts in to ``workload_name_exact=False`` (case-insensitive
        substring) so the L7 tree behaves like L4 ``owner_name`` filtering.
        """
        aid = str(analysis_id)
        params: Dict[str, Any] = {
            "analysis_id": aid,
            "analysis_id_prefix": f"{aid}-",
        }

        rel_where = "(r.analysis_id = $analysis_id OR r.analysis_id STARTS WITH $analysis_id_prefix)"
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
            rel_where += " AND src.cluster = $cluster_id"

        match_conditions = []
        if workload_name:
            params["workload_name"] = workload_name
            if workload_name_exact:
                match_conditions.append("(src.name = $workload_name OR dst.name = $workload_name)")
            else:
                match_conditions.append(
                    "(toLower(src.name) CONTAINS toLower($workload_name) "
                    "OR toLower(dst.name) CONTAINS toLower($workload_name))"
                )
        if namespace:
            params["namespace"] = namespace
            match_conditions.append("(src.namespace = $namespace OR dst.namespace = $namespace)")

        where_full = rel_where
        if match_conditions:
            where_full += " AND " + " AND ".join(match_conditions)

        meta_cols = ""
        if include_metadata:
            meta_cols = """,
                src.labels AS src_labels, src.annotations AS src_annotations, src.owner_kind AS src_owner_kind,
                dst.labels AS dst_labels, dst.annotations AS dst_annotations, dst.owner_kind AS dst_owner_kind"""

        safe_depth = max(1, min(depth, 3))
        if workload_name and safe_depth > 1:
            root_ns_filter = " AND root.namespace = $namespace" if namespace else ""
            if workload_name_exact:
                root_name_filter = "root.name = $workload_name"
            else:
                root_name_filter = "toLower(root.name) CONTAINS toLower($workload_name)"
            query = f"""
            MATCH path = (root:L7Workload)-[rels:L7_COMMUNICATES_WITH*1..{safe_depth}]->(leaf:L7Workload)
            WHERE {root_name_filter}{root_ns_filter}
              AND ALL(r IN rels WHERE {rel_where.replace("src.cluster", "root.cluster")})
            UNWIND relationships(path) AS r
            WITH startNode(r) AS src, endNode(r) AS dst, r
            RETURN DISTINCT
                src.name AS src_name, src.namespace AS src_namespace, src.cluster AS src_cluster,
                dst.name AS dst_name, dst.namespace AS dst_namespace, dst.cluster AS dst_cluster,
                r.protocol AS protocol, r.http_method AS http_method, r.http_path AS http_path,
                coalesce(r.request_count, 0) AS request_count,
                coalesce(r.error_count, 0) AS error_count,
                coalesce(r.avg_latency_ms, 0.0) AS avg_latency_ms{meta_cols}
            LIMIT {settings.max_results}
            """
        else:
            query = f"""
            MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
            WHERE {where_full}
            RETURN
                src.name AS src_name, src.namespace AS src_namespace, src.cluster AS src_cluster,
                dst.name AS dst_name, dst.namespace AS dst_namespace, dst.cluster AS dst_cluster,
                r.protocol AS protocol, r.http_method AS http_method, r.http_path AS http_path,
                coalesce(r.request_count, 0) AS request_count,
                coalesce(r.error_count, 0) AS error_count,
                coalesce(r.avg_latency_ms, 0.0) AS avg_latency_ms{meta_cols}
            LIMIT {settings.max_results}
            """
        result = self.execute_query(query, params)
        if not result.get("success"):
            return {"success": False, "error": result.get("error"), "matched_services": []}

        node_key = lambda name, ns: f"{ns}/{name}"
        nodes: Dict[str, Dict[str, Any]] = {}
        outgoing: Dict[str, list] = defaultdict(list)
        incoming: Dict[str, list] = defaultdict(list)

        def ensure_node(name, ns, cluster, labels=None, annotations=None, owner_kind=None):
            key = node_key(name, ns)
            if key not in nodes:
                nd: Dict[str, Any] = {"name": name or "", "namespace": ns or "", "cluster": cluster or ""}
                if include_metadata:
                    nd["labels"] = self._parse_json_field(labels)
                    nd["annotations"] = self._parse_json_field(annotations)
                    nd["owner_kind"] = str(owner_kind or "")
                nodes[key] = nd
            return key

        # Use the shared module-level glob matcher so L4 and L7 label/annotation
        # filters apply identical semantics (audit B-2 / E-13: fnmatch '*', '?',
        # '[seq]'; empty value or '*' means any value).
        _label_match = _glob_match_metadata

        for row in result.get("data", []):
            sk = ensure_node(
                row["src_name"], row["src_namespace"], row.get("src_cluster"),
                row.get("src_labels"), row.get("src_annotations"), row.get("src_owner_kind"),
            )
            dk = ensure_node(
                row["dst_name"], row["dst_namespace"], row.get("dst_cluster"),
                row.get("dst_labels"), row.get("dst_annotations"), row.get("dst_owner_kind"),
            )
            edge_info = {
                "name": row["dst_name"] or "",
                "namespace": row["dst_namespace"] or "",
                "cluster": row.get("dst_cluster") or "",
                "protocol": row.get("protocol") or "",
                "http_method": row.get("http_method") or "",
                "http_path": row.get("http_path") or "",
                "request_count": int(row.get("request_count") or 0),
                "error_count": int(row.get("error_count") or 0),
                "avg_latency_ms": float(row.get("avg_latency_ms") or 0.0),
            }
            outgoing[sk].append(edge_info)
            caller_info = {
                "name": row["src_name"] or "",
                "namespace": row["src_namespace"] or "",
                "cluster": row.get("src_cluster") or "",
                "protocol": row.get("protocol") or "",
                "http_method": row.get("http_method") or "",
                "http_path": row.get("http_path") or "",
                "request_count": int(row.get("request_count") or 0),
                "error_count": int(row.get("error_count") or 0),
                "avg_latency_ms": float(row.get("avg_latency_ms") or 0.0),
            }
            incoming[dk].append(caller_info)

        def group_by_protocol(edges: list) -> Dict[str, list]:
            groups: Dict[str, list] = defaultdict(list)
            for e in edges:
                cat = e.get("protocol") or "unknown"
                groups[cat].append(e)
            return dict(groups)

        if workload_name:
            if workload_name_exact:
                root_keys = [k for k, n in nodes.items()
                             if n["name"] == workload_name
                             and (not namespace or n["namespace"] == namespace)]
            else:
                needle = workload_name.lower()
                root_keys = [k for k, n in nodes.items()
                             if needle in (n["name"] or "").lower()
                             and (not namespace or n["namespace"] == namespace)]
        else:
            root_keys = sorted(nodes.keys())

        matched_services = []
        for rk in root_keys:
            n = nodes[rk]
            node_labels = n.get("labels", {}) if include_metadata else {}
            node_annots = n.get("annotations", {}) if include_metadata else {}
            if not _label_match(node_labels, label_key, label_value):
                continue
            if not _label_match(node_annots, annotation_key, annotation_value):
                continue
            ds_edges = outgoing.get(rk, [])
            cl_edges = incoming.get(rk, [])
            svc: Dict[str, Any] = {
                "name": n["name"],
                "namespace": n["namespace"],
                "cluster": n["cluster"],
                "downstream": {
                    "total": len(ds_edges),
                    "by_protocol": group_by_protocol(ds_edges),
                },
                "callers": {
                    "total": len(cl_edges),
                    "by_protocol": group_by_protocol(cl_edges),
                },
            }
            if include_metadata:
                svc["labels"] = node_labels
                svc["annotations"] = node_annots
                svc["owner_kind"] = n.get("owner_kind", "")
            matched_services.append(svc)

        total_ds = sum(s["downstream"]["total"] for s in matched_services)
        total_cl = sum(s["callers"]["total"] for s in matched_services)

        return {
            "success": True,
            "analysis_id": aid,
            "cluster_id": str(cluster_id) if cluster_id else None,
            "multi_service": len(matched_services) > 1,
            "summary": {
                "total_matched": len(matched_services),
                "total_downstream": total_ds,
                "total_callers": total_cl,
                "total_workloads": len(nodes),
            },
            "matched_services": matched_services,
        }

    def get_l7_communications(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        protocol: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Flat L7 communication records (Neo4j shape compatible with /communications)."""
        where_clause, params = self._l7_match_where(
            analysis_id,
            cluster_id=cluster_id,
            namespace=namespace,
            protocol=protocol,
        )
        params["limit"] = min(limit, settings.max_results)
        query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN
            src.id AS source_id,
            src.name AS source_name,
            src.namespace AS source_namespace,
            src.cluster AS source_cluster,
            src.kind AS source_kind,
            dst.id AS destination_id,
            dst.name AS destination_name,
            dst.namespace AS destination_namespace,
            dst.cluster AS destination_cluster,
            dst.kind AS destination_kind,
            r.protocol AS protocol,
            r.http_method AS http_method,
            r.http_path AS http_path,
            r.request_count AS request_count,
            r.error_count AS error_count,
            r.avg_latency_ms AS avg_latency_ms,
            r.analysis_id AS analysis_id
        ORDER BY coalesce(r.request_count, 0) DESC
        LIMIT $limit
        """
        return self.execute_query(query, params)

    def get_l7_error_stats(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """L7 error aggregation by protocol and totals."""
        where_clause, params = self._l7_match_where(
            analysis_id,
            cluster_id=cluster_id,
            namespace=namespace,
            protocol=None,
        )
        query = f"""
        MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
        WHERE {where_clause}
        RETURN
            r.protocol AS protocol,
            sum(coalesce(r.error_count, 0)) AS error_count,
            sum(coalesce(r.request_count, 0)) AS request_count
        """
        agg = self.execute_query(query, params)
        by_protocol: Dict[str, Dict[str, int]] = {}
        total_err = 0
        total_req = 0
        if not agg.get("success"):
            return {
                "success": False,
                "analysis_id": str(analysis_id),
                "cluster_id": str(cluster_id) if cluster_id else None,
                "namespace": namespace,
                "error": agg.get("error", "Neo4j query failed"),
                "total_errors": 0,
                "total_requests": 0,
                "error_rate_percent": 0.0,
                "by_protocol": {},
            }
        for row in agg.get("data", []):
            proto = row.get("protocol") or "UNKNOWN"
            e = int(row.get("error_count") or 0)
            q = int(row.get("request_count") or 0)
            by_protocol[proto] = {"error_count": e, "request_count": q}
            total_err += e
            total_req += q
        rate = round((total_err / total_req) * 100.0, 4) if total_req > 0 else 0.0
        return {
            "success": True,
            "analysis_id": str(analysis_id),
            "cluster_id": str(cluster_id) if cluster_id else None,
            "namespace": namespace,
            "total_errors": total_err,
            "total_requests": total_req,
            "error_rate_percent": rate,
            "by_protocol": by_protocol,
        }

    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j connection health"""
        try:
            if not self.driver:
                return {"healthy": False, "error": "No driver"}
            
            self.driver.verify_connectivity()
            
            # Execute simple query
            result = self.execute_query("RETURN 1 AS test")
            
            if result.get("success"):
                return {
                    "healthy": True,
                    "database": self.database,
                    "uri": settings.neo4j_bolt_uri
                }
            else:
                return {
                    "healthy": False,
                    "error": result.get("error")
                }
                
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    def find_pod_dependencies(
        self,
        analysis_id: Optional[str] = None,
        analysis_ids: Optional[List[str]] = None,
        cluster_id: Optional[str] = None,
        pod_name: Optional[str] = None,
        namespace: Optional[str] = None,
        owner_name: Optional[str] = None,
        label_key: Optional[str] = None,
        label_value: Optional[str] = None,
        annotation_key: Optional[str] = None,
        annotation_value: Optional[str] = None,
        ip: Optional[str] = None,
        depth: int = 1,
        include_communication_details: bool = True,
        # Plan v3 Akış D m.8 — Discovery mode.
        #
        # When the operator hasn't picked a service identification method
        # (no annotation/label/owner/pod_name/ip), they may still want to
        # see the dependency graph for the analysis scope as a whole.
        # The previous behaviour was to hard-fail with "At least one
        # search parameter required". `match_all=True` opts into the
        # broader query but keeps the result bounded:
        #
        #   - depth is capped at MAX_DISCOVERY_DEPTH (=2): preventing a
        #     `depth=5` discovery from producing a graph that takes
        #     30s+ to render.
        #   - the workload `LIMIT` (200) becomes the *seed* limit and
        #     the operator must pass `cluster_id` AND/OR `namespace` so
        #     a single analysis owner can't accidentally enumerate
        #     every workload in a shared cluster ("tenant guard").
        #
        # When `match_all` is False the previous semantics apply
        # verbatim — backward compatible.
        match_all: bool = False,
    ) -> Dict[str, Any]:
        """
        Find a pod by any metadata and return its upstream/downstream dependencies.
        
        The matched pod is the "upstream" (source). All pods it communicates with
        are "downstream" (targets). Pods that communicate TO the matched pod are
        also returned as callers (reverse upstream).
        
        Any combination of search parameters can be used. At least one is required
        unless `match_all=True` (discovery mode, see kwargs).
        
        Args:
            analysis_id: Single analysis ID for scope (backward compat)
            analysis_ids: Multiple analysis IDs for scope (takes precedence over analysis_id)
            cluster_id: Cluster ID for scope
            pod_name: Pod/workload name to search
            namespace: Namespace to narrow search
            owner_name: Deployment/StatefulSet/DaemonSet name to search
            label_key/label_value: Label key=value to match
            annotation_key/annotation_value: Annotation key=value to match
            ip: Pod IP to search
            depth: Traversal depth for dependencies (default 1)
        
        Returns:
            Dict with upstream pod info and downstream dependencies
        """
        # Build match conditions to find the target pod
        match_conditions = []
        params = {}
        
        # Consolidate analysis_ids (plural takes precedence)
        effective_ids = None
        if analysis_ids:
            effective_ids = [str(a) for a in analysis_ids]
        elif analysis_id:
            effective_ids = [str(analysis_id)]
        
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        
        if pod_name:
            match_conditions.append("toLower(w.name) CONTAINS toLower($pod_name)")
            params["pod_name"] = pod_name
        
        if namespace:
            match_conditions.append("w.namespace = $namespace")
            params["namespace"] = namespace
        
        if owner_name:
            match_conditions.append("toLower(w.owner_name) CONTAINS toLower($owner_name)")
            params["owner_name"] = owner_name
        
        if ip:
            match_conditions.append("w.ip = $ip")
            params["ip"] = ip
        
        if annotation_key:
            if '*' in annotation_key or '?' in annotation_key:
                ann_key_prefix = annotation_key.split('*')[0].split('?')[0]
                if ann_key_prefix:
                    match_conditions.append(
                        "w.annotations CONTAINS $annotation_key_search"
                    )
                    params["annotation_key_search"] = f'"{ann_key_prefix}'
            else:
                match_conditions.append(
                    "w.annotations CONTAINS $annotation_key_search"
                )
                params["annotation_key_search"] = f'"{annotation_key}"'
        
        if label_key and label_value:
            match_conditions.append(
                "w.labels CONTAINS $label_search"
            )
            params["label_search"] = f'"{label_key}"'
            params["label_value"] = label_value
        elif label_key:
            match_conditions.append(
                "w.labels CONTAINS $label_key_search"
            )
            params["label_key_search"] = f'"{label_key}"'
        
        # Plan v3 Akış D m.8 — discovery mode (`match_all=True`) lets
        # the operator see "all workloads in scope" without picking a
        # service identification method. We still require a tenant
        # guard (cluster_id OR namespace) AND an analysis scope so a
        # single discovery query can't enumerate every workload in a
        # shared multi-tenant cluster. depth is also capped to keep
        # graph size predictable.
        MAX_DISCOVERY_DEPTH = 2
        DISCOVERY_SEED_LIMIT = 200
        if not match_conditions:
            if not match_all:
                return {"success": False, "error": "At least one search parameter required (pod_name, namespace, owner_name, ip, annotation_key, label_key) or pass match_all=true for discovery mode", "count": 0, "results": []}
            # Tenant guard: discovery mode without ANY narrowing scope
            # would enumerate every workload in every analysis the
            # caller has access to. Force at least one of:
            #   - cluster_id (single-cluster discovery)
            #   - namespace (single-namespace discovery)
            # A bare analysis_id is NOT enough because a single analysis
            # may span thousands of workloads. The operator can still
            # combine namespace + cluster + analysis if they want even
            # tighter scoping.
            if not cluster_id and not namespace:
                return {
                    "success": False,
                    "error": "Discovery mode requires either cluster_id or namespace to bound the result set.",
                    "count": 0,
                    "results": [],
                }
            if depth > MAX_DISCOVERY_DEPTH:
                # Silently cap rather than fail: the operator's
                # `depth=5` choice still gets them a useful result
                # (depth-2), and the response payload echoes back
                # `effective_depth` (added below) so the UI can show
                # "depth capped at 2 for discovery mode".
                depth = MAX_DISCOVERY_DEPTH
        
        # Add analysis scope filter
        if effective_ids:
            params["analysis_ids"] = effective_ids
            params["analysis_id_prefixes"] = [f"{a}-" for a in effective_ids]
            match_conditions.append(
                "(w.analysis_id IN $analysis_ids OR "
                "ANY(prefix IN $analysis_id_prefixes WHERE w.analysis_id STARTS WITH prefix))"
            )
        if cluster_id:
            match_conditions.append("w.cluster_id = $cluster_id")
        
        where_clause = " AND ".join(match_conditions)
        
        # Step 1: Find the upstream pod(s) matching criteria
        find_query = f"""
        MATCH (w:Workload)
        WHERE {where_clause}
        RETURN 
            w.id AS id,
            w.name AS name,
            w.namespace AS namespace,
            w.cluster_id AS cluster_id,
            w.ip AS ip,
            w.labels AS labels,
            w.annotations AS annotations,
            w.owner_kind AS owner_kind,
            w.owner_name AS owner_name,
            w.phase AS phase,
            w.image AS image,
            w.container AS container,
            w.service_account AS service_account,
            w.host_ip AS host_ip,
            w.pod_uid AS pod_uid,
            w.node AS node
        LIMIT 200
        """
        
        find_result = self.execute_query(find_query, params)
        
        if not find_result.get("success") or not find_result.get("data"):
            return {
                "success": False,
                "error": "No pod found matching the given criteria",
                "search_params": {
                    k: v for k, v in {
                        "pod_name": pod_name, "namespace": namespace,
                        "owner_name": owner_name,
                        "annotation_key": annotation_key, "annotation_value": annotation_value,
                        "label_key": label_key, "label_value": label_value,
                        "ip": ip
                    }.items() if v
                }
            }
        
        # Post-filter for annotation_key/value (supports * glob pattern)
        matched_pods = find_result["data"]
        if annotation_key:
            from fnmatch import fnmatch
            ann_key_has_glob = '*' in annotation_key or '?' in annotation_key
            ann_val_any = not annotation_value or annotation_value == '*'
            ann_val_has_glob = not ann_val_any and ('*' in annotation_value or '?' in annotation_value)
            filtered = []
            for pod in matched_pods:
                ann_raw = pod.get("annotations", "{}")
                if isinstance(ann_raw, str):
                    try:
                        ann = json.loads(ann_raw)
                    except (json.JSONDecodeError, TypeError):
                        ann = {}
                else:
                    ann = ann_raw or {}
                
                hit_keys = [k for k in ann if fnmatch(k, annotation_key)] if ann_key_has_glob else ([annotation_key] if annotation_key in ann else [])
                if not hit_keys:
                    continue
                if ann_val_any:
                    filtered.append(pod)
                    continue
                for k in hit_keys:
                    v = str(ann[k])
                    if ann_val_has_glob:
                        if fnmatch(v, annotation_value):
                            filtered.append(pod)
                            break
                    else:
                        if v == annotation_value:
                            filtered.append(pod)
                            break
            matched_pods = filtered
        
        if label_key and label_value:
            filtered = []
            for pod in matched_pods:
                lbl_raw = pod.get("labels", "{}")
                if isinstance(lbl_raw, str):
                    try:
                        lbl = json.loads(lbl_raw)
                    except (json.JSONDecodeError, TypeError):
                        lbl = {}
                else:
                    lbl = lbl_raw or {}
                if lbl.get(label_key) == label_value:
                    filtered.append(pod)
            matched_pods = filtered
        
        if not matched_pods:
            return {
                "success": False,
                "error": "No pod found matching the given criteria after filtering",
                "search_params": {
                    k: v for k, v in {
                        "pod_name": pod_name, "namespace": namespace,
                        "owner_name": owner_name,
                        "annotation_key": annotation_key, "annotation_value": annotation_value,
                        "label_key": label_key, "label_value": label_value,
                        "ip": ip
                    }.items() if v
                }
            }
        
        results = []
        
        for upstream_pod in matched_pods:
            pod_id = upstream_pod["id"]
            
            # Parse JSON fields
            for field in ["labels", "annotations"]:
                raw = upstream_pod.get(field, "{}")
                if isinstance(raw, str):
                    try:
                        upstream_pod[field] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        upstream_pod[field] = {}
                elif not isinstance(raw, dict):
                    upstream_pod[field] = {}
            
            # Step 2: Get downstream (pods this upstream connects TO)
            depth_val = max(1, min(depth, 5))
            downstream_query = f"""
            MATCH path = (src:Workload {{id: $pod_id}})-[:COMMUNICATES_WITH*1..{depth_val}]->(dst)
            WHERE dst.id <> $pod_id
            WITH dst, path, length(path) as hops
            ORDER BY hops ASC
            WITH dst, collect(path)[0] as sp
            WITH dst, length(sp) as hop_count, relationships(sp) as rels
            WITH dst, hop_count, rels[size(rels)-1] as r
            RETURN 
                dst.id AS id,
                dst.name AS name,
                dst.namespace AS namespace,
                dst.cluster_id AS cluster_id,
                dst.ip AS ip,
                dst.labels AS labels,
                dst.annotations AS annotations,
                dst.owner_kind AS owner_kind,
                dst.owner_name AS owner_name,
                dst.phase AS phase,
                dst.image AS image,
                dst.container AS container,
                dst.service_account AS service_account,
                dst.host_ip AS host_ip,
                dst.pod_uid AS pod_uid,
                dst.node AS node,
                hop_count,
                r.protocol AS protocol,
                r.port AS port,
                r.destination_port AS destination_port,
                r.app_protocol AS app_protocol,
                r.request_count AS request_count,
                r.bytes_transferred AS bytes_transferred,
                r.error_count AS error_count,
                r.retransmit_count AS retransmit_count,
                r.avg_latency_ms AS avg_latency_ms,
                r.last_seen AS last_seen
            ORDER BY hop_count, dst.name
            LIMIT 200
            """
            
            downstream_result = self.execute_query(downstream_query, {"pod_id": pod_id})
            downstream_pods = []
            
            if downstream_result.get("success"):
                for d in downstream_result.get("data", []):
                    for field in ["labels", "annotations"]:
                        raw = d.get(field, "{}")
                        if isinstance(raw, str):
                            try:
                                d[field] = json.loads(raw)
                            except (json.JSONDecodeError, TypeError):
                                d[field] = {}
                        elif not isinstance(raw, dict):
                            d[field] = {}
                    
                    port = d.get("destination_port") or d.get("port")
                    request_count = d.get("request_count") or 0
                    error_count = d.get("error_count") or 0
                    retransmit_count = d.get("retransmit_count") or 0
                    avg_latency = d.get("avg_latency_ms") or 0
                    
                    dep_entry = {
                        "pod_name": d.get("name"),
                        "namespace": d.get("namespace"),
                        "cluster_id": d.get("cluster_id"),
                        "ip": d.get("ip"),
                        "labels": d.get("labels", {}),
                        "annotations": d.get("annotations", {}),
                        "owner_kind": d.get("owner_kind"),
                        "owner_name": d.get("owner_name"),
                        "phase": d.get("phase"),
                        "image": d.get("image"),
                        "container": d.get("container"),
                        "service_account": d.get("service_account"),
                        "host_ip": d.get("host_ip"),
                        "node": d.get("node"),
                        "hop_count": d.get("hop_count", 1),
                    }
                    if include_communication_details:
                        dep_entry["communication"] = self._build_communication_contract(
                            d.get("protocol"), d.get("app_protocol"), port,
                            request_count, d.get("bytes_transferred"),
                            error_count, retransmit_count, avg_latency,
                            d.get("last_seen"),
                            workload_name=d.get("name", "")
                        )
                        dep_entry["health"] = self._calculate_dependency_health(
                            request_count, error_count, retransmit_count, avg_latency
                        )
                    downstream_pods.append(dep_entry)
            
            # Step 3: Get callers (pods that connect TO this upstream pod - reverse direction)
            callers_query = f"""
            MATCH path = (caller)-[:COMMUNICATES_WITH*1..{depth_val}]->(target:Workload {{id: $pod_id}})
            WHERE caller.id <> $pod_id
            WITH caller, path, length(path) as hops
            ORDER BY hops ASC
            WITH caller, collect(path)[0] as sp
            WITH caller, length(sp) as hop_count, relationships(sp) as rels
            WITH caller, hop_count, rels[size(rels)-1] as r
            RETURN 
                caller.id AS id,
                caller.name AS name,
                caller.namespace AS namespace,
                caller.cluster_id AS cluster_id,
                caller.ip AS ip,
                caller.labels AS labels,
                caller.annotations AS annotations,
                caller.owner_kind AS owner_kind,
                caller.owner_name AS owner_name,
                caller.phase AS phase,
                caller.image AS image,
                caller.container AS container,
                caller.service_account AS service_account,
                caller.host_ip AS host_ip,
                caller.pod_uid AS pod_uid,
                caller.node AS node,
                hop_count,
                r.protocol AS protocol,
                r.port AS port,
                r.destination_port AS destination_port,
                r.app_protocol AS app_protocol,
                r.request_count AS request_count,
                r.bytes_transferred AS bytes_transferred,
                r.error_count AS error_count,
                r.retransmit_count AS retransmit_count,
                r.avg_latency_ms AS avg_latency_ms,
                r.last_seen AS last_seen
            ORDER BY hop_count, caller.name
            LIMIT 200
            """
            
            callers_result = self.execute_query(callers_query, {"pod_id": pod_id})
            caller_pods = []
            
            if callers_result.get("success"):
                for c in callers_result.get("data", []):
                    for field in ["labels", "annotations"]:
                        raw = c.get(field, "{}")
                        if isinstance(raw, str):
                            try:
                                c[field] = json.loads(raw)
                            except (json.JSONDecodeError, TypeError):
                                c[field] = {}
                        elif not isinstance(raw, dict):
                            c[field] = {}
                    
                    port = c.get("destination_port") or c.get("port")
                    request_count = c.get("request_count") or 0
                    error_count = c.get("error_count") or 0
                    retransmit_count = c.get("retransmit_count") or 0
                    avg_latency = c.get("avg_latency_ms") or 0
                    
                    caller_entry = {
                        "pod_name": c.get("name"),
                        "namespace": c.get("namespace"),
                        "cluster_id": c.get("cluster_id"),
                        "ip": c.get("ip"),
                        "labels": c.get("labels", {}),
                        "annotations": c.get("annotations", {}),
                        "owner_kind": c.get("owner_kind"),
                        "owner_name": c.get("owner_name"),
                        "phase": c.get("phase"),
                        "image": c.get("image"),
                        "container": c.get("container"),
                        "service_account": c.get("service_account"),
                        "host_ip": c.get("host_ip"),
                        "node": c.get("node"),
                        "hop_count": c.get("hop_count", 1),
                    }
                    if include_communication_details:
                        caller_entry["communication"] = self._build_communication_contract(
                            c.get("protocol"), c.get("app_protocol"), port,
                            request_count, c.get("bytes_transferred"),
                            error_count, retransmit_count, avg_latency,
                            c.get("last_seen"),
                            workload_name=c.get("name", "")
                        )
                        caller_entry["health"] = self._calculate_dependency_health(
                            request_count, error_count, retransmit_count, avg_latency
                        )
                    caller_pods.append(caller_entry)
            
            results.append({
                "upstream": {
                    "pod_name": upstream_pod.get("name"),
                    "namespace": upstream_pod.get("namespace"),
                    "cluster_id": upstream_pod.get("cluster_id"),
                    "ip": upstream_pod.get("ip"),
                    "labels": upstream_pod.get("labels", {}),
                    "annotations": upstream_pod.get("annotations", {}),
                    "owner_kind": upstream_pod.get("owner_kind"),
                    "owner_name": upstream_pod.get("owner_name"),
                    "phase": upstream_pod.get("phase"),
                    "image": upstream_pod.get("image"),
                    "container": upstream_pod.get("container"),
                    "service_account": upstream_pod.get("service_account"),
                    "host_ip": upstream_pod.get("host_ip"),
                    "node": upstream_pod.get("node")
                },
                "downstream": downstream_pods,
                "callers": caller_pods
            })
        
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
    
    def batch_find_dependencies(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        services: List[Dict[str, Any]] = None,
        depth: int = 1,
        include_communication_details: bool = True,
    ) -> Dict[str, Any]:
        """Batch find dependencies for multiple services in one call."""
        if not services:
            return {"error": "services list is required"}

        all_results = []
        all_downstream_ids: List[set] = []

        for svc in services:
            result = self.find_pod_dependencies(
                analysis_id=analysis_id,
                cluster_id=cluster_id,
                pod_name=svc.get("pod_name"),
                namespace=svc.get("namespace"),
                owner_name=svc.get("owner_name"),
                label_key=svc.get("label_key"),
                label_value=svc.get("label_value"),
                annotation_key=svc.get("annotation_key"),
                annotation_value=svc.get("annotation_value"),
                ip=svc.get("ip"),
                depth=depth,
                include_communication_details=include_communication_details,
            )
            all_results.append(result)

            ids = set()
            if result.get("success"):
                for r in result.get("results", []):
                    for d in r.get("downstream", []):
                        name = d.get("pod_name") or d.get("owner_name") or ""
                        ns = d.get("namespace", "")
                        ids.add(f"{ns}/{name}")
            all_downstream_ids.append(ids)

        shared = set()
        if len(all_downstream_ids) >= 2:
            shared = all_downstream_ids[0]
            for s in all_downstream_ids[1:]:
                shared = shared & s

        return {
            "success": True,
            "service_count": len(services),
            "results": all_results,
            "shared_dependencies": sorted(shared),
        }

    def format_dependency_summary(
        self,
        stream_result: Dict[str, Any],
        analysis_ids: List[str],
    ) -> Dict[str, Any]:
        """Transform find_pod_dependencies output into a compact, AI-agent-friendly
        grouped format. Dependencies are grouped by service_category with only the
        fields relevant for cross-project impact analysis.

        When multiple pods match (e.g. namespace-wide query), aggregates ALL
        downstream/caller entries (deduplicated) and exposes matched_services.
        Replica pods belonging to the same Deployment/StatefulSet are collapsed
        into a single logical workload entry.
        """
        try:
            int_ids = [int(a) for a in analysis_ids]
        except (ValueError, TypeError):
            int_ids = analysis_ids

        if not stream_result.get("success") or not stream_result.get("results"):
            return {
                "success": False,
                "analysis_ids": int_ids,
                "error": stream_result.get("error", "No results"),
            }

        results = stream_result["results"]

        _safe_labels = self._safe_labels
        _strip_template_hash = self._strip_template_hash

        def _workload_name(entry: dict) -> str:
            """Resolve the logical workload name from the richest source available."""
            labels = _safe_labels(entry)
            name = labels.get("app.kubernetes.io/name") or labels.get("app")
            if name:
                return name

            pth = labels.get("pod-template-hash", "")
            owner = entry.get("owner_name") or ""
            if owner:
                return _strip_template_hash(owner, pth)

            return _strip_template_hash(entry.get("pod_name", ""), pth)

        def _workload_key(entry: dict) -> str:
            """Determine a stable identity key that collapses replica pods into
            their owning Deployment/StatefulSet.

            Resolution order:
              1. namespace + app.kubernetes.io/name or app label (most reliable)
              2. namespace + owner_name (stripped of template hash if present)
              3. namespace + pod name (stripped of template hash if present)
            """
            ns = entry.get("namespace", "")
            labels = _safe_labels(entry)

            name = labels.get("app.kubernetes.io/name") or labels.get("app")
            if name:
                return f"{ns}/{name}"

            pth = labels.get("pod-template-hash", "")
            owner = entry.get("owner_name") or ""
            if owner:
                return f"{ns}/{_strip_template_hash(owner, pth)}"

            pod = entry.get("pod_name") or ""
            return f"{ns}/{_strip_template_hash(pod, pth)}"

        def _is_noise_entry(entry: dict) -> bool:
            """Filter out noise: reverse DNS, bare IPs with no metadata, 0.0.0.0."""
            name = entry.get("pod_name") or entry.get("owner_name") or ""
            if name.endswith(".in-addr.arpa.") or name.endswith(".in-addr.arpa"):
                return True
            if name in ("0.0.0.0", "0.0.0.0:0"):
                return True
            comm = entry.get("communication") or {}
            port = comm.get("port") or 0
            ns = entry.get("namespace", "")
            ann = entry.get("annotations") or {}
            lbl = entry.get("labels") or {}
            owner_kind = entry.get("owner_kind") or ""
            if port == 0 and not ann and not lbl and not owner_kind and ns in ("external", "cluster-network", ""):
                return True
            if ns == "sdn-infrastructure" and not ann and not lbl and not owner_kind:
                return True
            return False

        _KIND_ALIASES = {"ReplicaSet": "Deployment"}

        # _NOISE_ANNOTATION_PREFIXES and _filter_summary_annotations have moved
        # to module scope so they can be re-used by the L7 dependency_summary
        # filter path (audit v3 / E-10).

        def _resolve_kind(raw: str, labels: dict = None) -> str:
            if raw in _KIND_ALIASES:
                return _KIND_ALIASES[raw]
            if raw in ("Unknown", "") and labels:
                if labels.get("pod-template-hash"):
                    return "Deployment"
                if labels.get("controller-revision-hash"):
                    if labels.get("statefulset.kubernetes.io/pod-name"):
                        return "StatefulSet"
                    return "DaemonSet"
            return raw

        def _compact_service(entry: dict, direction: str = "downstream") -> dict:
            comm = entry.get("communication") or {}
            svc_type = comm.get("service_type", "unknown")
            svc_cat = comm.get("service_category", "")
            is_crit = comm.get("is_critical", False)
            if not svc_cat:
                svc_cat = self.classify_service_category(svc_type, entry.get("pod_name", ""))
            if not is_crit:
                is_crit = self.is_critical_service(svc_type, entry.get("pod_name", ""))
            labels = _safe_labels(entry)
            result = {
                "name": _workload_name(entry),
                "namespace": entry.get("namespace", ""),
                "kind": _resolve_kind(entry.get("owner_kind") or "", labels),
                "annotations": _filter_summary_annotations(entry.get("annotations", {})),
                "labels": labels,
                "is_critical": is_crit,
                "service_type": svc_type,
                "service_category": svc_cat,
                "port": comm.get("port"),
            }
            hop = entry.get("hop_count", 1)
            if hop > 1:
                result["hop_count"] = hop
            if entry.get("l7_details") is not None:
                result["l7_details"] = entry["l7_details"]
                result["has_l7_data"] = True
            elif "has_l7_data" in entry:
                result["has_l7_data"] = False
            return result

        def _dedup_entries(entries: list) -> list:
            """Deduplicate dependency entries by logical workload identity,
            collapsing replica pods that share the same Deployment/StatefulSet.
            When duplicates exist, keeps the entry with the lowest hop_count
            so multi-replica merges preserve the shortest path."""
            seen: Dict[str, dict] = {}
            for entry in entries:
                key = _workload_key(entry)
                if key not in seen:
                    seen[key] = entry
                elif entry.get("hop_count", 1) < seen[key].get("hop_count", 1):
                    seen[key] = entry
            return list(seen.values())

        def _filter_and_dedup(entries: list) -> list:
            """Remove noise entries then deduplicate."""
            return _dedup_entries([e for e in entries if not _is_noise_entry(e)])

        def _group_by_category(entries: list, direction: str = "downstream") -> dict:
            by_cat: Dict[str, list] = {}
            crit_count = 0
            for entry in entries:
                compact = _compact_service(entry, direction)
                cat = compact.pop("service_category", "") or "other"
                by_cat.setdefault(cat, []).append(compact)
                if compact.get("is_critical"):
                    crit_count += 1
            return {
                "total": len(entries),
                "critical_count": crit_count,
                "by_category": by_cat,
            }

        # --- Unified loop: works identically for single and multi-service ---
        workload_map: Dict[str, dict] = {}
        for res in results:
            up = res.get("upstream", {})
            ds = res.get("downstream", [])
            cl = res.get("callers", [])
            up_key = _workload_key(up)
            up_labels = _safe_labels(up)
            if up_key in workload_map:
                workload_map[up_key]["_raw_downstream"].extend(ds)
                workload_map[up_key]["_raw_callers"].extend(cl)
                existing = workload_map[up_key]
                resolved = _resolve_kind(up.get("owner_kind") or "", up_labels)
                if (not existing["kind"] or existing["kind"] == "Unknown") and resolved not in ("", "Unknown"):
                    existing["kind"] = resolved
                if not existing["annotations"] and up.get("annotations"):
                    existing["annotations"] = _filter_summary_annotations(up["annotations"])
            else:
                workload_map[up_key] = {
                    "name": _workload_name(up),
                    "namespace": up.get("namespace", ""),
                    "kind": _resolve_kind(up.get("owner_kind") or "", up_labels),
                    "annotations": _filter_summary_annotations(up.get("annotations", {})),
                    "labels": up_labels,
                    "_raw_downstream": list(ds),
                    "_raw_callers": list(cl),
                }

        # Build per-service grouped downstream/callers and collect for global summary
        all_downstream_raw = []
        all_callers_raw = []
        matched_services = []
        for wk_data in workload_map.values():
            raw_ds = wk_data.pop("_raw_downstream")
            raw_cl = wk_data.pop("_raw_callers")
            all_downstream_raw.extend(raw_ds)
            all_callers_raw.extend(raw_cl)
            wk_data["downstream"] = _group_by_category(_filter_and_dedup(raw_ds), "downstream")
            wk_data["callers"] = _group_by_category(_filter_and_dedup(raw_cl), "caller")
            matched_services.append(wk_data)

        # Global summary with cross-service deduplication
        global_ds = _filter_and_dedup(all_downstream_raw)
        global_cl = _filter_and_dedup(all_callers_raw)
        global_ds_grouped = _group_by_category(global_ds, "downstream")
        global_cl_grouped = _group_by_category(global_cl, "caller")

        is_multi = len(matched_services) > 1
        all_namespaces = sorted(set(s["namespace"] for s in matched_services if s["namespace"]))

        if is_multi:
            if len(all_namespaces) == 1:
                svc_label = f"{all_namespaces[0]} ({len(matched_services)} services)"
                svc_ns = all_namespaces[0]
            else:
                svc_label = f"{len(matched_services)} services across {len(all_namespaces)} namespaces"
                svc_ns = ", ".join(all_namespaces)
            service_info = {
                "name": svc_label,
                "namespace": svc_ns,
                "kind": "",
                "annotations": {},
                "labels": {},
            }
        else:
            ms = matched_services[0]
            service_info = {
                "name": ms["name"],
                "namespace": ms["namespace"],
                "kind": ms.get("kind", ""),
                "annotations": ms.get("annotations", {}),
                "labels": ms.get("labels", {}),
            }

        return {
            "success": True,
            "analysis_ids": int_ids,
            "multi_service": is_multi,
            "summary": {
                "total_matched": len(matched_services),
                "total_downstream_unique": global_ds_grouped["total"],
                "total_callers_unique": global_cl_grouped["total"],
                "downstream_critical_count": global_ds_grouped["critical_count"],
                "callers_critical_count": global_cl_grouped["critical_count"],
            },
            "service": service_info,
            "matched_services": matched_services,
        }

    def diff_pod_dependencies(
        self,
        analysis_id_before: str,
        analysis_id_after: str,
        pod_name: Optional[str] = None,
        namespace: Optional[str] = None,
        owner_name: Optional[str] = None,
        cluster_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare dependencies between two analysis runs."""
        search_kwargs = dict(
            pod_name=pod_name, namespace=namespace,
            owner_name=owner_name, cluster_id=cluster_id, depth=1,
        )

        before = self.find_pod_dependencies(analysis_id=analysis_id_before, **search_kwargs)
        after = self.find_pod_dependencies(analysis_id=analysis_id_after, **search_kwargs)

        def _extract_deps(result):
            deps = {}
            if result.get("success"):
                for r in result.get("results", []):
                    for d in r.get("downstream", []):
                        key = f"{d.get('namespace', '')}/{d.get('pod_name', '')}"
                        deps[key] = d
            return deps

        before_deps = _extract_deps(before)
        after_deps = _extract_deps(after)

        before_keys = set(before_deps.keys())
        after_keys = set(after_deps.keys())

        added = []
        for k in sorted(after_keys - before_keys):
            d = after_deps[k]
            comm = d.get("communication", {})
            added.append({
                "name": d.get("pod_name"), "namespace": d.get("namespace"),
                "port": comm.get("port"), "protocol": comm.get("protocol"),
                "service_type": comm.get("service_type"),
            })

        removed = []
        for k in sorted(before_keys - after_keys):
            d = before_deps[k]
            comm = d.get("communication", {})
            removed.append({
                "name": d.get("pod_name"), "namespace": d.get("namespace"),
                "port": comm.get("port"), "protocol": comm.get("protocol"),
                "service_type": comm.get("service_type"),
            })

        changed = []
        for k in sorted(before_keys & after_keys):
            b_comm = before_deps[k].get("communication", {})
            a_comm = after_deps[k].get("communication", {})
            changes = []
            for field in ("port", "protocol", "app_protocol", "service_type"):
                bv = b_comm.get(field)
                av = a_comm.get(field)
                if bv != av:
                    changes.append(field)
            if changes:
                changed.append({
                    "name": after_deps[k].get("pod_name"),
                    "namespace": after_deps[k].get("namespace"),
                    "change": "_".join(changes) + "_changed",
                    "before": {f: b_comm.get(f) for f in changes},
                    "after": {f: a_comm.get(f) for f in changes},
                })

        unchanged_count = len(before_keys & after_keys) - len(changed)
        service_name = owner_name or pod_name or namespace or "unknown"

        return {
            "success": True,
            "service": service_name,
            "analysis_before": analysis_id_before,
            "analysis_after": analysis_id_after,
            "added_dependencies": added,
            "removed_dependencies": removed,
            "changed_dependencies": changed,
            "unchanged_count": unchanged_count,
            "summary": f"{len(added)} added, {len(removed)} removed, {len(changed)} changed, {unchanged_count} unchanged",
        }

    def format_dependency_graph(self, result: Dict[str, Any], fmt: str = "json") -> Any:
        """Format dependency stream result as Mermaid, DOT, or JSON."""
        if fmt == "json" or not result.get("success"):
            return result

        lines = []
        for r in result.get("results", []):
            upstream = r.get("upstream", {})
            up_name = (upstream.get("owner_name") or upstream.get("pod_name") or "unknown").replace("-", "_")

            for d in r.get("downstream", []):
                name = (d.get("owner_name") or d.get("pod_name") or "unknown").replace("-", "_")
                comm = d.get("communication", {})
                proto = comm.get("protocol") or "TCP"
                port = comm.get("port") or 0
                req = comm.get("request_count") or 0
                label = f"{proto}:{port} ({self._format_count(req)} req)"
                lines.append((up_name, name, label, "downstream"))

            for c in r.get("callers", []):
                name = (c.get("owner_name") or c.get("pod_name") or "unknown").replace("-", "_")
                comm = c.get("communication", {})
                proto = comm.get("protocol") or "TCP"
                port = comm.get("port") or 0
                req = comm.get("request_count") or 0
                label = f"{proto}:{port} ({self._format_count(req)} req)"
                lines.append((name, up_name, label, "caller"))

        if fmt == "mermaid":
            out = ["graph LR"]
            for src, dst, label, _ in lines:
                out.append(f'    {src} -->|"{label}"| {dst}')
            return "\n".join(out)

        if fmt == "dot":
            out = ["digraph dependencies {", "    rankdir=LR;"]
            for src, dst, label, _ in lines:
                out.append(f'    {src} -> {dst} [label="{label}"];')
            out.append("}")
            return "\n".join(out)

        return result

    @staticmethod
    def _format_count(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    PORT_SERVICE_MAP = {
        # Relational databases
        5432: "postgresql",
        3306: "mysql", 33060: "mysql-x",
        1433: "mssql", 1434: "mssql-browser",
        1521: "oracle", 1830: "oracle-net",
        50000: "db2",
        26257: "cockroachdb",
        4000: "tidb",
        5433: "postgresql",  # also used by YugabyteDB; name-based detection resolves ambiguity
        # NoSQL / Document
        27017: "mongodb", 27018: "mongodb", 27019: "mongodb",
        5984: "couchdb",
        8091: "couchbase", 8092: "couchbase", 8093: "couchbase", 11210: "couchbase",
        8529: "arangodb",
        8086: "influxdb",
        # Key-value / Cache
        6379: "redis", 6380: "redis", 16379: "redis-sentinel", 26379: "redis-sentinel",
        11211: "memcached",
        5701: "hazelcast",
        3001: "aerospike",
        6060: "dragonflydb",
        # Wide-column / Column-family
        9042: "cassandra", 7000: "cassandra-inter", 7001: "cassandra-ssl",
        9160: "cassandra-thrift",
        19042: "scylladb",
        16000: "hbase-master", 16020: "hbase-region",
        8123: "clickhouse", 9440: "clickhouse-native",
        8082: "druid",
        # Graph databases
        7687: "neo4j", 7474: "neo4j-http",
        8182: "janusgraph",
        9080: "dgraph",
        # Time-series
        8428: "victoriametrics",
        4242: "opentsdb",
        # Message brokers / Streaming
        9092: "kafka", 9093: "kafka-ssl", 9094: "kafka",
        5672: "rabbitmq", 15672: "rabbitmq-mgmt", 25672: "rabbitmq-dist",
        4222: "nats", 6222: "nats-cluster", 8222: "nats-monitor",
        61616: "activemq", 5673: "activemq-amqp",
        6650: "pulsar",
        9876: "rocketmq",
        1883: "mqtt", 8883: "mqtt-ssl",
        # Search engines
        9200: "elasticsearch", 9300: "elasticsearch-transport",
        7700: "meilisearch",
        8983: "solr",
        19530: "milvus",
        6333: "qdrant", 6334: "qdrant-grpc",
        # Service discovery / Config
        2181: "zookeeper",
        8500: "consul", 8501: "consul-https",
        2379: "etcd", 2380: "etcd-peer",
        8848: "nacos",
        # Object storage
        9000: "minio",  # also used by ClickHouse native; name-based detection resolves ambiguity
        # LDAP / Identity
        389: "ldap", 636: "ldaps",
        88: "kerberos",
        # Monitoring / Observability
        9090: "prometheus",
        3100: "loki",
        9411: "zipkin",
        14268: "jaeger",
        6831: "jaeger-thrift",
        4317: "otlp-grpc", 4318: "otlp-http",
        # HTTP / API (generic -- name-based detection refines ambiguous ports)
        80: "http-api", 8080: "http-api", 8081: "http-api",
        443: "https-api", 8443: "https-api",
        3000: "http-api",
        # gRPC
        50051: "grpc", 50052: "grpc",
        # DNS
        53: "dns", 5353: "dns",
        # SSH / FTP
        22: "ssh", 21: "ftp", 990: "ftps",
        # SMTP / Mail
        25: "smtp", 465: "smtps", 587: "smtp-submission",
        143: "imap", 993: "imaps",
    }

    SERVICE_CATEGORY_MAP = {
        "database": {
            "postgresql", "mysql", "mysql-x", "mssql", "mssql-browser",
            "oracle", "oracle-net", "db2", "cockroachdb", "tidb",
            "yugabytedb", "mongodb", "couchdb", "couchbase", "arangodb",
            "cassandra", "cassandra-inter", "cassandra-ssl", "cassandra-thrift",
            "scylladb", "hbase-master", "hbase-region", "clickhouse",
            "clickhouse-native", "druid", "neo4j", "neo4j-http",
            "janusgraph", "dgraph", "influxdb", "opentsdb",
            "vitess", "percona", "mariadb", "singlestore", "timescaledb",
            "cratedb", "voltdb", "greenplum", "citusdb", "spanner",
            "cosmosdb", "dynamodb", "firestore", "fauna",
        },
        "cache": {
            "redis", "redis-sentinel", "memcached", "hazelcast",
            "aerospike", "dragonflydb", "varnish", "keydb",
        },
        "message_broker": {
            "kafka", "kafka-ssl", "rabbitmq", "rabbitmq-mgmt", "rabbitmq-dist",
            "nats", "nats-cluster", "nats-monitor", "activemq", "activemq-amqp",
            "pulsar", "pulsar-http", "rocketmq", "mqtt", "mqtt-ssl",
            "redpanda", "amazon-sqs", "azure-servicebus", "google-pubsub",
        },
        "search_engine": {
            "elasticsearch", "elasticsearch-transport", "opensearch",
            "solr", "meilisearch", "milvus", "qdrant", "qdrant-grpc",
            "typesense", "algolia", "weaviate", "pinecone",
        },
        "service_discovery": {
            "zookeeper", "consul", "consul-https", "etcd", "etcd-peer",
            "nacos", "eureka",
        },
        "identity": {
            "ldap", "ldaps", "kerberos", "keycloak",
            "okta", "auth0",
        },
        "object_storage": {
            "minio", "ceph", "swift",
        },
        "observability": {
            "prometheus", "victoriametrics", "loki", "zipkin", "jaeger",
            "jaeger-thrift", "otlp-grpc", "otlp-http",
            "grafana", "datadog", "newrelic", "splunk",
        },
        "api_gateway": {
            "http-api", "https-api", "grpc",
        },
        "mail": {
            "smtp", "smtps", "smtp-submission", "imap", "imaps",
        },
        "dns": {"dns"},
        "file_transfer": {"ssh", "ftp", "ftps"},
    }

    CRITICAL_CATEGORIES = frozenset({
        "database", "cache", "message_broker", "search_engine",
        "service_discovery", "identity", "object_storage",
    })

    NAME_CATEGORY_PATTERNS = {
        "database": [
            "postgres", "mysql", "mariadb", "mssql", "sqlserver", "oracle",
            "mongo", "couch", "dynamo", "fauna", "cockroach", "tidb",
            "yugabyte", "cassandra", "scylla", "hbase", "clickhouse",
            "druid", "neo4j", "janusgraph", "dgraph", "arangodb",
            "influx", "timescale", "opentsdb", "crate", "voltdb",
            "greenplum", "citus", "spanner", "cosmos", "firestore",
            "vitess", "percona", "singlestore", "database", "rds",
            "-db-", "-db", "db-",
        ],
        "cache": [
            "redis", "memcache", "hazelcast", "aerospike", "dragonfly",
            "varnish", "keydb", "cache",
        ],
        "message_broker": [
            "kafka", "rabbitmq", "rabbit", "nats", "activemq", "pulsar",
            "rocketmq", "mqtt", "redpanda", "broker", "queue",
            "messaging", "eventbus", "servicebus", "pubsub", "stream",
        ],
        "search_engine": [
            "elastic", "opensearch", "solr", "meilisearch", "milvus",
            "qdrant", "typesense", "weaviate", "pinecone", "algolia",
            "search",
        ],
        "service_discovery": [
            "zookeeper", "consul", "etcd", "nacos", "eureka",
            "registry", "discovery",
        ],
        "identity": [
            "ldap", "keycloak", "okta", "auth0", "identity",
            "iam", "sso",
        ],
        "object_storage": [
            "minio", "ceph", "swift", "s3", "blob", "storage",
        ],
    }

    @classmethod
    def classify_service_category(cls, service_type: str, workload_name: str = "") -> str:
        if service_type and service_type != "unknown":
            if service_type in cls.SERVICE_CATEGORY_MAP:
                return service_type
            for category, types in cls.SERVICE_CATEGORY_MAP.items():
                if service_type in types:
                    return category
        name_lower = (workload_name or "").lower()
        if name_lower:
            for category, patterns in cls.NAME_CATEGORY_PATTERNS.items():
                for pattern in patterns:
                    if pattern in name_lower:
                        return category
        return "service"

    @classmethod
    def is_critical_service(cls, service_type: str, workload_name: str = "") -> bool:
        return cls.classify_service_category(service_type, workload_name) in cls.CRITICAL_CATEGORIES

    def _detect_service_type(self, port: int, app_protocol: str = None, workload_name: str = None) -> str:
        if app_protocol:
            proto_lower = str(app_protocol).lower()
            if proto_lower in ("grpc", "http", "https", "dns"):
                return proto_lower if proto_lower != "http" else "http-api"
        if port and port in self.PORT_SERVICE_MAP:
            return self.PORT_SERVICE_MAP[port]
        if workload_name:
            name_lower = workload_name.lower()
            for category, patterns in self.NAME_CATEGORY_PATTERNS.items():
                for pattern in patterns:
                    if pattern in name_lower:
                        for svc_type in self.SERVICE_CATEGORY_MAP.get(category, set()):
                            if pattern in svc_type:
                                return svc_type
                        return category
        return "unknown"

    def _build_communication_contract(
        self, protocol, app_protocol, port,
        request_count, bytes_transferred,
        error_count, retransmit_count, avg_latency_ms,
        last_seen, workload_name: str = ""
    ) -> dict:
        port_val = int(port) if port else 0
        req = int(request_count) if request_count else 0
        err = int(error_count) if error_count else 0
        error_rate = round((err / req) * 100, 4) if req > 0 else 0.0
        svc_type = self._detect_service_type(port_val, app_protocol, workload_name)
        svc_category = self.classify_service_category(svc_type, workload_name)
        return {
            "protocol": protocol,
            "app_protocol": app_protocol,
            "port": port_val,
            "service_type": svc_type,
            "service_category": svc_category,
            "is_critical": svc_category in self.CRITICAL_CATEGORIES,
            "request_count": req,
            "bytes_transferred": int(bytes_transferred) if bytes_transferred else 0,
            "error_count": err,
            "error_rate_percent": error_rate,
            "retransmit_count": int(retransmit_count) if retransmit_count else 0,
            "avg_latency_ms": round(float(avg_latency_ms), 2) if avg_latency_ms else 0.0,
            "last_seen": last_seen,
        }

    def _calculate_dependency_health(
        self, request_count, error_count, retransmit_count, avg_latency_ms
    ) -> dict:
        req = int(request_count) if request_count else 0
        err = int(error_count) if error_count else 0
        retx = int(retransmit_count) if retransmit_count else 0
        latency = float(avg_latency_ms) if avg_latency_ms else 0.0

        error_rate = (err / req) * 100 if req > 0 else 0.0
        retransmit_rate = (retx / req) * 100 if req > 0 else 0.0

        score = 100
        risk_factors = []

        if error_rate > 5:
            score -= 30
            risk_factors.append(f"high_error_rate:{error_rate:.2f}%")
        elif error_rate > 1:
            score -= 20
            risk_factors.append(f"elevated_error_rate:{error_rate:.2f}%")

        if retransmit_rate > 10:
            score -= 20
            risk_factors.append(f"high_retransmit_rate:{retransmit_rate:.2f}%")
        elif retransmit_rate > 5:
            score -= 10
            risk_factors.append(f"elevated_retransmit_rate:{retransmit_rate:.2f}%")

        if latency > 500:
            score -= 25
            risk_factors.append(f"very_high_latency:{latency:.1f}ms")
        elif latency > 100:
            score -= 15
            risk_factors.append(f"high_latency:{latency:.1f}ms")

        if req == 0:
            score = 0
            risk_factors.append("no_traffic")

        score = max(0, score)

        if score >= 80:
            status = "healthy"
        elif score >= 60:
            status = "degraded"
        elif score >= 30:
            status = "unhealthy"
        else:
            status = "critical"

        return {
            "score": score,
            "status": status,
            "error_rate_percent": round(error_rate, 4),
            "retransmit_rate_percent": round(retransmit_rate, 4),
            "avg_latency_ms": round(latency, 2),
            "risk_factors": risk_factors,
        }

    # ------------------------------------------------------------------
    # Shared helpers for logical name resolution (used by both
    # format_dependency_summary and find_unified_dependencies)
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_labels(entry: dict) -> dict:
        """Parse labels from entry — handles both str and dict forms."""
        raw = entry.get("labels", {})
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _parse_json_field(raw) -> dict:
        """Generic JSON field parser — handles str, dict, and None forms."""
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @staticmethod
    def _strip_template_hash(name: str, pth: str) -> str:
        """Strip pod-template-hash from a name, handling both
        ReplicaSet names (name-HASH) and pod names (name-HASH-RANDOM)."""
        if not pth:
            return name
        if name.endswith(f"-{pth}"):
            return name[:-(len(pth) + 1)]
        marker = f"-{pth}-"
        idx = name.find(marker)
        if idx > 0:
            return name[:idx]
        return name

    def _resolve_logical_name(self, entry: dict) -> str:
        """Resolve logical workload name from L4 dependency entry (for L7 join).

        Resolution order matches _workload_name in format_dependency_summary:
          1. app.kubernetes.io/name or app label
          2. owner_name (stripped of template hash)
          3. pod_name (stripped of template hash)
        """
        labels = self._safe_labels(entry)

        name = labels.get("app.kubernetes.io/name") or labels.get("app")
        if name:
            return str(name)

        pth = labels.get("pod-template-hash", "")
        owner = entry.get("owner_name") or ""
        if owner:
            return self._strip_template_hash(owner, pth)

        pod = entry.get("pod_name", "")
        return self._strip_template_hash(pod, pth)

    # ------------------------------------------------------------------
    # Unified L4+L7 dependency methods
    # ------------------------------------------------------------------

    def _batch_get_l7_edges(self, analysis_ids, pairs):
        """Batch L7 edge lookup.

        pairs: list of dicts with keys:
            src_ns, src_name, src_name_re, dst_ns, dst_name, dst_name_re
        src_name_re/dst_name_re are regex-escaped versions for safe =~ matching.

        Returns (all_results_dict, batch_success_count, batch_fail_count).
        """
        if not pairs:
            return {}, 0, 0
        aids = [str(a) for a in analysis_ids]
        prefixes = [f"{a}-" for a in aids]

        MAX_BATCH = 500
        all_results = {}
        batch_success = 0
        batch_fail = 0
        for i in range(0, len(pairs), MAX_BATCH):
            chunk = pairs[i:i + MAX_BATCH]
            query = """
            UNWIND $pairs AS pair
            OPTIONAL MATCH (src:L7Workload)-[r:L7_COMMUNICATES_WITH]->(dst:L7Workload)
            WHERE src.namespace = pair.src_ns
              AND dst.namespace = pair.dst_ns
              AND (src.name = pair.src_name OR src.name =~ (pair.src_name_re + '-\\\\d+$')
                   OR pair.src_name =~ (src.name + '-\\\\d+$'))
              AND (dst.name = pair.dst_name OR dst.name =~ (pair.dst_name_re + '-\\\\d+$')
                   OR pair.dst_name =~ (dst.name + '-\\\\d+$'))
              AND (r.analysis_id IN $aids OR ANY(p IN $prefixes WHERE r.analysis_id STARTS WITH p))
            WITH pair, collect(CASE WHEN r IS NOT NULL THEN {
                protocol: r.protocol,
                http_method: r.http_method,
                http_path: r.http_path,
                request_count: coalesce(r.request_count, 0),
                error_count: coalesce(r.error_count, 0),
                avg_latency_ms: coalesce(r.avg_latency_ms, 0.0)
            } END) AS edges
            RETURN pair.src_ns + ':' + pair.src_name + '->' + pair.dst_ns + ':' + pair.dst_name AS pair_key,
                   [e IN edges WHERE e IS NOT NULL] AS edges
            """
            result = self.execute_query(query, {"pairs": chunk, "aids": aids, "prefixes": prefixes})
            if result.get("success"):
                batch_success += 1
                for row in result.get("data", []):
                    all_results[row["pair_key"]] = row.get("edges", [])
            else:
                batch_fail += 1
                logger.warning("l7_batch_lookup_failed", extra={
                    "error": result.get("error"),
                    "batch_idx": i // MAX_BATCH,
                    "batch_size": len(chunk),
                    "analysis_ids": aids,
                })
        return all_results, batch_success, batch_fail

    def _aggregate_l7_edges(self, raw_edges: list) -> Optional[dict]:
        """Aggregate L7 edge metrics from one or more relationship records."""
        if not raw_edges:
            return None
        total_req = sum(e.get("request_count", 0) for e in raw_edges)
        total_err = sum(e.get("error_count", 0) for e in raw_edges)
        protocols = sorted(set(e.get("protocol", "") for e in raw_edges if e.get("protocol")))
        avg_lat = round(sum(e.get("avg_latency_ms", 0) for e in raw_edges) / len(raw_edges), 2)
        return {
            "total_requests": total_req,
            "total_errors": total_err,
            "error_rate_percent": round((total_err / total_req * 100), 2) if total_req > 0 else 0.0,
            "avg_latency_ms": avg_lat,
            "protocols": protocols,
            "last_observed_method": raw_edges[-1].get("http_method", ""),
            "last_observed_path": raw_edges[-1].get("http_path", ""),
        }

    def find_unified_dependencies(self, analysis_ids=None, depth=1, include_l7=True, **kwargs):
        """Find L4 dependencies and enrich with L7 metrics at query-time."""
        l4_result = self.find_pod_dependencies(analysis_ids=analysis_ids, depth=depth, **kwargs)
        if not l4_result.get("success") or not include_l7:
            l4_result["l7_lookup_status"] = "skipped" if not include_l7 else "n/a"
            return l4_result

        pairs = []
        pair_index: Dict[str, list] = {}
        for ri, result in enumerate(l4_result.get("results", [])):
            up = result.get("upstream", {})
            up_name = self._resolve_logical_name(up)
            up_ns = up.get("namespace", "")
            for direction in ("downstream", "callers"):
                for di, dep in enumerate(result.get(direction, [])):
                    dep_name = self._resolve_logical_name(dep)
                    dep_ns = dep.get("namespace", "")
                    if not up_name or not dep_name:
                        continue
                    if direction == "downstream":
                        src_ns, src_name = up_ns, up_name
                        dst_ns, dst_name = dep_ns, dep_name
                    else:
                        src_ns, src_name = dep_ns, dep_name
                        dst_ns, dst_name = up_ns, up_name
                    pair_key = f"{src_ns}:{src_name}->{dst_ns}:{dst_name}"
                    if pair_key not in pair_index:
                        pairs.append({
                            "src_ns": src_ns, "src_name": src_name,
                            "src_name_re": re.escape(src_name),
                            "dst_ns": dst_ns, "dst_name": dst_name,
                            "dst_name_re": re.escape(dst_name),
                        })
                        pair_index[pair_key] = []
                    pair_index[pair_key].append((ri, direction, di))

        l7_map, batch_success, batch_fail = self._batch_get_l7_edges(analysis_ids, pairs)

        l7_pairs_matched = 0
        for pair_key, locations in pair_index.items():
            raw_edges = l7_map.get(pair_key, [])
            l7_details = self._aggregate_l7_edges(raw_edges)
            if l7_details is not None:
                l7_pairs_matched += 1
            for ri, direction, di in locations:
                l4_result["results"][ri][direction][di]["l7_details"] = l7_details
                l4_result["results"][ri][direction][di]["has_l7_data"] = l7_details is not None

        if batch_fail > 0 and batch_success == 0:
            status = "error"
        elif batch_fail > 0 and batch_success > 0:
            status = "partial"
        elif not pairs:
            status = "no_pairs"
        else:
            status = "ok"
        l4_result["l7_lookup_status"] = status
        l4_result["l7_pairs_checked"] = len(pairs)
        l4_result["l7_pairs_matched"] = l7_pairs_matched
        l4_result["l7_batch_success"] = batch_success
        l4_result["l7_batch_fail"] = batch_fail
        return l4_result

    def _is_ip_address(self, value: str) -> bool:
        """Check if a string is a valid IP address"""
        if not value:
            return False
        # IPv4 pattern
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if re.match(ipv4_pattern, value):
            parts = value.split('.')
            return all(0 <= int(p) <= 255 for p in parts)
        return False
    
    def close(self):
        """Close Neo4j driver connection"""
        if self.driver:
            self.driver.close()
            logger.info("🔌 Neo4j connection closed")


# Singleton instance
_query_engine_instance: Optional[GraphQueryEngine] = None


def get_query_engine() -> GraphQueryEngine:
    """Get singleton query engine instance"""
    global _query_engine_instance
    if _query_engine_instance is None:
        _query_engine_instance = GraphQueryEngine()
    return _query_engine_instance


# Create singleton instance for direct import
graph_query_engine = get_query_engine()
