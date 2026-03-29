# Flowfish Quick Reference Diagram

## One-Page Architecture

```
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║                                    FLOWFISH                                            ║
║                     eBPF-Based Kubernetes Observability Platform                       ║
╠═══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                        ║
║   USER                                                                                 ║
║    │                                                                                   ║
║    │ HTTP                                                                              ║
║    ▼                                                                                   ║
║   ┌─────────────────────────────────────────────────────────────────────────────────┐ ║
║   │                                                                                  │ ║
║   │   ┌──────────────────┐                    ┌──────────────────┐                  │ ║
║   │   │     frontend     │      REST/JSON     │     backend      │                  │ ║
║   │   │   (React:3000)   │◄──────────────────►│  (FastAPI:8000)  │                  │ ║
║   │   └──────────────────┘                    └────────┬─────────┘                  │ ║
║   │                                                     │ HTTP                       │ ║
║   │   ┌──────────────────────────────────────────────────────────────────────────┐  │ ║
║   │   │  change-detection-worker (:8001)  [Scalable - Leader Election]           │  │ ║
║   │   │  Periodic: Workload/Connection changes → PostgreSQL + Neo4j queries      │  │ ║
║   │   └──────────────────────────────────────────────────────────────────────────┘  │ ║
║   │                      ┌──────────────────────────────┼───────────────┐            │ ║
║   │                      │                              │               │            │ ║
║   │                      ▼                              ▼               ▼            │ ║
║   │         ┌─────────────────────┐    ┌────────────────────┐  ┌──────────────────┐ │ ║
║   │         │  timeseries-query   │    │    graph-query     │  │ analysis-orch.   │ │ ║
║   │         │     (:8002)         │    │     (:8001)        │  │    (:5002)       │ │ ║
║   │         └──────────┬──────────┘    └─────────┬──────────┘  └────────┬─────────┘ │ ║
║   │                    │ SQL                     │ Cypher               │ gRPC       │ ║
║   │                    ▼                         ▼                      ▼            │ ║
║   │         ┌──────────────────┐    ┌───────────────────┐   ┌──────────────────────┐│ ║
║   │         │    clickhouse    │    │      neo4j        │   │  ingestion-service   ││ ║
║   │         └──────────────────┘    └───────────────────┘   │      (:5000)         ││ ║
║   │                                                         │                      ││ ║
║   │                                                         │ ┌──────────────────┐ ││ ║
║   │                                                         │ │ kubectl-gadget   │ ││ ║
║   │                                                         │ │    (CLI)         │ ││ ║
║   │                                                         │ └────────┬─────────┘ ││ ║
║   │                                                         │          │           ││ ║
║   │                                                         │  ┌───────▼─────────┐ ││ ║
║   │                                                         │  │ RabbitMQ PUBLISH│ ││ ║
║   │                                                         │  └───────┬─────────┘ ││ ║
║   │                                                         └──────────┼───────────┘│ ║
║   │                                                                    │             │ ║
║   └────────────────────────────────────────────────────────────────────┼─────────────┘ ║
║                                                                        │ AMQP          ║
║                                                                        ▼               ║
║   ┌───────────────────────────────────────────────────┐  ┌────────────────────────┐  ║
║   │               TARGET CLUSTER                       │  │      rabbitmq          │  ║
║   │                                                    │  │     (:5672)            │  ║
║   │   ┌────────────────────────────────────────────┐  │  │                        │  ║
║   │   │           inspektor-gadget                  │  │  │  Queues:               │  ║
║   │   │             (DaemonSet)                     │  │  │   • network_flows     │  ║
║   │   │                                             │  │  │   • dns_queries       │  ║
║   │   │   eBPF Programs:                            │  │  │   • process_events    │  ║
║   │   │    • trace_tcp (network)                    │  │  │   • file_events       │  ║
║   │   │    • trace_dns                              │  │  │   • security_events   │  ║
║   │   │    • trace_exec (process)                   │  │  │   • oom_events        │  ║
║   │   │    • trace_open (file)                      │  │  │   • bind_events       │  ║
║   │   │    • trace_capabilities                     │  │  │   • sni_events        │  ║
║   │   │    • trace_oomkill                          │  │  │   • mount_events      │  ║
║   │   │    • trace_bind                             │  │  │                        │  ║
║   │   │    • trace_sni                              │  │  └───────────┬────────────┘  ║
║   │   │    • trace_mount                            │  │              │               ║
║   │   └────────────────────────────────────────────┘  │              │ AMQP          ║
║   │                                                    │              │ CONSUME       ║
║   │   Nodes: N | Pods: M | Namespaces: K              │              ▼               ║
║   │                                                    │  ┌────────────────────────┐  ║
║   │   Note: kubectl-gadget CLI runs trace commands    │  │  ┌──────────────────┐  │  ║
║   │         and streams JSON output to ingestion      │  │  │timeseries-writer │  │  ║
║   │                                                    │  │  │                  │  │  ║
║   └───────────────────────────────────────────────────┘  │  │ Batch → ClickH.  │  │  ║
║                                                           │  └────────┬─────────┘  │  ║
║                                                           │           │            │  ║
║                                                           │  ┌────────▼─────────┐  │  ║
║                                                           │  │  graph-writer    │  │  ║
║                                                           │  │                  │  │  ║
║                                                           │  │ Graph → Neo4j    │  │  ║
║                                                           │  └────────┬─────────┘  │  ║
║                                                           └───────────┼────────────┘  ║
║                                                                       │               ║
║                                                                       ▼               ║
║   ┌─────────────────────────────────────────────────────────────────────────────────┐ ║
║   │                              STORAGE LAYER                                       │ ║
║   │                                                                                  │ ║
║   │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │ ║
║   │  │   clickhouse     │  │     neo4j        │  │   postgresql     │              │ ║
║   │  │    (:9000)       │  │    (:7687)       │  │    (:5432)       │              │ ║
║   │  │                  │  │                  │  │                  │              │ ║
║   │  │  Time-Series     │  │   Dependency     │  │    Metadata      │              │ ║
║   │  │  Events          │  │   Graph          │  │   (Clusters,     │              │ ║
║   │  │  (10 tables)     │  │                  │  │    Analyses)     │              │ ║
║   │  └──────────────────┘  └──────────────────┘  └──────────────────┘              │ ║
║   │                                                                                  │ ║
║   └─────────────────────────────────────────────────────────────────────────────────┘ ║
║                                                                                        ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝


═══════════════════════════════════════════════════════════════════════════════════════
                                    LEGEND
═══════════════════════════════════════════════════════════════════════════════════════

    ─────────►  Synchronous request/response (REST, HTTP)
    ─ ─ ─ ─ ►  Asynchronous messaging (AMQP)
    
    (:PORT)     Service port number
    
    kubectl-gadget executes trace commands via subprocess
    JSON output is streamed and parsed by ingestion-service

═══════════════════════════════════════════════════════════════════════════════════════
                              SERVICE PORTS QUICK REFERENCE
═══════════════════════════════════════════════════════════════════════════════════════

    frontend              :3000   HTTP       React UI
    backend               :8000   HTTP       FastAPI Gateway
    change-detection-wrkr :8001   HTTP       Change Detection Worker
    timeseries-query      :8002   HTTP       ClickHouse Queries
    graph-query           :8001   HTTP       Neo4j Queries
    analysis-orchestrator :5002   gRPC       Analysis Lifecycle
    cluster-manager       :5001   gRPC       Cluster Management
    ingestion-service     :5000   gRPC       Event Collection
    rabbitmq              :5672   AMQP       Message Queue
    rabbitmq-mgmt         :15672  HTTP       RabbitMQ UI
    clickhouse            :9000   TCP        Time-Series DB
    clickhouse-http       :8123   HTTP       ClickHouse HTTP
    neo4j                 :7687   Bolt       Graph DB
    neo4j-http            :7474   HTTP       Neo4j Browser
    postgresql            :5432   TCP        Metadata DB
    redis                 :6379   TCP        Cache

═══════════════════════════════════════════════════════════════════════════════════════
                              WRITE PATH (Event Collection)
═══════════════════════════════════════════════════════════════════════════════════════

    1. User → frontend → backend → "Start Analysis"
    
    2. backend → analysis-orchestrator → "Create Task"
    
    3. analysis-orchestrator → ingestion-service → "Start Collection"
    
    4. ingestion-service → kubectl-gadget CLI → "Start Trace"
       (subprocess: kubectl gadget trace_tcp --output=json ...)
    
    5. kubectl-gadget → JSON stdout → ingestion-service → Events parsed
    
    6. ingestion-service → rabbitmq → "Publish Events" (10 event types)
    
    7a. timeseries-writer ◄── rabbitmq → "Consume" → ClickHouse (events)
    
    7b. graph-writer ◄── rabbitmq → "Consume" → Neo4j (dependency graph)

═══════════════════════════════════════════════════════════════════════════════════════
                              READ PATH (Data Queries)
═══════════════════════════════════════════════════════════════════════════════════════

    CLICKHOUSE (Time-Series Events):
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │  frontend → backend → timeseries-query:8002 → ClickHouse                    │
    │                                                                              │
    │  Pages: EventsTimeline, SecurityCenter, ActivityMonitor, NetworkExplorer    │
    │  Data:  network_flows, dns_queries, process_events, file_events, etc.       │
    └─────────────────────────────────────────────────────────────────────────────┘

    NEO4J (Dependency Graph):
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │  frontend → backend → graph-query:8001 → Neo4j                              │
    │                                                                              │
    │  Pages: LiveMap, Map (dependency visualization)                             │
    │  Data:  (:Pod)-[:COMMUNICATES]->(:Pod), (:Namespace), (:Deployment)         │
    └─────────────────────────────────────────────────────────────────────────────┘

    POSTGRESQL (Metadata):
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │  frontend → backend → cluster-manager:5001 → PostgreSQL                     │
    │                                                                              │
    │  Pages: Clusters, AnalysisWizard, Settings                                  │
    │  Data:  clusters, analyses, users, namespaces, workloads                    │
    └─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                              COMPLETE SERVICE LIST
═══════════════════════════════════════════════════════════════════════════════════════

    FRONTEND:
      • frontend              :3000   React + Ant Design + Cytoscape.js

    BACKEND SERVICES:
      • backend               :8000   FastAPI REST Gateway
      • cluster-manager       :5001   K8s Cluster Management (gRPC)
      • analysis-orchestrator :5002   Analysis Lifecycle (gRPC)
      • ingestion-service     :5000   kubectl-gadget Event Collection (gRPC)

    WORKER SERVICES (Scalable):
      • change-detection-worker :8001 Change Detection Worker (HTTP)

    QUERY SERVICES:
      • timeseries-query      :8002   ClickHouse Query Engine (HTTP)
      • graph-query           :8001   Neo4j Query Engine (HTTP)

    WRITER SERVICES (RabbitMQ Consumers):
      • timeseries-writer     (no port) ClickHouse Batch Writer
      • graph-writer          (no port) Neo4j Graph Builder

    INFRASTRUCTURE:
      • rabbitmq              :5672   Message Broker (AMQP)
      • clickhouse            :9000   Time-Series Database
      • neo4j                 :7687   Graph Database (Bolt)
      • postgresql            :5432   Metadata Database
      • redis                 :6379   Cache Layer

    EXTERNAL (Target Cluster):
      • inspektor-gadget      (DaemonSet) eBPF Data Source

═══════════════════════════════════════════════════════════════════════════════════════
                              KEY ARCHITECTURAL POINTS
═══════════════════════════════════════════════════════════════════════════════════════

    ✓ ingestion-service uses kubectl-gadget CLI (not gRPC)
      (subprocess execution, JSON stream parsing)
    
    ✓ All events flow through RabbitMQ
      (Decoupling, buffering, replay capability)
    
    ✓ Query services for each database
      (timeseries-query → ClickHouse, graph-query → Neo4j)
    
    ✓ Two parallel write paths from RabbitMQ
      (timeseries-writer → ClickHouse, graph-writer → Neo4j)
    
    ✓ Multiple databases for different query patterns
      (Time-series: ClickHouse, Graph: Neo4j, Metadata: PostgreSQL)
    
    ✓ Horizontal scaling for stateless services
      (ingestion-service, writers, query services, change-detection-worker)
    
    ✓ Change Detection Worker (Standalone Microservice)
      (Periodic change detection, blast radius calculation, risk assessment)
      (Scalable with Redis-based leader election for HA)
    
    ✓ 10 Event Types supported
      (network, dns, tcp, process, file, security, oom, bind, sni, mount)
```

