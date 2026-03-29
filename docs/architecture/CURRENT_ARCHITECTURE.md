# 🐟 Flowfish - Güncel Mimari (Ocak 2026)

## Sistem Genel Bakış

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND LAYER                                    │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         React Application                                 │  │
│  │  Pages: LiveMap, Map, EventsTimeline, SecurityCenter, ActivityMonitor,   │  │
│  │         NetworkExplorer, ChangeDetection, Reports, AnalysisWizard        │  │
│  │  API: eventsApi, communicationApi, changesApi, clusterApi, analysisApi   │  │
│  │  Port: 3000                                                               │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
└───────────────────────────────────┼────────────────────────────────────────────┘
                                    │ REST API (HTTP/JSON)
                                    ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND LAYER                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                      Backend (FastAPI) - Port: 8000                       │  │
│  │  Routers: events, communications, analyses, clusters, export, changes    │  │
│  │  Services: EventService, CommunicationService, ChangeDetectionService    │  │
│  │  Repositories: EventRepository → TimeseriesQueryEventRepository           │  │
│  └──────────┬────────────────────┬────────────────────┬─────────────────────┘  │
└─────────────┼────────────────────┼────────────────────┼────────────────────────┘
              │ gRPC               │ HTTP               │ HTTP
              ▼                    ▼                    ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   Cluster Manager   │  │  timeseries-query   │  │    graph-query      │
│    Port: 5001       │  │    Port: 8002  🆕   │  │    Port: 8001       │
│    (gRPC)           │  │    (HTTP/REST)      │  │    (HTTP/REST)      │
└──────────┬──────────┘  └──────────┬──────────┘  └──────────┬──────────┘
           │                        │                        │
           ▼                        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│    PostgreSQL       │  │     ClickHouse      │  │       Neo4j         │
│    (Metadata)       │  │    (TimeSeries)     │  │      (Graph)        │
│    Port: 5432       │  │    Port: 9000       │  │    Port: 7687       │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

## Veri Akış Mimarisi

### 1. OKUMA AKIŞI (Frontend → Database)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          READ PATH - Events                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Frontend Page (e.g., EventsTimeline.tsx)                                    │
│       │                                                                      │
│       ▼ useGetEventsQuery()                                                  │
│  eventsApi (RTK Query) → /api/v1/events/*                                    │
│       │                                                                      │
│       ▼                                                                      │
│  Backend Router (routers/events.py)                                          │
│       │                                                                      │
│       ▼                                                                      │
│  EventService (services/event_service.py)                                    │
│       │                                                                      │
│       ▼                                                                      │
│  TimeseriesQueryEventRepository ──HTTP──► timeseries-query:8002              │
│                                                      │                       │
│                                                      ▼                       │
│                                               ClickHouse                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                          READ PATH - Graph                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Frontend Page (e.g., LiveMap.tsx, Map.tsx)                                  │
│       │                                                                      │
│       ▼ useGetDependencyGraphQuery()                                         │
│  communicationApi (RTK Query) → /api/v1/communications/graph                 │
│       │                                                                      │
│       ▼                                                                      │
│  Backend Router (routers/communications.py)                                  │
│       │                                                                      │
│       ▼                                                                      │
│  GraphQueryClient ───────────────HTTP──────► graph-query:8001                │
│                                                      │                       │
│                                                      ▼                       │
│                                                   Neo4j                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2. YAZMA AKIŞI (Inspector Gadget → Database)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          WRITE PATH - Events                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Inspector Gadget (kubectl gadget trace_*)                                   │
│       │                                                                      │
│       ▼ JSON Stream (stdout)                                                 │
│  Ingestion Service (KubectlGadgetClient)                                     │
│       │                                                                      │
│       ▼ Normalized Events                                                    │
│  RabbitMQ (Exchange: flowfish.events)                                        │
│       │                                                                      │
│       ├──────────────────────────────────────────┐                           │
│       ▼                                          ▼                           │
│  timeseries-writer                        graph-writer                       │
│  (RabbitMQ Consumer)                      (RabbitMQ Consumer)                │
│       │                                          │                           │
│       ▼ Bulk INSERT                              ▼ MERGE                     │
│  ClickHouse                                   Neo4j                          │
│  (10 Event Tables)                           (Workload Nodes + Edges)        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3. ANALİZ AKIŞI (Analysis Orchestrator)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          ANALYSIS PATH                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Backend /analyses/{id}/start                                                │
│       │                                                                      │
│       ▼ gRPC                                                                 │
│  Analysis Orchestrator (Port: 5002)                                          │
│       │                                                                      │
│       ├── Start Inspector Gadget (gadget_client.py)                          │
│       │                                                                      │
│       └── Analysis Execution (analysis_executor.py)                          │
│              │                                                               │
│              ├── timeseries_query_client.py ──► timeseries-query:8002        │
│              │                                          │                    │
│              │                                          ▼                    │
│              │                                     ClickHouse                │
│              │                                                               │
│              └── graph_query_client.py ──────► graph-query:8001              │
│                                                         │                    │
│                                                         ▼                    │
│                                                      Neo4j                   │
│                                                                              │
│  Analysis Types:                                                             │
│  ├── dependency_mapping → graph-query                                        │
│  ├── change_detection → graph-query + timeseries-query                       │
│  ├── anomaly_detection → timeseries-query                                    │
│  ├── baseline_creation → graph-query + timeseries-query                      │
│  └── risk_assessment → graph-query + timeseries-query                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Microservice Listesi

| # | Servis | Port | Protokol | Sorumluluk |
|---|--------|------|----------|------------|
| 1 | **frontend** | 3000 | HTTP | React UI (Dashboard, LiveMap, Wizard) |
| 2 | **backend** | 8000 | HTTP | FastAPI REST API, Auth, WebSocket |
| 3 | **api-gateway** | 8000 | HTTP | FastAPI Gateway (microservices proxy) |
| 4 | **cluster-manager** | 5001 | gRPC | Kubernetes cluster management |
| 5 | **analysis-orchestrator** | 5002 | gRPC | Analysis lifecycle + Gadget lifecycle |
| 6 | **ingestion-service** | 5000 | gRPC | eBPF data ingestion via kubectl gadget |
| 7 | **timeseries-writer** | - | RabbitMQ | ClickHouse bulk writer + Change events |
| 8 | **timeseries-query** | 8002 | HTTP | ClickHouse query service |
| 9 | **graph-writer** | - | RabbitMQ | Neo4j dependency builder |
| 10 | **graph-query** | 8001 | HTTP | Neo4j query service |
| 11 | **change-detection-worker** | 8001 | HTTP | Periodic change detection (ClickHouse) |

## Veritabanları

| Veritabanı | Tip | Port | Kullanım |
|------------|-----|------|----------|
| **PostgreSQL** | RDBMS | 5432 | Metadata, configurations, workloads |
| **ClickHouse** | Columnar | 9000 | Time-series events (11 tablo), change_events |
| **Neo4j** | Graph | 7687 | Dependency graph (nodes + edges) |
| **Redis** | Cache | 6379 | Session, cache, leader election |
| **RabbitMQ** | Queue | 5672 | Event streaming, change_events exchange |

## ClickHouse Event Tabloları

| # | Tablo | Kaynak | Açıklama |
|---|-------|--------|----------|
| 1 | `network_flows` | trace_tcp | TCP/UDP network connections |
| 2 | `dns_queries` | trace_dns | DNS lookups |
| 3 | `tcp_lifecycle` | trace_tcp | TCP state transitions |
| 4 | `process_events` | trace_exec | Process execution |
| 5 | `file_operations` | trace_open | File I/O operations |
| 6 | `capability_checks` | trace_capabilities | Linux capabilities |
| 7 | `oom_kills` | trace_oomkill | OOM kills |
| 8 | `bind_events` | trace_bind | Socket binds |
| 9 | `sni_events` | trace_sni | TLS SNI |
| 10 | `mount_events` | trace_mount | Filesystem mounts |
| 11 | `change_events` | change-detection-worker | Infrastructure changes (run-based) 🆕 |

## Frontend-Backend API Mapping

| Frontend Sayfa | eventsApi Hook | Backend Endpoint | Query Service |
|----------------|----------------|------------------|---------------|
| EventsTimeline | `useGetEventsQuery` | `/events` | timeseries-query |
| SecurityCenter | `useGetSecurityEventsQuery` | `/events/security` | timeseries-query |
| SecurityCenter | `useGetOomEventsQuery` | `/events/oom` | timeseries-query |
| ActivityMonitor | `useGetProcessEventsQuery` | `/events/process` | timeseries-query |
| ActivityMonitor | `useGetFileEventsQuery` | `/events/file` | timeseries-query |
| ActivityMonitor | `useGetMountEventsQuery` | `/events/mount` | timeseries-query |
| NetworkExplorer | `useGetDnsQueriesQuery` | `/events/dns` | timeseries-query |
| NetworkExplorer | `useGetSniEventsQuery` | `/events/sni` | timeseries-query |
| NetworkExplorer | `useGetBindEventsQuery` | `/events/bind` | timeseries-query |
| LiveMap/Map | `useGetDependencyGraphQuery` | `/communications/graph` | graph-query |
| ChangeDetection | `useGetChangesQuery` | `/changes` | PostgreSQL/ClickHouse (hybrid) 🆕 |
| ChangeDetection | `useGetAnalysisRunsQuery` | `/analyses/{id}/runs` | PostgreSQL 🆕 |
| ChangeDetection | (WebSocket) | `/ws/changes` | Real-time updates 🆕 |

## Yeni Eklenen Dosyalar (Ocak 2026)

### Change Detection Worker (Hybrid Architecture) 🆕
```
backend/
├── worker_main.py              # Worker entry point
├── Dockerfile.worker           # Worker image build
├── services/
│   ├── change_detection_service.py   # Change detection logic
│   └── change_event_publisher.py     # RabbitMQ publisher (ClickHouse)
└── routers/
    ├── changes.py              # /changes API (hybrid PostgreSQL/ClickHouse)
    └── websocket.py            # /ws/changes real-time notifications

services/timeseries-writer/
├── app/
│   ├── rabbitmq_consumer.py    # Consumes change_events queue
│   ├── clickhouse_client.py    # Writes to change_events table
│   └── postgres_sync.py        # Workload sync to PostgreSQL
└── main.py                     # Added change_events consumer

deployment/kubernetes-manifests/
├── 18-change-detection-worker.yaml  # Worker deployment
└── 08-clickhouse.yaml               # Added change_events table

schemas/
└── clickhouse-change-events.sql     # ClickHouse schema
```

### Key Configuration (Environment Variables)
| Variable | Default | Description |
|----------|---------|-------------|
| `RUN_BASED_FILTERING_ENABLED` | `true` | Run-based filtering UI |
| `CHANGE_EVENTS_CONSUMER_ENABLED` | `true` | ClickHouse consumer (timeseries-writer) |
| `WORKLOAD_SYNC_ENABLED` | `true` | Sync workloads to PostgreSQL |

**Note:** Change events are stored exclusively in ClickHouse. PostgreSQL is used only for metadata.

---

## Yeni Eklenen Dosyalar (Kasım 2024)

### timeseries-query Microservice
```
services/timeseries-query/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration (pydantic-settings)
│   └── query_engine.py    # ClickHouse query logic
├── main.py                # FastAPI application
├── requirements.txt
└── Dockerfile
```

### Analysis Orchestrator Query Clients
```
services/analysis-orchestrator/app/
├── timeseries_query_client.py  # HTTP client for timeseries-query
└── graph_query_client.py       # HTTP client for graph-query
```

### Pipeline Updates
```
pipelines/scripts/
└── build-timeseries-query.sh   # Build script

pipelines/classic-build/
├── detect-changes/task.sh      # Added TIMESERIES_QUERY_CHANGED
└── build-microservices/task.sh # Added timeseries-query build

pipelines/classic-release/
└── deploy-microservices/task.sh # Added timeseries-query deploy
```

### Kubernetes Manifests
```
deployment/kubernetes-manifests/
├── 03-configmaps.yaml          # Added TIMESERIES_QUERY_URL
├── 13-analysis-orchestrator.yaml # Added query service URLs
└── 17-timeseries-query.yaml    # NEW: Deployment + Service
```

---

## Cluster Connectivity Architecture (December 2025)

### ClusterConnectionManager

Unified entry point for all cluster operations. Abstracts away connection type differences.

```
┌─────────────────────────────────────────────────────────────────┐
│               ClusterConnectionManager                           │
│  - Connection pooling (Dict[int, ClusterConnection])             │
│  - Auto-detect: in-cluster vs remote                             │
│  - Fernet credential decryption                                  │
│  - Background health monitoring                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   InClusterConnection    │    │  RemoteTokenConnection   │
│   (gRPC to cluster-mgr)  │    │  (Direct K8s API)        │
└──────────────────────────┘    └──────────────────────────┘
```

### Files

| File | Purpose |
|------|---------|
| `services/cluster_connection_manager.py` | Central manager |
| `services/connections/base.py` | Abstract ClusterConnection |
| `services/connections/in_cluster.py` | In-cluster via gRPC |
| `services/connections/remote_token.py` | Remote via token |
| `services/health/cluster_health_monitor.py` | Background health checks |

---

## Mimari Prensipler

1. **Separation of Concerns**: Read (query) ve Write (writer) servisleri ayrı
2. **Database Abstraction**: Backend doğrudan DB'ye erişmez, query service'ler üstünden
3. **Consistent Pattern**: Neo4j için graph-query, ClickHouse için timeseries-query
4. **Horizontal Scaling**: Query service'ler bağımsız scale edilebilir
5. **Fault Tolerance**: Microservice arızası diğerlerini etkilemez
6. **Unified Cluster Access**: Tüm cluster erişimi ClusterConnectionManager üzerinden
7. **Hybrid Storage**: PostgreSQL (ACID) + ClickHouse (Analytics) for Change Detection 🆕
8. **Dual-Write Pattern**: Critical data written to both stores simultaneously 🆕
9. **Analysis Lifecycle Retention**: Data deleted with analysis (no TTL) 🆕

---

*Last Updated: January 2026*
*Architecture Version: 2.0 (Hybrid Change Detection)*

