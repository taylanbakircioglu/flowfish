# 🐟 Flowfish - Microservice Naming

## Service Names

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

## Worker Names

### Ingestion Service (Data Collector Worker)
**Recommended name:** `flowfish-ingestion`

**Alternatives:**
- ❌ `flowfish-collector` (too generic)
- ❌ `flowfish-data-collector` (too long)
- ❌ `flowfish-gadget-worker` (implementation detail)
- ✅ **`flowfish-ingestion`** (short, clear, standard in microservice architecture)

**Explanation:**  
The term "Ingestion" refers to components that accept incoming data and feed it into processing in streaming data architectures. Uses like Kafka Ingestion and Stream Ingestion are common.

---

### ClickHouse Writer (Stream Writer)
**Recommended name:** `flowfish-writer`

**Alternatives:**
- ❌ `flowfish-clickhouse-writer` (too long, implementation detail)
- ❌ `flowfish-sink` (too generic, vague)
- ❌ `flowfish-stream-writer` (middling but redundant)
- ✅ **`flowfish-writer`** (short, clear, obvious role)

**Explanation:**  
The term "Writer" refers to components that write data to the final destination in streaming architectures. Uses like Clickhouse Writer and Kafka Writer are common.

---

## Kubernetes Deployment Naming

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

Inside Kubernetes, services talk to each other over DNS:

```
flowfish-api.flowfish.svc.cluster.local:8000
flowfish-cluster-mgr.flowfish.svc.cluster.local:5001
flowfish-orchestrator.flowfish.svc.cluster.local:5002
flowfish-ingestion.flowfish.svc.cluster.local:5003
flowfish-graph.flowfish.svc.cluster.local:5004
flowfish-writer.flowfish.svc.cluster.local:5005
change-detection-worker.flowfish.svc.cluster.local:8001
```

Short names (same namespace):
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

## Docker Image Naming

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

Standard environment variables per service:

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

Standard labels for Prometheus metrics and logging:

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
**Recommended name:** `change-detection-worker`

**Characteristics:**
- ✅ Standalone microservice (runs as its own Pod)
- ✅ Horizontally scalable (with leader election)
- ✅ Redis-based leader election for HA
- ✅ Health checks: `/health`, `/ready`, `/metrics`

**Port:** 8001 (HTTP)

**Explanation:**  
Change Detection Worker is a scalable worker that periodically detects infrastructure changes. It reads from PostgreSQL and Neo4j to compute workload/connection changes, risk levels, and blast radius.

---

## Decision

✅ **Ingestion Service:** `flowfish-ingestion`  
✅ **ClickHouse Writer:** `flowfish-writer`

These names are:
- Short and easy to remember
- Aligned with microservice conventions
- Kubernetes DNS friendly
- Hide implementation details (flexibility)
- Consistent with streaming data architecture terminology
