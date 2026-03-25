# 🐟 Flowfish - Microservices Architecture

## Architecture Overview

The Flowfish platform is built with a scalable, modular microservices architecture.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND (React)                                  │
│                         http://localhost:3000                                │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ REST API (HTTP/JSON)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY (FastAPI)                                │
│                           Port: 8000 (HTTP)                                  │
│  - REST API endpoints                                                        │
│  - Authentication & RBAC                                                     │
│  - Request routing to microservices                                          │
│  - Response aggregation                                                      │
└───┬──────────────┬──────────────┬──────────────┬──────────────────────────┬─┘
    │ gRPC         │ gRPC         │ gRPC         │ gRPC                     │
    ▼              ▼              ▼              ▼                          ▼
┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────────┐
│ CLUSTER │  │ ANALYSIS │  │ INGESTION │  │CLICKHOUSE│  │   CHANGE    │  │  DEPENDENCY  │
│ MANAGER │  │ORCHESTR. │  │  SERVICE  │  │  WRITER  │  │  DETECTION  │  │    GRAPH     │
│         │  │          │  │  (Worker) │  │ SERVICE  │  │   WORKER    │  │   SERVICE    │
│Port:5001│  │Port: 5002│  │Port: 5003 │  │Port: 5005│  │  Port: 8001 │  │  Port: 5004  │
└────┬────┘  └─────┬────┘  └─────┬─────┘  └─────┬────┘  └──────┬──────┘  └──────┬───────┘
     │             │              │               │              │                │
     │             │              │               │              │ (Scalable)     │
     │             │              │               │                       │
     │             │              ▼               ▼                       │
     │             │      ┌──────────────┐  ┌─────────┐                 │
     │             │      │  INSPEKTOR   │  │ RABBITMQ│                 │
     │             │      │   GADGET     │  │ (Queue) │                 │
     │             │      │  (External)  │  │Port:5672│                 │
     │             │      └──────────────┘  └────┬────┘                 │
     │             │                              │                       │
     │             │                              │ Consume               │
     │             │                              └───────────────────┐   │
     ▼             ▼                                                  ▼   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          SHARED DATABASES                                   │
│  - PostgreSQL (metadata, configs) - Port: 5432                              │
│  - ClickHouse (time-series data) - Port: 9000                               │
│  - Neo4j (dependency graphs) - Port: 7687                             │
│  - Redis (cache, job queue) - Port: 6379                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Inspektor Gadget → ClickHouse

```
┌──────────────────┐
│ Inspektor Gadget │ (eBPF data source in target cluster)
│   gRPC Stream    │
└────────┬─────────┘
         │ Real-time eBPF events
         │ (network, DNS, TCP, etc.)
         ▼
┌──────────────────────────────────────────────────┐
│         Ingestion Service (Multiple Workers)     │
│  - Connect to Inspektor Gadget gRPC             │
│  - Receive streaming data                        │
│  - Transform & validate                          │
│  - Add metadata (analysis_id, cluster_id)       │
│  - Publish to RabbitMQ                           │
└────────┬─────────────────────────────────────────┘
         │ Publish messages
         │ (JSON format, per event type)
         ▼
┌──────────────────────────────────────────────────┐
│              RabbitMQ (Message Queue)            │
│  Exchanges:                                      │
│    - flowfish.network_flows                      │
│    - flowfish.dns_queries                        │
│    - flowfish.tcp_connections                    │
│    - flowfish.change_events (NEW)                │
│    - flowfish.workload_metadata (NEW)            │
│                                                  │
│  Queues:                                         │
│    - network_flows.clickhouse                    │
│    - dns_queries.clickhouse                      │
│    - tcp_connections.clickhouse                  │
│    - flowfish.queue.change_events.timeseries     │
│    - flowfish.queue.workload_metadata.timeseries │
│                                                  │
│  Features:                                       │
│    - Message persistence                         │
│    - Dead letter queue                           │
│    - Message TTL                                 │
│    - Priority queues                             │
└────────┬─────────────────────────────────────────┘
         │ Consume messages (batch)
         │ Acknowledgment after write
         ▼
┌──────────────────────────────────────────────────┐
│      ClickHouse Writer Service (Workers)         │
│  - Consume from RabbitMQ queues                  │
│  - Batch messages (1000 events or 10s)           │
│  - Bulk insert to ClickHouse                     │
│  - Handle retries & errors                       │
│  - Send ACK to RabbitMQ                          │
└────────┬─────────────────────────────────────────┘
         │ Bulk INSERT
         ▼
┌──────────────────────────────────────────────────┐
│              ClickHouse Database                 │
│  Tables:                                         │
│    - network_flows (partitioned by date)        │
│    - dns_queries                                 │
│    - tcp_connections                             │
│                                                  │
│  Indexes:                                        │
│    - timestamp, cluster_id, analysis_id          │
│    - pod_name, namespace                         │
└──────────────────────────────────────────────────┘
```

## Microservice Details

### 1. API Gateway (Port: 8000)
**Technology:** FastAPI + Python  
**Responsibilities:**
- REST API endpoints (communication with the frontend)
- Authentication (JWT)
- Authorization (RBAC)
- Request routing to microservices
- Response aggregation
- Rate limiting
- CORS handling

**Endpoints:**
- `/api/v1/auth/*` - Authentication
- `/api/v1/clusters/*` - Cluster management (→ Cluster Manager)
- `/api/v1/analyses/*` - Analysis management (→ Analysis Orchestrator)
- `/api/v1/workloads/*` - Workload discovery (→ Cluster Manager)
- `/api/v1/dependencies/*` - Dependency graph (→ Graph Service)
- `/api/v1/health` - Health check

**Environment Variables:**
```env
PORT=8000
JWT_SECRET=your-secret-key
CLUSTER_MANAGER_GRPC=cluster-manager:5001
ANALYSIS_ORCHESTRATOR_GRPC=analysis-orchestrator:5002
DEPENDENCY_GRAPH_GRPC=dependency-graph:5004
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

---

### 2. Cluster Manager Service (Port: 5001)
**Technology:** Python + gRPC  
**Responsibilities:**
- Kubernetes/OpenShift cluster registration and management
- Cluster health monitoring
- Communication with the Kubernetes API
- Live resource discovery (namespaces, deployments, pods, services)
- ServiceAccount token management
- Inspektor Gadget health check

**gRPC Services:**
```protobuf
service ClusterManager {
  // Cluster CRUD
  rpc CreateCluster(CreateClusterRequest) returns (Cluster);
  rpc GetCluster(GetClusterRequest) returns (Cluster);
  rpc ListClusters(ListClustersRequest) returns (ClusterList);
  rpc UpdateCluster(UpdateClusterRequest) returns (Cluster);
  rpc DeleteCluster(DeleteClusterRequest) returns (Empty);
  
  // Health checks
  rpc CheckClusterHealth(CheckHealthRequest) returns (HealthStatus);
  rpc CheckGadgetHealth(CheckGadgetHealthRequest) returns (GadgetHealthStatus);
  
  // Resource discovery
  rpc ListNamespaces(ListNamespacesRequest) returns (NamespaceList);
  rpc ListDeployments(ListDeploymentsRequest) returns (DeploymentList);
  rpc ListStatefulSets(ListStatefulSetsRequest) returns (StatefulSetList);
  rpc ListServices(ListServicesRequest) returns (ServiceList);
  rpc ListPods(ListPodsRequest) returns (PodList);
}
```

**Database Tables:**
- `clusters` - Cluster metadata
- `cluster_health_history` - Health check logs

#### 2.1 ClusterConnectionManager (Backend Service Layer)

**December 2025 Update**: The backend now accesses clusters through `ClusterConnectionManager`.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ClusterConnectionManager                      │
│  Location: backend/services/cluster_connection_manager.py        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Features:                                                     │
│  ├── Connection pooling (per-cluster cache)                  │
│  ├── Automatic connection type detection (in-cluster/remote)     │
│  ├── Credential management with Fernet encryption                  │
│  ├── Background health monitoring (circuit breaker)             │
│  └── Unified API (get_cluster_info, get_namespaces, etc.)       │
│                                                                  │
│  Connection Types:                                               │
│  ├── InClusterConnection  → cluster-manager gRPC                │
│  └── RemoteTokenConnection → Direct K8s API (httpx)             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Files:**
```
backend/services/
├── cluster_connection_manager.py    # Unified manager
├── connections/
│   ├── base.py                      # Abstract ClusterConnection
│   ├── in_cluster.py                # InClusterConnection
│   └── remote_token.py              # RemoteTokenConnection
├── health/
│   └── cluster_health_monitor.py    # Background health checks
└── cluster_cache_service.py         # Redis cache (uses manager)
```

---

### 3. Analysis Orchestrator Service (Port: 5002)
**Technology:** Python + gRPC  
**Responsibilities:**
- Analysis definition management
- Analysis lifecycle management (create, start, stop, pause)
- Multi-cluster analysis orchestration
- Task assignment to data collector workers
- Analysis scheduling (periodic, time-based)
- Analysis status tracking
- Result aggregation

**gRPC Services:**
```protobuf
service AnalysisOrchestrator {
  // Analysis CRUD
  rpc CreateAnalysis(CreateAnalysisRequest) returns (Analysis);
  rpc GetAnalysis(GetAnalysisRequest) returns (Analysis);
  rpc ListAnalyses(ListAnalysesRequest) returns (AnalysisList);
  rpc UpdateAnalysis(UpdateAnalysisRequest) returns (Analysis);
  rpc DeleteAnalysis(DeleteAnalysisRequest) returns (Empty);
  
  // Analysis control
  rpc StartAnalysis(StartAnalysisRequest) returns (AnalysisStartResponse);
  rpc StopAnalysis(StopAnalysisRequest) returns (Empty);
  rpc PauseAnalysis(PauseAnalysisRequest) returns (Empty);
  rpc ResumeAnalysis(ResumeAnalysisRequest) returns (Empty);
  
  // Status & results
  rpc GetAnalysisStatus(GetStatusRequest) returns (AnalysisStatus);
  rpc GetAnalysisResults(GetResultsRequest) returns (AnalysisResults);
  
  // Worker coordination
  rpc AssignCollectorTask(AssignTaskRequest) returns (TaskAssignment);
  rpc ReportCollectorStatus(CollectorStatusReport) returns (Empty);
}
```

**Database Tables:**
- `analyses` - Analysis definitions
- `analysis_executions` - Analysis run history
- `collector_tasks` - Task assignments for workers

**Communication:**
- → **Cluster Manager**: Get cluster details, validate health
- → **Data Collector**: Assign collection tasks
- ← **Data Collector**: Receive status updates

---

### 4. Ingestion Service (Port: 5003)
**Name:** `flowfish-ingestion` (Ingestion Worker / Data Collector Worker)  
**Technology:** Python + gRPC + asyncio + RabbitMQ (pika)  
**Responsibilities:**
- gRPC communication with Inspektor Gadget
- eBPF data collection (streaming)
- Real-time data transformation
- Metadata enrichment (analysis_id, cluster_id, timestamps)
- Publish to RabbitMQ queues
- Error handling & reconnection logic
- Multiple workers (horizontal scaling)
- Worker health monitoring

**Name Alternatives:**
- ✅ **flowfish-ingestion** (Recommended — short and clear)
- flowfish-collector
- flowfish-gadget-worker
- flowfish-stream-processor

**gRPC Services:**
```protobuf
service DataCollector {
  // Task management
  rpc StartCollection(StartCollectionRequest) returns (CollectionSession);
  rpc StopCollection(StopCollectionRequest) returns (Empty);
  rpc GetCollectionStatus(GetStatusRequest) returns (CollectionStatus);
  
  // Data streaming
  rpc StreamData(stream DataPoint) returns (StreamAck);
  
  // Health
  rpc HealthCheck(Empty) returns (HealthStatus);
}
```

**Worker Logic:**
1. Receive task from the orchestrator
2. Connect to Inspektor Gadget (target cluster)
3. Start gadget trace (network, DNS, TCP, etc.)
4. Read the data stream
5. Batch write to ClickHouse
6. Send status updates to the orchestrator
7. On error, retry or fail

**Environment Variables:**
```env
PORT=5003
ORCHESTRATOR_GRPC=analysis-orchestrator:5002
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
BATCH_SIZE=1000
BATCH_INTERVAL_SECONDS=10
MAX_RETRIES=3
```

**Scaling:**
- Multiple worker instances (1-N)
- Redis queue for task distribution
- Worker registration to orchestrator

---

### 5. Dependency Graph Service (Port: 5004)
**Technology:** Python + gRPC + Neo4j  
**Responsibilities:**
- Read communication data from ClickHouse
- Build dependency graphs
- Graph database (Neo4j) management
- Graph queries (shortest path, neighbors, etc.)
- Change detection (new/lost connections)
- Anomaly detection integration

**gRPC Services:**
```protobuf
service DependencyGraph {
  // Graph generation
  rpc GenerateGraph(GenerateGraphRequest) returns (Graph);
  rpc UpdateGraph(UpdateGraphRequest) returns (Graph);
  
  // Graph queries
  rpc GetGraph(GetGraphRequest) returns (Graph);
  rpc GetServiceDependencies(GetDependenciesRequest) returns (DependencyList);
  rpc FindPath(FindPathRequest) returns (PathResult);
  rpc GetNeighbors(GetNeighborsRequest) returns (NodeList);
  
  // Analysis
  rpc DetectChanges(DetectChangesRequest) returns (ChangeList);
  rpc CalculateRiskScore(RiskScoreRequest) returns (RiskScore);
}
```

**Process:**
1. Triggered when an analysis completes
2. Pull network flow data from ClickHouse
3. Create vertices (pods, services, deployments)
4. Create edges (communication paths)
5. Write to Neo4j
6. Perform historical comparison
7. Return change detection results

---

## gRPC Proto Definitions

### Common Messages
```protobuf
syntax = "proto3";

package flowfish;

// Common types
message Empty {}

message Timestamp {
  int64 seconds = 1;
  int32 nanos = 2;
}

message Pagination {
  int32 page = 1;
  int32 page_size = 2;
}

message HealthStatus {
  bool healthy = 1;
  string message = 2;
  map<string, string> details = 3;
}
```

### Cluster Messages
```protobuf
message Cluster {
  int32 id = 1;
  string name = 2;
  string description = 3;
  string cluster_type = 4; // kubernetes, openshift
  string api_url = 5;
  string token = 6;
  string gadget_grpc_endpoint = 7;
  string gadget_token = 8;
  bool verify_ssl = 9;
  string health_status = 10;
  int32 node_count = 11;
  int32 pod_count = 12;
  Timestamp created_at = 13;
}

message CreateClusterRequest {
  string name = 1;
  string description = 2;
  string cluster_type = 3;
  string api_url = 4;
  string token = 5;
  string gadget_grpc_endpoint = 6;
  string gadget_token = 7;
  bool verify_ssl = 8;
}

message ListClustersRequest {
  Pagination pagination = 1;
  string filter = 2;
}

message ClusterList {
  repeated Cluster clusters = 1;
  int32 total = 2;
}
```

### Analysis Messages
```protobuf
message Analysis {
  int32 id = 1;
  string name = 2;
  string description = 3;
  repeated int32 cluster_ids = 4;
  ScopeConfig scope_config = 5;
  repeated string gadget_modules = 6;
  TimeConfig time_config = 7;
  string status = 8; // pending, running, completed, failed
  Timestamp created_at = 9;
  Timestamp started_at = 10;
  Timestamp completed_at = 11;
}

message ScopeConfig {
  string scope_type = 1; // cluster, namespace, deployment, pod, label
  repeated string namespaces = 2;
  repeated string deployments = 3;
  string label_selector = 4;
}

message TimeConfig {
  string mode = 1; // continuous, time_range, periodic
  int32 duration_seconds = 2;
  Timestamp start_time = 3;
  Timestamp end_time = 4;
}

message StartAnalysisRequest {
  int32 analysis_id = 1;
}

message AnalysisStartResponse {
  int32 analysis_id = 1;
  repeated TaskAssignment task_assignments = 2;
  string message = 3;
}

message TaskAssignment {
  string task_id = 1;
  int32 cluster_id = 2;
  int32 worker_id = 3;
  string worker_address = 4;
}
```

### Data Collection Messages
```protobuf
message StartCollectionRequest {
  string task_id = 1;
  int32 cluster_id = 2;
  int32 analysis_id = 3;
  string gadget_grpc_endpoint = 4;
  string gadget_token = 5;
  repeated string gadget_modules = 6;
  ScopeConfig scope = 7;
  int32 duration_seconds = 8;
}

message CollectionSession {
  string session_id = 1;
  string task_id = 2;
  string status = 3;
  Timestamp started_at = 4;
}

message DataPoint {
  string session_id = 1;
  string data_type = 2; // network_flow, dns_query, tcp_connection
  Timestamp timestamp = 3;
  bytes payload = 4; // JSON or protobuf encoded data
}

message CollectionStatus {
  string session_id = 1;
  string status = 2; // running, completed, failed
  int64 events_collected = 3;
  int64 bytes_written = 4;
  string error_message = 5;
}
```

---

## Project Structure

```
flowfish/
├── services/
│   ├── api-gateway/              # FastAPI REST API
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── middleware/
│   │   ├── dependencies.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── cluster-manager/          # gRPC service
│   │   ├── server.py
│   │   ├── services/
│   │   │   ├── kubernetes_client.py
│   │   │   └── gadget_client.py
│   │   ├── models/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── analysis-orchestrator/    # gRPC service
│   │   ├── server.py
│   │   ├── services/
│   │   │   ├── analysis_engine.py
│   │   │   ├── scheduler.py
│   │   │   └── task_manager.py
│   │   ├── models/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── data-collector/           # gRPC service + worker
│   │   ├── server.py
│   │   ├── worker.py
│   │   ├── services/
│   │   │   ├── gadget_client.py
│   │   │   ├── clickhouse_writer.py
│   │   │   └── stream_processor.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── dependency-graph/         # gRPC service
│       ├── server.py
│       ├── services/
│       │   ├── graph_builder.py
│       │   ├── change_detector.py
│       │   └── neo4j_client.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── proto/                         # gRPC proto definitions
│   ├── common.proto
│   ├── cluster_manager.proto
│   ├── analysis_orchestrator.proto
│   ├── data_collector.proto
│   └── dependency_graph.proto
│
├── shared/                        # Shared libraries
│   ├── grpc_clients/
│   ├── database/
│   ├── models/
│   └── utils/
│
├── frontend/                      # React app
│   └── ... (existing)
│
└── deployment/
    ├── docker-compose.microservices.yml
    └── kubernetes-manifests/
        ├── 01-namespace.yaml
        ├── 10-api-gateway.yaml
        ├── 11-cluster-manager.yaml
        ├── 12-analysis-orchestrator.yaml
        ├── 13-data-collector.yaml
        ├── 14-dependency-graph.yaml
        └── ...
```

---

## Communication Patterns

### 1. Synchronous (gRPC)
- API Gateway → Cluster Manager: Get cluster info
- API Gateway → Analysis Orchestrator: CRUD operations
- Analysis Orchestrator → Cluster Manager: Health checks
- API Gateway → Dependency Graph: Query graphs

### 2. Asynchronous (Redis Pub/Sub or Queue)
- Analysis Orchestrator → Data Collector: Task assignments
- Data Collector → Analysis Orchestrator: Status updates
- Data Collector → ClickHouse: Bulk data writes

### 3. Event-Driven
- Analysis completed → Trigger dependency graph generation
- New data collected → Update real-time dashboard
- Health check failed → Send alert

---

## Scaling Strategy

### Horizontal Scaling
1. **Data Collector Workers**: Scale based on active analyses (1-N instances)
2. **API Gateway**: Scale based on request load (2-N instances)
3. **Analysis Orchestrator**: Active-passive with leader election

### Vertical Scaling
- ClickHouse: Increase resources for write throughput
- Neo4j: Increase resources for graph queries

### Load Balancing
- Kubernetes Service (ClusterIP) for internal gRPC
- Nginx Ingress for external HTTP/REST

---

## Deployment

### Docker Compose (Local Development)
```yaml
version: '3.8'

services:
  api-gateway:
    build: ./services/api-gateway
    ports:
      - "8000:8000"
    environment:
      - CLUSTER_MANAGER_GRPC=cluster-manager:5001
      - ANALYSIS_ORCHESTRATOR_GRPC=analysis-orchestrator:5002
    depends_on:
      - cluster-manager
      - analysis-orchestrator

  cluster-manager:
    build: ./services/cluster-manager
    ports:
      - "5001:5001"
    environment:
      - DATABASE_URL=postgresql://...

  analysis-orchestrator:
    build: ./services/analysis-orchestrator
    ports:
      - "5002:5002"
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...

  data-collector:
    build: ./services/data-collector
    deploy:
      replicas: 3
    environment:
      - ORCHESTRATOR_GRPC=analysis-orchestrator:5002
      - CLICKHOUSE_HOST=clickhouse

  dependency-graph:
    build: ./services/dependency-graph
    ports:
      - "5004:5004"
    environment:
      - NEO4J_HOST=neo4j
```

### Kubernetes
- Each service: Deployment + Service
- gRPC services: ClusterIP
- API Gateway: Ingress
- Data Collector: Deployment with HPA (autoscaling)

---

## Advantages

1. **Scalability**: Each service scales independently
2. **Resilience**: Service failure doesn't affect others
3. **Technology Flexibility**: Different languages per service if needed
4. **Development Speed**: Teams work on services independently
5. **Deployment**: Deploy services individually
6. **Monitoring**: Service-level metrics and tracing

---

## Implementation Phases

### Phase 1: Core Services (Sprint 7-8)
1. Define gRPC proto files
2. Implement API Gateway (basic routing)
3. Implement Cluster Manager
4. Update frontend to use API Gateway

### Phase 2: Analysis Flow (Sprint 9-10)
1. Implement Analysis Orchestrator
2. Implement Data Collector Worker
3. Integrate with Inspektor Gadget
4. ClickHouse data pipeline

### Phase 3: Graph & Analytics (Sprint 11-12)
1. Implement Dependency Graph Service
2. Change detection logic
3. Risk scoring
4. Real-time updates

---

**Status:** Architecture design phase  
**Next Step:** Implement gRPC proto files and API Gateway  
**Target:** Production-ready microservices architecture

