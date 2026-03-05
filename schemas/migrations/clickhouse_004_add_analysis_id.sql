-- ============================================================================
-- ClickHouse Migration: Add analysis_id column to all event tables
-- ============================================================================
-- Version: 1.0.4
-- Date: January 2025
-- Description: Adds analysis_id column for filtering events by analysis
-- ============================================================================

-- Add analysis_id to network_flows
ALTER TABLE flowfish.network_flows ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to dns_queries
ALTER TABLE flowfish.dns_queries ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to tcp_connections
ALTER TABLE flowfish.tcp_connections ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to process_events
ALTER TABLE flowfish.process_events ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to file_access_events
ALTER TABLE flowfish.file_access_events ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to http_requests
ALTER TABLE flowfish.http_requests ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to syscall_events
ALTER TABLE flowfish.syscall_events ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to request_metrics
ALTER TABLE flowfish.request_metrics ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Add analysis_id to anomaly_scores
ALTER TABLE flowfish.anomaly_scores ADD COLUMN IF NOT EXISTS analysis_id String DEFAULT '';

-- Create indexes for analysis_id filtering
-- Note: These are skip indexes for faster filtering
ALTER TABLE flowfish.network_flows ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.dns_queries ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.tcp_connections ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.process_events ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.file_access_events ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.http_requests ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.syscall_events ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.request_metrics ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;
ALTER TABLE flowfish.anomaly_scores ADD INDEX IF NOT EXISTS idx_analysis_id (analysis_id) TYPE bloom_filter GRANULARITY 4;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================

