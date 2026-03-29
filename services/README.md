# Flowfish Microservices

Bu dizin Flowfish platformunun mikroservis uygulamalarını içerir.

## Servisler

### 1. Ingestion Service (`ingestion-service/`)
**Port:** 5000 (gRPC)

**Sorumluluklar:**
- Inspektor Gadget'tan gelen eBPF verilerini toplar (gRPC stream)
- Network flow, DNS query, TCP connection eventlerini parse eder
- Event'leri protobuf formatına dönüştürür
- RabbitMQ exchange'lerine publish eder

**Dependencies:**
- RabbitMQ (event publishing)

**Teknoloji:**
- Python 3.11
- gRPC (async)
- aio-pika (async RabbitMQ client)
- uvloop (performans)

---

### 2. Timeseries Writer (`timeseries-writer/`)
**Sorumluluklar:**
- RabbitMQ kuyruklarından event'leri consume eder
- Batch/bulk insert için buffer yönetir
- ClickHouse'a time-series data yazar (11 event tipi)
- Change events'leri ClickHouse'a yazar 🆕
- Workload metadata'yı PostgreSQL'e sync eder 🆕

**Event Types:**
- network_flows, dns_queries, tcp_lifecycle
- process_events, file_operations, capability_checks
- oom_kills, bind_events, sni_events, mount_events
- **change_events** (from Change Detection Worker) 🆕
- **workload_metadata** (from Ingestion Service) 🆕

**Dependencies:**
- RabbitMQ (event consumption)
- ClickHouse (data storage)
- PostgreSQL (workload sync) 🆕

**Teknoloji:**
- Python 3.11
- aio-pika (async RabbitMQ consumer)
- clickhouse-driver (async ClickHouse client)
- psycopg2-binary (PostgreSQL sync) 🆕
- uvloop (performans)

---

### 2.4. Change Detection Worker (`backend/worker_main.py`) 🆕
**Port:** 8001 (Health)

**Sorumluluklar:**
- Kubernetes workload ve connection değişikliklerini periyodik olarak tespit eder
- Değişiklikleri PostgreSQL'e kaydeder (ACID)
- Değişiklikleri RabbitMQ'ya publish eder (analytics için)
- WebSocket ile real-time bildirimler
- Leader election ile HA desteği (Redis)
- Circuit breaker pattern ile resilience

**Change Types:**
- workload_added, workload_removed, workload_updated
- connection_added, connection_removed
- port_changed, namespace_changed

**Dependencies:**
- PostgreSQL (change_events, change_workflow)
- RabbitMQ (change_events exchange)
- Redis (leader election)
- Neo4j (blast radius calculation)

**Teknoloji:**
- Python 3.11
- FastAPI (health endpoints)
- SQLAlchemy (PostgreSQL)
- aio-pika (RabbitMQ)
- Redis (leader election)

**Configuration:**
| Variable | Default | Description |
|----------|---------|-------------|
| `CHANGE_DETECTION_ENABLED` | `true` | Enable detection |
| `CHANGE_DETECTION_INTERVAL` | `60` | Detection interval (seconds) |
| `LEADER_ELECTION_ENABLED` | `false` | HA mode with Redis |

**Note:** Change events are published to RabbitMQ and consumed by timeseries-writer for ClickHouse storage.

---

### 2.5. Timeseries Query (`timeseries-query/`)
**Port:** 8002 (HTTP)

**Sorumluluklar:**
- ClickHouse'tan event verilerini sorgular
- Backend için database-agnostic query API sağlar
- Aggregation ve pagination desteği
- graph-query ile aynı pattern'ı takip eder

**Endpoints:**
- `GET /health` - Health check
- `GET /events/stats` - Event statistics
- `GET /events` - All events with filtering
- `GET /events/{type}` - Specific event type query

**Dependencies:**
- ClickHouse (data source)

**Teknoloji:**
- Python 3.11
- FastAPI
- clickhouse-driver
- httpx

---

### 3. Cluster Orchestrator (`cluster-orchestrator/`)
**Port:** 5001 (gRPC)

**Sorumluluklar:**
- Kubernetes/OpenShift cluster yönetimi
- Cluster bağlantı bilgileri saklama (kubeconfig, service account token)
- Cluster health check
- Namespace, deployment, pod listeleme
- Inspektor Gadget endpoint yönetimi

**Dependencies:**
- PostgreSQL (cluster metadata)
- Kubernetes API

**Teknoloji:**
- Python 3.11
- gRPC
- SQLAlchemy (async)
- kubernetes-client

**API:**
- `CreateCluster()`
- `GetCluster()`
- `ListClusters()`
- `DeleteCluster()`
- `PerformHealthCheck()`

---

### 4. Analysis Processor (`analysis-processor/`)
**Port:** 5002 (gRPC)

**Sorumluluklar:**
- Analiz lifecycle yönetimi
- Analiz tanımlarını saklar (wizard output)
- Scheduled analysis execution (APScheduler)
- Analysis execution history
- Analysis result summary

**Analysis Types:**
- Dependency Mapping
- Change Detection
- Anomaly Detection
- Baseline Creation
- Risk Assessment

**Dependencies:**
- PostgreSQL (analysis definitions & runs)
- NebulaGraph (graph queries)
- ClickHouse (time-series queries)
- Cluster Manager (cluster info)

**Teknoloji:**
- Python 3.11
- gRPC
- SQLAlchemy (async)
- APScheduler (cron scheduling)

**API:**
- `CreateAnalysis()`
- `GetAnalysis()`
- `ListAnalyses()`
- `DeleteAnalysis()`
- `ExecuteAnalysis()`
- `GetAnalysisHistory()`

---

### 5. API Proxy (`api-proxy/`)
**Port:** 8000 (HTTP/REST)

**Sorumluluklar:**
- Frontend için REST API gateway
- Authentication & authorization (JWT)
- gRPC servislerine proxy
- Request/response transformation (gRPC ↔ REST)
- CORS handling
- OpenAPI/Swagger documentation

**Dependencies:**
- Cluster Manager (gRPC)
- Analysis Orchestrator (gRPC)
- PostgreSQL (user data, sessions)

**Teknoloji:**
- Python 3.11
- FastAPI
- Uvicorn
- gRPC clients
- Pydantic (validation)
- Prometheus metrics

**Endpoints:**
- `GET /api/v1/health` - Health check
- `GET /api/v1/docs` - Swagger UI
- `/api/v1/clusters/*` - Cluster management
- `/api/v1/analyses/*` - Analysis management

---

## Deployment

Her servis için:
- **Dockerfile:** Container image build
- **requirements.txt:** Python dependencies
- **Kubernetes manifests:** `deployment/kubernetes-manifests/`

## Development

### Proto Generation
```bash
./scripts/generate_proto.sh
```

### Local Development
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
cd services/<service-name>
pip install -r requirements.txt

# Run service
python main.py
```

### Build Docker Images
```bash
cd services/<service-name>
docker build -t flowfish/<service-name>:latest .
```

## Architecture (Updated 2024)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                               │
│                           Port: 3000 (HTTP)                                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ REST API
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND (FastAPI)                                 │
│                           Port: 8000 (HTTP)                                 │
│  Routers: events, communications, analyses, clusters, export, changes      │
└────────────┬─────────────────────┬─────────────────────┬────────────────────┘
             │                     │                     │
             │ gRPC                │ HTTP                │ HTTP
             ▼                     ▼                     ▼
┌────────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  Cluster Manager   │  │  timeseries-     │  │     graph-query      │
│    Port: 5001      │  │     query        │  │     Port: 8001       │
│  (gRPC)            │  │   Port: 8002     │  │     (HTTP)           │
└────────┬───────────┘  │   (HTTP) 🆕      │  └──────────┬───────────┘
         │              └────────┬─────────┘             │
         │                       │                       │
         ▼                       ▼                       ▼
┌────────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│   PostgreSQL       │  │    ClickHouse    │  │       Neo4j          │
│   (Metadata)       │  │   (TimeSeries)   │  │      (Graph)         │
│    Port: 5432      │  │    Port: 9000    │  │    Port: 7687        │
└────────────────────┘  └──────────────────┘  └──────────────────────┘
                                 ▲
                                 │ Bulk Write
┌────────────────────────────────┴──────────────────────────────────────────┐
│                                                                           │
│  ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────────┐  │
│  │  Analysis        │───▶│    Ingestion     │───▶│    RabbitMQ         │  │
│  │  Orchestrator    │    │    Service       │    │    (Queue)          │  │
│  │  Port: 5002      │    │    Port: 5000    │    │    Port: 5672       │  │
│  └────────┬─────────┘    └──────────────────┘    └──────────┬──────────┘  │
│           │                                                  │            │
│           │                                                  ▼            │
│           │              ┌───────────────────┐    ┌─────────────────────┐  │
│           └─────────────▶│    graph-writer   │    │ timeseries-writer   │  │
│                          │    Port: 5005     │    │ (RabbitMQ Consumer) │  │
│                          └─────────┬─────────┘    └──────────┬──────────┘  │
│                                    │                         │            │
│                                    ▼                         ▼            │
│                          ┌──────────────────┐     ┌──────────────────┐    │
│                          │      Neo4j       │     │    ClickHouse    │    │
│                          └──────────────────┘     └──────────────────┘    │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

**READ Path (Frontend → DB):**
```
Frontend → Backend → timeseries-query → ClickHouse (Events)
Frontend → Backend → graph-query → Neo4j (Graph)
Frontend → Backend → PostgreSQL (Metadata)
Frontend → Backend → /changes → ClickHouse (change_events)
Frontend → Backend → /ws/changes → Real-time notifications 🆕
```

**WRITE Path (Inspector Gadget → DB):**
```
Inspector Gadget → Ingestion Service → RabbitMQ → timeseries-writer → ClickHouse
Inspector Gadget → Ingestion Service → RabbitMQ → graph-writer → Neo4j
```

**WRITE Path (Change Detection → DB):** 🆕
```
Change Detection Worker ──┬──► PostgreSQL (ACID, workflow)
                          └──► RabbitMQ → timeseries-writer → ClickHouse (analytics)
```

## Monitoring

Her servis:
- **Health checks:** Liveness & readiness probes
- **Prometheus metrics:** `/metrics` endpoint
- **Structured logging:** JSON format

## Security

- **Non-root containers:** Tüm servisler non-root user olarak çalışır
- **Network policies:** Pod-to-pod iletişim kontrolü
- **Secrets:** Hassas bilgiler Kubernetes secrets'da
- **RBAC:** Service account permissions

## 🏗️ Current Architecture (Enterprise)

**10 Core Microservices:**

| # | Service | Port | Protocol | Responsibility |
|---|---------|------|----------|----------------|
| 1 | **api-gateway** | 8000 | HTTP | REST API Gateway, Auth, Routing |
| 2 | **ingestion-service** | 5000 | gRPC | eBPF data ingestion via kubectl gadget |
| 3 | **timeseries-writer** | - | RabbitMQ | ClickHouse bulk writer + change events |
| 4 | **timeseries-query** | 8002 | HTTP | ClickHouse query service |
| 5 | **graph-writer** | 5005 | RabbitMQ | Neo4j dependency builder |
| 6 | **graph-query** | 8001 | HTTP | Neo4j query service |
| 7 | **cluster-manager** | 5001 | gRPC | Kubernetes cluster management |
| 8 | **analysis-orchestrator** | 5002 | gRPC | Analysis lifecycle + Gadget lifecycle |
| 9 | **backend** | 8000 | HTTP | REST API, WebSocket, ChangeDetectionService |
| 10 | **change-detection-worker** | 8001 | HTTP | Periodic change detection (ClickHouse) |

**Removed (Future Phase 2):**
- ❌ notification-service → Moved to Phase 2
- ❌ baseline-service → Moved to Phase 2

## 🔄 Storage Architecture

### Database Usage Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE FLOW DIAGRAM                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                              WRITE PATH                                      │   │
│  │                                                                               │   │
│  │  kubectl-gadget → ingestion-service → RabbitMQ                               │   │
│  │                                          │                                    │   │
│  │                          ┌───────────────┼───────────────┐                   │   │
│  │                          ▼               ▼               ▼                   │   │
│  │                  timeseries-writer   graph-writer   (metadata)               │   │
│  │                          │               │               │                   │   │
│  │                          ▼               ▼               ▼                   │   │
│  │                    ┌──────────┐   ┌──────────┐   ┌──────────┐               │   │
│  │                    │ClickHouse│   │  Neo4j   │   │PostgreSQL│               │   │
│  │                    │ (events) │   │ (graph)  │   │(metadata)│               │   │
│  │                    └──────────┘   └──────────┘   └──────────┘               │   │
│  │                                                                               │   │
│  │  CHANGE DETECTION (Dual-Write) 🆕                                            │   │
│  │  change-detection-worker ────┬──────► PostgreSQL (change_events, workflow)  │   │
│  │                              └──────► RabbitMQ → timeseries-writer           │   │
│  │                                                          │                   │   │
│  │                                                          ▼                   │   │
│  │                                                    ClickHouse               │   │
│  │                                                   (change_events)           │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                              READ PATH                                       │   │
│  │                                                                               │   │
│  │  frontend → backend                                                          │   │
│  │                │                                                             │   │
│  │       ┌────────┼────────┬────────────────┬────────────────┐                 │   │
│  │       ▼        ▼        ▼                ▼                ▼                 │   │
│  │  timeseries- graph-  cluster-      analysis-       /changes                 │   │
│  │    query     query   manager       orchestrator    (ClickHouse)             │   │
│  │       │        │        │                │             │                    │   │
│  │       ▼        ▼        ▼         ┌──────┴──────┐     │                    │   │
│  │  ClickHouse  Neo4j  PostgreSQL    │             │     │                    │   │
│  │                                timeseries-   graph-    │                    │   │
│  │                                  query       query     │                    │   │
│  │                                    │           │       │                    │   │
│  │                                    ▼           ▼       ▼                    │   │
│  │                                ClickHouse   Neo4j   PostgreSQL              │   │
│  │                                                     + ClickHouse            │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**ClickHouse (Time-Series):**
- High-volume event data (millions/day)
- Analytics & aggregations
- Historical queries

**NebulaGraph (Graph DB):**
- Real-time dependency graph
- Path finding & topology
- Impact analysis

📖 See: [`docs/architecture/HYBRID_STORAGE_ARCHITECTURE.md`](../docs/architecture/HYBRID_STORAGE_ARCHITECTURE.md)

## 🚀 Recent Improvements

### Analysis Orchestrator Enhancement
- ✅ **Inspector Gadget Lifecycle Management** added
- ✅ `gadget_client.py`: Start/stop eBPF traces
- ✅ `analysis_stopper.py`: Clean stop with stats
- ✅ Integration with analysis execution flow

### Data Flow
```
Analysis START → Gadget.StartTrace() → eBPF Collection → RabbitMQ → ClickHouse/Neo4j
Analysis STOP  → Gadget.StopTrace() → Stream Ends → Cleanup Complete
```

### Query Flow (NEW)
```
Frontend Request → Backend Router → EventService/CommService
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
          TimeseriesQueryEventRepository              GraphQueryClient
                    │                                           │
                    ▼ HTTP                                      ▼ HTTP
          timeseries-query:8002                      graph-query:8001
                    │                                           │
                    ▼                                           ▼
              ClickHouse                                     Neo4j
```

### Analysis Orchestrator Integration (NEW)
```
Analysis Orchestrator uses:
├── timeseries_query_client.py → timeseries-query:8002 → ClickHouse
│   └── For: anomaly_detection, change_detection, baseline_creation, risk_assessment
│
└── graph_query_client.py → graph-query:8001 → Neo4j
    └── For: dependency_mapping, change_detection, baseline_creation, risk_assessment
```
