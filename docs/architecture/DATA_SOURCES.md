# Page → Data Source Mapping

This document details which data sources (ClickHouse / Neo4j) each Flowfish frontend page uses and their time range filtering support.

## Data Sources Overview

### ClickHouse (timeseries-query microservice)
- **Purpose**: Store and query time-series event data
- **Data Type**: Events (DNS, SNI, Process, File, Security, OOM, Bind, Mount, Network Flows)
- **Features**: 
  - High-volume time-based data
  - Time range filtering support
  - Aggregation and analytics queries

### Neo4j (graph-query microservice)
- **Purpose**: Store and query service relationship graph (dependency graph)
- **Data Type**: Nodes (Workloads/Pods) and Edges (Communications)
- **Features**:
  - Relationship-based queries
  - Real-time state visualization
  - Impact analysis

---

## Page Details

### 1. Events Timeline (`/events-timeline`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| All Events | ClickHouse | `/events` | ✅ Supported |
| Event Histogram | ClickHouse | `/events/histogram` | ✅ Supported |
| Event Stats | ClickHouse | `/events/stats` | ❌ Aggregate |

**RTK Query Hooks:**
- `useGetEventsQuery` → ClickHouse
- `useGetEventHistogramQuery` → ClickHouse
- `useGetEventStatsQuery` → ClickHouse

**Time Range Implementation:**
```typescript
const queryParams = useMemo(() => ({
  cluster_id: selectedClusterId!,
  analysis_id: selectedAnalysisId,
  event_types: selectedTypes.join(','),
  start_time: dateRange?.[0]?.toISOString(),
  end_time: dateRange?.[1]?.toISOString(),
  limit: pagination.pageSize,
  offset: (pagination.current - 1) * pagination.pageSize,
}), [selectedClusterId, selectedAnalysisId, selectedTypes, dateRange, pagination]);
```

---

### 2. Activity Monitor (`/activity-monitor`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Process Events | ClickHouse | `/events/process` | ✅ Supported |
| File Events | ClickHouse | `/events/file` | ✅ Supported |
| Mount Events | ClickHouse | `/events/mount` | ✅ Supported |
| Event Stats | ClickHouse | `/events/stats` | ❌ Aggregate |

**RTK Query Hooks:**
- `useGetProcessEventsQuery` → ClickHouse
- `useGetFileEventsQuery` → ClickHouse
- `useGetMountEventsQuery` → ClickHouse
- `useGetEventStatsQuery` → ClickHouse

---

### 3. Security Center (`/security-center`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Security Events | ClickHouse | `/events/security` | ✅ Supported |
| OOM Events | ClickHouse | `/events/oom` | ✅ Supported |
| Event Stats | ClickHouse | `/events/stats` | ❌ Aggregate |

**RTK Query Hooks:**
- `useGetSecurityEventsQuery` → ClickHouse
- `useGetOomEventsQuery` → ClickHouse
- `useGetEventStatsQuery` → ClickHouse

**Note:** Security events are filtered by `verdict = 'denied'` (capability_checks table).

---

### 4. Network Explorer (`/network-explorer`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| **Network Flows** | **ClickHouse** | `/events/network` | ✅ Supported |
| DNS Queries | ClickHouse | `/events/dns` | ✅ Supported |
| SNI/TLS Events | ClickHouse | `/events/sni` | ✅ Supported |
| Bind Events | ClickHouse | `/events/bind` | ✅ Supported |
| Dependency Graph | Neo4j | `/communications/graph` | ✅ Supported |
| Communication Stats | Neo4j | `/communications/stats` | ❌ Aggregate |

**RTK Query Hooks:**
- `useGetNetworkFlowsQuery` → ClickHouse (**Flows Tab**)
- `useGetDnsQueriesQuery` → ClickHouse (DNS Tab)
- `useGetSniEventsQuery` → ClickHouse (TLS Tab)
- `useGetBindEventsQuery` → ClickHouse (Services Tab)
- `useGetDependencyGraphQuery` → Neo4j (Graph Visualization)
- `useGetCommunicationStatsQuery` → Neo4j

**Important:** The Flows tab fetches data from **ClickHouse `network_flows`** table (not Neo4j). This ensures proper time range filtering.

---

### 5. Change Detection (`/change-detection`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Changes | ClickHouse | `/changes` | ✅ Supported |

**RTK Query Hooks:**
- `useGetChangesQuery` → ClickHouse

---

### 6. Reports (`/reports`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Export Data | ClickHouse | `/export/*` | ✅ Supported |

**Export Endpoints:**
- `/export/events` → Export event data
- `/export/communications` → Export communication data

---

### 7. Map (`/map`) - Dependency Map

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Dependency Graph | Neo4j | `/communications/graph` | ❌ Current state |
| Node Enrichment | ClickHouse | `/events/*` | ❌ Analysis-based |

**RTK Query Hooks:**
- `useGetDependencyGraphQuery` → Neo4j
- `useNodeEnrichment` (custom hook) → Multiple ClickHouse endpoints

**Note:** Map page is designed for current state visualization, no time range filter needed.

---

### 8. Live Map (`/live-map`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Live Graph | Neo4j | `/communications/graph` | ❌ Real-time |

**Note:** Designed for live monitoring, uses auto-refresh instead of time range.

---

### 9. Impact Simulation (`/impact-simulation`)

| Data | Source | API Endpoint | Time Range |
|------|--------|--------------|------------|
| Dependency Graph | Neo4j | `/communications/graph` | ❌ Simulation |

**Note:** Performs graph analysis for "what-if" scenarios.

---

## Time Range Filtering Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                              │
├─────────────────────────────────────────────────────────────────┤
│  RangePicker (Ant Design)                                       │
│       ↓                                                         │
│  dateRange: [dayjs.Dayjs, dayjs.Dayjs]                         │
│       ↓                                                         │
│  toISOString() → "2024-12-01T00:00:00.000Z"                    │
│       ↓                                                         │
│  RTK Query: { start_time, end_time, ... }                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API (FastAPI)                         │
├─────────────────────────────────────────────────────────────────┤
│  @router.get("/events/...")                                     │
│  start_time: Optional[str] = Query(None)                        │
│  end_time: Optional[str] = Query(None)                          │
│       ↓                                                         │
│  EventService → EventRepository                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              CLICKHOUSE (timeseries-query)                       │
├─────────────────────────────────────────────────────────────────┤
│  WHERE timestamp >= parseDateTimeBestEffort('ISO_STRING')       │
│    AND timestamp <= parseDateTimeBestEffort('ISO_STRING')       │
│                                                                 │
│  parseDateTimeBestEffort: ISO 8601 string → DateTime            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                 NEO4J (graph-query)                              │
├─────────────────────────────────────────────────────────────────┤
│  WHERE comm.last_seen >= datetime('ISO_STRING').epochMillis     │
│    AND comm.last_seen <= datetime('ISO_STRING').epochMillis     │
│                                                                 │
│  last_seen: Stored using timestamp() function (epoch ms)        │
│  datetime().epochMillis: ISO string → epoch milliseconds        │
└─────────────────────────────────────────────────────────────────┘
```

---

## ClickHouse Tables

| Table | Event Type | Description |
|-------|------------|-------------|
| `network_flows` | network_flow | Network flow data |
| `dns_queries` | dns_query | DNS queries |
| `sni_events` | sni_event | TLS/SNI data |
| `bind_events` | bind_event | Socket bind operations |
| `process_events` | process_event | Process exec/exit |
| `file_operations` | file_event | File I/O operations |
| `mount_events` | mount_event | Mount/umount operations |
| `capability_checks` | security_event | Linux capability checks |
| `oom_kills` | oom_event | Out-of-memory events |

---

## Neo4j Node and Relationship Types

### Nodes
- `Workload`: Kubernetes workload (Deployment, StatefulSet, etc.)
- `Pod`: Kubernetes pod
- `Service`: Kubernetes service
- `ExternalService`: External cluster services

### Relationships
- `COMMUNICATES_WITH`: Inter-service communication
- `OWNS`: Owner relationship (Deployment → Pod)
- `EXPOSES`: Service → Pod relationship

### Relationship Properties
```cypher
(source)-[comm:COMMUNICATES_WITH {
  protocol: "TCP",
  port: 8080,
  request_count: 100,
  bytes_transferred: 50000,
  last_seen: 1701388800000,  // epoch milliseconds
  first_seen: 1701302400000,
  analysis_id: "123"
}]->(target)
```

---

## Performance Notes

1. **ClickHouse Queries**: `parseDateTimeBestEffort()` function auto-parses ISO 8601 format
2. **Neo4j Queries**: `datetime().epochMillis` conversion required for epoch milliseconds comparison
3. **RTK Query Cache**: Query params stabilized with `useMemo` to prevent unnecessary re-fetches
4. **Pagination**: All ClickHouse queries support `LIMIT` and `OFFSET`

---

*Last updated: December 2024*
