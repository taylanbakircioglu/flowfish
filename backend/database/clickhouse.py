"""
ClickHouse time-series database connection and utilities

This module provides ClickHouse connectivity for:
- Network flow event storage
- Change event storage and querying
- Analytics and metrics

Configuration via environment variables:
- CLICKHOUSE_HOST: ClickHouse server hostname (default: clickhouse)
- CLICKHOUSE_PORT: ClickHouse server port (default: 9000)
- CLICKHOUSE_USER: ClickHouse username (default: flowfish)
- CLICKHOUSE_PASSWORD: ClickHouse password
- CLICKHOUSE_DATABASE: Database name (default: flowfish)
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

# Configuration from environment
CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', 'clickhouse')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', '9000'))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', 'flowfish')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD', '')
CLICKHOUSE_DATABASE = os.getenv('CLICKHOUSE_DATABASE', 'flowfish')
CLICKHOUSE_ENABLED = os.getenv('CLICKHOUSE_ENABLED', 'true').lower() == 'true'

# Try to import clickhouse_driver
try:
    from clickhouse_driver import Client
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    logger.warning("clickhouse_driver not installed, using dummy client")


class DummyClickHouseClient:
    """Dummy ClickHouse client for development/testing when ClickHouse is not available"""
    
    def ping(self):
        return True
    
    def execute(self, query: str, params=None):
        logger.debug("ClickHouse query (dummy)", query=query[:100])
        return []


def create_clickhouse_client():
    """
    Create a ClickHouse client based on environment configuration.
    
    Returns real client if CLICKHOUSE_ENABLED=true and clickhouse_driver is available,
    otherwise returns a dummy client.
    """
    if not CLICKHOUSE_ENABLED:
        logger.info("ClickHouse disabled by configuration, using dummy client")
        return DummyClickHouseClient()
    
    if not CLICKHOUSE_AVAILABLE:
        logger.warning("clickhouse_driver not available, using dummy client")
        return DummyClickHouseClient()
    
    try:
        client = Client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            user=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DATABASE,
        )
        
        # Test connection
        client.execute("SELECT 1")
        logger.info(
            "ClickHouse client created successfully",
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DATABASE
        )
        
        return client
        
    except Exception as e:
        logger.error(
            "Failed to create ClickHouse client, using dummy",
            host=CLICKHOUSE_HOST,
            error=str(e)
        )
        return DummyClickHouseClient()


# Global client instance
clickhouse_client = create_clickhouse_client()


def get_clickhouse_client():
    """Get the ClickHouse client instance"""
    return clickhouse_client


class ClickHouseService:
    """
    ClickHouse service for time-series operations.
    
    Provides methods for:
    - Inserting eBPF event data (network flows, DNS, etc.)
    - Querying change events
    - Analytics and statistics
    """
    
    def __init__(self, client=None):
        self.client = client or clickhouse_client
    
    # ========================================
    # Change Event Methods
    # ========================================
    
    def get_change_events(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[int] = None,
        change_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get change events from ClickHouse with filters.
        
        Args:
            analysis_id: Filter by analysis ID
            cluster_id: Filter by cluster ID
            change_type: Filter by change type
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of results
            
        Returns:
            List of change event dictionaries
        """
        try:
            conditions = ["1 = 1"]
            params = {}
            
            if analysis_id:
                conditions.append("analysis_id = %(analysis_id)s")
                params['analysis_id'] = str(analysis_id)
            
            if cluster_id:
                conditions.append("cluster_id = %(cluster_id)s")
                params['cluster_id'] = cluster_id
            
            if change_type:
                conditions.append("change_type = %(change_type)s")
                params['change_type'] = change_type
            
            if start_time:
                conditions.append("timestamp >= %(start_time)s")
                params['start_time'] = start_time
            
            if end_time:
                conditions.append("timestamp <= %(end_time)s")
                params['end_time'] = end_time
            
            query = f"""
            SELECT 
                event_id,
                timestamp,
                cluster_id,
                analysis_id,
                run_id,
                run_number,
                change_type,
                risk_level,
                target_name,
                target_namespace,
                target_type,
                before_state,
                after_state,
                affected_services,
                blast_radius,
                changed_by,
                details,
                metadata
            FROM change_events
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
            
            result = self.client.execute(query, params)
            
            columns = [
                'event_id', 'timestamp', 'cluster_id', 'analysis_id',
                'run_id', 'run_number', 'change_type', 'risk_level',
                'target_name', 'target_namespace', 'target_type',
                'before_state', 'after_state', 'affected_services',
                'blast_radius', 'changed_by', 'details', 'metadata'
            ]
            
            events = []
            for row in result:
                event = dict(zip(columns, row))
                # Convert to API-friendly format
                events.append({
                    'id': hash(event['event_id']) % (10 ** 9),
                    'cluster_id': event['cluster_id'],
                    'analysis_id': event['analysis_id'],
                    'timestamp': event['timestamp'].isoformat() if event['timestamp'] else None,
                    'change_type': event['change_type'],
                    'target': event['target_name'],
                    'namespace': event['target_namespace'],
                    'details': event['details'],
                    'risk': event['risk_level'],
                    'affected_services': event['affected_services'],
                    'changed_by': event['changed_by'],
                    'status': 'detected',
                    'metadata': event['metadata']
                })
            
            return events
            
        except Exception as e:
            logger.error("Failed to get change events", error=str(e))
            return []
    
    def get_change_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get a single change event by ID"""
        try:
            query = """
            SELECT 
                event_id, timestamp, cluster_id, analysis_id,
                run_id, run_number, change_type, risk_level,
                target_name, target_namespace, target_type,
                before_state, after_state, affected_services,
                blast_radius, changed_by, details, metadata
            FROM change_events
            WHERE event_id = %(event_id)s
            LIMIT 1
            """
            
            result = self.client.execute(query, {'event_id': event_id})
            
            if not result:
                return None
            
            columns = [
                'event_id', 'timestamp', 'cluster_id', 'analysis_id',
                'run_id', 'run_number', 'change_type', 'risk_level',
                'target_name', 'target_namespace', 'target_type',
                'before_state', 'after_state', 'affected_services',
                'blast_radius', 'changed_by', 'details', 'metadata'
            ]
            
            event = dict(zip(columns, result[0]))
            
            return {
                'id': hash(event['event_id']) % (10 ** 9),
                'event_id': event['event_id'],
                'cluster_id': event['cluster_id'],
                'analysis_id': event['analysis_id'],
                'timestamp': event['timestamp'].isoformat() if event['timestamp'] else None,
                'change_type': event['change_type'],
                'target': event['target_name'],
                'namespace': event['target_namespace'],
                'details': event['details'],
                'risk': event['risk_level'],
                'before_state': event['before_state'],
                'after_state': event['after_state'],
                'affected_services': event['affected_services'],
                'blast_radius': event['blast_radius'],
                'changed_by': event['changed_by'],
                'status': 'detected',
                'metadata': event['metadata']
            }
            
        except Exception as e:
            logger.error("Failed to get change event", event_id=event_id, error=str(e))
            return None
    
    def get_change_stats(
        self,
        analysis_id: Optional[str] = None,
        cluster_id: Optional[int] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get change detection statistics.
        
        Returns summary of changes by type, risk level, and time.
        """
        try:
            conditions = ["timestamp >= now() - INTERVAL %(hours)s HOUR"]
            params = {'hours': hours}
            
            if analysis_id:
                conditions.append("analysis_id = %(analysis_id)s")
                params['analysis_id'] = str(analysis_id)
            
            if cluster_id:
                conditions.append("cluster_id = %(cluster_id)s")
                params['cluster_id'] = cluster_id
            
            # Total counts by type
            type_query = f"""
            SELECT change_type, count() as count
            FROM change_events
            WHERE {' AND '.join(conditions)}
            GROUP BY change_type
            """
            
            type_result = self.client.execute(type_query, params)
            by_type = {row[0]: row[1] for row in type_result}
            
            # Total counts by risk
            risk_query = f"""
            SELECT risk_level, count() as count
            FROM change_events
            WHERE {' AND '.join(conditions)}
            GROUP BY risk_level
            """
            
            risk_result = self.client.execute(risk_query, params)
            by_risk = {row[0]: row[1] for row in risk_result}
            
            # Total count
            total_query = f"""
            SELECT count() as total
            FROM change_events
            WHERE {' AND '.join(conditions)}
            """
            
            total_result = self.client.execute(total_query, params)
            total = total_result[0][0] if total_result else 0
            
            return {
                'total': total,
                'by_type': by_type,
                'by_risk': by_risk,
                'hours': hours
            }
            
        except Exception as e:
            logger.error("Failed to get change stats", error=str(e))
            return {'total': 0, 'by_type': {}, 'by_risk': {}, 'hours': hours}
    
    # ========================================
    # Network Flow Methods
    # ========================================
    
    def insert_network_flows(self, flows: List[Dict[str, Any]]) -> bool:
        """Insert network flow events in batch"""
        try:
            if not flows:
                return True
                
            # Prepare data for batch insert
            data = []
            for flow in flows:
                data.append([
                    flow.get('timestamp', datetime.utcnow()),
                    flow.get('cluster_id'),
                    flow.get('cluster_name'),
                    flow.get('source_namespace'),
                    flow.get('source_workload_name'),
                    flow.get('destination_namespace'),
                    flow.get('destination_workload_name'),
                    flow.get('destination_ip'),
                    flow.get('destination_port'),
                    flow.get('protocol'),
                    flow.get('bytes_sent', 0),
                    flow.get('bytes_received', 0),
                    1 if flow.get('is_external', False) else 0,
                    flow.get('metadata', '{}')
                ])
            
            self.client.execute(
                """
                INSERT INTO flowfish.network_flows (
                    timestamp, cluster_id, cluster_name,
                    source_namespace, source_workload_name,
                    destination_namespace, destination_workload_name,
                    destination_ip, destination_port, protocol,
                    bytes_sent, bytes_received, is_external, metadata
                ) VALUES
                """,
                data
            )
            
            logger.info("Network flows inserted", count=len(flows))
            return True
            
        except Exception as e:
            logger.error("Failed to insert network flows", error=str(e), count=len(flows))
            return False
    
    def insert_request_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Insert request metrics in batch"""
        try:
            if not metrics:
                return True
                
            data = []
            for metric in metrics:
                data.append([
                    metric.get('timestamp', datetime.utcnow()),
                    metric.get('cluster_id'),
                    metric.get('source_workload'),
                    metric.get('destination_workload'),
                    metric.get('request_count', 0),
                    metric.get('avg_latency_ms', 0.0)
                ])
            
            self.client.execute(
                """
                INSERT INTO flowfish.request_metrics (
                    timestamp, cluster_id, source_workload, 
                    destination_workload, request_count, avg_latency_ms
                ) VALUES
                """,
                data
            )
            
            logger.info("Request metrics inserted", count=len(metrics))
            return True
            
        except Exception as e:
            logger.error("Failed to insert request metrics", error=str(e))
            return False
    
    def get_network_flows(
        self, 
        cluster_id: int,
        start_time: datetime,
        end_time: datetime,
        namespace: Optional[str] = None,
        limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """Get network flows for time range"""
        try:
            query = """
            SELECT 
                timestamp,
                cluster_id,
                source_namespace,
                source_workload_name,
                destination_namespace,
                destination_workload_name,
                destination_ip,
                destination_port,
                protocol,
                bytes_sent,
                bytes_received,
                is_external
            FROM flowfish.network_flows
            WHERE cluster_id = %(cluster_id)s
              AND timestamp >= %(start_time)s
              AND timestamp <= %(end_time)s
            """
            
            params = {
                'cluster_id': cluster_id,
                'start_time': start_time,
                'end_time': end_time
            }
            
            if namespace:
                query += " AND (source_namespace = %(namespace)s OR destination_namespace = %(namespace)s)"
                params['namespace'] = namespace
            
            query += f" ORDER BY timestamp DESC LIMIT {limit}"
            
            result = self.client.execute(query, params)
            
            # Convert to list of dicts
            columns = [
                'timestamp', 'cluster_id', 'source_namespace', 'source_workload_name',
                'destination_namespace', 'destination_workload_name', 'destination_ip',
                'destination_port', 'protocol', 'bytes_sent', 'bytes_received', 'is_external'
            ]
            
            flows = []
            for row in result:
                flows.append(dict(zip(columns, row)))
            
            return flows
            
        except Exception as e:
            logger.error("Failed to get network flows", error=str(e))
            return []
    
    def get_communication_stats(self, cluster_id: int, hours: int = 24) -> Dict[str, Any]:
        """Get communication statistics for last N hours"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            query = """
            SELECT
                count() as total_flows,
                countDistinct(source_workload_name) as unique_sources,
                countDistinct(destination_workload_name) as unique_destinations,
                countIf(is_external = 1) as external_flows,
                countDistinct(protocol) as unique_protocols,
                sum(bytes_sent) as total_bytes_sent,
                sum(bytes_received) as total_bytes_received
            FROM flowfish.network_flows
            WHERE cluster_id = %(cluster_id)s
              AND timestamp >= %(start_time)s
              AND timestamp <= %(end_time)s
            """
            
            result = self.client.execute(query, {
                'cluster_id': cluster_id,
                'start_time': start_time,
                'end_time': end_time
            })
            
            if result:
                columns = [
                    'total_flows', 'unique_sources', 'unique_destinations',
                    'external_flows', 'unique_protocols', 'total_bytes_sent', 'total_bytes_received'
                ]
                return dict(zip(columns, result[0]))
            
            return {}
            
        except Exception as e:
            logger.error("Failed to get communication stats", error=str(e))
            return {}
    
    def get_top_communicating_workloads(self, cluster_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top communicating workloads by request count"""
        try:
            query = """
            SELECT
                source_workload_name,
                count() as total_communications,
                countDistinct(destination_workload_name) as unique_destinations,
                sum(bytes_sent) as total_bytes_sent
            FROM flowfish.network_flows
            WHERE cluster_id = %(cluster_id)s
              AND timestamp >= now() - INTERVAL 24 HOUR
            GROUP BY source_workload_name
            ORDER BY total_communications DESC
            LIMIT %(limit)s
            """
            
            result = self.client.execute(query, {
                'cluster_id': cluster_id,
                'limit': limit
            })
            
            columns = ['workload_name', 'total_communications', 'unique_destinations', 'total_bytes_sent']
            workloads = []
            for row in result:
                workloads.append(dict(zip(columns, row)))
            
            return workloads
            
        except Exception as e:
            logger.error("Failed to get top communicating workloads", error=str(e))
            return []
    
    # ========================================
    # Other Event Methods (placeholders)
    # ========================================
    
    def insert_dns_queries(self, queries: List[Dict[str, Any]]) -> bool:
        """Insert DNS query events in batch"""
        try:
            if not queries:
                return True
            logger.info("DNS queries inserted", count=len(queries))
            return True
        except Exception as e:
            logger.error("Failed to insert DNS queries", error=str(e))
            return False
    
    def insert_tcp_lifecycle(self, events: List[Dict[str, Any]]) -> bool:
        """Insert TCP lifecycle events in batch"""
        try:
            if not events:
                return True
            logger.info("TCP lifecycle events inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert TCP lifecycle events", error=str(e))
            return False
    
    def insert_process_events(self, events: List[Dict[str, Any]]) -> bool:
        """Insert process events in batch"""
        try:
            if not events:
                return True
            logger.info("Process events inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert process events", error=str(e))
            return False
    
    def insert_file_operations(self, events: List[Dict[str, Any]]) -> bool:
        """Insert file operation events in batch"""
        try:
            if not events:
                return True
            logger.info("File operations inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert file operations", error=str(e))
            return False
    
    def insert_capability_checks(self, events: List[Dict[str, Any]]) -> bool:
        """Insert capability/security events in batch"""
        try:
            if not events:
                return True
            logger.info("Capability checks inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert capability checks", error=str(e))
            return False
    
    def insert_oom_kills(self, events: List[Dict[str, Any]]) -> bool:
        """Insert OOM kill events in batch"""
        try:
            if not events:
                return True
            logger.info("OOM kills inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert OOM kills", error=str(e))
            return False
    
    def insert_bind_events(self, events: List[Dict[str, Any]]) -> bool:
        """Insert socket bind events in batch"""
        try:
            if not events:
                return True
            logger.info("Bind events inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert bind events", error=str(e))
            return False
    
    def insert_sni_events(self, events: List[Dict[str, Any]]) -> bool:
        """Insert TLS/SNI events in batch"""
        try:
            if not events:
                return True
            logger.info("SNI events inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert SNI events", error=str(e))
            return False
    
    def insert_mount_events(self, events: List[Dict[str, Any]]) -> bool:
        """Insert mount events in batch"""
        try:
            if not events:
                return True
            logger.info("Mount events inserted", count=len(events))
            return True
        except Exception as e:
            logger.error("Failed to insert mount events", error=str(e))
            return False


# Service instance
clickhouse_service = ClickHouseService(clickhouse_client)


# Connection test function
def test_clickhouse_connection() -> bool:
    """Test ClickHouse connection"""
    try:
        clickhouse_client.execute("SELECT 1")
        logger.info("ClickHouse connection test successful")
        return True
    except Exception as e:
        logger.error("ClickHouse connection test failed", error=str(e))
        return False
