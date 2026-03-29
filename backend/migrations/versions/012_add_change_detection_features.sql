-- ============================================================================
-- Migration: 012_add_change_detection_features
-- Description: Add Sprint 6 features - baseline marking, notifications
-- Date: January 2025
-- 
-- NOTE: change_events table removed from PostgreSQL (moved to ClickHouse only)
-- ============================================================================

-- ============================================================================
-- Part 1: Baseline Analysis Support
-- ============================================================================

-- Add is_baseline flag to analyses table
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS is_baseline BOOLEAN DEFAULT false;

-- Add baseline_marked_at timestamp
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS baseline_marked_at TIMESTAMP WITH TIME ZONE;

-- Add baseline_marked_by to track who marked it
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS baseline_marked_by VARCHAR(255);

-- Create index for baseline queries
CREATE INDEX IF NOT EXISTS idx_analyses_is_baseline ON analyses(is_baseline) WHERE is_baseline = true;

-- Comment on new columns
COMMENT ON COLUMN analyses.is_baseline IS 'Whether this analysis is marked as the baseline for drift detection';
COMMENT ON COLUMN analyses.baseline_marked_at IS 'When this analysis was marked as baseline';
COMMENT ON COLUMN analyses.baseline_marked_by IS 'Who marked this analysis as baseline';

-- ============================================================================
-- Part 2: Notification Hooks Configuration
-- ============================================================================

-- Create notification_hooks table for storing webhook/integration configs
CREATE TABLE IF NOT EXISTS notification_hooks (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    hook_type VARCHAR(50) NOT NULL, -- slack, teams, email, webhook
    config JSONB NOT NULL DEFAULT '{}', -- type-specific configuration
    is_enabled BOOLEAN DEFAULT true,
    
    -- Trigger conditions
    trigger_on_critical BOOLEAN DEFAULT true,
    trigger_on_high BOOLEAN DEFAULT true,
    trigger_on_medium BOOLEAN DEFAULT false,
    trigger_on_low BOOLEAN DEFAULT false,
    trigger_change_types TEXT[], -- array of change types to trigger on
    
    -- Rate limiting
    rate_limit_per_hour INTEGER DEFAULT 100,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT chk_hook_type CHECK (hook_type IN ('slack', 'teams', 'email', 'webhook'))
);

-- Create indexes for enabled hooks
CREATE INDEX IF NOT EXISTS idx_notification_hooks_enabled ON notification_hooks(cluster_id, is_enabled) 
    WHERE is_enabled = true;
CREATE INDEX IF NOT EXISTS idx_notification_hooks_cluster ON notification_hooks(cluster_id);

-- Comment on table
COMMENT ON TABLE notification_hooks IS 'Configuration for notification integrations (Slack, Teams, Email, Webhooks)';

-- ============================================================================
-- Track migration
-- ============================================================================
INSERT INTO schema_migrations (version, name) 
VALUES (12, 'change_detection_features')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
