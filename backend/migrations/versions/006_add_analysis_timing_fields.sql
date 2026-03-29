-- Migration: Add started_at and stopped_at fields to analyses table
-- These fields are used by auto-stop monitor to track analysis execution time

-- Add started_at column (when analysis started running)
ALTER TABLE analyses 
ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NULL;

-- Add stopped_at column (when analysis stopped/completed/failed)
ALTER TABLE analyses 
ADD COLUMN IF NOT EXISTS stopped_at TIMESTAMP NULL;

-- Create index for faster querying of running analyses
CREATE INDEX IF NOT EXISTS idx_analyses_started_at ON analyses(started_at) 
WHERE status = 'running';

-- Comment on columns
COMMENT ON COLUMN analyses.started_at IS 'Timestamp when analysis started running (for auto-stop calculation)';
COMMENT ON COLUMN analyses.stopped_at IS 'Timestamp when analysis stopped/completed/failed';

