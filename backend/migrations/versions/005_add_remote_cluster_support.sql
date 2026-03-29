-- Migration: Add remote cluster support to clusters table
-- Date: 2025-01-19
-- Description: Adds CA certificate, TLS verification, and Inspector Gadget configuration for remote clusters

-- Add CA certificate column for remote cluster connections
ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS ca_cert_encrypted TEXT;

-- Add TLS verification skip flag
ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS skip_tls_verify BOOLEAN DEFAULT FALSE;

-- Add connection type to track how we connect to the cluster
ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS connection_type VARCHAR(50) DEFAULT 'in-cluster';

-- Add Inspector Gadget configuration columns
ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS gadget_endpoint TEXT;

ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS gadget_namespace VARCHAR(255);

-- Update existing clusters: set gadget_namespace based on existing gadget_endpoint or use flowfish namespace
-- This ensures all existing clusters have a valid gadget_namespace before making it NOT NULL
UPDATE clusters
SET gadget_namespace = COALESCE(
    -- Try to extract namespace from gadget_endpoint (format: inspektor-gadget.NAMESPACE.svc...)
    CASE 
        WHEN gadget_endpoint LIKE '%.%.svc%' THEN 
            SPLIT_PART(SPLIT_PART(gadget_endpoint, '.', 2), '.', 1)
        ELSE NULL
    END,
    -- Fallback: use the OpenShift namespace from environment or 'flowfish'
    'flowfish'
)
WHERE gadget_namespace IS NULL OR gadget_namespace = '';

-- Now make gadget_namespace NOT NULL (safe because we updated all existing rows)
ALTER TABLE clusters
ALTER COLUMN gadget_namespace SET NOT NULL;

ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS gadget_health_status VARCHAR(50) DEFAULT 'unknown';

ALTER TABLE clusters
ADD COLUMN IF NOT EXISTS gadget_version VARCHAR(50);

-- Create index for connection_type for filtering remote clusters
CREATE INDEX IF NOT EXISTS idx_clusters_connection_type ON clusters(connection_type);

-- Update existing remote clusters to have proper connection_type
-- Note: Uses token_encrypted (new column name from deployment migrations)
UPDATE clusters
SET connection_type = CASE
    WHEN token_encrypted IS NOT NULL THEN 'token'
    WHEN kubeconfig_encrypted IS NOT NULL THEN 'kubeconfig'
    ELSE 'in-cluster'
END
WHERE connection_type IS NULL OR connection_type = '';

