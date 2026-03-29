-- ClickHouse Change Events Schema
-- Hybrid Architecture: ClickHouse for high-volume change event storage
-- Version: 1.0
--
-- NOTES:
-- - NO TTL: Data retained until analysis is deleted (analysis lifecycle)
-- - Deletion handled by delete_analysis() cascade
-- - run_id included for run-based filtering and comparison
-- - ReplacingMergeTree for idempotency (dedupe by event_id)
-- - ORDER BY starts with analysis_id for fast cascade deletes

CREATE DATABASE IF NOT EXISTS flowfish;
USE flowfish;

-- =============================================================================
-- 1. CHANGE EVENTS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS change_events (
    -- Timestamps
    timestamp DateTime64(3) DEFAULT now64(3),
    detected_at DateTime64(3),
    
    -- Identifiers (for idempotency and cascade delete)
    event_id UUID DEFAULT generateUUIDv4(),
    cluster_id UInt32,
    cluster_name String DEFAULT '',
    analysis_id String,  -- String for multi-cluster format: "123" or "123-456"
    
    -- Run Information (for run-based filtering)
    run_id UInt32 DEFAULT 0,           -- FK to analysis_runs.id
    run_number UInt16 DEFAULT 1,       -- Human-readable run number (1, 2, 3...)
    
    -- Change Details
    change_type LowCardinality(String),  -- workload_added, workload_removed, connection_added, etc.
    risk_level LowCardinality(String) DEFAULT 'medium',  -- critical, high, medium, low
    
    -- Target Info
    target_name String DEFAULT '',
    target_namespace String DEFAULT '',
    target_type LowCardinality(String) DEFAULT 'workload',  -- workload, communication, namespace
    entity_id UInt64 DEFAULT 0,
    namespace_id Nullable(UInt32),
    
    -- State (JSON strings for flexibility)
    before_state String DEFAULT '{}',
    after_state String DEFAULT '{}',
    
    -- Impact Assessment
    affected_services UInt16 DEFAULT 0,
    blast_radius UInt16 DEFAULT 0,
    
    -- Audit
    changed_by String DEFAULT 'auto-discovery',
    details String DEFAULT '',
    metadata String DEFAULT '{}'
    
) ENGINE = ReplacingMergeTree(timestamp)  -- Deduplication by event_id using latest timestamp
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (analysis_id, run_id, timestamp, event_id)  -- analysis_id FIRST for fast cascade deletes
SETTINGS index_granularity = 8192;
-- NOTE: NO TTL - data retained until analysis is deleted via delete_analysis()

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ce_run_id ON change_events (run_id) TYPE minmax();
CREATE INDEX IF NOT EXISTS idx_ce_change_type ON change_events (change_type) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_ce_risk_level ON change_events (risk_level) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_ce_target_name ON change_events (target_name) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_ce_target_namespace ON change_events (target_namespace) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_ce_cluster_id ON change_events (cluster_id) TYPE minmax();

-- =============================================================================
-- 2. MATERIALIZED VIEW: Hourly Aggregations (for dashboard)
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS change_events_hourly_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (analysis_id, run_id, hour, change_type, risk_level)
AS SELECT
    analysis_id,
    run_id,
    cluster_id,
    toStartOfHour(timestamp) AS hour,
    change_type,
    risk_level,
    count() AS change_count,
    uniq(target_name) AS unique_targets,
    sum(affected_services) AS total_affected
FROM change_events
GROUP BY analysis_id, run_id, cluster_id, hour, change_type, risk_level;

-- =============================================================================
-- 3. MATERIALIZED VIEW: Per-Run Statistics (for run comparison)
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS change_events_run_stats_mv
ENGINE = SummingMergeTree()
ORDER BY (analysis_id, run_id)
AS SELECT
    analysis_id,
    run_id,
    anyLast(run_number) AS run_number,
    cluster_id,
    count() AS total_changes,
    countIf(risk_level = 'critical') AS critical_count,
    countIf(risk_level = 'high') AS high_count,
    countIf(risk_level = 'medium') AS medium_count,
    countIf(risk_level = 'low') AS low_count,
    -- Legacy / Workload lifecycle
    countIf(change_type = 'workload_added') AS workloads_added,
    countIf(change_type = 'workload_removed') AS workloads_removed,
    -- K8s API - Workload changes
    countIf(change_type = 'replica_changed') AS replicas_changed,
    countIf(change_type = 'config_changed') AS configs_changed,
    countIf(change_type = 'image_changed') AS images_changed,
    countIf(change_type = 'label_changed') AS labels_changed,
    countIf(change_type = 'resource_changed') AS resources_changed,
    countIf(change_type = 'env_changed') AS envs_changed,
    countIf(change_type = 'spec_changed') AS specs_changed,
    -- K8s API - Service changes
    countIf(change_type = 'service_added') AS services_added,
    countIf(change_type = 'service_removed') AS services_removed,
    countIf(change_type = 'service_port_changed') AS service_ports_changed,
    countIf(change_type = 'service_selector_changed') AS service_selectors_changed,
    countIf(change_type = 'service_type_changed') AS service_types_changed,
    -- K8s API - Network / Ingress / Route
    countIf(change_type IN ('network_policy_added','network_policy_removed','network_policy_changed')) AS network_policy_changes,
    countIf(change_type IN ('ingress_added','ingress_removed','ingress_changed')) AS ingress_changes,
    countIf(change_type IN ('route_added','route_removed','route_changed')) AS route_changes,
    -- eBPF - Connections
    countIf(change_type = 'connection_added') AS connections_added,
    countIf(change_type = 'connection_removed') AS connections_removed,
    countIf(change_type = 'port_changed') AS ports_changed,
    -- eBPF - Anomalies
    countIf(change_type IN ('traffic_anomaly','dns_anomaly','process_anomaly','error_anomaly')) AS anomalies_total,
    -- Namespace
    countIf(change_type = 'namespace_changed') AS namespaces_changed,
    min(timestamp) AS first_change_at,
    max(timestamp) AS last_change_at
FROM change_events
GROUP BY analysis_id, run_id, cluster_id;

-- =============================================================================
-- 4. MATERIALIZED VIEW: Daily Summary (for trends)
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS change_events_daily_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (analysis_id, day, cluster_id)
AS SELECT
    analysis_id,
    cluster_id,
    toDate(timestamp) AS day,
    count() AS total_changes,
    countIf(risk_level = 'critical') AS critical_count,
    countIf(risk_level = 'high') AS high_count,
    uniq(target_name) AS unique_targets,
    uniq(target_namespace) AS unique_namespaces,
    uniq(run_id) AS runs_count
FROM change_events
GROUP BY analysis_id, cluster_id, day;

-- =============================================================================
-- USEFUL QUERIES
-- =============================================================================

-- Get changes for a specific analysis and run
-- SELECT * FROM change_events 
-- WHERE analysis_id = '123' AND run_id = 1
-- ORDER BY timestamp DESC
-- LIMIT 100;

-- Compare two runs
-- SELECT 
--     run_id,
--     count() as total_changes,
--     countIf(risk_level = 'critical') as critical,
--     countIf(risk_level = 'high') as high
-- FROM change_events
-- WHERE analysis_id = '123' AND run_id IN (1, 2)
-- GROUP BY run_id;

-- Get run statistics from materialized view
-- SELECT * FROM change_events_run_stats_mv
-- WHERE analysis_id = '123'
-- ORDER BY run_id;

-- Delete all change events for an analysis (used by delete_analysis cascade)
-- ALTER TABLE change_events DELETE WHERE analysis_id = '123' OR analysis_id LIKE '123-%';

