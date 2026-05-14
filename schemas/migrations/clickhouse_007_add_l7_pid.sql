-- ============================================================================
-- ClickHouse Migration: PID-based Virtual Trace Correlation (Phase 4B)
-- ============================================================================
-- Version: 1.0.7
-- Date: April 2026
-- Description:
--   Adds the columns needed for PID-temporal virtual_trace_id correlation
--   to L7 HTTP and gRPC flows. When a service does NOT propagate W3C
--   `traceparent` headers, Beyla emits a single-hop span per request with
--   an empty trace_id. The timeseries-writer then groups consecutive
--   spans on the same (cluster, pod, container, pid) within a 50ms
--   window into a single virtual trace, identified by a sha1 hash.
--
--   When the producing service IS instrumented, the existing W3C
--   trace_id is preserved untouched — virtual_trace_id is independent
--   and only used for the fallback grouping.
--
-- Schema additions (idempotent — safe to re-run):
--   * pid                — Linux PID of the producing thread (UInt32)
--   * ppid               — Parent PID, used for cross-thread join
--   * container_id       — Stable container ID; PID can be reused so
--                          (pod, container_id, pid) is required to
--                          uniquely scope a process within a 50ms window
--   * virtual_trace_id   — sha1 hash output by the writer's correlator
--   * idx_virtual_trace_id — bloom filter to accelerate trace lookup
--                            via OR clause (`trace_id = X OR virtual_trace_id = X`)
--
-- DNS is intentionally excluded: a "DNS trace" is single-RPC by
-- definition and has no peer span to stitch.
--
-- Manual deployment (no auto-runner exists, see Plan Section 16.A):
--   clickhouse-client --user="$CH_USER" --password="$CH_PASS" \
--     --database=flowfish --multiquery < clickhouse_007_add_l7_pid.sql
--
-- Backwards compatibility:
--   * All new columns DEFAULT to 0 / '', so existing rows keep working.
--   * Existing query_l7_http_histogram / get_recent_traces queries do
--     not reference these columns — no behaviour change for them.
--   * get_trace_spans is updated separately (Phase 4E) to OR the new
--     virtual_trace_id; that migration is feature-flagged.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- HTTP flows: pid + ppid + container_id + virtual_trace_id + bloom index
-- ----------------------------------------------------------------------------
ALTER TABLE flowfish.l7_http_flows
    ADD COLUMN IF NOT EXISTS pid UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ppid UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS container_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS virtual_trace_id String DEFAULT '';

ALTER TABLE flowfish.l7_http_flows
    ADD INDEX IF NOT EXISTS idx_virtual_trace_id virtual_trace_id TYPE bloom_filter(0.01) GRANULARITY 4;

-- Materialize the index over historical rows (no-op for empty
-- virtual_trace_id but harmless). Heavy on large tables.
ALTER TABLE flowfish.l7_http_flows MATERIALIZE INDEX idx_virtual_trace_id;

-- ----------------------------------------------------------------------------
-- gRPC flows: same shape as HTTP
-- ----------------------------------------------------------------------------
ALTER TABLE flowfish.l7_grpc_flows
    ADD COLUMN IF NOT EXISTS pid UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ppid UInt32 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS container_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS virtual_trace_id String DEFAULT '';

ALTER TABLE flowfish.l7_grpc_flows
    ADD INDEX IF NOT EXISTS idx_virtual_trace_id virtual_trace_id TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE flowfish.l7_grpc_flows MATERIALIZE INDEX idx_virtual_trace_id;

-- ----------------------------------------------------------------------------
-- Verification queries (run manually after migration):
--
--   -- 1. Columns exist:
--   SELECT name, type
--   FROM system.columns
--   WHERE database = 'flowfish'
--     AND table = 'l7_http_flows'
--     AND name IN ('pid', 'ppid', 'container_id', 'virtual_trace_id');
--   -- Expected: 4 rows.
--
--   -- 2. Index exists:
--   SELECT name, type, expr
--   FROM system.data_skipping_indices
--   WHERE database = 'flowfish'
--     AND table IN ('l7_http_flows', 'l7_grpc_flows')
--     AND name = 'idx_virtual_trace_id';
--   -- Expected: 2 rows (one per table).
--
--   -- 3. Once Phase 4C/4D is deployed, fresh inserts populate pid:
--   SELECT countIf(pid > 0) AS with_pid, count() AS total
--   FROM flowfish.l7_http_flows
--   WHERE timestamp >= now() - INTERVAL 5 MINUTE;
--   -- with_pid / total should grow toward 1.0 once writers redeploy.
-- ============================================================================
