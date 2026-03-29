-- Migration: Add Enhanced Cluster Management
-- Version: 004
-- Description: Add comprehensive cluster management with Inspector Gadget validation
-- Date: 2024-01-20

BEGIN;

-- Drop existing clusters table if exists (for clean migration)
DROP TABLE IF EXISTS cluster_statistics CASCADE;
DROP TABLE IF EXISTS clusters CASCADE;

-- Create clusters table with enhanced fields
CREATE TABLE clusters (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    
    -- Classification
    environment VARCHAR(50) NOT NULL, -- production, staging, development, testing
    provider VARCHAR(50) NOT NULL,    -- kubernetes, openshift, eks, aks, gke, on-premise
    region VARCHAR(100),
    tags JSONB DEFAULT '{}',
    
    -- Connection
    connection_type VARCHAR(50) NOT NULL, -- in-cluster, kubeconfig, service-account
    api_server_url VARCHAR(500) NOT NULL,
    kubeconfig_encrypted TEXT,    -- Encrypted with Fernet/AES
    ca_cert_encrypted TEXT,
    token_encrypted TEXT,
    skip_tls_verify BOOLEAN DEFAULT FALSE,
    
    -- Inspector Gadget (REQUIRED)
    gadget_endpoint VARCHAR(500) NOT NULL,
    gadget_auto_detect BOOLEAN DEFAULT TRUE,
    gadget_version VARCHAR(50),
    gadget_capabilities JSONB DEFAULT '[]',
    gadget_health_status VARCHAR(50) DEFAULT 'unknown', -- healthy, degraded, unavailable, unknown
    gadget_last_check TIMESTAMP WITH TIME ZONE,
    
    -- Validation & Status
    status VARCHAR(50) DEFAULT 'inactive', -- active, inactive, error, validating
    validation_status JSONB,
    last_sync TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Statistics (cached for performance)
    total_namespaces INTEGER DEFAULT 0,
    total_pods INTEGER DEFAULT 0,
    total_nodes INTEGER DEFAULT 0,
    k8s_version VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    
    -- Constraints
    CONSTRAINT chk_environment CHECK (environment IN ('production', 'staging', 'development', 'testing')),
    CONSTRAINT chk_connection_type CHECK (connection_type IN ('in-cluster', 'kubeconfig', 'service-account')),
    CONSTRAINT chk_gadget_health CHECK (gadget_health_status IN ('healthy', 'degraded', 'unavailable', 'unknown')),
    CONSTRAINT chk_status CHECK (status IN ('active', 'inactive', 'error', 'validating'))
);

-- Indexes for performance
CREATE INDEX idx_clusters_environment ON clusters(environment);
CREATE INDEX idx_clusters_status ON clusters(status);
CREATE INDEX idx_clusters_provider ON clusters(provider);
CREATE INDEX idx_clusters_gadget_health ON clusters(gadget_health_status);
CREATE INDEX idx_clusters_created_at ON clusters(created_at DESC);
CREATE INDEX idx_clusters_updated_at ON clusters(updated_at DESC);
CREATE INDEX idx_clusters_tags ON clusters USING GIN(tags);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_clusters_updated_at
    BEFORE UPDATE ON clusters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample localcluster for testing
INSERT INTO clusters (
    name,
    description,
    environment,
    provider,
    region,
    tags,
    connection_type,
    api_server_url,
    gadget_endpoint,
    gadget_auto_detect,
    status
) VALUES (
    'localcluster',
    'Local Kubernetes cluster for Flowfish development and testing',
    'development',
    'kubernetes',
    'local',
    '{"team": "engineering", "purpose": "testing"}',
    'in-cluster',
    'https://kubernetes.default.svc',
    'inspektor-gadget.flowfish.svc.cluster.local:16060',
    false,
    'active'
) ON CONFLICT (name) DO NOTHING;

COMMIT;

-- Rollback script (for reference)
-- BEGIN;
-- DROP TRIGGER IF EXISTS update_clusters_updated_at ON clusters;
-- DROP FUNCTION IF EXISTS update_updated_at_column();
-- DROP TABLE IF EXISTS clusters CASCADE;
-- COMMIT;

