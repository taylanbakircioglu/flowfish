# Flowfish Storage Architecture

## Overview

Flowfish uses a **specialized storage architecture** with **ClickHouse**, **Neo4j**, and **PostgreSQL** working together for different data needs.

### Why Three Databases?

| Database | Strength | Role in Flowfish |
|----------|----------|------------------|
| **ClickHouse** | Time-series, High-volume analytics | Event data, metrics, change_events |
| **Neo4j** | Graph queries, Relationships | Dependency graph, path finding, topology |
| **PostgreSQL** | ACID, Transactional, Relational | Metadata, configurations, workloads |

### Data Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Flowfish Data Architecture                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    PostgreSQL (Metadata Layer)                   │    │
│  │  ┌─────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────┐  │    │
│  │  │  clusters   │ │  analyses  │ │ workloads  │ │    users    │  │    │
│  │  │  (config)   │ │ (settings) │ │ (metadata) │ │   (RBAC)    │  │    │
│  │  └─────────────┘ └────────────┘ └────────────┘ └─────────────┘  │    │
│  │  ┌─────────────┐ ┌────────────┐ ┌────────────────────────────┐  │    │
│  │  │ namespaces  │ │notifications│ │    communications        │  │    │
│  │  │  (names)    │ │  (hooks)   │ │    (relationships)        │  │    │
│  │  └─────────────┘ └────────────┘ └────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    ClickHouse (Event Layer)                      │    │
│  │  ┌─────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────┐  │    │
│  │  │network_flows│ │dns_queries │ │process_evts│ │change_events│  │    │
│  │  │ (millions)  │ │ (millions) │ │ (millions) │ │ (analytics) │  │    │
│  │  └─────────────┘ └────────────┘ └────────────┘ └─────────────┘  │    │
│  │  ┌─────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────┐  │    │
│  │  │tcp_lifecycle│ │bind_events │ │ sni_events │ │workload_meta│  │    │
│  │  └─────────────┘ └────────────┘ └────────────┘ └─────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Neo4j (Graph Layer)                           │    │
│  │  ┌─────────────────────────────────────────────────────────┐    │    │
│  │  │  (:Workload)-[:COMMUNICATES_WITH]->(:Workload)         │    │    │
│  │  │  (:Namespace)-[:CONTAINS]->(:Workload)                 │    │    │
│  │  │  Path finding, impact analysis, topology               │    │    │
│  │  └─────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Change Detection Architecture

Change events are stored **exclusively in ClickHouse**. PostgreSQL is no longer used for change events.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Change Detection - ClickHouse Only                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Backend / Change Detection Worker                                       │
│           │                                                              │
│           └───────────► RabbitMQ ───────────► Timeseries Writer         │
│                         (flowfish.change_events)         │              │
│                                                          ▼              │
│                                                    ClickHouse           │
│                                                    (change_events)      │
│                                                    • Analytics          │
│                                                    • Run-based filter   │
│                                                    • High performance   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Change Events Table (ClickHouse)

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
    target_namespace Nullable(String),
    risk_level String,               -- low, medium, high, critical
    affected_services Int32,
    details String,                  -- JSON
    changed_by String,
    detected_at DateTime,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMMDD(detected_at)
ORDER BY (analysis_id, cluster_id, detected_at, event_id);
```

**Key Features:**
- `run_id`: Enables run-based filtering (which analysis cycle)
- `ReplacingMergeTree`: Idempotent writes with event_id
- **No TTL**: Data deleted when analysis is deleted (cascade pattern)

---

## ClickHouse: Time-Series & Analytics Engine

### Tables

| Table | Purpose | Volume |
|-------|---------|--------|
| `network_flows` | Network traffic events | Millions/day |
| `dns_queries` | DNS query events | Millions/day |
| `process_events` | Process lifecycle | Millions/day |
| `tcp_lifecycle` | TCP state transitions | High |
| `change_events` | Infrastructure changes | Thousands/day |
| `workload_metadata` | Pod discovery data | Thousands |
| `communication_edges` | Aggregated connections | Thousands |

### Use Cases

**Time-series Analysis:**
```sql
SELECT 
    toStartOfMinute(timestamp) as minute,
    count(*) as requests,
    avg(latency_ms) as avg_latency
FROM network_flows
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY minute
ORDER BY minute;
```

**Change Analytics:**
```sql
SELECT 
    change_type,
    risk_level,
    count(*) as count
FROM change_events
WHERE analysis_id = 123
  AND run_id = 456  -- Optional: filter by run
GROUP BY change_type, risk_level
ORDER BY count DESC;
```

---

## Neo4j: Dependency Graph Engine

### Graph Model

```cypher
// Workload Node
(:Workload {
    name: "pod-name",
    namespace: "production",
    cluster_id: 1,
    analysis_id: 123
})

// Communication Relationship
(:Workload)-[:COMMUNICATES_WITH {
    port: 8080,
    protocol: "TCP",
    request_count: 12450,
    avg_latency: 12.5
}]->(:Workload)
```

### Use Cases

**Impact Analysis:**
```cypher
MATCH (target:Workload {name: "payment-service"})<-[:COMMUNICATES_WITH*1..3]-(affected)
RETURN affected.name, affected.namespace
```

**Path Finding:**
```cypher
MATCH path = shortestPath(
    (src:Workload {name: "frontend"})-[:COMMUNICATES_WITH*]-(dst:Workload {name: "database"})
)
RETURN path
```

---

## PostgreSQL: Metadata & Configuration

### Tables

| Table | Purpose |
|-------|---------|
| `clusters` | Cluster connection configuration |
| `analyses` | Analysis definitions and settings |
| `analysis_runs` | Analysis execution history |
| `workloads` | Workload metadata (synced from ClickHouse) |
| `namespaces` | Namespace metadata |
| `communications` | Communication relationships |
| `users` | User management and RBAC |
| `notification_hooks` | Alert configurations |
| `system_settings` | Global configuration |

### Key Fields

**analyses table (includes change detection toggle):**
```sql
CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cluster_id INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    change_detection_enabled BOOLEAN DEFAULT TRUE,  -- Feature toggle
    scope_config JSONB,
    gadget_config JSONB,
    time_config JSONB,
    output_config JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Data Flow

### Event Ingestion Pipeline

```
Inspector Gadget (eBPF)
        │
        ▼
Ingestion Service (gRPC)
        │
        ├──► RabbitMQ (flowfish.network_flows)
        │           │
        │           ▼
        │    Timeseries Writer ──► ClickHouse
        │
        ├──► RabbitMQ (flowfish.workload_metadata)
        │           │
        │           ▼
        │    Timeseries Writer ──► ClickHouse
        │                     └──► PostgreSQL (workloads sync)
        │
        └──► RabbitMQ (flowfish.change_events)  [If change detection enabled]
                    │
                    ▼
             Timeseries Writer ──► ClickHouse (change_events)
```

### Change Detection Flow

```
Analysis Running (change_detection_enabled=true)
        │
        ▼
Change Detection Worker
        │
        ├── Detect changes (compare current vs previous state)
        │
        └── Publish to RabbitMQ ──► Timeseries Writer ──► ClickHouse
                                                              │
                                                              ▼
                                                    Frontend (Change Detection Page)
```

---

## Data Retention & Cleanup

### Analysis Deletion (Cascade)

When an analysis is deleted, all associated data is removed:

| Layer | Data Deleted |
|-------|--------------|
| PostgreSQL | `analyses`, `analysis_runs` (CASCADE) |
| ClickHouse | All tables filtered by `analysis_id` |
| Neo4j | Workload nodes and edges with `analysis_id` |
| Redis | Analysis-specific cache keys |

```python
# Deletion order in analyses.py delete_analysis()
1. Neo4j: DELETE nodes/edges WHERE analysis_id = X
2. ClickHouse: DELETE FROM <all tables> WHERE analysis_id = X
3. Redis: DELETE analysis:* keys
4. PostgreSQL: DELETE FROM analyses WHERE id = X (CASCADE to analysis_runs)
```

---

## Performance Characteristics

| Operation | ClickHouse | Neo4j | PostgreSQL |
|-----------|------------|-------|------------|
| Raw event storage | ✅ Excellent | ❌ Poor | ❌ Poor |
| Time-series aggregation | ✅ Excellent | ❌ Poor | ⚠️ Limited |
| Graph traversal | ❌ Poor | ✅ Excellent | ❌ Poor |
| Path finding | ❌ N/A | ✅ Excellent | ❌ N/A |
| Metadata queries | ⚠️ Limited | ❌ Poor | ✅ Excellent |
| ACID transactions | ❌ No | ❌ Limited | ✅ Excellent |

---

## Summary

**ClickHouse:**
- High-volume, high-dimensional event data
- Time-series analytics
- Change events (run-based analytics)
- Historical data retention

**Neo4j:**
- Real-time dependency graph
- Complex path queries
- Impact analysis
- Topology visualization

**PostgreSQL:**
- ACID transactions
- Metadata (clusters, analyses, users)
- Configuration storage
- Feature toggles (e.g., change_detection_enabled)

**Together:**
- Complete visibility (events + relationships + metadata)
- Optimal performance (right tool for right job)
- Scalability (scale each independently)
- Enterprise-ready (ACID + Analytics + Graph)

---

**Flowfish = ClickHouse (event lake) + Neo4j (dependency brain) + PostgreSQL (metadata store)**

---

*Last Updated: January 2026*
*Architecture Version: 3.0 (ClickHouse-only Change Detection)*
