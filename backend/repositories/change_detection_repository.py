"""
Change Detection Repository - Data Access Layer for ClickHouse

Handles all database operations for change detection queries in ClickHouse.
Abstracts query building and result transformation from the service layer.

This repository supports:
- Connection pattern queries
- Traffic statistics queries
- DNS pattern queries
- Process pattern queries
- Error statistics queries

Design:
- Abstract base class defines interface
- Concrete implementation for ClickHouse
- Used by eBPF detector through service layer
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
import structlog
import os

logger = structlog.get_logger(__name__)


# ==========================================
# Port Filtering Configuration
# ==========================================

# Ephemeral port range - these are dynamically assigned client ports
# and should NOT be tracked as connection changes
EPHEMERAL_PORT_START = 32768  # Linux default ephemeral port range start
EPHEMERAL_PORT_END = 65535

# Well-known service ports that should always be tracked
WELL_KNOWN_SERVICE_PORTS = {
    22,    # SSH
    80,    # HTTP
    443,   # HTTPS
    3000,  # Node.js / Frontend
    3306,  # MySQL
    5432,  # PostgreSQL
    5672,  # RabbitMQ AMQP
    6379,  # Redis
    8000,  # Backend API
    8080,  # HTTP Proxy
    8123,  # ClickHouse HTTP
    8443,  # HTTPS Alt
    9000,  # ClickHouse Native
    9090,  # Prometheus
    9200,  # Elasticsearch
    15672, # RabbitMQ Management
    27017, # MongoDB
}

# Maximum port number to consider as a "service port"
# Ports above this are likely ephemeral unless in WELL_KNOWN_SERVICE_PORTS
MAX_SERVICE_PORT = 32767


def is_service_port(port: int) -> bool:
    """
    Check if a port is a service port (not ephemeral).
    
    Service ports are:
    - Well-known service ports (explicitly listed)
    - Ports below the ephemeral range (< 32768)
    
    Ephemeral ports (32768-65535) are dynamically assigned by OS
    for client-side connections and should NOT be tracked.
    """
    if port in WELL_KNOWN_SERVICE_PORTS:
        return True
    if port < EPHEMERAL_PORT_START:
        return True
    return False


# ==========================================
# Data Classes for Query Results
# ==========================================

@dataclass
class ConnectionRecord:
    """Connection record from ClickHouse"""
    source_pod: str
    source_namespace: str
    dest_pod: str
    dest_namespace: str
    dest_port: int
    protocol: str
    direction: str


@dataclass
class TrafficStats:
    """Traffic statistics per connection pair"""
    source_pod: str
    dest_pod: str
    total_bytes: int
    total_packets: int
    avg_latency_ms: float
    max_latency_ms: float
    error_count: int
    retransmit_count: int
    connection_count: int


@dataclass
class DNSRecord:
    """DNS query record"""
    source_pod: str
    source_namespace: str
    query_name: str
    query_type: str
    response_code: str


@dataclass
class ProcessRecord:
    """Process execution record"""
    namespace: str
    pod: str
    container: str
    comm: str
    exe: str
    uid: int
    is_root: bool


@dataclass
class ErrorStats:
    """Error statistics per connection"""
    source_pod: str
    dest_pod: str
    error_type: str
    error_count: int
    retransmit_count: int
    total_events: int


# ==========================================
# Abstract Repository Interface
# ==========================================

class ChangeDetectionRepository(ABC):
    """
    Abstract Change Detection Repository Interface
    
    Defines the contract for change detection data access.
    All ClickHouse queries for anomaly detection go through this interface.
    """
    
    @abstractmethod
    async def get_connections(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None,
        service_ports: Optional[Set[int]] = None
    ) -> List[ConnectionRecord]:
        """
        Get distinct connections with direction information.
        
        Args:
            analysis_id: Analysis identifier
            start_time: Start of time window
            end_time: End of time window
            namespace_scope: Optional list of namespaces to filter
            service_ports: Optional set of known service ports to filter by.
                          If provided, only connections to these ports are returned.
                          If not provided, falls back to ephemeral port filtering.
        """
        pass
    
    @abstractmethod
    async def get_traffic_stats(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[Tuple[str, str], TrafficStats]:
        """Get aggregated traffic statistics per connection pair"""
        pass
    
    @abstractmethod
    async def get_dns_queries(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> List[DNSRecord]:
        """Get distinct DNS query patterns"""
        pass
    
    @abstractmethod
    async def get_process_executions(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> List[ProcessRecord]:
        """Get distinct process execution patterns"""
        pass
    
    @abstractmethod
    async def get_error_stats(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[Tuple[str, str, str], ErrorStats]:
        """Get connection error statistics"""
        pass


# ==========================================
# ClickHouse Implementation
# ==========================================

class ClickHouseChangeDetectionRepository(ChangeDetectionRepository):
    """
    ClickHouse implementation of Change Detection Repository.
    
    Queries the following tables:
    - network_flows: Connection and traffic data
    - dns_queries: DNS query patterns
    - process_events: Process execution patterns
    """
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """Get or create ClickHouse client lazily"""
        if self._client is None:
            try:
                from clickhouse_driver import Client
                
                self._client = Client(
                    host=os.getenv('CLICKHOUSE_HOST', 'clickhouse'),
                    port=int(os.getenv('CLICKHOUSE_PORT', '9000')),
                    user=os.getenv('CLICKHOUSE_USER', 'flowfish'),
                    password=os.getenv('CLICKHOUSE_PASSWORD', ''),
                    database=os.getenv('CLICKHOUSE_DATABASE', 'flowfish'),
                )
                logger.info("ClickHouse client initialized for change detection repository")
            except ImportError:
                logger.error("clickhouse_driver not installed")
                return None
            except Exception as e:
                logger.error("Failed to create ClickHouse client", error=str(e))
                return None
        return self._client
    
    async def get_connections(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None,
        service_ports: Optional[Set[int]] = None
    ) -> List[ConnectionRecord]:
        """
        Query distinct connections with direction information.
        
        Returns connections with:
        - source/dest pod and namespace
        - port and protocol
        - direction (inbound/outbound/internal)
        
        Port Filtering Strategy:
        1. If service_ports provided: Only include connections to those ports
        2. Otherwise: Fallback to ephemeral port filtering (dest_port < 32768)
        
        Args:
            analysis_id: Analysis identifier for filtering
            start_time: Start of time window
            end_time: End of time window  
            namespace_scope: If provided, filter by these namespaces (source or dest)
            service_ports: If provided, only return connections to these ports
        """
        client = self._get_client()
        if not client:
            return []
        
        # Build scope filter - always include analysis_id for data isolation,
        # add namespace filter when scope is narrower than cluster-wide
        namespace_filter = ""
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'analysis_id': str(analysis_id)
        }
        
        if namespace_scope:
            namespace_filter = "AND analysis_id = %(analysis_id)s AND (source_namespace IN %(namespaces)s OR dest_namespace IN %(namespaces)s)"
            params['namespaces'] = namespace_scope
        else:
            namespace_filter = "AND analysis_id = %(analysis_id)s"
        
        # Build port filter based on whether service_ports is provided
        if service_ports and len(service_ports) > 0:
            # Use explicit service port list from ServicePortRegistry
            port_filter = "AND dest_port IN %(service_ports)s"
            params['service_ports'] = list(service_ports)
            logger.debug(
                "Using explicit service port filter",
                port_count=len(service_ports),
                sample_ports=list(service_ports)[:10]
            )
        else:
            # Fallback: filter out ephemeral ports
            port_filter = "AND dest_port < %(ephemeral_start)s"
            params['ephemeral_start'] = EPHEMERAL_PORT_START
            logger.debug("Using ephemeral port filter (fallback)")
        
        query = f"""
        SELECT DISTINCT
            source_pod,
            source_namespace,
            dest_pod,
            dest_namespace,
            dest_port,
            protocol,
            direction
        FROM network_flows
        WHERE timestamp >= %(start_time)s
          AND timestamp < %(end_time)s
          AND source_pod != ''
          AND dest_pod != ''
          {port_filter}
          {namespace_filter}
        """
        
        try:
            result = client.execute(query, params)
            
            connections = []
            for row in result:
                dest_port = row[4]
                
                # If service_ports provided, trust the query filter
                # Otherwise, double-check with is_service_port
                if not service_ports and not is_service_port(dest_port):
                    continue
                    
                connections.append(ConnectionRecord(
                    source_pod=row[0],
                    source_namespace=row[1] or '',
                    dest_pod=row[2],
                    dest_namespace=row[3] or '',
                    dest_port=dest_port,
                    protocol=row[5] or 'TCP',
                    direction=row[6] or 'outbound'
                ))
            
            logger.info(
                "ClickHouse query: connections",
                analysis_id=analysis_id,
                time_window=f"{start_time.isoformat()} to {end_time.isoformat()}",
                rows_returned=len(connections),
                raw_rows=len(result),
                filter_type="namespace" if namespace_scope else "analysis_id",
                namespace_scope=namespace_scope,
                service_ports_provided=service_ports is not None
            )
            return connections
            
        except Exception as e:
            logger.error("Failed to query connections", error=str(e))
            return []
    
    async def get_traffic_stats(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[Tuple[str, str], TrafficStats]:
        """
        Query aggregated traffic statistics per connection pair.
        
        Aggregates:
        - bytes sent/received
        - packets sent/received
        - latency (avg and max)
        - errors and retransmits
        """
        client = self._get_client()
        if not client:
            return {}
        
        # Build namespace filter - always include analysis_id for isolation
        namespace_filter = ""
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'analysis_id': str(analysis_id)
        }
        
        if namespace_scope:
            namespace_filter = "AND analysis_id = %(analysis_id)s AND (source_namespace IN %(namespaces)s OR dest_namespace IN %(namespaces)s)"
            params['namespaces'] = namespace_scope
        else:
            namespace_filter = "AND analysis_id = %(analysis_id)s"
        
        query = f"""
        SELECT
            source_pod,
            dest_pod,
            sum(bytes_sent + bytes_received) as total_bytes,
            sum(packets_sent + packets_received) as total_packets,
            avg(latency_ms) as avg_latency,
            max(latency_ms) as max_latency,
            sum(error_count) as errors,
            sum(retransmit_count) as retransmits,
            count(*) as conn_count
        FROM network_flows
        WHERE timestamp >= %(start_time)s
          AND timestamp < %(end_time)s
          AND source_pod != ''
          AND dest_pod != ''
          {namespace_filter}
        GROUP BY source_pod, dest_pod
        """
        
        try:
            result = client.execute(query, params)
            
            stats = {}
            for row in result:
                key = (row[0], row[1])
                stats[key] = TrafficStats(
                    source_pod=row[0],
                    dest_pod=row[1],
                    total_bytes=row[2] or 0,
                    total_packets=row[3] or 0,
                    avg_latency_ms=float(row[4] or 0),
                    max_latency_ms=float(row[5] or 0),
                    error_count=row[6] or 0,
                    retransmit_count=row[7] or 0,
                    connection_count=row[8] or 0
                )
            
            logger.info(
                "ClickHouse query: traffic_stats",
                analysis_id=analysis_id,
                time_window=f"{start_time.isoformat()} to {end_time.isoformat()}",
                rows_returned=len(stats),
                filter_type="namespace" if namespace_scope else "analysis_id"
            )
            return stats
            
        except Exception as e:
            logger.error("Failed to query traffic stats", error=str(e))
            return {}
    
    async def get_dns_queries(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> List[DNSRecord]:
        """
        Query distinct DNS query patterns.
        
        Returns:
        - source pod/namespace
        - query name and type
        - response code
        """
        client = self._get_client()
        if not client:
            return []
        
        # Build namespace filter - always include analysis_id for isolation
        namespace_filter = ""
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'analysis_id': str(analysis_id)
        }
        
        if namespace_scope:
            namespace_filter = "AND analysis_id = %(analysis_id)s AND source_namespace IN %(namespaces)s"
            params['namespaces'] = namespace_scope
        else:
            namespace_filter = "AND analysis_id = %(analysis_id)s"
        
        query = f"""
        SELECT DISTINCT
            source_pod,
            source_namespace,
            query_name,
            query_type,
            response_code
        FROM dns_queries
        WHERE timestamp >= %(start_time)s
          AND timestamp < %(end_time)s
          AND source_pod != ''
          {namespace_filter}
        """
        
        try:
            result = client.execute(query, params)
            
            queries = []
            for row in result:
                queries.append(DNSRecord(
                    source_pod=row[0],
                    source_namespace=row[1] or '',
                    query_name=row[2],
                    query_type=row[3] or 'A',
                    response_code=row[4] or 'NOERROR'
                ))
            
            logger.info(
                "ClickHouse query: dns_queries",
                analysis_id=analysis_id,
                time_window=f"{start_time.isoformat()} to {end_time.isoformat()}",
                rows_returned=len(queries),
                filter_type="namespace" if namespace_scope else "analysis_id"
            )
            return queries
            
        except Exception as e:
            logger.error("Failed to query DNS patterns", error=str(e))
            return []
    
    async def get_process_executions(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> List[ProcessRecord]:
        """
        Query distinct process execution patterns.
        
        Returns exec events with:
        - pod/container context
        - command and executable
        - UID (to detect root)
        """
        client = self._get_client()
        if not client:
            return []
        
        # Build namespace filter - always include analysis_id for isolation
        namespace_filter = ""
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'analysis_id': str(analysis_id)
        }
        
        if namespace_scope:
            namespace_filter = "AND analysis_id = %(analysis_id)s AND namespace IN %(namespaces)s"
            params['namespaces'] = namespace_scope
        else:
            namespace_filter = "AND analysis_id = %(analysis_id)s"
        
        query = f"""
        SELECT DISTINCT
            namespace,
            pod,
            container,
            comm,
            exe,
            uid
        FROM process_events
        WHERE timestamp >= %(start_time)s
          AND timestamp < %(end_time)s
          AND event_type = 'exec'
          AND pod != ''
          {namespace_filter}
        """
        
        try:
            result = client.execute(query, params)
            
            processes = []
            for row in result:
                processes.append(ProcessRecord(
                    namespace=row[0] or '',
                    pod=row[1],
                    container=row[2] or '',
                    comm=row[3],
                    exe=row[4] or '',
                    uid=row[5] or 0,
                    is_root=(row[5] == 0)
                ))
            
            logger.info(
                "ClickHouse query: process_executions",
                analysis_id=analysis_id,
                time_window=f"{start_time.isoformat()} to {end_time.isoformat()}",
                rows_returned=len(processes),
                filter_type="namespace" if namespace_scope else "analysis_id"
            )
            return processes
            
        except Exception as e:
            logger.error("Failed to query process executions", error=str(e))
            return []
    
    async def get_error_stats(
        self,
        analysis_id: str,
        start_time: datetime,
        end_time: datetime,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[Tuple[str, str, str], ErrorStats]:
        """
        Query connection error statistics.
        
        Groups by source/dest pod and error type.
        """
        client = self._get_client()
        if not client:
            return {}
        
        # Build namespace filter - always include analysis_id for isolation
        namespace_filter = ""
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'analysis_id': str(analysis_id)
        }
        
        if namespace_scope:
            namespace_filter = "AND analysis_id = %(analysis_id)s AND (source_namespace IN %(namespaces)s OR dest_namespace IN %(namespaces)s)"
            params['namespaces'] = namespace_scope
        else:
            namespace_filter = "AND analysis_id = %(analysis_id)s"
        
        query = f"""
        SELECT
            source_pod,
            dest_pod,
            error_type,
            sum(error_count) as errors,
            sum(retransmit_count) as retransmits,
            count(*) as total
        FROM network_flows
        WHERE timestamp >= %(start_time)s
          AND timestamp < %(end_time)s
          AND source_pod != ''
          AND dest_pod != ''
          AND (error_count > 0 OR error_type != '')
          {namespace_filter}
        GROUP BY source_pod, dest_pod, error_type
        """
        
        try:
            result = client.execute(query, params)
            
            stats = {}
            for row in result:
                key = (row[0], row[1], row[2] or 'unknown')
                stats[key] = ErrorStats(
                    source_pod=row[0],
                    dest_pod=row[1],
                    error_type=row[2] or 'unknown',
                    error_count=row[3] or 0,
                    retransmit_count=row[4] or 0,
                    total_events=row[5] or 0
                )
            
            logger.info(
                "ClickHouse query: error_stats",
                analysis_id=analysis_id,
                time_window=f"{start_time.isoformat()} to {end_time.isoformat()}",
                rows_returned=len(stats),
                filter_type="namespace" if namespace_scope else "analysis_id"
            )
            return stats
            
        except Exception as e:
            logger.error("Failed to query error stats", error=str(e))
            return {}


# ==========================================
# Factory Function
# ==========================================

_repository_instance: Optional[ChangeDetectionRepository] = None


def get_change_detection_repository() -> ChangeDetectionRepository:
    """
    Get singleton instance of ChangeDetectionRepository.
    
    Returns ClickHouse implementation by default.
    """
    global _repository_instance
    
    if _repository_instance is None:
        _repository_instance = ClickHouseChangeDetectionRepository()
        logger.info("Created ChangeDetectionRepository instance")
    
    return _repository_instance
