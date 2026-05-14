-- ============================================================================
-- L7 Application Level Tables (Beyla eBPF)
-- Completely separate from L4 tables - no existing tables are modified
-- ============================================================================

-- L7 HTTP Flows
CREATE TABLE IF NOT EXISTS l7_http_flows (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    cluster_id String,
    cluster_name String,
    analysis_id String,
    -- Source
    src_namespace String,
    src_workload String,
    src_pod String,
    src_ip String,
    src_port UInt16,
    -- Destination
    dst_namespace String,
    dst_workload String,
    dst_pod String,
    dst_ip String,
    dst_port UInt16,
    dst_service String,
    -- HTTP
    http_method String,
    http_path String,
    http_host String,
    http_status_code UInt16,
    http_version String,
    content_type String,
    -- Metrics
    request_size UInt64,
    response_size UInt64,
    latency_ms Float64,
    -- Labels
    src_labels String DEFAULT '{}',
    dst_labels String DEFAULT '{}',
    request_headers String DEFAULT '{}',
    -- L7 W3C Distributed Trace columns from OpenTelemetry/Beyla.
    -- NOT to be confused with Inspector Gadget session "trace_id" in L4 pipeline.
    trace_id String DEFAULT '',           -- W3C trace ID (16-byte hex)
    span_id String DEFAULT '',            -- OTLP span ID (8-byte hex)
    parent_span_id String DEFAULT '',     -- OTLP parent span ID (8-byte hex)
    span_name String DEFAULT '',          -- OTLP span name
    span_kind UInt8 DEFAULT 0,            -- 1=INTERNAL, 2=SERVER, 3=CLIENT, 4=PRODUCER, 5=CONSUMER
    event_data_json String,
    INDEX idx_trace_id trace_id TYPE bloom_filter GRANULARITY 4
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (analysis_id, cluster_id, timestamp, src_namespace, dst_namespace)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

-- L7 gRPC Flows
CREATE TABLE IF NOT EXISTS l7_grpc_flows (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    cluster_id String,
    cluster_name String,
    analysis_id String,
    -- Source
    src_namespace String,
    src_workload String,
    src_pod String,
    src_ip String,
    src_port UInt16,
    -- Destination
    dst_namespace String,
    dst_workload String,
    dst_pod String,
    dst_ip String,
    dst_port UInt16,
    dst_service String,
    -- gRPC
    grpc_service String,
    grpc_method String,
    grpc_status_code Int32,
    grpc_status_message String,
    -- Metrics
    request_size UInt64,
    response_size UInt64,
    latency_ms Float64,
    -- Labels
    src_labels String DEFAULT '{}',
    dst_labels String DEFAULT '{}',
    -- L7 W3C Distributed Trace columns (see l7_http_flows for context)
    trace_id String DEFAULT '',
    span_id String DEFAULT '',
    parent_span_id String DEFAULT '',
    span_name String DEFAULT '',
    span_kind UInt8 DEFAULT 0,
    event_data_json String,
    INDEX idx_trace_id trace_id TYPE bloom_filter GRANULARITY 4
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (analysis_id, cluster_id, timestamp, src_namespace, dst_namespace)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

-- L7 DNS Flows
CREATE TABLE IF NOT EXISTS l7_dns_flows (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    cluster_id String,
    cluster_name String,
    analysis_id String,
    -- Source
    src_namespace String,
    src_workload String,
    src_pod String,
    src_ip String,
    src_port UInt16,
    -- Destination
    dst_namespace String,
    dst_workload String,
    dst_pod String,
    dst_ip String,
    dst_port UInt16,
    -- DNS
    query_name String,
    query_type String,
    response_code Int32,
    response_ips String DEFAULT '[]',
    -- Metrics
    latency_ms Float64,
    -- Labels
    src_labels String DEFAULT '{}',
    dst_labels String DEFAULT '{}',
    -- L7 W3C Distributed Trace columns (see l7_http_flows for context).
    -- NOTE: DNS spans typically have trace context but cannot propagate traceparent
    -- (DNS protocol has no header support). Useful for correlation only.
    trace_id String DEFAULT '',
    span_id String DEFAULT '',
    parent_span_id String DEFAULT '',
    span_name String DEFAULT '',
    span_kind UInt8 DEFAULT 0,
    event_data_json String,
    INDEX idx_trace_id trace_id TYPE bloom_filter GRANULARITY 4
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (analysis_id, cluster_id, timestamp, src_namespace, query_name)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

-- L7 HTTP Flows 5-minute Materialized View
-- Uses SummingMergeTree with sum(latency_ms) so avg = total_latency / request_count at query time.
CREATE MATERIALIZED VIEW IF NOT EXISTS l7_http_flows_5min_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (analysis_id, timestamp_5min, cluster_id, src_workload, dst_workload, http_method, http_path)
AS SELECT
    analysis_id,
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    src_workload, dst_workload,
    http_method, http_path,
    count() AS request_count,
    countIf(http_status_code >= 400) AS error_count,
    sum(latency_ms) AS total_latency_ms,
    sum(request_size) AS total_request_size,
    sum(response_size) AS total_response_size
FROM l7_http_flows
GROUP BY analysis_id, timestamp_5min, cluster_id, src_workload, dst_workload, http_method, http_path;
