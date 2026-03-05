# Flowfish - Kubernetes Deployment Architecture

## 🎯 Overview

This document describes the Kubernetes/OpenShift deployment architecture for Flowfish platform.

## 📦 Component Deployment

### Namespace Organization

```
flowfish/                    # Main application namespace
├── frontend                 # React UI
├── backend                  # FastAPI application
├── change-detection-worker  # Scalable change detection worker
├── postgresql              # Relational database
├── redis                   # Cache
├── clickhouse              # Time-series database
└── neo4j                   # Graph database (bolt:7687, http:7474)

gadget/                      # Inspektor Gadget namespace
└── inspektor-gadget        # eBPF data collection DaemonSet
```

## 🏗️ Resource Requirements

### Minimum (Development/Test)

| Component | Pods | CPU Request | Memory Request | Storage |
|-----------|------|-------------|----------------|---------|
| Frontend | 1 | 100m | 256Mi | - |
| Backend | 1 | 500m | 1Gi | - |
| Change Detection Worker | 1 | 100m | 256Mi | - |
| PostgreSQL | 1 | 500m | 2Gi | 20Gi |
| Redis | 1 | 250m | 512Mi | - |
| ClickHouse | 1 | 1000m | 4Gi | 50Gi |
| Neo4j (total) | 6 | 3000m | 10Gi | 50Gi |
| Inspektor Gadget | 1/node | 100m | 256Mi | - |
| **Total** | **13+** | **5.6** cores | **18.5Gi** | **120Gi** |

### Production

| Component | Pods | CPU Request | Memory Request | Storage |
|-----------|------|-------------|----------------|---------|
| Frontend | 2-5 | 100m | 256Mi | - |
| Backend | 3-10 | 500m | 1Gi | - |
| Change Detection Worker | 1-3 (with leader election) | 100m | 256Mi | - |
| PostgreSQL | 2 (1+1 replica) | 2000m | 8Gi | 200Gi SSD |
| Redis | 3 (1+2 replica) | 500m | 2Gi | - |
| ClickHouse | 6 (3+3 replica) | 4000m | 16Gi | 1TB SSD |
| Neo4j | 14 (2+2+6+4) | 20000m | 80Gi | 500Gi SSD |
| Inspektor Gadget | 1/node | 100m | 256Mi | - |
| **Total** | **32+** | **31.3+** cores | **116+Gi** | **1.7+TB** |

## 📋 Deployment Order

The manifests should be applied in this order:

```bash
# 1. Namespace and RBAC
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-rbac.yaml

# 2. ConfigMaps and Secrets
kubectl apply -f 03-configmaps.yaml
kubectl apply -f 04-secrets.yaml

# 3. Databases (StatefulSets)
kubectl apply -f 05-postgres.yaml
kubectl apply -f 06-redis.yaml
kubectl apply -f 07-clickhouse.yaml
kubectl apply -f 07-neo4j.yaml
kubectl apply -f 08-neo4j-init.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish --timeout=300s
kubectl wait --for=condition=ready pod -l app=clickhouse -n flowfish --timeout=300s
kubectl wait --for=condition=ready pod -l app=neo4j -n flowfish --timeout=300s

# 4. Application
kubectl apply -f 09-backend.yaml
kubectl apply -f 10-frontend.yaml

# Wait for application
kubectl wait --for=condition=ready pod -l app=backend -n flowfish --timeout=300s

# 5. Inspektor Gadget
kubectl apply -f 11-inspektor-gadget.yaml

# 6. Change Detection Worker (Scalable)
kubectl apply -f 18-change-detection-worker.yaml

# Wait for worker
kubectl wait --for=condition=ready pod -l app=change-detection-worker -n flowfish --timeout=120s

# 7. Ingress
kubectl apply -f 12-ingress.yaml
```

## 🔐 Security

### Pod Security Standards

All pods run with restricted security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 2000
  seccompProfile:
    type: RuntimeDefault
  
  # Container level
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true  # where possible
  capabilities:
    drop:
    - ALL
```

### Network Policies

Default deny-all ingress policy with explicit allow rules:

```yaml
# Default deny
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
spec:
  podSelector: {}
  policyTypes:
  - Ingress
```

Specific allow policies for each component pair.

## 📊 High Availability

### Frontend
- **Replicas**: 2 minimum
- **Update Strategy**: RollingUpdate (maxSurge: 1, maxUnavailable: 0)
- **Readiness Probe**: HTTP GET /
- **Liveness Probe**: HTTP GET /
- **Anti-Affinity**: Spread across nodes

### Backend
- **Replicas**: 3 minimum
- **Update Strategy**: RollingUpdate (maxSurge: 1, maxUnavailable: 0)
- **Readiness Probe**: HTTP GET /api/v1/health
- **Liveness Probe**: HTTP GET /api/v1/health
- **Anti-Affinity**: Spread across nodes
- **PodDisruptionBudget**: minAvailable: 2

### PostgreSQL
- **Architecture**: Master + Replica (using Patroni/Stolon)
- **Replication**: Streaming replication
- **Failover**: Automatic
- **Backup**: pg_dump + WAL archiving to object storage

### ClickHouse
- **Architecture**: 3 shards × 2 replicas
- **Replication**: ZooKeeper-coordinated
- **Sharding**: By cluster_id
- **Distributed Tables**: Automatic query distribution

### Neo4j
- **Graphd**: 2 replicas (stateless, load balanced)
- **Metad**: 2 replicas (Raft consensus)
- **Storaged**: 3 partitions × 2 replicas (Raft consensus)
- **Replication Factor**: 3 for critical data

### Redis
- **Architecture**: Sentinel (1 master + 2 replicas)
- **Failover**: Automatic via Sentinel
- **Persistence**: RDB + AOF

### Change Detection Worker
- **Architecture**: Standalone microservice (separate from backend)
- **Replicas**: 1 (single) or 1-3+ (with leader election)
- **Scaling**: Horizontal with Redis-based leader election
- **Communication**: HTTP to backend for WebSocket notifications
- **Health Checks**: /health, /ready, /metrics endpoints
- **Deployment**: `18-change-detection-worker.yaml`

#### Single Instance Mode (Default)
```yaml
LEADER_ELECTION_ENABLED=false
Replicas: 1
```

#### Multi-Instance Mode (High Availability)
```yaml
LEADER_ELECTION_ENABLED=true
Replicas: 3
```
Only the leader instance performs detection; others are standby.

## 🔄 Auto-Scaling

### Horizontal Pod Autoscaler (HPA)

**Frontend**:
```yaml
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

**Backend**:
```yaml
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
```

### Vertical Pod Autoscaler (VPA)

Recommended for databases:
- PostgreSQL: updateMode: "Off" (recommendations only)
- ClickHouse: updateMode: "Off"
- Redis: updateMode: "Auto"

## 💾 Persistent Storage

### Storage Classes

```yaml
# SSD for databases (recommended)
kind: StorageClass
apiVersion: storage.k8s.io/v1
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs  # or appropriate for your cloud
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
allowVolumeExpansion: true
```

### Persistent Volume Claims

| Component | Size (Min) | Size (Prod) | Storage Class |
|-----------|------------|-------------|---------------|
| PostgreSQL | 20Gi | 200Gi | fast-ssd |
| ClickHouse (per node) | 50Gi | 500Gi | fast-ssd |
| Neo4j Metad | 10Gi | 50Gi | fast-ssd |
| Neo4j Storaged | 50Gi | 200Gi | fast-ssd |

### Backup Strategy

**PostgreSQL**:
- Daily full backup (pg_dump)
- Continuous WAL archiving
- Retention: 30 days
- Storage: S3/Azure Blob/GCS

**ClickHouse**:
- Snapshot-based backups
- Retention: 90 days
- Backup to object storage

**Neo4j**:
- SNAPSHOT command for full backup
- Retention: 30 days

## 🌐 Ingress Configuration

### Nginx Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: flowfish-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - flowfish.example.com
    secretName: flowfish-tls
  rules:
  - host: flowfish.example.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 3000
```

## 📈 Monitoring

### Prometheus Metrics

All components expose Prometheus metrics:

- Frontend: `/metrics` (via nginx-prometheus-exporter)
- Backend: `/api/v1/metrics`
- PostgreSQL: postgres_exporter sidecar
- ClickHouse: Built-in `/metrics`
- Neo4j: Built-in metrics endpoint
- Redis: redis_exporter sidecar

### Service Monitors

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: flowfish-backend
spec:
  selector:
    matchLabels:
      app: backend
  endpoints:
  - port: http
    path: /api/v1/metrics
    interval: 30s
```

## 🚀 Deployment Strategies

### Blue-Green Deployment

Use separate namespaces:
- `flowfish-blue` (current production)
- `flowfish-green` (new version)

Switch traffic via Ingress update.

### Canary Deployment

Use traffic splitting:
```yaml
# Argo Rollouts example
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    canary:
      steps:
      - setWeight: 10
      - pause: {duration: 5m}
      - setWeight: 50
      - pause: {duration: 5m}
      - setWeight: 100
```

## 🔧 Maintenance

### Database Migrations

```bash
# Backend migration job
kubectl apply -f jobs/migration-job.yaml
kubectl wait --for=condition=complete job/migration --timeout=300s
```

### Rolling Updates

```bash
# Update backend image
kubectl set image deployment/backend \
  backend=flowfish/backend:v2.0.0 \
  -n flowfish

# Monitor rollout
kubectl rollout status deployment/backend -n flowfish

# Rollback if needed
kubectl rollout undo deployment/backend -n flowfish
```

---

**Version**: 1.0.0  
**Last Updated**: January 2025

