"""Graph Database Query Engine - Neo4j Implementation"""

import json
import logging
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver, Session, Result
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.config import settings

logger = logging.getLogger(__name__)


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
            dst.pod_uid AS destination_pod_uid,
            dst.host_ip AS destination_host_ip,
            dst.container AS destination_container,
            dst.image AS destination_image,
            dst.service_account AS destination_service_account,
            dst.phase AS destination_phase,
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
                CASE WHEN w.owner_kind = 'Service' THEN 'Service' ELSE COALESCE(labels(w)[0], 'Workload') END AS kind,
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
            # Parse node ID format: cluster_id:namespace:name
            for node_id in missing_node_ids:
                parts = node_id.split(":", 2)  # Split into max 3 parts
                if len(parts) >= 3:
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
                
                synthetic_node = {
                    "id": node_id,
                    "name": node_name,
                    "kind": "Workload",
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
        include_communication_details: bool = True
    ) -> Dict[str, Any]:
        """
        Find a pod by any metadata and return its upstream/downstream dependencies.
        
        The matched pod is the "upstream" (source). All pods it communicates with
        are "downstream" (targets). Pods that communicate TO the matched pod are
        also returned as callers (reverse upstream).
        
        Any combination of search parameters can be used. At least one is required.
        
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
            ann_key_prefix = annotation_key.split('*')[0] if '*' in annotation_key else annotation_key
            if ann_key_prefix:
                match_conditions.append(
                    "w.annotations CONTAINS $annotation_key_search"
                )
                params["annotation_key_search"] = f'"{ann_key_prefix}'
        
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
        
        if not match_conditions:
            return {"success": False, "error": "At least one search parameter required (pod_name, namespace, owner_name, ip, annotation_key, label_key)", "count": 0, "results": []}
        
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
                if not annotation_value or annotation_value == '*':
                    filtered.append(pod)
                    continue
                ann_val_has_glob = '*' in annotation_value or '?' in annotation_value
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
        first = results[0]
        upstream = first.get("upstream", {})
        is_multi = len(results) > 1

        def _safe_labels(entry: dict) -> dict:
            lbl = entry.get("labels") or {}
            if isinstance(lbl, str):
                try:
                    lbl = json.loads(lbl)
                except (json.JSONDecodeError, TypeError):
                    lbl = {}
            return lbl

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
            return False

        _KIND_ALIASES = {"ReplicaSet": "Deployment"}

        _NOISE_ANNOTATION_PREFIXES = (
            'kubectl.kubernetes.io/',
            'kubernetes.io/',
            'openshift.io/',
            'openshift.openshift.io/',
            'k8s.v1.cni.cncf.io/',
            'k8s.ovn.org/',
            'seccomp.security.alpha.kubernetes.io/',
        )

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

        def _filter_summary_annotations(ann: dict) -> dict:
            if not ann or not isinstance(ann, dict):
                return ann or {}
            return {
                k: v for k, v in ann.items()
                if not any(k.startswith(p) for p in _NOISE_ANNOTATION_PREFIXES)
                and len(str(v)) < 500
            }

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
            return {
                "name": _workload_name(entry),
                "namespace": entry.get("namespace", ""),
                "kind": _resolve_kind(entry.get("owner_kind", ""), labels),
                "annotations": _filter_summary_annotations(entry.get("annotations", {})),
                "labels": labels,
                "is_critical": is_crit,
                "service_type": svc_type,
                "service_category": svc_cat,
                "port": comm.get("port"),
            }

        def _dedup_entries(entries: list) -> list:
            """Deduplicate dependency entries by logical workload identity,
            collapsing replica pods that share the same Deployment/StatefulSet."""
            seen: Dict[str, dict] = {}
            for entry in entries:
                key = _workload_key(entry)
                if key not in seen:
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

        if is_multi:
            all_downstream = []
            all_callers = []
            workload_map: Dict[str, dict] = {}
            for res in results:
                up = res.get("upstream", {})
                ds = res.get("downstream", [])
                cl = res.get("callers", [])
                all_downstream.extend(ds)
                all_callers.extend(cl)
                up_key = _workload_key(up)
                up_labels = _safe_labels(up)
                if up_key in workload_map:
                    workload_map[up_key]["downstream_count"] += len(ds)
                    workload_map[up_key]["callers_count"] += len(cl)
                    existing = workload_map[up_key]
                    resolved = _resolve_kind(up.get("owner_kind", ""), up_labels)
                    if (not existing["kind"] or existing["kind"] == "Unknown") and resolved not in ("", "Unknown"):
                        existing["kind"] = resolved
                    if not existing["annotations"] and up.get("annotations"):
                        existing["annotations"] = _filter_summary_annotations(up["annotations"])
                else:
                    workload_map[up_key] = {
                        "name": _workload_name(up),
                        "namespace": up.get("namespace", ""),
                        "kind": _resolve_kind(up.get("owner_kind", ""), up_labels),
                        "annotations": _filter_summary_annotations(up.get("annotations", {})),
                        "labels": up_labels,
                        "downstream_count": len(ds),
                        "callers_count": len(cl),
                    }
            matched_services = list(workload_map.values())
            all_downstream = _filter_and_dedup(all_downstream)
            all_callers = _filter_and_dedup(all_callers)
            all_namespaces = sorted(set(s["namespace"] for s in matched_services if s["namespace"]))
            if len(all_namespaces) == 1:
                svc_label = f"{all_namespaces[0]} ({len(matched_services)} services)"
                svc_ns = all_namespaces[0]
            else:
                svc_label = f"{len(matched_services)} services across {len(all_namespaces)} namespaces"
                svc_ns = ", ".join(all_namespaces)
            return {
                "success": True,
                "analysis_ids": int_ids,
                "multi_service": True,
                "service": {
                    "name": svc_label,
                    "namespace": svc_ns,
                    "kind": "",
                    "annotations": {},
                    "labels": {},
                },
                "matched_services": matched_services,
                "downstream": _group_by_category(all_downstream, "downstream"),
                "callers": _group_by_category(all_callers, "caller"),
            }

        single_downstream = _filter_and_dedup(first.get("downstream", []))
        single_callers = _filter_and_dedup(first.get("callers", []))
        return {
            "success": True,
            "analysis_ids": int_ids,
            "multi_service": False,
            "service": {
                "name": _workload_name(upstream),
                "namespace": upstream.get("namespace", ""),
                "kind": _resolve_kind(upstream.get("owner_kind", ""), _safe_labels(upstream)),
                "annotations": _filter_summary_annotations(upstream.get("annotations", {})),
                "labels": _safe_labels(upstream),
            },
            "downstream": _group_by_category(single_downstream, "downstream"),
            "callers": _group_by_category(single_callers, "caller"),
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

    def _is_ip_address(self, value: str) -> bool:
        """Check if a string is a valid IP address"""
        if not value:
            return False
        import re
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
