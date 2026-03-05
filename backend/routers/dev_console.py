"""
Dev Console Router - Developer Query Console for ClickHouse and Neo4j

Elastic DevTools benzeri sorgu arayüzü için API endpoints.
Desteklenen veritabanları:
- ClickHouse (SQL): network_flows, dns_queries, tcp_connections, sni_events, etc.
- Neo4j (Cypher): Workload, Namespace, COMMUNICATES_WITH relationships

Architecture:
- Uses microservices for query execution (Enterprise pattern)
- timeseries-query service: ClickHouse SQL queries
- graph-query service: Neo4j Cypher queries

Security Features:
- Read-only queries only (no INSERT, UPDATE, DELETE, DROP, etc.)
- Query result size limits
- Query timeout enforcement
- Large value truncation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
import time
import re
import httpx
import structlog

from config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/dev-console", tags=["Dev Console"])

# Microservice URLs from config
TIMESERIES_QUERY_URL = settings.TIMESERIES_QUERY_URL  # http://timeseries-query:8002
GRAPH_QUERY_URL = settings.GRAPH_QUERY_URL  # http://graph-query:8001

# HTTP client timeout
HTTP_TIMEOUT = 60.0


# ============ Security Constants ============
#
# Philosophy: Allow maximum read access, block only actual write operations.
# Smart validation that doesn't block legitimate queries with keywords in
# table/column names (e.g., "oom_kills", "update_time", "delete_flag").
#
# ============================================================================

# Maximum size for a single cell value (in characters)
MAX_CELL_VALUE_LENGTH = 10000

# Maximum total response size (approximate, in characters)
MAX_RESPONSE_SIZE = 5_000_000  # 5MB

# ClickHouse: Allowed read-only command prefixes
CLICKHOUSE_ALLOWED_PREFIXES = (
    'SELECT', 'WITH', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN', 'EXISTS'
)

# Neo4j/Cypher: Allowed read-only command prefixes
CYPHER_ALLOWED_PREFIXES = (
    'MATCH', 'OPTIONAL MATCH', 'RETURN', 'WITH', 'UNWIND', 'CALL', 'USE', 'PROFILE', 'EXPLAIN'
)

# Neo4j: Safe CALL procedure prefixes (read-only introspection)
CYPHER_SAFE_CALL_PREFIXES = (
    'CALL DB.',              # db.labels(), db.relationshipTypes(), db.schema.*
    'CALL DBMS.',            # dbms.components(), dbms.listConfig(), etc.
    'CALL APOC.META.',       # apoc.meta.data(), apoc.meta.schema()
    'CALL APOC.HELP',        # apoc.help()
    'CALL APOC.VERSION',     # apoc.version()
    'CALL GDS.',             # Graph Data Science read procedures
)

# Neo4j: Dangerous write commands (statement-level)
CYPHER_WRITE_COMMANDS = (
    'CREATE', 'MERGE', 'DELETE', 'DETACH DELETE', 'SET', 'REMOVE', 'FOREACH'
)

# ============ Security Functions ============

def validate_query_safety(query: str, database: str) -> tuple[bool, str]:
    """
    Smart validation that checks query structure, not keywords in identifiers.
    
    Security Model:
    - Query must START with an allowed read-only command
    - For Cypher: CALL must use safe procedure prefixes
    - Multiple statements are blocked
    - No keyword scanning within query body (avoids false positives)
    
    Returns:
        Tuple of (is_safe, error_message)
    """
    # Remove comments first
    cleaned_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)  # SQL single-line
    cleaned_query = re.sub(r'//.*$', '', cleaned_query, flags=re.MULTILINE)  # Cypher single-line
    cleaned_query = re.sub(r'/\*.*?\*/', '', cleaned_query, flags=re.DOTALL)  # Block comments
    
    query_stripped = cleaned_query.strip()
    query_upper = query_stripped.upper()
    
    if not query_stripped:
        return False, "Empty query"
    
    if database == "clickhouse":
        # ClickHouse: Query must start with read-only prefix
        if not query_upper.startswith(CLICKHOUSE_ALLOWED_PREFIXES):
            return False, "Only read-only queries allowed (SELECT, WITH, SHOW, DESCRIBE, EXPLAIN)"
    
    elif database == "neo4j":
        # Neo4j: Check for allowed prefixes
        starts_with_allowed = any(
            query_upper.startswith(prefix) for prefix in CYPHER_ALLOWED_PREFIXES
        )
        
        if not starts_with_allowed:
            # Check if it's a write command
            if any(query_upper.startswith(cmd) for cmd in CYPHER_WRITE_COMMANDS):
                return False, "Write operations not allowed (CREATE, MERGE, DELETE, SET, REMOVE)"
            return False, "Query must start with MATCH, RETURN, CALL, or WITH"
        
        # Special handling for CALL - must be safe procedure
        if query_upper.startswith('CALL'):
            is_safe_call = any(
                query_upper.startswith(prefix) for prefix in CYPHER_SAFE_CALL_PREFIXES
            )
            if not is_safe_call:
                # Extract procedure name for better error message
                proc_match = re.match(r'CALL\s+(\S+)', query_upper)
                proc_name = proc_match.group(1) if proc_match else 'unknown'
                return False, f"Procedure '{proc_name}' not allowed. Safe: db.*, dbms.*, apoc.meta.*"
    
    # Check for multiple statements (SQL injection protection)
    statements = [s.strip() for s in cleaned_query.split(';') if s.strip()]
    if len(statements) > 1:
        return False, "Multiple statements not allowed"
    
    return True, ""


def sanitize_value(value: Any) -> Any:
    """
    Sanitize a single value for safe transmission.
    Truncates large strings and handles special types.
    """
    if value is None:
        return None
    
    if isinstance(value, str):
        # Truncate very long strings
        if len(value) > MAX_CELL_VALUE_LENGTH:
            return value[:MAX_CELL_VALUE_LENGTH] + f"... [truncated, total {len(value)} chars]"
        return value
    
    if isinstance(value, bytes):
        # Convert bytes to hex representation (truncated if needed)
        hex_str = value.hex()
        if len(hex_str) > MAX_CELL_VALUE_LENGTH:
            return hex_str[:MAX_CELL_VALUE_LENGTH] + f"... [truncated binary, total {len(value)} bytes]"
        return f"0x{hex_str}"
    
    if isinstance(value, (datetime,)):
        return value.isoformat()
    
    if isinstance(value, dict):
        # Recursively sanitize dict values
        sanitized = {k: sanitize_value(v) for k, v in value.items()}
        result = str(sanitized)
        if len(result) > MAX_CELL_VALUE_LENGTH:
            return result[:MAX_CELL_VALUE_LENGTH] + "... [truncated]"
        return sanitized
    
    if isinstance(value, (list, tuple)):
        # Recursively sanitize list values
        sanitized = [sanitize_value(v) for v in value]
        result = str(sanitized)
        if len(result) > MAX_CELL_VALUE_LENGTH:
            return result[:MAX_CELL_VALUE_LENGTH] + "... [truncated]"
        return sanitized
    
    # For numbers, booleans, etc., return as-is
    return value


def sanitize_row(row: List[Any]) -> List[Any]:
    """Sanitize all values in a row."""
    return [sanitize_value(v) for v in row]


def estimate_response_size(columns: List[str], rows: List[List[Any]]) -> int:
    """Estimate the size of the response in characters."""
    size = sum(len(str(col)) for col in columns)
    for row in rows:
        size += sum(len(str(v)) for v in row)
    return size


# ============ Pydantic Models ============

class QueryRequest(BaseModel):
    """Query execution request"""
    database: Literal["clickhouse", "neo4j"] = Field(..., description="Target database")
    query: str = Field(..., min_length=1, max_length=50000, description="SQL or Cypher query")
    analysis_ids: Optional[List[str]] = Field(None, description="Analysis IDs for filtering")
    limit: int = Field(default=1000, ge=1, le=10000, description="Max rows to return")
    timeout: int = Field(default=30, ge=1, le=60, description="Query timeout in seconds")
    
    @field_validator('query')
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace"""
        if not v or not v.strip():
            raise ValueError('Query cannot be empty or whitespace only')
        return v.strip()


class QueryError(BaseModel):
    """Query error details"""
    code: str
    message: str
    line: Optional[int] = None
    position: Optional[int] = None


class QueryResponse(BaseModel):
    """Query execution response"""
    success: bool
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: int = 0
    execution_time_ms: int = 0
    truncated: bool = False
    error: Optional[QueryError] = None


class ColumnSchema(BaseModel):
    """Column schema definition"""
    name: str
    type: str
    description: Optional[str] = None


class TableSchema(BaseModel):
    """Table schema definition"""
    name: str
    columns: List[ColumnSchema]


class SchemaResponse(BaseModel):
    """Database schema response"""
    database: str
    tables: List[TableSchema]


# ============ ClickHouse Schema ============

CLICKHOUSE_SCHEMA = [
    TableSchema(
        name="network_flows",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="source_namespace", type="String", description="Source namespace"),
            ColumnSchema(name="source_pod", type="String", description="Source pod name"),
            ColumnSchema(name="source_container", type="String", description="Source container name"),
            ColumnSchema(name="source_node", type="String", description="Source node name"),
            ColumnSchema(name="source_ip", type="String", description="Source IP address"),
            ColumnSchema(name="source_port", type="UInt16", description="Source port"),
            ColumnSchema(name="dest_namespace", type="String", description="Destination namespace"),
            ColumnSchema(name="dest_pod", type="String", description="Destination pod name"),
            ColumnSchema(name="dest_container", type="String", description="Destination container name"),
            ColumnSchema(name="dest_ip", type="String", description="Destination IP"),
            ColumnSchema(name="dest_port", type="UInt16", description="Destination port"),
            ColumnSchema(name="dest_hostname", type="String", description="Destination hostname (if resolved)"),
            ColumnSchema(name="protocol", type="String", description="Protocol (TCP/UDP/ICMP/HTTP/GRPC)"),
            ColumnSchema(name="direction", type="String", description="Direction (inbound/outbound/internal)"),
            ColumnSchema(name="connection_state", type="String", description="TCP state (ESTABLISHED, SYN_SENT, etc.)"),
            ColumnSchema(name="bytes_sent", type="UInt64", description="Bytes sent"),
            ColumnSchema(name="bytes_received", type="UInt64", description="Bytes received"),
            ColumnSchema(name="packets_sent", type="UInt32", description="Packets sent"),
            ColumnSchema(name="packets_received", type="UInt32", description="Packets received"),
            ColumnSchema(name="duration_ms", type="UInt32", description="Connection duration in ms"),
            ColumnSchema(name="latency_ms", type="Float32", description="Latency in ms"),
            ColumnSchema(name="error_count", type="UInt16", description="Error count"),
            ColumnSchema(name="retransmit_count", type="UInt16", description="Retransmit count"),
            ColumnSchema(name="error_type", type="String", description="Error type"),
        ]
    ),
    TableSchema(
        name="dns_queries",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="source_namespace", type="String", description="Source namespace"),
            ColumnSchema(name="source_pod", type="String", description="Source pod name"),
            ColumnSchema(name="source_container", type="String", description="Source container name"),
            ColumnSchema(name="source_ip", type="String", description="Source IP address"),
            ColumnSchema(name="query_name", type="String", description="DNS query domain"),
            ColumnSchema(name="query_type", type="String", description="DNS query type (A, AAAA, CNAME, MX, TXT)"),
            ColumnSchema(name="query_class", type="String", description="DNS query class"),
            ColumnSchema(name="response_code", type="String", description="DNS response code (NOERROR, NXDOMAIN, etc.)"),
            ColumnSchema(name="response_ips", type="Array(String)", description="Resolved IP addresses"),
            ColumnSchema(name="response_cnames", type="Array(String)", description="CNAME chain"),
            ColumnSchema(name="response_ttl", type="UInt32", description="Response TTL"),
            ColumnSchema(name="latency_ms", type="Float32", description="Response latency in ms"),
            ColumnSchema(name="dns_server_ip", type="String", description="DNS server IP"),
            ColumnSchema(name="dns_server_port", type="UInt16", description="DNS server port"),
        ]
    ),
    TableSchema(
        name="sni_events",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="sni_name", type="String", description="SNI hostname (Server Name Indication)"),
            ColumnSchema(name="src_ip", type="String", description="Source IP"),
            ColumnSchema(name="src_port", type="UInt16", description="Source port"),
            ColumnSchema(name="dst_ip", type="String", description="Destination IP"),
            ColumnSchema(name="dst_port", type="UInt16", description="Destination port"),
            ColumnSchema(name="tls_version", type="String", description="TLS version (TLS1.2, TLS1.3)"),
            ColumnSchema(name="cipher_suite", type="String", description="Cipher suite"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
        ]
    ),
    TableSchema(
        name="tcp_lifecycle",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="source_ip", type="String", description="Source IP"),
            ColumnSchema(name="source_port", type="UInt16", description="Source port"),
            ColumnSchema(name="dest_ip", type="String", description="Destination IP"),
            ColumnSchema(name="dest_port", type="UInt16", description="Destination port"),
            ColumnSchema(name="old_state", type="String", description="Previous TCP state"),
            ColumnSchema(name="new_state", type="String", description="New TCP state"),
            ColumnSchema(name="source_namespace", type="String", description="Source namespace"),
            ColumnSchema(name="source_pod", type="String", description="Source pod name"),
            ColumnSchema(name="source_container", type="String", description="Source container name"),
        ]
    ),
    TableSchema(
        name="process_events",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="node", type="String", description="Node name"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="ppid", type="UInt32", description="Parent process ID"),
            ColumnSchema(name="uid", type="UInt32", description="User ID"),
            ColumnSchema(name="gid", type="UInt32", description="Group ID"),
            ColumnSchema(name="comm", type="String", description="Command name"),
            ColumnSchema(name="exe", type="String", description="Executable path"),
            ColumnSchema(name="args", type="Array(String)", description="Command arguments"),
            ColumnSchema(name="cwd", type="String", description="Working directory"),
            ColumnSchema(name="event_type", type="String", description="Event type (exec, exit, signal)"),
            ColumnSchema(name="exit_code", type="Int32", description="Exit code"),
            ColumnSchema(name="signal", type="Int32", description="Signal number"),
        ]
    ),
    TableSchema(
        name="file_operations",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="operation", type="String", description="Operation (open, read, write, close, unlink, rename)"),
            ColumnSchema(name="file_path", type="String", description="File path"),
            ColumnSchema(name="file_flags", type="String", description="File flags (O_RDONLY, O_WRONLY, etc.)"),
            ColumnSchema(name="file_mode", type="UInt32", description="File mode"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
            ColumnSchema(name="uid", type="UInt32", description="User ID"),
            ColumnSchema(name="gid", type="UInt32", description="Group ID"),
            ColumnSchema(name="bytes", type="UInt64", description="Bytes read/written"),
            ColumnSchema(name="duration_us", type="UInt32", description="Operation duration (microseconds)"),
            ColumnSchema(name="error_code", type="Int32", description="Error code (0 = success)"),
        ]
    ),
    TableSchema(
        name="capability_checks",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="capability", type="String", description="Linux capability (CAP_NET_ADMIN, etc.)"),
            ColumnSchema(name="syscall", type="String", description="Syscall that triggered check"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
            ColumnSchema(name="uid", type="UInt32", description="User ID"),
            ColumnSchema(name="gid", type="UInt32", description="Group ID"),
            ColumnSchema(name="verdict", type="String", description="Result (allowed/denied)"),
        ]
    ),
    TableSchema(
        name="oom_kills",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="node", type="String", description="Node name"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
            ColumnSchema(name="memory_limit", type="UInt64", description="Memory limit (bytes)"),
            ColumnSchema(name="memory_usage", type="UInt64", description="Memory usage at kill (bytes)"),
            ColumnSchema(name="memory_pages_total", type="UInt64", description="Total memory pages"),
            ColumnSchema(name="memory_pages_free", type="UInt64", description="Free memory pages"),
            ColumnSchema(name="cgroup_path", type="String", description="Cgroup path"),
        ]
    ),
    TableSchema(
        name="bind_events",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="node", type="String", description="Node name"),
            ColumnSchema(name="bind_addr", type="String", description="Bind address"),
            ColumnSchema(name="bind_port", type="UInt16", description="Bind port"),
            ColumnSchema(name="protocol", type="String", description="Protocol (TCP/UDP)"),
            ColumnSchema(name="interface", type="String", description="Network interface"),
            ColumnSchema(name="error_code", type="Int32", description="Error code (0 = success)"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
            ColumnSchema(name="uid", type="UInt32", description="User ID"),
        ]
    ),
    TableSchema(
        name="mount_events",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="event_id", type="String", description="Unique event ID"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="pod", type="String", description="Pod name"),
            ColumnSchema(name="container", type="String", description="Container name"),
            ColumnSchema(name="node", type="String", description="Node name"),
            ColumnSchema(name="operation", type="String", description="Operation (mount/umount)"),
            ColumnSchema(name="source", type="String", description="Source path/device"),
            ColumnSchema(name="target", type="String", description="Mount point"),
            ColumnSchema(name="fs_type", type="String", description="Filesystem type"),
            ColumnSchema(name="flags", type="String", description="Mount flags"),
            ColumnSchema(name="options", type="String", description="Mount options"),
            ColumnSchema(name="error_code", type="Int32", description="Error code (0 = success)"),
            ColumnSchema(name="pid", type="UInt32", description="Process ID"),
            ColumnSchema(name="comm", type="String", description="Process command"),
        ]
    ),
    TableSchema(
        name="workload_metadata",
        columns=[
            ColumnSchema(name="timestamp", type="DateTime64(3)", description="Event timestamp"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster identifier"),
            ColumnSchema(name="cluster_name", type="String", description="Cluster name"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis identifier"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="workload_name", type="String", description="Workload name (Deployment/StatefulSet/DaemonSet)"),
            ColumnSchema(name="workload_type", type="String", description="Workload type"),
            ColumnSchema(name="pod_name", type="String", description="Pod name"),
            ColumnSchema(name="pod_uid", type="String", description="Pod UID"),
            ColumnSchema(name="container_name", type="String", description="Container name"),
            ColumnSchema(name="container_id", type="String", description="Container ID"),
            ColumnSchema(name="node_name", type="String", description="Node name"),
            ColumnSchema(name="pod_ip", type="String", description="Pod IP address"),
            ColumnSchema(name="owner_kind", type="String", description="Owner kind (ReplicaSet, etc.)"),
            ColumnSchema(name="owner_name", type="String", description="Owner name"),
            ColumnSchema(name="first_seen", type="DateTime64(3)", description="First seen timestamp"),
            ColumnSchema(name="last_seen", type="DateTime64(3)", description="Last seen timestamp"),
            ColumnSchema(name="event_count", type="UInt32", description="Event count"),
        ]
    ),
]


# ============ Neo4j Schema ============

NEO4J_SCHEMA = [
    TableSchema(
        name="Cluster (Node)",
        columns=[
            ColumnSchema(name="id", type="String", description="Unique cluster ID"),
            ColumnSchema(name="name", type="String", description="Cluster name"),
            ColumnSchema(name="cluster_type", type="String", description="Type (kubernetes/openshift)"),
            ColumnSchema(name="api_url", type="String", description="Cluster API URL"),
            ColumnSchema(name="k8s_version", type="String", description="Kubernetes version"),
            ColumnSchema(name="node_count", type="Integer", description="Number of nodes"),
            ColumnSchema(name="is_active", type="Boolean", description="Active flag"),
        ]
    ),
    TableSchema(
        name="Namespace (Node)",
        columns=[
            ColumnSchema(name="name", type="String", description="Namespace name"),
            ColumnSchema(name="cluster", type="String", description="Parent cluster ID"),
            ColumnSchema(name="uid", type="String", description="Kubernetes UID"),
            ColumnSchema(name="status", type="String", description="Status (Active/Terminating)"),
        ]
    ),
    TableSchema(
        name="Workload (Node)",
        columns=[
            ColumnSchema(name="id", type="String", description="Unique workload ID"),
            ColumnSchema(name="name", type="String", description="Workload name"),
            ColumnSchema(name="namespace", type="String", description="Kubernetes namespace"),
            ColumnSchema(name="kind", type="String", description="Kind (Pod/Deployment/StatefulSet/Service)"),
            ColumnSchema(name="cluster", type="String", description="Cluster name"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster ID (indexed)"),
            ColumnSchema(name="analysis_id", type="String", description="Analysis ID (indexed)"),
            ColumnSchema(name="ip_address", type="String", description="IP address"),
            ColumnSchema(name="status", type="String", description="Current status"),
            ColumnSchema(name="phase", type="String", description="Pod phase"),
            ColumnSchema(name="node_name", type="String", description="Node name (for Pods)"),
            ColumnSchema(name="replicas", type="Integer", description="Replica count"),
            ColumnSchema(name="is_active", type="Boolean", description="Active flag"),
            ColumnSchema(name="first_seen", type="DateTime", description="First seen timestamp"),
            ColumnSchema(name="last_seen", type="DateTime", description="Last seen timestamp"),
        ]
    ),
    TableSchema(
        name="Pod (Node)",
        columns=[
            ColumnSchema(name="id", type="String", description="Unique pod ID"),
            ColumnSchema(name="name", type="String", description="Pod name"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster ID"),
            ColumnSchema(name="ip_address", type="String", description="Pod IP"),
            ColumnSchema(name="node_name", type="String", description="Node name"),
            ColumnSchema(name="status", type="String", description="Status"),
            ColumnSchema(name="phase", type="String", description="Phase (Running/Pending/Failed)"),
        ]
    ),
    TableSchema(
        name="Deployment (Node)",
        columns=[
            ColumnSchema(name="id", type="String", description="Unique deployment ID"),
            ColumnSchema(name="name", type="String", description="Deployment name"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster ID"),
            ColumnSchema(name="replicas", type="Integer", description="Desired replicas"),
            ColumnSchema(name="available_replicas", type="Integer", description="Available replicas"),
        ]
    ),
    TableSchema(
        name="Service (Node)",
        columns=[
            ColumnSchema(name="id", type="String", description="Unique service ID"),
            ColumnSchema(name="name", type="String", description="Service name"),
            ColumnSchema(name="namespace", type="String", description="Namespace"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster ID"),
            ColumnSchema(name="service_type", type="String", description="Type (ClusterIP/NodePort/LoadBalancer)"),
            ColumnSchema(name="cluster_ip", type="String", description="Cluster IP"),
        ]
    ),
    TableSchema(
        name="ExternalEndpoint (Node)",
        columns=[
            ColumnSchema(name="ip_address", type="String", description="IP address (unique)"),
            ColumnSchema(name="hostname", type="String", description="Hostname/domain"),
            ColumnSchema(name="port", type="Integer", description="Port number"),
            ColumnSchema(name="endpoint_type", type="String", description="Type (internet/cloud_service)"),
            ColumnSchema(name="is_public", type="Boolean", description="Public internet flag"),
        ]
    ),
    TableSchema(
        name="COMMUNICATES_WITH (Relationship)",
        columns=[
            ColumnSchema(name="analysis_id", type="String", description="Analysis ID for filtering"),
            ColumnSchema(name="cluster_id", type="String", description="Cluster ID"),
            ColumnSchema(name="destination_port", type="Integer", description="Destination port"),
            ColumnSchema(name="protocol", type="String", description="Protocol (TCP/UDP/HTTP/gRPC)"),
            ColumnSchema(name="direction", type="String", description="Direction (inbound/outbound)"),
            ColumnSchema(name="request_count", type="Integer", description="Total request count"),
            ColumnSchema(name="bytes_transferred", type="Integer", description="Total bytes"),
            ColumnSchema(name="avg_latency_ms", type="Float", description="Average latency (ms)"),
            ColumnSchema(name="error_count", type="Integer", description="Error count"),
            ColumnSchema(name="risk_score", type="Integer", description="Risk score (0-100)"),
            ColumnSchema(name="risk_level", type="String", description="Risk level"),
            ColumnSchema(name="is_cross_namespace", type="Boolean", description="Cross-namespace flag"),
            ColumnSchema(name="is_external", type="Boolean", description="External comm flag"),
            ColumnSchema(name="is_active", type="Boolean", description="Active flag"),
            ColumnSchema(name="first_seen", type="DateTime", description="First seen"),
            ColumnSchema(name="last_seen", type="DateTime", description="Last seen"),
        ]
    ),
    TableSchema(
        name="PART_OF (Relationship)",
        columns=[
            ColumnSchema(name="relation_type", type="String", description="Type (pod_to_deployment, etc.)"),
        ]
    ),
    TableSchema(
        name="EXPOSES (Relationship)",
        columns=[
            ColumnSchema(name="service_name", type="String", description="Service name"),
            ColumnSchema(name="service_type", type="String", description="Service type"),
            ColumnSchema(name="ports", type="String", description="Exposed ports (JSON)"),
        ]
    ),
    TableSchema(
        name="DEPENDS_ON (Relationship)",
        columns=[
            ColumnSchema(name="dependency_type", type="String", description="Type (application/infrastructure)"),
            ColumnSchema(name="strength", type="String", description="Strength (weak/moderate/strong/critical)"),
            ColumnSchema(name="confidence", type="Float", description="Confidence score (0.0-1.0)"),
            ColumnSchema(name="is_active", type="Boolean", description="Active flag"),
        ]
    ),
]


# ============ Query Execution Functions ============

async def execute_clickhouse_query(query: str, limit: int, timeout: int) -> QueryResponse:
    """
    Execute ClickHouse SQL query via timeseries-query microservice
    
    Enterprise architecture: API Gateway delegates to specialized microservice.
    This ensures:
    - Consistent data access patterns
    - Single point of database configuration
    - Better scalability and maintainability
    
    Features:
    - Read-only query validation (defense in depth)
    - Automatic LIMIT enforcement
    - Result sanitization
    - Error handling
    """
    start_time = time.time()
    
    try:
        # Security check: validate query is read-only (defense in depth)
        is_safe, error_message = validate_query_safety(query, "clickhouse")
        if not is_safe:
            return QueryResponse(
                success=False,
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=0,
                truncated=False,
                error=QueryError(
                    code="SECURITY_ERROR",
                    message=error_message
                )
            )
        
        # Call timeseries-query microservice
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{TIMESERIES_QUERY_URL}/dev-console/query",
                json={
                    "query": query,
                    "limit": limit,
                    "timeout": timeout
                }
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                logger.error("Timeseries query service error",
                           status=response.status_code,
                           response=response.text[:500])
                return QueryResponse(
                    success=False,
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                    truncated=False,
                    error=QueryError(
                        code="SERVICE_ERROR",
                        message=f"Timeseries service error: {response.status_code}"
                    )
                )
            
            result = response.json()
            
            if result.get("success"):
                columns = result.get("columns", [])
                rows = result.get("rows", [])
                
                # Sanitize values (defense in depth)
                sanitized_rows = [sanitize_row(row) for row in rows]
                
                # Check response size at gateway level
                response_size = estimate_response_size(columns, sanitized_rows)
                truncated = result.get("truncated", False)
                
                if response_size > MAX_RESPONSE_SIZE:
                    while sanitized_rows and estimate_response_size(columns, sanitized_rows) > MAX_RESPONSE_SIZE:
                        sanitized_rows = sanitized_rows[:len(sanitized_rows) // 2]
                    truncated = True
                    logger.warning("Response truncated at API Gateway",
                                  original_rows=len(rows),
                                  returned_rows=len(sanitized_rows))
                
                return QueryResponse(
                    success=True,
                    columns=columns,
                    rows=sanitized_rows,
                    row_count=len(sanitized_rows),
                    execution_time_ms=result.get("execution_time_ms", execution_time_ms),
                    truncated=truncated
                )
            else:
                error_info = result.get("error", {})
                return QueryResponse(
                    success=False,
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=result.get("execution_time_ms", execution_time_ms),
                    truncated=False,
                    error=QueryError(
                        code=error_info.get("code", "QUERY_ERROR"),
                        message=error_info.get("message", "Unknown error")[:500]
                    )
                )
                
    except httpx.ConnectError as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error("Cannot connect to timeseries-query service", error=str(e))
        return QueryResponse(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            execution_time_ms=execution_time_ms,
            truncated=False,
            error=QueryError(
                code="CONNECTION_ERROR",
                message="Cannot connect to ClickHouse query service. Please try again later."
            )
        )
    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        
        # Sanitize error message
        if "password" in error_msg.lower() or "secret" in error_msg.lower():
            error_msg = "Database error. Please contact administrator."
        
        logger.error("ClickHouse query failed", error=error_msg, query=query[:200])
        
        return QueryResponse(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            execution_time_ms=execution_time_ms,
            truncated=False,
            error=QueryError(
                code="CLICKHOUSE_ERROR",
                message=error_msg[:500]
            )
        )


async def execute_neo4j_query(query: str, limit: int, timeout: int) -> QueryResponse:
    """
    Execute Neo4j Cypher query via graph-query microservice
    
    Enterprise architecture: API Gateway delegates to specialized microservice
    """
    start_time = time.time()
    
    try:
        # Security check: validate query is read-only (defense in depth)
        is_safe, error_message = validate_query_safety(query, "neo4j")
        if not is_safe:
            return QueryResponse(
                success=False,
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=0,
                truncated=False,
                error=QueryError(
                    code="SECURITY_ERROR",
                    message=error_message
                )
            )
        
        # Add LIMIT if not present
        query_upper = query.upper().strip()
        if "LIMIT" not in query_upper:
            query = f"{query.rstrip().rstrip(';')} LIMIT {limit}"
        
        # Call graph-query microservice
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{GRAPH_QUERY_URL}/query",
                json={"query": query}
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                logger.error("Graph query service error",
                           status=response.status_code,
                           response=response.text[:500])
                return QueryResponse(
                    success=False,
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                    truncated=False,
                    error=QueryError(
                        code="SERVICE_ERROR",
                        message=f"Graph service error: {response.status_code}"
                    )
                )
            
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", [])
                
                if not data:
                    return QueryResponse(
                        success=True,
                        columns=[],
                        rows=[],
                        row_count=0,
                        execution_time_ms=execution_time_ms,
                        truncated=False
                    )
                
                # Extract columns from first record
                columns = list(data[0].keys()) if data else []
                
                # Convert dict records to rows
                rows = []
                for record in data[:limit]:
                    row = []
                    for col in columns:
                        value = record.get(col)
                        # Handle Neo4j objects
                        if isinstance(value, dict):
                            value = str(value)
                        row.append(sanitize_value(value))
                    rows.append(row)
                
                # Check response size
                response_size = estimate_response_size(columns, rows)
                truncated = len(data) > limit
                
                if response_size > MAX_RESPONSE_SIZE:
                    while rows and estimate_response_size(columns, rows) > MAX_RESPONSE_SIZE:
                        rows = rows[:len(rows) // 2]
                    truncated = True
                    logger.warning("Response truncated at API Gateway",
                                  original_rows=len(data),
                                  returned_rows=len(rows))
                
                return QueryResponse(
                    success=True,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=execution_time_ms,
                    truncated=truncated
                )
            else:
                return QueryResponse(
                    success=False,
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                    truncated=False,
                    error=QueryError(
                        code=result.get("code", "QUERY_ERROR"),
                        message=result.get("error", "Unknown error")[:500]
                    )
                )
                
    except httpx.ConnectError as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error("Cannot connect to graph-query service", error=str(e))
        return QueryResponse(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            execution_time_ms=execution_time_ms,
            truncated=False,
            error=QueryError(
                code="CONNECTION_ERROR",
                message="Cannot connect to Neo4j query service. Please try again later."
            )
        )
    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        
        # Sanitize error message
        if "password" in error_msg.lower() or "secret" in error_msg.lower() or "auth" in error_msg.lower():
            error_msg = "Service error. Please contact administrator."
        
        logger.error("Neo4j query failed", error=error_msg, query=query[:200])
        
        return QueryResponse(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            execution_time_ms=execution_time_ms,
            truncated=False,
            error=QueryError(
                code="NEO4J_ERROR",
                message=error_msg[:500]
            )
        )


# ============ API Endpoints ============

@router.post("/query", response_model=QueryResponse)
async def execute_query(request: QueryRequest):
    """
    Execute a query against ClickHouse or Neo4j
    
    - **database**: Target database ('clickhouse' or 'neo4j')
    - **query**: SQL query for ClickHouse, Cypher query for Neo4j
    - **analysis_ids**: Optional analysis IDs filter (list)
    - **limit**: Maximum rows to return (default: 1000, max: 10000)
    - **timeout**: Query timeout in seconds (default: 30, max: 60)
    """
    logger.info(
        "Dev Console query",
        database=request.database,
        query_length=len(request.query),
        analysis_ids=request.analysis_ids
    )
    
    if request.database == "clickhouse":
        return await execute_clickhouse_query(
            query=request.query,
            limit=request.limit,
            timeout=request.timeout
        )
    elif request.database == "neo4j":
        return await execute_neo4j_query(
            query=request.query,
            limit=request.limit,
            timeout=request.timeout
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported database: {request.database}"
        )


@router.get("/schema/{database}", response_model=SchemaResponse)
async def get_schema(database: Literal["clickhouse", "neo4j"]):
    """
    Get database schema information
    
    - **database**: Target database ('clickhouse' or 'neo4j')
    
    Returns table/node definitions with column names and types.
    Fetches live schema from microservices when available,
    falls back to static definitions if service unavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if database == "clickhouse":
                try:
                    response = await client.get(f"{TIMESERIES_QUERY_URL}/dev-console/schema")
                    if response.status_code == 200:
                        schema_data = response.json()
                        # Convert microservice response to our model
                        tables = []
                        for table in schema_data.get("tables", []):
                            columns = [
                                ColumnSchema(
                                    name=col["name"],
                                    type=col["type"],
                                    description=col.get("description")
                                )
                                for col in table.get("columns", [])
                            ]
                            tables.append(TableSchema(name=table["name"], columns=columns))
                        return SchemaResponse(database="clickhouse", tables=tables)
                except Exception as e:
                    logger.warning(f"Failed to get live ClickHouse schema, using static: {e}")
                
                # Fallback to static schema
                return SchemaResponse(database="clickhouse", tables=CLICKHOUSE_SCHEMA)
                
            elif database == "neo4j":
                try:
                    response = await client.get(f"{GRAPH_QUERY_URL}/dev-console/schema")
                    if response.status_code == 200:
                        schema_data = response.json()
                        tables = []
                        for table in schema_data.get("tables", []):
                            columns = [
                                ColumnSchema(
                                    name=col["name"],
                                    type=col["type"],
                                    description=col.get("description")
                                )
                                for col in table.get("columns", [])
                            ]
                            tables.append(TableSchema(name=table["name"], columns=columns))
                        return SchemaResponse(database="neo4j", tables=tables)
                except Exception as e:
                    logger.warning(f"Failed to get live Neo4j schema, using static: {e}")
                
                # Fallback to static schema
                return SchemaResponse(database="neo4j", tables=NEO4J_SCHEMA)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported database: {database}"
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Schema fetch error: {e}")
        # Final fallback to static schemas
        if database == "clickhouse":
            return SchemaResponse(database="clickhouse", tables=CLICKHOUSE_SCHEMA)
        else:
            return SchemaResponse(database="neo4j", tables=NEO4J_SCHEMA)


@router.get("/health")
async def health():
    """
    Dev Console health check
    
    Checks connectivity to underlying microservices:
    - timeseries-query for ClickHouse
    - graph-query for Neo4j
    """
    clickhouse_status = "unavailable"
    neo4j_status = "unavailable"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check timeseries-query service
            try:
                ch_response = await client.get(f"{TIMESERIES_QUERY_URL}/health")
                if ch_response.status_code == 200:
                    ch_health = ch_response.json()
                    clickhouse_status = "healthy" if ch_health.get("status") == "healthy" else "degraded"
            except Exception as e:
                logger.warning("Timeseries query service health check failed", error=str(e))
                clickhouse_status = "unavailable"
            
            # Check graph-query service
            try:
                neo_response = await client.get(f"{GRAPH_QUERY_URL}/health")
                if neo_response.status_code == 200:
                    neo4j_status = "healthy"
            except Exception as e:
                logger.warning("Graph query service health check failed", error=str(e))
                neo4j_status = "unavailable"
    except Exception as e:
        logger.error("Health check failed", error=str(e))
    
    overall_status = "healthy" if clickhouse_status == "healthy" and neo4j_status == "healthy" else "degraded"
    
    return {
        "status": overall_status,
        "databases": {
            "clickhouse": clickhouse_status,
            "neo4j": neo4j_status
        },
        "services": {
            "timeseries_query": TIMESERIES_QUERY_URL,
            "graph_query": GRAPH_QUERY_URL
        }
    }

