# Flowfish Architecture - Simple Overview

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 FLOWFISH DATA FLOW                                   │
│                        eBPF-Based Kubernetes Observability                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────┐
                                    │    USER     │
                                    │  (Browser)  │
                                    └──────┬──────┘
                                           │ HTTP
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                              frontend                                        │    │
│  │                         (React + TypeScript)                                 │    │
│  │                                                                              │    │
│  │   Dashboard │ Clusters │ Analysis Wizard │ Live Map │ Alerts                │    │
│  └──────────────────────────────────────┬──────────────────────────────────────┘    │
│                                          │ REST API                                  │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                               backend                                        │    │
│  │                         (FastAPI + Python)                                   │    │
│  │                                                                              │    │
│  │   Auth │ Cluster CRUD │ Analysis API │ Query Proxy                          │    │
│  └──────────────────────────────────────┬──────────────────────────────────────┘    │
│                                          │ gRPC                                      │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                        analysis-orchestrator                                 │    │
│  │                         (gRPC Server + Python)                               │    │
│  │                                                                              │    │
│  │   Analysis Lifecycle │ Task Distribution │ State Management                 │    │
│  └──────────────────────────────────────┬──────────────────────────────────────┘    │
│                                          │ gRPC                                      │
│  ┌───────────────────────────────────────┼──────────────────────────────────────┐   │
│  │                        cluster-manager│                                       │   │
│  │                     (gRPC Server :5003)                                       │   │
│  │                                       │                                       │   │
│  │   K8s API → Namespaces, Pods, Deployments, Labels (Cluster-wide access)      │   │
│  └───────────────────────────────────────┼──────────────────────────────────────┘   │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                         ingestion-service                                    │    │
│  │                         (gRPC Server + Python)                               │    │
│  │                                                                              │    │
│  │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │    │
│  │   │  Trace Manager  │ ─► │  gRPC CLIENT    │ ─► │ RabbitMQ Pub    │        │    │
│  │   │  (Lifecycle)    │    │  (to Gadget)    │    │ (Event Publish) │        │    │
│  │   └─────────────────┘    └────────┬────────┘    └────────┬────────┘        │    │
│  └───────────────────────────────────┼─────────────────────┼───────────────────┘    │
│                                       │                     │                        │
└───────────────────────────────────────┼─────────────────────┼────────────────────────┘
                                        │                     │
                                        │ gRPC (Pull Events)  │ AMQP (Publish)
                                        ▼                     ▼
┌───────────────────────────────────────────────┐  ┌──────────────────────────────────┐
│           TARGET CLUSTER                       │  │           rabbitmq               │
│  ┌─────────────────────────────────────────┐  │  │        (Message Queue)           │
│  │          inspektor-gadget               │  │  │                                  │
│  │           (DaemonSet)                    │  │  │  flowfish.events.network ───┐   │
│  │                                          │  │  │  flowfish.events.dns    ───┼─► │
│  │   eBPF Programs → gRPC Server (:16060)  │  │  │  flowfish.events.tcp    ───┘   │
│  │                                          │  │  │                                  │
│  │   Events: network, dns, tcp, process    │  │  └──────────────┬───────────────────┘
│  └─────────────────────────────────────────┘  │                  │
└───────────────────────────────────────────────┘                  │ AMQP (Consume)
                                                                   │
                                                    ┌──────────────┴──────────────┐
                                                    │                             │
                                                    ▼                             ▼
                                  ┌─────────────────────────────┐  ┌─────────────────────────────┐
                                  │     timeseries-writer       │  │      graph-writer           │
                                  │    (RabbitMQ Consumer)      │  │    (RabbitMQ Consumer)      │
                                  │                             │  │                             │
                                  │  Batch Events → ClickHouse  │  │  Build Graph → Neo4j       │
                                  └──────────────┬──────────────┘  └──────────────┬──────────────┘
                                                 │                                │
                                                 ▼                                ▼
                                  ┌─────────────────────────────┐  ┌─────────────────────────────┐
                                  │         clickhouse          │  │           neo4j             │
                                  │    (Time-Series Database)   │  │     (Graph Database)        │
                                  │                             │  │                             │
                                  │  Tables:                    │  │  Nodes: Pod, Service, NS    │
                                  │   • network_flows           │  │  Edges: COMMUNICATES_WITH   │
                                  │   • dns_queries             │  │         BELONGS_TO          │
                                  │   • tcp_connections         │  │         DEPENDS_ON          │
                                  └──────────────┬──────────────┘  └──────────────┬──────────────┘
                                                 │                                │
                                                 └────────────────┬───────────────┘
                                                                  │ Query
                                                                  ▼
                                                    ┌─────────────────────────────┐
                                                    │        graph-query          │
                                                    │     (Query Service)         │
                                                    │                             │
                                                    │  Dependency Graph Queries   │
                                                    └──────────────┬──────────────┘
                                                                   │ gRPC
                                                                   ▼
                                                    ┌─────────────────────────────┐
                                                    │          backend            │
                                                    │      (Query Results)        │
                                                    └──────────────┬──────────────┘
                                                                   │ REST
                                                                   ▼
                                                    ┌─────────────────────────────┐
                                                    │         frontend            │
                                                    │      (Live Map / Dashboard) │
                                                    └─────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
                              KEY COMMUNICATION PATTERNS
═══════════════════════════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  PROTOCOL       │ SOURCE              │ TARGET               │ DIRECTION        │
  ├─────────────────┼─────────────────────┼──────────────────────┼──────────────────┤
  │  REST/HTTP      │ frontend            │ backend              │ Request/Response │
  │  gRPC           │ backend             │ analysis-orchestrator│ Request/Response │
  │  gRPC           │ analysis-orchestrator│ ingestion-service   │ Request/Response │
  │  gRPC           │ ingestion-service   │ inspektor-gadget     │ Stream (PULL)    │
  │  AMQP           │ ingestion-service   │ rabbitmq             │ Publish          │
  │  AMQP           │ rabbitmq            │ timeseries-writer    │ Consume          │
  │  AMQP           │ rabbitmq            │ graph-writer         │ Consume          │
  │  TCP/Native     │ timeseries-writer   │ clickhouse           │ Batch Insert     │
  │  Bolt           │ graph-writer        │ neo4j                │ Cypher Queries   │
  │  gRPC           │ backend             │ graph-query          │ Request/Response │
  └─────────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                                 CRITICAL POINT
═══════════════════════════════════════════════════════════════════════════════════════

  ⚠️  ingestion-service Gadget'a CLIENT olarak bağlanır!
  
      Inspektor Gadget → gRPC SERVER (sadece API sunar, hiçbir yere push yapmaz)
      ingestion-service → gRPC CLIENT (Gadget'tan event ÇEKER)
      ingestion-service → RabbitMQ'ya PUBLISH eder
      
      Bu mimari sayesinde:
      ✓ Gadget lightweight kalır (sadece eBPF + gRPC server)
      ✓ Decouple - Queue failure Gadget'ı etkilemez
      ✓ Backpressure - ingestion-service rate control yapabilir
      ✓ Multi-cluster - Farklı cluster'lara farklı protokollerle bağlanılabilir

```

## Service Summary

| Pod Name | Port | Role | Technology |
|----------|------|------|------------|
| frontend | 3000 | Web UI | React, TypeScript, Ant Design |
| backend | 8000 | REST API Gateway | FastAPI, Python |
| change-detection-worker | 8001 | Change Detection (Scalable) | FastAPI, Python |
| analysis-orchestrator | 5002 | Analysis Lifecycle | gRPC, Python |
| cluster-manager | 5003 | Cluster Connections | gRPC, Python |
| ingestion-service | 5000 | Event Collection | gRPC, Python |
| timeseries-writer | - | ClickHouse Writer | Python, pika |
| graph-writer | - | Neo4j Writer | Python, aio_pika |
| graph-query | 8001 | Graph Queries | REST, Python |
| inspektor-gadget | 16060 | eBPF Data Source | DaemonSet, gRPC |
| rabbitmq | 5672 | Message Queue | RabbitMQ |
| clickhouse | 9000 | Time-Series DB | ClickHouse |
| neo4j | 7687 | Graph DB | Neo4j |
| postgresql | 5432 | Metadata DB | PostgreSQL |
| redis | 6379 | Cache (+ Leader Election) | Redis |

