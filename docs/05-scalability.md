# Flowfish - Ölçeklenebilirlik Yaklaşımı

## 🎯 Genel Bakış

Flowfish platformu, küçük test ortamlarından büyük enterprise production ortamlarına kadar ölçeklenebilir mimari ile tasarlanmıştır.

---

## 📏 Ölçeklenebilirlik Hedefleri

### Desteklenen Boyutlar

| Metrik | Minimum (Test) | Orta (Production) | Maksimum (Enterprise) |
|--------|----------------|-------------------|----------------------|
| **Clusters** | 1 | 5-10 | 50+ |
| **Namespaces/Cluster** | 10 | 100 | 500+ |
| **Pods/Cluster** | 100 | 10,000 | 50,000+ |
| **Communications/Day** | 100K | 10M | 1B+ |
| **Real-time Graph Nodes** | 500 | 2,000 | 10,000 |
| **Concurrent Users** | 10 | 100 | 1,000+ |
| **Data Retention** | 30 days | 90 days | 365 days |

---

## 🏗️ Horizontal Scaling Stratejisi

### 1. Application Layer Scaling

#### Frontend (React)

**Stateless Replicas**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: 3  # Base replicas
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

**Horizontal Pod Autoscaler (HPA)**:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: frontend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: frontend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Scaling Behavior**:
- Traffic spike → CPU > 70% → Scale up
- Idle time → CPU < 30% → Scale down (after 5 min)
- Load balancing: Kubernetes Service + Ingress

#### Backend (FastAPI)

**Stateless Replicas**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 5  # Base replicas
```

**HPA Configuration**:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
```

**Connection Pooling**:
- Database connection pool: 20 connections/pod
- Total connections: replicas × 20
- Example: 10 replicas = 200 connections

---

### 2. Data Layer Scaling

#### PostgreSQL (İlişkisel Veri)

**Master-Replica Architecture**:
```
┌─────────────────────────────────────────┐
│                                         │
│  Backend Pods                           │
│  (Write: Master, Read: Replicas)        │
│                                         │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
   ┌───▼────┐      ┌────▼───┐
   │ Master │──────│Replica │
   │  (R/W) │      │  (R)   │
   └────────┘      └────────┘
                        │
                   ┌────▼───┐
                   │Replica │
                   │  (R)   │
                   └────────┘
```

**Scaling Strategies**:

**Vertical Scaling**:
- CPU: 1 → 4 → 8 cores
- Memory: 4GB → 16GB → 32GB
- Storage: SSD required (IOPS critical)

**Read Replicas**:
- 1 master + N replicas
- Read queries → replicas (load balanced)
- Write queries → master only
- Streaming replication latency: <1 second

**Connection Pooling** (PgBouncer):
```
Backend (500 pods) → PgBouncer (100 connections) → PostgreSQL (20 connections)
```

**Partitioning** (Large Tables):
```sql
-- Time-based partitioning for audit_logs
CREATE TABLE audit_logs (
    id BIGSERIAL,
    created_at TIMESTAMP,
    ...
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_logs_2024_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

#### ClickHouse (Time-Series Veri)

**Distributed Architecture**:

```
┌──────────────────────────────────────────────────┐
│          Distributed Table (Query Layer)         │
└──────────────┬───────────────────────────────────┘
               │
       ┌───────┼───────────┐
       │       │           │
   ┌───▼───┐ ┌─▼─────┐ ┌──▼────┐
   │Shard 1│ │Shard 2│ │Shard 3│
   │       │ │       │ │       │
   │Replica│ │Replica│ │Replica│
   └───┬───┘ └───┬───┘ └───┬───┘
       │         │         │
   ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
   │Replica│ │Replica│ │Replica│
   └───────┘ └───────┘ └───────┘
```

**Sharding Strategy**:
- **Sharding Key**: `cluster_id` (cluster bazlı dağıtım)
- **Shard Count**: 3-6 shards (production)
- **Replication Factor**: 2 (her shard için 2 replica)

**Example Configuration**:
```xml
<remote_servers>
    <flowfish_cluster>
        <shard>
            <replica>
                <host>clickhouse-01</host>
                <port>9000</port>
            </replica>
            <replica>
                <host>clickhouse-01-replica</host>
                <port>9000</port>
            </replica>
        </shard>
        <shard>
            <replica>
                <host>clickhouse-02</host>
                <port>9000</port>
            </replica>
            <replica>
                <host>clickhouse-02-replica</host>
                <port>9000</port>
            </replica>
        </shard>
    </flowfish_cluster>
</remote_servers>
```

**Query Distribution**:
- Query → Distributed table → Parallel execution on shards → Merge results
- Network_flows table: 1B rows → 3 shards → ~333M rows/shard

**Materialized Views** (Pre-aggregation):
```sql
-- Hourly aggregation reduces query load
CREATE MATERIALIZED VIEW network_flows_hourly
ENGINE = SummingMergeTree()
AS SELECT ...
```

#### Neo4j (Graph Veritabanı)

**Multi-Node Architecture**:

```
┌──────────────────────────────────────────┐
│  Graph Service (Graphd) - Stateless      │
│  ┌────────┐  ┌────────┐  ┌────────┐     │
│  │Graphd-1│  │Graphd-2│  │Graphd-3│     │
│  └────┬───┘  └────┬───┘  └────┬───┘     │
└───────┼──────────┼──────────┼───────────┘
        │          │          │
┌───────┼──────────┼──────────┼───────────┐
│       │  Meta Service (Metad) - Raft    │
│  ┌────▼───┐  ┌──▼─────┐  ┌──▼──────┐   │
│  │Metad-1 │  │Metad-2 │  │Metad-3  │   │
│  └────┬───┘  └────┬───┘  └────┬────┘   │
└───────┼──────────┼──────────┼───────────┘
        │          │          │
┌───────┼──────────┼──────────┼───────────┐
│       │  Storage Service (Storaged)     │
│  ┌────▼───┐  ┌──▼─────┐  ┌──▼──────┐   │
│  │Storage │  │Storage │  │Storage  │   │
│  │  -1    │  │  -2    │  │  -3     │   │
│  └────┬───┘  └────┬───┘  └────┬────┘   │
│       │          │          │           │
│  ┌────▼───┐  ┌──▼─────┐  ┌──▼──────┐   │
│  │Replica │  │Replica │  │Replica  │   │
│  └────────┘  └────────┘  └────────┘   │
└──────────────────────────────────────────┘
```

**Scaling Components**:

**Graphd (Query Layer)**:
- Stateless → Horizontal scaling
- Load balancer distributes queries
- 2-5 instances (production)

**Metad (Metadata Service)**:
- Raft consensus (3 or 5 nodes)
- Leader election for HA
- Stores schema, partition info

**Storaged (Data Storage)**:
- Partitioned by vertex ID
- Replication factor: 3
- Horizontal scaling: Add more storage nodes
- Data redistribution: Automatic rebalancing

**Partition Strategy**:
- **Partition Count**: 100 partitions (default)
- **Rebalancing**: Automatic when nodes added/removed

#### Redis (Cache)

**Cluster Mode** (High Scale):

```
┌─────────────────────────────────────────┐
│          Redis Cluster                  │
│                                         │
│  Master-1  →  Replica-1                │
│  Master-2  →  Replica-2                │
│  Master-3  →  Replica-3                │
│                                         │
│  Hash Slots: 0-16383                   │
│  Automatic sharding by key hash        │
└─────────────────────────────────────────┘
```

**Alternative: Sentinel** (Medium Scale):

```
┌─────────────────────────────────────────┐
│       Redis Sentinel (HA)               │
│                                         │
│  Master  ←→  Replica-1                 │
│    ↕          ↕                         │
│  Sentinel-1  Sentinel-2  Sentinel-3   │
│                                         │
│  Automatic Failover                     │
└─────────────────────────────────────────┘
```

---

### 3. Caching Strategy

#### Multi-Layer Caching

**Layer 1: Browser Cache** (Frontend)
- Service Worker cache
- IndexedDB for offline support
- TTL: 5 minutes

**Layer 2: Redis Cache** (Backend)
- Hot data (frequently accessed)
- TTL: 5-15 minutes

**Layer 3: Database** (Persistent)
- Source of truth
- No TTL

#### Cache Patterns

**Cache-Aside**:
```python
def get_workload(workload_id):
    # 1. Check cache
    cached = redis.get(f"workload:{workload_id}")
    if cached:
        return json.loads(cached)
    
    # 2. Cache miss → DB query
    workload = postgres.query("SELECT * FROM workloads WHERE id = %s", workload_id)
    
    # 3. Store in cache
    redis.setex(f"workload:{workload_id}", 300, json.dumps(workload))
    
    return workload
```

**Write-Through**:
```python
def update_workload(workload_id, data):
    # 1. Update database
    postgres.update("UPDATE workloads SET ... WHERE id = %s", workload_id, data)
    
    # 2. Update cache
    redis.setex(f"workload:{workload_id}", 300, json.dumps(data))
```

**Cache Invalidation**:
- Time-based: TTL expiration
- Event-based: Pub/Sub notifications
- Pattern-based: Delete by key pattern

---

### 4. Data Collection Scaling

#### Inspektor Gadget (DaemonSet)

**Per-Node Resource Usage**:
- CPU: 100m (0.1 core)
- Memory: 256 MB
- Network: Minimal (local processing)

**Cluster-Wide Scaling**:
- 100 nodes × 0.1 core = 10 cores total
- 100 nodes × 256 MB = 25.6 GB total
- Automatic: DaemonSet scales with cluster

#### Data Ingestion Pipeline

```
eBPF Events → Collector → Enricher → Database
(100K/s)      (Buffer)    (Batch)    (Bulk Insert)
```

**Buffering**:
- In-memory buffer: 10K events
- Flush interval: 5 seconds
- Back-pressure handling: Drop oldest events

**Batching**:
- Batch size: 1000 records
- Bulk insert to ClickHouse
- Async processing (no blocking)

**Throughput Calculation**:
- 1 event = ~500 bytes
- 100K events/s = 50 MB/s
- Daily data: 50 MB/s × 86400 = 4.3 TB/day
- With compression (10x): ~430 GB/day

---

## 📊 Performance Targets

### Response Time SLAs

| Endpoint | Target (p95) | Max (p99) |
|----------|--------------|-----------|
| `/auth/login` | 200ms | 500ms |
| `/clusters` (list) | 100ms | 300ms |
| `/workloads` (list) | 200ms | 500ms |
| `/dependencies/graph` | 500ms | 1000ms |
| `/anomalies` (list) | 150ms | 400ms |

### Throughput Targets

| Operation | Target |
|-----------|--------|
| API Requests | 10,000 req/s |
| WebSocket Connections | 1,000 concurrent |
| eBPF Events Ingestion | 100,000 events/s |
| Graph Queries | 100 queries/s |
| Dashboard Loads | 500 concurrent users |

---

## 🔄 Auto-Scaling Triggers

### Metrics-Based Scaling

**CPU-Based**:
```
IF avg(cpu_usage) > 70% FOR 2 minutes THEN
    scale_up(25%)
END IF

IF avg(cpu_usage) < 30% FOR 5 minutes THEN
    scale_down(1 pod)
END IF
```

**Memory-Based**:
```
IF avg(memory_usage) > 80% FOR 2 minutes THEN
    scale_up(25%)
END IF
```

**Custom Metrics** (KEDA):
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: backend-scaler
spec:
  scaleTargetRef:
    name: backend
  minReplicaCount: 3
  maxReplicaCount: 20
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: api_request_rate
      threshold: '1000'
      query: sum(rate(http_requests_total[1m]))
```

---

## 💾 Storage Optimization

### Data Retention Policies

| Data Type | Hot Storage | Cold Storage | Archive | Delete |
|-----------|-------------|--------------|---------|--------|
| Network flows | 7 days | 30 days | 90 days | 90+ days |
| Communications | 30 days | 90 days | 365 days | Never |
| Anomalies | 90 days | 180 days | 365 days | Never |
| Audit logs | 90 days | 365 days | 7 years | 7+ years |

### Compression

**ClickHouse**:
- CODEC(DoubleDelta, LZ4) for timestamps
- Compression ratio: 10-20x
- 1 TB raw → 50-100 GB compressed

**PostgreSQL**:
- TOAST for large JSONB
- Vacuum for space reclaim

---

## 🌍 Multi-Region Deployment (Future)

### Active-Active Setup

```
┌──────────────┐      ┌──────────────┐
│   US-East    │◄────►│   EU-West    │
│              │      │              │
│  - Backend   │      │  - Backend   │
│  - Frontend  │      │  - Frontend  │
│  - Databases │      │  - Databases │
└──────────────┘      └──────────────┘
        ▲                     ▲
        │                     │
     Users (US)           Users (EU)
```

**Data Replication**:
- PostgreSQL: Logical replication (async)
- ClickHouse: Distributed tables (cross-region)
- Neo4j: Multi-datacenter setup

---

## 📈 Monitoring Scaling

### Key Metrics

- **Pod Count**: Track replica count over time
- **Resource Usage**: CPU, memory, disk per pod
- **Request Rate**: Requests/second per endpoint
- **Error Rate**: 4xx/5xx responses
- **Latency**: p50, p95, p99 response times
- **Database Connections**: Active connections
- **Queue Depth**: Message queue depth
- **Cache Hit Ratio**: Redis cache effectiveness

---

**Versiyon**: 1.0.0  
**Son Güncelleme**: Ocak 2025

