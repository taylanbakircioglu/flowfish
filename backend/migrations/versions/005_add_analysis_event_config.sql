-- Migration: Add Analysis Event Configuration
-- Version: 005
-- Description: Store event type selections and filters per analysis
-- Date: 2024-01-20

BEGIN;

-- Create analysis_event_types table
CREATE TABLE IF NOT EXISTS analysis_event_types (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    event_type_id VARCHAR(50) NOT NULL, -- network_flow, dns_query, etc.
    enabled BOOLEAN DEFAULT TRUE,
    sampling_rate INTEGER DEFAULT 100, -- 0-100, 100 = all events
    filters JSONB DEFAULT '[]', -- Array of filter objects
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(analysis_id, event_type_id)
);

-- Index for fast lookups
CREATE INDEX idx_analysis_event_types_analysis_id ON analysis_event_types(analysis_id);
CREATE INDEX idx_analysis_event_types_event_type_id ON analysis_event_types(event_type_id);
CREATE INDEX idx_analysis_event_types_enabled ON analysis_event_types(enabled);

-- Trigger for updated_at
CREATE TRIGGER update_analysis_event_types_updated_at
    BEFORE UPDATE ON analysis_event_types
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Sample data for testing
-- (This would be inserted when an analysis is created)

COMMIT;

-- Rollback script
-- BEGIN;
-- DROP TABLE IF EXISTS analysis_event_types CASCADE;
-- COMMIT;

