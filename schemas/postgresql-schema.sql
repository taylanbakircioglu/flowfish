-- ============================================================================
-- Flowfish - PostgreSQL Database Schema
-- ============================================================================
-- Version: 1.0.0
-- Date: January 2025
-- Description: Complete database schema for Flowfish platform
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- For composite indexes

-- ============================================================================
-- SCHEMA CREATION
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS flowfish;
SET search_path TO flowfish, public;

-- ============================================================================
-- TABLE: users
-- Description: User accounts for platform access
-- ============================================================================

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),  -- NULL for OAuth-only users
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    avatar_url TEXT,
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    is_active BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_is_active ON users(is_active);

-- ============================================================================
-- TABLE: roles
-- Description: RBAC roles definition
-- ============================================================================

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_system_role BOOLEAN DEFAULT FALSE,  -- System roles cannot be deleted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default system roles
INSERT INTO roles (name, description, is_system_role) VALUES
('Super Admin', 'Full system access with all permissions', TRUE),
('Platform Admin', 'Platform management without user administration', TRUE),
('Security Analyst', 'Security analysis and anomaly detection', TRUE),
('Developer', 'Read-only access to dashboards and maps', TRUE);

-- ============================================================================
-- TABLE: permissions
-- Description: Granular permissions
-- ============================================================================

CREATE TABLE permissions (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,  -- e.g., 'clusters', 'analyses'
    action VARCHAR(50) NOT NULL,     -- e.g., 'view', 'create', 'edit', 'delete'
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(resource, action)
);

CREATE INDEX idx_permissions_resource ON permissions(resource);

-- Insert default permissions
INSERT INTO permissions (resource, action, description) VALUES
('clusters', 'view', 'View cluster information'),
('clusters', 'create', 'Create new clusters'),
('clusters', 'edit', 'Edit cluster configuration'),
('clusters', 'delete', 'Delete clusters'),
('namespaces', 'view', 'View namespace information'),
('analyses', 'view', 'View analysis configurations'),
('analyses', 'create', 'Create new analyses'),
('analyses', 'edit', 'Edit analysis configurations'),
('analyses', 'delete', 'Delete analyses'),
('analyses', 'execute', 'Start/stop analyses'),
('dependencies', 'view', 'View dependency maps'),
('dependencies', 'export', 'Export dependency data'),
('anomalies', 'view', 'View anomalies'),
('anomalies', 'manage', 'Manage anomaly status and comments'),
('changes', 'view', 'View change events'),
('changes', 'manage', 'Manage change event status'),
('users', 'view', 'View user accounts'),
('users', 'create', 'Create new users'),
('users', 'edit', 'Edit user accounts'),
('users', 'delete', 'Delete user accounts'),
('roles', 'view', 'View roles'),
('roles', 'create', 'Create custom roles'),
('roles', 'edit', 'Edit roles'),
('roles', 'delete', 'Delete custom roles'),
('settings', 'view', 'View system settings'),
('settings', 'edit', 'Edit system settings'),
('audit', 'view', 'View audit logs');

-- ============================================================================
-- TABLE: role_permissions
-- Description: Role to permission mapping
-- ============================================================================

CREATE TABLE role_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_id, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_id);

-- ============================================================================
-- TABLE: user_roles
-- Description: User to role mapping
-- ============================================================================

CREATE TABLE user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    UNIQUE(user_id, role_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);

-- ============================================================================
-- TABLE: oauth_providers
-- Description: OAuth provider configuration
-- ============================================================================

CREATE TABLE oauth_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- e.g., 'google', 'azure', 'okta'
    display_name VARCHAR(100) NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    authorization_url TEXT NOT NULL,
    token_url TEXT NOT NULL,
    user_info_url TEXT,
    scope VARCHAR(500) DEFAULT 'openid profile email',
    is_enabled BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TABLE: user_oauth_connections
-- Description: User OAuth connections
-- ============================================================================

CREATE TABLE user_oauth_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES oauth_providers(id) ON DELETE CASCADE,
    provider_user_id VARCHAR(255) NOT NULL,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_id, provider_user_id)
);

CREATE INDEX idx_user_oauth_user ON user_oauth_connections(user_id);

-- ============================================================================
-- TABLE: clusters
-- Description: Kubernetes/OpenShift clusters
-- ============================================================================

CREATE TABLE clusters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    cluster_type VARCHAR(50) NOT NULL,  -- 'kubernetes', 'openshift'
    api_url TEXT NOT NULL,
    kubeconfig_encrypted TEXT,  -- Encrypted kubeconfig
    token_encrypted TEXT,  -- Encrypted SA token (renamed from service_account_token_encrypted)
    ca_cert_encrypted TEXT,  -- Encrypted CA certificate for remote clusters
    skip_tls_verify BOOLEAN DEFAULT FALSE,  -- Skip TLS verification for remote clusters
    connection_type VARCHAR(50) DEFAULT 'in-cluster',  -- 'in-cluster', 'kubeconfig', 'token'
    
    -- Inspector Gadget configuration
    gadget_endpoint TEXT,  -- Inspector Gadget gRPC endpoint (e.g., host:16060)
    gadget_namespace VARCHAR(255) NOT NULL,  -- Namespace where IG is installed (REQUIRED from UI)
    gadget_health_status VARCHAR(50) DEFAULT 'unknown',  -- 'healthy', 'degraded', 'unhealthy', 'unknown'
    gadget_version VARCHAR(50),  -- Detected IG version
    
    -- Note: is_in_cluster removed; use connection_type instead
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    kubernetes_version VARCHAR(50),
    node_count INTEGER,
    pod_count INTEGER,
    namespace_count INTEGER,
    last_sync_at TIMESTAMP,
    health_status VARCHAR(50) DEFAULT 'unknown',  -- 'healthy', 'degraded', 'unhealthy', 'unknown'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_clusters_name ON clusters(name);
CREATE INDEX idx_clusters_is_active ON clusters(is_active);
CREATE INDEX idx_clusters_is_default ON clusters(is_default);
CREATE INDEX idx_clusters_connection_type ON clusters(connection_type);

-- ============================================================================
-- TABLE: namespaces
-- Description: Kubernetes namespaces
-- ============================================================================

CREATE TABLE namespaces (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}'::jsonb,
    annotations JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, name)
);

CREATE INDEX idx_namespaces_cluster ON namespaces(cluster_id);
CREATE INDEX idx_namespaces_name ON namespaces(name);
CREATE INDEX idx_namespaces_labels ON namespaces USING gin(labels);

-- ============================================================================
-- TABLE: workloads
-- Description: Kubernetes workloads (Pod, Deployment, StatefulSet, Service)
-- ============================================================================

CREATE TABLE workloads (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace_id INTEGER NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    workload_type VARCHAR(50) NOT NULL,  -- 'pod', 'deployment', 'statefulset', 'service'
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}'::jsonb,
    annotations JSONB DEFAULT '{}'::jsonb,
    owner_kind VARCHAR(100),  -- e.g., 'Deployment', 'StatefulSet'
    owner_name VARCHAR(255),
    owner_uid VARCHAR(255),
    ip_address INET,
    ports JSONB DEFAULT '[]'::jsonb,  -- [{port: 8080, protocol: 'TCP'}]
    replicas INTEGER,
    status VARCHAR(50),  -- 'Running', 'Pending', 'Failed', etc.
    containers JSONB DEFAULT '[]'::jsonb,  -- [{name, image, ...}]
    node_name VARCHAR(255),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(cluster_id, namespace_id, workload_type, name)
);

CREATE INDEX idx_workloads_cluster ON workloads(cluster_id);
CREATE INDEX idx_workloads_namespace ON workloads(namespace_id);
CREATE INDEX idx_workloads_type ON workloads(workload_type);
CREATE INDEX idx_workloads_name ON workloads(name);
CREATE INDEX idx_workloads_ip ON workloads(ip_address);
CREATE INDEX idx_workloads_labels ON workloads USING gin(labels);
CREATE INDEX idx_workloads_is_active ON workloads(is_active);
CREATE INDEX idx_workloads_last_seen ON workloads(last_seen);

-- ============================================================================
-- TABLE: communications
-- Description: Communication records between workloads
-- ============================================================================

CREATE TABLE communications (
    id BIGSERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    source_namespace_id INTEGER REFERENCES namespaces(id) ON DELETE CASCADE,
    source_workload_id INTEGER REFERENCES workloads(id) ON DELETE CASCADE,
    source_ip INET,
    source_port INTEGER,
    destination_namespace_id INTEGER REFERENCES namespaces(id) ON DELETE CASCADE,
    destination_workload_id INTEGER REFERENCES workloads(id) ON DELETE CASCADE,
    destination_ip INET NOT NULL,
    destination_port INTEGER NOT NULL,
    protocol VARCHAR(50) NOT NULL,  -- 'TCP', 'UDP', 'HTTP', 'HTTPS', 'gRPC'
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_count BIGINT DEFAULT 0,
    request_rate_per_second DECIMAL(10,2),
    bytes_transferred BIGINT DEFAULT 0,
    avg_latency_ms DECIMAL(10,2),
    p50_latency_ms DECIMAL(10,2),
    p95_latency_ms DECIMAL(10,2),
    p99_latency_ms DECIMAL(10,2),
    error_count BIGINT DEFAULT 0,
    error_rate DECIMAL(5,2),
    risk_score INTEGER DEFAULT 0,  -- 0-100
    risk_level VARCHAR(20) DEFAULT 'low',  -- 'low', 'medium', 'high', 'critical'
    importance_score INTEGER DEFAULT 0,
    is_cross_namespace BOOLEAN DEFAULT FALSE,
    is_external BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(cluster_id, source_workload_id, destination_workload_id, destination_port, protocol)
);

CREATE INDEX idx_communications_cluster ON communications(cluster_id);
CREATE INDEX idx_communications_source_workload ON communications(source_workload_id);
CREATE INDEX idx_communications_destination_workload ON communications(destination_workload_id);
CREATE INDEX idx_communications_destination_ip_port ON communications(destination_ip, destination_port);
CREATE INDEX idx_communications_protocol ON communications(protocol);
CREATE INDEX idx_communications_risk_level ON communications(risk_level);
CREATE INDEX idx_communications_is_active ON communications(is_active);
CREATE INDEX idx_communications_last_seen ON communications(last_seen);

-- ============================================================================
-- TABLE: analyses
-- Description: Analysis configuration (from wizard)
-- ============================================================================

CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,  -- Primary cluster
    cluster_ids JSONB DEFAULT '[]'::jsonb,  -- All cluster IDs for multi-cluster analysis
    is_multi_cluster BOOLEAN DEFAULT FALSE,  -- Flag for multi-cluster analysis
    scope_type VARCHAR(50) NOT NULL,  -- 'cluster', 'namespace', 'deployment', 'pod', 'label'
    scope_config JSONB NOT NULL,  -- Scope details (includes per_cluster_scope for multi-cluster)
    gadget_config JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Gadget module configuration
    gadget_modules JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Enabled gadgets (legacy)
    time_config JSONB NOT NULL,  -- Time settings
    output_config JSONB NOT NULL,  -- Dashboard, LLM, alerts
    status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'running', 'stopped', 'completed', 'failed'
    is_active BOOLEAN DEFAULT TRUE,
    change_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,  -- Enable/disable change tracking for this analysis
    change_detection_strategy VARCHAR(50) DEFAULT 'baseline',  -- Detection strategy: 'baseline', 'rolling_window', 'run_comparison'
    change_detection_types JSONB DEFAULT '["all"]'::jsonb,  -- Change types to track: ['all'] or specific types like ['replica_changed', 'connection_added']
    started_at TIMESTAMP,  -- When analysis started running
    stopped_at TIMESTAMP,  -- When analysis stopped
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_analyses_cluster ON analyses(cluster_id);
CREATE INDEX idx_analyses_status ON analyses(status);
CREATE INDEX idx_analyses_created_by ON analyses(created_by);
CREATE INDEX idx_analyses_is_multi_cluster ON analyses(is_multi_cluster);
CREATE INDEX idx_analyses_cluster_ids ON analyses USING GIN(cluster_ids);

COMMENT ON COLUMN analyses.cluster_ids IS 'JSON array of cluster IDs for multi-cluster analysis';
COMMENT ON COLUMN analyses.is_multi_cluster IS 'Flag indicating multi-cluster analysis';
COMMENT ON COLUMN analyses.change_detection_strategy IS 'Detection strategy: baseline (default), rolling_window, or run_comparison';
COMMENT ON COLUMN analyses.change_detection_types IS 'JSON array of change types to track: ["all"] or specific types';

-- ============================================================================
-- TABLE: analysis_runs
-- Description: Analysis execution history
-- ============================================================================

CREATE TABLE analysis_runs (
    id BIGSERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'running',  -- 'running', 'completed', 'failed', 'cancelled'
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds INTEGER,
    events_collected BIGINT DEFAULT 0,
    workloads_discovered INTEGER DEFAULT 0,
    communications_discovered INTEGER DEFAULT 0,
    anomalies_detected INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    error_message TEXT,
    logs JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_analysis_runs_analysis ON analysis_runs(analysis_id);
CREATE INDEX idx_analysis_runs_status ON analysis_runs(status);
CREATE INDEX idx_analysis_runs_start_time ON analysis_runs(start_time);

-- ============================================================================
-- TABLE: baselines
-- Description: Traffic baseline profiles
-- ============================================================================

CREATE TABLE baselines (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace_id INTEGER REFERENCES namespaces(id) ON DELETE SET NULL,
    workload_id INTEGER REFERENCES workloads(id) ON DELETE SET NULL,
    learning_period_days INTEGER NOT NULL,
    learning_start_date TIMESTAMP NOT NULL,
    learning_end_date TIMESTAMP NOT NULL,
    profile_data JSONB NOT NULL,  -- Baseline communication patterns
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX idx_baselines_cluster ON baselines(cluster_id);
CREATE INDEX idx_baselines_namespace ON baselines(namespace_id);
CREATE INDEX idx_baselines_workload ON baselines(workload_id);
CREATE INDEX idx_baselines_is_active ON baselines(is_active);

-- ============================================================================
-- TABLE: anomalies
-- Description: Detected anomalies
-- ============================================================================

CREATE TABLE anomalies (
    id BIGSERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    analysis_run_id BIGINT REFERENCES analysis_runs(id) ON DELETE SET NULL,
    anomaly_type VARCHAR(100) NOT NULL,  -- 'network', 'behavioral', 'security'
    severity VARCHAR(20) NOT NULL,  -- 'low', 'medium', 'high', 'critical'
    anomaly_score INTEGER NOT NULL,  -- 0-100
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    affected_workloads JSONB DEFAULT '[]'::jsonb,
    communication_id BIGINT REFERENCES communications(id) ON DELETE SET NULL,
    baseline_id INTEGER REFERENCES baselines(id) ON DELETE SET NULL,
    llm_analysis JSONB,  -- LLM response data
    recommended_action TEXT,
    confidence_level INTEGER,  -- 0-100
    status VARCHAR(50) DEFAULT 'new',  -- 'new', 'investigating', 'resolved', 'false_positive'
    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    comments TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_anomalies_cluster ON anomalies(cluster_id);
CREATE INDEX idx_anomalies_severity ON anomalies(severity);
CREATE INDEX idx_anomalies_status ON anomalies(status);
CREATE INDEX idx_anomalies_detected_at ON anomalies(detected_at);
CREATE INDEX idx_anomalies_assigned_to ON anomalies(assigned_to);

-- ============================================================================
-- NOTE: change_events table REMOVED from PostgreSQL
-- Change events are now stored in ClickHouse only (schemas/clickhouse-change-events.sql)
-- This follows the project architecture: PostgreSQL for metadata, ClickHouse for events
-- ============================================================================

-- ============================================================================
-- TABLE: risk_scores
-- Description: Risk scoring metadata and configuration
-- ============================================================================

CREATE TABLE risk_scores (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    factor_name VARCHAR(100) NOT NULL,
    weight DECIMAL(5,2) NOT NULL,  -- Percentage weight
    calculation_rule JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default risk factors
INSERT INTO risk_scores (name, description, factor_name, weight, calculation_rule) VALUES
('External Communication', 'Internet egress traffic', 'external_egress', 40.00, '{"condition": "is_external=true", "score": 40}'::jsonb),
('Cross-Namespace', 'Cross-namespace communication', 'cross_namespace', 20.00, '{"condition": "is_cross_namespace=true", "score": 20}'::jsonb),
('Privileged Ports', 'Ports below 1024', 'privileged_ports', 15.00, '{"condition": "port<1024", "score": 15}'::jsonb),
('Unencrypted Protocol', 'HTTP, FTP, etc.', 'unencrypted_protocol', 10.00, '{"condition": "protocol IN (HTTP, FTP)", "score": 10}'::jsonb),
('High Frequency', 'Very high request rate', 'high_frequency', 10.00, '{"condition": "request_rate > 1000", "score": 10}'::jsonb),
('Security Context', 'Privileged pods', 'security_context', 5.00, '{"condition": "privileged=true", "score": 5}'::jsonb);

-- ============================================================================
-- TABLE: llm_configs
-- Description: LLM provider configuration
-- ============================================================================

CREATE TABLE llm_configs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    provider VARCHAR(100) NOT NULL,  -- 'openai', 'azure', 'anthropic', 'custom'
    api_url TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    model VARCHAR(100) NOT NULL,  -- 'gpt-4', 'claude-3-sonnet', etc.
    temperature DECIMAL(3,2) DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2000,
    timeout_seconds INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- TABLE: webhooks
-- Description: Webhook configuration
-- ============================================================================

CREATE TABLE webhooks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    secret_key_encrypted TEXT,
    event_types JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ['anomaly_detected', 'change_detected']
    headers JSONB DEFAULT '{}'::jsonb,
    timeout_seconds INTEGER DEFAULT 10,
    retry_count INTEGER DEFAULT 3,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX idx_webhooks_is_active ON webhooks(is_active);

-- ============================================================================
-- TABLE: webhook_deliveries
-- Description: Webhook delivery log
-- ============================================================================

CREATE TABLE webhook_deliveries (
    id BIGSERIAL PRIMARY KEY,
    webhook_id INTEGER NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    http_status INTEGER,
    response_body TEXT,
    error_message TEXT,
    attempt_number INTEGER DEFAULT 1,
    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER
);

CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_event_type ON webhook_deliveries(event_type);
CREATE INDEX idx_webhook_deliveries_delivered_at ON webhook_deliveries(delivered_at);

-- ============================================================================
-- TABLE: import_jobs
-- Description: Import job tracking
-- ============================================================================

CREATE TABLE import_jobs (
    id BIGSERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    file_name VARCHAR(500) NOT NULL,
    file_format VARCHAR(50) NOT NULL,  -- 'csv', 'graph_json'
    file_size_bytes BIGINT,
    import_mode VARCHAR(50) NOT NULL,  -- 'merge', 'overwrite', 'snapshot'
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    total_records INTEGER,
    processed_records INTEGER DEFAULT 0,
    successful_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_import_jobs_cluster ON import_jobs(cluster_id);
CREATE INDEX idx_import_jobs_status ON import_jobs(status);
CREATE INDEX idx_import_jobs_created_at ON import_jobs(created_at);

-- ============================================================================
-- TABLE: export_jobs
-- Description: Export job tracking
-- ============================================================================

CREATE TABLE export_jobs (
    id BIGSERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    export_format VARCHAR(50) NOT NULL,  -- 'csv', 'graph_json'
    scope_config JSONB NOT NULL,
    file_name VARCHAR(500),
    file_size_bytes BIGINT,
    file_path TEXT,
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    total_records INTEGER,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_export_jobs_cluster ON export_jobs(cluster_id);
CREATE INDEX idx_export_jobs_status ON export_jobs(status);
CREATE INDEX idx_export_jobs_created_at ON export_jobs(created_at);

-- ============================================================================
-- TABLE: graph_snapshots
-- Description: Graph snapshot versioning
-- ============================================================================

CREATE TABLE graph_snapshots (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    snapshot_name VARCHAR(255) NOT NULL,
    description TEXT,
    snapshot_type VARCHAR(50) DEFAULT 'manual',  -- 'manual', 'auto_daily', 'auto_weekly', 'import'
    version VARCHAR(50),
    tags JSONB DEFAULT '[]'::jsonb,
    node_count INTEGER,
    edge_count INTEGER,
    storage_path TEXT,
    storage_size_bytes BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_graph_snapshots_cluster ON graph_snapshots(cluster_id);
CREATE INDEX idx_graph_snapshots_created_at ON graph_snapshots(created_at);

-- ============================================================================
-- TABLE: audit_logs
-- Description: Comprehensive audit trail
-- ============================================================================

CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,  -- 'login', 'logout', 'create_cluster', etc.
    resource_type VARCHAR(100),  -- 'cluster', 'analysis', 'user', etc.
    resource_id VARCHAR(100),
    http_method VARCHAR(10),
    endpoint VARCHAR(500),
    ip_address INET,
    user_agent TEXT,
    request_body JSONB,
    response_status INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- ============================================================================
-- TABLE: system_settings
-- Description: System-wide configuration
-- ============================================================================

CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES users(id),
    UNIQUE(category, key)
);

CREATE INDEX idx_system_settings_category ON system_settings(category);

-- Insert default settings
INSERT INTO system_settings (category, key, value, description) VALUES
('general', 'platform_name', '"Flowfish"'::jsonb, 'Platform display name'),
('general', 'default_timezone', '"UTC"'::jsonb, 'Default timezone'),
('general', 'session_timeout_minutes', '60'::jsonb, 'Session timeout in minutes'),
('analysis', 'max_concurrent_analyses', '10'::jsonb, 'Max concurrent analyses'),
('analysis', 'default_collection_interval_seconds', '5'::jsonb, 'Default data collection interval'),
('export', 'max_export_records', '1000000'::jsonb, 'Max records per export'),
('llm', 'default_analysis_interval_minutes', '15'::jsonb, 'Default LLM analysis interval'),
('retention', 'communications_retention_days', '90'::jsonb, 'Communication data retention'),
('retention', 'anomalies_retention_days', '180'::jsonb, 'Anomaly data retention'),
('retention', 'audit_logs_retention_days', '365'::jsonb, 'Audit log retention');

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_roles_updated_at BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_clusters_updated_at BEFORE UPDATE ON clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_namespaces_updated_at BEFORE UPDATE ON namespaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workloads_updated_at BEFORE UPDATE ON workloads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_communications_updated_at BEFORE UPDATE ON communications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_analyses_updated_at BEFORE UPDATE ON analyses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_baselines_updated_at BEFORE UPDATE ON baselines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Active communications with workload details
CREATE OR REPLACE VIEW v_active_communications AS
SELECT 
    c.id,
    c.cluster_id,
    cl.name AS cluster_name,
    src_ns.name AS source_namespace,
    src_wl.name AS source_workload,
    src_wl.workload_type AS source_type,
    dst_ns.name AS destination_namespace,
    dst_wl.name AS destination_workload,
    dst_wl.workload_type AS destination_type,
    c.destination_ip,
    c.destination_port,
    c.protocol,
    c.request_count,
    c.request_rate_per_second,
    c.avg_latency_ms,
    c.risk_level,
    c.risk_score,
    c.is_cross_namespace,
    c.is_external,
    c.first_seen,
    c.last_seen
FROM communications c
JOIN clusters cl ON c.cluster_id = cl.id
LEFT JOIN namespaces src_ns ON c.source_namespace_id = src_ns.id
LEFT JOIN workloads src_wl ON c.source_workload_id = src_wl.id
LEFT JOIN namespaces dst_ns ON c.destination_namespace_id = dst_ns.id
LEFT JOIN workloads dst_wl ON c.destination_workload_id = dst_wl.id
WHERE c.is_active = TRUE;

-- View: User permissions (flattened)
CREATE OR REPLACE VIEW v_user_permissions AS
SELECT 
    u.id AS user_id,
    u.username,
    r.name AS role_name,
    p.resource,
    p.action
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE u.is_active = TRUE;

-- View: Cluster overview
CREATE OR REPLACE VIEW v_cluster_overview AS
SELECT 
    c.id AS cluster_id,
    c.name AS cluster_name,
    c.cluster_type,
    c.health_status,
    COUNT(DISTINCT n.id) AS namespace_count,
    COUNT(DISTINCT w.id) AS workload_count,
    COUNT(DISTINCT CASE WHEN w.workload_type = 'pod' THEN w.id END) AS pod_count,
    COUNT(DISTINCT comm.id) AS communication_count,
    COUNT(DISTINCT a.id) AS active_anomaly_count,
    c.last_sync_at
FROM clusters c
LEFT JOIN namespaces n ON c.id = n.cluster_id
LEFT JOIN workloads w ON c.id = w.cluster_id AND w.is_active = TRUE
LEFT JOIN communications comm ON c.id = comm.cluster_id AND comm.is_active = TRUE
LEFT JOIN anomalies a ON c.id = a.cluster_id AND a.status IN ('new', 'investigating')
WHERE c.is_active = TRUE
GROUP BY c.id;

-- ============================================================================
-- TABLE: blast_radius_assessments
-- Description: History of blast radius assessments from CI/CD pipelines
-- ============================================================================

CREATE TABLE blast_radius_assessments (
    id SERIAL PRIMARY KEY,
    assessment_id VARCHAR(50) UNIQUE NOT NULL,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id),
    analysis_id INTEGER REFERENCES analyses(id),
    target VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL DEFAULT 'default',
    change_type VARCHAR(50) NOT NULL,
    risk_score INTEGER NOT NULL CHECK (risk_score >= 0 AND risk_score <= 100),
    risk_level VARCHAR(20) NOT NULL,
    affected_count INTEGER NOT NULL DEFAULT 0,
    triggered_by VARCHAR(255),
    pipeline VARCHAR(255),
    response_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_blast_radius_cluster ON blast_radius_assessments(cluster_id);
CREATE INDEX idx_blast_radius_created ON blast_radius_assessments(created_at DESC);
CREATE INDEX idx_blast_radius_target ON blast_radius_assessments(target);
CREATE INDEX idx_blast_radius_risk ON blast_radius_assessments(risk_level);

-- ============================================================================
-- TABLE: api_keys
-- Description: API Keys for CI/CD pipeline and external system authentication
-- ============================================================================

CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    key_id VARCHAR(50) UNIQUE NOT NULL,           -- Public identifier (fk_xxx)
    key_hash VARCHAR(255) NOT NULL,                -- Hashed API key (never store plain!)
    key_prefix VARCHAR(10) NOT NULL,               -- First 8 chars for identification
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

CREATE INDEX idx_api_keys_key_id ON api_keys(key_id);
CREATE INDEX idx_api_keys_key_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);
CREATE INDEX idx_api_keys_expires ON api_keys(expires_at) WHERE expires_at IS NOT NULL;

-- Add API key permissions
INSERT INTO permissions (resource, action, description) VALUES
('api_keys', 'view', 'View API keys'),
('api_keys', 'create', 'Create new API keys'),
('api_keys', 'revoke', 'Revoke API keys');

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create default admin user (password: admin123 - should be changed!)
-- Password hash for 'admin123' using bcrypt
INSERT INTO users (username, email, password_hash, first_name, last_name, is_active, email_verified)
VALUES ('admin', 'admin@flowfish.local', '$2b$12$t.gxj5CSj1Bcrf7VyZEQqO0PNUJnwKvwiY5W1xQ0hFMDrjpVYN3.u', 'System', 'Administrator', TRUE, TRUE);

-- Assign Super Admin role to admin user
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'Super Admin';

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON DATABASE flowfish IS 'Flowfish Platform - eBPF-based Kubernetes Application Communication and Dependency Mapping';
COMMENT ON TABLE users IS 'User accounts for platform access with OAuth support';
COMMENT ON TABLE roles IS 'RBAC roles including Super Admin, Platform Admin, Security Analyst, Developer';
COMMENT ON TABLE permissions IS 'Granular permissions for resource access control';
COMMENT ON TABLE clusters IS 'Kubernetes/OpenShift clusters managed by Flowfish';
COMMENT ON TABLE workloads IS 'Kubernetes workloads (Pod, Deployment, StatefulSet, Service) discovered via eBPF';
COMMENT ON TABLE communications IS 'Network communications between workloads tracked in real-time';
COMMENT ON TABLE analyses IS 'Analysis configurations created via wizard';
COMMENT ON TABLE anomalies IS 'Anomalies detected via LLM analysis';
COMMENT ON TABLE baselines IS 'Traffic baseline profiles for anomaly detection';
COMMENT ON TABLE audit_logs IS 'Comprehensive audit trail of all system activities';

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

