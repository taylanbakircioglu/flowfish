# Flowfish - Deployment Architecture

## Overview

Flowfish is an eBPF-based Kubernetes observability platform with a microservices architecture.
This document describes the deployment topology and component relationships.

## Microservices Architecture

```
                                    ┌─────────────┐
                                    │   Nginx      │ :30080 (K8s) / :80 (Prod)
                                    │   Proxy      │
                                    └──────┬───────┘
                              ┌────────────┴────────────┐
                              ▼                         ▼
                     ┌──────────────┐          ┌──────────────┐
                     │   Frontend   │          │   Backend    │
                     │   (React)    │ :3000    │   (FastAPI)  │ :8000
                     └──────────────┘          └──────┬───────┘
                                                      │
              ┌───────────┬───────────┬───────────┬───┴───────┬────────────┐
              ▼           ▼           ▼           ▼           ▼            ▼
     ┌──────────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
     │  Cluster     │ │Analysis│ │Ingest. │ │ Change │ │  Graph   │ │Timeseries│
     │  Manager     │ │Orchest.│ │Service │ │Detect. │ │  Query   │ │  Query   │
     │  (gRPC)      │ │        │ │        │ │Worker  │ │          │ │          │
     └──────┬───────┘ └────────┘ └────┬───┘ └────────┘ └──────────┘ └──────────┘
            │  :5001      :5002       │ :5000    :8001      :8001       :8002
            │                         │
            ▼                         ▼
     ┌──────────────┐          ┌──────────────┐
     │  Kubernetes  │          │  RabbitMQ    │ :5672
     │  API Server  │          └──────┬───────┘
     └──────────────┘                 │
                              ┌───────┴───────┐
                              ▼               ▼
                     ┌──────────────┐ ┌──────────────┐
                     │ Graph Writer │ │  Timeseries  │
                     │              │ │   Writer     │
                     └──────┬───────┘ └──────┬───────┘
                            │                │
              ┌─────────────┼────────────────┼─────────────┐
              ▼             ▼                ▼             ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────┐
     │  PostgreSQL  │ │    Neo4j     │ │  ClickHouse  │ │ Redis  │
     │              │ │   (Graph)    │ │ (Timeseries) │ │(Cache) │
     └──────────────┘ └──────────────┘ └──────────────┘ └────────┘
         :5432            :7687            :8123           :6379
```

## Component Summary

| Component | Image | Port | Purpose |
|-----------|-------|------|---------|
| Frontend | `flowfish:frontend-latest` | 3000 | React UI |
| Backend | `flowfish:backend-latest` | 8000 | FastAPI main API |
| Cluster Manager | `flowfish:cluster-manager-latest` | 5001 | gRPC gateway for K8s API |
| Analysis Orchestrator | `flowfish:analysis-orchestrator-latest` | 5002 | Analysis lifecycle management |
| Ingestion Service | `flowfish:ingestion-service-latest` | 5000 | eBPF data collection via Inspektor Gadget |
| Graph Query | `flowfish:graph-query-latest` | 8001 | Neo4j graph queries |
| Graph Writer | `flowfish:graph-writer-latest` | - | RabbitMQ consumer -> Neo4j |
| Timeseries Query | `flowfish:timeseries-query-latest` | 8002 | ClickHouse time-series queries |
| Timeseries Writer | `flowfish:timeseries-writer-latest` | - | RabbitMQ consumer -> ClickHouse |
| Change Detection Worker | `flowfish:change-worker-latest` | 8001 | Change event detection & analysis |
| Nginx Proxy | `nginx:alpine` | 30080 | Reverse proxy / load balancer |

## Databases

| Database | Image | Port | Purpose |
|----------|-------|------|---------|
| PostgreSQL | `postgres:15-alpine` | 5432 | Core data (users, clusters, analyses) |
| ClickHouse | `clickhouse/clickhouse-server:23` | 8123/9000 | eBPF event time-series storage |
| Neo4j | `neo4j:5.15-community` | 7687/7474 | Service dependency graph |
| Redis | `redis:7-alpine` | 6379 | Caching and session management |
| RabbitMQ | `rabbitmq:3-management-alpine` | 5672/15672 | Message queue for event processing |

## Deployment Options

### 1. Kubernetes / K3s (Recommended)

Pre-built manifests in `local-test/` directory. All images are pulled from Docker Hub.

```bash
# One-line install
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/local-test/deploy.sh | bash
```

### 2. Docker Compose

```bash
docker compose up -d                    # Standard setup
docker compose -f docker-compose.local-test.yml up -d  # Full local test
```

### 3. Production Kubernetes / OpenShift

Production manifests are in `deployment/kubernetes-manifests/` with pipeline variable placeholders.
These are deployed via Azure DevOps pipelines with environment-specific configurations.

## Deployment Order

### Local / K3s

```
00-namespace.yaml          # Namespace
01-rbac.yaml               # ServiceAccount, ClusterRole, ClusterRoleBinding
02-databases.yaml          # PostgreSQL, ClickHouse, Redis, Neo4j, RabbitMQ
03-migrations.yaml         # Database schema + RabbitMQ exchanges/queues (Job)
04-backend.yaml            # Backend API
05-cluster-manager.yaml    # Cluster Manager (gRPC)
06-analysis-orchestrator   # Analysis Orchestrator
07-ingestion-service.yaml  # Ingestion Service
08-graph-query.yaml        # Graph Query Service
09-timeseries-query.yaml   # Timeseries Query Service
10-graph-writer.yaml       # Graph Writer (RabbitMQ consumer)
11-timeseries-writer.yaml  # Timeseries Writer (RabbitMQ consumer)
12-change-detection.yaml   # Change Detection Worker
13-frontend.yaml           # Frontend UI
14-nginx-proxy.yaml        # Nginx reverse proxy (NodePort 30080)
```

### Production

Manifests numbered 01-19 with `{{VARIABLE}}` placeholders, applied via CI/CD pipeline.

## Data Flow

1. **Collection**: Ingestion Service triggers Inspektor Gadget to collect eBPF events
2. **Queuing**: Events published to RabbitMQ exchanges (network_flows, dns_queries, tcp_connections)
3. **Processing**: Graph Writer and Timeseries Writer consume from queues
4. **Storage**: Graph Writer -> Neo4j, Timeseries Writer -> ClickHouse
5. **Query**: Graph Query and Timeseries Query serve read requests
6. **API**: Backend aggregates data from all services
7. **UI**: Frontend displays dashboards, topology maps, and analysis results

## CI/CD

Docker images are built and pushed to Docker Hub via GitHub Actions on every push to `main`:

- **Registry**: `taylanbakircioglu/flowfish`
- **Tags**: `{service}-latest` and `{service}-{date}-{sha}`
- **Architecture**: linux/amd64

## Access Points

| Environment | URL | Notes |
|-------------|-----|-------|
| Local K8s | `http://localhost:30080` | NodePort via nginx-proxy |
| Docker Compose | `http://localhost:3000` (UI), `http://localhost:8000` (API) | Direct port mapping |
| Production | Via Ingress/Route | Configured per environment |

## Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Flowfish UI | admin | admin123 |
| PostgreSQL | flowfish | flowfish123 |
| ClickHouse | flowfish | flowfish123 |
| Neo4j | neo4j | flowfish123 |
| Redis | - | redis123 |
| RabbitMQ | flowfish | flowfish123 |

---

**Last Updated**: March 2026
