-- ============================================================================
-- Flowfish - PostgreSQL Database Schema
-- ============================================================================
-- Description: Complete database schema for Flowfish platform
-- Aligned with: local-test/03-migrations.yaml (Kubernetes migration)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ============================================================================
-- TABLE: schema_migrations
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TABLE: clusters
-- ============================================================================

CREATE TABLE IF NOT EXISTS clusters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    environment VARCHAR(50) NOT NULL DEFAULT 'production',
    provider VARCHAR(50) NOT NULL DEFAULT 'openshift',
    region VARCHAR(100),
    tags JSONB DEFAULT '{}',
    connection_type VARCHAR(50) NOT NULL DEFAULT 'in-cluster',
    api_server_url VARCHAR(500) NOT NULL DEFAULT 'https://kubernetes.default.svc',
    kubeconfig_encrypted TEXT,
    ca_cert_encrypted TEXT,
    token_encrypted TEXT,
    skip_tls_verify BOOLEAN DEFAULT FALSE,
    gadget_endpoint VARCHAR(500),
    gadget_namespace VARCHAR(255) NOT NULL DEFAULT 'gadget',
    gadget_protocol VARCHAR(50) DEFAULT 'kubectl',
    gadget_auto_detect BOOLEAN DEFAULT TRUE,
    gadget_version VARCHAR(50),
    gadget_capabilities JSONB DEFAULT '[]',
    gadget_health_status VARCHAR(50) DEFAULT 'unknown',
    gadget_last_check TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'active',
    validation_status JSONB,
    last_sync TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    total_namespaces INTEGER DEFAULT 0,
    total_pods INTEGER DEFAULT 0,
    total_nodes INTEGER DEFAULT 0,
    k8s_version VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    updated_by INTEGER
);
CREATE INDEX IF NOT EXISTS idx_clusters_environment ON clusters(environment);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON clusters(status);
CREATE INDEX IF NOT EXISTS idx_clusters_name ON clusters(name);

-- ============================================================================
-- TABLE: analysis_event_types
-- ============================================================================

CREATE TABLE IF NOT EXISTS analysis_event_types (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL,
    event_type_id VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    sampling_rate INTEGER DEFAULT 100,
    filters JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(analysis_id, event_type_id)
);
CREATE INDEX IF NOT EXISTS idx_analysis_event_types_analysis_id ON analysis_event_types(analysis_id);

-- ============================================================================
-- TABLE: namespaces
-- ============================================================================

CREATE TABLE IF NOT EXISTS namespaces (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}',
    annotations JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, name)
);
CREATE INDEX IF NOT EXISTS idx_namespaces_cluster ON namespaces(cluster_id);
CREATE INDEX IF NOT EXISTS idx_namespaces_name ON namespaces(name);
CREATE INDEX IF NOT EXISTS idx_namespaces_labels ON namespaces USING gin(labels);

-- ============================================================================
-- TABLE: workloads
-- ============================================================================

CREATE TABLE IF NOT EXISTS workloads (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace_id INTEGER NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    workload_type VARCHAR(50) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}',
    annotations JSONB DEFAULT '{}',
    replicas INTEGER,
    available_replicas INTEGER,
    image VARCHAR(500),
    status VARCHAR(50) DEFAULT 'Unknown',
    is_active BOOLEAN DEFAULT TRUE,
    owner_kind VARCHAR(100),
    owner_name VARCHAR(255),
    owner_uid VARCHAR(255),
    ip_address INET,
    ports JSONB DEFAULT '[]',
    containers JSONB DEFAULT '[]',
    node_name VARCHAR(255),
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, namespace_id, workload_type, name)
);
CREATE INDEX IF NOT EXISTS idx_workloads_cluster ON workloads(cluster_id);
CREATE INDEX IF NOT EXISTS idx_workloads_namespace ON workloads(namespace_id);
CREATE INDEX IF NOT EXISTS idx_workloads_type ON workloads(workload_type);
CREATE INDEX IF NOT EXISTS idx_workloads_labels ON workloads USING gin(labels);
CREATE INDEX IF NOT EXISTS idx_workloads_ip ON workloads(ip_address);
CREATE INDEX IF NOT EXISTS idx_workloads_is_active ON workloads(is_active);

-- ============================================================================
-- TABLE: communications
-- ============================================================================

CREATE TABLE IF NOT EXISTS communications (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    source_namespace_id INTEGER REFERENCES namespaces(id) ON DELETE SET NULL,
    source_workload_id INTEGER REFERENCES workloads(id) ON DELETE SET NULL,
    source_ip INET,
    source_port INTEGER,
    destination_namespace_id INTEGER REFERENCES namespaces(id) ON DELETE SET NULL,
    destination_workload_id INTEGER REFERENCES workloads(id) ON DELETE SET NULL,
    destination_ip INET NOT NULL,
    destination_port INTEGER NOT NULL,
    protocol VARCHAR(50) NOT NULL,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_count BIGINT DEFAULT 0,
    request_rate_per_second VARCHAR(10),
    bytes_transferred BIGINT DEFAULT 0,
    avg_latency_ms VARCHAR(10),
    p50_latency_ms VARCHAR(10),
    p95_latency_ms VARCHAR(10),
    p99_latency_ms VARCHAR(10),
    error_count BIGINT DEFAULT 0,
    error_rate VARCHAR(5),
    risk_score INTEGER DEFAULT 0,
    risk_level VARCHAR(20) DEFAULT 'low',
    importance_score INTEGER DEFAULT 0,
    is_cross_namespace BOOLEAN DEFAULT FALSE,
    is_external BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_communications_cluster ON communications(cluster_id);
CREATE INDEX IF NOT EXISTS idx_communications_source_workload ON communications(source_workload_id);
CREATE INDEX IF NOT EXISTS idx_communications_dest_workload ON communications(destination_workload_id);
CREATE INDEX IF NOT EXISTS idx_communications_dest_ip ON communications(destination_ip);
CREATE INDEX IF NOT EXISTS idx_communications_protocol ON communications(protocol);
CREATE INDEX IF NOT EXISTS idx_communications_risk_level ON communications(risk_level);
CREATE INDEX IF NOT EXISTS idx_communications_is_active ON communications(is_active);

-- ============================================================================
-- TABLE: analyses
-- ============================================================================

CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    cluster_ids JSONB DEFAULT '[]',
    is_multi_cluster BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'draft',
    scope_type VARCHAR(50) NOT NULL DEFAULT 'cluster',
    scope_config JSONB DEFAULT '{}',
    gadget_config JSONB DEFAULT '{}',
    gadget_modules JSONB DEFAULT '[]',
    time_config JSONB DEFAULT '{}',
    output_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    namespaces JSONB,
    change_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    change_detection_strategy VARCHAR(50) DEFAULT 'baseline',
    change_detection_types JSONB DEFAULT '["all"]'::jsonb,
    is_baseline BOOLEAN DEFAULT false,
    baseline_marked_at TIMESTAMP WITH TIME ZONE,
    baseline_marked_by VARCHAR(255),
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE,
    created_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_analyses_cluster ON analyses(cluster_id);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
CREATE INDEX IF NOT EXISTS idx_analyses_is_active ON analyses(is_active);
CREATE INDEX IF NOT EXISTS idx_analyses_is_multi_cluster ON analyses(is_multi_cluster);
CREATE INDEX IF NOT EXISTS idx_analyses_cluster_ids ON analyses USING GIN(cluster_ids);
CREATE INDEX IF NOT EXISTS idx_analyses_namespaces ON analyses USING GIN(namespaces);
CREATE INDEX IF NOT EXISTS idx_analyses_is_baseline ON analyses(is_baseline) WHERE is_baseline = true;
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at);

-- ============================================================================
-- TABLE: analysis_runs
-- ============================================================================

CREATE TABLE IF NOT EXISTS analysis_runs (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(50) DEFAULT 'running',
    start_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    events_collected BIGINT DEFAULT 0,
    workloads_discovered INTEGER DEFAULT 0,
    communications_discovered INTEGER DEFAULT 0,
    anomalies_detected INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    error_message TEXT,
    logs JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_analysis ON analysis_runs(analysis_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_start_time ON analysis_runs(start_time);

-- ============================================================================
-- TABLE: cluster_sync_status
-- ============================================================================

CREATE TABLE IF NOT EXISTS cluster_sync_status (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50) DEFAULT 'pending',
    namespaces_count INTEGER DEFAULT 0,
    deployments_count INTEGER DEFAULT 0,
    pods_count INTEGER DEFAULT 0,
    services_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id)
);
CREATE INDEX IF NOT EXISTS idx_cluster_sync_status_cluster ON cluster_sync_status(cluster_id);

-- ============================================================================
-- TABLE: cached_pods
-- ============================================================================

CREATE TABLE IF NOT EXISTS cached_pods (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    status VARCHAR(50),
    node_name VARCHAR(255),
    ip VARCHAR(50),
    labels JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, namespace, name)
);
CREATE INDEX IF NOT EXISTS idx_cached_pods_cluster ON cached_pods(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cached_pods_namespace ON cached_pods(namespace);
CREATE INDEX IF NOT EXISTS idx_cached_pods_labels ON cached_pods USING gin(labels);

-- ============================================================================
-- TABLE: cached_services
-- ============================================================================

CREATE TABLE IF NOT EXISTS cached_services (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    service_type VARCHAR(50),
    cluster_ip VARCHAR(50),
    ports JSONB DEFAULT '[]',
    selector JSONB DEFAULT '{}',
    labels JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, namespace, name)
);
CREATE INDEX IF NOT EXISTS idx_cached_services_cluster ON cached_services(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cached_services_namespace ON cached_services(namespace);

-- ============================================================================
-- TABLE: users
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    full_name VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    avatar_url TEXT,
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    last_login TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_login_ip VARCHAR(45),
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    created_by INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

INSERT INTO users (username, email, password_hash, full_name, first_name, role)
VALUES ('admin', 'admin@flowfish.local',
    '$2b$12$t.gxj5CSj1Bcrf7VyZEQqO0PNUJnwKvwiY5W1xQ0hFMDrjpVYN3.u',
    'System Administrator', 'Admin', 'admin')
ON CONFLICT (username) DO NOTHING;

-- ============================================================================
-- TABLE: roles
-- ============================================================================

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_system_role BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TABLE: permissions
-- ============================================================================

CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(resource, action)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id)
);

-- ============================================================================
-- TABLE: oauth_providers
-- ============================================================================

CREATE TABLE IF NOT EXISTS oauth_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    authorization_url TEXT NOT NULL,
    token_url TEXT NOT NULL,
    user_info_url TEXT,
    scope VARCHAR(500) DEFAULT 'openid profile email',
    is_enabled BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_oauth_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES oauth_providers(id) ON DELETE CASCADE,
    provider_user_id VARCHAR(255) NOT NULL,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions(permission_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_user_oauth_connections_user ON user_oauth_connections(user_id);

INSERT INTO roles (name, description, is_system_role) VALUES
    ('admin', 'Full system access', TRUE),
    ('viewer', 'Read-only access', TRUE),
    ('operator', 'Read and operate clusters', TRUE),
    ('analyst', 'Access to analysis features', TRUE)
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- TABLE: system_settings
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER
);
INSERT INTO system_settings (key, value, description) VALUES
('analysis_limits',
 '{"continuous_auto_stop_enabled": true, "default_continuous_duration_minutes": 10, "max_allowed_duration_minutes": 1440, "warning_before_minutes": 2}',
 'Global analysis time and size limits')
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- TABLE: notification_hooks
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_hooks (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    hook_type VARCHAR(50) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    is_enabled BOOLEAN DEFAULT true,
    trigger_on_critical BOOLEAN DEFAULT true,
    trigger_on_high BOOLEAN DEFAULT true,
    trigger_on_medium BOOLEAN DEFAULT false,
    trigger_on_low BOOLEAN DEFAULT false,
    trigger_change_types TEXT[],
    rate_limit_per_hour INTEGER DEFAULT 100,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_hook_type CHECK (hook_type IN ('slack', 'teams', 'email', 'webhook'))
);
CREATE INDEX IF NOT EXISTS idx_notification_hooks_enabled ON notification_hooks(cluster_id, is_enabled) WHERE is_enabled = true;
CREATE INDEX IF NOT EXISTS idx_notification_hooks_cluster ON notification_hooks(cluster_id);

-- ============================================================================
-- TABLE: scheduled_reports
-- ============================================================================

CREATE TABLE IF NOT EXISTS scheduled_reports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    format VARCHAR(20) NOT NULL DEFAULT 'csv',
    schedule VARCHAR(20) NOT NULL DEFAULT 'daily',
    filters JSONB DEFAULT '{}',
    recipients JSONB DEFAULT '[]',
    is_enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP WITH TIME ZONE,
    next_run TIMESTAMP WITH TIME ZONE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scheduled_reports_enabled ON scheduled_reports(is_enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_reports_next_run ON scheduled_reports(next_run);

-- ============================================================================
-- TABLE: generated_reports
-- ============================================================================

CREATE TABLE IF NOT EXISTS generated_reports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    format VARCHAR(20) NOT NULL DEFAULT 'csv',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    file_size BIGINT,
    file_path TEXT,
    filters JSONB DEFAULT '{}',
    error_message TEXT,
    scheduled_report_id INTEGER REFERENCES scheduled_reports(id) ON DELETE SET NULL,
    generated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    cluster_id INTEGER REFERENCES clusters(id) ON DELETE SET NULL,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE SET NULL,
    namespace VARCHAR(255),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generated_reports_status ON generated_reports(status);
CREATE INDEX IF NOT EXISTS idx_generated_reports_type ON generated_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_generated_reports_created ON generated_reports(created_at);

-- ============================================================================
-- TABLE: activity_logs
-- ============================================================================

CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    resource_name VARCHAR(255),
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    user_agent TEXT,
    status VARCHAR(20) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_action ON activity_logs(action);
CREATE INDEX IF NOT EXISTS idx_activity_logs_resource ON activity_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_username ON activity_logs(username);

-- ============================================================================
-- TABLE: two_factor_codes
-- ============================================================================

CREATE TABLE IF NOT EXISTS two_factor_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    code VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_two_factor_codes_expires_at ON two_factor_codes(expires_at);

-- ============================================================================
-- TABLE: blast_radius_assessments
-- ============================================================================

CREATE TABLE IF NOT EXISTS blast_radius_assessments (
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
    commit_sha VARCHAR(100),
    assessment_data JSONB DEFAULT '{}',
    recommendations JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blast_radius_cluster ON blast_radius_assessments(cluster_id);
CREATE INDEX IF NOT EXISTS idx_blast_radius_analysis ON blast_radius_assessments(analysis_id);
CREATE INDEX IF NOT EXISTS idx_blast_radius_created ON blast_radius_assessments(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blast_radius_risk ON blast_radius_assessments(risk_level);
CREATE INDEX IF NOT EXISTS idx_blast_radius_target ON blast_radius_assessments(target, namespace);

-- ============================================================================
-- TABLE: scheduled_simulations
-- ============================================================================

CREATE TABLE IF NOT EXISTS scheduled_simulations (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    cluster_id VARCHAR(50) NOT NULL,
    analysis_id VARCHAR(50),
    target_name VARCHAR(255) NOT NULL,
    target_namespace VARCHAR(255) NOT NULL,
    target_kind VARCHAR(50) DEFAULT 'Deployment',
    change_type VARCHAR(50) NOT NULL,
    schedule_type VARCHAR(20) DEFAULT 'once',
    scheduled_time TIMESTAMP NOT NULL,
    notify_before_minutes INT DEFAULT 15,
    auto_rollback BOOLEAN DEFAULT FALSE,
    rollback_on_failure BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'scheduled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    last_run_at TIMESTAMP,
    last_run_result TEXT
);

-- ============================================================================
-- SEED DATA: permissions, role_permissions, user_roles
-- ============================================================================

INSERT INTO permissions (resource, action, description) VALUES
    ('dashboard', 'view', 'View dashboard'),
    ('dashboard', 'stats', 'View statistics'),
    ('analysis', 'view', 'View analyses'),
    ('analysis', 'create', 'Create analysis'),
    ('analysis', 'start', 'Start/stop analysis'),
    ('analysis', 'delete', 'Delete analysis'),
    ('clusters', 'view', 'View clusters'),
    ('clusters', 'create', 'Add clusters'),
    ('clusters', 'edit', 'Edit clusters'),
    ('clusters', 'delete', 'Delete clusters'),
    ('events', 'view', 'View events'),
    ('events', 'export', 'Export events'),
    ('reports', 'view', 'View reports'),
    ('reports', 'generate', 'Generate reports'),
    ('reports', 'schedule', 'Schedule reports'),
    ('reports', 'history', 'View report history'),
    ('security', 'view', 'View security events'),
    ('security', 'manage', 'Manage security settings'),
    ('users', 'view', 'View users'),
    ('users', 'create', 'Create users'),
    ('users', 'edit', 'Edit users'),
    ('users', 'delete', 'Delete users'),
    ('roles', 'view', 'View roles'),
    ('roles', 'create', 'Create roles'),
    ('roles', 'edit', 'Edit roles'),
    ('roles', 'delete', 'Delete roles'),
    ('settings', 'view', 'View settings'),
    ('settings', 'edit', 'Edit settings')
ON CONFLICT (resource, action) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'viewer' AND p.action = 'view'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'analyst' AND (p.action = 'view' OR
    (p.resource IN ('analysis','events','reports') AND p.action IN ('create','export','generate')))
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'operator' AND (p.action = 'view' OR
    (p.resource IN ('clusters','analysis') AND p.action IN ('create','edit','start')))
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u, roles r WHERE u.username = 'admin' AND r.name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;
