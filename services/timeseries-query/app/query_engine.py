"""
Timeseries Query Engine - Event Data Query Layer

Provides abstracted access to time-series event data.
Currently backed by ClickHouse, but interface is database-agnostic.
"""

import logging
import math
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as DatabaseError

# W3C trace_id is 32 hex chars (16 bytes); we accept any non-empty hex prefix
# in case truncated/legacy values arrive, but validate strictly to prevent
# SQL injection via the ClickHouse string-interpolation pattern used here.
_TRACE_ID_RE = re.compile(r'^[0-9a-fA-F]{1,32}$')


def _validate_trace_id(trace_id: str) -> str:
    """Validate and normalize a W3C trace_id. Raises ValueError when invalid.

    Used by all trace-related query methods. Returns lowercase normalized form.
    """
    if not isinstance(trace_id, str) or not _TRACE_ID_RE.match(trace_id):
        raise ValueError(f"Invalid trace_id format: {trace_id!r}")
    return trace_id.lower()

from app.config import settings

logger = logging.getLogger(__name__)


class TimeseriesQueryEngine:
    """
    Query engine for time-series event data
    
    Features:
    - Database-agnostic interface
    - Connection pooling
    - Query timeout handling
    - Result pagination
    - Aggregation support
    """
    
    # Event type to table mapping
    # NOTE: tcp_lifecycle removed - IG trace_tcp doesn't produce TCP state events
    EVENT_TABLES = {
        "network_flow": "network_flows",
        "dns_query": "dns_queries",
        "process_event": "process_events",
        "file_event": "file_operations",
        "security_event": "capability_checks",
        "oom_event": "oom_kills",
        "bind_event": "bind_events",
        "sni_event": "sni_events",
        "mount_event": "mount_events",
        "l7_http_flow": "l7_http_flows",
        "l7_grpc_flow": "l7_grpc_flows",
        "l7_dns_flow": "l7_dns_flows",
    }
    
    def __init__(self):
        self.client = None
        self._connect()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.client = Client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                user=settings.clickhouse_user,
                password=settings.clickhouse_password,
                database=settings.clickhouse_database,
                send_receive_timeout=settings.query_timeout,
                connect_timeout=10,
            )
            
            # Test connection
            self.client.execute('SELECT 1')
            logger.info(f"✅ Connected to timeseries database at {settings.clickhouse_host}:{settings.clickhouse_port}")
            
        except DatabaseError as e:
            logger.error(f"❌ Failed to connect to timeseries database: {e}")
            raise
    
    TABLE_SEARCH_FIELDS = {
        "network_flows": ["source_ip", "dest_ip", "source_pod", "dest_pod", "source_namespace", "dest_namespace"],
        "dns_queries": ["query_name", "dns_server_ip", "source_pod", "source_namespace"],
        "sni_events": ["sni_name", "dst_ip", "pod", "namespace", "comm"],
        "process_events": ["comm", "exe", "pod", "namespace"],
        "file_operations": ["file_path", "comm", "pod", "namespace"],
        "capability_checks": ["capability", "syscall", "comm", "pod", "namespace"],
        "oom_kills": ["comm", "pod", "namespace", "node"],
        "bind_events": ["bind_addr", "comm", "interface", "pod", "namespace"],
        "mount_events": ["source", "target", "fs_type", "comm", "pod", "namespace"],
        "l7_http_flows": ["src_namespace", "src_workload", "dst_namespace", "dst_workload", "http_method", "http_path", "http_host"],
        "l7_grpc_flows": ["src_namespace", "src_workload", "dst_namespace", "dst_workload", "grpc_method", "grpc_service"],
        "l7_dns_flows": ["src_namespace", "src_workload", "query_name", "query_type"],
    }

    def _build_search_condition(self, search: str, search_fields: List[str]) -> str:
        """
        Build search condition for full-text search across multiple fields.
        Uses positionCaseInsensitive for case-insensitive substring matching.

        Escaping note: ClickHouse string literals interpret backslash as
        an escape introducer, so a malicious caller could pass `\\' OR 1=1`
        and the doubled-up quote would land *inside* an active escape
        sequence rather than terminating it. We therefore double the
        backslashes first and only then double the single quotes — this
        mirrors the `_escape_ch` helper used elsewhere in this file
        (added during a previous audit).
        """
        if not search or not search.strip():
            return ""

        safe_search = (
            search.strip()
            .replace("\\", "\\\\")
            .replace("'", "''")
        )
        conditions = []
        for field in search_fields:
            conditions.append(f"positionCaseInsensitive(toString({field}), '{safe_search}') > 0")

        return f"({' OR '.join(conditions)})"

    def _build_where_clause(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        namespace_column: str = "namespace",
        extra_conditions: Optional[List[str]] = None,
        search: Optional[str] = None,
        search_fields: Optional[List[str]] = None
    ) -> str:
        """
        Build WHERE clause from filters
        
        Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
        Uses LIKE pattern matching to support both formats.
        """
        conditions = ["1=1"]
        
        # cluster_id filter - optional for multi-cluster queries
        if cluster_id and cluster_id > 0:
            conditions.append(f"cluster_id = '{cluster_id}'")
        
        # Multi-cluster support: match both single-cluster and multi-cluster analysis_id formats
        if analysis_id:
            conditions.append(f"(analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%')")
        
        if namespace:
            conditions.append(f"{namespace_column} = '{namespace}'")
        
        if start_time:
            # Use parseDateTimeBestEffort for robust ISO 8601 parsing
            conditions.append(f"timestamp >= parseDateTimeBestEffort('{start_time}')")
        
        if end_time:
            # Use parseDateTimeBestEffort for robust ISO 8601 parsing
            conditions.append(f"timestamp <= parseDateTimeBestEffort('{end_time}')")
        
        if search and search_fields:
            search_condition = self._build_search_condition(search, search_fields)
            if search_condition:
                conditions.append(search_condition)
        
        if extra_conditions:
            conditions.extend(extra_conditions)
        
        return " AND ".join(conditions)
    
    async def get_event_stats(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated event statistics
        
        Returns counts per event type, time range, top namespaces/pods.
        Gracefully handles missing tables (e.g., L7 tables absent in L4-only
        deployments, or L4 tables absent in L7-only setups).
        """
        try:
            event_counts = {}
            
            L7_TABLES = {"l7_http_flows", "l7_grpc_flows", "l7_dns_flows"}
            SOURCE_COL_TABLES = {"network_flows", "dns_queries"}

            for event_type, table_name in self.EVENT_TABLES.items():
                ns_col = "source_namespace" if table_name in SOURCE_COL_TABLES else ("src_namespace" if table_name in L7_TABLES else "namespace")
                where = self._build_where_clause(cluster_id, analysis_id, namespace_column=ns_col)
                
                if table_name == "capability_checks":
                    sensitive_caps = [
                        'CAP_SYS_ADMIN', 'CAP_NET_ADMIN', 'CAP_NET_RAW', 
                        'CAP_SYS_PTRACE', 'CAP_SYS_MODULE', 'CAP_DAC_OVERRIDE',
                        'CAP_SETUID', 'CAP_SETGID', 'CAP_CHOWN', 'CAP_FOWNER',
                        'CAP_SYS_RAWIO', 'CAP_MKNOD', 'CAP_LINUX_IMMUTABLE'
                    ]
                    sensitive_caps_str = ", ".join([f"'{c}'" for c in sensitive_caps])
                    where += f" AND (verdict = 'denied' OR verdict = '1' OR toString(verdict) = '1' OR capability IN ({sensitive_caps_str}))"
                
                try:
                    query = f"SELECT count() as cnt FROM {table_name} WHERE {where}"
                    result = self.client.execute(query)
                    count = result[0][0] if result else 0
                    if count > 0:
                        event_counts[event_type] = count
                except Exception as table_err:
                    logger.debug(f"Table {table_name} not available: {table_err}")
            
            total_events = sum(event_counts.values())
            
            # Time range / top namespaces / top pods — try network_flows first,
            # fall back to l7_http_flows, then skip if neither exists.
            time_range = {"start": None, "end": None}
            top_namespaces: list = []
            top_pods: list = []
            
            for stats_table, ns_col, pod_col in [
                ("network_flows", "source_namespace", "source_pod"),
                ("l7_http_flows", "src_namespace", "src_workload"),
            ]:
                try:
                    where_ts = self._build_where_clause(cluster_id, analysis_id, namespace_column=ns_col)
                    time_query = f"SELECT min(timestamp), max(timestamp) FROM {stats_table} WHERE {where_ts}"
                    time_result = self.client.execute(time_query)
                    if time_result and time_result[0][0]:
                        time_range = {
                            "start": time_result[0][0].isoformat(),
                            "end": time_result[0][1].isoformat() if time_result[0][1] else None
                        }
                    
                    ns_query = f"""
                    SELECT {ns_col} as namespace, count() as cnt 
                    FROM {stats_table} WHERE {where_ts}
                    GROUP BY {ns_col} ORDER BY cnt DESC LIMIT 10
                    """
                    ns_result = self.client.execute(ns_query)
                    top_namespaces = [{"namespace": r[0], "count": r[1]} for r in ns_result]
                    
                    pod_query = f"""
                    SELECT {pod_col} as pod, {ns_col} as namespace, count() as cnt 
                    FROM {stats_table} WHERE {where_ts}
                    GROUP BY {pod_col}, {ns_col} ORDER BY cnt DESC LIMIT 10
                    """
                    pod_result = self.client.execute(pod_query)
                    top_pods = [{"pod": r[0], "namespace": r[1], "count": r[2]} for r in pod_result]
                    break  # success — no need to try the next table
                except Exception:
                    continue
            
            return {
                "cluster_id": str(cluster_id),
                "analysis_id": str(analysis_id) if analysis_id else "",
                "total_events": total_events,
                "event_counts": event_counts,
                "time_range": time_range,
                "top_namespaces": top_namespaces,
                "top_pods": top_pods
            }
            
        except Exception as e:
            logger.error(f"Failed to get event stats: {e}")
            raise
    
    async def query_events(
        self,
        event_type: str,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query events by type with pagination
        
        Args:
            event_type: Type of event (network_flow, dns_query, etc.)
            cluster_id: Cluster ID filter
            analysis_id: Optional analysis ID filter
            namespace: Optional namespace filter
            start_time: Optional start time (ISO format)
            end_time: Optional end time (ISO format)
            limit: Max results (default 100)
            offset: Pagination offset
            search: Optional full-text search across relevant fields
            
        Returns:
            Tuple of (events list, total count)
        """
        try:
            table_name = self.EVENT_TABLES.get(event_type)
            if not table_name:
                raise ValueError(f"Unknown event type: {event_type}")
            
            L7_TABLES_Q = {"l7_http_flows", "l7_grpc_flows", "l7_dns_flows"}
            SOURCE_COL_TABLES_Q = {"network_flows", "dns_queries"}
            ns_col = "source_namespace" if table_name in SOURCE_COL_TABLES_Q else ("src_namespace" if table_name in L7_TABLES_Q else "namespace")
            
            # Resolve search fields for this table
            s_fields = self.TABLE_SEARCH_FIELDS.get(table_name) if search else None
            
            where_clause = self._build_where_clause(
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                namespace=namespace,
                start_time=start_time,
                end_time=end_time,
                namespace_column=ns_col,
                search=search,
                search_fields=s_fields
            )
            
            # For security events (capability_checks), show:
            # 1. All denied verdicts (blocked capabilities)
            # 2. Sensitive capabilities even if allowed (potential security concerns)
            # Note: verdict can be string ('denied') or integer (1) depending on data version
            if table_name == "capability_checks":
                sensitive_caps = [
                    'CAP_SYS_ADMIN', 'CAP_NET_ADMIN', 'CAP_NET_RAW', 
                    'CAP_SYS_PTRACE', 'CAP_SYS_MODULE', 'CAP_DAC_OVERRIDE',
                    'CAP_SETUID', 'CAP_SETGID', 'CAP_CHOWN', 'CAP_FOWNER',
                    'CAP_SYS_RAWIO', 'CAP_MKNOD', 'CAP_LINUX_IMMUTABLE'
                ]
                sensitive_caps_str = ", ".join([f"'{c}'" for c in sensitive_caps])
                # Support both string 'denied' and integer '1' verdict formats
                where_clause += f" AND (verdict = 'denied' OR verdict = '1' OR toString(verdict) = '1' OR capability IN ({sensitive_caps_str}))"
                logger.info(f"Security events filter: denied + sensitive capabilities")
            
            # Get count
            count_query = f"SELECT count() FROM {table_name} WHERE {where_clause}"
            count_result = self.client.execute(count_query)
            total = count_result[0][0] if count_result else 0
            
            # Get data
            data_query = f"""
            SELECT * 
            FROM {table_name} 
            WHERE {where_clause} 
            ORDER BY timestamp DESC 
            LIMIT {limit} OFFSET {offset}
            """
            
            result = self.client.execute(data_query, with_column_types=True)
            
            if not result:
                return ([], total)
            
            rows, columns = result
            column_names = [col[0] for col in columns]
            
            events = []
            for row in rows:
                event = {}
                for i, col_name in enumerate(column_names):
                    value = row[i]
                    # Handle datetime serialization
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    event[col_name] = value
                events.append(event)
            
            return (events, total)
            
        except Exception as e:
            logger.error(f"Failed to query {event_type} events: {e}")
            raise
    
    async def query_network_flows(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query network flow events"""
        return await self.query_events(
            "network_flow", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_dns_queries(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query DNS query events"""
        return await self.query_events(
            "dns_query", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_process_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query process events"""
        return await self.query_events(
            "process_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_file_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query file operation events"""
        return await self.query_events(
            "file_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_security_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query security/capability events"""
        return await self.query_events(
            "security_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_oom_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query OOM kill events"""
        return await self.query_events(
            "oom_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_bind_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query socket bind events"""
        return await self.query_events(
            "bind_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_sni_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query TLS/SNI events"""
        return await self.query_events(
            "sni_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    async def query_mount_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query mount events"""
        return await self.query_events(
            "mount_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset, search=search
        )
    
    # NOTE: query_tcp_connections removed - IG trace_tcp doesn't produce TCP state events
    # TCP connection info is captured in network_flows via connect/accept/close events
    
    # Per-table search field map. Mirrors backend ClickHouseEventRepository
    # `TABLE_SEARCH_FIELDS` so the UI's "Search" box matches the same
    # surface regardless of which repository implementation is wired in.
    #
    # CRITICAL: every column listed here must actually exist on the
    # table — `_build_search_condition` builds
    # `positionCaseInsensitive(toString({col}), '...')` and ClickHouse
    # rejects unknown identifiers with a 500. The legacy
    # `TABLE_SEARCH_FIELDS` in event_repository.py listed `dest_pod`
    # and `dest_namespace` for `tcp_lifecycle`, but the actual schema
    # for that table only has source-side columns plus dest_ip /
    # dest_port. We deliberately diverge from the backend copy here
    # (and document the discrepancy) so this code path doesn't
    # inherit a 500-on-search bug.
    _SEARCH_FIELDS_BY_TABLE: Dict[str, List[str]] = {
        "network_flows": [
            "source_ip", "dest_ip", "source_pod", "dest_pod",
            "source_namespace", "dest_namespace",
        ],
        # tcp_lifecycle has source_namespace/source_pod but no
        # dest_namespace/dest_pod columns — only dest_ip/dest_port.
        "tcp_lifecycle": [
            "source_ip", "dest_ip", "source_pod", "source_namespace",
        ],
        "dns_queries": [
            "query_name", "dns_server_ip", "source_pod", "source_namespace",
        ],
        "process_events": ["comm", "exe", "pod", "namespace"],
        "file_operations": ["file_path", "comm", "pod", "namespace"],
        "capability_checks": ["capability", "syscall", "comm", "pod", "namespace"],
        "oom_kills": ["comm", "pod", "namespace", "node"],
        "bind_events": ["bind_addr", "comm", "pod", "namespace"],
        "sni_events": ["sni_name", "dst_ip", "pod", "namespace", "comm"],
        "mount_events": ["source", "target", "fs_type", "comm", "pod", "namespace"],
        # L7 tables use src_*/dst_* column families instead of pod/namespace
        # (the generic L4 fallback). Without these explicit entries the
        # `query_all_events` search clause silently dropped L7 rows because
        # the unknown identifier raised a ClickHouse error that was caught
        # and translated to "table unavailable" → 0 results in the UI.
        "l7_http_flows": [
            "src_namespace", "src_workload", "src_pod",
            "dst_namespace", "dst_workload", "dst_pod",
            "http_method", "http_path", "http_host",
        ],
        "l7_grpc_flows": [
            "src_namespace", "src_workload", "src_pod",
            "dst_namespace", "dst_workload", "dst_pod",
            "grpc_service", "grpc_method",
        ],
        "l7_dns_flows": [
            "src_namespace", "src_workload", "src_pod",
            "query_name", "query_type",
        ],
    }

    async def query_all_events(
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
        Query all events with unified format
        
        Uses UNION ALL to merge results from multiple tables
        """
        try:
            # Filter tables
            tables_to_query = self.EVENT_TABLES.copy()
            if event_types:
                tables_to_query = {k: v for k, v in self.EVENT_TABLES.items() if k in event_types}
            
            if not tables_to_query:
                return ([], 0)
            
            # Column mapping per table family:
            # - L4 "source_*" tables: network_flows, dns_queries
            # - L4 generic tables: sni_events, process_events, etc.
            # - L7 tables: l7_http_flows, l7_grpc_flows, l7_dns_flows
            L7_TABLES = {"l7_http_flows", "l7_grpc_flows", "l7_dns_flows"}
            SOURCE_COL_TABLES = {"network_flows", "dns_queries"}

            def _col_map(tbl: str):
                if tbl in SOURCE_COL_TABLES:
                    return "source_namespace", "source_pod", "source_container"
                if tbl in L7_TABLES:
                    return "src_namespace", "src_pod", "''"
                return "namespace", "pod", "container"

            def _search_fields(tbl: str) -> List[str]:
                # Default fallback covers tables without a dedicated entry
                # (mostly the L7 ones, which this generic endpoint usually
                # doesn't surface but keep safe just in case).
                return self._SEARCH_FIELDS_BY_TABLE.get(tbl, ["pod", "namespace"])

            # Count total (skip missing tables gracefully)
            total = 0
            available_tables: Dict[str, str] = {}
            for event_type, table_name in tables_to_query.items():
                ns_col, _, _ = _col_map(table_name)
                where = self._build_where_clause(
                    cluster_id, analysis_id, namespace, start_time, end_time, ns_col,
                    search=search, search_fields=_search_fields(table_name),
                )
                try:
                    count_query = f"SELECT count() FROM {table_name} WHERE {where}"
                    result = self.client.execute(count_query)
                    total += result[0][0] if result else 0
                    available_tables[event_type] = table_name
                except Exception:
                    continue
            
            if not available_tables:
                return ([], 0)
            
            # Build UNION query only for tables that exist
            union_parts = []
            for event_type, table_name in available_tables.items():
                ns_col, pod_col, container_col = _col_map(table_name)
                
                where = self._build_where_clause(
                    cluster_id, analysis_id, namespace, start_time, end_time, ns_col,
                    search=search, search_fields=_search_fields(table_name),
                )
                
                union_parts.append(f"""
                SELECT 
                    timestamp,
                    '{event_type}' as event_type,
                    cluster_id,
                    analysis_id,
                    {ns_col} as namespace,
                    {pod_col} as pod,
                    {container_col} as container,
                    event_data_json as details
                FROM {table_name}
                WHERE {where}
                """)
            
            union_query = " UNION ALL ".join(union_parts)
            full_query = f"""
            SELECT * FROM ({union_query})
            ORDER BY timestamp DESC
            LIMIT {limit} OFFSET {offset}
            """
            
            result = self.client.execute(full_query, with_column_types=True)
            
            if not result:
                return ([], total)
            
            rows, columns = result
            column_names = [col[0] for col in columns]
            
            events = []
            for row in rows:
                event = {}
                for i, col_name in enumerate(column_names):
                    value = row[i]
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    event[col_name] = value
                events.append(event)
            
            return (events, total)
            
        except Exception as e:
            logger.error(f"Failed to query all events: {e}")
            raise
    
    async def query_event_histogram(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        bucket_count: int = 60
    ) -> Dict[str, Any]:
        """
        Time-bucketed event histogram for timeline visualization.
        
        Uses ClickHouse toStartOfInterval for efficient server-side aggregation
        across all event tables, returning counts per bucket per event type.
        """
        try:
            tables_to_query = self.EVENT_TABLES.copy()
            if event_types:
                tables_to_query = {k: v for k, v in self.EVENT_TABLES.items() if k in event_types}
            
            if not tables_to_query:
                return {"buckets": [], "time_range": {"start": None, "end": None}, "interval_seconds": 0, "total_events": 0}
            
            sensitive_caps = [
                'CAP_SYS_ADMIN', 'CAP_NET_ADMIN', 'CAP_NET_RAW',
                'CAP_SYS_PTRACE', 'CAP_SYS_MODULE', 'CAP_DAC_OVERRIDE',
                'CAP_SETUID', 'CAP_SETGID', 'CAP_CHOWN', 'CAP_FOWNER',
                'CAP_SYS_RAWIO', 'CAP_MKNOD', 'CAP_LINUX_IMMUTABLE'
            ]
            sensitive_caps_str = ", ".join([f"'{c}'" for c in sensitive_caps])
            cap_filter = f" AND (verdict = 'denied' OR verdict = '1' OR toString(verdict) = '1' OR capability IN ({sensitive_caps_str}))"
            
            # Step 1: Find global time range across all tables
            global_min = None
            global_max = None
            available_tables: Dict[str, str] = {}
            
            L7_TABLES_H = {"l7_http_flows", "l7_grpc_flows", "l7_dns_flows"}
            SOURCE_COL_TABLES_H = {"network_flows", "dns_queries"}

            for event_type, table_name in tables_to_query.items():
                ns_col = "source_namespace" if table_name in SOURCE_COL_TABLES_H else ("src_namespace" if table_name in L7_TABLES_H else "namespace")
                where = self._build_where_clause(
                    cluster_id, analysis_id,
                    start_time=start_time, end_time=end_time,
                    namespace_column=ns_col
                )
                if table_name == "capability_checks":
                    where += cap_filter
                
                try:
                    query = f"SELECT min(timestamp), max(timestamp), count() FROM {table_name} WHERE {where}"
                    result = self.client.execute(query)
                    
                    if result and result[0][2] > 0:
                        t_min, t_max = result[0][0], result[0][1]
                        if global_min is None or t_min < global_min:
                            global_min = t_min
                        if global_max is None or t_max > global_max:
                            global_max = t_max
                    available_tables[event_type] = table_name
                except Exception:
                    continue
            
            if global_min is None or global_max is None:
                return {"buckets": [], "time_range": {"start": None, "end": None}, "interval_seconds": 0, "total_events": 0}
            
            # Step 2: Compute interval
            total_seconds = (global_max - global_min).total_seconds()
            interval_seconds = max(1, math.ceil(total_seconds / bucket_count))
            
            # Step 3: Query histogram per table (only available tables)
            raw_buckets: Dict[str, Dict[str, int]] = {}
            total_events = 0
            
            for event_type, table_name in available_tables.items():
                ns_col = "source_namespace" if table_name in SOURCE_COL_TABLES_H else ("src_namespace" if table_name in L7_TABLES_H else "namespace")
                where = self._build_where_clause(
                    cluster_id, analysis_id,
                    start_time=start_time, end_time=end_time,
                    namespace_column=ns_col
                )
                if table_name == "capability_checks":
                    where += cap_filter
                
                try:
                    hist_query = f"""
                    SELECT 
                        toStartOfInterval(timestamp, INTERVAL {interval_seconds} SECOND) as bucket,
                        count() as cnt
                    FROM {table_name}
                    WHERE {where}
                    GROUP BY bucket
                    ORDER BY bucket
                    """
                    result = self.client.execute(hist_query)
                    
                    for row in result:
                        bucket_time = row[0].isoformat() if isinstance(row[0], datetime) else str(row[0])
                        count = row[1]
                        total_events += count
                        
                        if bucket_time not in raw_buckets:
                            raw_buckets[bucket_time] = {}
                        raw_buckets[bucket_time][event_type] = raw_buckets[bucket_time].get(event_type, 0) + count
                except Exception:
                    continue
            
            # Step 4-5: Build complete bucket series with empty fills.
            # Align to epoch-based boundaries matching ClickHouse toStartOfInterval:
            #   intDiv(toUnixTimestamp(ts), N) * N
            epoch = datetime(1970, 1, 1)
            if global_min.tzinfo:
                epoch = epoch.replace(tzinfo=global_min.tzinfo)
            
            global_min_unix = int((global_min - epoch).total_seconds())
            global_max_unix = int((global_max - epoch).total_seconds())
            aligned_start = epoch + timedelta(seconds=(global_min_unix // interval_seconds) * interval_seconds)
            aligned_end = epoch + timedelta(seconds=(global_max_unix // interval_seconds) * interval_seconds)
            
            buckets = []
            current = aligned_start
            while current <= aligned_end:
                bucket_key = current.isoformat()
                types = raw_buckets.get(bucket_key, {})
                bucket_total = sum(types.values())
                buckets.append({
                    "time": bucket_key,
                    "count": bucket_total,
                    "types": types
                })
                current = current + timedelta(seconds=interval_seconds)
            
            if len(buckets) > bucket_count + 2:
                buckets = buckets[:bucket_count + 2]
            
            return {
                "buckets": buckets,
                "time_range": {
                    "start": global_min.isoformat(),
                    "end": global_max.isoformat()
                },
                "interval_seconds": interval_seconds,
                "total_events": total_events
            }
            
        except Exception as e:
            logger.error(f"Failed to query event histogram: {e}")
            raise
    
    def _escape_ch(self, value: str) -> str:
        """Escape a string for safe inclusion inside a ClickHouse single-quoted
        literal. Backslashes MUST be doubled before single quotes are doubled —
        ClickHouse accepts both `''` and `\'` as escape sequences inside
        single-quoted strings, so a naive `.replace("'", "''")` leaves an
        attacker-controlled `\'` payload exploitable (the leading backslash
        consumes the first quote and the trailing one closes the literal).
        Order matters: escape `\` first, then `'`.
        """
        return str(value).replace("\\", "\\\\").replace("'", "''")

    def _build_l7_base_where(
        self,
        cluster_id=None,
        analysis_id=None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> str:
        conditions = ["1=1"]
        if cluster_id is not None and str(cluster_id).strip() not in ("", "0"):
            conditions.append(f"cluster_id = '{self._escape_ch(str(cluster_id))}'")
        if analysis_id is not None:
            aid = self._escape_ch(str(analysis_id))
            conditions.append(f"(analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')")
        if namespace:
            ns = self._escape_ch(namespace)
            conditions.append(f"(src_namespace = '{ns}' OR dst_namespace = '{ns}')")
        if start_time:
            conditions.append(
                f"timestamp >= parseDateTimeBestEffort('{self._escape_ch(start_time)}')"
            )
        if end_time:
            conditions.append(
                f"timestamp <= parseDateTimeBestEffort('{self._escape_ch(end_time)}')"
            )
        return " AND ".join(conditions)

    async def query_l7_http_flows(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        status_code: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        where = self._build_l7_base_where(
            cluster_id, analysis_id, namespace, start_time, end_time
        )
        if method:
            where += f" AND http_method = '{self._escape_ch(method)}'"
        if path:
            where += f" AND http_path = '{self._escape_ch(path)}'"
        if status_code is not None:
            where += f" AND http_status_code = {int(status_code)}"
        table = "l7_http_flows"
        try:
            count_query = f"SELECT count() FROM {table} WHERE {where}"
            total = self.client.execute(count_query)[0][0]
            data_query = f"""
            SELECT * FROM {table} WHERE {where}
            ORDER BY timestamp DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
            """
            result = self.client.execute(data_query, with_column_types=True)
            if not result:
                return ([], total)
            rows, columns = result
            column_names = [col[0] for col in columns]
            events = []
            for row in rows:
                event = {}
                for i, col_name in enumerate(column_names):
                    value = row[i]
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    event[col_name] = value
                events.append(event)
            return (events, total)
        except Exception as e:
            logger.warning(f"L7 HTTP flows query failed (table may not exist): {e}")
            return ([], 0)

    async def query_l7_grpc_flows(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        grpc_service: Optional[str] = None,
        grpc_method: Optional[str] = None,
        grpc_status_code: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        where = self._build_l7_base_where(
            cluster_id, analysis_id, namespace, start_time, end_time
        )
        if grpc_service:
            where += f" AND grpc_service = '{self._escape_ch(grpc_service)}'"
        if grpc_method:
            where += f" AND grpc_method = '{self._escape_ch(grpc_method)}'"
        if grpc_status_code is not None:
            where += f" AND grpc_status_code = {int(grpc_status_code)}"
        table = "l7_grpc_flows"
        try:
            count_query = f"SELECT count() FROM {table} WHERE {where}"
            total = self.client.execute(count_query)[0][0]
            data_query = f"""
            SELECT * FROM {table} WHERE {where}
            ORDER BY timestamp DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
            """
            result = self.client.execute(data_query, with_column_types=True)
            if not result:
                return ([], total)
            rows, columns = result
            column_names = [col[0] for col in columns]
            events = []
            for row in rows:
                event = {}
                for i, col_name in enumerate(column_names):
                    value = row[i]
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    event[col_name] = value
                events.append(event)
            return (events, total)
        except Exception as e:
            logger.warning(f"L7 gRPC flows query failed (table may not exist): {e}")
            return ([], 0)

    async def query_l7_dns_flows(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        query_name: Optional[str] = None,
        query_type: Optional[str] = None,
        response_code: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        where = self._build_l7_base_where(
            cluster_id, analysis_id, namespace, start_time, end_time
        )
        if query_name:
            where += f" AND query_name = '{self._escape_ch(query_name)}'"
        if query_type:
            where += f" AND query_type = '{self._escape_ch(query_type)}'"
        if response_code is not None:
            where += f" AND response_code = {int(response_code)}"
        table = "l7_dns_flows"
        try:
            count_query = f"SELECT count() FROM {table} WHERE {where}"
            total = self.client.execute(count_query)[0][0]
            data_query = f"""
            SELECT * FROM {table} WHERE {where}
            ORDER BY timestamp DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
            """
            result = self.client.execute(data_query, with_column_types=True)
            if not result:
                return ([], total)
            rows, columns = result
            column_names = [col[0] for col in columns]
            events = []
            for row in rows:
                event = {}
                for i, col_name in enumerate(column_names):
                    value = row[i]
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    event[col_name] = value
                events.append(event)
            return (events, total)
        except Exception as e:
            logger.warning(f"L7 DNS flows query failed (table may not exist): {e}")
            return ([], 0)

    async def query_l7_events_stats(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        base = self._build_l7_base_where(
            cluster_id, analysis_id, namespace, start_time, end_time
        )
        http_where = base
        grpc_where = base
        dns_where = base

        empty_row = (0, 0, 0.0)
        try:
            http_row = self.client.execute(
                f"""
                SELECT
                    count() AS total,
                    countIf(http_status_code >= 400) AS errors,
                    if(count() > 0, avg(latency_ms), 0) AS avg_latency
                FROM l7_http_flows
                WHERE {http_where}
                """
            )[0]
        except Exception as e:
            logger.warning(f"L7 HTTP stats query failed: {e}")
            http_row = empty_row

        try:
            grpc_row = self.client.execute(
                f"""
                SELECT
                    count() AS total,
                    countIf(grpc_status_code != 0) AS errors,
                    if(count() > 0, avg(latency_ms), 0) AS avg_latency
                FROM l7_grpc_flows
                WHERE {grpc_where}
                """
            )[0]
        except Exception as e:
            logger.warning(f"L7 gRPC stats query failed: {e}")
            grpc_row = empty_row

        try:
            dns_row = self.client.execute(
                f"""
                SELECT
                    count() AS total,
                    countIf(response_code != 0) AS errors,
                    if(count() > 0, avg(latency_ms), 0) AS avg_latency
                FROM l7_dns_flows
                WHERE {dns_where}
                """
            )[0]
        except Exception as e:
            logger.warning(f"L7 DNS stats query failed: {e}")
            dns_row = empty_row

        def pack(row) -> Dict[str, Any]:
            total = int(row[0] or 0)
            err = int(row[1] or 0)
            lat = row[2]
            try:
                avg_lat = float(lat) if lat is not None else 0.0
                import math
                if math.isnan(avg_lat) or math.isinf(avg_lat):
                    avg_lat = 0.0
            except (TypeError, ValueError):
                avg_lat = 0.0
            return {
                "total_requests": total,
                "error_count": err,
                "avg_latency_ms": round(avg_lat, 4),
                "error_rate_percent": round((err / total) * 100.0, 4) if total > 0 else 0.0,
            }

        http_s = pack(http_row)
        grpc_s = pack(grpc_row)
        dns_s = pack(dns_row)

        total_req = http_s["total_requests"] + grpc_s["total_requests"] + dns_s["total_requests"]
        total_err = http_s["error_count"] + grpc_s["error_count"] + dns_s["error_count"]
        combined_avg = 0.0
        if total_req > 0:
            weighted = (
                http_s["avg_latency_ms"] * http_s["total_requests"]
                + grpc_s["avg_latency_ms"] * grpc_s["total_requests"]
                + dns_s["avg_latency_ms"] * dns_s["total_requests"]
            )
            combined_avg = round(weighted / total_req, 4)

        return {
            "cluster_id": str(cluster_id) if cluster_id else None,
            "analysis_id": str(analysis_id) if analysis_id is not None else None,
            "namespace": namespace,
            "http": http_s,
            "grpc": grpc_s,
            "dns": dns_s,
            "total_requests": total_req,
            "total_errors": total_err,
            "error_rate_percent": round((total_err / total_req) * 100.0, 4) if total_req > 0 else 0.0,
            "avg_latency_ms": combined_avg,
        }

    async def query_l7_http_histogram(
        self,
        cluster_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        bucket_count: int = 60,
    ) -> Dict[str, Any]:
        """
        Time-based HTTP histogram aligned with l7_http_flows_5min_mv (5-minute buckets).

        Reads from l7_http_flows_5min_mv when no namespace filter (MV has no namespace
        columns). With namespace, rolls up l7_http_flows with toStartOfFiveMinutes.
        """
        use_mv = not namespace

        if use_mv:
            conditions = ["1=1"]
            if cluster_id is not None and str(cluster_id).strip() not in ("", "0"):
                conditions.append(f"cluster_id = '{self._escape_ch(str(cluster_id))}'")
            if analysis_id is not None:
                aid = self._escape_ch(str(analysis_id))
                conditions.append(f"(analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')")
            if start_time:
                conditions.append(
                    f"timestamp_5min >= toStartOfFiveMinutes(parseDateTimeBestEffort('{self._escape_ch(start_time)}'))"
                )
            if end_time:
                conditions.append(
                    f"timestamp_5min <= toStartOfFiveMinutes(parseDateTimeBestEffort('{self._escape_ch(end_time)}'))"
                )
            where_mv = " AND ".join(conditions)

            bounds = self.client.execute(
                f"""
                SELECT min(timestamp_5min), max(timestamp_5min), sum(request_count)
                FROM l7_http_flows_5min_mv
                WHERE {where_mv}
                """
            )
            if not bounds or not bounds[0][0] or (bounds[0][2] or 0) == 0:
                return {
                    "buckets": [],
                    "time_range": {"start": None, "end": None},
                    "interval_seconds": 300,
                    "total_requests": 0,
                    "source": "l7_http_flows_5min_mv",
                }

            global_min, global_max = bounds[0][0], bounds[0][1]
            total_requests = int(bounds[0][2] or 0)
            total_seconds = (global_max - global_min).total_seconds()
            interval_seconds = max(300, math.ceil(total_seconds / max(1, bucket_count)))
            interval_seconds = (interval_seconds // 300) * 300 or 300

            hist_query = f"""
            SELECT
                toStartOfInterval(timestamp_5min, INTERVAL {interval_seconds} SECOND) AS bucket,
                sum(request_count) AS cnt,
                sum(error_count) AS err_cnt,
                if(sum(request_count) > 0, sum(total_latency_ms) / sum(request_count), 0) AS avg_lat
            FROM l7_http_flows_5min_mv
            WHERE {where_mv}
            GROUP BY bucket
            ORDER BY bucket
            """
            result = self.client.execute(hist_query)
            buckets = []
            for row in result:
                bt = row[0]
                buckets.append(
                    {
                        "time": bt.isoformat() if isinstance(bt, datetime) else str(bt),
                        "request_count": int(row[1] or 0),
                        "error_count": int(row[2] or 0),
                        "avg_latency_ms": round(float(row[3] or 0), 4),
                    }
                )

            return {
                "buckets": buckets,
                "time_range": {
                    "start": global_min.isoformat(),
                    "end": global_max.isoformat(),
                },
                "interval_seconds": interval_seconds,
                "total_requests": total_requests,
                "namespace": None,
                "source": "l7_http_flows_5min_mv",
            }

        where = self._build_l7_base_where(
            cluster_id, analysis_id, namespace, start_time, end_time
        )
        bounds = self.client.execute(
            f"""
            SELECT min(timestamp), max(timestamp), count()
            FROM l7_http_flows
            WHERE {where}
            """
        )
        if not bounds or not bounds[0][0] or (bounds[0][2] or 0) == 0:
            return {
                "buckets": [],
                "time_range": {"start": None, "end": None},
                "interval_seconds": 300,
                "total_requests": 0,
                "source": "l7_http_flows",
            }

        global_min, global_max = bounds[0][0], bounds[0][1]
        total_requests = int(bounds[0][2] or 0)
        total_seconds = (global_max - global_min).total_seconds()
        interval_seconds = max(300, math.ceil(total_seconds / max(1, bucket_count)))
        interval_seconds = (interval_seconds // 300) * 300 or 300

        hist_query = f"""
        SELECT
            toStartOfInterval(toStartOfFiveMinutes(timestamp), INTERVAL {interval_seconds} SECOND) AS bucket,
            count() AS cnt,
            countIf(http_status_code >= 400) AS err_cnt,
            avg(latency_ms) AS avg_lat
        FROM l7_http_flows
        WHERE {where}
        GROUP BY bucket
        ORDER BY bucket
        """
        result = self.client.execute(hist_query)
        buckets = []
        for row in result:
            bt = row[0]
            buckets.append(
                {
                    "time": bt.isoformat() if isinstance(bt, datetime) else str(bt),
                    "request_count": int(row[1] or 0),
                    "error_count": int(row[2] or 0),
                    "avg_latency_ms": round(float(row[3] or 0), 4),
                }
            )

        return {
            "buckets": buckets,
            "time_range": {
                "start": global_min.isoformat(),
                "end": global_max.isoformat(),
            },
            "interval_seconds": interval_seconds,
            "total_requests": total_requests,
            "namespace": namespace,
            "source": "l7_http_flows",
        }

    def health_check(self) -> Dict[str, Any]:
        """Check database health"""
        try:
            start = datetime.now(timezone.utc)
            self.client.execute("SELECT 1")
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            return {
                "healthy": True,
                "latency_ms": round(latency_ms, 2),
                "database": settings.clickhouse_database
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    async def delete_analysis_data(
        self,
        analysis_id: int,
        wait_for_completion: bool = True,
        timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Delete all events for an analysis from all tables
        
        Args:
            analysis_id: Analysis ID to delete data for
            wait_for_completion: If True, wait for mutations to complete
            timeout_seconds: Max time to wait for mutations
            
        Returns:
            Deletion summary with counts and timing
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        # All tables that might contain analysis-specific data.
        # NOTE: tcp_lifecycle included even though no data is written to it currently
        # — this ensures complete cleanup if data is ever written in the future.
        # NOTE: APM RED MVs (Phase 2) point at separate destination tables, not
        # the *_mv view names. We delete from the destination table directly so
        # mutations actually drop rows; deleting from a MV is a no-op.
        tables = list(self.EVENT_TABLES.values()) + [
            'workload_metadata',
            'communication_edges',
            'tcp_lifecycle',
            'change_events',
            'l7_http_flows_5min_mv',
            # APM RED MVs (Phase 2) — destination tables for AggregatingMergeTree
            'l7_http_red_svc_5min',
            'l7_http_red_ops_5min',
            'l7_grpc_red_svc_5min',
            'l7_grpc_red_ops_5min',
            'l7_dns_red_svc_5min',
        ]
        
        # Step 1: Get counts before deletion
        # Multi-cluster support: match both single-cluster (analysis_id = '123') 
        # and multi-cluster (analysis_id LIKE '123-%') formats
        counts_before = {}
        for table in tables:
            try:
                result = self.client.execute(
                    f"SELECT count() as cnt FROM {table} WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                )
                counts_before[table] = result[0][0] if result else 0
            except Exception:
                counts_before[table] = 0
        
        total_to_delete = sum(counts_before.values())
        logger.info(f"Found {total_to_delete} records to delete for analysis_id={analysis_id}")
        
        if total_to_delete == 0:
            return {
                "tables": counts_before,
                "total_deleted": 0,
                "completed": True,
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        
        # Step 2: Submit delete mutations
        # Multi-cluster support: delete both single and multi-cluster analysis_id formats
        for table in tables:
            if counts_before.get(table, 0) == 0:
                continue
            try:
                self.client.execute(
                    f"ALTER TABLE {table} DELETE WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                )
                logger.debug(f"Delete mutation submitted for {table}")
            except Exception as e:
                logger.warning(f"Failed to delete from {table}: {e}")
        
        # Step 3: Wait for mutations if requested
        completed = True
        if wait_for_completion:
            deadline = time.time() + timeout_seconds
            
            while time.time() < deadline:
                try:
                    pending = self.client.execute("""
                        SELECT table, mutation_id, is_done
                        FROM system.mutations
                        WHERE database = 'flowfish' AND is_done = 0
                          AND create_time > now() - INTERVAL 5 MINUTE
                    """)
                    
                    pending_tables = {r[0] for r in pending} if pending else set()
                    our_pending = set(tables) & pending_tables
                    
                    if not our_pending:
                        break
                    
                    await asyncio.sleep(0.5)
                except Exception:
                    await asyncio.sleep(1)
            else:
                completed = False
        
        # Step 4: Get counts after deletion (verify with same multi-cluster pattern)
        counts_after = {}
        for table in tables:
            try:
                result = self.client.execute(
                    f"SELECT count() as cnt FROM {table} WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'"
                )
                counts_after[table] = result[0][0] if result else 0
            except Exception:
                counts_after[table] = 0
        
        deleted_counts = {
            table: counts_before.get(table, 0) - counts_after.get(table, 0)
            for table in tables
        }
        total_deleted = sum(deleted_counts.values())
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Deletion completed: analysis_id={analysis_id}, total_deleted={total_deleted}, duration_ms={duration_ms}")
        
        return {
            "tables": deleted_counts,
            "total_deleted": total_deleted,
            "completed": completed,
            "duration_ms": duration_ms
        }
    
    # ============================================================
    # L7 Distributed Tracing API (Faz 3.1)
    # Reads from l7_http_flows + l7_grpc_flows. DNS spans are excluded
    # because the DNS protocol cannot propagate W3C traceparent headers.
    # All methods raise on database error; callers should propagate to
    # the HTTP layer (do not silently return empty lists).
    # ============================================================
    def get_trace_spans(
        self,
        trace_id: str,
        analysis_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all spans (HTTP + gRPC) for a given trace_id, ordered by timestamp.

        When `analysis_id` is supplied the result is restricted to that
        analysis (and its multi-cluster sub-analyses via the `<aid>-*` prefix).
        When omitted, the lookup spans every analysis — used for the Trace
        Explorer deep-link where the operator only has the trace_id (the
        16-byte hex string is unique per W3C spec, so collisions across
        analyses are not a concern).

        Phase 4: matches BOTH `trace_id` and `virtual_trace_id`. The two
        columns share the same hex width and are mutually exclusive per
        row (see virtual_trace_correlator.correlate — events with a real
        trace_id are skipped). The `virtual_trace_id != ''` guard
        prevents matching unstamped legacy rows. The bloom_filter index
        added by clickhouse_007_add_l7_pid.sql accelerates the OR clause;
        when the column is missing on legacy schemas the writer leaves
        virtual_trace_id at default '' and the OR collapses to the
        original trace_id-only behaviour with no performance penalty.
        """
        tid = _validate_trace_id(trace_id)
        if analysis_id is not None and str(analysis_id):
            aid = self._escape_ch(str(analysis_id))
            scope = f"AND (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')"
        else:
            scope = ""
        # `virtual_trace_id` is added defensively as a column reference: on
        # clusters where clickhouse_007 hasn't been applied yet the column
        # doesn't exist and the query throws "Unknown column virtual_trace_id".
        # We catch that and fall back to a query without the OR.
        primary_query = f"""
        SELECT trace_id, span_id, parent_span_id, span_name, span_kind,
               timestamp, analysis_id, cluster_id, cluster_name,
               src_namespace, src_workload, src_pod, src_ip, src_port,
               dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
               virtual_trace_id,
               'HTTP' AS protocol,
               http_method AS method, http_path AS path, '' AS grpc_service,
               toInt32(http_status_code) AS status_code, latency_ms
        FROM l7_http_flows
        WHERE (trace_id = '{tid}' OR (virtual_trace_id = '{tid}' AND virtual_trace_id != ''))
              {scope}
        UNION ALL
        SELECT trace_id, span_id, parent_span_id, span_name, span_kind,
               timestamp, analysis_id, cluster_id, cluster_name,
               src_namespace, src_workload, src_pod, src_ip, src_port,
               dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
               virtual_trace_id,
               'GRPC' AS protocol,
               grpc_method AS method, grpc_service AS path, grpc_service,
               grpc_status_code AS status_code, latency_ms
        FROM l7_grpc_flows
        WHERE (trace_id = '{tid}' OR (virtual_trace_id = '{tid}' AND virtual_trace_id != ''))
              {scope}
        ORDER BY timestamp ASC
        """
        legacy_query = f"""
        SELECT trace_id, span_id, parent_span_id, span_name, span_kind,
               timestamp, analysis_id, cluster_id, cluster_name,
               src_namespace, src_workload, src_pod, src_ip, src_port,
               dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
               '' AS virtual_trace_id,
               'HTTP' AS protocol,
               http_method AS method, http_path AS path, '' AS grpc_service,
               toInt32(http_status_code) AS status_code, latency_ms
        FROM l7_http_flows
        WHERE trace_id = '{tid}' {scope}
        UNION ALL
        SELECT trace_id, span_id, parent_span_id, span_name, span_kind,
               timestamp, analysis_id, cluster_id, cluster_name,
               src_namespace, src_workload, src_pod, src_ip, src_port,
               dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
               '' AS virtual_trace_id,
               'GRPC' AS protocol,
               grpc_method AS method, grpc_service AS path, grpc_service,
               grpc_status_code AS status_code, latency_ms
        FROM l7_grpc_flows
        WHERE trace_id = '{tid}' {scope}
        ORDER BY timestamp ASC
        """
        try:
            result = self.client.execute(primary_query, with_column_types=True)
        except Exception as e:
            err_str = str(e)
            if (
                "Unknown column" in err_str
                or "doesn't have column" in err_str
                or "No such column" in err_str
            ) and "virtual_trace_id" in err_str:
                logger.warning(
                    "virtual_trace_id column missing — falling back to legacy trace_id-only query (apply clickhouse_007 to enable Phase 4)"
                )
                result = self.client.execute(legacy_query, with_column_types=True)
            else:
                raise
        rows, cols = result if isinstance(result, tuple) else (result, [])
        col_names = [c[0] for c in cols]
        spans = [dict(zip(col_names, row)) for row in rows]
        for s in spans:
            ts = s.get("timestamp")
            if hasattr(ts, "isoformat"):
                s["timestamp"] = ts.isoformat()
        return spans

    def get_recent_traces(
        self,
        analysis_id: str,
        workload: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        # Phase 1A filters (optional, backward-compat). Each filter narrows
        # the returned trace set further; passing none reproduces the
        # legacy behaviour exactly.
        cluster_id: Optional[str] = None,
        src_workload: Optional[str] = None,
        dst_workload: Optional[str] = None,
        operation: Optional[str] = None,
        min_latency_ms: Optional[float] = None,
        # Plan v3 Akış B m.3 (B1.1, B1.2): trace-level upper bound on the
        # aggregated `max(latency_ms)`. Used by the Trace Explorer latency
        # histogram bucket click — combined with `min_latency_ms` it lets
        # operators isolate traces whose worst span falls inside a bucket
        # (e.g. 100-500ms tail).
        max_latency_ms: Optional[float] = None,
        error_only: bool = False,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        # Plan v3 Akış B m.4: free-form search across operation, src/dst
        # workload, namespace and trace_id. Mapped to ClickHouse via
        # `_build_search_condition` which already escapes single quotes
        # and short-circuits on empty / oversized inputs.
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List recent traces (grouped by trace_id) for an analysis, optionally filtered by workload.

        Returns {"traces": [...], "total": N}. Each trace contains start/end time,
        span count, error count, max latency, and the set of clusters involved.

        Filter semantics:
        - workload: matches src_workload OR dst_workload (legacy combined filter).
        - src_workload / dst_workload: column-specific filters (apply on top of `workload`).
        - operation: matches http_path on HTTP rows OR grpc_method on gRPC rows.
        - min_latency_ms: keeps only spans with latency >= threshold (any span in a
          trace passing the threshold keeps the whole trace).
        - max_latency_ms: trace-level upper bound — keeps only traces whose
          aggregated max(latency_ms) < threshold (HAVING clause). The bucket
          click on the latency histogram passes both min and max to scope a
          trace to a specific log-scale bucket (Plan v3 Akış B m.3).
        - error_only: keeps only HTTP 4xx/5xx OR gRPC non-zero status spans.
        - start_time / end_time: ISO-8601, applied to span timestamps.
        - q: free-form search; matches operation, workloads, namespace, trace_id.
        """
        aid = self._escape_ch(str(analysis_id))

        # Shared filters that apply equally to both HTTP and gRPC rows.
        shared_filters: List[str] = []
        if cluster_id:
            # cluster_id is a stable identifier (numeric string from the
            # clusters table). Escape defensively in case a multi-cluster
            # rename ever lets non-numeric values through.
            shared_filters.append(
                f"cluster_id = '{self._escape_ch(str(cluster_id))}'"
            )
        if workload:
            wl = self._escape_ch(str(workload))
            shared_filters.append(f"(src_workload = '{wl}' OR dst_workload = '{wl}')")
        if src_workload:
            shared_filters.append(f"src_workload = '{self._escape_ch(str(src_workload))}'")
        if dst_workload:
            shared_filters.append(f"dst_workload = '{self._escape_ch(str(dst_workload))}'")
        if min_latency_ms is not None:
            shared_filters.append(f"latency_ms >= {float(min_latency_ms)}")
        if start_time:
            shared_filters.append(
                f"timestamp >= parseDateTimeBestEffort('{self._escape_ch(start_time)}')"
            )
        if end_time:
            shared_filters.append(
                f"timestamp <= parseDateTimeBestEffort('{self._escape_ch(end_time)}')"
            )
        shared_clause = (" AND " + " AND ".join(shared_filters)) if shared_filters else ""

        # Protocol-specific filters: `operation` and `error_only` map to
        # different columns for HTTP vs gRPC. We build separate clauses to
        # avoid impossible cross-column constraints.
        http_extra: List[str] = []
        grpc_extra: List[str] = []
        if operation:
            op_esc = self._escape_ch(str(operation))
            http_extra.append(f"http_path = '{op_esc}'")
            grpc_extra.append(f"grpc_method = '{op_esc}'")
        if error_only:
            http_extra.append("http_status_code >= 400")
            grpc_extra.append("grpc_status_code != 0")

        # Plan v3 Akış B m.4 (B1.3): free-form search. We extend the
        # existing TABLE_SEARCH_FIELDS list with `trace_id` so operators
        # can paste a short hex prefix and still get a hit. Empty / blank
        # `q` is filtered out upstream (`min_length=1`) but we keep the
        # defensive `if q` guard here.
        if q:
            http_search_cond = self._build_search_condition(
                q, list(self.TABLE_SEARCH_FIELDS["l7_http_flows"]) + ["trace_id"]
            )
            grpc_search_cond = self._build_search_condition(
                q, list(self.TABLE_SEARCH_FIELDS["l7_grpc_flows"]) + ["trace_id"]
            )
            if http_search_cond:
                http_extra.append(http_search_cond)
            if grpc_search_cond:
                grpc_extra.append(grpc_search_cond)

        http_clause = (" AND " + " AND ".join(http_extra)) if http_extra else ""
        grpc_clause = (" AND " + " AND ".join(grpc_extra)) if grpc_extra else ""

        # Trace-level HAVING — applies to the aggregated max(latency_ms),
        # not individual spans. Only used when the histogram bucket click
        # provides an upper bound (Plan v3 Akış B m.3 / B1.2).
        trace_having_clauses: List[str] = []
        if max_latency_ms is not None:
            trace_having_clauses.append(f"max_lat < {float(max_latency_ms)}")
        having_clause = (
            " HAVING " + " AND ".join(trace_having_clauses)
            if trace_having_clauses
            else ""
        )

        # Per-table aggregation, then outer aggregation merges HTTP + gRPC.
        # error_count semantics: HTTP -> status>=400; gRPC -> grpc_status_code != 0.
        # NOTE — Phase 4 known gap: this query intentionally returns ONLY rows
        # with a non-empty W3C `trace_id`. PID-correlated virtual traces
        # (rows where `trace_id = ''` but `virtual_trace_id != ''`) are NOT
        # surfaced in the Recent Traces list because mixing the two without
        # a UI badge would confuse operators. Virtual traces are still:
        # (1) discoverable via the Related Traces tab on any anchor trace,
        # (2) addressable directly via the Trace Explorer search box (paste
        # the virtual_trace_id; get_trace_spans matches both columns), and
        # (3) tracked in the L7_DISTRIBUTED_TRACING_MIGRATION runbook.
        # Surfacing them in this list will require an `include_virtual` opt-in
        # plus an `is_virtual` badge column on the frontend.
        inner = f"""
        SELECT trace_id, min(timestamp) AS ts, max(timestamp) AS ts2,
               count() AS cnt, countIf(http_status_code >= 400) AS errs,
               max(latency_ms) AS max_lat,
               groupUniqArray(cluster_id) AS clusters_arr
        FROM l7_http_flows
        WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
          AND trace_id != ''{shared_clause}{http_clause}
        GROUP BY trace_id
        UNION ALL
        SELECT trace_id, min(timestamp), max(timestamp),
               count(), countIf(grpc_status_code != 0),
               max(latency_ms),
               groupUniqArray(cluster_id)
        FROM l7_grpc_flows
        WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
          AND trace_id != ''{shared_clause}{grpc_clause}
        GROUP BY trace_id
        """
        query = f"""
        SELECT trace_id, min(ts) AS start_time, max(ts2) AS end_time,
               sum(cnt) AS span_count, sum(errs) AS error_count,
               max(max_lat) AS max_latency_ms,
               groupUniqArrayArray(clusters_arr) AS clusters
        FROM ({inner})
        GROUP BY trace_id{having_clause}
        ORDER BY start_time DESC
        LIMIT {int(limit)} OFFSET {int(offset)}
        """
        rows = self.client.execute(query)

        # Total distinct traces (HTTP + gRPC combined). Separate query because
        # the LIMIT/OFFSET above doesn't allow direct count.
        # Plan v3 Akış B m.3 (B1.2 fix): when `max_latency_ms` is in play
        # we can't just count the union — we have to apply the same
        # trace-level HAVING. The two-level subquery materialises the
        # `max(latency_ms)` per trace_id and counts rows that pass.
        if having_clause:
            total_query = f"""
            SELECT count() FROM (
                SELECT trace_id, max(max_lat) AS max_lat FROM (
                    SELECT trace_id, max(latency_ms) AS max_lat FROM l7_http_flows
                    WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
                      AND trace_id != ''{shared_clause}{http_clause}
                    GROUP BY trace_id
                    UNION ALL
                    SELECT trace_id, max(latency_ms) AS max_lat FROM l7_grpc_flows
                    WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
                      AND trace_id != ''{shared_clause}{grpc_clause}
                    GROUP BY trace_id
                )
                GROUP BY trace_id{having_clause}
            )
            """
        else:
            total_query = f"""
            SELECT uniqExact(trace_id) FROM (
                SELECT trace_id FROM l7_http_flows
                WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
                  AND trace_id != ''{shared_clause}{http_clause}
                UNION ALL
                SELECT trace_id FROM l7_grpc_flows
                WHERE (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')
                  AND trace_id != ''{shared_clause}{grpc_clause}
            )
            """
        total_rows = self.client.execute(total_query)
        total = int(total_rows[0][0]) if total_rows else 0

        traces = []
        for row in rows:
            trace_id, start_time, end_time, span_count, error_count, max_latency, clusters = row
            duration_ms = 0.0
            if start_time and end_time:
                try:
                    duration_ms = (end_time - start_time).total_seconds() * 1000.0
                except (TypeError, AttributeError):
                    duration_ms = 0.0
            traces.append({
                "trace_id": trace_id,
                "start_time": start_time.isoformat() if hasattr(start_time, "isoformat") else start_time,
                "end_time": end_time.isoformat() if hasattr(end_time, "isoformat") else end_time,
                "span_count": int(span_count or 0),
                "error_count": int(error_count or 0),
                "max_latency_ms": float(max_latency or 0.0),
                "duration_ms": duration_ms,
                "clusters": [str(c) for c in (clusters or []) if c],
            })

        return {"traces": traces, "total": total, "limit": int(limit), "offset": int(offset)}

    def get_trace_summary(
        self,
        trace_id: str,
        analysis_id: Optional[str] = None,
        spans: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Return summary statistics for a single trace.

        If `spans` is supplied (as in the /l7/traces/{trace_id} endpoint that
        also returns the spans themselves) we skip the second ClickHouse round
        trip and compute the summary in-memory. Backward compatible: when
        `spans` is None we fall back to fetching them. `analysis_id` accepts
        None for the Trace Explorer deep-link path (looks up across
        analyses); see get_trace_spans() for the scoping rules.
        """
        if spans is None:
            spans = self.get_trace_spans(trace_id, analysis_id)
        if not spans:
            return {
                "trace_id": trace_id,
                "span_count": 0,
                "clusters": [],
                "services": [],
                "error_count": 0,
                "duration_ms": 0.0,
            }
        clusters = sorted({s.get("cluster_id") for s in spans if s.get("cluster_id")})
        services = sorted({
            s.get("dst_workload") for s in spans if s.get("dst_workload")
        } | {
            s.get("src_workload") for s in spans if s.get("src_workload")
        })
        errors = 0
        for s in spans:
            sc = s.get("status_code") or 0
            proto = s.get("protocol")
            if proto == "HTTP" and sc >= 400:
                errors += 1
            elif proto == "GRPC" and sc != 0:
                errors += 1
        timestamps = [s.get("timestamp") for s in spans if s.get("timestamp")]
        duration_ms = 0.0
        if len(timestamps) >= 2:
            try:
                ts_dt = [datetime.fromisoformat(t) if isinstance(t, str) else t for t in timestamps]
                duration_ms = (max(ts_dt) - min(ts_dt)).total_seconds() * 1000.0
            except (ValueError, TypeError):
                duration_ms = 0.0
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "clusters": clusters,
            "services": services,
            "error_count": errors,
            "duration_ms": duration_ms,
        }

    # ============================================================
    # APM RED Metrics API (Phase 2)
    # ============================================================
    # Reads from the AggregatingMergeTree RED MVs introduced by
    # `clickhouse_005_add_apm_red_mvs.sql`. All four endpoints share the
    # same scoping rules: analysis_id is matched as both the exact ID and
    # the multi-cluster sub-analysis prefix `<aid>-*`. cluster_id is an
    # optional narrowing filter.
    #
    # Latency percentiles (p50/p95/p99) are computed via
    # `quantileTDigestMerge`, which is mathematically sound across any
    # number of 5-minute states (TDigests merge associatively). Rate and
    # error counts use `sumMerge` for the same reason.
    #
    # Protocol handling: by default HTTP and gRPC are unioned, since most
    # services have a mix; DNS is excluded from the default view because
    # its latency characteristics differ in scale (DNS p99 in the
    # sub-millisecond range vs. HTTP p99 in the hundreds-of-ms range)
    # and would skew tail-latency aggregates. DNS gets its own future
    # endpoint when needed.
    # ============================================================

    def _apm_scope(self, analysis_id: str, cluster_id: Optional[str] = None) -> str:
        """Standard scoping clause used by every APM query. analysis_id is
        always required; cluster_id narrows further. Multi-cluster sub-IDs
        (`44-15`) are matched via the `<aid>-*` LIKE pattern.
        """
        aid = self._escape_ch(str(analysis_id))
        clauses = [f"(analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')"]
        if cluster_id is not None and str(cluster_id).strip() not in ("", "0"):
            clauses.append(f"cluster_id = '{self._escape_ch(str(cluster_id))}'")
        return " AND ".join(clauses)

    def get_apm_services(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        sort_by: str = "rate",
        limit: int = 100,
        offset: int = 0,
        # Plan v3 Akış B m.4 — free-form search across dst_workload and
        # dst_namespace so the Trace Explorer "Services" tab stays in sync
        # with the page-level search box. `_build_search_condition`
        # already escapes single quotes & backslashes.
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Service-level RED tablosu for APM Services List page.

        Combines HTTP and gRPC RED MVs into a single per-(cluster,
        dst_workload, dst_namespace) row. p50/p95/p99 are weighted by
        protocol via TDigest merge; rate and errors are simple sums.
        """
        # NOTE: `avg` was previously in this whitelist but the SELECT clause
        # below does not project an `avg` column (only rate/errors/p50/p95/p99
        # are computed from the AggregatingMergeTree state). ORDER BY avg
        # would therefore raise "Unknown identifier" -> HTTP 500. Removing
        # `avg` makes the API contract match what the SQL actually supports,
        # so an `avg` value coming through (e.g. URL hand-edit) silently
        # falls back to `rate` instead of crashing. Frontend dropdown does
        # not expose `avg`; backend Pydantic regex was also tightened.
        if sort_by not in {"rate", "errors", "p50", "p95", "p99"}:
            sort_by = "rate"
        scope = self._apm_scope(analysis_id, cluster_id)
        ns_filter = ""
        if namespace:
            ns_filter = f" AND dst_namespace = '{self._escape_ch(namespace)}'"

        # `q` is applied at the inner UNION level (per-table scope) and at
        # the outer aggregated level (post-union) — the inner scope keeps
        # the row count low; the outer scope makes the filter visible to
        # operators inspecting the SQL plan.
        q_scope = ""
        if q:
            cond = self._build_search_condition(q, ["dst_workload", "dst_namespace"])
            if cond:
                q_scope = f" AND {cond}"

        query = f"""
        WITH unioned AS (
            SELECT cluster_id, dst_workload, dst_namespace,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_http_red_svc_5min
            WHERE {scope}{ns_filter}{q_scope}
            UNION ALL
            SELECT cluster_id, dst_workload, dst_namespace,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_grpc_red_svc_5min
            WHERE {scope}{ns_filter}{q_scope}
        )
        SELECT cluster_id, dst_workload, dst_namespace,
               sumMerge(request_count_state) AS rate,
               sumMerge(error_count_state) AS errors,
               quantileTDigestMerge(0.50)(lat_quantile_state) AS p50,
               quantileTDigestMerge(0.95)(lat_quantile_state) AS p95,
               quantileTDigestMerge(0.99)(lat_quantile_state) AS p99
        FROM unioned
        WHERE dst_workload != ''
        GROUP BY cluster_id, dst_workload, dst_namespace
        ORDER BY {sort_by} DESC
        LIMIT {int(limit)} OFFSET {int(offset)}
        """
        rows = self.client.execute(query)

        # Total count for pagination — separate query because the LIMIT
        # above would otherwise truncate the count.
        total_query = f"""
        SELECT count() FROM (
            SELECT cluster_id, dst_workload, dst_namespace
            FROM (
                SELECT cluster_id, dst_workload, dst_namespace
                FROM flowfish.l7_http_red_svc_5min
                WHERE {scope}{ns_filter}{q_scope}
                UNION ALL
                SELECT cluster_id, dst_workload, dst_namespace
                FROM flowfish.l7_grpc_red_svc_5min
                WHERE {scope}{ns_filter}{q_scope}
            )
            WHERE dst_workload != ''
            GROUP BY cluster_id, dst_workload, dst_namespace
        )
        """
        total_rows = self.client.execute(total_query)
        total = int(total_rows[0][0]) if total_rows else 0

        services = []
        for row in rows:
            cluster_id_v, dst_workload, dst_namespace, rate, errors, p50, p95, p99 = row
            rate_v = int(rate or 0)
            errors_v = int(errors or 0)
            error_rate = (errors_v / rate_v) if rate_v > 0 else 0.0
            services.append({
                "cluster_id": str(cluster_id_v or ""),
                "dst_workload": str(dst_workload or ""),
                "dst_namespace": str(dst_namespace or ""),
                "workload_key": f"{dst_namespace}/{dst_workload}",
                "request_count": rate_v,
                "error_count": errors_v,
                "error_rate": round(error_rate, 4),
                "latency_p50_ms": round(float(p50 or 0.0), 4),
                "latency_p95_ms": round(float(p95 or 0.0), 4),
                "latency_p99_ms": round(float(p99 or 0.0), 4),
            })

        return {
            "services": services,
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
            "sort_by": sort_by,
        }

    def get_apm_operations(
        self,
        analysis_id: str,
        workload_key: str,
        cluster_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        # Plan v3 Akış B m.4 — free-form search across HTTP path/method
        # and gRPC method/service columns. Wired into the Trace Explorer
        # global search → "Operations" tab path.
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Per-operation RED tablosu (HTTP method+path / gRPC service+method).

        `workload_key` is `{dst_namespace}/{dst_workload}`; we split it back
        into namespace and workload to filter the ops MV.
        """
        if "/" not in workload_key:
            return {"operations": [], "total": 0, "limit": int(limit), "offset": int(offset)}
        ns, wl = workload_key.split("/", 1)
        ns_esc = self._escape_ch(ns)
        wl_esc = self._escape_ch(wl)
        scope = self._apm_scope(analysis_id, cluster_id)

        http_q_scope = ""
        grpc_q_scope = ""
        if q:
            http_cond = self._build_search_condition(q, ["http_method", "http_path_normalized"])
            grpc_cond = self._build_search_condition(q, ["grpc_method", "grpc_service"])
            if http_cond:
                http_q_scope = f" AND {http_cond}"
            if grpc_cond:
                grpc_q_scope = f" AND {grpc_cond}"

        # gRPC mapping note: Beyla emits the full RPC path (e.g.
        # `/grpc.health.v1.Health/Check`) in `grpc_method` and frequently
        # leaves `grpc_service` empty. Using `grpc_service` for `op_path`
        # therefore produced blank `operation` rows in the UI. We feed
        # `grpc_method` into `op_path` (the unique-key column for the
        # group-by) and surface `grpc_service` in `op_method` as auxiliary
        # context. Combined with the Python-side fallback below, this
        # guarantees a non-empty `operation` for every gRPC entry.
        query = f"""
        WITH unioned AS (
            SELECT 'HTTP' AS protocol,
                   http_method AS op_method,
                   http_path_normalized AS op_path,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_http_red_ops_5min
            WHERE {scope}
              AND dst_namespace = '{ns_esc}'
              AND dst_workload = '{wl_esc}'{http_q_scope}
            UNION ALL
            SELECT 'GRPC' AS protocol,
                   grpc_service AS op_method,
                   grpc_method AS op_path,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_grpc_red_ops_5min
            WHERE {scope}
              AND dst_namespace = '{ns_esc}'
              AND dst_workload = '{wl_esc}'{grpc_q_scope}
        )
        SELECT protocol, op_method, op_path,
               sumMerge(request_count_state) AS rate,
               sumMerge(error_count_state) AS errors,
               quantileTDigestMerge(0.50)(lat_quantile_state) AS p50,
               quantileTDigestMerge(0.95)(lat_quantile_state) AS p95,
               quantileTDigestMerge(0.99)(lat_quantile_state) AS p99
        FROM unioned
        GROUP BY protocol, op_method, op_path
        ORDER BY rate DESC
        LIMIT {int(limit)} OFFSET {int(offset)}
        """
        rows = self.client.execute(query)
        operations = []
        for row in rows:
            protocol, method, path_v, rate, errors, p50, p95, p99 = row
            rate_v = int(rate or 0)
            errors_v = int(errors or 0)
            method_str = str(method or "")
            # Defensive fallback: if both fields exist but `op_path` is
            # empty (Beyla pre-3.x sometimes emits service-only or
            # method-only spans), promote `op_method` to `operation` so
            # the UI never renders a blank row that the operator can't
            # correlate back to traffic.
            operation_str = str(path_v or "") or method_str
            if not operation_str:
                operation_str = "(unknown)"
            operations.append({
                "protocol": str(protocol),
                "method": method_str,
                "operation": operation_str,
                "request_count": rate_v,
                "error_count": errors_v,
                "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                "latency_p50_ms": round(float(p50 or 0.0), 4),
                "latency_p95_ms": round(float(p95 or 0.0), 4),
                "latency_p99_ms": round(float(p99 or 0.0), 4),
            })
        return {
            "operations": operations,
            "workload_key": workload_key,
            "limit": int(limit),
            "offset": int(offset),
        }

    def get_apm_service_stats(
        self,
        analysis_id: str,
        workload_key: str,
        cluster_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RED metrics over time (5-minute buckets) for a single service.

        Returns a list of `{timestamp, rate, errors, p50, p95, p99}` rows
        suitable for a recharts LineChart. Combines HTTP+gRPC like
        `get_apm_services`.
        """
        if "/" not in workload_key:
            return {"buckets": [], "workload_key": workload_key}
        ns, wl = workload_key.split("/", 1)
        ns_esc = self._escape_ch(ns)
        wl_esc = self._escape_ch(wl)
        scope = self._apm_scope(analysis_id, cluster_id)

        query = f"""
        WITH unioned AS (
            SELECT timestamp_5min, request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_http_red_svc_5min
            WHERE {scope}
              AND dst_namespace = '{ns_esc}'
              AND dst_workload = '{wl_esc}'
            UNION ALL
            SELECT timestamp_5min, request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_grpc_red_svc_5min
            WHERE {scope}
              AND dst_namespace = '{ns_esc}'
              AND dst_workload = '{wl_esc}'
        )
        SELECT timestamp_5min,
               sumMerge(request_count_state) AS rate,
               sumMerge(error_count_state) AS errors,
               quantileTDigestMerge(0.50)(lat_quantile_state) AS p50,
               quantileTDigestMerge(0.95)(lat_quantile_state) AS p95,
               quantileTDigestMerge(0.99)(lat_quantile_state) AS p99
        FROM unioned
        GROUP BY timestamp_5min
        ORDER BY timestamp_5min ASC
        """
        rows = self.client.execute(query)
        buckets = []
        for row in rows:
            ts, rate, errors, p50, p95, p99 = row
            rate_v = int(rate or 0)
            errors_v = int(errors or 0)
            buckets.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "request_count": rate_v,
                "error_count": errors_v,
                "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                "latency_p50_ms": round(float(p50 or 0.0), 4),
                "latency_p95_ms": round(float(p95 or 0.0), 4),
                "latency_p99_ms": round(float(p99 or 0.0), 4),
            })
        return {"buckets": buckets, "workload_key": workload_key, "interval_seconds": 300}

    def get_apm_service_dependencies(
        self,
        analysis_id: str,
        workload_key: str,
        cluster_id: Optional[str] = None,
        direction: str = "both",
        # Plan v3 Akış B m.4 — search across the *peer* workload/namespace
        # (i.e. for upstream we filter `src_*`, for downstream `dst_*`).
        # The peer side is what the operator sees in the table, so it's
        # what they'd type into the global search box.
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dependency neighbours of a service (upstream/downstream).

        Reads from the SVC RED MVs and groups by the *other* side of the
        edge: when `direction=upstream` we look at rows where the target
        is `workload_key` and group by source; vice versa for `downstream`.
        `both` returns two lists.
        """
        if "/" not in workload_key:
            return {"upstream": [], "downstream": [], "workload_key": workload_key}
        ns, wl = workload_key.split("/", 1)
        ns_esc = self._escape_ch(ns)
        wl_esc = self._escape_ch(wl)
        scope = self._apm_scope(analysis_id, cluster_id)

        up_q_scope = ""
        dn_q_scope = ""
        if q:
            up_cond = self._build_search_condition(q, ["src_workload", "src_namespace"])
            dn_cond = self._build_search_condition(q, ["dst_workload", "dst_namespace"])
            if up_cond:
                up_q_scope = f" AND {up_cond}"
            if dn_cond:
                dn_q_scope = f" AND {dn_cond}"

        upstream: List[Dict[str, Any]] = []
        downstream: List[Dict[str, Any]] = []

        # Audit fix (multi-cluster correctness): the previous query
        # grouped only by (workload, namespace) so a peer service with
        # the same name in two different clusters collapsed into a
        # single row, hiding which cluster contributed which traffic.
        # We add `cluster_id` to the SELECT and GROUP BY so the
        # DependencyCard can render a ClusterBadge alongside each
        # neighbour and downstream consumers can disambiguate edges
        # that span clusters (e.g. service mesh / shared LB topologies).
        if direction in ("both", "upstream"):
            up_query = f"""
            WITH unioned AS (
                SELECT cluster_id, src_workload, src_namespace, request_count_state,
                       error_count_state, lat_quantile_state
                FROM flowfish.l7_http_red_svc_5min
                WHERE {scope}
                  AND dst_namespace = '{ns_esc}'
                  AND dst_workload = '{wl_esc}'{up_q_scope}
                UNION ALL
                SELECT cluster_id, src_workload, src_namespace, request_count_state,
                       error_count_state, lat_quantile_state
                FROM flowfish.l7_grpc_red_svc_5min
                WHERE {scope}
                  AND dst_namespace = '{ns_esc}'
                  AND dst_workload = '{wl_esc}'{up_q_scope}
            )
            SELECT cluster_id, src_workload, src_namespace,
                   sumMerge(request_count_state) AS rate,
                   sumMerge(error_count_state) AS errors,
                   quantileTDigestMerge(0.95)(lat_quantile_state) AS p95
            FROM unioned
            WHERE src_workload != ''
            GROUP BY cluster_id, src_workload, src_namespace
            ORDER BY rate DESC LIMIT 50
            """
            for row in self.client.execute(up_query):
                cluster_id_v, src_wl, src_ns, rate, errors, p95 = row
                rate_v = int(rate or 0)
                errors_v = int(errors or 0)
                upstream.append({
                    "cluster_id": str(cluster_id_v or ""),
                    "workload": str(src_wl or ""),
                    "namespace": str(src_ns or ""),
                    "workload_key": f"{src_ns}/{src_wl}",
                    "request_count": rate_v,
                    "error_count": errors_v,
                    "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                    "latency_p95_ms": round(float(p95 or 0.0), 4),
                })

        if direction in ("both", "downstream"):
            dn_query = f"""
            WITH unioned AS (
                SELECT cluster_id, dst_workload, dst_namespace, request_count_state,
                       error_count_state, lat_quantile_state
                FROM flowfish.l7_http_red_svc_5min
                WHERE {scope}
                  AND src_namespace = '{ns_esc}'
                  AND src_workload = '{wl_esc}'{dn_q_scope}
                UNION ALL
                SELECT cluster_id, dst_workload, dst_namespace, request_count_state,
                       error_count_state, lat_quantile_state
                FROM flowfish.l7_grpc_red_svc_5min
                WHERE {scope}
                  AND src_namespace = '{ns_esc}'
                  AND src_workload = '{wl_esc}'{dn_q_scope}
            )
            SELECT cluster_id, dst_workload, dst_namespace,
                   sumMerge(request_count_state) AS rate,
                   sumMerge(error_count_state) AS errors,
                   quantileTDigestMerge(0.95)(lat_quantile_state) AS p95
            FROM unioned
            WHERE dst_workload != ''
            GROUP BY cluster_id, dst_workload, dst_namespace
            ORDER BY rate DESC LIMIT 50
            """
            for row in self.client.execute(dn_query):
                cluster_id_v, dst_wl, dst_ns, rate, errors, p95 = row
                rate_v = int(rate or 0)
                errors_v = int(errors or 0)
                downstream.append({
                    "cluster_id": str(cluster_id_v or ""),
                    "workload": str(dst_wl or ""),
                    "namespace": str(dst_ns or ""),
                    "workload_key": f"{dst_ns}/{dst_wl}",
                    "request_count": rate_v,
                    "error_count": errors_v,
                    "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                    "latency_p95_ms": round(float(p95 or 0.0), 4),
                })

        return {
            "workload_key": workload_key,
            "upstream": upstream,
            "downstream": downstream,
            "direction": direction,
        }

    # ============================================================
    # Plan v3 Akış B m.2 — Trace Explorer "Operations" /
    # "Dependencies" tabs need a *cross-workload* aggregate (the
    # operator hasn't picked a single service yet). The per-workload
    # endpoints `get_apm_operations` / `get_apm_service_dependencies`
    # require a workload_key, so we add two thin sibling methods that
    # share the same MV scoping rules but group by the global axes.
    #
    # All three filters from the parent page are honoured:
    #   - analysis_id (always)
    #   - cluster_id (optional narrowing)
    #   - q (free-form search; scoped to the per-table columns the
    #     operator might reasonably type)
    #
    # Limits intentionally cap top-N at 50; the goal is to give the
    # operator a quick "at a glance" picture, not pagination. If they
    # need the full list they can pivot to the dedicated APM page.
    # ============================================================

    def get_apm_operations_global(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Top operations across every workload in the analysis scope.

        Used by the Trace Explorer "Operations" tab so the operator can
        see what kinds of HTTP/gRPC calls the analysis collected without
        first picking a service. Combines HTTP + gRPC ops MVs and
        applies the same `q` semantics as `get_apm_operations`.
        """
        scope = self._apm_scope(analysis_id, cluster_id)

        http_q_scope = ""
        grpc_q_scope = ""
        if q:
            http_cond = self._build_search_condition(
                q, ["http_method", "http_path_normalized", "dst_workload", "dst_namespace"]
            )
            grpc_cond = self._build_search_condition(
                q, ["grpc_method", "grpc_service", "dst_workload", "dst_namespace"]
            )
            if http_cond:
                http_q_scope = f" AND {http_cond}"
            if grpc_cond:
                grpc_q_scope = f" AND {grpc_cond}"

        # gRPC mirroring of `get_apm_operations`: feed `grpc_method` into
        # `op_path` (the unique-key column for the group-by) and surface
        # `grpc_service` in `op_method` so the UI can render either.
        query = f"""
        WITH unioned AS (
            SELECT 'HTTP' AS protocol,
                   cluster_id, dst_workload, dst_namespace,
                   http_method AS op_method,
                   http_path_normalized AS op_path,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_http_red_ops_5min
            WHERE {scope}{http_q_scope}
            UNION ALL
            SELECT 'GRPC' AS protocol,
                   cluster_id, dst_workload, dst_namespace,
                   grpc_service AS op_method,
                   grpc_method AS op_path,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_grpc_red_ops_5min
            WHERE {scope}{grpc_q_scope}
        )
        SELECT protocol, cluster_id, dst_workload, dst_namespace,
               op_method, op_path,
               sumMerge(request_count_state) AS rate,
               sumMerge(error_count_state) AS errors,
               quantileTDigestMerge(0.50)(lat_quantile_state) AS p50,
               quantileTDigestMerge(0.95)(lat_quantile_state) AS p95,
               quantileTDigestMerge(0.99)(lat_quantile_state) AS p99
        FROM unioned
        GROUP BY protocol, cluster_id, dst_workload, dst_namespace, op_method, op_path
        ORDER BY rate DESC
        LIMIT {int(limit)}
        """
        rows = self.client.execute(query)
        operations = []
        for row in rows:
            (protocol, cluster_id_v, dst_wl, dst_ns,
             method, path_v, rate, errors, p50, p95, p99) = row
            rate_v = int(rate or 0)
            errors_v = int(errors or 0)
            method_str = str(method or "")
            operation_str = str(path_v or "") or method_str
            if not operation_str:
                operation_str = "(unknown)"
            operations.append({
                "protocol": str(protocol),
                "cluster_id": str(cluster_id_v or ""),
                "workload": str(dst_wl or ""),
                "namespace": str(dst_ns or ""),
                "workload_key": f"{dst_ns}/{dst_wl}",
                "method": method_str,
                "operation": operation_str,
                "request_count": rate_v,
                "error_count": errors_v,
                "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                "latency_p50_ms": round(float(p50 or 0.0), 4),
                "latency_p95_ms": round(float(p95 or 0.0), 4),
                "latency_p99_ms": round(float(p99 or 0.0), 4),
            })
        return {"operations": operations, "limit": int(limit)}

    def get_apm_dependencies_global(
        self,
        analysis_id: str,
        cluster_id: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """All service-to-service edges across the analysis scope.

        Powers the Trace Explorer "Dependencies" tab. Each row is a
        directed edge `(src → dst)` with rate / errors / p95 latency.
        Searches across either side of the edge so a single token like
        "checkout" surfaces both upstream and downstream uses.
        """
        scope = self._apm_scope(analysis_id, cluster_id)

        q_scope = ""
        if q:
            cond = self._build_search_condition(
                q,
                [
                    "src_workload",
                    "src_namespace",
                    "dst_workload",
                    "dst_namespace",
                ],
            )
            if cond:
                q_scope = f" AND {cond}"

        query = f"""
        WITH unioned AS (
            SELECT cluster_id,
                   src_namespace, src_workload,
                   dst_namespace, dst_workload,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_http_red_svc_5min
            WHERE {scope}{q_scope}
            UNION ALL
            SELECT cluster_id,
                   src_namespace, src_workload,
                   dst_namespace, dst_workload,
                   request_count_state, error_count_state, lat_quantile_state
            FROM flowfish.l7_grpc_red_svc_5min
            WHERE {scope}{q_scope}
        )
        SELECT cluster_id, src_namespace, src_workload, dst_namespace, dst_workload,
               sumMerge(request_count_state) AS rate,
               sumMerge(error_count_state) AS errors,
               quantileTDigestMerge(0.95)(lat_quantile_state) AS p95
        FROM unioned
        WHERE src_workload != '' AND dst_workload != ''
        GROUP BY cluster_id, src_namespace, src_workload, dst_namespace, dst_workload
        ORDER BY rate DESC
        LIMIT {int(limit)}
        """
        rows = self.client.execute(query)
        edges = []
        for row in rows:
            (cluster_id_v, src_ns, src_wl, dst_ns, dst_wl,
             rate, errors, p95) = row
            rate_v = int(rate or 0)
            errors_v = int(errors or 0)
            edges.append({
                "cluster_id": str(cluster_id_v or ""),
                "src_workload": str(src_wl or ""),
                "src_namespace": str(src_ns or ""),
                "src_workload_key": f"{src_ns}/{src_wl}",
                "dst_workload": str(dst_wl or ""),
                "dst_namespace": str(dst_ns or ""),
                "dst_workload_key": f"{dst_ns}/{dst_wl}",
                "request_count": rate_v,
                "error_count": errors_v,
                "error_rate": round((errors_v / rate_v) if rate_v > 0 else 0.0, 4),
                "latency_p95_ms": round(float(p95 or 0.0), 4),
            })
        return {"edges": edges, "limit": int(limit)}

    # ============================================================
    # Phase 3B: Related Traces
    # ============================================================
    # Given an "anchor" trace_id, find other traces that share useful
    # context. Two correlation strategies are exposed:
    #   - same_edge: same (src_workload, dst_workload) pair. Answers
    #     "what other calls did service A make to service B around the
    #     same time?".
    #   - same_pod: same dst_pod (or src_pod when the anchor span is
    #     client-side). Answers "what else hit this exact replica?".
    #
    # 5-tuple correlation is intentionally deferred to Phase 4 because
    # in Beyla passive mode src_port is ephemeral and rarely matches
    # across spans (Plan v1.5 Section 16.F).
    #
    # The anchor trace's metadata is fetched by reading the *earliest*
    # span of the trace. For multi-cluster traces this is fine — we
    # only need (src_workload, dst_workload, src_pod, dst_pod, ts) to
    # build the related queries.
    # ============================================================

    def get_related_traces(
        self,
        trace_id: str,
        analysis_id: Optional[str] = None,
        rel_type: str = "both",
        limit: int = 50,
        time_window_minutes: int = 60,
    ) -> Dict[str, Any]:
        """Find traces related to `trace_id` by edge or pod proximity.

        Args:
            trace_id: Anchor trace's W3C 16-byte hex ID.
            analysis_id: Restrict the search to this analysis (and its
                multi-cluster sub-analyses via `<aid>-*`). When omitted
                the search spans every analysis — operator deep-link case.
            rel_type: `same_edge`, `same_pod`, or `both`.
            limit: Max results *per group* (default 50).
            time_window_minutes: Look-back window from the anchor's
                start time (default 60). Caps the search to bounded
                partitions for ClickHouse efficiency.

        Returns:
            {"anchor": {...}, "same_edge": [...], "same_pod": [...]}.
            Each related trace has the same shape as `get_recent_traces`:
            trace_id, start_time, end_time, span_count, error_count,
            max_latency_ms, duration_ms, clusters[].

            Anchor metadata is included so the UI can show "what we
            pivoted from" without a second round trip.
        """
        if rel_type not in {"same_edge", "same_pod", "both"}:
            rel_type = "both"
        tid = _validate_trace_id(trace_id)
        if analysis_id is not None and str(analysis_id):
            aid = self._escape_ch(str(analysis_id))
            scope = f"AND (analysis_id = '{aid}' OR analysis_id LIKE '{aid}-%')"
        else:
            scope = ""

        # 1. Anchor metadata: pull the earliest span to get the edge
        # signature. We use UNION ALL across HTTP+gRPC because the
        # anchor could be either protocol; DNS is excluded because a
        # DNS-only "trace" has no meaningful peer to pivot on.
        # Phase 4: also match `virtual_trace_id` so operators can pivot
        # FROM a virtual trace. Falls back to the legacy trace_id-only
        # query when the column is missing (Phase 4 migration not yet
        # applied) — same defensive pattern used in get_trace_spans.
        anchor_match_with_vt = (
            f"(trace_id = '{tid}' OR (virtual_trace_id = '{tid}' AND virtual_trace_id != ''))"
        )
        anchor_match_legacy = f"trace_id = '{tid}'"
        anchor_query_vt = f"""
        SELECT timestamp, src_namespace, src_workload, src_pod,
               dst_namespace, dst_workload, dst_pod, cluster_id, 'HTTP' AS proto
        FROM l7_http_flows
        WHERE {anchor_match_with_vt} {scope}
        UNION ALL
        SELECT timestamp, src_namespace, src_workload, src_pod,
               dst_namespace, dst_workload, dst_pod, cluster_id, 'GRPC' AS proto
        FROM l7_grpc_flows
        WHERE {anchor_match_with_vt} {scope}
        ORDER BY timestamp ASC
        LIMIT 1
        """
        anchor_query_legacy = f"""
        SELECT timestamp, src_namespace, src_workload, src_pod,
               dst_namespace, dst_workload, dst_pod, cluster_id, 'HTTP' AS proto
        FROM l7_http_flows
        WHERE {anchor_match_legacy} {scope}
        UNION ALL
        SELECT timestamp, src_namespace, src_workload, src_pod,
               dst_namespace, dst_workload, dst_pod, cluster_id, 'GRPC' AS proto
        FROM l7_grpc_flows
        WHERE {anchor_match_legacy} {scope}
        ORDER BY timestamp ASC
        LIMIT 1
        """
        try:
            anchor_rows = self.client.execute(anchor_query_vt)
            virtual_trace_supported = True
        except Exception as e:
            err_str = str(e)
            if (
                "Unknown column" in err_str
                or "doesn't have column" in err_str
                or "No such column" in err_str
            ) and "virtual_trace_id" in err_str:
                logger.warning(
                    "virtual_trace_id column missing in anchor query — falling back to legacy"
                )
                anchor_rows = self.client.execute(anchor_query_legacy)
                virtual_trace_supported = False
            else:
                raise
        if not anchor_rows:
            return {
                "anchor": None,
                "same_edge": [],
                "same_pod": [],
                "rel_type": rel_type,
            }
        a_ts, a_src_ns, a_src_wl, a_src_pod, a_dst_ns, a_dst_wl, a_dst_pod, a_cluster, _ = anchor_rows[0]
        anchor_meta = {
            "trace_id": tid,
            "timestamp": a_ts.isoformat() if hasattr(a_ts, "isoformat") else str(a_ts),
            "src_namespace": str(a_src_ns or ""),
            "src_workload": str(a_src_wl or ""),
            "src_pod": str(a_src_pod or ""),
            "dst_namespace": str(a_dst_ns or ""),
            "dst_workload": str(a_dst_wl or ""),
            "dst_pod": str(a_dst_pod or ""),
            "cluster_id": str(a_cluster or ""),
        }

        # Time bounds applied to all related queries; converts the anchor
        # timestamp + ±window into ClickHouse DateTime literals. We bound
        # both ends to make the query bounded on partition pruning.
        try:
            window_minutes = max(5, min(int(time_window_minutes), 24 * 60))
        except (TypeError, ValueError):
            window_minutes = 60
        ts_clause = (
            f"timestamp >= toDateTime64('{a_ts.isoformat()}', 3) - INTERVAL {window_minutes} MINUTE "
            f"AND timestamp <= toDateTime64('{a_ts.isoformat()}', 3) + INTERVAL {window_minutes} MINUTE"
        )

        same_edge: List[Dict[str, Any]] = []
        same_pod: List[Dict[str, Any]] = []

        if rel_type in {"same_edge", "both"} and a_src_wl and a_dst_wl:
            src_wl_esc = self._escape_ch(a_src_wl)
            dst_wl_esc = self._escape_ch(a_dst_wl)
            edge_filter = (
                f"src_workload = '{src_wl_esc}' AND dst_workload = '{dst_wl_esc}'"
            )
            same_edge = self._related_traces_query(
                tid, scope, edge_filter, ts_clause, int(limit), virtual_trace_supported
            )

        if rel_type in {"same_pod", "both"} and a_dst_pod:
            # Use dst_pod for server-side pivot (most common case: which
            # other traces hit this same backend pod?). When the anchor
            # span has no dst_pod (e.g. external destinations) we skip.
            dst_pod_esc = self._escape_ch(a_dst_pod)
            pod_filter = f"dst_pod = '{dst_pod_esc}'"
            same_pod = self._related_traces_query(
                tid, scope, pod_filter, ts_clause, int(limit), virtual_trace_supported
            )

        return {
            "anchor": anchor_meta,
            "same_edge": same_edge,
            "same_pod": same_pod,
            "rel_type": rel_type,
            "time_window_minutes": window_minutes,
        }

    def _related_traces_query(
        self,
        anchor_tid: str,
        scope: str,
        extra_filter: str,
        ts_clause: str,
        limit: int,
        virtual_trace_supported: bool = True,
    ) -> List[Dict[str, Any]]:
        """Run the trace-grouping aggregation used by both same_edge and
        same_pod. Mirrors the structure of get_recent_traces' inner query
        but with an `extra_filter` (edge or pod) and the anchor trace_id
        excluded from the result. The bloom filter index on src_pod /
        dst_pod (clickhouse_006) accelerates the pod variant.

        When `virtual_trace_supported` is True (Phase 4 migration applied)
        the query also surfaces virtual traces by selecting an
        `effective_id = if(trace_id != '', trace_id, virtual_trace_id)`
        and grouping by it. The returned `trace_id` column always carries
        the effective ID, so callers don't need to know the underlying
        column. When False, the legacy W3C-only query runs.
        """
        if virtual_trace_supported:
            # `if(...)` selects trace_id when present, virtual_trace_id when not.
            # The outer GROUP BY collapses each virtual trace into one row,
            # exactly like a real W3C trace.
            #
            # Alias is `effective_id` (NOT `trace_id`) — aliasing to the same
            # name as a base column makes ClickHouse resolve `trace_id` inside
            # GROUP BY back to the alias, which expands recursively and
            # produces a different expression than the SELECT one. The
            # planner then complains "Column `trace_id` is not under
            # aggregate function and not in GROUP BY". The outer query
            # renames `effective_id` back to `trace_id` so the response
            # shape stays identical.
            inner = f"""
            SELECT if(trace_id != '', trace_id, virtual_trace_id) AS effective_id,
                   min(timestamp) AS ts, max(timestamp) AS ts2,
                   count() AS cnt, countIf(http_status_code >= 400) AS errs,
                   max(latency_ms) AS max_lat,
                   groupUniqArray(cluster_id) AS clusters_arr
            FROM l7_http_flows
            WHERE (trace_id != '' OR virtual_trace_id != '')
              AND if(trace_id != '', trace_id, virtual_trace_id) != '{anchor_tid}'
              {scope}
              AND {ts_clause}
              AND {extra_filter}
            GROUP BY effective_id
            UNION ALL
            SELECT if(trace_id != '', trace_id, virtual_trace_id) AS effective_id,
                   min(timestamp), max(timestamp),
                   count(), countIf(grpc_status_code != 0),
                   max(latency_ms),
                   groupUniqArray(cluster_id)
            FROM l7_grpc_flows
            WHERE (trace_id != '' OR virtual_trace_id != '')
              AND if(trace_id != '', trace_id, virtual_trace_id) != '{anchor_tid}'
              {scope}
              AND {ts_clause}
              AND {extra_filter}
            GROUP BY effective_id
            """
            outer_id_alias = "effective_id AS trace_id"
            outer_group_col = "effective_id"
        else:
            inner = f"""
            SELECT trace_id, min(timestamp) AS ts, max(timestamp) AS ts2,
                   count() AS cnt, countIf(http_status_code >= 400) AS errs,
                   max(latency_ms) AS max_lat,
                   groupUniqArray(cluster_id) AS clusters_arr
            FROM l7_http_flows
            WHERE trace_id != '' AND trace_id != '{anchor_tid}' {scope}
              AND {ts_clause}
              AND {extra_filter}
            GROUP BY trace_id
            UNION ALL
            SELECT trace_id, min(timestamp), max(timestamp),
                   count(), countIf(grpc_status_code != 0),
                   max(latency_ms),
                   groupUniqArray(cluster_id)
            FROM l7_grpc_flows
            WHERE trace_id != '' AND trace_id != '{anchor_tid}' {scope}
              AND {ts_clause}
              AND {extra_filter}
            GROUP BY trace_id
            """
            outer_id_alias = "trace_id"
            outer_group_col = "trace_id"
        query = f"""
        SELECT {outer_id_alias}, min(ts) AS start_time, max(ts2) AS end_time,
               sum(cnt) AS span_count, sum(errs) AS error_count,
               max(max_lat) AS max_latency_ms,
               groupUniqArrayArray(clusters_arr) AS clusters
        FROM ({inner})
        GROUP BY {outer_group_col}
        ORDER BY start_time DESC
        LIMIT {int(limit)}
        """
        try:
            rows = self.client.execute(query)
        except Exception as e:
            err_str = str(e)
            if (
                virtual_trace_supported
                and (
                    "Unknown column" in err_str
                    or "doesn't have column" in err_str
                    or "No such column" in err_str
                )
                and "virtual_trace_id" in err_str
            ):
                # Schema drift between anchor and table — anchor query
                # succeeded with virtual_trace_id but inner failed (e.g.
                # one table migrated, other not). Re-run with legacy.
                logger.warning(
                    "virtual_trace_id column missing in related-traces inner query — falling back to legacy"
                )
                return self._related_traces_query(
                    anchor_tid, scope, extra_filter, ts_clause, limit, virtual_trace_supported=False
                )
            raise
        out: List[Dict[str, Any]] = []
        for row in rows:
            tid, st, et, cnt, errs, lat, clusters = row
            duration_ms = 0.0
            if st and et:
                try:
                    duration_ms = (et - st).total_seconds() * 1000.0
                except (TypeError, AttributeError):
                    duration_ms = 0.0
            out.append({
                "trace_id": str(tid),
                "start_time": st.isoformat() if hasattr(st, "isoformat") else st,
                "end_time": et.isoformat() if hasattr(et, "isoformat") else et,
                "span_count": int(cnt or 0),
                "error_count": int(errs or 0),
                "max_latency_ms": float(lat or 0.0),
                "duration_ms": duration_ms,
                "clusters": [str(c) for c in (clusters or []) if c],
            })
        return out

    def close(self):
        """Close database connection"""
        if self.client:
            self.client.disconnect()
            logger.info("Timeseries database connection closed")

