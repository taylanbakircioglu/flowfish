/**
 * ExamplesDropdown Component - Example queries for ClickHouse and Neo4j
 * 
 * Provides ready-to-use query templates organized by category.
 * Column names aligned with actual ClickHouse schema (clickhouse-events-schema.sql)
 */

import React from 'react';
import { Dropdown, Button, Typography, Space } from 'antd';
import { 
  BookOutlined, 
  DatabaseOutlined,
  GlobalOutlined,
  SafetyOutlined,
  CodeOutlined,
  LineChartOutlined,
  FolderOutlined,
  ApartmentOutlined,
  SearchOutlined,
  ClusterOutlined,
  ApiOutlined,
  AlertOutlined,
  SwapOutlined,
  AimOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { DatabaseType } from '../../store/api/devConsoleApi';

const { Text } = Typography;

interface QueryExample {
  key: string;
  label: string;
  query: string;
}

interface QueryCategory {
  key: string;
  label: string;
  icon: React.ReactNode;
  examples: QueryExample[];
}

// ============================================================================
// ClickHouse Example Queries - Organized by Category
// ============================================================================

const CLICKHOUSE_CATEGORIES: QueryCategory[] = [
  // ---------------------------------------------------------------------------
  // Network Analysis
  // ---------------------------------------------------------------------------
  {
    key: 'ch-network',
    label: 'Network Analysis',
    icon: <GlobalOutlined />,
    examples: [
      {
        key: 'ch-network-top',
        label: 'Top Communication Pairs',
        query: `-- Top Communication Pairs (Last Hour)
SELECT 
    source_namespace,
    source_pod,
    dest_pod,
    dest_ip,
    dest_port,
    protocol,
    sum(bytes_sent) as total_bytes_sent,
    sum(bytes_received) as total_bytes_received,
    count(*) as flow_count
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY source_namespace, source_pod, dest_pod, dest_ip, dest_port, protocol
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-network-by-port',
        label: 'Traffic by Port',
        query: `-- Traffic Distribution by Port
SELECT 
    dest_port,
    protocol,
    count(*) as connection_count,
    sum(bytes_sent + bytes_received) as total_bytes,
    uniqExact(source_pod) as unique_sources,
    uniqExact(dest_pod) as unique_destinations
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY dest_port, protocol
ORDER BY connection_count DESC
LIMIT 50`,
      },
      {
        key: 'ch-network-by-namespace',
        label: 'Traffic by Namespace',
        query: `-- Traffic Volume by Namespace
SELECT 
    source_namespace,
    count(*) as flow_count,
    sum(bytes_sent) as bytes_sent,
    sum(bytes_received) as bytes_received,
    uniqExact(source_pod) as unique_pods,
    uniqExact(dest_ip) as unique_destinations
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY source_namespace
ORDER BY flow_count DESC`,
      },
      {
        key: 'ch-network-external',
        label: 'External Traffic (Egress)',
        query: `-- External/Egress Traffic (Non-cluster destinations)
SELECT 
    source_namespace,
    source_pod,
    dest_ip,
    dest_port,
    protocol,
    count(*) as connection_count,
    sum(bytes_sent) as bytes_sent
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND dest_pod = ''  -- No pod = external destination
GROUP BY source_namespace, source_pod, dest_ip, dest_port, protocol
ORDER BY connection_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-network-timeline',
        label: 'Traffic Timeline (5min buckets)',
        query: `-- Network Traffic Timeline
SELECT 
    toStartOfFiveMinute(timestamp) as time_bucket,
    count(*) as flow_count,
    sum(bytes_sent + bytes_received) as total_bytes,
    uniqExact(source_pod) as active_pods
FROM network_flows
WHERE timestamp > now() - INTERVAL 6 HOUR
GROUP BY time_bucket
ORDER BY time_bucket`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // IP & Port Lookup
  // ---------------------------------------------------------------------------
  {
    key: 'ch-ip-port',
    label: 'IP & Port Lookup',
    icon: <AimOutlined />,
    examples: [
      {
        key: 'ch-ip-dest-agg',
        label: 'Who Talks to This IP? (Aggregated)',
        query: `-- Who is sending traffic to a destination IP? (Aggregated view)
-- Replace '10.0.1.50' with the target IP
SELECT
    source_namespace,
    source_pod,
    source_ip,
    dest_pod,
    dest_ip,
    dest_port,
    protocol,
    count(*) as flow_count,
    sum(bytes_sent + bytes_received) as total_bytes
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND dest_ip = '10.0.1.50'
GROUP BY
    source_namespace, source_pod, source_ip,
    dest_pod, dest_ip, dest_port, protocol
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-direction',
        label: 'IP Direction Analysis (IN/OUT)',
        query: `-- Incoming vs Outgoing traffic for a specific IP
-- Replace '10.0.2.15' with the target IP
SELECT
    CASE 
        WHEN source_ip = '10.0.2.15' THEN 'OUTGOING'
        ELSE 'INCOMING'
    END as direction,
    count(*) as flow_count,
    sum(bytes_sent) as total_bytes_sent,
    sum(bytes_received) as total_bytes_received
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (source_ip = '10.0.2.15' OR dest_ip = '10.0.2.15')
GROUP BY direction`,
      },
      {
        key: 'ch-ip-port-peers',
        label: 'IP + Port Peer List',
        query: `-- All peers communicating with an IP on a specific port
-- Replace '10.0.2.15' and port 80 as needed
SELECT
    source_pod,
    dest_pod,
    dest_ip,
    count(*) as flow_count
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (source_ip = '10.0.2.15' OR dest_ip = '10.0.2.15')
  AND dest_port = 80
GROUP BY source_pod, dest_pod, dest_ip
ORDER BY flow_count DESC
LIMIT 50`,
      },
      {
        key: 'ch-ip-source-agg',
        label: 'Where Does This IP Go? (Aggregated)',
        query: `-- What destinations does a source IP communicate with?
-- Replace '10.244.0.15' with the source IP
SELECT
    dest_pod,
    dest_ip,
    dest_port,
    protocol,
    count(*) as flow_count,
    sum(bytes_sent) as bytes_sent,
    sum(bytes_received) as bytes_received
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND source_ip = '10.244.0.15'
GROUP BY dest_pod, dest_ip, dest_port, protocol
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-all-traffic',
        label: 'Full IP Traffic Profile',
        query: `-- Complete traffic profile for an IP (both directions, grouped)
-- Replace '10.0.2.15' with the target IP
SELECT
    CASE 
        WHEN source_ip = '10.0.2.15' THEN 'OUTGOING'
        ELSE 'INCOMING'
    END as direction,
    source_namespace,
    source_pod,
    source_ip,
    dest_pod,
    dest_ip,
    dest_port,
    protocol,
    count(*) as flow_count,
    sum(bytes_sent + bytes_received) as total_bytes
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (source_ip = '10.0.2.15' OR dest_ip = '10.0.2.15')
GROUP BY
    direction, source_namespace, source_pod, source_ip,
    dest_pod, dest_ip, dest_port, protocol
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-port-who-uses',
        label: 'Port Traffic Summary',
        query: `-- Who is using a specific destination port?
-- Replace 8080 with the port to investigate
SELECT
    source_namespace,
    source_pod,
    dest_pod,
    dest_ip,
    protocol,
    count(*) as flow_count,
    sum(bytes_sent) as total_bytes_sent,
    sum(bytes_received) as total_bytes_received,
    round(avg(latency_ms), 2) as avg_latency_ms
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND dest_port = 8080
GROUP BY source_namespace, source_pod, dest_pod, dest_ip, protocol
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-timeline',
        label: 'IP Traffic Over Time',
        query: `-- Traffic timeline for a specific IP (5min buckets)
-- Replace '10.0.2.15' with the target IP
SELECT
    toStartOfFiveMinute(timestamp) as time_bucket,
    CASE 
        WHEN source_ip = '10.0.2.15' THEN 'OUTGOING'
        ELSE 'INCOMING'
    END as direction,
    count(*) as flow_count,
    sum(bytes_sent + bytes_received) as total_bytes,
    uniqExact(dest_port) as unique_ports
FROM network_flows
WHERE timestamp > now() - INTERVAL 6 HOUR
  AND (source_ip = '10.0.2.15' OR dest_ip = '10.0.2.15')
GROUP BY time_bucket, direction
ORDER BY time_bucket`,
      },
      {
        key: 'ch-ip-subnet',
        label: 'Subnet Traffic (CIDR)',
        query: `-- Traffic from/to a specific subnet
-- Replace '10.244.0' with the subnet prefix
SELECT
    source_ip,
    dest_ip,
    dest_port,
    protocol,
    source_pod,
    dest_pod,
    count(*) as flow_count,
    sum(bytes_sent + bytes_received) as total_bytes
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (source_ip LIKE '10.244.0.%' OR dest_ip LIKE '10.244.0.%')
GROUP BY source_ip, dest_ip, dest_port, protocol, source_pod, dest_pod
ORDER BY flow_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-dns',
        label: 'DNS Lookups by IP',
        query: `-- DNS queries originating from a specific IP
-- Replace '10.244.0.15' with the target IP
SELECT
    source_pod,
    query_name,
    query_type,
    response_code,
    response_ips,
    count(*) as query_count,
    round(avg(latency_ms), 2) as avg_latency_ms
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND source_ip = '10.244.0.15'
GROUP BY source_pod, query_name, query_type, response_code, response_ips
ORDER BY query_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-reverse-dns',
        label: 'Reverse DNS (IP to Domain)',
        query: `-- Find which domain resolved to a specific IP
-- Replace '10.96.0.10' with the target IP
SELECT
    query_name,
    response_code,
    response_ips,
    source_pod,
    source_namespace,
    count(*) as lookup_count,
    max(timestamp) as last_resolved
FROM dns_queries
WHERE timestamp > now() - INTERVAL 24 HOUR
  AND has(response_ips, '10.96.0.10')
GROUP BY query_name, response_code, response_ips, source_pod, source_namespace
ORDER BY lookup_count DESC
LIMIT 50`,
      },
      {
        key: 'ch-ip-sni',
        label: 'TLS/SNI by IP',
        query: `-- TLS/SNI connections for a specific IP
-- Replace '10.244.0.15' with the target IP
SELECT
    pod,
    namespace,
    sni_name,
    dst_ip,
    dst_port,
    tls_version,
    count(*) as connection_count
FROM sni_events
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (src_ip = '10.244.0.15' OR dst_ip = '10.244.0.15')
GROUP BY pod, namespace, sni_name, dst_ip, dst_port, tls_version
ORDER BY connection_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-ip-errors',
        label: 'IP Error Analysis',
        query: `-- Connection errors for a specific IP
-- Replace '10.0.2.15' with the target IP
SELECT
    source_pod,
    dest_pod,
    dest_ip,
    dest_port,
    error_type,
    connection_state,
    count(*) as error_count,
    max(timestamp) as last_seen
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND (source_ip = '10.0.2.15' OR dest_ip = '10.0.2.15')
  AND (error_count > 0 OR error_type != '')
GROUP BY source_pod, dest_pod, dest_ip, dest_port, error_type, connection_state
ORDER BY error_count DESC
LIMIT 100`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // DNS Analysis
  // ---------------------------------------------------------------------------
  {
    key: 'ch-dns',
    label: 'DNS Analysis',
    icon: <SearchOutlined />,
    examples: [
      {
        key: 'ch-dns-top',
        label: 'Top Queried Domains',
        query: `-- Most Queried DNS Domains
SELECT 
    query_name,
    query_type,
    count(*) as query_count,
    countIf(response_code = 'NOERROR') as success_count,
    countIf(response_code = 'NXDOMAIN') as nxdomain_count,
    round(avg(latency_ms), 2) as avg_latency_ms
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY query_name, query_type
ORDER BY query_count DESC
LIMIT 50`,
      },
      {
        key: 'ch-dns-errors',
        label: 'DNS Errors & NXDOMAIN',
        query: `-- DNS Errors and Failed Lookups
SELECT 
    query_name,
    response_code,
    source_namespace,
    source_pod,
    count(*) as error_count
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND response_code != 'NOERROR'
GROUP BY query_name, response_code, source_namespace, source_pod
ORDER BY error_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-dns-by-pod',
        label: 'DNS Queries by Pod',
        query: `-- DNS Activity by Pod
SELECT 
    source_namespace,
    source_pod,
    count(*) as total_queries,
    uniqExact(query_name) as unique_domains,
    countIf(response_code = 'NOERROR') as success,
    countIf(response_code != 'NOERROR') as errors,
    round(avg(latency_ms), 2) as avg_latency
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY source_namespace, source_pod
ORDER BY total_queries DESC
LIMIT 50`,
      },
      {
        key: 'ch-dns-latency',
        label: 'DNS Latency Analysis',
        query: `-- DNS Latency Statistics
SELECT 
    query_name,
    count(*) as query_count,
    round(min(latency_ms), 2) as min_latency,
    round(avg(latency_ms), 2) as avg_latency,
    round(quantile(0.95)(latency_ms), 2) as p95_latency,
    round(max(latency_ms), 2) as max_latency
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND latency_ms > 0
GROUP BY query_name
HAVING count(*) > 10
ORDER BY avg_latency DESC
LIMIT 50`,
      },
      {
        key: 'ch-dns-external',
        label: 'External Domain Lookups',
        query: `-- External Domain Lookups (Non-cluster DNS)
SELECT 
    query_name,
    source_namespace,
    count(*) as lookup_count,
    uniqExact(source_pod) as unique_pods
FROM dns_queries
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND query_name NOT LIKE '%.svc.cluster.local'
  AND query_name NOT LIKE '%.cluster.local'
GROUP BY query_name, source_namespace
ORDER BY lookup_count DESC
LIMIT 100`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Security & TLS
  // ---------------------------------------------------------------------------
  {
    key: 'ch-security',
    label: 'Security & TLS',
    icon: <SafetyOutlined />,
    examples: [
      {
        key: 'ch-tls-versions',
        label: 'TLS Version Distribution',
        query: `-- TLS Version Distribution
SELECT 
    tls_version,
    count(*) as connection_count,
    uniqExact(namespace) as namespaces,
    uniqExact(pod) as unique_pods
FROM sni_events
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY tls_version
ORDER BY connection_count DESC`,
      },
      {
        key: 'ch-tls-sni',
        label: 'SNI/TLS Destinations',
        query: `-- TLS/SNI Connection Destinations
SELECT 
    sni_name,
    tls_version,
    count(*) as connection_count,
    uniqExact(namespace) as namespaces,
    uniqExact(pod) as unique_pods
FROM sni_events
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY sni_name, tls_version
ORDER BY connection_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-security-bind',
        label: 'Listening Ports (Bind Events)',
        query: `-- Socket Bind Events - Services Listening on Ports
SELECT 
    namespace,
    pod,
    bind_port,
    protocol,
    comm as process,
    count(*) as bind_count,
    max(timestamp) as last_seen
FROM bind_events
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY namespace, pod, bind_port, protocol, comm
ORDER BY bind_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-security-capabilities',
        label: 'Capability Checks',
        query: `-- Linux Capability Checks
SELECT 
    namespace,
    pod,
    container,
    capability,
    verdict,
    count(*) as check_count
FROM capability_checks
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY namespace, pod, container, capability, verdict
ORDER BY check_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-security-privileged',
        label: 'Privileged Operations',
        query: `-- Privileged/Sensitive Operations
SELECT 
    namespace,
    pod,
    comm as process,
    uid,
    count(*) as operation_count
FROM process_events
WHERE timestamp > now() - INTERVAL 24 HOUR
  AND uid = 0  -- root user
GROUP BY namespace, pod, comm, uid
ORDER BY operation_count DESC
LIMIT 100`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Process Monitoring
  // ---------------------------------------------------------------------------
  {
    key: 'ch-process',
    label: 'Process Monitoring',
    icon: <CodeOutlined />,
    examples: [
      {
        key: 'ch-process-exec',
        label: 'Process Executions',
        query: `-- Process Execution Events
SELECT 
    namespace,
    pod,
    container,
    comm as process_name,
    exe as executable,
    event_type,
    count(*) as exec_count
FROM process_events
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY namespace, pod, container, comm, exe, event_type
ORDER BY exec_count DESC
LIMIT 100`,
      },
      {
        key: 'ch-process-by-container',
        label: 'Processes by Container',
        query: `-- Process Activity by Container
SELECT 
    namespace,
    pod,
    container,
    uniqExact(comm) as unique_processes,
    count(*) as total_events,
    groupArray(10)(DISTINCT comm) as sample_processes
FROM process_events
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY namespace, pod, container
ORDER BY total_events DESC
LIMIT 50`,
      },
      {
        key: 'ch-process-shell',
        label: 'Shell Executions (Security)',
        query: `-- Shell Execution Detection (Potential Security Risk)
SELECT 
    namespace,
    pod,
    container,
    comm,
    exe,
    args,
    timestamp
FROM process_events
WHERE timestamp > now() - INTERVAL 24 HOUR
  AND (comm IN ('sh', 'bash', 'zsh', 'ash', 'dash', 'ksh')
       OR exe LIKE '%/sh' OR exe LIKE '%/bash')
ORDER BY timestamp DESC
LIMIT 100`,
      },
      {
        key: 'ch-process-oom',
        label: 'OOM Kill Events',
        query: `-- Out-of-Memory Kill Events
SELECT 
    namespace,
    pod,
    container,
    comm as killed_process,
    memory_usage,
    memory_limit,
    round(memory_usage / memory_limit * 100, 2) as memory_percent,
    timestamp
FROM oom_kills
WHERE timestamp > now() - INTERVAL 7 DAY
ORDER BY timestamp DESC
LIMIT 100`,
      },
      {
        key: 'ch-process-file-ops',
        label: 'File Operations',
        query: `-- File System Operations
SELECT 
    namespace,
    pod,
    file_path,
    operation,
    comm as process,
    count(*) as operation_count
FROM file_operations
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY namespace, pod, file_path, operation, comm
ORDER BY operation_count DESC
LIMIT 100`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Statistics & Metrics
  // ---------------------------------------------------------------------------
  {
    key: 'ch-stats',
    label: 'Statistics & Metrics',
    icon: <LineChartOutlined />,
    examples: [
      {
        key: 'ch-stats-overview',
        label: 'Data Overview (All Tables)',
        query: `-- Data Overview - Row Counts by Table
SELECT 'network_flows' as table_name, count(*) as total_rows, 
       countIf(timestamp > now() - INTERVAL 1 HOUR) as last_hour FROM network_flows
UNION ALL
SELECT 'dns_queries', count(*), countIf(timestamp > now() - INTERVAL 1 HOUR) FROM dns_queries
UNION ALL
SELECT 'process_events', count(*), countIf(timestamp > now() - INTERVAL 1 HOUR) FROM process_events
UNION ALL
SELECT 'sni_events', count(*), countIf(timestamp > now() - INTERVAL 1 HOUR) FROM sni_events
UNION ALL
SELECT 'bind_events', count(*), countIf(timestamp > now() - INTERVAL 1 HOUR) FROM bind_events
ORDER BY total_rows DESC`,
      },
      {
        key: 'ch-stats-ingestion',
        label: 'Data Ingestion Rate',
        query: `-- Data Ingestion Rate (Last 24 Hours)
SELECT 
    toStartOfHour(timestamp) as hour,
    count(*) as events_per_hour,
    round(count(*) / 3600, 2) as events_per_second
FROM network_flows
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY hour
ORDER BY hour`,
      },
      {
        key: 'ch-stats-active-namespaces',
        label: 'Active Namespaces',
        query: `-- Active Namespaces Summary
SELECT 
    source_namespace as namespace,
    uniqExact(source_pod) as active_pods,
    count(*) as total_flows,
    sum(bytes_sent + bytes_received) as total_bytes
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
  AND source_namespace != ''
GROUP BY source_namespace
ORDER BY total_flows DESC`,
      },
      {
        key: 'ch-stats-analysis',
        label: 'Analysis Data by ID',
        query: `-- Data by Analysis ID
SELECT 
    analysis_id,
    count(*) as event_count,
    min(timestamp) as first_event,
    max(timestamp) as last_event,
    dateDiff('minute', min(timestamp), max(timestamp)) as duration_minutes
FROM network_flows
WHERE analysis_id != ''
GROUP BY analysis_id
ORDER BY last_event DESC
LIMIT 50`,
      },
      {
        key: 'ch-stats-workloads',
        label: 'Workload Metadata Stats',
        query: `-- Workload Metadata Statistics
SELECT 
    namespace,
    workload_type,
    count(*) as workload_count,
    groupArray(10)(workload_name) as sample_workloads
FROM workload_metadata
GROUP BY namespace, workload_type
ORDER BY workload_count DESC`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Schema Exploration
  // ---------------------------------------------------------------------------
  {
    key: 'ch-schema',
    label: 'Schema Exploration',
    icon: <FolderOutlined />,
    examples: [
      {
        key: 'ch-schema-tables',
        label: 'List All Tables',
        query: `SHOW TABLES`,
      },
      {
        key: 'ch-schema-databases',
        label: 'List Databases',
        query: `SHOW DATABASES`,
      },
      {
        key: 'ch-schema-network-flows',
        label: 'Describe network_flows',
        query: `DESCRIBE network_flows`,
      },
      {
        key: 'ch-schema-dns-queries',
        label: 'Describe dns_queries',
        query: `DESCRIBE dns_queries`,
      },
      {
        key: 'ch-schema-process-events',
        label: 'Describe process_events',
        query: `DESCRIBE process_events`,
      },
      {
        key: 'ch-schema-sample',
        label: 'Sample Data (network_flows)',
        query: `-- Sample Data from network_flows
SELECT *
FROM network_flows
ORDER BY timestamp DESC
LIMIT 10`,
      },
      {
        key: 'ch-schema-explain',
        label: 'Explain Query Plan',
        query: `-- Query Execution Plan
EXPLAIN
SELECT source_pod, dest_pod, count(*) as cnt
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY source_pod, dest_pod
ORDER BY cnt DESC
LIMIT 10`,
      },
    ],
  },
];

// ============================================================================
// Neo4j Example Queries - Organized by Category
// ============================================================================

const NEO4J_CATEGORIES: QueryCategory[] = [
  // ---------------------------------------------------------------------------
  // Service Dependencies
  // ---------------------------------------------------------------------------
  {
    key: 'neo-deps',
    label: 'Service Dependencies',
    icon: <ApartmentOutlined />,
    examples: [
      {
        key: 'neo-deps-all',
        label: 'All Active Communications',
        query: `// All Active Workload Communications
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true
RETURN 
    src.name as source,
    src.namespace as src_namespace,
    dst.name as destination,
    dst.namespace as dst_namespace,
    c.protocol,
    c.port as dest_port,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`,
      },
      {
        key: 'neo-deps-service',
        label: 'Service Dependencies (Specific)',
        query: `// Find all services a specific workload depends on
// Change 'your-service-name' to your service
MATCH (src:Workload {name: 'your-service-name'})-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true
RETURN 
    dst.name as dependency,
    dst.namespace,
    c.protocol,
    c.port,
    c.request_count
ORDER BY c.request_count DESC`,
      },
      {
        key: 'neo-deps-reverse',
        label: 'Reverse Dependencies (Who calls me)',
        query: `// Find all services that call a specific workload
// Change 'your-service-name' to your service
MATCH (caller:Workload)-[c:COMMUNICATES_WITH]->(target:Workload {name: 'your-service-name'})
WHERE c.is_active = true
RETURN 
    caller.name as caller,
    caller.namespace,
    c.protocol,
    c.port,
    c.request_count
ORDER BY c.request_count DESC`,
      },
      {
        key: 'neo-deps-most-connected',
        label: 'Most Connected Workloads',
        query: `// Workloads with Most Connections (Hub Services)
MATCH (w:Workload)-[c:COMMUNICATES_WITH]-()
WHERE c.is_active = true
WITH w, count(c) as conn_count, sum(c.request_count) as total_requests
RETURN 
    w.name,
    w.namespace,
    w.kind,
    conn_count as connections,
    total_requests
ORDER BY conn_count DESC
LIMIT 20`,
      },
      {
        key: 'neo-deps-chain',
        label: 'Dependency Chain (2 hops)',
        query: `// Dependency Chain - Find services 2 hops away
// Change 'your-service-name' to your service
MATCH path = (src:Workload {name: 'your-service-name'})
              -[:COMMUNICATES_WITH*1..2]->(dst:Workload)
WHERE src <> dst
RETURN 
    [n in nodes(path) | n.namespace + '/' + n.name] as chain,
    length(path) as hops
LIMIT 50`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Namespace Analysis
  // ---------------------------------------------------------------------------
  {
    key: 'neo-namespace',
    label: 'Namespace Analysis',
    icon: <ClusterOutlined />,
    examples: [
      {
        key: 'neo-ns-workloads',
        label: 'Workloads by Namespace',
        query: `// Active Workloads grouped by Namespace
MATCH (w:Workload)
WHERE w.is_active = true
RETURN 
    w.namespace,
    w.kind,
    count(*) as workload_count
ORDER BY workload_count DESC`,
      },
      {
        key: 'neo-ns-cross',
        label: 'Cross-Namespace Communications',
        query: `// Cross-Namespace Traffic (Potential Security Risk)
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE src.namespace <> dst.namespace
  AND c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source,
    dst.namespace + '/' + dst.name as destination,
    c.protocol,
    c.port,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`,
      },
      {
        key: 'neo-ns-graph',
        label: 'Namespace Dependency Graph',
        query: `// Namespace-level Dependency Summary
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true AND src.namespace <> dst.namespace
WITH src.namespace as src_ns, dst.namespace as dst_ns, 
     count(c) as edge_count, sum(c.request_count) as total_requests
RETURN src_ns, dst_ns, edge_count, total_requests
ORDER BY edge_count DESC`,
      },
      {
        key: 'neo-ns-internal',
        label: 'Internal Namespace Traffic',
        query: `// Traffic within a specific namespace
// Change 'your-namespace' to target namespace
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE src.namespace = 'your-namespace'
  AND dst.namespace = 'your-namespace'
  AND c.is_active = true
RETURN 
    src.name as source,
    dst.name as destination,
    c.protocol,
    c.port,
    c.request_count
ORDER BY c.request_count DESC`,
      },
      {
        key: 'neo-ns-list',
        label: 'List All Namespaces',
        query: `// All Namespaces with Workload Counts
MATCH (w:Workload)
WITH w.namespace as ns, count(*) as total,
     sum(CASE WHEN w.is_active THEN 1 ELSE 0 END) as active
RETURN ns as namespace, total as total_workloads, active as active_workloads
ORDER BY total DESC`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Security Analysis
  // ---------------------------------------------------------------------------
  {
    key: 'neo-security',
    label: 'Security Analysis',
    icon: <AlertOutlined />,
    examples: [
      {
        key: 'neo-sec-orphan',
        label: 'Orphan Workloads (No Traffic)',
        query: `// Workloads with No Communications
MATCH (w:Workload)
WHERE w.is_active = true
  AND NOT (w)-[:COMMUNICATES_WITH]-()
  AND NOT ()-[:COMMUNICATES_WITH]->(w)
RETURN 
    w.name,
    w.namespace,
    w.kind
ORDER BY w.namespace, w.name
LIMIT 50`,
      },
      {
        key: 'neo-sec-external',
        label: 'External Communications',
        query: `// Communications to External IPs (Non-workload destinations)
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst)
WHERE NOT dst:Workload
  AND c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source,
    dst.ip as external_ip,
    c.port,
    c.protocol,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`,
      },
      {
        key: 'neo-sec-high-traffic',
        label: 'High Traffic Connections',
        query: `// Highest Traffic Connections (Potential Hotspots)
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source,
    dst.namespace + '/' + dst.name as destination,
    c.request_count,
    c.protocol,
    c.port
ORDER BY c.request_count DESC
LIMIT 50`,
      },
      {
        key: 'neo-sec-protocols',
        label: 'Protocol Distribution',
        query: `// Communication Protocols Distribution
MATCH ()-[c:COMMUNICATES_WITH]->()
WHERE c.is_active = true
RETURN 
    c.protocol,
    count(*) as connection_count,
    sum(c.request_count) as total_requests
ORDER BY connection_count DESC`,
      },
      {
        key: 'neo-sec-ports',
        label: 'Port Usage Analysis',
        query: `// Most Used Destination Ports
MATCH ()-[c:COMMUNICATES_WITH]->()
WHERE c.is_active = true
RETURN 
    c.port,
    c.protocol,
    count(*) as connection_count,
    sum(c.request_count) as total_requests
ORDER BY connection_count DESC
LIMIT 30`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // IP & Port Lookup
  // ---------------------------------------------------------------------------
  {
    key: 'neo-ip-port',
    label: 'IP & Port Lookup',
    icon: <AimOutlined />,
    examples: [
      {
        key: 'neo-ip-external-dest',
        label: 'Traffic to External IP',
        query: `// Find workloads communicating with a specific external IP
// Replace '203.0.113.50' with the target IP
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst)
WHERE c.dest_ip = '203.0.113.50'
  AND c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source_workload,
    c.dest_ip as dest_ip,
    c.port as dest_port,
    c.protocol,
    c.request_count
ORDER BY c.request_count DESC`,
      },
      {
        key: 'neo-ip-port-filter',
        label: 'Communications by Port',
        query: `// Find all communications on a specific port
// Replace 443 with the target port
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.port = 443
  AND c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source,
    dst.namespace + '/' + dst.name as destination,
    c.protocol,
    c.port,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`,
      },
      {
        key: 'neo-ip-who-talks-to-port',
        label: 'Who Connects to Port?',
        query: `// Find all source workloads connecting to a specific destination port
// Replace 5432 with the target port (e.g. 5432=PostgreSQL, 6379=Redis, 3306=MySQL)
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.port = 5432
  AND c.is_active = true
RETURN 
    dst.namespace + '/' + dst.name as service,
    collect(DISTINCT src.namespace + '/' + src.name) as callers,
    count(src) as caller_count,
    sum(c.request_count) as total_requests
ORDER BY caller_count DESC`,
      },
      {
        key: 'neo-ip-external-all',
        label: 'All External IP Communications',
        query: `// All communications to non-workload (external) destinations
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst)
WHERE NOT dst:Workload
  AND c.is_active = true
RETURN 
    src.namespace + '/' + src.name as source,
    dst.ip as external_ip,
    c.port as dest_port,
    c.protocol,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`,
      },
      {
        key: 'neo-ip-multi-port',
        label: 'Services Exposing Multiple Ports',
        query: `// Find workloads that receive traffic on multiple ports
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true
WITH dst, collect(DISTINCT c.port) as ports, count(c) as conn_count
WHERE size(ports) > 1
RETURN 
    dst.namespace + '/' + dst.name as workload,
    ports as exposed_ports,
    size(ports) as port_count,
    conn_count as total_connections
ORDER BY port_count DESC`,
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Graph Exploration
  // ---------------------------------------------------------------------------
  {
    key: 'neo-explore',
    label: 'Graph Exploration',
    icon: <ApiOutlined />,
    examples: [
      {
        key: 'neo-explore-labels',
        label: 'All Node Labels',
        query: `// All Node Labels in the Graph
CALL db.labels() YIELD label
RETURN label
ORDER BY label`,
      },
      {
        key: 'neo-explore-rels',
        label: 'All Relationship Types',
        query: `// All Relationship Types
CALL db.relationshipTypes() YIELD relationshipType
RETURN relationshipType
ORDER BY relationshipType`,
      },
      {
        key: 'neo-explore-stats',
        label: 'Graph Statistics',
        query: `// Graph Statistics - Node and Edge Counts
MATCH (n)
WITH count(n) as total_nodes
MATCH ()-[r]->()
WITH total_nodes, count(r) as total_edges
RETURN total_nodes, total_edges`,
      },
      {
        key: 'neo-explore-sample',
        label: 'Sample Workloads',
        query: `// Sample Workload Nodes
MATCH (w:Workload)
RETURN w.name, w.namespace, w.kind, w.is_active
LIMIT 20`,
      },
      {
        key: 'neo-explore-path',
        label: 'Shortest Path Between Services',
        query: `// Shortest Path Between Two Services
// Change service names as needed
MATCH path = shortestPath(
    (a:Workload {name: 'service-a'})-[:COMMUNICATES_WITH*]-(b:Workload {name: 'service-b'})
)
RETURN [n in nodes(path) | n.namespace + '/' + n.name] as path,
       length(path) as hops`,
      },
      {
        key: 'neo-explore-analysis',
        label: 'Analysis Summary',
        query: `// Analysis Data Summary
MATCH (a:Analysis)
RETURN 
    a.analysis_id as analysis_id,
    a.status,
    a.cluster_name,
    a.created_at
ORDER BY a.created_at DESC
LIMIT 20`,
      },
    ],
  },
];

// ============================================================================
// Component
// ============================================================================

interface ExamplesDropdownProps {
  database: DatabaseType;
  onSelectExample: (query: string) => void;
  onDatabaseChange?: (db: DatabaseType) => void;
}

const ExamplesDropdown: React.FC<ExamplesDropdownProps> = ({
  database,
  onSelectExample,
  onDatabaseChange,
}) => {
  const categories = database === 'clickhouse' ? CLICKHOUSE_CATEGORIES : NEO4J_CATEGORIES;
  const otherDb = database === 'clickhouse' ? 'neo4j' : 'clickhouse';
  const otherDbLabel = database === 'clickhouse' ? 'Graph' : 'TimeSeries';
  const currentDbLabel = database === 'clickhouse' ? 'TimeSeries' : 'Graph';
  const dbColor = database === 'clickhouse' ? '#0891b2' : '#4d9f7c';

  const menuItems: MenuProps['items'] = [
    // Header with database indicator
    {
      key: 'header',
      type: 'group',
      label: (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            <span style={{ 
              width: 10, 
              height: 10, 
              borderRadius: '50%', 
              background: dbColor,
              display: 'inline-block',
            }} />
            <Text strong>
              {currentDbLabel} Templates
            </Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {database === 'clickhouse' ? 'SQL' : 'Cypher'}
          </Text>
        </div>
      ),
    },
    { type: 'divider' },
    // Template categories
    ...categories.map((category) => ({
      key: category.key,
      label: (
        <Space>
          {category.icon}
          <span>{category.label}</span>
          <Text type="secondary" style={{ fontSize: 11 }}>
            ({category.examples.length})
          </Text>
        </Space>
      ),
      children: category.examples.map((example) => ({
        key: example.key,
        label: example.label,
        onClick: () => onSelectExample(example.query),
      })),
    })),
    // Footer with switch option
    { type: 'divider' },
    {
      key: 'switch-db',
      label: (
        <div 
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            color: '#8c8c8c',
            fontSize: 12,
          }}
        >
          <SwapOutlined style={{ marginRight: 6 }} />
          Switch to {otherDbLabel} Templates
        </div>
      ),
      onClick: () => onDatabaseChange?.(otherDb as DatabaseType),
    },
  ];

  return (
    <Dropdown
      menu={{ items: menuItems }}
      placement="bottomRight"
      trigger={['click']}
    >
      <Button icon={<BookOutlined />}>
        <Space size={4}>
          Templates
          <span style={{ 
            width: 6, 
            height: 6, 
            borderRadius: '50%', 
            background: dbColor,
            display: 'inline-block',
          }} />
        </Space>
      </Button>
    </Dropdown>
  );
};

export default ExamplesDropdown;
