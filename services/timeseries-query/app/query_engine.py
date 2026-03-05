"""
Timeseries Query Engine - Event Data Query Layer

Provides abstracted access to time-series event data.
Currently backed by ClickHouse, but interface is database-agnostic.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as DatabaseError

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
    
    def _build_where_clause(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        namespace_column: str = "namespace",
        extra_conditions: Optional[List[str]] = None
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
        
        Returns counts per event type, time range, top namespaces/pods
        """
        try:
            event_counts = {}
            
            # Count events per table
            for event_type, table_name in self.EVENT_TABLES.items():
                # network_flows and dns_queries use source_* columns
                ns_col = "source_namespace" if table_name in ("network_flows", "dns_queries") else "namespace"
                where = self._build_where_clause(cluster_id, analysis_id, namespace_column=ns_col)
                
                # For security events (capability_checks), count:
                # 1. All denied verdicts (blocked capabilities)
                # 2. Sensitive capabilities even if allowed (potential security concerns)
                # This filters out millions of routine "allowed" capability checks
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
                    where += f" AND (verdict = 'denied' OR verdict = '1' OR toString(verdict) = '1' OR capability IN ({sensitive_caps_str}))"
                    logger.info(f"Security stats filter: denied + sensitive capabilities")
                
                query = f"SELECT count() as cnt FROM {table_name} WHERE {where}"
                result = self.client.execute(query)
                count = result[0][0] if result else 0
                event_counts[event_type] = count
                
                if table_name == "capability_checks":
                    logger.info(f"Security events count (denied only): {count}")
            
            total_events = sum(event_counts.values())
            
            # Get time range from network_flows (usually has most data)
            time_query = f"""
            SELECT min(timestamp), max(timestamp) 
            FROM network_flows 
            WHERE {self._build_where_clause(cluster_id, analysis_id, namespace_column='source_namespace')}
            """
            time_result = self.client.execute(time_query)
            
            time_range = {
                "start": time_result[0][0].isoformat() if time_result and time_result[0][0] else None,
                "end": time_result[0][1].isoformat() if time_result and time_result[0][1] else None
            }
            
            # Top namespaces
            ns_query = f"""
            SELECT source_namespace as namespace, count() as cnt 
            FROM network_flows 
            WHERE {self._build_where_clause(cluster_id, analysis_id, namespace_column='source_namespace')}
            GROUP BY source_namespace 
            ORDER BY cnt DESC 
            LIMIT 10
            """
            ns_result = self.client.execute(ns_query)
            top_namespaces = [{"namespace": r[0], "count": r[1]} for r in ns_result]
            
            # Top pods
            pod_query = f"""
            SELECT source_pod as pod, source_namespace as namespace, count() as cnt 
            FROM network_flows 
            WHERE {self._build_where_clause(cluster_id, analysis_id, namespace_column='source_namespace')}
            GROUP BY source_pod, source_namespace 
            ORDER BY cnt DESC 
            LIMIT 10
            """
            pod_result = self.client.execute(pod_query)
            top_pods = [{"pod": r[0], "namespace": r[1], "count": r[2]} for r in pod_result]
            
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
        offset: int = 0
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
            
        Returns:
            Tuple of (events list, total count)
        """
        try:
            table_name = self.EVENT_TABLES.get(event_type)
            if not table_name:
                raise ValueError(f"Unknown event type: {event_type}")
            
            # Determine namespace column based on table
            # network_flows and dns_queries use source_* columns
            ns_col = "source_namespace" if table_name in ("network_flows", "dns_queries") else "namespace"
            
            where_clause = self._build_where_clause(
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                namespace=namespace,
                start_time=start_time,
                end_time=end_time,
                namespace_column=ns_col
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
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query network flow events"""
        return await self.query_events(
            "network_flow", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_dns_queries(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query DNS query events"""
        return await self.query_events(
            "dns_query", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_process_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query process events"""
        return await self.query_events(
            "process_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_file_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query file operation events"""
        return await self.query_events(
            "file_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_security_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query security/capability events"""
        return await self.query_events(
            "security_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_oom_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query OOM kill events"""
        return await self.query_events(
            "oom_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_bind_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query socket bind events"""
        return await self.query_events(
            "bind_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_sni_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query TLS/SNI events"""
        return await self.query_events(
            "sni_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    async def query_mount_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query mount events"""
        return await self.query_events(
            "mount_event", cluster_id, analysis_id, namespace,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )
    
    # NOTE: query_tcp_connections removed - IG trace_tcp doesn't produce TCP state events
    # TCP connection info is captured in network_flows via connect/accept/close events
    
    async def query_all_events(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
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
            
            # Count total
            total = 0
            for event_type, table_name in tables_to_query.items():
                # network_flows and dns_queries use source_* columns
                ns_col = "source_namespace" if table_name in ("network_flows", "dns_queries") else "namespace"
                where = self._build_where_clause(
                    cluster_id, analysis_id, namespace, start_time, end_time, ns_col
                )
                count_query = f"SELECT count() FROM {table_name} WHERE {where}"
                result = self.client.execute(count_query)
                total += result[0][0] if result else 0
            
            # Build UNION query for data
            union_parts = []
            for event_type, table_name in tables_to_query.items():
                # network_flows and dns_queries use source_* columns
                uses_source_cols = table_name in ("network_flows", "dns_queries")
                ns_col = "source_namespace" if uses_source_cols else "namespace"
                pod_col = "source_pod" if uses_source_cols else "pod"
                container_col = "source_container" if uses_source_cols else "container"
                
                where = self._build_where_clause(
                    cluster_id, analysis_id, namespace, start_time, end_time, ns_col
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
        
        # All tables that might contain analysis-specific data
        # NOTE: tcp_lifecycle included even though no data is written to it currently
        # This ensures complete cleanup if data is ever written in the future
        tables = list(self.EVENT_TABLES.values()) + [
            'workload_metadata', 
            'communication_edges',
            'tcp_lifecycle'  # Safety: include even if empty
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
    
    def close(self):
        """Close database connection"""
        if self.client:
            self.client.disconnect()
            logger.info("Timeseries database connection closed")

