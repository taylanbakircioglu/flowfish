# 🐟 Flowfish - Microservice İsimlendirme

## Service İsimleri

| Service | Kubernetes Name | Container Name | Port | Description |
|---------|----------------|----------------|------|-------------|
| **API Gateway** | `flowfish-api` | `api-gateway` | 8000 | REST API Gateway - Frontend interface |
| **Cluster Manager** | `flowfish-cluster-mgr` | `cluster-manager` | 5001 | K8s/OpenShift cluster management |
| **Analysis Orchestrator** | `flowfish-orchestrator` | `analysis-orchestrator` | 5002 | Analysis lifecycle & scheduling |
| **Ingestion Service** | `flowfish-ingestion` | `ingestion-worker` | 5003 | eBPF data collection from Inspektor Gadget |
| **ClickHouse Writer** | `flowfish-writer` | `clickhouse-writer` | 5005 | RabbitMQ → ClickHouse stream writer |
| **Dependency Graph** | `flowfish-graph` | `dependency-graph` | 5004 | Neo4j interface & graph queries |
| **Change Detection Worker** | `change-detection-worker` | `change-worker` | 8001 | Periodic change detection (scalable with leader election) |

---

## Worker İsimleri

### Ingestion Service (Data Collector Worker)
**Önerilen İsim:** `flowfish-ingestion`

**Alternatifler:**
- ❌ `flowfish-collector` (çok genel)
- ❌ `flowfish-data-collector` (çok uzun)
- ❌ `flowfish-gadget-worker` (implementation detayı)
- ✅ **`flowfish-ingestion`** (kısa, açık, mikroservis mimarisinde standart)

**Açıklama:**  
"Ingestion" terimi, streaming data architectures'da gelen veriyi kabul edip işleme sokan bileşenleri ifade eder. Kafka Ingestion, Stream Ingestion gibi kullanımlar yaygındır.

---

### ClickHouse Writer (Stream Writer)
**Önerilen İsim:** `flowfish-writer`

**Alternatifler:**
- ❌ `flowfish-clickhouse-writer` (çok uzun, implementation detayı)
- ❌ `flowfish-sink` (çok genel, belirsiz)
- ❌ `flowfish-stream-writer` (orta seviye ama redundant)
- ✅ **`flowfish-writer`** (kısa, açık, ne yaptığı belli)

**Açıklama:**  
"Writer" terimi, streaming mimarilerinde veriyi son hedefine yazan bileşenleri ifade eder. Clickhouse Writer, Kafka Writer gibi kullanımlar yaygındır.

---

## Kubernetes Deployment İsimlendirme

```yaml
# Ingestion Service
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flowfish-ingestion
  namespace: flowfish
  labels:
    app: flowfish
    component: ingestion
    tier: worker
spec:
  selector:
    matchLabels:
      app: flowfish
      component: ingestion
  template:
    metadata:
      labels:
        app: flowfish
        component: ingestion
        tier: worker
    spec:
      containers:
      - name: ingestion-worker
        image: flowfish/ingestion:latest
        ports:
        - name: grpc
          containerPort: 5003
```

```yaml
# ClickHouse Writer
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flowfish-writer
  namespace: flowfish
  labels:
    app: flowfish
    component: writer
    tier: worker
spec:
  selector:
    matchLabels:
      app: flowfish
      component: writer
  template:
    metadata:
      labels:
        app: flowfish
        component: writer
        tier: worker
    spec:
      containers:
      - name: clickhouse-writer
        image: flowfish/writer:latest
        ports:
        - name: grpc
          containerPort: 5005
```

---

## Service Discovery (Internal DNS)

Kubernetes içinde servisler birbiriyle DNS üzerinden iletişim kurar:

```
flowfish-api.flowfish.svc.cluster.local:8000
flowfish-cluster-mgr.flowfish.svc.cluster.local:5001
flowfish-orchestrator.flowfish.svc.cluster.local:5002
flowfish-ingestion.flowfish.svc.cluster.local:5003
flowfish-graph.flowfish.svc.cluster.local:5004
flowfish-writer.flowfish.svc.cluster.local:5005
change-detection-worker.flowfish.svc.cluster.local:8001
```

Kısa isim kullanımı (aynı namespace içinde):
```
flowfish-api:8000
flowfish-cluster-mgr:5001
flowfish-orchestrator:5002
flowfish-ingestion:5003
flowfish-graph:5004
flowfish-writer:5005
change-detection-worker:8001
```

---

## Docker Image İsimlendirme

```bash
# Public Docker Hub
docker.io/flowfish/api-gateway:v1.0.0
docker.io/flowfish/cluster-manager:v1.0.0
docker.io/flowfish/analysis-orchestrator:v1.0.0
docker.io/flowfish/ingestion:v1.0.0
docker.io/flowfish/writer:v1.0.0
docker.io/flowfish/dependency-graph:v1.0.0

# Private Registry
registry.example.com/flowfish/api-gateway:v1.0.0
registry.example.com/flowfish/cluster-manager:v1.0.0
# ...
```

---

## Environment Variables

Her servis için standart environment variables:

```bash
# Common
SERVICE_NAME=flowfish-ingestion
SERVICE_PORT=5003
LOG_LEVEL=info
ENVIRONMENT=production

# gRPC
GRPC_PORT=5003
GRPC_MAX_WORKERS=10

# Database connections
POSTGRES_URL=postgresql://flowfish:***@postgresql:5432/flowfish
CLICKHOUSE_URL=http://clickhouse:8123
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://flowfish:***@rabbitmq:5672/

# Service dependencies
API_GATEWAY_URL=flowfish-api:8000
CLUSTER_MANAGER_URL=flowfish-cluster-mgr:5001
ORCHESTRATOR_URL=flowfish-orchestrator:5002
```

---

## Logging & Monitoring Labels

Prometheus metrics ve logging için standart labels:

```yaml
labels:
  app: flowfish
  component: ingestion  # api, cluster-mgr, orchestrator, ingestion, writer, graph
  tier: worker          # frontend, api, worker, database
  version: v1.0.0
  environment: production
```

Prometheus metrics endpoint:
```
http://flowfish-ingestion:5003/metrics
http://flowfish-writer:5005/metrics
```

---

### Change Detection Worker (Scalable Background Worker)
**Önerilen İsim:** `change-detection-worker`

**Özellikler:**
- ✅ Standalone microservice (ayrı Pod olarak çalışır)
- ✅ Horizontally scalable (leader election ile)
- ✅ Redis-based leader election for HA
- ✅ Health checks: `/health`, `/ready`, `/metrics`

**Port:** 8001 (HTTP)

**Açıklama:**  
Change Detection Worker, periyodik olarak altyapı değişikliklerini tespit eden scalable bir worker'dır. PostgreSQL ve Neo4j'den veri okuyarak workload/connection değişikliklerini, risk seviyelerini ve blast radius'u hesaplar.

---

## Karar

✅ **Ingestion Service:** `flowfish-ingestion`  
✅ **ClickHouse Writer:** `flowfish-writer`

Bu isimler:
- Kısa ve kolay hatırlanır
- Mikroservis standartlarına uygun
- Kubernetes DNS friendly
- Implementation detaylarını gizler (flexibility)
- Streaming data architecture terminolojisiyle uyumlu

