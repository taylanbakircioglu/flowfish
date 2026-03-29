"""
Neo4j graph database connection and utilities
Replaces NebulaGraph with Neo4j for production stability
"""

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from typing import List, Dict, Any, Optional
import structlog
import json
import asyncio

from config import settings, get_neo4j_config

logger = structlog.get_logger()

# Global driver instance
neo4j_driver: Optional[GraphDatabase.driver] = None


def get_neo4j_driver() -> GraphDatabase.driver:
    """Get Neo4j driver (singleton pattern)"""
    global neo4j_driver
    if neo4j_driver is None:
        config = get_neo4j_config()
        
        try:
            neo4j_driver = GraphDatabase.driver(
                config["uri"],
                auth=(config["user"], config["password"]),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_timeout=30,
                encrypted=False  # For internal cluster communication
            )
            
            # Test connection
            neo4j_driver.verify_connectivity()
            
            logger.info("Neo4j connection established", uri=config["uri"])
            
        except AuthError as e:
            logger.error("Neo4j authentication failed", error=str(e))
            raise
        except ServiceUnavailable as e:
            logger.error("Neo4j service unavailable", error=str(e))
            raise
        except Exception as e:
            logger.error("Neo4j connection failed", error=str(e))
            raise
    
    return neo4j_driver


# Initialize driver
neo4j_driver = get_neo4j_driver()


class Neo4jService:
    """Neo4j service for graph operations"""
    
    def __init__(self, driver: GraphDatabase.driver):
        self.driver = driver
        self.config = get_neo4j_config()
        self.database = self.config.get("database", "neo4j")
    
    def _execute_query(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute Cypher query and return results
        
        Args:
            query: Cypher query string
            parameters: Query parameters (prevents injection)
        
        Returns:
            List of result records as dictionaries
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters or {})
                records = [dict(record) for record in result]
                logger.debug("Query executed", query=query[:100], record_count=len(records))
                return records
                
        except Exception as e:
            logger.error("Neo4j query execution failed", error=str(e), query=query[:200])
            return None
    
    def _execute_delete(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Execute delete query and return count of deleted elements.
        Uses Neo4j's result summary counters for accurate counts.
        
        Args:
            query: Cypher DELETE query string
            parameters: Query parameters
        
        Returns:
            Number of deleted nodes + relationships
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters or {})
                summary = result.consume()
                deleted_nodes = summary.counters.nodes_deleted
                deleted_rels = summary.counters.relationships_deleted
                total = deleted_nodes + deleted_rels
                logger.debug("Delete query executed", 
                            query=query[:100], 
                            deleted_nodes=deleted_nodes,
                            deleted_rels=deleted_rels)
                return total
                
        except Exception as e:
            logger.error("Neo4j delete query failed", error=str(e), query=query[:200])
            return 0
    
    def _execute_write(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Execute write query (CREATE, MERGE, SET, DELETE)
        
        Args:
            query: Cypher query string
            parameters: Query parameters
        
        Returns:
            Success boolean
        """
        try:
            with self.driver.session(database=self.database) as session:
                session.run(query, parameters or {})
                logger.debug("Write query executed", query=query[:100])
                return True
                
        except Exception as e:
            logger.error("Neo4j write query failed", error=str(e), query=query[:200])
            return False
    
    def insert_cluster(self, cluster_id: str, name: str, cluster_type: str) -> bool:
        """
        Insert or update cluster node
        
        Args:
            cluster_id: Unique cluster identifier
            name: Cluster name
            cluster_type: Type (kubernetes, openshift, etc.)
        
        Returns:
            Success boolean
        """
        query = """
        MERGE (c:Cluster {id: $cluster_id})
        SET c.name = $name,
            c.cluster_type = $cluster_type,
            c.is_active = true,
            c.updated_at = timestamp()
        RETURN c
        """
        
        params = {
            "cluster_id": cluster_id,
            "name": name,
            "cluster_type": cluster_type
        }
        
        return self._execute_write(query, params)
    
    def insert_workload(
        self, 
        workload_id: str, 
        name: str, 
        namespace: str, 
        kind: str,
        cluster_id: str, 
        ip: str = "", 
        status: str = "Unknown"
    ) -> bool:
        """
        Insert or update workload node (Pod, Deployment, StatefulSet, Service)
        
        Args:
            workload_id: Unique workload identifier
            name: Workload name
            namespace: Kubernetes namespace
            kind: Workload kind (Pod, Deployment, etc.)
            cluster_id: Parent cluster ID
            ip: IP address (for Pods)
            status: Current status
        
        Returns:
            Success boolean
        """
        query = """
        MERGE (w:Workload {id: $workload_id})
        SET w.name = $name,
            w.namespace = $namespace,
            w.kind = $kind,
            w.cluster = $cluster_id,
            w.ip_address = $ip,
            w.status = $status,
            w.is_active = true,
            w.updated_at = timestamp()
        
        WITH w
        MERGE (n:Namespace {name: $namespace, cluster: $cluster_id})
        MERGE (w)-[:PART_OF {relation_type: 'namespace'}]->(n)
        
        WITH w
        MERGE (c:Cluster {id: $cluster_id})
        MERGE (w)-[:PART_OF {relation_type: 'cluster'}]->(c)
        
        RETURN w
        """
        
        params = {
            "workload_id": workload_id,
            "name": name,
            "namespace": namespace,
            "kind": kind,
            "cluster_id": cluster_id,
            "ip": ip,
            "status": status
        }
        
        return self._execute_write(query, params)
    
    def insert_communication(
        self, 
        source_id: str, 
        dest_id: str, 
        port: int, 
        protocol: str,
        direction: str = "outbound",
        request_count: int = 0,
        bytes_transferred: int = 0,
        is_active: bool = True
    ) -> bool:
        """
        Insert or update communication edge between workloads
        
        Args:
            source_id: Source workload ID
            dest_id: Destination workload ID
            port: Destination port
            protocol: Protocol (TCP, UDP, HTTP, etc.)
            direction: Communication direction
            request_count: Number of requests
            bytes_transferred: Bytes transferred
            is_active: Whether communication is currently active
        
        Returns:
            Success boolean
        """
        query = """
        MATCH (src:Workload {id: $source_id})
        MATCH (dst:Workload {id: $dest_id})
        
        MERGE (src)-[c:COMMUNICATES_WITH {
            port: $port,
            protocol: $protocol
        }]->(dst)
        
        SET c.direction = $direction,
            c.request_count = coalesce(c.request_count, 0) + $request_count,
            c.bytes_transferred = coalesce(c.bytes_transferred, 0) + $bytes_transferred,
            c.is_active = $is_active,
            c.last_seen = timestamp(),
            c.first_seen = coalesce(c.first_seen, timestamp())
        
        RETURN c
        """
        
        params = {
            "source_id": source_id,
            "dest_id": dest_id,
            "port": port,
            "protocol": protocol,
            "direction": direction,
            "request_count": request_count,
            "bytes_transferred": bytes_transferred,
            "is_active": is_active
        }
        
        return self._execute_write(query, params)
    
    def get_graph_data(
        self, 
        cluster_id: str, 
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get graph data for visualization (nodes + edges)
        
        Args:
            cluster_id: Cluster identifier
            namespace: Optional namespace filter
        
        Returns:
            Dictionary with nodes and edges for visualization
        """
        # Build filter conditions
        node_filter = "w.cluster = $cluster_id"
        if namespace:
            node_filter += " AND w.namespace = $namespace"
        
        # Get nodes
        nodes_query = f"""
        MATCH (w:Workload)
        WHERE {node_filter}
        RETURN w.id as id, 
               labels(w) as type, 
               properties(w) as props
        """
        
        # Get edges
        edge_filter = "src.cluster = $cluster_id AND dst.cluster = $cluster_id"
        if namespace:
            edge_filter += " AND (src.namespace = $namespace OR dst.namespace = $namespace)"
        
        edges_query = f"""
        MATCH (src:Workload)-[e:COMMUNICATES_WITH]->(dst:Workload)
        WHERE {edge_filter}
        RETURN src.id as source, 
               dst.id as target,
               e.port as port,
               e.protocol as protocol,
               e.direction as direction,
               e.request_count as request_count,
               e.bytes_transferred as bytes_transferred,
               e.is_active as is_active
        """
        
        params = {"cluster_id": cluster_id}
        if namespace:
            params["namespace"] = namespace
        
        nodes = self._execute_query(nodes_query, params) or []
        edges = self._execute_query(edges_query, params) or []
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        }
    
    def get_cross_namespace_communications(
        self, 
        cluster_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get cross-namespace communications (potential security risk)
        
        Args:
            cluster_id: Cluster identifier
        
        Returns:
            List of cross-namespace communication records
        """
        query = """
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
        WHERE src.cluster = $cluster_id 
          AND dst.cluster = $cluster_id
          AND src.namespace <> dst.namespace
          AND comm.is_active = true
        RETURN src.namespace as source_namespace,
               src.name as source_name,
               dst.namespace as dest_namespace,
               dst.name as dest_name,
               comm.port as port,
               comm.protocol as protocol,
               comm.request_count as request_count
        ORDER BY comm.request_count DESC
        """
        
        params = {"cluster_id": cluster_id}
        return self._execute_query(query, params) or []
    
    def get_external_communications(
        self, 
        cluster_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get external communications (outside cluster)
        
        Args:
            cluster_id: Cluster identifier
        
        Returns:
            List of external communication records
        """
        query = """
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE src.cluster = $cluster_id 
          AND comm.is_active = true
          AND NOT (dst:Workload AND dst.cluster = $cluster_id)
        RETURN src.namespace as namespace,
               src.name as source_name,
               dst.ip_address as destination_ip,
               comm.port as port,
               comm.protocol as protocol,
               comm.request_count as request_count
        ORDER BY comm.request_count DESC
        """
        
        params = {"cluster_id": cluster_id}
        return self._execute_query(query, params) or []

    def get_workloads(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all workloads for a cluster or analysis
        
        Uses same filtering pattern as graph-query service:
        - Combines all conditions with AND
        - Multi-cluster support for analysis_id
        
        Args:
            cluster_id: Cluster identifier
            analysis_id: Analysis identifier
        
        Returns:
            List of workload records
        """
        # Build conditions list (same pattern as graph-query service)
        conditions = ["w.is_active = true"]
        params = {}
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append("(w.analysis_id = $analysis_id OR w.analysis_id STARTS WITH $analysis_id_prefix)")
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("(w.cluster = $cluster_id OR w.cluster_id = $cluster_id)")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (w:Workload)
        WHERE {where_clause}
        RETURN w.id as id,
               w.name as name,
               w.namespace as namespace,
               w.kind as type,
               w.status as status,
               properties(w) as metadata
        """
        
        return self._execute_query(query, params) or []

    def get_communications(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all communications for a cluster or analysis
        
        Uses same filtering pattern as graph-query service:
        - Combines all conditions with AND
        - Multi-cluster support for analysis_id
        
        Args:
            cluster_id: Cluster identifier
            analysis_id: Analysis identifier
        
        Returns:
            List of communication records
        """
        # Build conditions list (same pattern as graph-query service)
        conditions = []
        params = {}
        
        # Multi-cluster support: match both single and multi-cluster analysis_id formats
        if analysis_id:
            analysis_id_str = str(analysis_id)
            analysis_id_prefix = f"{analysis_id_str}-"
            conditions.append(
                "(comm.analysis_id = $analysis_id OR comm.analysis_id STARTS WITH $analysis_id_prefix OR "
                "src.analysis_id = $analysis_id OR src.analysis_id STARTS WITH $analysis_id_prefix)"
            )
            params["analysis_id"] = analysis_id_str
            params["analysis_id_prefix"] = analysis_id_prefix
        
        if cluster_id:
            conditions.append("(src.cluster_id = $cluster_id OR comm.cluster_id = $cluster_id)")
            params["cluster_id"] = str(cluster_id)
        
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        query = f"""
        MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst)
        WHERE {where_clause}
        RETURN src.id as source_id,
               dst.id as target_id,
               comm.port as port,
               comm.protocol as protocol,
               comm.request_count as request_count,
               comm.bytes_transferred as bytes_transferred
        """
        
        return self._execute_query(query, params) or []

    def get_workload_incoming_connections(
        self,
        cluster_id: int,
        analysis_id: Optional[int],
        namespace: str,
        workload_name: str
    ) -> List[Dict[str, Any]]:
        """
        Get incoming connections to a workload (for network policy generation)
        
        Args:
            cluster_id: Cluster identifier
            analysis_id: Analysis identifier
            namespace: Target namespace
            workload_name: Target workload name
        
        Returns:
            List of incoming connection records
        """
        if analysis_id:
            vid_prefix = f"{analysis_id}:"
            query = """
            MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
            WHERE dst.id STARTS WITH $vid_prefix
              AND dst.namespace = $namespace
              AND dst.name CONTAINS $workload_name
            RETURN src.id as id,
                   src.name as name,
                   src.namespace as namespace,
                   src.kind as kind,
                   comm.port as port,
                   comm.protocol as protocol,
                   comm.request_count as request_count,
                   'incoming' as direction,
                   CASE WHEN src.namespace = 'external' OR src.name CONTAINS '.' THEN true ELSE false END as is_external
            """
            params = {
                "vid_prefix": vid_prefix,
                "namespace": namespace,
                "workload_name": workload_name
            }
        else:
            query = """
            MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
            WHERE dst.cluster = $cluster_id
              AND dst.namespace = $namespace
              AND dst.name CONTAINS $workload_name
            RETURN src.id as id,
                   src.name as name,
                   src.namespace as namespace,
                   src.kind as kind,
                   comm.port as port,
                   comm.protocol as protocol,
                   comm.request_count as request_count,
                   'incoming' as direction,
                   CASE WHEN src.namespace = 'external' OR src.name CONTAINS '.' THEN true ELSE false END as is_external
            """
            params = {
                "cluster_id": str(cluster_id),
                "namespace": namespace,
                "workload_name": workload_name
            }
        
        return self._execute_query(query, params) or []

    def get_workload_outgoing_connections(
        self,
        cluster_id: int,
        analysis_id: Optional[int],
        namespace: str,
        workload_name: str
    ) -> List[Dict[str, Any]]:
        """
        Get outgoing connections from a workload (for network policy generation)
        
        Args:
            cluster_id: Cluster identifier
            analysis_id: Analysis identifier
            namespace: Source namespace
            workload_name: Source workload name
        
        Returns:
            List of outgoing connection records
        """
        if analysis_id:
            vid_prefix = f"{analysis_id}:"
            query = """
            MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
            WHERE src.id STARTS WITH $vid_prefix
              AND src.namespace = $namespace
              AND src.name CONTAINS $workload_name
            RETURN dst.id as id,
                   dst.name as name,
                   dst.namespace as namespace,
                   dst.kind as kind,
                   dst.ip_address as ip,
                   comm.port as port,
                   comm.protocol as protocol,
                   comm.request_count as request_count,
                   'outgoing' as direction,
                   CASE WHEN dst.namespace = 'external' OR dst.name CONTAINS '.' THEN true ELSE false END as is_external
            """
            params = {
                "vid_prefix": vid_prefix,
                "namespace": namespace,
                "workload_name": workload_name
            }
        else:
            query = """
            MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
            WHERE src.cluster = $cluster_id
              AND src.namespace = $namespace
              AND src.name CONTAINS $workload_name
            RETURN dst.id as id,
                   dst.name as name,
                   dst.namespace as namespace,
                   dst.kind as kind,
                   dst.ip_address as ip,
                   comm.port as port,
                   comm.protocol as protocol,
                   comm.request_count as request_count,
                   'outgoing' as direction,
                   CASE WHEN dst.namespace = 'external' OR dst.name CONTAINS '.' THEN true ELSE false END as is_external
            """
            params = {
                "cluster_id": str(cluster_id),
                "namespace": namespace,
                "workload_name": workload_name
            }
        
        return self._execute_query(query, params) or []

    def get_workload_dependencies(
        self, 
        cluster_id: int,
        analysis_id: Optional[int],
        namespace: str,
        workload_name: str
    ) -> Dict[str, Any]:
        """
        Get workload dependencies for impact simulation (1-hop and 2-hop)
        
        Args:
            cluster_id: Cluster identifier
            analysis_id: Analysis identifier
            namespace: Target namespace
            workload_name: Target workload name
        
        Returns:
            Dictionary with direct and indirect dependencies
        """
        import structlog
        logger = structlog.get_logger(__name__)
        
        logger.info(
            "get_workload_dependencies called",
            cluster_id=cluster_id,
            target_analysis_id=analysis_id,
            namespace=namespace,
            workload_name=workload_name
        )
        
        # Find the target workload node(s)
        # Try multiple matching strategies for robustness
        if analysis_id:
            vid_prefix = f"{analysis_id}:"
            # Strategy 1: Exact namespace and name contains
            target_query = """
            MATCH (target:Workload)
            WHERE target.id STARTS WITH $vid_prefix
              AND (target.namespace = $namespace OR target.namespace CONTAINS $namespace OR $namespace CONTAINS target.namespace)
              AND (target.name CONTAINS $workload_name OR $workload_name CONTAINS target.name)
            RETURN target.id as id, target.name as name, target.namespace as ns
            """
            params = {
                "vid_prefix": vid_prefix,
                "namespace": namespace,
                "workload_name": workload_name
            }
        else:
            target_query = """
            MATCH (target:Workload)
            WHERE target.cluster = $cluster_id
              AND (target.namespace = $namespace OR target.namespace CONTAINS $namespace OR $namespace CONTAINS target.namespace)
              AND (target.name CONTAINS $workload_name OR $workload_name CONTAINS target.name)
            RETURN target.id as id, target.name as name, target.namespace as ns
            """
            params = {
                "cluster_id": str(cluster_id),
                "namespace": namespace,
                "workload_name": workload_name
            }
        
        target_nodes = self._execute_query(target_query, params) or []
        
        logger.info(
            "Target node search result",
            query_params=params,
            found_count=len(target_nodes),
            found_nodes=target_nodes[:5] if target_nodes else []
        )
        
        # If no results, try a broader search to help debug
        if not target_nodes and analysis_id:
            debug_query = """
            MATCH (target:Workload)
            WHERE target.id STARTS WITH $vid_prefix
            RETURN DISTINCT target.namespace as ns, count(*) as cnt
            LIMIT 20
            """
            debug_result = self._execute_query(debug_query, {"vid_prefix": vid_prefix}) or []
            logger.warning(
                "No target found - available namespaces in analysis",
                target_analysis_id=analysis_id,
                requested_namespace=namespace,
                available_namespaces=debug_result
            )
        
        if not target_nodes:
            return {
                "direct_dependencies": [],
                "indirect_dependencies": [],
                "node_matches": 0,
                "has_external_connections": False,
                "confidence": 0.0
            }
        
        target_ids = [n["id"] for n in target_nodes]
        
        # Get direct dependencies (1-hop)
        direct_query = """
        MATCH (target:Workload)-[comm:COMMUNICATES_WITH]-(dep:Workload)
        WHERE target.id IN $target_ids
          AND NOT dep.id IN $target_ids
        RETURN DISTINCT dep.id as id,
               dep.name as name,
               dep.namespace as namespace,
               dep.kind as kind,
               comm.port as port,
               comm.protocol as protocol,
               comm.request_count as request_count,
               CASE WHEN (target)-[comm]->(dep) THEN 'outgoing' ELSE 'incoming' END as direction,
               CASE WHEN dep.namespace = 'external' OR dep.name CONTAINS '.' THEN true ELSE false END as is_external
        """
        
        direct_deps = self._execute_query(direct_query, {"target_ids": target_ids}) or []
        direct_ids = [d["id"] for d in direct_deps]
        
        # Get indirect dependencies (2-hop)
        if direct_ids:
            indirect_query = """
            MATCH (direct:Workload)-[comm:COMMUNICATES_WITH]-(indirect:Workload)
            WHERE direct.id IN $direct_ids
              AND NOT indirect.id IN $target_ids
              AND NOT indirect.id IN $direct_ids
            RETURN DISTINCT indirect.id as id,
                   indirect.name as name,
                   indirect.namespace as namespace,
                   indirect.kind as kind,
                   comm.port as port,
                   comm.protocol as protocol,
                   comm.request_count as request_count,
                   CASE WHEN indirect.namespace = 'external' OR indirect.name CONTAINS '.' THEN true ELSE false END as is_external
            """
            
            indirect_deps = self._execute_query(indirect_query, {
                "direct_ids": direct_ids,
                "target_ids": target_ids
            }) or []
        else:
            indirect_deps = []
        
        # Check for external connections
        has_external = any(d.get("is_external", False) for d in direct_deps + indirect_deps)
        
        # Calculate confidence based on data quality
        total_deps = len(direct_deps) + len(indirect_deps)
        confidence = min(1.0, 0.5 + (total_deps * 0.05)) if total_deps > 0 else 0.3
        
        return {
            "direct_dependencies": direct_deps,
            "indirect_dependencies": indirect_deps,
            "node_matches": len(target_nodes),
            "has_external_connections": has_external,
            "confidence": confidence
        }
    
    def delete_analysis_data(
        self, 
        analysis_id: int,
        cluster_id: Optional[int] = None,
        batch_size: int = 10000
    ) -> Dict[str, Any]:
        """
        Delete all graph data associated with an analysis using batch processing
        
        FULL ISOLATION DELETION (v3.0):
        With the new VID format {analysis_id}:{cluster_id}:{namespace}:{workload},
        each analysis has completely isolated graph data. We can safely delete
        both nodes and edges by matching the VID prefix.
        
        VID Format: {analysis_id}:{cluster_id}:{namespace}:{workload}
        Example: "26:1:prod-payments:payments-pod-xyz"
        
        Deletion is done by:
        1. Matching all nodes where n.id STARTS WITH '{analysis_id}:'
        2. Using DETACH DELETE to remove nodes and their edges together
        
        This approach ensures:
        - Complete isolation between analyses
        - No orphan node accumulation
        - Fast and simple deletion
        
        Args:
            analysis_id: Analysis ID to delete data for
            cluster_id: Optional cluster_id (for logging only)
            batch_size: Number of elements to delete per batch (default 10000)
        
        Returns:
            Dictionary with deletion summary
        """
        import time
        start_time = time.time()
        
        analysis_id_str = str(analysis_id)
        total_nodes = 0
        total_edges = 0
        batches = 0
        
        # VID prefix for this analysis (includes trailing colon to prevent partial matches)
        # e.g., "26:" will match "26:1:ns:pod" but NOT "260:1:ns:pod"
        vid_prefix = f"{analysis_id_str}:"
        
        # Step 0: Diagnostic - count nodes/edges for this analysis
        diagnostic = {"total_nodes": 0, "total_edges": 0, "analysis_nodes": 0, "analysis_edges": 0}
        try:
            # Total counts
            total_nodes_query = "MATCH (n) RETURN count(n) as cnt"
            total_edges_query = "MATCH ()-[r]->() RETURN count(r) as cnt"
            
            result = self._execute_query(total_nodes_query, {})
            diagnostic["total_nodes"] = result[0]["cnt"] if result else 0
            
            result = self._execute_query(total_edges_query, {})
            diagnostic["total_edges"] = result[0]["cnt"] if result else 0
            
            # Count nodes for this analysis (by VID prefix)
            analysis_nodes_query = """
                MATCH (n) WHERE n.id STARTS WITH $vid_prefix
                RETURN count(n) as cnt
            """
            result = self._execute_query(analysis_nodes_query, {"vid_prefix": vid_prefix})
            diagnostic["analysis_nodes"] = result[0]["cnt"] if result else 0
            
            # Count edges for this analysis (by VID prefix on source node)
            analysis_edges_query = """
                MATCH (src)-[r]->(dst) 
                WHERE src.id STARTS WITH $vid_prefix
                RETURN count(r) as cnt
            """
            result = self._execute_query(analysis_edges_query, {"vid_prefix": vid_prefix})
            diagnostic["analysis_edges"] = result[0]["cnt"] if result else 0
            
            logger.info("Neo4j diagnostic before deletion",
                       target_analysis_id=analysis_id,
                       vid_prefix=vid_prefix,
                       total_nodes=diagnostic["total_nodes"],
                       total_edges=diagnostic["total_edges"],
                       analysis_nodes=diagnostic["analysis_nodes"],
                       analysis_edges=diagnostic["analysis_edges"])
        except Exception as e:
            logger.warning(f"Diagnostic query failed: {e}")
        
        initial_nodes = diagnostic.get("analysis_nodes", 0)
        initial_edges = diagnostic.get("analysis_edges", 0)
        
        logger.info("Starting FULL ISOLATION deletion (nodes + edges by VID prefix)",
                   target_analysis_id=analysis_id,
                   vid_prefix=vid_prefix,
                   initial_nodes=initial_nodes,
                   initial_edges=initial_edges,
                   batch_size=batch_size)
        
        # Step 1: Delete all nodes (and their edges) by VID prefix
        # DETACH DELETE removes the node and all its relationships
        while True:
            delete_query = """
            MATCH (n)
            WHERE n.id STARTS WITH $vid_prefix
            WITH n LIMIT $batch_size
            DETACH DELETE n
            """
            
            try:
                deleted = self._execute_delete(delete_query, {
                    "vid_prefix": vid_prefix,
                    "batch_size": batch_size
                })
                
                total_nodes += deleted
                batches += 1
                
                if deleted < batch_size:
                    break  # Last batch
                
                logger.debug(f"Deleted batch {batches}: {deleted} nodes")
            except Exception as e:
                logger.warning(f"Node deletion failed: {e}")
                break
        
        # Estimate edges deleted (DETACH DELETE doesn't return edge count)
        # We use the initial edge count as the best estimate
        total_edges = initial_edges
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info("FULL ISOLATION deletion completed",
                   target_analysis_id=analysis_id,
                   vid_prefix=vid_prefix,
                   deleted_nodes=total_nodes,
                   deleted_edges_estimate=total_edges,
                   batches=batches,
                   duration_ms=duration_ms)
        
        return {
            "deleted_edges": total_edges,
            "deleted_nodes": total_nodes,
            "orphaned_nodes": 0,
            "batches": batches,
            "duration_ms": duration_ms,
            "analysis_id": analysis_id,
            "cluster_id": cluster_id,
            "diagnostic": diagnostic
        }
    
    def close(self):
        """Close Neo4j driver connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j driver closed")


# Service instance
neo4j_service = Neo4jService(neo4j_driver)


def test_neo4j_connection() -> bool:
    """
    Test Neo4j connection
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            
            if record and record["test"] == 1:
                logger.info("Neo4j connection test successful")
                return True
            else:
                logger.error("Neo4j connection test failed: unexpected result")
                return False
                
    except Exception as e:
        logger.error("Neo4j connection test failed", error=str(e))
        return False


# Cleanup on module unload
def cleanup():
    """Cleanup Neo4j connections"""
    global neo4j_driver
    if neo4j_driver:
        neo4j_driver.close()
        neo4j_driver = None
        logger.info("Neo4j driver cleaned up")


# Export public API
__all__ = [
    "neo4j_driver",
    "neo4j_service",
    "Neo4jService",
    "get_neo4j_driver",
    "test_neo4j_connection",
    "cleanup"
]

