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
            w.created_at AS created_at
        ORDER BY w.namespace, w.name
        LIMIT $limit
        """
        
        return self.execute_query(query, params)
    
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
        # Neo4j stores labels as JSON string, but frontend expects object
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
