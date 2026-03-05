-- ClickHouse Event Tables for Inspector Gadget Data
-- Complete schema for all event types
-- Version: 1.1
--
-- NOTES:
-- - All tables include analysis_id for filtering by analysis scope
-- - cluster_name field stores analysis context (analysis_name) for easier identification
-- - All tables have bloom_filter index on analysis_id for fast filtering

-- =============================================================================
-- 1. NETWORK FLOWS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS network_flows (
    -- Timestamp
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Cluster & Analysis Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Source
    source_namespace String,
    source_pod String,
    source_container String,
    source_node String,
    source_ip String,
    source_port UInt16,
    
    -- Destination
    dest_namespace String,
    dest_pod String,
    dest_container String,
    dest_ip String,
    dest_port UInt16,
    dest_hostname String, -- If resolved
    
    -- Connection Details
    protocol String DEFAULT 'TCP',  -- TCP, UDP, ICMP, HTTP, GRPC, etc.
    direction String DEFAULT 'outbound',  -- inbound, outbound, internal
    connection_state String, -- ESTABLISHED, SYN_SENT, CLOSE_WAIT, etc.
    
    -- Metrics
    bytes_sent UInt64,
    bytes_received UInt64,
    packets_sent UInt32,
    packets_received UInt32,
    duration_ms UInt32,
    latency_ms Float32,
    
    -- Errors
    error_count UInt16,
    retransmit_count UInt16,
    error_type String DEFAULT '',  -- CONNECTION_RESET, CONNECTION_REFUSED, RETRANSMIT, etc.
    
    -- Labels & Metadata
    source_labels Map(String, String),
    dest_labels Map(String, String),
    
    -- Raw Event Data
    event_data_json String -- Full event JSON for debugging
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_pod, dest_pod, dest_port)
TTL toDateTime(timestamp) + INTERVAL 90 DAY;

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_source_pod ON network_flows (source_pod) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_dest_pod ON network_flows (dest_pod) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_dest_port ON network_flows (dest_port) TYPE set(1000);
CREATE INDEX IF NOT EXISTS idx_analysis_id ON network_flows (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 2. DNS QUERIES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS dns_queries (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Source
    source_namespace String,
    source_pod String,
    source_container String,
    source_ip String,
    
    -- DNS Query
    query_name String, -- domain name
    query_type String DEFAULT 'A',  -- A, AAAA, CNAME, MX, TXT, PTR, NS, SOA, SRV
    query_class String DEFAULT 'IN',
    
    -- DNS Response
    response_code String DEFAULT 'NOERROR',  -- NOERROR, FORMERR, SERVFAIL, NXDOMAIN, NOTIMP, REFUSED
    response_ips Array(String), -- Resolved IPs
    response_cnames Array(String), -- CNAME chain
    response_ttl UInt32,
    
    -- Performance
    latency_ms Float32,
    
    -- DNS Server
    dns_server_ip String,
    dns_server_port UInt16 DEFAULT 53,
    
    -- Metadata
    labels Map(String, String),
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_pod, query_name)
TTL toDateTime(timestamp) + INTERVAL 90 DAY;

CREATE INDEX IF NOT EXISTS idx_query_name ON dns_queries (query_name) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_dns_analysis_id ON dns_queries (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 3. TCP LIFECYCLE TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS tcp_lifecycle (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,  -- Also stores analysis_name for filtering
    analysis_id String,
    
    -- Connection
    source_ip String,
    source_port UInt16,
    dest_ip String,
    dest_port UInt16,
    
    -- TCP State
    old_state String DEFAULT 'CLOSED',  -- CLOSED, LISTEN, SYN_SENT, etc.
    new_state String DEFAULT 'ESTABLISHED',  -- CLOSED, LISTEN, SYN_SENT, etc.
    
    -- Pod Context
    source_namespace String,
    source_pod String,
    source_container String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_ip, dest_ip, dest_port)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_tcp_analysis_id ON tcp_lifecycle (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 4. PROCESS EVENTS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS process_events (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Process
    pid UInt32,
    ppid UInt32, -- Parent PID
    uid UInt32,
    gid UInt32,
    comm String, -- Command name
    exe String, -- Executable path
    args Array(String), -- Command arguments
    cwd String, -- Current working directory
    
    -- Event Type
    event_type String DEFAULT 'exec',  -- exec, exit, signal
    exit_code Int32, -- For exit events
    signal Int32, -- For signal events (SIGTERM=15, SIGKILL=9)
    
    -- Metadata
    labels Map(String, String),
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, pid)
TTL toDateTime(timestamp) + INTERVAL 90 DAY;

CREATE INDEX IF NOT EXISTS idx_comm ON process_events (comm) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_process_analysis_id ON process_events (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 5. FILE OPERATIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS file_operations (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    
    -- File Operation
    operation String DEFAULT 'open',  -- open, read, write, close, unlink, rename
    file_path String,
    file_flags String, -- O_RDONLY, O_WRONLY, O_RDWR, O_CREAT, etc.
    file_mode UInt32,
    
    -- Process
    pid UInt32,
    comm String,
    uid UInt32,
    gid UInt32,
    
    -- Metrics
    bytes UInt64, -- Bytes read/written
    duration_us UInt32, -- Operation duration in microseconds
    
    -- Result
    error_code Int32, -- 0 = success, errno on failure
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, file_path)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_file_path ON file_operations (file_path) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_file_analysis_id ON file_operations (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 6. CAPABILITY CHECKS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS capability_checks (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    
    -- Capability
    capability String, -- CAP_NET_ADMIN, CAP_SYS_ADMIN, etc.
    syscall String, -- Syscall that triggered check
    
    -- Process
    pid UInt32,
    comm String,
    uid UInt32,
    gid UInt32,
    
    -- Result
    verdict String DEFAULT 'allowed',  -- allowed, denied
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, capability)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_capability ON capability_checks (capability) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_cap_analysis_id ON capability_checks (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 7. OOM KILLS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS oom_kills (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Killed Process
    pid UInt32,
    comm String,
    
    -- Memory
    memory_limit UInt64, -- Container memory limit (bytes)
    memory_usage UInt64, -- Memory usage at time of kill (bytes)
    memory_pages_total UInt64,
    memory_pages_free UInt64,
    
    -- Cgroup
    cgroup_path String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod)
TTL toDateTime(timestamp) + INTERVAL 90 DAY;

CREATE INDEX IF NOT EXISTS idx_oom_analysis_id ON oom_kills (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 8. BIND EVENTS TABLE (Socket Binds)
-- =============================================================================
CREATE TABLE IF NOT EXISTS bind_events (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Bind Details
    bind_addr String,
    bind_port UInt16,
    protocol String DEFAULT 'TCP',  -- TCP, UDP
    interface String,
    
    -- Result
    error_code Int32 DEFAULT 0,
    
    -- Process
    pid UInt32,
    comm String,
    uid UInt32,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, bind_port)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_bind_port ON bind_events (bind_port) TYPE set(1000);
CREATE INDEX IF NOT EXISTS idx_bind_analysis_id ON bind_events (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 9. SNI EVENTS TABLE (TLS/SSL Server Name Indication)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sni_events (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    
    -- SNI Details
    sni_name String,  -- Server Name from TLS ClientHello
    src_ip String,
    src_port UInt16,
    dst_ip String,
    dst_port UInt16,
    
    -- TLS Details
    tls_version String,  -- TLS1.2, TLS1.3, etc.
    cipher_suite String,
    
    -- Process
    pid UInt32,
    comm String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, sni_name)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_sni_name ON sni_events (sni_name) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_sni_analysis_id ON sni_events (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 10. MOUNT EVENTS TABLE (Filesystem Mounts)
-- =============================================================================
CREATE TABLE IF NOT EXISTS mount_events (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Mount Details
    operation String DEFAULT 'mount',  -- mount, umount
    source String,  -- Source path/device
    target String,  -- Mount point
    fs_type String,  -- ext4, nfs, tmpfs, etc.
    flags String,
    options String,
    
    -- Result
    error_code Int32 DEFAULT 0,
    
    -- Process
    pid UInt32,
    comm String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, target)
TTL toDateTime(timestamp) + INTERVAL 30 DAY;

CREATE INDEX IF NOT EXISTS idx_mount_target ON mount_events (target) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_mount_analysis_id ON mount_events (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- 11. WORKLOAD METADATA TABLE (Pod/Workload Info for IP -> Name Lookups)
-- =============================================================================
CREATE TABLE IF NOT EXISTS workload_metadata (
    timestamp DateTime64(3) DEFAULT now64(3),
    
    -- Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Workload Info
    namespace String,
    workload_name String,  -- Deployment/StatefulSet/DaemonSet name
    workload_type String DEFAULT 'Pod',  -- Pod, Deployment, StatefulSet, DaemonSet
    
    -- Pod Info
    pod_name String,
    pod_uid String,
    container_name String,
    container_id String,
    node_name String,
    pod_ip String,
    
    -- Labels & Annotations
    labels Map(String, String),
    annotations Map(String, String),
    
    -- Owner Reference
    owner_kind String,  -- ReplicaSet, StatefulSet, DaemonSet
    owner_name String,
    
    -- Tracking
    first_seen DateTime64(3),
    last_seen DateTime64(3),
    event_count UInt32 DEFAULT 1
    
) ENGINE = ReplacingMergeTree(last_seen)
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (analysis_id, cluster_id, namespace, pod_name)  -- analysis_id FIRST for full isolation
TTL toDateTime(timestamp) + INTERVAL 90 DAY;

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_wm_pod_ip ON workload_metadata (pod_ip) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_wm_pod_name ON workload_metadata (pod_name) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_wm_workload_name ON workload_metadata (workload_name) TYPE bloom_filter();
CREATE INDEX IF NOT EXISTS idx_wm_analysis_id ON workload_metadata (analysis_id) TYPE bloom_filter();

-- =============================================================================
-- MATERIALIZED VIEWS FOR AGGREGATIONS
-- =============================================================================
-- NOTE: All MV's include analysis_id for full isolation between analyses.
-- This prevents data from different analyses being merged together.

-- Top talkers (per 5 minutes) - WITH ANALYSIS ISOLATION
CREATE MATERIALIZED VIEW IF NOT EXISTS network_flows_5min_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_5min)
ORDER BY (analysis_id, timestamp_5min, cluster_id, source_pod, dest_pod, dest_port)
AS SELECT
    analysis_id,
    toStartOfFiveMinutes(timestamp) AS timestamp_5min,
    cluster_id,
    source_pod,
    dest_pod,
    dest_port,
    protocol,
    count() AS request_count,
    sum(bytes_sent) AS total_bytes_sent,
    sum(bytes_received) AS total_bytes_received,
    avg(latency_ms) AS avg_latency_ms,
    max(latency_ms) AS max_latency_ms
FROM network_flows
GROUP BY analysis_id, timestamp_5min, cluster_id, source_pod, dest_pod, dest_port, protocol;

-- DNS query statistics (per hour) - WITH ANALYSIS ISOLATION
CREATE MATERIALIZED VIEW IF NOT EXISTS dns_queries_hourly_mv
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(timestamp_hour)
ORDER BY (analysis_id, timestamp_hour, cluster_id, query_name)
AS SELECT
    analysis_id,
    toStartOfHour(timestamp) AS timestamp_hour,
    cluster_id,
    query_name,
    query_type,
    count() AS query_count,
    countIf(response_code = 'NOERROR') AS success_count,
    countIf(response_code = 'NXDOMAIN') AS nxdomain_count,
    avg(latency_ms) AS avg_latency_ms
FROM dns_queries
GROUP BY analysis_id, timestamp_hour, cluster_id, query_name, query_type;

-- =============================================================================
-- USEFUL QUERIES
-- =============================================================================

-- Top 10 communication pairs in last hour
-- SELECT 
--     source_pod, dest_pod, dest_port,
--     count() as connections,
--     sum(bytes_sent + bytes_received) as total_bytes
-- FROM network_flows
-- WHERE timestamp > now() - INTERVAL 1 HOUR
-- GROUP BY source_pod, dest_pod, dest_port
-- ORDER BY connections DESC
-- LIMIT 10;

-- DNS resolution failures in last 24h
-- SELECT 
--     query_name, response_code, count() as failures
-- FROM dns_queries
-- WHERE timestamp > now() - INTERVAL 24 HOUR
--   AND response_code != 'NOERROR'
-- GROUP BY query_name, response_code
-- ORDER BY failures DESC;

-- OOM kills per pod in last 7 days
-- SELECT 
--     namespace, pod, count() as oom_count,
--     avg(memory_usage / memory_limit * 100) as avg_mem_usage_percent
-- FROM oom_kills
-- WHERE timestamp > now() - INTERVAL 7 DAY
-- GROUP BY namespace, pod
-- ORDER BY oom_count DESC;

