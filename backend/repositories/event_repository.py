"""
Event Repository - Data Access Layer for ClickHouse Events

Handles all database operations for event data stored in ClickHouse.
Abstracts query building and result transformation from the service layer.

Design:
- Abstract base class defines interface
- Concrete implementation for ClickHouse
- Can be extended for other time-series databases
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import structlog
import httpx
import json

logger = structlog.get_logger(__name__)


class EventRepository(ABC):
    """
    Abstract Event Repository Interface
    
    Defines the contract for event data access.
    Allows swapping implementations (ClickHouse, TimescaleDB, etc.)
    """
    
    @abstractmethod
    async def get_event_counts_by_type(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Get event counts grouped by event type"""
        pass
    
    @abstractmethod
    async def get_top_namespaces(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top namespaces by event count"""
        pass
    
    @abstractmethod
    async def get_top_pods(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top pods by event count"""
        pass
    
    @abstractmethod
    async def get_time_range(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, Optional[str]]:
        """Get time range of events"""
        pass
    
    @abstractmethod
    async def get_dns_queries(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get DNS query events with pagination and search"""
        pass
    
    @abstractmethod
    async def delete_analysis_data(
        self, 
        analysis_id: int,
        wait_for_completion: bool = True,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Delete all events for an analysis
        
        Args:
            analysis_id: Analysis ID to delete
            wait_for_completion: Wait for mutations to complete
            timeout_seconds: Max wait time
            
        Returns:
            Deletion summary with counts and timing
        """
        pass
    
    @abstractmethod
    async def get_sni_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get TLS/SNI events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_process_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get process events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_file_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get file operation events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_security_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get security/capability events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_oom_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get OOM kill events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_bind_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get socket bind events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_mount_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get mount events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_network_flows(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get network flow events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_tcp_connections(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get TCP connection lifecycle events with pagination and search"""
        pass
    
    @abstractmethod
    async def get_all_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get all events with filtering, search and pagination"""
        pass


class ClickHouseEventRepository(EventRepository):
    """
    ClickHouse Implementation of Event Repository
    
    Uses HTTP interface to query ClickHouse.
    Handles query building, execution, and result transformation.
    """
    
    # Event tables mapping
    # Keys MUST match frontend EventType (frontend/src/store/api/eventsApi.ts)
    # Event tables mapping
    # Keys are frontend event types, values are ClickHouse table names
    # Table names MUST match the migrations (03-migrations-job.yaml)
    EVENT_TABLES = {
        "network_flow": "network_flows",
        "dns_query": "dns_queries",
        "tcp_connection": "tcp_lifecycle",       # Table: tcp_lifecycle
        "process_event": "process_events",
        "file_event": "file_operations",         # Table: file_operations
        "security_event": "capability_checks",   # Table: capability_checks
        "oom_event": "oom_kills",                # Table: oom_kills
        "bind_event": "bind_events",
        "sni_event": "sni_events",
        "mount_event": "mount_events",
    }
    
    def __init__(
        self,
        host: str = "clickhouse",
        port: int = 8123,
        database: str = "flowfish",
        user: str = "default",
        password: str = "",
        timeout: float = 30.0
    ):
        """
        Initialize ClickHouse repository
        
        Args:
            host: ClickHouse server hostname
            port: ClickHouse HTTP port
            database: Database name
            user: ClickHouse user (default: 'default')
            password: ClickHouse password
            timeout: Query timeout in seconds
        """
        self.base_url = f"http://{host}:{port}"
        self.database = database
        self.user = user
        self.password = password
        self.timeout = timeout
    
    async def _execute_query(self, sql: str) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a ClickHouse query via HTTP interface
        
        Args:
            sql: SQL query string
            
        Returns:
            List of result rows as dictionaries, or None on error
        """
        try:
            # Build query parameters with authentication
            params = {
                "database": self.database,
                "default_format": "JSONEachRow"
            }
            
            # Add authentication if user is specified
            if self.user:
                params["user"] = self.user
            if self.password:
                params["password"] = self.password
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    params=params,
                    content=sql.encode('utf-8')
                )
                
                if response.status_code == 200:
                    text = response.text.strip()
                    if not text:
                        return []
                    lines = text.split('\n')
                    return [json.loads(line) for line in lines if line]
                else:
                    logger.warning(
                        "ClickHouse query failed",
                        status_code=response.status_code,
                        response=response.text[:500]
                    )
                    return None
                    
        except httpx.ConnectError as e:
            logger.warning("Cannot connect to ClickHouse", error=str(e))
            return None
        except Exception as e:
            logger.error("ClickHouse query error", error=str(e))
            return None
    
    def _build_search_condition(self, search: str, fields: List[str]) -> str:
        """
        Build search condition for full-text search across multiple fields
        
        Uses ClickHouse's positionCaseInsensitive for case-insensitive substring matching.
        
        Args:
            search: Search term to look for
            fields: List of column names to search in
            
        Returns:
            SQL condition string (without AND prefix) or empty string if no search
            
        Example:
            _build_search_condition("10.128", ["source_ip", "dest_ip"])
            Returns: "(positionCaseInsensitive(source_ip, '10.128') > 0 OR positionCaseInsensitive(dest_ip, '10.128') > 0)"
        """
        if not search or not search.strip():
            return ""
        
        # SQL injection prevention - escape single quotes
        safe_search = search.strip().replace("'", "''")
        
        # Build OR conditions for each field
        conditions = []
        for field in fields:
            # positionCaseInsensitive returns position (1-based) or 0 if not found
            conditions.append(f"positionCaseInsensitive(toString({field}), '{safe_search}') > 0")
        
        return f"({' OR '.join(conditions)})"
    
    def _build_where_clause(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        extra_conditions: Optional[List[str]] = None,
        namespace_column: str = "source_namespace"
    ) -> str:
        """
        Build WHERE clause for queries
        
        Args:
            cluster_id: Required cluster filter (can be 0 to skip cluster filter for multi-cluster)
            analysis_id: Optional analysis filter
            namespace: Optional namespace filter
            search: Optional full-text search term
            search_fields: List of columns to search in (required if search is provided)
            start_time: Optional start time filter (ISO format)
            end_time: Optional end time filter (ISO format)
            extra_conditions: Additional WHERE conditions
            namespace_column: Column name for namespace (source_namespace for network tables)
            
        Returns:
            WHERE clause string (without 'WHERE' keyword)
            
        Note:
            - cluster_id and analysis_id are stored as Strings in ClickHouse
            - Use string comparison to avoid type mismatch errors
            - Multi-cluster support: analysis_id format is '{analysis_id}-{cluster_id}'
              so we use LIKE pattern matching for multi-cluster analyses
        """
        conditions = []
        
        # cluster_id filter - skip if 0 (for multi-cluster queries filtered by analysis_id)
        if cluster_id and cluster_id > 0:
            conditions.append(f"cluster_id = '{cluster_id}'")
        
        # Always filter out events with empty analysis_id (orphaned events)
        conditions.append("analysis_id != ''")
        
        if analysis_id:
            # Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
            # Use pattern matching to catch both single and multi-cluster traces
            conditions.append(f"(analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%')")
        
        if namespace:
            # Escape single quotes in namespace
            safe_ns = namespace.replace("'", "''")
            conditions.append(f"{namespace_column} = '{safe_ns}'")
        
        # Full-text search across specified fields
        if search and search_fields:
            search_condition = self._build_search_condition(search, search_fields)
            if search_condition:
                conditions.append(search_condition)
        
        if start_time:
            # Use parseDateTimeBestEffort for robust ISO 8601 parsing
            conditions.append(f"timestamp >= parseDateTimeBestEffort('{start_time}')")
        
        if end_time:
            # Use parseDateTimeBestEffort for robust ISO 8601 parsing
            conditions.append(f"timestamp <= parseDateTimeBestEffort('{end_time}')")
        
        if extra_conditions:
            conditions.extend(extra_conditions)
        
        return " AND ".join(conditions)
    
    async def get_event_counts_by_type(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Get event counts for each event type
        
        Queries each event table and aggregates counts.
        Note: For security_event (capability_checks), only counts denied verdicts
              to filter out millions of routine "allowed" capability checks.
        """
        counts = {}
        total = 0
        where_clause = self._build_where_clause(cluster_id, analysis_id)
        
        for event_type, table_name in self.EVENT_TABLES.items():
            # For security events, only count denied capability checks
            # This filters out millions of noise events from routine operations
            effective_where = where_clause
            if table_name == "capability_checks":
                effective_where += " AND verdict = 'denied'"
            
            sql = f"SELECT count() as cnt FROM {table_name} WHERE {effective_where}"
            result = await self._execute_query(sql)
            
            if result and len(result) > 0:
                cnt = int(result[0].get("cnt", 0))
                if cnt > 0:
                    counts[event_type] = cnt
                    total += cnt
        
        return counts
    
    async def get_top_namespaces(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top namespaces by event count from network_flows"""
        # Use source_namespace column (actual ClickHouse column name)
        where_clause = self._build_where_clause(
            cluster_id, 
            analysis_id,
            extra_conditions=["source_namespace != ''"],
            namespace_column="source_namespace"
        )
        
        sql = f"""
        SELECT source_namespace as namespace, count() as count
        FROM network_flows
        WHERE {where_clause}
        GROUP BY source_namespace
        ORDER BY count DESC
        LIMIT {limit}
        """
        
        result = await self._execute_query(sql)
        if result:
            return [
                {"namespace": r["namespace"], "count": int(r["count"])}
                for r in result
            ]
        return []
    
    async def get_top_pods(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top pods by event count from network_flows"""
        # Use source_pod and source_namespace columns (actual ClickHouse column names)
        where_clause = self._build_where_clause(
            cluster_id,
            analysis_id,
            extra_conditions=["source_pod != ''"],
            namespace_column="source_namespace"
        )
        
        sql = f"""
        SELECT source_pod as pod_name, source_namespace as namespace, count() as count
        FROM network_flows
        WHERE {where_clause}
        GROUP BY source_pod, source_namespace
        ORDER BY count DESC
        LIMIT {limit}
        """
        
        result = await self._execute_query(sql)
        if result:
            return [
                {
                    "pod": r["pod_name"],
                    "namespace": r["namespace"],
                    "count": int(r["count"])
                }
                for r in result
            ]
        return []
    
    async def get_time_range(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, Optional[str]]:
        """Get earliest and latest timestamp from network_flows"""
        where_clause = self._build_where_clause(cluster_id, analysis_id)
        
        sql = f"""
        SELECT
            min(timestamp) as start_time,
            max(timestamp) as end_time
        FROM network_flows
        WHERE {where_clause}
        """
        
        result = await self._execute_query(sql)
        if result and len(result) > 0:
            row = result[0]
            return {
                "start": str(row.get("start_time")) if row.get("start_time") else None,
                "end": str(row.get("end_time")) if row.get("end_time") else None
            }
        return {"start": None, "end": None}
    
    # Search fields for each event type
    DNS_SEARCH_FIELDS = ["query_name", "dns_server_ip", "pod", "namespace"]
    SNI_SEARCH_FIELDS = ["server_name", "dest_ip", "pod", "namespace", "comm"]
    NETWORK_SEARCH_FIELDS = ["source_ip", "dest_ip", "source_pod", "dest_pod", "source_namespace", "dest_namespace"]
    BIND_SEARCH_FIELDS = ["bind_addr", "bind_port", "comm", "interface", "pod", "namespace"]
    PROCESS_SEARCH_FIELDS = ["comm", "exe", "pod", "namespace"]
    FILE_SEARCH_FIELDS = ["file_path", "comm", "pod", "namespace"]
    SECURITY_SEARCH_FIELDS = ["capability", "syscall", "comm", "pod", "namespace"]
    OOM_SEARCH_FIELDS = ["comm", "pod", "namespace", "node"]
    MOUNT_SEARCH_FIELDS = ["source", "target", "fs_type", "comm", "pod", "namespace"]
    
    async def get_dns_queries(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get DNS query events with pagination and search
        
        Args:
            search: Full-text search across query_name, dns_server_ip, pod, namespace
        
        Returns:
            Tuple of (events list, total count)
        """
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.DNS_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time
        )
        
        # Get count first
        count_sql = f"SELECT count() as cnt FROM dns_queries WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        # Get data
        sql = f"""
        SELECT *
        FROM dns_queries
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_sni_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get TLS/SNI events with pagination and search
        
        Args:
            search: Full-text search across server_name, dest_ip, pod, namespace, comm
        
        Returns:
            Tuple of (events list, total count)
        """
        # SNI events use 'namespace' column, not 'source_namespace'
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.SNI_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        # Get count first
        count_sql = f"SELECT count() as cnt FROM sni_events WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        # Get data
        sql = f"""
        SELECT *
        FROM sni_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_process_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get process events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.PROCESS_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM process_events WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM process_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_file_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get file operation events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.FILE_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM file_operations WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM file_operations
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_security_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get security/capability events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.SECURITY_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        # Only show denied capability checks - allowed checks are routine operations
        # This filters out millions of noise events and shows actual security concerns
        where_clause += " AND verdict = 'denied'"
        
        count_sql = f"SELECT count() as cnt FROM capability_checks WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM capability_checks
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_oom_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get OOM kill events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.OOM_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM oom_kills WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM oom_kills
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_bind_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get socket bind events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.BIND_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM bind_events WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM bind_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_mount_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get mount events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.MOUNT_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM mount_events WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM mount_events
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_network_flows(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get network flow events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.NETWORK_SEARCH_FIELDS,
            start_time=start_time, end_time=end_time,
            namespace_column="source_namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM network_flows WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM network_flows
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    async def get_tcp_connections(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get TCP connection lifecycle events with pagination and search"""
        where_clause = self._build_where_clause(
            cluster_id, analysis_id, namespace,
            search=search, search_fields=self.NETWORK_SEARCH_FIELDS,
            namespace_column="source_namespace"
        )
        
        count_sql = f"SELECT count() as cnt FROM tcp_lifecycle WHERE {where_clause}"
        count_result = await self._execute_query(count_sql)
        total = int(count_result[0]["cnt"]) if count_result else 0
        
        sql = f"""
        SELECT *
        FROM tcp_lifecycle
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(sql)
        return (result if result else [], total)
    
    # Search fields mapping for each table
    TABLE_SEARCH_FIELDS = {
        "network_flows": ["source_ip", "dest_ip", "source_pod", "dest_pod", "source_namespace", "dest_namespace"],
        "tcp_lifecycle": ["source_ip", "dest_ip", "source_pod", "dest_pod", "source_namespace", "dest_namespace"],
        "dns_queries": ["query_name", "dns_server_ip", "source_pod", "source_namespace"],
        "sni_events": ["sni_name", "dst_ip", "pod", "namespace", "comm"],
        "process_events": ["comm", "exe", "pod", "namespace"],
        "file_operations": ["file_path", "comm", "pod", "namespace"],
        "capability_checks": ["capability", "syscall", "comm", "pod", "namespace"],
        "oom_kills": ["comm", "pod", "namespace", "node"],
        "bind_events": ["bind_addr", "bind_port", "comm", "interface", "pod", "namespace"],
        "mount_events": ["source", "target", "fs_type", "comm", "pod", "namespace"],
    }
    
    async def get_all_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all events with filtering, search and pagination
        
        Uses UNION ALL to query multiple tables and merge results.
        """
        # Filter tables based on event_types
        tables_to_query = self.EVENT_TABLES.copy()
        if event_types:
            tables_to_query = {k: v for k, v in self.EVENT_TABLES.items() if k in event_types}
        
        if not tables_to_query:
            return ([], 0)
        
        # Build time conditions
        extra_conditions = []
        if start_time:
            extra_conditions.append(f"timestamp >= '{start_time}'")
        if end_time:
            extra_conditions.append(f"timestamp <= '{end_time}'")
        
        # Build UNION ALL query for counts
        count_queries = []
        for event_type, table_name in tables_to_query.items():
            # Different namespace column for network tables
            ns_col = "source_namespace" if table_name in ("network_flows", "tcp_lifecycle") else "namespace"
            # Get appropriate search fields for this table
            search_fields = self.TABLE_SEARCH_FIELDS.get(table_name, ["pod", "namespace"])
            where_clause = self._build_where_clause(
                cluster_id, analysis_id, namespace,
                search=search, search_fields=search_fields,
                extra_conditions=extra_conditions,
                namespace_column=ns_col
            )
            count_queries.append(f"SELECT count() as cnt FROM {table_name} WHERE {where_clause}")
        
        # Sum all counts
        total = 0
        for cq in count_queries:
            result = await self._execute_query(cq)
            if result:
                total += int(result[0].get("cnt", 0))
        
        # Build UNION ALL for data
        data_queries = []
        for event_type, table_name in tables_to_query.items():
            ns_col = "source_namespace" if table_name in ("network_flows", "tcp_lifecycle") else "namespace"
            search_fields = self.TABLE_SEARCH_FIELDS.get(table_name, ["pod", "namespace"])
            where_clause = self._build_where_clause(
                cluster_id, analysis_id, namespace,
                search=search, search_fields=search_fields,
                extra_conditions=extra_conditions,
                namespace_column=ns_col
            )
            
            # Normalize column names across different tables
            if table_name == "network_flows":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        source_namespace as namespace,
                        source_pod as pod,
                        source_container as container,
                        source_pod as source,
                        dest_pod as target,
                        concat('Port ', toString(dest_port), ' via ', protocol) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "tcp_lifecycle":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        source_namespace as namespace,
                        source_pod as pod,
                        source_container as container,
                        source_ip as source,
                        dest_ip as target,
                        concat(old_state, ' -> ', new_state) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "dns_queries":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        source_namespace as namespace,
                        source_pod as pod,
                        source_container as container,
                        source_pod as source,
                        query_name as target,
                        concat(query_type, ' query, ', response_code) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "process_events":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        comm as source,
                        exe as target,
                        concat(event_type, ' PID:', toString(pid)) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "file_operations":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        comm as source,
                        file_path as target,
                        concat(operation, ' ', toString(bytes), 'B') as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "capability_checks":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        comm as source,
                        capability as target,
                        concat(syscall, ' - ', verdict) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "oom_kills":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        comm as source,
                        '' as target,
                        concat('OOM Kill - ', toString(memory_usage), '/', toString(memory_limit)) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "bind_events":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        comm as source,
                        concat(bind_addr, ':', toString(bind_port)) as target,
                        concat('Bind ', protocol) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "sni_events":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        pod as source,
                        sni_name as target,
                        concat('TLS to ', dst_ip, ':', toString(dst_port)) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
            elif table_name == "mount_events":
                data_queries.append(f"""
                    SELECT 
                        timestamp,
                        event_id,
                        '{event_type}' as event_type,
                        cluster_id,
                        analysis_id,
                        namespace,
                        pod,
                        container,
                        source as source,
                        target as target,
                        concat(operation, ' ', fs_type) as details
                    FROM {table_name}
                    WHERE {where_clause}
                """)
        
        if not data_queries:
            return ([], 0)
        
        # Combine with UNION ALL and sort
        union_sql = " UNION ALL ".join(data_queries)
        final_sql = f"""
        SELECT * FROM (
            {union_sql}
        ) AS combined
        ORDER BY timestamp DESC
        LIMIT {limit} OFFSET {offset}
        """
        
        result = await self._execute_query(final_sql)
        return (result if result else [], total)
    
    async def delete_analysis_data(
        self, 
        analysis_id: int, 
        wait_for_completion: bool = True,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Delete all events for an analysis from all ClickHouse tables
        
        Args:
            analysis_id: Analysis ID to delete data for
            wait_for_completion: If True, wait for mutations to complete
            timeout_seconds: Max time to wait for mutations (default 60s)
        
        Returns:
            Dictionary with deletion summary:
            {
                "tables": {"network_flows": 1234, ...},
                "total_deleted": 5678,
                "completed": True/False,
                "duration_ms": 1234
            }
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        tables = [
            'network_flows',
            'dns_queries', 
            'tcp_lifecycle',
            'process_events',
            'file_operations',
            'capability_checks',
            'oom_kills',  # Fixed: was 'oom_events' but table is 'oom_kills'
            'bind_events',
            'sni_events',
            'mount_events',
            'workload_metadata',
            'communication_edges',  # Added: also needs to be deleted
            'change_events'  # Change events (ClickHouse-only storage)
        ]
        
        # Step 0: Diagnostic - check for orphaned records (empty analysis_id)
        diagnostic = {"total_all": {}, "with_analysis_id": {}, "empty_analysis_id": {}}
        for table in tables:
            try:
                # Total count
                total_sql = f"SELECT count() as cnt FROM {table}"
                result = await self._execute_query(total_sql)
                diagnostic["total_all"][table] = int(result[0]["cnt"]) if result else 0
                
                # Count with empty/null analysis_id
                empty_sql = f"SELECT count() as cnt FROM {table} WHERE analysis_id = '' OR analysis_id IS NULL"
                result = await self._execute_query(empty_sql)
                diagnostic["empty_analysis_id"][table] = int(result[0]["cnt"]) if result else 0
            except Exception as e:
                logger.debug(f"Diagnostic query failed for {table}: {e}")
        
        total_orphaned = sum(diagnostic["empty_analysis_id"].values())
        total_in_db = sum(diagnostic["total_all"].values())
        
        if total_orphaned > 0:
            logger.warning(f"Found {total_orphaned} orphaned records (empty analysis_id) out of {total_in_db} total",
                          breakdown=diagnostic["empty_analysis_id"])
        
        # Step 1: Get counts before deletion for reporting
        # Multi-cluster support: analysis_id can be '{id}' or '{id}-{cluster_id}' format
        counts_before = {}
        for table in tables:
            try:
                # Match both single-cluster (analysis_id = '123') and multi-cluster (analysis_id LIKE '123-%')
                count_sql = f"SELECT count() as cnt FROM {table} WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                result = await self._execute_query(count_sql)
                counts_before[table] = int(result[0]["cnt"]) if result else 0
                diagnostic["with_analysis_id"][table] = counts_before[table]
            except:
                counts_before[table] = 0
        
        total_to_delete = sum(counts_before.values())
        logger.info(f"Found {total_to_delete} records to delete across {len(tables)} tables",
                   analysis_id=analysis_id,
                   breakdown=counts_before,
                   diagnostic=diagnostic)
        
        if total_to_delete == 0:
            return {
                "tables": counts_before,
                "total_deleted": 0,
                "completed": True,
                "duration_ms": int((time.time() - start_time) * 1000),
                "diagnostic": diagnostic,
                "warning": f"Found {total_orphaned} orphaned records with empty analysis_id" if total_orphaned > 0 else None
            }
        
        # Step 2: Submit delete mutations
        # Multi-cluster support: delete both single-cluster and multi-cluster data
        mutation_ids = []
        for table in tables:
            if counts_before.get(table, 0) == 0:
                continue  # Skip empty tables
            try:
                # Use SETTINGS mutations_sync=1 for synchronous execution if possible
                # Otherwise use async mutation
                # Match both single-cluster (analysis_id = '123') and multi-cluster (analysis_id LIKE '123-%')
                delete_sql = f"ALTER TABLE {table} DELETE WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                await self._execute_query(delete_sql)
                mutation_ids.append(table)
                logger.debug(f"Delete mutation submitted for {table}", analysis_id=analysis_id)
            except Exception as e:
                logger.warning(f"Failed to delete from {table}", 
                             analysis_id=analysis_id, 
                             error=str(e))
        
        # Step 3: Wait for mutations to complete (if requested)
        completed = True
        if wait_for_completion and mutation_ids:
            deadline = time.time() + timeout_seconds
            
            while time.time() < deadline:
                # Check if any mutations are still running
                try:
                    # Query system.mutations for pending mutations
                    check_sql = """
                    SELECT table, mutation_id, is_done
                    FROM system.mutations
                    WHERE database = 'flowfish' 
                      AND is_done = 0
                      AND create_time > now() - INTERVAL 5 MINUTE
                    """
                    pending = await self._execute_query(check_sql)
                    
                    # Check if our tables have pending mutations
                    pending_tables = {r["table"] for r in (pending or [])}
                    our_pending = set(mutation_ids) & pending_tables
                    
                    if not our_pending:
                        logger.info("All mutations completed", analysis_id=analysis_id)
                        break
                    
                    logger.debug(f"Waiting for mutations: {our_pending}", analysis_id=analysis_id)
                    await asyncio.sleep(0.5)  # Poll every 500ms
                    
                except Exception as e:
                    logger.warning(f"Error checking mutation status: {e}")
                    await asyncio.sleep(1)
            else:
                completed = False
                logger.warning("Mutation timeout - some deletions may still be in progress",
                             analysis_id=analysis_id)
        
        # Step 4: Get final counts for verification (use same multi-cluster pattern)
        counts_after = {}
        for table in tables:
            try:
                count_sql = f"SELECT count() as cnt FROM {table} WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                result = await self._execute_query(count_sql)
                counts_after[table] = int(result[0]["cnt"]) if result else 0
            except:
                counts_after[table] = 0
        
        deleted_counts = {
            table: counts_before.get(table, 0) - counts_after.get(table, 0)
            for table in tables
        }
        total_deleted = sum(deleted_counts.values())
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info("ClickHouse deletion completed",
                   analysis_id=analysis_id,
                   total_deleted=total_deleted,
                   duration_ms=duration_ms,
                   completed=completed,
                   orphaned_records=total_orphaned)
        
        result = {
            "tables": deleted_counts,
            "total_deleted": total_deleted,
            "completed": completed,
            "duration_ms": duration_ms,
            "diagnostic": diagnostic
        }
        
        if total_orphaned > 0:
            result["warning"] = f"Found {total_orphaned} orphaned records with empty analysis_id in database"
        
        return result


class TimeseriesQueryEventRepository(EventRepository):
    """
    Timeseries Query Service based Event Repository
    
    Uses the timeseries-query microservice for data access.
    This follows the same pattern as graph-query for Neo4j.
    
    Benefits:
    - Database access is abstracted behind a microservice
    - Centralized query optimization and caching
    - Consistent architecture with graph-query pattern
    """
    
    def __init__(self, base_url: str = "http://timeseries-query:8002", timeout: float = 30.0):
        """
        Initialize Timeseries Query client
        
        Args:
            base_url: Timeseries Query Service URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        logger.info(f"TimeseriesQueryEventRepository initialized", base_url=self.base_url)
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to timeseries-query service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}{endpoint}",
                    params={k: v for k, v in (params or {}).items() if v is not None}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        "Timeseries query request failed",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        response=response.text[:500]
                    )
                    return None
                    
        except httpx.ConnectError as e:
            logger.warning("Cannot connect to timeseries-query service", error=str(e))
            return None
        except Exception as e:
            logger.error("Timeseries query error", endpoint=endpoint, error=str(e))
            return None
    
    async def get_event_counts_by_type(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Get event counts by type from timeseries-query service"""
        result = await self._request(
            "/events/stats",
            {"cluster_id": cluster_id, "analysis_id": analysis_id}
        )
        
        if result:
            return result.get("event_counts", {})
        return {}
    
    async def get_top_namespaces(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top namespaces from timeseries-query service"""
        result = await self._request(
            "/events/stats",
            {"cluster_id": cluster_id, "analysis_id": analysis_id}
        )
        
        if result:
            return result.get("top_namespaces", [])[:limit]
        return []
    
    async def get_top_pods(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top pods from timeseries-query service"""
        result = await self._request(
            "/events/stats",
            {"cluster_id": cluster_id, "analysis_id": analysis_id}
        )
        
        if result:
            return result.get("top_pods", [])[:limit]
        return []
    
    async def get_time_range(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, Optional[str]]:
        """Get time range from timeseries-query service"""
        result = await self._request(
            "/events/stats",
            {"cluster_id": cluster_id, "analysis_id": analysis_id}
        )
        
        if result:
            time_range = result.get("time_range", {})
            return {
                "start": time_range.get("start"),
                "end": time_range.get("end")
            }
        return {"start": None, "end": None}
    
    async def get_dns_queries(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get DNS queries from timeseries-query service"""
        result = await self._request(
            "/events/dns",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("queries", []), result.get("total", 0))
        return ([], 0)
    
    async def get_sni_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get SNI events from timeseries-query service"""
        result = await self._request(
            "/events/sni",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_process_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get process events from timeseries-query service"""
        result = await self._request(
            "/events/process",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_file_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get file events from timeseries-query service"""
        result = await self._request(
            "/events/file",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_security_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get security events from timeseries-query service"""
        result = await self._request(
            "/events/security",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_oom_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get OOM events from timeseries-query service"""
        result = await self._request(
            "/events/oom",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_bind_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get bind events from timeseries-query service"""
        result = await self._request(
            "/events/bind",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_mount_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get mount events from timeseries-query service"""
        result = await self._request(
            "/events/mount",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_network_flows(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get network flows from timeseries-query service"""
        result = await self._request(
            "/events/network",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_tcp_connections(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get TCP connections from timeseries-query service"""
        result = await self._request(
            "/events/tcp",
            {
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "search": search,
                "limit": limit,
                "offset": offset
            }
        )
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_all_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get all events from timeseries-query service"""
        params = {
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "namespace": namespace,
            "search": search,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "offset": offset
        }
        
        if event_types:
            params["event_types"] = ",".join(event_types)
        
        result = await self._request("/events", params)
        
        if result:
            return (result.get("events", []), result.get("total", 0))
        return ([], 0)
    
    async def get_event_histogram(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        bucket_count: int = 60
    ) -> Dict[str, Any]:
        """Get time-bucketed event histogram from timeseries-query service"""
        params = {
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "start_time": start_time,
            "end_time": end_time,
            "bucket_count": bucket_count
        }
        
        if event_types:
            params["event_types"] = ",".join(event_types)
        
        result = await self._request("/events/histogram", params)
        
        if result:
            return result
        return {"buckets": [], "time_range": {"start": None, "end": None}, "interval_seconds": 0, "total_events": 0}
    
    async def delete_analysis_data(
        self,
        analysis_id: int,
        wait_for_completion: bool = True,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Delete analysis data via timeseries-query service
        
        This uses the /admin/analysis/{analysis_id} endpoint which handles
        the actual ClickHouse deletion with mutation tracking.
        """
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds + 10) as client:
                response = await client.delete(
                    f"{self.base_url}/admin/analysis/{analysis_id}",
                    params={
                        "wait_for_completion": wait_for_completion,
                        "timeout_seconds": timeout_seconds
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        "Delete analysis data failed",
                        analysis_id=analysis_id,
                        status_code=response.status_code,
                        response=response.text[:500]
                    )
                    return {
                        "tables": {},
                        "total_deleted": 0,
                        "completed": False,
                        "error": f"HTTP {response.status_code}: {response.text[:200]}"
                    }
                    
        except httpx.ConnectError as e:
            logger.error("Cannot connect to timeseries-query service", error=str(e))
            return {
                "tables": {},
                "total_deleted": 0,
                "completed": False,
                "error": f"Connection error: {str(e)}"
            }
        except Exception as e:
            logger.error("Delete analysis data error", error=str(e))
            return {
                "tables": {},
                "total_deleted": 0,
                "completed": False,
                "error": str(e)
            }


# Default repository instance factory
def get_event_repository(use_microservice: bool = True) -> EventRepository:
    """
    Factory function for EventRepository dependency injection
    
    Args:
        use_microservice: If True, use timeseries-query microservice (recommended).
                         If False, use direct ClickHouse connection.
    
    Returns:
        EventRepository implementation
    
    Architecture:
    - use_microservice=True → TimeseriesQueryEventRepository (via HTTP)
      Same pattern as graph-query service for Neo4j.
      
    - use_microservice=False → ClickHouseEventRepository (direct)
      For admin operations like delete, or when microservice is unavailable.
    """
    from config import settings, get_clickhouse_config
    
    if use_microservice:
        # Use timeseries-query microservice (recommended for production)
        return TimeseriesQueryEventRepository(
            base_url=settings.TIMESERIES_QUERY_URL,
            timeout=30.0
        )
    else:
        # Direct ClickHouse access (for admin operations)
        ch_config = get_clickhouse_config()
        return ClickHouseEventRepository(
            host=ch_config.get('host', 'clickhouse'),
            port=ch_config.get('port', 8123),
            database=ch_config.get('database', 'flowfish'),
            user=ch_config.get('user', 'default'),
            password=ch_config.get('password', ''),
            timeout=30.0
        )

