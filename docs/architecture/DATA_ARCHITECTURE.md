# Flowfish Data Architecture

## Overview

Flowfish uses a polyglot persistence architecture with three specialized databases, each optimized for its specific use case.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Flowfish Data Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    PostgreSQL (Metadata & Config)                    │    │
│  │                         Port: 5432                                   │    │
│  │                                                                      │    │
│  │  • Cluster configurations (connection details, credentials)          │    │
│  │  • Analysis definitions (scope, gadgets, time settings)              │    │
│  │  • User management and RBAC                                          │    │
│  │  • Workload metadata (synced from ClickHouse)                        │    │
│  │  • System settings and notification hooks                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ClickHouse (Event Lake)                           │    │
│  │                         Port: 9000                                   │    │
│  │                                                                      │    │
│  │  • Network flows (millions/day)                                      │    │
│  │  • DNS queries (millions/day)                                        │    │
│  │  • Process events (millions/day)                                     │    │
│  │  • Change events (infrastructure changes)                            │    │
│  │  • Workload metadata (pod discovery)                                 │    │
│  │  • Communication edges (aggregated)                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Neo4j (Dependency Graph)                          │    │
│  │                         Port: 7687                                   │    │
│  │                                                                      │    │
│  │  • Workload nodes (pods, deployments, services)                      │    │
│  │  • Communication relationships (COMMUNICATES_WITH)                   │    │
│  │  • Path finding and impact analysis                                  │    │
│  │  • Topology visualization                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Supporting Services                               │    │
│  │                                                                      │    │
│  │  Redis (6379): Session cache, leader election, rate limiting         │    │
│  │  RabbitMQ (5672): Event streaming, async processing                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## PostgreSQL Tables

### Core Metadata

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `clusters` | Cluster connection config | `api_url`, `kubeconfig_encrypted`, `gadget_namespace` |
| `analyses` | Analysis definitions | `scope_config`, `gadget_config`, `change_detection_enabled` |
| `analysis_runs` | Execution history | `started_at`, `completed_at`, `events_collected` |
| `users` | User accounts | `username`, `email`, `password_hash`, `role` |
| `roles` | RBAC roles | `name`, `permissions` |

### Supporting Tables

| Table | Purpose |
|-------|---------|
| `namespaces` | Namespace metadata |
| `workloads` | Workload metadata (synced from ClickHouse) |
| `communications` | Communication relationships |
| `notification_hooks` | Alert configurations |
| `system_settings` | Global settings |
| `oauth_providers` | SSO configurations |

### Analysis Configuration

```sql
-- Key analysis table structure
CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cluster_id INTEGER REFERENCES clusters(id),
    cluster_ids JSONB DEFAULT '[]',           -- Multi-cluster support
    is_multi_cluster BOOLEAN DEFAULT FALSE,
    scope_type VARCHAR(50),                   -- cluster, namespace, pod
    scope_config JSONB,                       -- Scope details
    gadget_config JSONB,                      -- eBPF modules
    time_config JSONB,                        -- Duration settings
    output_config JSONB,                      -- Dashboard, alerts
    change_detection_enabled BOOLEAN DEFAULT TRUE,  -- Feature toggle
    change_detection_strategy VARCHAR(50) DEFAULT 'baseline',  -- baseline, rolling_window, run_comparison
    change_detection_types JSONB DEFAULT '["all"]',  -- Types to track
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## ClickHouse Tables

### Event Tables

| Table | Source | Description | Volume |
|-------|--------|-------------|--------|
| `network_flows` | trace_tcp | Network connections | Millions/day |
| `dns_queries` | trace_dns | DNS lookups | Millions/day |
| `tcp_lifecycle` | trace_tcp | TCP state transitions | High |
| `process_events` | trace_exec | Process execution | High |
| `file_operations` | trace_open | File I/O | Medium |
| `capability_checks` | trace_capabilities | Linux caps | Low |
| `oom_kills` | trace_oomkill | OOM events | Low |
| `bind_events` | trace_bind | Socket binds | Medium |
| `sni_events` | trace_sni | TLS SNI | Medium |
| `mount_events` | trace_mount | Mount operations | Low |

### Change Events Table

```sql
CREATE TABLE change_events (
    event_id UUID,
    analysis_id Int32,
    run_id Int32,                    -- Analysis run reference
    cluster_id Int32,
    change_type String,              -- workload_added, workload_removed, etc.
    entity_type String,              -- workload, connection, namespace
    target_name String,
    namespace String,
    risk_level String,               -- low, medium, high, critical
    affected_services Int32,
    details String,
    changed_by String,
    detected_at DateTime,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMMDD(detected_at)
ORDER BY (analysis_id, cluster_id, detected_at, event_id);
```

### Derived Tables

| Table | Purpose |
|-------|---------|
| `workload_metadata` | Pod discovery (ReplacingMergeTree) |
| `communication_edges` | Aggregated communications (SummingMergeTree) |
| `change_events_*_mv` | Materialized views for stats |

---

## Neo4j Graph Model

### Nodes

```cypher
// Workload Node (Pod, Deployment, Service)
(:Workload {
    name: "pod-name",
    namespace: "default",
    workload_type: "pod",
    cluster_id: 1,
    analysis_id: 123,
    labels: '{"app": "frontend"}',
    created_at: datetime(),
    last_seen: datetime()
})

// Namespace Node
(:Namespace {
    name: "production",
    cluster_id: 1
})
```

### Relationships

```cypher
// Communication between workloads
(:Workload)-[:COMMUNICATES_WITH {
    port: 8080,
    protocol: "TCP",
    request_count: 12450,
    avg_latency_ms: 12.5,
    first_seen: datetime(),
    last_seen: datetime()
}]->(:Workload)

// Namespace containment
(:Namespace)-[:CONTAINS]->(:Workload)
```

---

## Data Flow Patterns

### Write Path (Ingestion)

```
Inspector Gadget (eBPF)
        │
        ▼
Ingestion Service
        │
        ├──► RabbitMQ (flowfish.network_flows)
        │           │
        │           └──► Timeseries Writer ──► ClickHouse
        │
        ├──► RabbitMQ (flowfish.workload_metadata)
        │           │
        │           └──► Timeseries Writer ──► ClickHouse
        │                                  └──► PostgreSQL (workloads sync)
        │
        └──► RabbitMQ (flowfish.change_events)  [If enabled]
                    │
                    └──► Timeseries Writer ──► ClickHouse
```

### Change Detection Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Change Detection Worker                              │
│                                                                             │
│  ┌─────────────────────────┐        ┌─────────────────────────┐            │
│  │    K8s API Detector     │        │    eBPF Event Detector   │            │
│  │                         │        │                          │            │
│  │ Source: K8s API         │        │ Source: ClickHouse       │            │
│  │ Detects:                │        │ Detects:                 │            │
│  │  • replica_changed      │        │  • connection_added      │            │
│  │  • config_changed       │        │  • connection_removed    │            │
│  │  • image_changed        │        │  • port_changed          │            │
│  │  • label_changed        │        │  • traffic_anomaly       │            │
│  └───────────┬─────────────┘        └───────────┬──────────────┘            │
│              │                                  │                            │
│              └──────────────┬───────────────────┘                            │
│                             │                                                │
│                             ▼                                                │
│                    ┌────────────────┐                                       │
│                    │  Merge Changes │                                       │
│                    └────────┬───────┘                                       │
│                             │                                                │
└─────────────────────────────┼────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    RabbitMQ     │
                    │ (change_events) │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │Timeseries Writer│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   ClickHouse    │
                    │ (change_events) │
                    └─────────────────┘
```

#### Detection Sources

| Source | Data Type | Storage | Update Frequency |
|--------|-----------|---------|------------------|
| K8s API | Infrastructure state | PostgreSQL (workloads) | 60s polling |
| ClickHouse | Behavioral events | ClickHouse (network_flows) | Real-time |

#### Detection Strategies

| Strategy | Description | Data Windows |
|----------|-------------|--------------|
| `baseline` | Compare against initial state | First 10min vs Now |
| `rolling_window` | Compare recent periods | Last 10min vs Last 5min |
| `run_comparison` | Compare between runs | Run N-1 vs Run N |

### Read Path (Query)

```
Frontend
    │
    ├── Events/Analytics ──► Backend ──► ClickHouse
    │
    ├── Dependency Graph ──► Backend ──► Neo4j
    │
    └── Metadata/Config ──► Backend ──► PostgreSQL
```

---

## Data Lifecycle

### Analysis-Scoped Data

All event data is scoped to an analysis. When an analysis is deleted:

| Layer | Cleanup Action |
|-------|----------------|
| PostgreSQL | CASCADE delete (analyses → analysis_runs) |
| ClickHouse | DELETE WHERE analysis_id = X (all tables) |
| Neo4j | DELETE nodes/edges WHERE analysis_id = X |
| Redis | DELETE analysis:* cache keys |

### Retention Policy

- **ClickHouse**: Time-partitioned with configurable TTL (default: 90 days)
- **Neo4j**: No TTL, cleaned with analysis deletion
- **PostgreSQL**: No TTL, cleaned with analysis deletion
- **Redis**: Session TTL (1 hour), cache TTL (5 minutes)

---

## Feature Toggles

### Change Detection

The change detection settings on `analyses` table control:

```
change_detection_enabled = TRUE (default)
├── Change Detection Worker monitors for changes
├── Both K8s API and eBPF detectors run
├── Changes published to RabbitMQ → ClickHouse
└── Change Detection page shows data

change_detection_enabled = FALSE
├── No change tracking
├── No data written to change_events
└── Lower storage/processing overhead
```

### Detection Strategy

The `change_detection_strategy` controls how changes are detected:

```
strategy = 'baseline' (default)
├── First N minutes captured as baseline
├── Current state compared against baseline
└── Best for long-running analyses

strategy = 'rolling_window'
├── Compares recent window vs previous window
├── Continuous real-time detection
└── Best for monitoring/alerting

strategy = 'run_comparison'
├── Compares current run vs previous run
├── Requires multiple runs
└── Best for deployment validation
```

### Change Types Filter

The `change_detection_types` array controls which changes to track:

```
types = ['all'] (default)
└── All change types tracked

types = ['replica_changed', 'connection_added']
├── Only specified types tracked
├── K8s types: replica_changed, config_changed, image_changed, label_changed
└── eBPF types: connection_added, connection_removed, port_changed
```

---

## Data Distribution Summary

| Data Type | PostgreSQL | ClickHouse | Neo4j |
|-----------|------------|------------|-------|
| Cluster config | ✅ | ❌ | ❌ |
| Analysis config | ✅ | ❌ | ❌ |
| User/RBAC | ✅ | ❌ | ❌ |
| Workload metadata | ✅ (synced) | ✅ (source) | ✅ (nodes) |
| Network events | ❌ | ✅ | ❌ |
| Change events | ❌ | ✅ | ❌ |
| Dependencies | ❌ | ❌ | ✅ |
| Aggregations | ❌ | ✅ | ❌ |
| Path finding | ❌ | ❌ | ✅ |

---

## Best Practices

### Query Optimization

1. **Time-series queries**: Always include time range filter
2. **Graph queries**: Limit traversal depth (default: 1 hop, max: 5 hops)
3. **Metadata queries**: Use indexed columns (cluster_id, analysis_id)

### Data Consistency

1. Analysis ID propagates across all layers
2. Deletion is atomic across all databases
3. Workload sync ensures PostgreSQL reflects ClickHouse state

### Scaling

| Database | Scaling Strategy |
|----------|------------------|
| PostgreSQL | Vertical (single master) |
| ClickHouse | Horizontal (sharding by analysis_id) |
| Neo4j | Causal cluster (read replicas) |

---

*Last Updated: January 2026*
*Architecture Version: 3.0*
