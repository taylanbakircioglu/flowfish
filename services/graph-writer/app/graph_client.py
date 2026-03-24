"""
Neo4j Graph Database Client for Graph Writer Service
Replaces NebulaGraph with Neo4j for production stability
"""

import logging
import re
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from app.config import settings

logger = logging.getLogger(__name__)


class GraphClient:
    """Neo4j graph database client for dependency graph operations"""
    
    def __init__(self):
        self.driver: Optional[GraphDatabase.driver] = None
        self.database = "neo4j"  # Default database for Neo4j Community Edition
        
        try:
            self._connect()
        except Exception as e:
            logger.warning(f"⚠️  Graph database connection failed (will retry later): {e}")
    
    def _connect(self):
        """Connect to Neo4j graph database"""
        try:
            # Parse connection details
            uri = settings.neo4j_bolt_uri
            user = settings.neo4j_user
            password = settings.neo4j_password
            
            # Create Neo4j driver
            self.driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_timeout=30,
                encrypted=False  # Internal cluster communication
            )
            
            # Verify connectivity
            self.driver.verify_connectivity()
            
            logger.info(f"✅ Connected to Neo4j graph database: {uri}")
            
            # Ensure schema exists
            self._ensure_schema()
            
        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}")
            raise
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def _ensure_schema(self):
        """Ensure graph schema (constraints and indexes) exists"""
        try:
            with self.driver.session(database=self.database) as session:
                # Create constraints (unique identifiers)
                constraints = [
                    "CREATE CONSTRAINT workload_id IF NOT EXISTS FOR (w:Workload) REQUIRE w.id IS UNIQUE",
                    "CREATE CONSTRAINT namespace_name IF NOT EXISTS FOR (n:Namespace) REQUIRE (n.name, n.cluster) IS UNIQUE",
                    "CREATE CONSTRAINT cluster_id IF NOT EXISTS FOR (c:Cluster) REQUIRE c.id IS UNIQUE"
                ]
                
                for constraint in constraints:
                    try:
                        session.run(constraint)
                    except Exception as e:
                        # Constraint may already exist
                        logger.debug(f"Constraint creation skipped: {e}")
                
                # Create indexes for performance
                indexes = [
                    "CREATE INDEX workload_name IF NOT EXISTS FOR (w:Workload) ON (w.name)",
                    "CREATE INDEX workload_namespace IF NOT EXISTS FOR (w:Workload) ON (w.namespace)",
                    "CREATE INDEX workload_kind IF NOT EXISTS FOR (w:Workload) ON (w.kind)",
                    "CREATE INDEX workload_cluster IF NOT EXISTS FOR (w:Workload) ON (w.cluster)",
                    "CREATE INDEX namespace_cluster IF NOT EXISTS FOR (n:Namespace) ON (n.cluster)"
                ]
                
                for index in indexes:
                    try:
                        session.run(index)
                    except Exception as e:
                        # Index may already exist
                        logger.debug(f"Index creation skipped: {e}")
                
                logger.info("✅ Neo4j graph database schema ensured")
                
        except Exception as e:
            logger.error(f"Failed to ensure schema: {e}")
            raise
    
    def execute_query(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a Cypher query
        
        Args:
            query: Cypher query string
            parameters: Query parameters (prevents injection)
        
        Returns:
            Response dictionary with success status and results
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters or {})
                
                # Consume results
                records = [dict(record) for record in result]
                summary = result.consume()
                
                return {
                    "success": True,
                    "records": records,
                    "counters": {
                        "nodes_created": summary.counters.nodes_created,
                        "nodes_deleted": summary.counters.nodes_deleted,
                        "relationships_created": summary.counters.relationships_created,
                        "relationships_deleted": summary.counters.relationships_deleted,
                        "properties_set": summary.counters.properties_set
                    },
                    "latency_ms": summary.result_available_after + summary.result_consumed_after
                }
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "error_msg": str(e),
                "records": []
            }
    
    def _sanitize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize property values for Neo4j - ensure all values are primitives.
        Neo4j only accepts: bool, int, float, str, bytes, or arrays of these.
        Nested dicts/lists are converted to JSON strings.
        """
        sanitized = {}
        for key, value in properties.items():
            if value is None:
                sanitized[key] = ""
            elif isinstance(value, (bool, int, float, str, bytes)):
                sanitized[key] = value
            elif isinstance(value, (dict, list)):
                # Convert complex types to JSON string
                import json
                sanitized[key] = json.dumps(value, default=str)
            else:
                # Convert unknown types to string
                sanitized[key] = str(value)
        return sanitized
    
    def upsert_vertex(
        self,
        vid: str,
        labels: List[str],
        properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Upsert a vertex (node)
        
        Args:
            vid: Vertex ID (unique identifier)
            labels: Node labels (e.g., ['Workload', 'Pod'])
            properties: Node properties
        
        Returns:
            Response dictionary
        """
        # Sanitize properties to ensure Neo4j compatibility
        safe_props = self._sanitize_properties(properties)
        
        # Build label string
        label_str = ":".join(labels)
        
        # Build SET clause
        set_clauses = [f"n.{key} = ${key}" for key in safe_props.keys()]
        set_clause = ", ".join(set_clauses)
        
        query = f"""
        MERGE (n:{label_str} {{id: $vid}})
        SET {set_clause}, n.updated_at = timestamp()
        RETURN n
        """
        
        params = {"vid": vid, **safe_props}
        
        return self.execute_query(query, params)
    
    def _parse_vertex_id(self, vid: str) -> tuple:
        """
        Parse vertex ID to extract analysis_id, cluster_id, namespace, name, and ip.
        
        VID Format v2.0 (Full Isolation):
        {analysis_id}:{cluster_id}:{namespace}:{workload_name}
        
        Legacy format (backward compatibility):
        {cluster_id}:{namespace}:{workload_name}
        
        Returns: (cluster_id, namespace, name, ip)
        Note: analysis_id is already embedded in the VID for MERGE operations
        """
        parts = vid.split(':')
        
        if len(parts) >= 4:
            # New format: analysis_id:cluster_id:namespace:workload
            # Workload may contain ':' (e.g., for bind addresses like "0.0.0.0:8080")
            analysis_id, cluster_id, namespace = parts[0], parts[1], parts[2]
            name = ':'.join(parts[3:])  # Join remaining parts for workload name
        elif len(parts) == 3:
            # Legacy format: cluster_id:namespace:workload
            cluster_id, namespace, name = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            cluster_id, namespace, name = '', parts[0], parts[1]
        else:
            cluster_id, namespace, name = '', 'unknown', vid
        
        # If name looks like an IP address, use it as ip
        ip = name if re.match(r'^\d+\.\d+\.\d+\.\d+$', name) else ''
        
        return cluster_id, namespace, name, ip
    
    def upsert_edge(
        self,
        src_vid: str,
        dst_vid: str,
        edge_type: str,
        properties: Dict[str, Any],
        # Labels (JSON strings)
        src_labels: str = '{}',
        dst_labels: str = '{}',
        # Annotations (JSON strings)
        src_annotations: str = '{}',
        dst_annotations: str = '{}',
        # Owner info
        src_owner_kind: str = '',
        src_owner_name: str = '',
        dst_owner_kind: str = '',
        dst_owner_name: str = '',
        # Extended metadata - source
        src_pod_uid: str = '',
        src_ip: str = '',  # Pod IP address
        src_host_ip: str = '',  # Node/Host IP
        src_container: str = '',
        src_image: str = '',
        src_service_account: str = '',
        src_phase: str = '',
        # Extended metadata - destination
        dst_pod_uid: str = '',
        dst_ip: str = '',  # Pod IP address
        dst_host_ip: str = '',  # Node/Host IP
        dst_container: str = '',
        dst_image: str = '',
        dst_service_account: str = '',
        dst_phase: str = ''
    ) -> Dict[str, Any]:
        """
        Upsert an edge (relationship)
        
        Creates nodes if they don't exist using MERGE (not MATCH)
        
        Args:
            src_vid: Source vertex ID
            dst_vid: Destination vertex ID
            edge_type: Relationship type (e.g., 'COMMUNICATES_WITH')
            properties: Relationship properties
            src_labels/dst_labels: Node labels as JSON strings
            src_owner_kind/dst_owner_kind: Owner type (Deployment, StatefulSet, etc.)
            src_owner_name/dst_owner_name: Owner name
            Extended metadata: pod_uid, host_ip, container, image, service_account, phase
        
        Returns:
            Response dictionary
        """
        # Sanitize properties to ensure Neo4j compatibility
        safe_props = self._sanitize_properties(properties)
        
        # Build SET clause
        set_clauses = [f"r.{key} = ${key}" for key in safe_props.keys()]
        set_clause = ", ".join(set_clauses)
        
        # Parse vertex IDs to extract name, namespace (IP comes from parameter now)
        src_cluster, src_ns, src_name, _ = self._parse_vertex_id(src_vid)
        dst_cluster, dst_ns, dst_name, _ = self._parse_vertex_id(dst_vid)
        
        # Use MERGE for nodes to ensure they exist before creating relationship
        # Always SET name/namespace/ip/owner/metadata (use coalesce to preserve existing values if better)
        # ON CREATE: set initial values including IP and host_ip from enrichment
        # ON MATCH: update missing (NULL or empty) values only, including IP
        # For labels: prefer new value if not empty, otherwise keep existing
        # Extract analysis_id from properties for node tracking
        analysis_id = safe_props.get('analysis_id', '')
        
        # NOTE: Use :Workload label in MERGE to match the constraint
        # This ensures consistent node creation/matching with the unique constraint
        # IP and host_ip are set from enrichment data (not parsed from vertex ID)
        query = f"""
        MERGE (src:Workload {{id: $src_vid}})
        ON CREATE SET src.created_at = timestamp(), src.kind = 'Pod', src.status = 'active',
                      src.name = $src_name, src.namespace = $src_ns, src.cluster_id = $src_cluster,
                      src.ip = $src_ip, src.host_ip = $src_host_ip, 
                      src.labels = $src_labels, src.annotations = $src_annotations,
                      src.analysis_id = $analysis_id
        ON MATCH SET src.analysis_id = coalesce(src.analysis_id, $analysis_id),
                     src.cluster_id = coalesce(src.cluster_id, $src_cluster),
                     src.ip = CASE WHEN $src_ip <> '' THEN $src_ip ELSE coalesce(src.ip, '') END,
                     src.host_ip = CASE WHEN $src_host_ip <> '' THEN $src_host_ip ELSE coalesce(src.host_ip, '') END,
                     src.labels = CASE WHEN $src_labels <> '{{}}' THEN $src_labels ELSE coalesce(src.labels, '{{}}') END,
                     src.annotations = CASE WHEN $src_annotations <> '{{}}' THEN $src_annotations ELSE coalesce(src.annotations, '{{}}') END
        WITH src
        MERGE (dst:Workload {{id: $dst_vid}})
        ON CREATE SET dst.created_at = timestamp(), dst.kind = 'Pod', dst.status = 'active',
                      dst.name = $dst_name, dst.namespace = $dst_ns, dst.cluster_id = $dst_cluster,
                      dst.ip = $dst_ip, dst.host_ip = $dst_host_ip,
                      dst.labels = $dst_labels, dst.annotations = $dst_annotations,
                      dst.analysis_id = $analysis_id
        ON MATCH SET dst.analysis_id = coalesce(dst.analysis_id, $analysis_id),
                     dst.cluster_id = coalesce(dst.cluster_id, $dst_cluster),
                     dst.ip = CASE WHEN $dst_ip <> '' THEN $dst_ip ELSE coalesce(dst.ip, '') END,
                     dst.host_ip = CASE WHEN $dst_host_ip <> '' THEN $dst_host_ip ELSE coalesce(dst.host_ip, '') END,
                     dst.labels = CASE WHEN $dst_labels <> '{{}}' THEN $dst_labels ELSE coalesce(dst.labels, '{{}}') END,
                     dst.annotations = CASE WHEN $dst_annotations <> '{{}}' THEN $dst_annotations ELSE coalesce(dst.annotations, '{{}}') END
        WITH src, dst
        MERGE (src)-[r:{edge_type}]->(dst)
        SET {set_clause}, 
            r.analysis_id = coalesce(r.analysis_id, $analysis_id),
            r.cluster_id = coalesce(r.cluster_id, $src_cluster),
            r.last_seen = timestamp(),
            r.first_seen = coalesce(r.first_seen, timestamp())
        RETURN r
        """
        
        params = {
            "src_vid": src_vid, 
            "dst_vid": dst_vid,
            "src_name": src_name,
            "src_ns": src_ns,
            "src_cluster": src_cluster,
            "src_ip": src_ip or '',  # Pod IP from enrichment
            "src_host_ip": src_host_ip or '',  # Node/Host IP from enrichment
            "src_labels": src_labels or '{}',
            "src_annotations": src_annotations or '{}',
            "src_owner_kind": src_owner_kind or '',
            "src_owner_name": src_owner_name or '',
            "src_pod_uid": src_pod_uid or '',
            "src_container": src_container or '',
            "src_image": src_image or '',
            "src_service_account": src_service_account or '',
            "src_phase": src_phase or '',
            "dst_name": dst_name,
            "dst_ns": dst_ns,
            "dst_cluster": dst_cluster,
            "dst_ip": dst_ip or '',  # Pod IP from enrichment
            "dst_host_ip": dst_host_ip or '',  # Node/Host IP from enrichment
            "dst_labels": dst_labels or '{}',
            "dst_annotations": dst_annotations or '{}',
            "dst_owner_kind": dst_owner_kind or '',
            "dst_owner_name": dst_owner_name or '',
            "dst_pod_uid": dst_pod_uid or '',
            "dst_container": dst_container or '',
            "dst_image": dst_image or '',
            "dst_service_account": dst_service_account or '',
            "dst_phase": dst_phase or '',
            "analysis_id": analysis_id,  # For node tracking and deletion
            **safe_props
        }
        
        return self.execute_query(query, params)
    
    def batch_upsert_vertices(self, vertices: List[Dict[str, Any]]) -> int:
        """
        Batch upsert vertices using UNWIND for optimal performance
        
        Args:
            vertices: List of vertex dictionaries with 'vid', 'labels', 'properties'
        
        Returns:
            Number of successful upserts
        """
        if not vertices:
            return 0
        
        success_count = 0
        
        # Process in larger batches using UNWIND for better performance
        batch_size = 500
        for i in range(0, len(vertices), batch_size):
            batch = vertices[i:i + batch_size]
            
            # Prepare batch data
            batch_data = []
            for vertex in batch:
                props = self._sanitize_properties(vertex.get('properties', {}))
                batch_data.append({
                    'vid': vertex['vid'],
                    'props': props
                })
            
            # Use UNWIND for batch insert
            query = """
            UNWIND $batch AS item
            MERGE (n:Workload {id: item.vid})
            SET n += item.props, n.updated_at = timestamp()
            RETURN count(n) as count
            """
            
            result = self.execute_query(query, {'batch': batch_data})
            if result.get('success'):
                records = result.get('records', [])
                if records:
                    success_count += records[0].get('count', 0)
        
        logger.info(f"Batch upserted {success_count}/{len(vertices)} vertices")
        return success_count
    
    def batch_upsert_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Batch upsert edges using UNWIND for optimal performance
        
        Args:
            edges: List of edge dictionaries with 'src_vid', 'dst_vid', 'edge_type', 'properties'
        
        Returns:
            Number of successful upserts
        """
        if not edges:
            return 0
        
        success_count = 0
        relationships_created = 0
        errors = []
        
        # Process in larger batches using UNWIND
        batch_size = 500
        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            
            # Prepare batch data with all properties
            batch_data = []
            for edge in batch:
                props = self._sanitize_properties(edge.get('properties', {}))
                src_cluster, src_ns, src_name, _ = self._parse_vertex_id(edge['src_vid'])
                dst_cluster, dst_ns, dst_name, _ = self._parse_vertex_id(edge['dst_vid'])
                
                batch_data.append({
                    'src_vid': edge['src_vid'],
                    'dst_vid': edge['dst_vid'],
                    'src_name': src_name,
                    'src_ns': src_ns,
                    'src_cluster': src_cluster,
                    'dst_name': dst_name,
                    'dst_ns': dst_ns,
                    'dst_cluster': dst_cluster,
                    'src_ip': edge.get('src_ip', ''),
                    'dst_ip': edge.get('dst_ip', ''),
                    'src_labels': edge.get('src_labels', '{}'),
                    'dst_labels': edge.get('dst_labels', '{}'),
                    'src_annotations': edge.get('src_annotations', '{}'),
                    'dst_annotations': edge.get('dst_annotations', '{}'),
                    'props': props
                })
            
            # Use UNWIND for batch edge insert - single query for all edges
            query = """
            UNWIND $batch AS item
            MERGE (src:Workload {id: item.src_vid})
            ON CREATE SET src.name = item.src_name, src.namespace = item.src_ns, 
                          src.cluster_id = item.src_cluster, src.ip = item.src_ip,
                          src.labels = item.src_labels, src.annotations = item.src_annotations,
                          src.kind = 'Pod', src.status = 'active', src.created_at = timestamp()
            ON MATCH SET src.labels = CASE WHEN item.src_labels <> '{}' THEN item.src_labels ELSE coalesce(src.labels, '{}') END,
                         src.annotations = CASE WHEN item.src_annotations <> '{}' THEN item.src_annotations ELSE coalesce(src.annotations, '{}') END
            WITH src, item
            MERGE (dst:Workload {id: item.dst_vid})
            ON CREATE SET dst.name = item.dst_name, dst.namespace = item.dst_ns,
                          dst.cluster_id = item.dst_cluster, dst.ip = item.dst_ip,
                          dst.labels = item.dst_labels, dst.annotations = item.dst_annotations,
                          dst.kind = 'Pod', dst.status = 'active', dst.created_at = timestamp()
            ON MATCH SET dst.labels = CASE WHEN item.dst_labels <> '{}' THEN item.dst_labels ELSE coalesce(dst.labels, '{}') END,
                         dst.annotations = CASE WHEN item.dst_annotations <> '{}' THEN item.dst_annotations ELSE coalesce(dst.annotations, '{}') END
            WITH src, dst, item
            MERGE (src)-[r:COMMUNICATES_WITH]->(dst)
            SET r += item.props,
                r.last_seen = timestamp(),
                r.first_seen = coalesce(r.first_seen, timestamp())
            RETURN count(r) as count
            """
            
            try:
                result = self.execute_query(query, {'batch': batch_data})
                if result.get('success'):
                    records = result.get('records', [])
                    if records:
                        batch_count = records[0].get('count', 0)
                        success_count += batch_count
                        relationships_created += result.get('counters', {}).get('relationships_created', 0)
                else:
                    errors.append(result.get('error_msg', 'Unknown error'))
            except Exception as e:
                errors.append(str(e))
                logger.error(f"Batch edge upsert failed: {e}")
        
        # Log detailed stats
        if errors:
            logger.warning(f"Edge upsert had {len(errors)} errors: {errors[:3]}")
        
        logger.info(f"Batch upserted {success_count}/{len(edges)} edges "
                   f"(created: {relationships_created})")
        return success_count
    
    def insert_workload(
        self,
        workload_id: str,
        name: str,
        namespace: str,
        kind: str,
        cluster_id: str,
        **additional_props
    ) -> Dict[str, Any]:
        """
        Insert or update workload node with relationships
        
        Args:
            workload_id: Unique workload ID
            name: Workload name
            namespace: Kubernetes namespace
            kind: Workload kind (Pod, Deployment, etc.)
            cluster_id: Parent cluster ID
            **additional_props: Additional properties (ip, status, etc.)
        
        Returns:
            Response dictionary
        """
        query = """
        MERGE (w:Workload {id: $workload_id})
        SET w.name = $name,
            w.namespace = $namespace,
            w.kind = $kind,
            w.cluster = $cluster_id,
            w += $additional_props,
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
            "additional_props": additional_props
        }
        
        return self.execute_query(query, params)
    
    def insert_communication(
        self,
        source_id: str,
        dest_id: str,
        port: int,
        protocol: str,
        **additional_props
    ) -> Dict[str, Any]:
        """
        Insert or update communication edge
        
        Args:
            source_id: Source workload ID
            dest_id: Destination workload ID
            port: Destination port
            protocol: Protocol (TCP, UDP, HTTP, etc.)
            **additional_props: Additional properties (request_count, bytes_transferred, etc.)
        
        Returns:
            Response dictionary
        """
        query = """
        MATCH (src:Workload {id: $source_id})
        MATCH (dst:Workload {id: $dest_id})
        
        MERGE (src)-[c:COMMUNICATES_WITH {port: $port, protocol: $protocol}]->(dst)
        
        SET c += $additional_props,
            c.request_count = coalesce(c.request_count, 0) + coalesce($request_count, 1),
            c.bytes_transferred = coalesce(c.bytes_transferred, 0) + coalesce($bytes, 0),
            c.error_count = coalesce(c.error_count, 0) + coalesce($error_count, 0),
            c.retransmit_count = coalesce(c.retransmit_count, 0) + coalesce($retransmit_count, 0),
            c.last_error_type = CASE WHEN $error_type <> '' THEN $error_type ELSE c.last_error_type END,
            c.last_seen = timestamp(),
            c.first_seen = coalesce(c.first_seen, timestamp())
        
        RETURN c
        """
        
        params = {
            "source_id": source_id,
            "dest_id": dest_id,
            "port": port,
            "protocol": protocol,
            "request_count": additional_props.get("request_count", 1),
            "bytes": additional_props.get("bytes_transferred", 0),
            "error_count": additional_props.get("error_count", 0),
            "retransmit_count": additional_props.get("retransmit_count", 0),
            "error_type": additional_props.get("error_type") or additional_props.get("last_error_type") or "",
            "additional_props": {
                k: v for k, v in additional_props.items() 
                if k not in ["request_count", "bytes_transferred", "error_count", "retransmit_count", "error_type", "last_error_type"]
            }
        }
        
        return self.execute_query(query, params)
    
    def close(self):
        """Close Neo4j driver connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j driver closed")


# Global graph database client instance
graph_client = GraphClient()


# Export
__all__ = ["graph_client", "GraphClient"]
