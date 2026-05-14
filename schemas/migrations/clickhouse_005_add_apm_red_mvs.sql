-- ============================================================================
-- ClickHouse Migration: APM RED Materialized Views (Phase 2)
-- ============================================================================
-- Version: 1.0.5
-- Date: April 2026
-- Description:
--   Adds 5 AggregatingMergeTree MVs that pre-aggregate L7 flow data into
--   RED metrics (Rate, Errors, Duration p50/p95/p99) at 5-minute granularity.
--
--   The existing `l7_http_flows_5min_mv` is a SummingMergeTree — it can give
--   us avg latency (sum/count) but NOT percentiles (raw values are lost).
--   APM enterprise dashboards need p95 / p99 to answer "is the tail latency
--   getting worse?" so we add parallel MVs that store
--   `quantileTDigestState(latency_ms)` instead. Existing MV is left untouched
--   for backward-compat with `query_l7_http_histogram`.
--
--   Two granularity layers:
--     - `_red_svc_5min` — service-level (cluster, src_workload, dst_workload)
--     - `_red_ops_5min` — operation-level (HTTP method+path_normalized,
--                          gRPC service+method)
--   DNS is service-level only because `query_name` is high-cardinality.
--
--   Path normalization (HTTP only) collapses ID-bearing paths
--   (`/users/123` → `/users/{id}`, `/orders/abc-uuid-...` → `/orders/{uuid}`)
--   to keep operation cardinality bounded. See Plan v1.4 Section 13.AF for
--   the rationale and Section 13.AK for write-amplification monitoring.
-- ============================================================================

-- ============================================================================
-- HTTP service-level RED MV (rate + errors + p50/p95/p99 per workload pair)
-- ============================================================================
CREATE TABLE IF NOT EXISTS flowfish.l7_http_red_svc_5min (
    timestamp_5min DateTime,
    cluster_id String,
    analysis_id String,
    src_workload String,
    dst_workload String,
    src_namespace String,
    dst_namespace String,
    request_count_state AggregateFunction(sum, UInt64),
    error_count_state AggregateFunction(sum, UInt64),
    lat_quantile_state AggregateFunction(quantileTDigest, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (cluster_id, analysis_id, dst_workload, src_workload, timestamp_5min)
TTL toDateTime(timestamp_5min) + INTERVAL 30 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS flowfish.l7_http_red_svc_5min_mv
TO flowfish.l7_http_red_svc_5min AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    analysis_id,
    src_workload,
    dst_workload,
    src_namespace,
    dst_namespace,
    sumState(toUInt64(1)) AS request_count_state,
    sumState(toUInt64(if(http_status_code >= 400, 1, 0))) AS error_count_state,
    quantileTDigestState(latency_ms) AS lat_quantile_state
FROM flowfish.l7_http_flows
GROUP BY timestamp_5min, cluster_id, analysis_id,
         src_workload, dst_workload, src_namespace, dst_namespace;

-- ============================================================================
-- HTTP operation-level RED MV (per HTTP method + normalized path)
-- ============================================================================
CREATE TABLE IF NOT EXISTS flowfish.l7_http_red_ops_5min (
    timestamp_5min DateTime,
    cluster_id String,
    analysis_id String,
    dst_workload String,
    dst_namespace String,
    http_method String,
    http_path_normalized String,
    request_count_state AggregateFunction(sum, UInt64),
    error_count_state AggregateFunction(sum, UInt64),
    lat_quantile_state AggregateFunction(quantileTDigest, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (cluster_id, analysis_id, dst_workload, http_method, http_path_normalized, timestamp_5min)
TTL toDateTime(timestamp_5min) + INTERVAL 30 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS flowfish.l7_http_red_ops_5min_mv
TO flowfish.l7_http_red_ops_5min AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    analysis_id,
    dst_workload,
    dst_namespace,
    http_method,
    -- Normalize numeric IDs and UUIDs (Plan v1.4 Section 13.AF):
    --   /users/123       -> /users/{id}
    --   /orders/abc-uuid -> /orders/{uuid}
    -- Inner replace runs first (numeric IDs), outer replaces 16+ char hex
    -- segments common in UUIDs / hashes / opaque tokens.
    replaceRegexpAll(
        replaceRegexpAll(http_path, '/[0-9]+(/|$)', '/{id}\\1'),
        '/[0-9a-f-]{16,}(/|$)', '/{uuid}\\1'
    ) AS http_path_normalized,
    sumState(toUInt64(1)) AS request_count_state,
    sumState(toUInt64(if(http_status_code >= 400, 1, 0))) AS error_count_state,
    quantileTDigestState(latency_ms) AS lat_quantile_state
FROM flowfish.l7_http_flows
GROUP BY timestamp_5min, cluster_id, analysis_id, dst_workload,
         dst_namespace, http_method, http_path_normalized;

-- ============================================================================
-- gRPC service-level RED MV
-- ============================================================================
CREATE TABLE IF NOT EXISTS flowfish.l7_grpc_red_svc_5min (
    timestamp_5min DateTime,
    cluster_id String,
    analysis_id String,
    src_workload String,
    dst_workload String,
    src_namespace String,
    dst_namespace String,
    request_count_state AggregateFunction(sum, UInt64),
    error_count_state AggregateFunction(sum, UInt64),
    lat_quantile_state AggregateFunction(quantileTDigest, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (cluster_id, analysis_id, dst_workload, src_workload, timestamp_5min)
TTL toDateTime(timestamp_5min) + INTERVAL 30 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS flowfish.l7_grpc_red_svc_5min_mv
TO flowfish.l7_grpc_red_svc_5min AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    analysis_id,
    src_workload,
    dst_workload,
    src_namespace,
    dst_namespace,
    sumState(toUInt64(1)) AS request_count_state,
    sumState(toUInt64(if(grpc_status_code != 0, 1, 0))) AS error_count_state,
    quantileTDigestState(latency_ms) AS lat_quantile_state
FROM flowfish.l7_grpc_flows
GROUP BY timestamp_5min, cluster_id, analysis_id,
         src_workload, dst_workload, src_namespace, dst_namespace;

-- ============================================================================
-- gRPC operation-level RED MV (grpc_service+grpc_method already low-cardinality)
-- ============================================================================
CREATE TABLE IF NOT EXISTS flowfish.l7_grpc_red_ops_5min (
    timestamp_5min DateTime,
    cluster_id String,
    analysis_id String,
    dst_workload String,
    dst_namespace String,
    grpc_service String,
    grpc_method String,
    request_count_state AggregateFunction(sum, UInt64),
    error_count_state AggregateFunction(sum, UInt64),
    lat_quantile_state AggregateFunction(quantileTDigest, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (cluster_id, analysis_id, dst_workload, grpc_service, grpc_method, timestamp_5min)
TTL toDateTime(timestamp_5min) + INTERVAL 30 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS flowfish.l7_grpc_red_ops_5min_mv
TO flowfish.l7_grpc_red_ops_5min AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    analysis_id,
    dst_workload,
    dst_namespace,
    grpc_service,
    grpc_method,
    sumState(toUInt64(1)) AS request_count_state,
    sumState(toUInt64(if(grpc_status_code != 0, 1, 0))) AS error_count_state,
    quantileTDigestState(latency_ms) AS lat_quantile_state
FROM flowfish.l7_grpc_flows
GROUP BY timestamp_5min, cluster_id, analysis_id,
         dst_workload, dst_namespace, grpc_service, grpc_method;

-- ============================================================================
-- DNS service-level RED MV (no operation-level — query_name is high-cardinality)
-- ============================================================================
CREATE TABLE IF NOT EXISTS flowfish.l7_dns_red_svc_5min (
    timestamp_5min DateTime,
    cluster_id String,
    analysis_id String,
    src_workload String,
    dst_workload String,
    src_namespace String,
    request_count_state AggregateFunction(sum, UInt64),
    error_count_state AggregateFunction(sum, UInt64),
    lat_quantile_state AggregateFunction(quantileTDigest, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (cluster_id, analysis_id, dst_workload, src_workload, timestamp_5min)
TTL toDateTime(timestamp_5min) + INTERVAL 30 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS flowfish.l7_dns_red_svc_5min_mv
TO flowfish.l7_dns_red_svc_5min AS
SELECT
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    analysis_id,
    src_workload,
    dst_workload,
    src_namespace,
    sumState(toUInt64(1)) AS request_count_state,
    sumState(toUInt64(if(response_code != 0, 1, 0))) AS error_count_state,
    quantileTDigestState(latency_ms) AS lat_quantile_state
FROM flowfish.l7_dns_flows
GROUP BY timestamp_5min, cluster_id, analysis_id,
         src_workload, dst_workload, src_namespace;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
