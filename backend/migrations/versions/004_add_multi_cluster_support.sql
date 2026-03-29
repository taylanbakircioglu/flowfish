-- Migration: Add multi-cluster support to analyses table
-- Date: 2025-01-19
-- Description: Adds cluster_ids and is_multi_cluster columns for multi-cluster analysis support

-- Add cluster_ids column (JSONB array of cluster IDs)
ALTER TABLE analyses 
ADD COLUMN IF NOT EXISTS cluster_ids JSONB DEFAULT '[]'::jsonb;

-- Add is_multi_cluster flag
ALTER TABLE analyses 
ADD COLUMN IF NOT EXISTS is_multi_cluster BOOLEAN DEFAULT FALSE;

-- Create index for is_multi_cluster flag
CREATE INDEX IF NOT EXISTS idx_analyses_is_multi_cluster ON analyses(is_multi_cluster);

-- Create GIN index for cluster_ids array search
CREATE INDEX IF NOT EXISTS idx_analyses_cluster_ids ON analyses USING GIN(cluster_ids);

-- Update existing analyses to have cluster_ids populated with their cluster_id
UPDATE analyses 
SET cluster_ids = jsonb_build_array(cluster_id)
WHERE cluster_ids = '[]'::jsonb OR cluster_ids IS NULL;

-- Comment for documentation
COMMENT ON COLUMN analyses.cluster_ids IS 'JSON array of cluster IDs for multi-cluster analysis. Primary cluster_id is always included.';
COMMENT ON COLUMN analyses.is_multi_cluster IS 'Flag indicating this analysis spans multiple clusters';

