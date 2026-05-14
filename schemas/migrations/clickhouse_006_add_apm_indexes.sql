-- ============================================================================
-- ClickHouse Migration: APM Indexes for Related Traces (Phase 3B)
-- ============================================================================
-- Version: 1.0.6
-- Date: April 2026
-- Description:
--   Adds bloom_filter indexes on src_pod and dst_pod columns of L7 flow
--   tables. These accelerate "Related Traces" queries that pivot from a
--   single trace to other traces sharing the same source or destination
--   pod (Section 16.F of the APM-style L7 Refactor plan, v1.5).
--
--   Rationale:
--     - Same-pod correlation: "show me other traces hitting the same
--       backend pod within the last N minutes". Without an index this is
--       a full partition scan; bloom filters narrow it to a few granules.
--     - bloom_filter(0.01) gives 1% false-positive rate which is fine
--       for *narrowing* — the WHERE clause still filters exactly.
--     - GRANULARITY 4 means one bloom per 4 granules of 8192 rows = 32K
--       rows per filter unit. Good balance for high-cardinality pods.
--
--   Idempotency:
--     IF NOT EXISTS guards every ADD INDEX, so re-running this script is
--     safe. The MATERIALIZE INDEX statements are *not* idempotent in the
--     strict sense (they always re-materialize) but they don't error.
--
--   Manual deployment (no auto-runner exists, see Plan Section 16.A):
--     clickhouse-client --user="$CH_USER" --password="$CH_PASS" \
--       --database=flowfish --multiquery < clickhouse_006_add_apm_indexes.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- HTTP flows: src_pod + dst_pod indexes
-- ----------------------------------------------------------------------------
ALTER TABLE flowfish.l7_http_flows
    ADD INDEX IF NOT EXISTS idx_src_pod src_pod TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE flowfish.l7_http_flows
    ADD INDEX IF NOT EXISTS idx_dst_pod dst_pod TYPE bloom_filter(0.01) GRANULARITY 4;

-- Materialize over existing data so historical rows benefit immediately.
-- This is a heavy operation on large tables; run during a low-traffic window.
ALTER TABLE flowfish.l7_http_flows MATERIALIZE INDEX idx_src_pod;
ALTER TABLE flowfish.l7_http_flows MATERIALIZE INDEX idx_dst_pod;

-- ----------------------------------------------------------------------------
-- gRPC flows: src_pod + dst_pod indexes
-- ----------------------------------------------------------------------------
ALTER TABLE flowfish.l7_grpc_flows
    ADD INDEX IF NOT EXISTS idx_src_pod src_pod TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE flowfish.l7_grpc_flows
    ADD INDEX IF NOT EXISTS idx_dst_pod dst_pod TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE flowfish.l7_grpc_flows MATERIALIZE INDEX idx_src_pod;
ALTER TABLE flowfish.l7_grpc_flows MATERIALIZE INDEX idx_dst_pod;

-- ----------------------------------------------------------------------------
-- DNS flows: only src_pod (DNS has no dst_pod — destination is a resolver)
-- ----------------------------------------------------------------------------
ALTER TABLE flowfish.l7_dns_flows
    ADD INDEX IF NOT EXISTS idx_src_pod src_pod TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE flowfish.l7_dns_flows MATERIALIZE INDEX idx_src_pod;

-- ----------------------------------------------------------------------------
-- Verification queries (run manually after migration):
--
--   SELECT name, type, expr, granularity
--   FROM system.data_skipping_indices
--   WHERE database = 'flowfish'
--     AND table IN ('l7_http_flows', 'l7_grpc_flows', 'l7_dns_flows')
--     AND name IN ('idx_src_pod', 'idx_dst_pod');
--
-- Expected: 5 rows (HTTP×2 + gRPC×2 + DNS×1).
-- ============================================================================
