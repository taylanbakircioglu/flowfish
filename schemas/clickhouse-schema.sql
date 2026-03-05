-- ============================================================================
-- Flowfish - ClickHouse Time-Series Database Schema
-- ============================================================================
-- Version: 1.0.0
-- Date: January 2025
-- Description: Time-series schema for eBPF event data and metrics
-- ============================================================================

-- Create database
CREATE DATABASE IF NOT EXISTS flowfish;

USE flowfish;

-- ============================================================================
-- TABLE: network_flows
-- Description: Raw network flow events from eBPF
-- ============================================================================

CREATE TABLE IF NOT EXISTS network_flows (
    -- Timestamp (partition key)
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context (for filtering by analysis)
    analysis_id String DEFAULT '',  -- Analysis ID that collected this event
    
    -- Cluster and namespace context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    
    -- Source information
    source_namespace LowCardinality(String),
    source_pod_name String,
    source_pod_uid String,
    source_workload_type LowCardinality(String), -- pod, deployment, service
    source_workload_name String,
    source_ip IPv4,
    source_port UInt16,
    
    -- Destination information
    destination_namespace LowCardinality(String),
    destination_pod_name String,
    destination_pod_uid String,
    destination_workload_type LowCardinality(String),
    destination_workload_name String,
    destination_ip IPv4,
    destination_port UInt16,
    
    -- Protocol and transport
    protocol LowCardinality(String), -- TCP, UDP, ICMP
    transport_protocol LowCardinality(String), -- HTTP, HTTPS, gRPC, DNS
    
    -- Traffic metrics
    bytes_sent UInt64,
    bytes_received UInt64,
    packets_sent UInt32,
    packets_received UInt32,
    
    -- Connection details
    connection_state LowCardinality(String), -- SYN, ACK, FIN, etc.
    connection_duration_ms UInt32,
    
    -- Flags
    is_cross_namespace UInt8 DEFAULT 0,
    is_external UInt8 DEFAULT 0,
    is_encrypted UInt8 DEFAULT 0,
    
    -- Labels (for filtering)
    source_labels Map(String, String),
    destination_labels Map(String, String),
    
    -- Metadata
    metadata String -- JSON metadata
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, source_ip, destination_ip, destination_port)
TTL event_date + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;

-- Materialized view for hourly aggregations
CREATE MATERIALIZED VIEW IF NOT EXISTS network_flows_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, hour, source_workload_name, destination_workload_name, destination_port, protocol)
TTL event_date + INTERVAL 180 DAY DELETE
AS SELECT
    toStartOfHour(timestamp) as hour,
    event_date,
    cluster_id,
    cluster_name,
    source_namespace,
    source_workload_name,
    destination_namespace,
    destination_workload_name,
    destination_port,
    protocol,
    transport_protocol,
    count() as flow_count,
    sum(bytes_sent) as total_bytes_sent,
    sum(bytes_received) as total_bytes_received,
    sum(packets_sent) as total_packets_sent,
    sum(packets_received) as total_packets_received,
    avg(connection_duration_ms) as avg_duration_ms,
    sumIf(1, is_external = 1) as external_count,
    sumIf(1, is_cross_namespace = 1) as cross_namespace_count
FROM network_flows
GROUP BY 
    hour, event_date, cluster_id, cluster_name,
    source_namespace, source_workload_name,
    destination_namespace, destination_workload_name,
    destination_port, protocol, transport_protocol;

-- ============================================================================
-- TABLE: dns_queries
-- Description: DNS query events
-- ============================================================================

CREATE TABLE IF NOT EXISTS dns_queries (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    pod_name String,
    pod_uid String,
    workload_name String,
    
    -- DNS query details
    query_name String,
    query_type LowCardinality(String), -- A, AAAA, CNAME, MX, TXT, SRV
    query_class LowCardinality(String), -- IN, CH, HS
    
    -- DNS response details
    response_code LowCardinality(String), -- NOERROR, NXDOMAIN, SERVFAIL, etc.
    response_answers Array(String), -- Resolved IPs/names
    response_ttl UInt32,
    response_time_ms UInt16,
    
    -- DNS server
    dns_server_ip IPv4,
    
    -- Flags
    is_cached UInt8 DEFAULT 0,
    is_external_query UInt8 DEFAULT 0,
    
    -- Metadata
    labels Map(String, String),
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, namespace, query_name)
TTL event_date + INTERVAL 60 DAY DELETE
SETTINGS index_granularity = 8192;

-- Materialized view for DNS query statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS dns_query_stats
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, hour, query_name, query_type)
TTL event_date + INTERVAL 120 DAY DELETE
AS SELECT
    toStartOfHour(timestamp) as hour,
    event_date,
    cluster_id,
    cluster_name,
    query_name,
    query_type,
    count() as query_count,
    countIf(response_code = 'NOERROR') as successful_queries,
    countIf(response_code = 'NXDOMAIN') as nxdomain_count,
    countIf(response_code = 'SERVFAIL') as servfail_count,
    avg(response_time_ms) as avg_response_time_ms,
    quantile(0.95)(response_time_ms) as p95_response_time_ms,
    sumIf(1, is_external_query = 1) as external_query_count
FROM dns_queries
GROUP BY hour, event_date, cluster_id, cluster_name, query_name, query_type;

-- ============================================================================
-- TABLE: tcp_connections
-- Description: TCP connection lifecycle events
-- ============================================================================

CREATE TABLE IF NOT EXISTS tcp_connections (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    pod_name String,
    pod_uid String,
    
    -- Connection 5-tuple
    source_ip IPv4,
    source_port UInt16,
    destination_ip IPv4,
    destination_port UInt16,
    protocol LowCardinality(String) DEFAULT 'TCP',
    
    -- Connection state
    connection_id String, -- Unique connection identifier
    state LowCardinality(String), -- SYN, SYN_ACK, ESTABLISHED, FIN, CLOSE
    previous_state LowCardinality(String),
    
    -- Timing
    connection_start_time DateTime64(3),
    connection_end_time DateTime64(3),
    duration_ms UInt32,
    
    -- TCP metrics
    retransmit_count UInt16,
    window_size UInt32,
    rtt_ms Float32, -- Round-trip time
    
    -- Flags
    is_syn UInt8,
    is_ack UInt8,
    is_fin UInt8,
    is_rst UInt8,
    
    -- Direction
    direction LowCardinality(String), -- OUTBOUND, INBOUND
    
    -- Metadata
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, connection_id)
TTL event_date + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- TABLE: http_requests
-- Description: HTTP/HTTPS request events (L7)
-- ============================================================================

CREATE TABLE IF NOT EXISTS http_requests (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    source_namespace LowCardinality(String),
    source_workload String,
    destination_namespace LowCardinality(String),
    destination_workload String,
    
    -- HTTP request details
    method LowCardinality(String), -- GET, POST, PUT, DELETE, etc.
    url String,
    path String,
    query_string String,
    host String,
    user_agent String,
    
    -- HTTP response details
    status_code UInt16,
    status_category LowCardinality(String), -- 2xx, 3xx, 4xx, 5xx
    content_type LowCardinality(String),
    content_length UInt32,
    
    -- Timing
    request_duration_ms UInt32,
    ttfb_ms UInt16, -- Time to first byte
    
    -- Protocol
    http_version LowCardinality(String), -- HTTP/1.1, HTTP/2, HTTP/3
    is_tls UInt8,
    tls_version LowCardinality(String),
    
    -- Additional context
    trace_id String, -- Distributed tracing
    span_id String,
    
    -- Metadata
    headers Map(String, String),
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, destination_workload, path)
TTL event_date + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

-- Materialized view for HTTP metrics
CREATE MATERIALIZED VIEW IF NOT EXISTS http_request_metrics
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, minute, destination_workload, path, method, status_category)
TTL event_date + INTERVAL 90 DAY DELETE
AS SELECT
    toStartOfMinute(timestamp) as minute,
    event_date,
    cluster_id,
    cluster_name,
    destination_namespace,
    destination_workload,
    path,
    method,
    status_category,
    countState() as request_count,
    avgState(request_duration_ms) as avg_duration_ms,
    quantileState(0.50)(request_duration_ms) as p50_duration_ms,
    quantileState(0.95)(request_duration_ms) as p95_duration_ms,
    quantileState(0.99)(request_duration_ms) as p99_duration_ms,
    sumState(content_length) as total_bytes,
    countIfState(status_code >= 400) as error_count
FROM http_requests
GROUP BY 
    minute, event_date, cluster_id, cluster_name,
    destination_namespace, destination_workload, path, method, status_category;

-- ============================================================================
-- TABLE: process_events
-- Description: Process creation and termination events
-- ============================================================================

CREATE TABLE IF NOT EXISTS process_events (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    pod_name String,
    pod_uid String,
    container_name String,
    node_name String,
    
    -- Process details
    pid UInt32,
    ppid UInt32, -- Parent process ID
    process_name String,
    binary_path String,
    arguments Array(String),
    
    -- User context
    uid UInt32,
    gid UInt32,
    username String,
    
    -- Event type
    event_type LowCardinality(String), -- EXEC, EXIT, FORK
    exit_code Int32,
    
    -- Security context
    is_privileged UInt8,
    capabilities Array(String),
    
    -- Metadata
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, namespace, pod_name)
TTL event_date + INTERVAL 60 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- TABLE: syscall_events
-- Description: System call tracking (network/file related)
-- ============================================================================

CREATE TABLE IF NOT EXISTS syscall_events (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    pod_name String,
    container_name String,
    
    -- Process context
    pid UInt32,
    process_name String,
    
    -- Syscall details
    syscall_name LowCardinality(String), -- socket, connect, bind, open, read, write
    syscall_number UInt16,
    return_value Int64,
    errno Int32,
    
    -- Syscall arguments (JSON)
    arguments String,
    
    -- Timing
    duration_ns UInt64,
    
    -- Classification
    category LowCardinality(String), -- network, file, process, memory
    
    -- Metadata
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, namespace, syscall_name)
TTL event_date + INTERVAL 14 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- TABLE: file_access_events
-- Description: File access tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_access_events (
    -- Timestamp
    timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    pod_name String,
    container_name String,
    
    -- Process context
    pid UInt32,
    process_name String,
    uid UInt32,
    
    -- File details
    file_path String,
    file_inode UInt64,
    file_mode UInt32,
    
    -- Operation
    operation LowCardinality(String), -- open, read, write, close, delete, rename
    flags String, -- O_RDONLY, O_WRONLY, O_CREAT, etc.
    bytes_accessed UInt64,
    
    -- Result
    success UInt8,
    error_code Int32,
    
    -- Security flags
    is_sensitive_path UInt8, -- /etc/passwd, /root, etc.
    
    -- Metadata
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, namespace, file_path)
TTL event_date + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- TABLE: request_metrics
-- Description: Aggregated request metrics (derived)
-- ============================================================================

CREATE TABLE IF NOT EXISTS request_metrics (
    -- Time bucket
    timestamp DateTime CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    source_namespace LowCardinality(String),
    source_workload String,
    destination_namespace LowCardinality(String),
    destination_workload String,
    destination_port UInt16,
    protocol LowCardinality(String),
    
    -- Metrics (aggregated per minute)
    request_count UInt64,
    request_rate Float32, -- requests/second
    
    -- Latency metrics
    avg_latency_ms Float32,
    p50_latency_ms Float32,
    p95_latency_ms Float32,
    p99_latency_ms Float32,
    max_latency_ms Float32,
    
    -- Throughput
    bytes_sent UInt64,
    bytes_received UInt64,
    
    -- Error metrics
    error_count UInt32,
    error_rate Float32,
    
    -- Connection metrics
    connection_count UInt32,
    active_connections UInt32,
    
    -- Metadata
    metadata String
    
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, source_workload, destination_workload)
TTL event_date + INTERVAL 180 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- TABLE: anomaly_scores
-- Description: Anomaly detection scores over time
-- ============================================================================

CREATE TABLE IF NOT EXISTS anomaly_scores (
    -- Timestamp
    timestamp DateTime CODEC(DoubleDelta, LZ4),
    event_date Date DEFAULT toDate(timestamp),
    
    -- Analysis context
    analysis_id String DEFAULT '',
    
    -- Context
    cluster_id UInt32,
    cluster_name LowCardinality(String),
    namespace LowCardinality(String),
    workload_name String,
    
    -- Anomaly details
    anomaly_type LowCardinality(String), -- traffic_spike, new_connection, unusual_port
    anomaly_score Float32, -- 0.0 to 1.0
    severity LowCardinality(String), -- low, medium, high, critical
    
    -- Baseline comparison
    baseline_value Float32,
    current_value Float32,
    deviation_percent Float32,
    
    -- Detection method
    detection_method LowCardinality(String), -- statistical, ml_model, llm
    model_version String,
    
    -- Metadata
    details String, -- JSON details
    metadata String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (cluster_id, event_date, timestamp, anomaly_type, workload_name)
TTL event_date + INTERVAL 180 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Skipping indexes for faster queries
ALTER TABLE network_flows ADD INDEX idx_source_workload (source_workload_name) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE network_flows ADD INDEX idx_dest_workload (destination_workload_name) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE network_flows ADD INDEX idx_dest_port (destination_port) TYPE set(100) GRANULARITY 4;

ALTER TABLE dns_queries ADD INDEX idx_query_name (query_name) TYPE bloom_filter GRANULARITY 4;

ALTER TABLE http_requests ADD INDEX idx_path (path) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE http_requests ADD INDEX idx_status_code (status_code) TYPE set(100) GRANULARITY 4;

-- ============================================================================
-- SAMPLE QUERIES (Documentation)
-- ============================================================================

-- Query 1: Get network flow summary for last hour
-- SELECT 
--     source_workload_name, 
--     destination_workload_name,
--     destination_port,
--     protocol,
--     count() as flow_count,
--     sum(bytes_sent) as total_bytes
-- FROM network_flows
-- WHERE timestamp >= now() - INTERVAL 1 HOUR
-- GROUP BY source_workload_name, destination_workload_name, destination_port, protocol
-- ORDER BY flow_count DESC
-- LIMIT 100;

-- Query 2: Get DNS query statistics
-- SELECT 
--     query_name,
--     query_type,
--     count() as query_count,
--     avg(response_time_ms) as avg_response_time,
--     countIf(response_code = 'NXDOMAIN') as nxdomain_count
-- FROM dns_queries
-- WHERE event_date = today()
-- GROUP BY query_name, query_type
-- ORDER BY query_count DESC
-- LIMIT 50;

-- Query 3: Get HTTP error rate by service
-- SELECT 
--     destination_workload,
--     path,
--     count() as total_requests,
--     countIf(status_code >= 400) as error_count,
--     (error_count / total_requests) * 100 as error_rate_percent
-- FROM http_requests
-- WHERE timestamp >= now() - INTERVAL 1 HOUR
-- GROUP BY destination_workload, path
-- HAVING error_rate_percent > 5
-- ORDER BY error_rate_percent DESC;

-- Query 4: Get latency percentiles
-- SELECT 
--     destination_workload,
--     avg(request_duration_ms) as avg_latency,
--     quantile(0.50)(request_duration_ms) as p50,
--     quantile(0.95)(request_duration_ms) as p95,
--     quantile(0.99)(request_duration_ms) as p99
-- FROM http_requests
-- WHERE event_date = today()
-- GROUP BY destination_workload;

-- Query 5: Detect traffic spikes (compared to previous hour)
-- WITH current_hour AS (
--     SELECT source_workload_name, count() as current_count
--     FROM network_flows
--     WHERE timestamp >= now() - INTERVAL 1 HOUR
--     GROUP BY source_workload_name
-- ),
-- previous_hour AS (
--     SELECT source_workload_name, count() as previous_count
--     FROM network_flows
--     WHERE timestamp >= now() - INTERVAL 2 HOUR
--       AND timestamp < now() - INTERVAL 1 HOUR
--     GROUP BY source_workload_name
-- )
-- SELECT 
--     c.source_workload_name,
--     c.current_count,
--     p.previous_count,
--     ((c.current_count - p.previous_count) / p.previous_count) * 100 as increase_percent
-- FROM current_hour c
-- JOIN previous_hour p ON c.source_workload_name = p.source_workload_name
-- WHERE increase_percent > 50
-- ORDER BY increase_percent DESC;

-- ============================================================================
-- OPTIMIZATION TIPS
-- ============================================================================

-- 1. Use PARTITION BY toYYYYMM(event_date) for time-based data
-- 2. ORDER BY should include frequently filtered columns
-- 3. Use LowCardinality for columns with <10K unique values
-- 4. Enable TTL for automatic data cleanup
-- 5. Use materialized views for pre-aggregated data
-- 6. Use AggregatingMergeTree for incremental aggregations
-- 7. Monitor query performance with EXPLAIN and system.query_log
-- 8. Use compression codecs (DoubleDelta, LZ4) for timestamp columns

-- ============================================================================
-- MONITORING
-- ============================================================================

-- Check table sizes
-- SELECT 
--     table,
--     formatReadableSize(sum(bytes)) as size,
--     sum(rows) as rows
-- FROM system.parts
-- WHERE database = 'flowfish'
-- GROUP BY table
-- ORDER BY sum(bytes) DESC;

-- Check partition sizes
-- SELECT 
--     table,
--     partition,
--     formatReadableSize(sum(bytes)) as size,
--     sum(rows) as rows
-- FROM system.parts
-- WHERE database = 'flowfish'
-- GROUP BY table, partition
-- ORDER BY table, partition;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

