/* ============================================================================
   Flowfish - Neo4j Schema Definition
   ============================================================================
   Version: 1.0.0 (Migrated from NebulaGraph)
   Date: November 2024
   Description: Graph database schema for workload dependencies and communications
   ============================================================================ */

// Neo4j Community Edition uses default "neo4j" database
// Schema is defined through constraints and indexes

/* ============================================================================
   CONSTRAINTS (Unique Identifiers)
   ============================================================================ */

// Cluster constraints
CREATE CONSTRAINT cluster_id IF NOT EXISTS
FOR (c:Cluster) REQUIRE c.id IS UNIQUE;

// Namespace constraints (composite uniqueness: name + cluster)
CREATE CONSTRAINT namespace_name_cluster IF NOT EXISTS
FOR (n:Namespace) REQUIRE (n.name, n.cluster) IS UNIQUE;

// Workload constraints (unified node type)
CREATE CONSTRAINT workload_id IF NOT EXISTS
FOR (w:Workload) REQUIRE w.id IS UNIQUE;

// Pod constraints (for specific pod queries)
CREATE CONSTRAINT pod_id IF NOT EXISTS
FOR (p:Pod) REQUIRE p.id IS UNIQUE;

// Deployment constraints
CREATE CONSTRAINT deployment_id IF NOT EXISTS
FOR (d:Deployment) REQUIRE d.id IS UNIQUE;

// StatefulSet constraints
CREATE CONSTRAINT statefulset_id IF NOT EXISTS
FOR (s:StatefulSet) REQUIRE s.id IS UNIQUE;

// Service constraints
CREATE CONSTRAINT service_id IF NOT EXISTS
FOR (svc:Service) REQUIRE svc.id IS UNIQUE;

// External endpoint constraints
CREATE CONSTRAINT external_endpoint_ip IF NOT EXISTS
FOR (e:ExternalEndpoint) REQUIRE e.ip_address IS UNIQUE;

/* ============================================================================
   INDEXES (Performance Optimization)
   ============================================================================ */

// Cluster indexes
CREATE INDEX cluster_name IF NOT EXISTS FOR (c:Cluster) ON (c.name);
CREATE INDEX cluster_type IF NOT EXISTS FOR (c:Cluster) ON (c.cluster_type);

// Namespace indexes
CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name);
CREATE INDEX namespace_cluster IF NOT EXISTS FOR (n:Namespace) ON (n.cluster);

// Workload indexes (most queried)
CREATE INDEX workload_name IF NOT EXISTS FOR (w:Workload) ON (w.name);
CREATE INDEX workload_namespace IF NOT EXISTS FOR (w:Workload) ON (w.namespace);
CREATE INDEX workload_kind IF NOT EXISTS FOR (w:Workload) ON (w.kind);
CREATE INDEX workload_cluster IF NOT EXISTS FOR (w:Workload) ON (w.cluster);
CREATE INDEX workload_cluster_id IF NOT EXISTS FOR (w:Workload) ON (w.cluster_id);
CREATE INDEX workload_analysis_id IF NOT EXISTS FOR (w:Workload) ON (w.analysis_id);
CREATE INDEX workload_ip IF NOT EXISTS FOR (w:Workload) ON (w.ip_address);
CREATE INDEX workload_status IF NOT EXISTS FOR (w:Workload) ON (w.status);
CREATE INDEX workload_active IF NOT EXISTS FOR (w:Workload) ON (w.is_active);

// Pod indexes
CREATE INDEX pod_name IF NOT EXISTS FOR (p:Pod) ON (p.name);
CREATE INDEX pod_namespace IF NOT EXISTS FOR (p:Pod) ON (p.namespace);
CREATE INDEX pod_cluster IF NOT EXISTS FOR (p:Pod) ON (p.cluster_id);
CREATE INDEX pod_ip IF NOT EXISTS FOR (p:Pod) ON (p.ip_address);
CREATE INDEX pod_status IF NOT EXISTS FOR (p:Pod) ON (p.status);
CREATE INDEX pod_node IF NOT EXISTS FOR (p:Pod) ON (p.node_name);

// Deployment indexes
CREATE INDEX deployment_name IF NOT EXISTS FOR (d:Deployment) ON (d.name);
CREATE INDEX deployment_namespace IF NOT EXISTS FOR (d:Deployment) ON (d.namespace);
CREATE INDEX deployment_cluster IF NOT EXISTS FOR (d:Deployment) ON (d.cluster_id);

// StatefulSet indexes
CREATE INDEX statefulset_name IF NOT EXISTS FOR (s:StatefulSet) ON (s.name);
CREATE INDEX statefulset_namespace IF NOT EXISTS FOR (s:StatefulSet) ON (s.namespace);
CREATE INDEX statefulset_cluster IF NOT EXISTS FOR (s:StatefulSet) ON (s.cluster_id);

// Service indexes
CREATE INDEX service_name IF NOT EXISTS FOR (svc:Service) ON (svc.name);
CREATE INDEX service_namespace IF NOT EXISTS FOR (svc:Service) ON (svc.namespace);
CREATE INDEX service_cluster IF NOT EXISTS FOR (svc:Service) ON (svc.cluster_id);
CREATE INDEX service_type IF NOT EXISTS FOR (svc:Service) ON (svc.service_type);

// External endpoint indexes
CREATE INDEX external_endpoint_hostname IF NOT EXISTS FOR (e:ExternalEndpoint) ON (e.hostname);

/* ============================================================================
   NODE TYPES (Labels) AND PROPERTIES
   ============================================================================ */

/*
Node Label: Cluster
Represents a Kubernetes/OpenShift cluster

Properties:
  - id: STRING (UNIQUE) - Cluster identifier
  - name: STRING - Cluster name
  - cluster_type: STRING - 'kubernetes' or 'openshift'
  - api_url: STRING - Cluster API URL
  - k8s_version: STRING - Kubernetes version
  - node_count: INT - Number of nodes
  - is_active: BOOLEAN - Active status
  - created_at: DATETIME - Creation timestamp
  - updated_at: DATETIME - Last update timestamp
  - metadata: STRING - JSON metadata
*/

/*
Node Label: Namespace
Represents a Kubernetes namespace

Properties:
  - name: STRING - Namespace name
  - cluster: STRING - Parent cluster ID
  - uid: STRING - Kubernetes UID
  - status: STRING - Status (Active, Terminating)
  - labels: STRING - JSON labels
  - annotations: STRING - JSON annotations
  - created_at: DATETIME - Creation timestamp
  - updated_at: DATETIME - Last update timestamp
*/

/*
Node Label: Workload
Unified workload type (Pod, Deployment, StatefulSet, Service, etc.)

Properties:
  - id: STRING (UNIQUE) - Workload identifier
  - name: STRING - Workload name
  - namespace: STRING - Kubernetes namespace
  - kind: STRING - Workload kind (Pod, Deployment, StatefulSet, Service)
  - cluster: STRING - Parent cluster name
  - cluster_id: STRING - Parent cluster ID (indexed for filtering)
  - analysis_id: STRING - Analysis ID (indexed for scope filtering)
  - ip_address: STRING - IP address (for Pods/Services)
  - status: STRING - Current status
  - phase: STRING - Pod phase (Running, Pending, Failed)
  - node_name: STRING - Node name (for Pods)
  - replicas: INT - Replica count (for Deployments/StatefulSets)
  - available_replicas: INT - Available replicas
  - service_type: STRING - Service type (ClusterIP, NodePort, LoadBalancer)
  - labels: STRING - JSON labels
  - annotations: STRING - JSON annotations
  - owner_kind: STRING - Owner kind
  - owner_name: STRING - Owner name
  - owner_uid: STRING - Owner UID
  - first_seen: DATETIME - First seen timestamp
  - last_seen: DATETIME - Last seen timestamp
  - is_active: BOOLEAN - Active status
  - metadata: STRING - JSON additional metadata
*/

/*
Node Label: Pod
Represents a Kubernetes pod (can also use Workload label)

Properties: (Same as Workload, Pod-specific)
  - id, name, namespace, cluster_id, uid, ip_address, node_name
  - status, phase, containers (JSON), owner_kind, owner_name
  - labels, annotations, first_seen, last_seen, is_active, metadata
*/

/*
Node Label: Deployment
Represents a Kubernetes deployment

Properties:
  - id, name, namespace, cluster_id, uid
  - replicas, available_replicas, ready_replicas
  - strategy (RollingUpdate, Recreate)
  - labels, annotations, selector (JSON)
  - conditions (JSON), first_seen, last_seen, is_active, metadata
*/

/*
Node Label: StatefulSet
Represents a Kubernetes statefulset

Properties:
  - id, name, namespace, cluster_id, uid
  - replicas, ready_replicas, current_replicas
  - service_name, update_strategy
  - labels, annotations, selector (JSON)
  - volume_claims (JSON), first_seen, last_seen, is_active, metadata
*/

/*
Node Label: Service
Represents a Kubernetes service

Properties:
  - id, name, namespace, cluster_id, uid
  - service_type (ClusterIP, NodePort, LoadBalancer)
  - cluster_ip, external_ips (JSON), ports (JSON)
  - selector (JSON), labels, annotations
  - first_seen, last_seen, is_active, metadata
*/

/*
Node Label: ExternalEndpoint
Represents an external IP/domain (not in cluster)

Properties:
  - ip_address: STRING (UNIQUE) - IP address
  - hostname: STRING - Hostname/domain
  - port: INT - Port number
  - endpoint_type: STRING - 'internet', 'internal_network', 'cloud_service'
  - geolocation: STRING - Country, city if known
  - is_public: BOOLEAN - Public internet or private
  - first_seen: DATETIME - First seen timestamp
  - last_seen: DATETIME - Last seen timestamp
  - metadata: STRING - JSON metadata
*/

/* ============================================================================
   RELATIONSHIP TYPES AND PROPERTIES
   ============================================================================ */

/*
Relationship: PART_OF
Represents hierarchical containment

Properties:
  - relation_type: STRING - Type of relationship
    ('pod_to_deployment', 'namespace_to_cluster', 'workload_to_namespace')
  - created_at: DATETIME - Creation timestamp
*/

/*
Relationship: EXPOSES
Represents service exposure (service -> deployment/statefulset)

Properties:
  - service_name: STRING - Service name
  - service_type: STRING - Service type
  - ports: STRING - JSON array of exposed ports
  - created_at: DATETIME - Creation timestamp
  - updated_at: DATETIME - Last update timestamp
*/

/*
Relationship: COMMUNICATES_WITH
Represents network communication between workloads

Properties:
  Analysis context:
  - analysis_id: STRING - Analysis ID for scope filtering
  - cluster_id: STRING - Cluster ID
  
  Communication details:
  - source_ip: STRING - Source IP
  - source_port: INT - Source port
  - destination_ip: STRING - Destination IP
  - destination_port: INT - Destination port
  - protocol: STRING - TCP, UDP, HTTP, HTTPS, gRPC
  - direction: STRING - 'inbound', 'outbound', 'bidirectional'
  
  Temporal data:
  - first_seen: DATETIME - First communication timestamp
  - last_seen: DATETIME - Last communication timestamp
  
  Traffic metrics:
  - request_count: INT - Total request count
  - request_rate_per_second: FLOAT - Requests per second
  - bytes_transferred: INT - Total bytes
  - bytes_in: INT - Inbound bytes
  - bytes_out: INT - Outbound bytes
  
  Latency metrics:
  - avg_latency_ms: FLOAT - Average latency
  - p50_latency_ms: FLOAT - P50 latency
  - p95_latency_ms: FLOAT - P95 latency
  - p99_latency_ms: FLOAT - P99 latency
  - max_latency_ms: FLOAT - Maximum latency
  
  Error metrics:
  - error_count: INT - Total errors
  - error_rate: FLOAT - Error rate
  
  Risk scoring:
  - risk_score: INT - Risk score (0-100)
  - risk_level: STRING - 'low', 'medium', 'high', 'critical'
  - risk_factors: STRING - JSON array of factors
  
  Importance scoring:
  - importance_score: INT - Importance score (0-100)
  - importance_level: STRING - 'low', 'medium', 'high', 'critical'
  
  Classification:
  - is_cross_namespace: BOOLEAN - Cross-namespace communication
  - is_external: BOOLEAN - External communication
  - is_encrypted: BOOLEAN - Encrypted connection
  
  Status:
  - is_active: BOOLEAN - Currently active
  - last_updated: DATETIME - Last update timestamp
  
  Metadata:
  - http_methods: STRING - JSON array (if HTTP/HTTPS)
  - http_status_codes: STRING - JSON object with counts
  - dns_names: STRING - JSON array (if DNS involved)
  - metadata: STRING - JSON additional metadata
*/

/*
Relationship: DEPENDS_ON
Represents logical application dependency

Properties:
  - dependency_type: STRING - 'application', 'infrastructure', 'data'
  - strength: STRING - 'weak', 'moderate', 'strong', 'critical'
  - confidence: FLOAT - Confidence score (0.0-1.0)
  - evidence: STRING - JSON evidence data
  - first_detected: DATETIME - First detection timestamp
  - last_verified: DATETIME - Last verification timestamp
  - is_active: BOOLEAN - Currently active
*/

/*
Relationship: RUNS_ON
Represents pod to node placement

Properties:
  - node_name: STRING - Node name
  - scheduled_at: DATETIME - Scheduling timestamp
  - is_active: BOOLEAN - Currently running
*/

/*
Relationship: RESOLVES_TO
Represents DNS resolution (service/hostname -> IP)

Properties:
  - query_name: STRING - DNS query name
  - record_type: STRING - 'A', 'AAAA', 'CNAME', 'SRV'
  - ttl: INT - DNS TTL
  - first_seen: DATETIME - First seen timestamp
  - last_seen: DATETIME - Last seen timestamp
  - query_count: INT - Total queries
*/

/* ============================================================================
   SAMPLE CYPHER QUERIES (Documentation)
   ============================================================================ */

// Query 1: Get all communications from a specific workload
// MATCH (src:Workload {name: 'web-app-123'})-[comm:COMMUNICATES_WITH]->(dst)
// RETURN src.name, dst.name, comm.protocol, comm.destination_port, 
//        comm.request_count, comm.risk_level;

// Query 2: Find all dependencies of a deployment (1-3 hops)
// MATCH path = (dep:Deployment {name: 'api-service'})-[*1..3]->(target)
// RETURN dep.name, nodes(path), relationships(path);

// Query 3: Get cross-namespace communications (potential security risk)
// MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
// WHERE src.namespace <> dst.namespace 
//   AND comm.is_active = true
// RETURN src.namespace, src.name, dst.namespace, dst.name, 
//        comm.protocol, comm.risk_score
// ORDER BY comm.risk_score DESC;

// Query 4: Find all external communications
// MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(ext:ExternalEndpoint)
// WHERE comm.is_active = true
// RETURN src.name, src.namespace, ext.ip_address, ext.hostname, 
//        comm.destination_port, comm.protocol;

// Query 5: Get service exposure map
// MATCH (svc:Service)-[:EXPOSES]->(dep:Deployment)
// MATCH (dep)<-[:PART_OF]-(pod:Pod)
// RETURN svc.name, dep.name, COLLECT(pod.name) AS pods;

// Query 6: Find high-risk communications
// MATCH (src)-[comm:COMMUNICATES_WITH]->(dst)
// WHERE comm.risk_level IN ['high', 'critical'] 
//   AND comm.is_active = true
// RETURN src, comm, dst
// ORDER BY comm.risk_score DESC
// LIMIT 50;

// Query 7: Get application tier topology (frontend -> backend -> database)
// MATCH path = (frontend:Pod)-[*1..5]->(database:Pod)
// WHERE frontend.tier = 'frontend' AND database.tier = 'database'
// RETURN path;

// Query 8: Find workloads with most outbound connections
// MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst)
// WHERE comm.is_active = true
// RETURN src.name, src.namespace, COUNT(dst) AS connection_count
// ORDER BY connection_count DESC
// LIMIT 20;

// Query 9: Get namespace isolation violations
// MATCH (src:Workload)-[comm:COMMUNICATES_WITH]->(dst:Workload)
// WHERE src.namespace <> dst.namespace
//   AND comm.is_active = true
//   AND NOT src.namespace IN ['kube-system', 'kube-public']
// RETURN src.namespace, dst.namespace, COUNT(*) AS violation_count
// ORDER BY violation_count DESC;

// Query 10: Find circular dependencies
// MATCH path = (a:Deployment)-[*2..5]->(a)
// RETURN path;

// Query 11: Get upstream dependencies of a service
// MATCH (target:Service {name: 'database-service'})<-[*1..3]-(upstream)
// RETURN DISTINCT upstream;

// Query 12: Get downstream dependencies of a service
// MATCH (source:Service {name: 'api-gateway'})-[*1..3]->(downstream)
// RETURN DISTINCT downstream;

// Query 13: Find services with no inbound traffic
// MATCH (svc:Service)
// WHERE NOT (svc)<-[:COMMUNICATES_WITH]-()
// RETURN svc.name, svc.namespace;

// Query 14: Get all communications in a time window
// MATCH (src)-[comm:COMMUNICATES_WITH]->(dst)
// WHERE comm.last_seen > datetime('2024-01-15T10:00:00')
//   AND comm.last_seen < datetime('2024-01-15T11:00:00')
// RETURN src, comm, dst;

// Query 15: Calculate service importance by dependent count
// MATCH (svc:Service)<-[*1..2]-(dependents)
// RETURN svc.name, svc.namespace, COUNT(DISTINCT dependents) AS dependent_count
// ORDER BY dependent_count DESC;

/* ============================================================================
   DATA LIFECYCLE MANAGEMENT
   ============================================================================ */

// Neo4j does not have native TTL like NebulaGraph
// Use application-level logic or periodic jobs for cleanup:

// Example: Delete inactive communications older than 90 days
// MATCH (src)-[comm:COMMUNICATES_WITH]->(dst)
// WHERE comm.is_active = false
//   AND comm.last_seen < datetime() - duration({days: 90})
// DELETE comm;

// Example: Mark old workloads as inactive
// MATCH (w:Workload)
// WHERE w.last_seen < datetime() - duration({days: 30})
// SET w.is_active = false;

/* ============================================================================
   PERFORMANCE OPTIMIZATION NOTES
   ============================================================================ */

// 1. Use indexes on frequently queried properties
// 2. Limit traversal depth with [*1..N] to avoid expensive deep queries
// 3. Use LIMIT clause to restrict result sets
// 4. Filter early in the query (WHERE clause)
// 5. Use PROFILE/EXPLAIN to analyze query performance
// 6. Batch operations using UNWIND for better performance
// 7. Use query parameters to enable query plan caching
// 8. Consider using APOC procedures for complex operations

/* ============================================================================
   BACKUP AND RESTORE
   ============================================================================ */

// Neo4j backup:
// - Use neo4j-admin backup (Enterprise Edition)
// - Use APOC export procedures (Community Edition)
// - File system snapshots of data directory

// Restore:
// - Use neo4j-admin restore
// - Use APOC import procedures
// - Copy backup files to data directory (service stopped)

/* ============================================================================
   SECURITY CONSIDERATIONS
   ============================================================================ */

// 1. Use authentication (username/password or LDAP/AD)
// 2. Enable SSL/TLS for Bolt connections
// 3. Implement role-based access control (RBAC)
// 4. Encrypt sensitive data in properties
// 5. Regular security audits
// 6. Monitor for unusual query patterns
// 7. Implement rate limiting at application level

/* ============================================================================
   SCHEMA VERSIONING
   ============================================================================ */

// Schema version: 1.0.0 (Neo4j migration)
// Migrated from: NebulaGraph schema v1.0.0
// Date: November 2024
// Last modified: November 2024

// Migration notes:
// - Converted from nGQL to Cypher
// - Unified some node types into Workload label
// - Adapted constraints to Neo4j syntax
// - Updated indexes for Neo4j performance
// - Maintained property compatibility

/* ============================================================================
   VERIFICATION QUERIES
   ============================================================================ */

// After schema creation, verify with:
// SHOW CONSTRAINTS;
// SHOW INDEXES;
// CALL db.schema.visualization();
// CALL db.schema.nodeTypeProperties();
// CALL db.schema.relTypeProperties();

/* ============================================================================
   END OF SCHEMA
   ============================================================================ */

