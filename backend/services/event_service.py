"""
Event Service - Business Logic Layer

Orchestrates event-related operations between repositories and provides
business logic that doesn't belong in controllers or data access layers.

Responsibilities:
- Aggregate data from multiple repositories
- Apply business rules and transformations
- Handle caching strategies
- Provide unified interface for controllers
"""

from typing import Any, Dict, Optional
import asyncio
import structlog

from schemas.events import (
    EventStats,
    TimeRange,
    NamespaceCount,
    PodCount,
    DnsQueryEvent,
    DnsQueriesResponse,
    SniEvent,
    SniEventsResponse,
    ProcessEvent,
    ProcessEventsResponse,
    FileEvent,
    FileEventsResponse,
    SecurityEvent,
    SecurityEventsResponse,
    OomEvent,
    OomEventsResponse,
    BindEvent,
    BindEventsResponse,
    MountEvent,
    MountEventsResponse,
    NetworkFlowEvent,
    NetworkFlowsResponse,
    TcpConnectionEvent,
    TcpConnectionsResponse,
    GenericEvent,
    GenericEventsResponse,
)
from repositories.event_repository import EventRepository
from typing import List

logger = structlog.get_logger(__name__)


class EventService:
    """
    Event Service
    
    Encapsulates all event-related business logic.
    Uses dependency injection for repository access.
    """
    
    def __init__(self, event_repository: EventRepository):
        """
        Initialize service with repository dependency
        
        Args:
            event_repository: EventRepository implementation
        """
        self.repository = event_repository
    
    async def get_event_stats(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None
    ) -> EventStats:
        """
        Get comprehensive event statistics
        
        Aggregates data from multiple repository calls into a single response.
        
        Args:
            cluster_id: Cluster to get stats for
            analysis_id: Optional analysis filter
            
        Returns:
            EventStats with counts, top namespaces/pods, time range
        """
        logger.info(
            "Getting event statistics",
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        
        # Fetch all data in parallel for better performance
        event_counts_task = self.repository.get_event_counts_by_type(cluster_id, analysis_id)
        top_namespaces_task = self.repository.get_top_namespaces(cluster_id, analysis_id, limit=10)
        top_pods_task = self.repository.get_top_pods(cluster_id, analysis_id, limit=10)
        time_range_task = self.repository.get_time_range(cluster_id, analysis_id)
        
        # Execute all queries in parallel
        event_counts, top_namespaces_raw, top_pods_raw, time_range_raw = await asyncio.gather(
            event_counts_task,
            top_namespaces_task,
            top_pods_task,
            time_range_task
        )
        
        # Calculate total
        total_events = sum(event_counts.values())
        
        # Transform to DTOs
        top_namespaces = [
            NamespaceCount(**ns) for ns in top_namespaces_raw
        ]
        
        top_pods = [
            PodCount(**pod) for pod in top_pods_raw
        ]
        
        time_range = TimeRange(
            start=time_range_raw.get("start"),
            end=time_range_raw.get("end")
        )
        
        # Build response (use empty string for null values - frontend compatibility)
        stats = EventStats(
            cluster_id=str(cluster_id),
            analysis_id=str(analysis_id) if analysis_id else "",
            total_events=total_events,
            event_counts=event_counts,
            time_range=time_range,
            top_namespaces=top_namespaces,
            top_pods=top_pods
        )
        
        logger.info(
            "Event statistics retrieved",
            cluster_id=cluster_id,
            total_events=total_events,
            event_types=len(event_counts)
        )
        
        return stats
    
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
    ) -> DnsQueriesResponse:
        """
        Get DNS query events
        
        Args:
            cluster_id: Cluster to query
            analysis_id: Optional analysis filter
            namespace: Optional namespace filter
            search: Full-text search across query_name, dns_server_ip, pod, namespace
            start_time: Optional start time filter (ISO format)
            end_time: Optional end time filter (ISO format)
            limit: Max results
            offset: Pagination offset
            
        Returns:
            DnsQueriesResponse with queries and total count
        """
        logger.info(
            "Getting DNS queries",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            limit=limit,
            offset=offset
        )
        
        queries_raw, total = await self.repository.get_dns_queries(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        # Transform to response DTOs (matching frontend interface)
        # NOTE: ClickHouse uses source_namespace, source_pod, source_container
        # but frontend expects namespace, pod, container
        queries = []
        for q in queries_raw:
            try:
                # Parse event_data_json for fallback values (old data may have empty columns)
                raw_data = {}
                if q.get("event_data_json"):
                    try:
                        import json
                        raw_data = json.loads(q.get("event_data_json", "{}"))
                    except:
                        pass
                
                # Get values with fallback chain: column -> raw_data -> default
                ns = q.get("source_namespace") or raw_data.get("src_namespace") or raw_data.get("namespace") or ""
                pod_name = q.get("source_pod") or raw_data.get("src_pod") or raw_data.get("pod") or ""
                container = q.get("source_container") or raw_data.get("src_container") or raw_data.get("container")
                query_nm = q.get("query_name") or raw_data.get("name") or raw_data.get("query_name") or ""
                query_tp = q.get("query_type") or raw_data.get("qtype") or raw_data.get("query_type") or ""
                resp_code = q.get("response_code") or raw_data.get("rcode") or raw_data.get("response_code") or ""
                # response_ips can be in 'addresses' or 'answers' field
                resp_ips = q.get("response_ips") or raw_data.get("addresses") or raw_data.get("answers") or []
                dns_server = q.get("dns_server_ip") or raw_data.get("dst_ip") or raw_data.get("dns_server_ip") or ""
                
                # Parse latency - latency_ns can be string like "0ns" or "123456ns"
                latency = q.get("latency_ms") or 0
                if not latency:
                    latency_ns_val = raw_data.get("latency_ns") or raw_data.get("latency_ns_raw") or 0
                    if isinstance(latency_ns_val, str):
                        # Remove 'ns' suffix if present
                        latency_ns_val = latency_ns_val.strip().rstrip('ns').strip()
                        try:
                            latency_ns_val = float(latency_ns_val) if latency_ns_val else 0
                        except:
                            latency_ns_val = 0
                    latency = float(latency_ns_val) / 1000000 if latency_ns_val else 0
                
                queries.append(DnsQueryEvent(
                    timestamp=q.get("timestamp"),
                    event_id=str(q.get("event_id", "")),
                    event_type="dns_query",
                    cluster_id=str(q.get("cluster_id", cluster_id)),
                    cluster_name=q.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(q.get("analysis_id", analysis_id or "")),
                    namespace=ns,
                    pod=pod_name,
                    container=container,
                    query_name=query_nm,
                    query_type=query_tp,
                    response_code=resp_code,
                    response_ips=resp_ips if isinstance(resp_ips, list) else [],
                    latency_ms=float(latency),
                    dns_server_ip=dns_server
                ))
            except Exception as e:
                logger.warning("Failed to parse DNS query", error=str(e), raw=q)
        
        return DnsQueriesResponse(queries=queries, total=total)
    
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
    ) -> SniEventsResponse:
        """
        Get TLS/SNI events
        
        Args:
            cluster_id: Cluster to query
            analysis_id: Optional analysis filter
            namespace: Optional namespace filter
            search: Full-text search across server_name, dest_ip, pod, namespace, comm
            start_time: Optional start time filter (ISO format)
            end_time: Optional end time filter (ISO format)
            limit: Max results
            offset: Pagination offset
            
        Returns:
            SniEventsResponse with events and total count
        """
        logger.info(
            "Getting SNI events",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            limit=limit,
            offset=offset
        )
        
        events_raw, total = await self.repository.get_sni_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        # Transform to response DTOs (matching frontend interface)
        # NOTE: ClickHouse uses sni_name, dst_ip, dst_port
        # but frontend expects server_name, dest_ip, dest_port
        events = []
        for e in events_raw:
            try:
                # Parse event_data_json for fallback values (old data may have empty columns)
                raw_data = {}
                if e.get("event_data_json"):
                    try:
                        import json
                        raw_data = json.loads(e.get("event_data_json", "{}"))
                    except:
                        pass
                
                # Get values with fallback chain: column -> raw_data -> default
                sni_name = e.get("sni_name") or raw_data.get("name") or raw_data.get("sni_name") or ""
                dst_ip = e.get("dst_ip") or raw_data.get("dst_ip") or ""
                dst_port = e.get("dst_port") or raw_data.get("dst_port") or 0
                tls_ver = e.get("tls_version") or raw_data.get("version") or raw_data.get("tls_version") or ""
                cipher = e.get("cipher_suite") or raw_data.get("cipher_suite") or ""
                ns = e.get("namespace") or raw_data.get("namespace") or raw_data.get("src_namespace") or ""
                pod_name = e.get("pod") or raw_data.get("pod") or raw_data.get("src_pod") or ""
                
                events.append(SniEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="sni_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=ns,
                    pod=pod_name,
                    container=e.get("container") or raw_data.get("container") or raw_data.get("src_container"),
                    server_name=sni_name,
                    src_ip=e.get("src_ip") or raw_data.get("src_ip"),
                    src_port=int(e.get("src_port") or raw_data.get("src_port") or 0) or None,
                    dest_ip=dst_ip,
                    dest_port=int(dst_port),
                    tls_version=tls_ver,
                    cipher_suite=cipher,
                    pid=int(e.get("pid") or raw_data.get("pid") or 0) or None,
                    comm=e.get("comm") or raw_data.get("comm")
                ))
            except Exception as e_err:
                logger.warning("Failed to parse SNI event", error=str(e_err), raw=e)
        
        return SniEventsResponse(events=events, total=total)
    
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
    ) -> ProcessEventsResponse:
        """Get process events"""
        logger.info("Getting process events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_process_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                # Parse event_data_json for fallback values (old data may have empty columns)
                raw_data = {}
                if e.get("event_data_json"):
                    try:
                        import json
                        raw_data = json.loads(e.get("event_data_json", "{}"))
                    except:
                        pass
                
                # Parse args if it's a string
                args = e.get("args") or raw_data.get("args") or []
                if isinstance(args, str):
                    try:
                        import json
                        args = json.loads(args)
                    except:
                        # Handle space-separated args string from Inspector Gadget
                        args = args.split('\xa0') if '\xa0' in args else [args] if args else []
                
                # Get values with fallback chain: column -> raw_data -> default
                ns = e.get("namespace") or raw_data.get("namespace") or raw_data.get("src_namespace") or ""
                pod_name = e.get("pod") or raw_data.get("pod") or raw_data.get("src_pod") or ""
                container = e.get("container") or raw_data.get("container") or raw_data.get("src_container")
                pid_val = e.get("pid") or raw_data.get("pid") or 0
                ppid_val = e.get("ppid") or raw_data.get("ppid") or 0
                comm_val = e.get("comm") or raw_data.get("comm") or ""
                exe_val = e.get("exe") or raw_data.get("exepath") or raw_data.get("exe") or ""
                event_type_val = e.get("event_type") or raw_data.get("type") or "exec"
                uid_val = e.get("uid") or raw_data.get("uid") or 0
                gid_val = e.get("gid") or raw_data.get("gid") or 0
                
                events.append(ProcessEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="process_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=ns,
                    pod=pod_name,
                    container=container,
                    pid=int(pid_val),
                    ppid=int(ppid_val),
                    comm=comm_val,
                    exe=exe_val,
                    args=args,
                    event_subtype=event_type_val,
                    exit_code=e.get("exit_code"),
                    signal=e.get("signal"),
                    uid=int(uid_val),
                    gid=int(gid_val)
                ))
            except Exception as err:
                logger.warning("Failed to parse process event", error=str(err), raw=e)
        
        return ProcessEventsResponse(events=events, total=total)
    
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
    ) -> FileEventsResponse:
        """Get file operation events"""
        logger.info("Getting file events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_file_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(FileEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="file_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("namespace", ""),
                    pod=e.get("pod", ""),
                    container=e.get("container"),
                    operation=e.get("operation", ""),
                    file_path=e.get("file_path", ""),
                    file_flags=e.get("file_flags", ""),
                    file_mode=int(e.get("file_mode", 0)),
                    bytes=int(e.get("bytes", 0)),
                    duration_us=int(e.get("duration_us", 0)),
                    error_code=int(e.get("error_code", 0)),
                    pid=int(e.get("pid", 0)),
                    comm=e.get("comm", ""),
                    uid=int(e.get("uid", 0)),
                    gid=int(e.get("gid", 0))
                ))
            except Exception as err:
                logger.warning("Failed to parse file event", error=str(err), raw=e)
        
        return FileEventsResponse(events=events, total=total)
    
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
    ) -> SecurityEventsResponse:
        """Get security/capability events"""
        logger.info("Getting security events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_security_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(SecurityEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="security_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("namespace", ""),
                    pod=e.get("pod", ""),
                    container=e.get("container"),
                    security_type="capability",
                    capability=e.get("capability"),
                    syscall=e.get("syscall"),
                    verdict=e.get("verdict", "allowed"),
                    pid=int(e.get("pid", 0)),
                    comm=e.get("comm", ""),
                    uid=int(e.get("uid", 0)),
                    gid=int(e.get("gid", 0))
                ))
            except Exception as err:
                logger.warning("Failed to parse security event", error=str(err), raw=e)
        
        return SecurityEventsResponse(events=events, total=total)
    
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
    ) -> OomEventsResponse:
        """Get OOM kill events"""
        logger.info("Getting OOM events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_oom_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(OomEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="oom_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("namespace", ""),
                    pod=e.get("pod", ""),
                    container=e.get("container"),
                    node=e.get("node"),
                    pid=int(e.get("pid", 0)),
                    comm=e.get("comm", ""),
                    memory_limit=int(e.get("memory_limit", 0)),
                    memory_usage=int(e.get("memory_usage", 0)),
                    memory_pages_total=int(e.get("memory_pages_total", 0)),
                    memory_pages_free=int(e.get("memory_pages_free", 0)),
                    cgroup_path=e.get("cgroup_path", "")
                ))
            except Exception as err:
                logger.warning("Failed to parse OOM event", error=str(err), raw=e)
        
        return OomEventsResponse(events=events, total=total)
    
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
    ) -> BindEventsResponse:
        """Get socket bind events"""
        logger.info("Getting bind events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_bind_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                # Parse event_data_json for fallback values (old data may have empty columns)
                raw_data = {}
                if e.get("event_data_json"):
                    try:
                        import json
                        raw_data = json.loads(e.get("event_data_json", "{}"))
                    except:
                        pass
                
                # Get values with fallback chain: column -> raw_data -> default
                ns = e.get("namespace") or raw_data.get("namespace") or raw_data.get("src_namespace") or ""
                pod_name = e.get("pod") or raw_data.get("pod") or raw_data.get("src_pod") or ""
                container = e.get("container") or raw_data.get("container") or raw_data.get("src_container")
                node = e.get("node") or raw_data.get("node") or raw_data.get("src_node")
                bind_addr = e.get("bind_addr") or raw_data.get("addr") or raw_data.get("dst_ip") or ""
                bind_port = e.get("bind_port") or raw_data.get("port") or raw_data.get("dst_port") or 0
                protocol = e.get("protocol") or raw_data.get("protocol") or "TCP"
                interface = e.get("interface") or raw_data.get("if") or raw_data.get("interface") or ""
                error_code = e.get("error_code") or raw_data.get("error") or raw_data.get("error_raw") or 0
                pid_val = e.get("pid") or raw_data.get("pid") or 0
                comm_val = e.get("comm") or raw_data.get("comm") or ""
                uid_val = e.get("uid") or raw_data.get("uid") or 0
                
                events.append(BindEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="bind_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=ns,
                    pod=pod_name,
                    container=container,
                    node=node,
                    bind_addr=bind_addr,
                    bind_port=int(bind_port),
                    protocol=protocol,
                    interface=interface,
                    error_code=int(error_code),
                    pid=int(pid_val),
                    comm=comm_val,
                    uid=int(uid_val)
                ))
            except Exception as err:
                logger.warning("Failed to parse bind event", error=str(err), raw=e)
        
        return BindEventsResponse(events=events, total=total)
    
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
    ) -> MountEventsResponse:
        """Get mount events"""
        logger.info("Getting mount events", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_mount_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(MountEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="mount_event",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("namespace", ""),
                    pod=e.get("pod", ""),
                    container=e.get("container"),
                    node=e.get("node"),
                    operation=e.get("operation", "mount"),
                    source=e.get("source", ""),
                    target=e.get("target", ""),
                    fs_type=e.get("fs_type", ""),
                    flags=e.get("flags", ""),
                    options=e.get("options", ""),
                    error_code=int(e.get("error_code", 0)),
                    pid=int(e.get("pid", 0)),
                    comm=e.get("comm", "")
                ))
            except Exception as err:
                logger.warning("Failed to parse mount event", error=str(err), raw=e)
        
        return MountEventsResponse(events=events, total=total)
    
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
    ) -> NetworkFlowsResponse:
        """Get network flow events"""
        logger.info("Getting network flows", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_network_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                # Parse event_data_json for fallback values (old data may have empty columns)
                raw_data = {}
                if e.get("event_data_json"):
                    try:
                        import json
                        raw_data = json.loads(e.get("event_data_json", "{}"))
                    except:
                        pass
                
                # Get values with fallback chain: column -> raw_data -> default
                ns = e.get("source_namespace") or raw_data.get("src_namespace") or raw_data.get("namespace") or ""
                pod_name = e.get("source_pod") or raw_data.get("src_pod") or raw_data.get("pod") or ""
                container = e.get("source_container") or raw_data.get("src_container") or raw_data.get("container")
                src_ip = e.get("source_ip") or raw_data.get("src_ip") or ""
                src_port = e.get("source_port") or raw_data.get("src_port") or 0
                dst_ip = e.get("dest_ip") or raw_data.get("dst_ip") or ""
                dst_port = e.get("dest_port") or raw_data.get("dst_port") or 0
                protocol = e.get("protocol") or raw_data.get("protocol") or "TCP"
                direction = e.get("direction") or raw_data.get("direction") or "outbound"
                bytes_s = e.get("bytes_sent") or raw_data.get("bytes_sent") or 0
                bytes_r = e.get("bytes_received") or raw_data.get("bytes_received") or 0
                conn_state = e.get("connection_state") or raw_data.get("type") or raw_data.get("event_subtype") or ""
                
                # Parse error fields from ClickHouse or raw_data
                error_count = e.get("error_count") or raw_data.get("error_count") or raw_data.get("error") or 0
                retransmit_count = e.get("retransmit_count") or raw_data.get("retransmit_count") or raw_data.get("retransmits") or 0
                error_type = e.get("error_type") or raw_data.get("error_type") or ""
                
                # Parse latency - latency_ns can be string like "0ns" or "123456ns"
                latency = e.get("latency_ms") or 0
                if not latency:
                    latency_ns_val = raw_data.get("latency_ns") or raw_data.get("latency_ns_raw") or 0
                    if isinstance(latency_ns_val, str):
                        latency_ns_val = latency_ns_val.strip().rstrip('ns').strip()
                        try:
                            latency_ns_val = float(latency_ns_val) if latency_ns_val else 0
                        except:
                            latency_ns_val = 0
                    latency = float(latency_ns_val) / 1000000 if latency_ns_val else 0
                
                events.append(NetworkFlowEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="network_flow",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=ns,
                    pod=pod_name,
                    container=container,
                    source_ip=src_ip,
                    source_port=int(src_port),
                    dest_ip=dst_ip,
                    dest_port=int(dst_port),
                    protocol=protocol,
                    direction=direction,
                    bytes_sent=int(bytes_s),
                    bytes_received=int(bytes_r),
                    latency_ms=float(latency),
                    connection_state=conn_state,
                    # Error fields from ClickHouse
                    error_count=int(error_count) if error_count else 0,
                    retransmit_count=int(retransmit_count) if retransmit_count else 0,
                    error_type=error_type if error_type else None
                ))
            except Exception as err:
                logger.warning("Failed to parse network flow", error=str(err), raw=e)
        
        return NetworkFlowsResponse(events=events, total=total)
    
    async def get_tcp_connections(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> TcpConnectionsResponse:
        """Get TCP connection lifecycle events"""
        logger.info("Getting TCP connections", cluster_id=cluster_id, analysis_id=analysis_id, search=search)
        
        events_raw, total = await self.repository.get_tcp_connections(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(TcpConnectionEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type="tcp_connection",
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("source_namespace", ""),
                    pod=e.get("source_pod", ""),
                    container=e.get("source_container"),
                    source_ip=e.get("source_ip", ""),
                    source_port=int(e.get("source_port", 0)),
                    dest_ip=e.get("dest_ip", ""),
                    dest_port=int(e.get("dest_port", 0)),
                    old_state=e.get("old_state", ""),
                    new_state=e.get("new_state", ""),
                    pid=int(e.get("pid", 0)),
                    comm=e.get("comm", "")
                ))
            except Exception as err:
                logger.warning("Failed to parse TCP connection", error=str(err), raw=e)
        
        return TcpConnectionsResponse(events=events, total=total)
    
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
    ) -> GenericEventsResponse:
        """Get all events with filtering and search"""
        logger.info("Getting all events", 
                   cluster_id=cluster_id, 
                   analysis_id=analysis_id,
                   event_types=event_types,
                   search=search)
        
        events_raw, total = await self.repository.get_all_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            event_types=event_types,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        
        events = []
        for e in events_raw:
            try:
                events.append(GenericEvent(
                    timestamp=e.get("timestamp"),
                    event_id=str(e.get("event_id", "")),
                    event_type=e.get("event_type", "unknown"),
                    cluster_id=str(e.get("cluster_id", cluster_id)),
                    cluster_name=e.get("cluster_name"),  # Include cluster name for multi-cluster visibility
                    analysis_id=str(e.get("analysis_id", analysis_id or "")),
                    namespace=e.get("namespace", ""),
                    pod=e.get("pod", ""),
                    container=e.get("container"),
                    source=e.get("source"),
                    target=e.get("target"),
                    details=e.get("details", ""),
                    data={}
                ))
            except Exception as err:
                logger.warning("Failed to parse event", error=str(err), raw=e)
        
        has_more = (offset + len(events)) < total
        return GenericEventsResponse(events=events, total=total, has_more=has_more)

    async def get_event_histogram(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        bucket_count: int = 60
    ) -> Dict[str, Any]:
        """Get time-bucketed event histogram for timeline visualization"""
        return await self.repository.get_event_histogram(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            event_types=event_types,
            start_time=start_time,
            end_time=end_time,
            bucket_count=bucket_count
        )


# Service factory for dependency injection
def get_event_service() -> EventService:
    """
    Factory function for EventService dependency injection
    
    Creates service with its repository dependency.
    Can be overridden in tests.
    """
    from repositories.event_repository import get_event_repository
    
    repository = get_event_repository()
    return EventService(event_repository=repository)

