# Flowfish Architecture - Detailed Technical Specification

## Table of Contents
1. [System Overview](#system-overview)
2. [Layer Architecture](#layer-architecture)
3. [Service Details](#service-details)
4. [Data Flow Sequences](#data-flow-sequences)
5. [Storage Strategy](#storage-strategy)
6. [Scalability Considerations](#scalability-considerations)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              FLOWFISH PLATFORM OVERVIEW                                  │
│                    Enterprise eBPF-Based Kubernetes Observability                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│   │                           PRESENTATION LAYER                                      │  │
│   │                                                                                    │  │
│   │   frontend (React)  ◄────── REST/JSON ──────►  backend (FastAPI)                 │  │
│   │        │                                              │                           │  │
│   │   • Dashboard                                    • Auth (JWT/RBAC)               │  │
│   │   • Cluster Management                           • Cluster CRUD                   │  │
│   │   • Analysis Wizard                              • Analysis API                   │  │
│   │   • Live Map (Cytoscape)                         • Query Proxy                    │  │
│   │   • Alerts & Reports                             • File Export                    │  │
│   └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                               │
│                                          │ gRPC                                          │
│                                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│   │                          ORCHESTRATION LAYER                                      │  │
│   │                                                                                    │  │
│   │   analysis-orchestrator          cluster-manager                                  │  │
│   │   (Port 5002)                    (Port 5003)                                      │  │
│   │        │                              │                                           │  │
│   │   • Analysis Start/Stop          • K8s API Access (ClusterRole)                  │  │
│   │   • Task Scheduling              • List Namespaces/Pods/Deployments              │  │
│   │   • State Machine                • Health Monitoring                              │  │
│   │   • Error Recovery               • Multi-Protocol Support                         │  │
│   └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                          │                                               │
│                                          │ gRPC                                          │
│                                          ▼                                               │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│   │                         DATA COLLECTION LAYER                                     │  │
│   │                                                                                    │  │
│   │   ingestion-service (Port 5000)                                                   │  │
│   │        │                                                                          │  │
│   │   • Trace Manager                                                                 │  │
│   │   • kubectl-gadget CLI for event collection                                      │  │
│   │   • Event Transformation & Normalization                                         │  │
│   │   • RabbitMQ Publisher                                                           │  │
│   │                                                                                    │  │
│   │   ┌─────────────────────────────────────────────────────────────────────────┐    │  │
│   │   │                    KUBECTL GADGET CLIENT                                 │    │  │
│   │   │                                                                          │    │  │
│   │   │   ┌────────────────────────────────────────────────────────────────┐   │    │  │
│   │   │   │ KubectlGadgetClient                                             │   │    │  │
│   │   │   │                                                                 │   │    │  │
│   │   │   │  • Subprocess: kubectl gadget trace_* --output=json            │   │    │  │
│   │   │   │  • JSON stream parsing                                          │   │    │  │
│   │   │   │  • Event normalization                                          │   │    │  │
│   │   │   └────────────────────────────────────────────────────────────────┘   │    │  │
│   │   │                                                                          │    │  │
│   │   └──────────────────────────────────────────────────────────────────────────┘    │  │
│   │                                      │                                            │  │
│   └──────────────────────────────────────┼────────────────────────────────────────────┘  │
│                                          │ kubectl gadget CLI                            │
└──────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                              TARGET CLUSTERS                                              │
│                                                                                           │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                        inspektor-gadget (DaemonSet)                                 │ │
│  │                                                                                      │ │
│  │  Inspektor Gadget v0.46.0+                                                          │ │
│  │                                                                                      │ │
│  │  eBPF Programs:                                                                     │ │
│  │   • trace_tcp, trace_dns, trace_exec, trace_open                                   │ │
│  │   • trace_capabilities, trace_oomkill, trace_bind                                  │ │
│  │   • trace_sni, trace_mount                                                         │ │
│  │                                                                                      │ │
│  │  Integration: kubectl-gadget CLI → JSON stdout                                      │ │
│  │  Platforms: Kubernetes 1.24+, OpenShift 4.12+                                       │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                LAYERED ARCHITECTURE                                      │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  LAYER 1: PRESENTATION                                                                  │
│  ════════════════════                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: frontend                                          POD: backend             │   │
│  │ ┌─────────────────────────────┐                ┌─────────────────────────────┐ │   │
│  │ │ React + TypeScript          │                │ FastAPI + Python            │ │   │
│  │ │ Ant Design Components       │    REST        │ Pydantic Schemas            │ │   │
│  │ │ Cytoscape.js (Graph)        │ ◄─────────────►│ JWT Authentication          │ │   │
│  │ │ Redux Toolkit (State)       │    JSON        │ RBAC Authorization          │ │   │
│  │ │ RTK Query (API)             │                │ Structlog (Logging)         │ │   │
│  │ └─────────────────────────────┘                └─────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                               │
│                                          │ gRPC (Protocol Buffers)                       │
│                                          ▼                                               │
│  LAYER 2: ORCHESTRATION                                                                 │
│  ══════════════════════                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: analysis-orchestrator                POD: cluster-manager                  │   │
│  │ ┌─────────────────────────────┐    ┌─────────────────────────────┐             │   │
│  │ │ gRPC Server (:5002)         │    │ gRPC Server (:5003)         │             │   │
│  │ │                             │    │                             │             │   │
│  │ │ AnalysisExecutor:           │    │ K8sClient:                  │             │   │
│  │ │  • StartAnalysis()          │    │  • ValidateConnection()     │             │   │
│  │ │  • StopAnalysis()           │    │  • ListNamespaces()         │             │   │
│  │ │  • GetStatus()              │    │  • ListDeployments()        │             │   │
│  │ │                             │    │  • GetPodLabels()           │             │   │
│  │ │ Scheduler:                  │    │                             │             │   │
│  │ │  • PeriodicTasks            │    │ HealthMonitor:              │             │   │
│  │ │  • BaselineComparison       │    │  • ClusterHealth            │             │   │
│  │ │                             │    │  • GadgetHealth             │             │   │
│  │ │ IngestionClient: ──────────────►│                             │             │   │
│  │ │  • StartCollection()        │    └─────────────────────────────┘             │   │
│  │ │  • StopCollection()         │                                                 │   │
│  │ └─────────────────────────────┘                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                               │
│                                          │ gRPC                                          │
│                                          ▼                                               │
│  LAYER 3: DATA COLLECTION                                                               │
│  ════════════════════════                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: ingestion-service                                                          │   │
│  │ ┌─────────────────────────────────────────────────────────────────────────────┐ │   │
│  │ │ gRPC Server (:5000)                                                         │ │   │
│  │ │                                                                              │ │   │
│  │ │ ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐       │ │   │
│  │ │ │   TraceManager    │  │  ClientFactory    │  │ RabbitMQPublisher │       │ │   │
│  │ │ │                   │  │                   │  │                   │       │ │   │
│  │ │ │ • StartCollection │  │ • KubectlClient   │  │ • publish()       │       │ │   │
│  │ │ │ • StopCollection  │  │   (subprocess)    │  │ • exchange:       │       │ │   │
│  │ │ │ • TraceSession    │  │                   │  │   flowfish.events │       │ │   │
│  │ │ └────────┬──────────┘  └────────┬──────────┘  └────────┬──────────┘       │ │   │
│  │ │          │                      │                       │                  │ │   │
│  │ │          │  ┌───────────────────┘                       │                  │ │   │
│  │ │          │  │                                           │                  │ │   │
│  │ │          ▼  ▼                                           ▼                  │ │   │
│  │ │   ┌─────────────────────────────┐        ┌─────────────────────────────┐  │ │   │
│  │ │   │ kubectl-gadget CLI          │        │ Event Publisher             │  │ │   │
│  │ │   │                             │        │                             │  │ │   │
│  │ │   │ subprocess: kubectl gadget  │────────┤ → flowfish.events.network  │  │ │   │
│  │ │   │   trace_tcp --output=json   │ Events │ → flowfish.events.dns      │  │ │   │
│  │ │   │                             │        │ → flowfish.events.tcp      │  │ │   │
│  │ │   │ • stdout JSON stream ───────┼────────┤ → flowfish.events.process  │  │ │   │
│  │ │   │ • Event parsing             │        │                             │  │ │   │
│  │ │   └─────────────────────────────┘        └─────────────────────────────┘  │ │   │
│  │ └─────────────────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                                │
│                                                        │ AMQP                           │
│                                                        ▼                                │
│  LAYER 4: MESSAGE QUEUE                                                                 │
│  ══════════════════════                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: rabbitmq-0 (StatefulSet)                                                   │   │
│  │ ┌─────────────────────────────────────────────────────────────────────────────┐ │   │
│  │ │                                                                              │ │   │
│  │ │  Exchange: flowfish.events (Topic)                                          │ │   │
│  │ │      │                                                                       │ │   │
│  │ │      ├── routing_key: flowfish.events.network → Queue: network_events      │ │   │
│  │ │      ├── routing_key: flowfish.events.dns     → Queue: dns_events          │ │   │
│  │ │      ├── routing_key: flowfish.events.tcp     → Queue: tcp_events          │ │   │
│  │ │      ├── routing_key: flowfish.events.process → Queue: process_events      │ │   │
│  │ │      └── routing_key: flowfish.events.#       → Queue: all_events (debug)  │ │   │
│  │ │                                                                              │ │   │
│  │ │  Features:                                                                   │ │   │
│  │ │   • Durable queues (persist on restart)                                     │ │   │
│  │ │   • Message acknowledgment (at-least-once)                                  │ │   │
│  │ │   • Dead letter queue (failed messages)                                     │ │   │
│  │ │   • Prefetch (backpressure control)                                         │ │   │
│  │ │                                                                              │ │   │
│  │ └─────────────────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                              │                                    │                     │
│                              │ AMQP (Consume)                     │ AMQP (Consume)      │
│                              ▼                                    ▼                     │
│  LAYER 5: STORAGE WRITERS                                                               │
│  ════════════════════════                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: timeseries-writer                    POD: graph-writer                     │   │
│  │ ┌─────────────────────────────┐    ┌─────────────────────────────┐             │   │
│  │ │ RabbitMQ Consumer           │    │ RabbitMQ Consumer           │             │   │
│  │ │                             │    │                             │             │   │
│  │ │ Queues:                     │    │ Queue:                      │             │   │
│  │ │  • network_events           │    │  • network_events           │             │   │
│  │ │  • dns_events               │    │                             │             │   │
│  │ │  • tcp_events               │    │ GraphBuilder:               │             │   │
│  │ │                             │    │  • ExtractNodes()           │             │   │
│  │ │ ClickHouseWriter:           │    │  • ExtractEdges()           │             │   │
│  │ │  • Batch (100 or 5sec)      │    │  • MergeRelationships()     │             │   │
│  │ │  • write_network_flows()    │    │                             │             │   │
│  │ │  • write_dns_queries()      │    │ Neo4jClient:                │             │   │
│  │ │  • write_tcp_connections()  │    │  • MERGE nodes              │             │   │
│  │ │                             │    │  • MERGE relationships      │             │   │
│  │ └──────────────┬──────────────┘    └──────────────┬──────────────┘             │   │
│  │                │                                   │                            │   │
│  └────────────────┼───────────────────────────────────┼────────────────────────────┘   │
│                   │                                   │                                 │
│                   ▼                                   ▼                                 │
│  LAYER 6: STORAGE                                                                       │
│  ═══════════════                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                  │   │
│  │  POD: clickhouse-0               POD: neo4j-0                POD: postgresql-0 │   │
│  │  ┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐       │   │
│  │  │ ClickHouse        │    │ Neo4j             │    │ PostgreSQL        │       │   │
│  │  │ (Time-Series)     │    │ (Graph)           │    │ (Metadata)        │       │   │
│  │  │                   │    │                   │    │                   │       │   │
│  │  │ Tables:           │    │ Nodes:            │    │ Tables:           │       │   │
│  │  │ • network_flows   │    │ • (:Pod)          │    │ • clusters        │       │   │
│  │  │ • dns_queries     │    │ • (:Service)      │    │ • analyses        │       │   │
│  │  │ • tcp_connections │    │ • (:Namespace)    │    │ • analysis_runs   │       │   │
│  │  │ • process_events  │    │ • (:Deployment)   │    │ • users           │       │   │
│  │  │                   │    │                   │    │ • namespaces      │       │   │
│  │  │ Features:         │    │ Relationships:    │    │ • workloads       │       │   │
│  │  │ • Columnar        │    │ • COMMUNICATES    │    │                   │       │   │
│  │  │ • Compression     │    │ • BELONGS_TO      │    │ Features:         │       │   │
│  │  │ • Partitioned     │    │ • DEPENDS_ON      │    │ • ACID            │       │   │
│  │  │ • TTL             │    │ • EXPOSES         │    │ • Transactions    │       │   │
│  │  └───────────────────┘    └───────────────────┘    └───────────────────┘       │   │
│  │                                                                                  │   │
│  │  POD: redis-0                                                                   │   │
│  │  ┌───────────────────┐                                                          │   │
│  │  │ Redis (Cache)     │                                                          │   │
│  │  │ • Session         │                                                          │   │
│  │  │ • Hot data cache  │                                                          │   │
│  │  │ • Rate limiting   │                                                          │   │
│  │  └───────────────────┘                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  LAYER 7: QUERY SERVICES                                                                │
│  ═══════════════════════                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │ POD: timeseries-query                          POD: graph-query                 │   │
│  │ ┌─────────────────────────────┐        ┌─────────────────────────────┐         │   │
│  │ │ REST API (:8002)            │        │ REST API (:8001)            │         │   │
│  │ │                             │        │                             │         │   │
│  │ │ Endpoints:                  │        │ Endpoints:                  │         │   │
│  │ │ • GET /events/stats         │        │ • GET /graph/dependencies   │         │   │
│  │ │ • GET /events               │        │ • GET /graph/impact         │         │   │
│  │ │ • GET /events/histogram     │        │                             │         │   │
│  │ │ • GET /events/{type}        │        │ • GET /graph/path           │         │   │
│  │ │ • GET /events/network       │        │ • GET /communications       │         │   │
│  │ │ • GET /events/dns           │        │                             │         │   │
│  │ │ • GET /events/process       │        │ GraphQueryEngine:           │         │   │
│  │ │ • DELETE /admin/analysis    │        │ • Neo4j Cypher queries      │         │   │
│  │ │                             │        │ • Result → JSON             │         │   │
│  │ │ TimeseriesQueryEngine:      │        │ • Caching (Redis)           │         │   │
│  │ │ • ClickHouse SQL queries    │        │                             │         │   │
│  │ │ • Pagination & filtering    │        │ Data Source:                │         │   │
│  │ │ • Aggregations              │        │ • Neo4j (Bolt :7687)        │         │   │
│  │ │                             │        │                             │         │   │
│  │ │ Data Source:                │        │ Used By:                    │         │   │
│  │ │ • ClickHouse (HTTP :8123)   │        │ • Backend (communications)  │         │   │
│  │ │                             │        │ • Analysis Orchestrator     │         │   │
│  │ │ Used By:                    │        │ • LiveMap.tsx, Map.tsx      │         │   │
│  │ │ • Backend (events API)      │        │                             │         │   │
│  │ │ • Analysis Orchestrator     │        │                             │         │   │
│  │ └─────────────────────────────┘        └─────────────────────────────┘         │   │
│  │              │                                        │                         │   │
│  │              ▼                                        ▼                         │   │
│  │         ClickHouse                                  Neo4j                       │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Service Details

### 3.1 Pod Summary Table

| Layer | Pod Name | Port | Protocol | Scaling | Description |
|-------|----------|------|----------|---------|-------------|
| Presentation | frontend | 3000 | HTTP | HPA | React UI - Dashboard, Wizard, Live Map |
| Presentation | backend | 8000 | HTTP | HPA | FastAPI - REST Gateway, Auth |
| Orchestration | analysis-orchestrator | 5002 | gRPC | Deployment | Analysis lifecycle management |
| Orchestration | cluster-manager | 5001 | gRPC | Deployment | Multi-cluster connections |
| Collection | ingestion-service | 5000 | gRPC | HPA | Event collection via kubectl-gadget |
| Queue | rabbitmq | 5672 | AMQP | StatefulSet | Message broker |
| Writer | timeseries-writer | - | AMQP | HPA | ClickHouse batch writer |
| Writer | graph-writer | - | AMQP | HPA | Neo4j graph builder |
| Query | timeseries-query | 8002 | HTTP | HPA | ClickHouse query service |
| Query | graph-query | 8001 | HTTP | HPA | Neo4j query service |
| eBPF | inspektor-gadget | - | CLI | DaemonSet | eBPF data source (kubectl-gadget) |
| Storage | clickhouse | 9000 | TCP | StatefulSet | Time-series database |
| Storage | neo4j | 7687 | Bolt | StatefulSet | Graph database |
| Storage | postgresql | 5432 | TCP | StatefulSet | Metadata database |
| Cache | redis | 6379 | TCP | StatefulSet | Caching layer |

---

## 4. Data Flow Sequences

### 4.1 Analysis Start Sequence

```
┌──────────┐    ┌──────────┐    ┌─────────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ frontend │    │ backend  │    │analysis-orchestrator│    │ ingestion-service│    │inspektor-gadget  │
└────┬─────┘    └────┬─────┘    └──────────┬──────────┘    └────────┬─────────┘    └────────┬─────────┘
     │               │                      │                        │                       │
     │ POST /analyses│                      │                        │                       │
     │──────────────►│                      │                        │                       │
     │               │                      │                        │                       │
     │               │ INSERT analyses      │                        │                       │
     │               │─────────────────────►│ PostgreSQL             │                       │
     │               │                      │                        │                       │
     │ 201 Created   │                      │                        │                       │
     │◄──────────────│                      │                        │                       │
     │               │                      │                        │                       │
     │ POST /analyses/1/start              │                        │                       │
     │──────────────►│                      │                        │                       │
     │               │                      │                        │                       │
     │               │ gRPC: StartAnalysis()│                        │                       │
     │               │─────────────────────►│                        │                       │
     │               │                      │                        │                       │
     │               │                      │ gRPC: StartCollection()│                       │
     │               │                      │───────────────────────►│                       │
     │               │                      │                        │                       │
     │               │                      │                        │ kubectl gadget trace  │
     │               │                      │                        │──────────────────────►│
     │               │                      │                        │                       │
     │               │                      │                        │ (JSON stdout stream)  │
     │               │                      │                        │──────────────────────►│
     │               │                      │                        │                       │
     │               │                      │                        │◄──────────────────────│
     │               │                      │                        │  Parse JSON events    │
     │               │                      │                        │                       │
     │               │                      │                        │ Publish to RabbitMQ   │
     │               │                      │                        │─────────────────────► │
     │               │                      │                        │                       │
     │               │                      │◄───────────────────────│ Session Started       │
     │               │                      │                        │                       │
     │               │◄─────────────────────│ Analysis Started       │                       │
     │               │                      │                        │                       │
     │ 200 OK        │                      │                        │                       │
     │◄──────────────│                      │                        │                       │
     │               │                      │                        │                       │
```

### 4.2 Event Processing Flow

```
┌──────────────────┐    ┌──────────────────┐    ┌────────────┐    ┌──────────────────┐    ┌────────────┐
│inspektor-gadget  │    │ ingestion-service│    │  rabbitmq  │    │timeseries-writer │    │ clickhouse │
└────────┬─────────┘    └────────┬─────────┘    └──────┬─────┘    └────────┬─────────┘    └──────┬─────┘
         │                       │                      │                   │                    │
         │ eBPF Event            │                      │                   │                    │
         │ (kernel level)        │                      │                   │                    │
         │──────────────────────►│                      │                   │                    │
         │                       │                      │                   │                    │
         │                       │ Transform Event      │                   │                    │
         │                       │ (add metadata)       │                   │                    │
         │                       │                      │                   │                    │
         │                       │ Publish              │                   │                    │
         │                       │─────────────────────►│                   │                    │
         │                       │  flowfish.events.    │                   │                    │
         │                       │  network             │                   │                    │
         │                       │                      │                   │                    │
         │                       │                      │ Consume           │                    │
         │                       │                      │──────────────────►│                    │
         │                       │                      │                   │                    │
         │                       │                      │                   │ Batch (100 events  │
         │                       │                      │                   │ or 5 sec timeout)  │
         │                       │                      │                   │                    │
         │                       │                      │                   │ INSERT INTO        │
         │                       │                      │                   │ network_flows      │
         │                       │                      │                   │───────────────────►│
         │                       │                      │                   │                    │
         │                       │                      │                   │◄───────────────────│
         │                       │                      │                   │    ACK             │
         │                       │                      │                   │                    │
         │                       │                      │◄──────────────────│ ACK messages       │
         │                       │                      │                   │                    │
```

### 4.3 Graph Building Flow (Neo4j)

```
┌──────────────────┐    ┌──────────────────┐    ┌────────────┐    ┌──────────────────┐    ┌────────────┐
│ ingestion-service│    │    rabbitmq      │    │graph-writer│    │      neo4j       │    │            │
└────────┬─────────┘    └────────┬─────────┘    └──────┬─────┘    └────────┬─────────┘    │            │
         │                       │                      │                   │              │            │
         │ Publish network event │                      │                   │              │            │
         │──────────────────────►│                      │                   │              │            │
         │  routing: flowfish.   │                      │                   │              │            │
         │  events.network       │                      │                   │              │            │
         │                       │                      │                   │              │            │
         │                       │ Consume from         │                   │              │            │
         │                       │ network_events queue │                   │              │            │
         │                       │─────────────────────►│                   │              │            │
         │                       │                      │                   │              │            │
         │                       │                      │ GraphBuilder:     │              │            │
         │                       │                      │ ExtractNodes()    │              │            │
         │                       │                      │  • source_pod     │              │            │
         │                       │                      │  • dest_pod       │              │            │
         │                       │                      │  • namespaces     │              │            │
         │                       │                      │                   │              │            │
         │                       │                      │ ExtractEdges()    │              │            │
         │                       │                      │  • COMMUNICATES   │              │            │
         │                       │                      │  • protocol, port │              │            │
         │                       │                      │  • bytes, count   │              │            │
         │                       │                      │                   │              │            │
         │                       │                      │ MERGE (:Pod)      │              │            │
         │                       │                      │───────────────────►│              │            │
         │                       │                      │                   │              │            │
         │                       │                      │ MERGE [:COMMUN.]  │              │            │
         │                       │                      │───────────────────►│              │            │
         │                       │                      │                   │              │            │
         │                       │                      │◄──────────────────│ ACK          │            │
         │                       │                      │                   │              │            │
         │                       │◄─────────────────────│ ACK message       │              │            │
         │                       │                      │                   │              │            │
```

### 4.4 Graph Query Flow (LiveMap/Map)

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────┐
│    frontend      │    │     backend      │    │   graph-query    │    │      neo4j       │    │   redis    │
│  (LiveMap.tsx)   │    │    (FastAPI)     │    │    (:8001)       │    │    (:7687)       │    │  (cache)   │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └──────┬─────┘
         │                       │                       │                       │                     │
         │ GET /communications/  │                       │                       │                     │
         │     graph?cluster=1   │                       │                       │                     │
         │──────────────────────►│                       │                       │                     │
         │                       │                       │                       │                     │
         │                       │ HTTP GET /graph/      │                       │                     │
         │                       │ dependencies          │                       │                     │
         │                       │──────────────────────►│                       │                     │
         │                       │                       │                       │                     │
         │                       │                       │ Check cache           │                     │
         │                       │                       │──────────────────────────────────────────────►│
         │                       │                       │                       │                     │
         │                       │                       │◄─────────────────────────────────────────────│
         │                       │                       │ Cache miss            │                     │
         │                       │                       │                       │                     │
         │                       │                       │ Cypher Query:         │                     │
         │                       │                       │ MATCH (p:Pod)-[c:     │                     │
         │                       │                       │ COMMUNICATES]->(t:Pod)│                     │
         │                       │                       │ WHERE p.cluster_id=1  │                     │
         │                       │                       │───────────────────────►│                     │
         │                       │                       │                       │                     │
         │                       │                       │◄──────────────────────│                     │
         │                       │                       │ Nodes + Edges         │                     │
         │                       │                       │                       │                     │
         │                       │                       │ Store in cache        │                     │
         │                       │                       │──────────────────────────────────────────────►│
         │                       │                       │                       │                     │
         │                       │◄──────────────────────│                       │                     │
         │                       │ { nodes: [...],       │                       │                     │
         │                       │   edges: [...] }      │                       │                     │
         │                       │                       │                       │                     │
         │◄──────────────────────│                       │                       │                     │
         │ Cytoscape.js Graph    │                       │                       │                     │
         │                       │                       │                       │                     │
```

### 4.5 Events Query Flow (ClickHouse)

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│    frontend      │    │     backend      │    │timeseries-query  │    │   clickhouse     │
│(EventsTimeline)  │    │    (FastAPI)     │    │    (:8002)       │    │    (:8123)       │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │                       │
         │ GET /events?          │                       │                       │
         │   cluster_id=1        │                       │                       │
         │   &limit=100          │                       │                       │
         │──────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │ EventService.         │                       │
         │                       │ get_all_events()      │                       │
         │                       │                       │                       │
         │                       │ HTTP GET /events      │                       │
         │                       │──────────────────────►│                       │
         │                       │                       │                       │
         │                       │                       │ SQL Query:            │
         │                       │                       │ SELECT * FROM         │
         │                       │                       │ network_flows         │
         │                       │                       │ UNION ALL             │
         │                       │                       │ SELECT * FROM         │
         │                       │                       │ dns_queries ...       │
         │                       │                       │───────────────────────►│
         │                       │                       │                       │
         │                       │                       │◄──────────────────────│
         │                       │                       │ JSON rows             │
         │                       │                       │                       │
         │                       │◄──────────────────────│                       │
         │                       │ { events: [...],      │                       │
         │                       │   total: 1500 }       │                       │
         │                       │                       │                       │
         │◄──────────────────────│                       │                       │
         │ Render timeline       │                       │                       │
         │                       │                       │                       │
```

---

## 5. Storage Strategy

### 5.1 Database Responsibilities

| Database | Purpose | Data Type | Retention | Query Pattern |
|----------|---------|-----------|-----------|---------------|
| PostgreSQL | Metadata | Clusters, Analyses, Users | Forever | CRUD, Joins |
| ClickHouse | Events | Network, DNS, TCP flows | 30-90 days | Time-range, Aggregation |
| Neo4j | Graph | Pod relationships | Until refresh | Path finding, Impact |
| Redis | Cache | Sessions, Hot data | TTL-based | Key-value lookup |

### 5.2 Data Model

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATA STORAGE MODEL                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PostgreSQL (Metadata)                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                          │   │
│  │  clusters                    analyses                    users          │   │
│  │  ├── id                      ├── id                      ├── id         │   │
│  │  ├── name                    ├── name                    ├── username   │   │
│  │  ├── connection_type         ├── cluster_id (FK)         ├── email      │   │
│  │  ├── gadget_endpoint         ├── status                  ├── role       │   │
│  │  ├── gadget_health_status    ├── scope_config (JSONB)    └── ...        │   │
│  │  ├── total_nodes             ├── gadget_config (JSONB)                  │   │
│  │  ├── total_pods              └── ...                                     │   │
│  │  └── ...                                                                 │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ClickHouse (Time-Series Events)                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                          │   │
│  │  network_flows                        dns_queries                       │   │
│  │  ├── timestamp (DateTime)             ├── timestamp                     │   │
│  │  ├── analysis_id                      ├── analysis_id                   │   │
│  │  ├── cluster_id                       ├── cluster_id                    │   │
│  │  ├── source_namespace                 ├── source_pod                    │   │
│  │  ├── source_pod                       ├── query_name                    │   │
│  │  ├── dest_namespace                   ├── query_type                    │   │
│  │  ├── dest_pod                         ├── response_ips (Array)          │   │
│  │  ├── dest_ip                          ├── latency_ms                    │   │
│  │  ├── dest_port                        └── ...                           │   │
│  │  ├── protocol                                                           │   │
│  │  ├── bytes_sent                                                         │   │
│  │  └── bytes_received                                                     │   │
│  │                                                                          │   │
│  │  Partitioning: BY toYYYYMM(timestamp)                                   │   │
│  │  TTL: timestamp + INTERVAL 90 DAY                                       │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Neo4j (Dependency Graph)                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                          │   │
│  │  (:Pod {name, namespace, cluster_id, labels})                           │   │
│  │       │                                                                  │   │
│  │       ├──[:COMMUNICATES_WITH {protocol, port, bytes, first_seen}]──►   │   │
│  │       │                                                                  │   │
│  │       ├──[:BELONGS_TO]──► (:Namespace {name})                          │   │
│  │       │                                                                  │   │
│  │       └──[:PART_OF]──► (:Deployment {name, namespace})                 │   │
│  │                                                                          │   │
│  │  Queries:                                                                │   │
│  │   • MATCH path = (a)-[:COMMUNICATES*1..5]->(b) RETURN path             │   │
│  │   • MATCH (p:Pod)-[c:COMMUNICATES]-() WHERE c.bytes > 1000000          │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Scalability Considerations

### 6.1 Horizontal Scaling Points

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SCALABILITY ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  STATELESS SERVICES (HPA)                 STATEFUL SERVICES (StatefulSet)      │
│  ┌─────────────────────────────┐         ┌─────────────────────────────┐       │
│  │                             │         │                             │       │
│  │  frontend: 2-10 replicas    │         │  postgresql: 1 (primary)   │       │
│  │  backend: 2-20 replicas     │         │  clickhouse: 1-3 (sharded) │       │
│  │  ingestion: 5-50 replicas   │         │  neo4j: 1 (core)           │       │
│  │  timeseries-writer: 3-20    │         │  rabbitmq: 1-3 (clustered) │       │
│  │  graph-writer: 2-10         │         │  redis: 1-3 (sentinel)     │       │
│  │                             │         │                             │       │
│  │  CPU/Memory based scaling   │         │  Manual scaling            │       │
│  │                             │         │  Data replication          │       │
│  └─────────────────────────────┘         └─────────────────────────────┘       │
│                                                                                  │
│  SCALING TRIGGERS:                                                              │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ ingestion-service:                                                       │  │
│  │   • CPU > 70% → Scale up                                                 │  │
│  │   • RabbitMQ queue depth > 10000 → Scale up                             │  │
│  │   • Events/sec > 50000 per pod → Scale up                               │  │
│  │                                                                          │  │
│  │ timeseries-writer:                                                       │  │
│  │   • Queue depth > 5000 → Scale up                                       │  │
│  │   • Write latency > 100ms → Scale up                                    │  │
│  │                                                                          │  │
│  │ backend:                                                                 │  │
│  │   • Request latency p99 > 500ms → Scale up                              │  │
│  │   • CPU > 80% → Scale up                                                 │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Multi-Cluster Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          MULTI-CLUSTER DEPLOYMENT                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│                        ┌─────────────────────────────┐                          │
│                        │     FLOWFISH CONTROL        │                          │
│                        │        PLANE                │                          │
│                        │                             │                          │
│                        │  frontend + backend +       │                          │
│                        │  orchestrator + writers +   │                          │
│                        │  storage (single cluster)   │                          │
│                        └──────────────┬──────────────┘                          │
│                                       │                                          │
│            ┌──────────────────────────┼──────────────────────────┐              │
│            │                          │                          │              │
│            ▼                          ▼                          ▼              │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐    │
│  │  TARGET CLUSTER A   │  │  TARGET CLUSTER B   │  │  TARGET CLUSTER C   │    │
│  │  (In-Cluster gRPC)  │  │  (Remote HTTP)      │  │  (Agent-Based)      │    │
│  │                     │  │                     │  │                     │    │
│  │  inspektor-gadget   │  │  inspektor-gadget   │  │  flowfish-agent     │    │
│  │  (:16060)           │  │  (:8080 HTTPS)      │  │  (:16061)           │    │
│  │                     │  │                     │  │                     │    │
│  │  Latency: <10ms     │  │  Latency: 50-200ms  │  │  Latency: varies    │    │
│  │  Bandwidth: High    │  │  Bandwidth: Medium  │  │  Bandwidth: Low     │    │
│  │  Security: Internal │  │  Security: mTLS     │  │  Security: Agent    │    │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

Flowfish uses a **microservices architecture** with clear separation of concerns:

1. **Presentation**: React frontend + FastAPI backend
2. **Orchestration**: Analysis lifecycle and cluster management
3. **Collection**: Protocol-agnostic Gadget communication
4. **Queue**: RabbitMQ for decoupling and buffering
5. **Storage**: Purpose-built databases (time-series, graph, relational)
6. **Query**: Specialized query services

**Key Design Decisions**:
- `ingestion-service` uses **kubectl-gadget CLI** to collect events (subprocess, JSON stream)
- All events flow through RabbitMQ (decoupling, buffering, replay)
- Query services for each database (timeseries-query, graph-query)
- Multiple database types for different query patterns
- Horizontal scaling for stateless services
- Inspektor Gadget v0.46.0+ with 10 event types supported

