-- Migration: Add API Keys table for CI/CD pipeline authentication
-- Date: 2026-01-29
-- Description: Creates api_keys table for storing API keys used by pipelines

-- Create the api_keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_id VARCHAR(50) UNIQUE NOT NULL,           -- Public identifier (key_xxx)
    key_hash VARCHAR(255) NOT NULL,                -- Hashed API key (never store plain!)
    key_prefix VARCHAR(12) NOT NULL,               -- First 8 chars for identification (fk_xxxxxxxx)
    name VARCHAR(255) NOT NULL,                    -- Human-readable name
    description TEXT,
    user_id INTEGER NOT NULL REFERENCES users(id), -- Who created this key
    
    -- Permissions & Scope
    scopes TEXT[] DEFAULT ARRAY['blast-radius'],   -- Allowed API scopes
    cluster_ids INTEGER[],                         -- NULL = all clusters, or specific IDs
    
    -- Expiration & Status
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP,                          -- NULL = never expires
    last_used_at TIMESTAMP,
    last_used_ip VARCHAR(45),
    usage_count INTEGER DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP,
    revoked_by INTEGER REFERENCES users(id),
    revoke_reason TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_key_id ON api_keys(key_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_expires ON api_keys(expires_at) WHERE expires_at IS NOT NULL;

-- Add API key permissions to permissions table
INSERT INTO permissions (resource, action, description) 
VALUES 
    ('api_keys', 'view', 'View API keys'),
    ('api_keys', 'create', 'Create new API keys'),
    ('api_keys', 'revoke', 'Revoke API keys')
ON CONFLICT (resource, action) DO NOTHING;

-- Grant API key permissions to Super Admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'Super Admin' 
AND p.resource = 'api_keys'
ON CONFLICT DO NOTHING;

-- Add comment
COMMENT ON TABLE api_keys IS 'API Keys for CI/CD pipeline authentication. Keys are hashed with SHA256.';
