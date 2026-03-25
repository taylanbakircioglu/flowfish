# Flowfish - Technology Choices and Rationale

## 🎯 Overview

Technologies selected for the Flowfish platform follow principles of high performance, scalability, reliability, and developer productivity.

---

## 📊 Technology Stack Summary

| Layer | Technology | Version |
|--------|-----------|----------|
| **Data Collection** | Inspektor Gadget + eBPF | Latest |
| **Backend** | Python + FastAPI | 3.11+ / 0.100+ |
| **Frontend** | React + TypeScript | 18+ / 5+ |
| **UI Framework** | Ant Design | 5+ |
| **Graph Viz** | Cytoscape.js | 3.26+ |
| **Relational DB** | PostgreSQL | 15+ |
| **Graph DB** | Neo4j | 3.6+ |
| **Time-series DB** | ClickHouse | 23+ |
| **Cache** | Redis | 7+ |
| **Container** | Docker | 20.10+ |
| **Orchestration** | Kubernetes/OpenShift | 1.27+ / 4.13+ |

---

## 🔬 Data Collection: Inspektor Gadget + eBPF

### Selection Rationale

**Why Inspektor Gadget?**
- ✅ **Kubernetes Native**: Purpose-built for K8s/OpenShift
- ✅ **eBPF Powered**: Kernel-level data collection, near-zero overhead
- ✅ **Zero Application Change**: No application changes required
- ✅ **DaemonSet Architecture**: Easy deployment, automatic scaling
- ✅ **Rich Gadget Library**: Network, DNS, TCP, process, syscall, file tracking
- ✅ **Open Source**: MIT license, active community

**Alternatives and Why They Were Not Chosen:**

| Alternative | Pros | Cons | Why Not Chosen |
|------------|------|------|----------------|
| **Service Mesh (Istio/Linkerd)** | L7 metrics, mTLS | Sidecar injection required, high overhead | Requires application changes |
| **APM Tools (Datadog, New Relic)** | Rich UI, easy setup | Paid, vendor lock-in | Costly, external dependency |
| **Custom eBPF Programs** | Full control | Development complexity | High development cost |
| **Network Sniffer (tcpdump)** | Simple | High performance impact | Scalability issues |

### Technical Details

**eBPF (Extended Berkeley Packet Filter)**:
- Linux kernel 4.4+ support
- In-kernel execution (no user-space round trips)
- Verifiable bytecode (safe execution)
- CO-RE (Compile Once Run Everywhere)
- Minimal CPU/memory overhead (<1–2%)

**Inspektor Gadgets**:
- `trace_network`: TCP/UDP connection tracking
- `trace_dns`: DNS query/response logging
- `trace_tcp`: TCP lifecycle events
- `trace_exec`: Process execution tracking
- `trace_open`: File access monitoring
- `trace_bind`: Port binding detection

---

## 🚀 Backend: Python + FastAPI

### Selection Rationale

**Python**:
- ✅ **Ecosystem**: Rich library support (data processing, ML/AI)
- ✅ **LLM Integration**: Libraries like OpenAI, LangChain are native to Python
- ✅ **Async Support**: Modern async programming with asyncio
- ✅ **Developer Productivity**: Fast development, readable syntax

**FastAPI**:
- ✅ **High Performance**: Starlette + Pydantic, Go/Node.js–level speed
- ✅ **Automatic OpenAPI**: Swagger UI generated automatically
- ✅ **Type Safety**: Compile-time type checking with Pydantic
- ✅ **Async Native**: Native async/await support
- ✅ **Dependency Injection**: Clean, testable code
- ✅ **WebSocket Support**: Real-time communication

**Alternatives**:

| Alternative | Why Not Chosen |
|------------|----------------|
| **Django** | Monolithic, overhead for non-REST needs |
| **Flask** | Sync-only, lacks modern features |
| **Go (Gin/Echo)** | Weaker Python ecosystem and LLM integration |
| **Node.js (Express)** | Callback hell, weak type safety |

---

## ⚛️ Frontend: React + TypeScript + Ant Design

### Selection Rationale

**React 18**:
- ✅ **Industry Standard**: Large community, abundant resources
- ✅ **Component-Based**: Reusable, maintainable components
- ✅ **Hooks**: Modern state management
- ✅ **Virtual DOM**: Efficient rendering
- ✅ **Server Components**: Future-proof (RSC)

**TypeScript**:
- ✅ **Type Safety**: Catch errors at compile time
- ✅ **Better IntelliSense**: Excellent IDE support
- ✅ **Refactoring**: Safe rename, move operations
- ✅ **Documentation**: Types = self-documenting code

**Ant Design (antd)**:
- ✅ **Enterprise-Grade**: Used by Fortune 500 companies
- ✅ **Comprehensive**: 60+ high-quality components
- ✅ **Consistent**: Unified design language
- ✅ **Customizable**: Theme support, CSS-in-JS
- ✅ **Accessible**: WCAG 2.0 AA compliant
- ✅ **I18n**: Multi-language support built-in

**Alternatives**:

| Alternative | Why Not Chosen |
|------------|----------------|
| **Vue.js** | Smaller ecosystem, less enterprise adoption |
| **Angular** | Steep learning curve, verbose |
| **Material-UI** | Ant Design is more enterprise-focused |
| **Chakra UI** | Younger, less battle-tested |

---

## 🎨 Graph Visualization: Cytoscape.js

### Selection Rationale

**Cytoscape.js**:
- ✅ **Purpose-Built**: Designed specifically for graph visualization
- ✅ **Performance**: Handles 1000+ nodes/edges
- ✅ **Extensible**: Plugin ecosystem
- ✅ **Layout Algorithms**: Hierarchical, force-directed, circular, grid
- ✅ **Styling**: CSS-like styling system
- ✅ **Events**: Rich interaction events
- ✅ **Export**: PNG, JPG, JSON export

**Alternatives**:

| Alternative | Pros | Cons |
|------------|------|------|
| **D3.js** | Very flexible, powerful | Steep learning curve, verbose |
| **Vis.js** | Easy to use | Performance issues (>500 nodes) |
| **Sigma.js** | Fast rendering | Limited feature set |
| **React Flow** | React-native | Missing graph algorithms |

---

## 🗄️ Databases

### PostgreSQL 15+ (Relational Data)

**Selection Rationale**:
- ✅ **ACID Compliance**: Reliable transactions
- ✅ **JSONB Support**: JSON storage for flexible schema
- ✅ **Full-Text Search**: Built-in search capabilities
- ✅ **Extensions**: PostGIS, pg_trgm, btree_gin
- ✅ **Replication**: Streaming replication, logical replication
- ✅ **Partitioning**: Table partitioning for large datasets
- ✅ **Mature**: 30+ years, production-proven

**Use Cases**:
- User accounts, roles, permissions
- Cluster and namespace metadata
- Analysis configurations
- Anomaly and change records
- Audit logs

**Why Alternatives Were Not Chosen**:
- **MySQL**: Weak JSONB support, complex replication
- **MongoDB**: Weak ACID guarantees, not ideal for relational data

### Neo4j 3.6+ (Graph Database)

**Selection Rationale**:
- ✅ **Distributed**: Native distributed architecture
- ✅ **Scale**: Support for trillions of vertices/edges
- ✅ **Performance**: Sub-millisecond graph traversal
- ✅ **GQL (nGQL)**: SQL-like graph query language
- ✅ **Open Source**: Apache 2.0 license
- ✅ **Kubernetes-Friendly**: Helm charts, operators
- ✅ **Consistency**: Strong consistency via Raft

**Use Cases**:
- Workload dependencies (Pod → Deployment → Service)
- Communication edges (COMMUNICATES_WITH)
- Dependency chains (DEPENDS_ON)
- Graph traversal queries (upstream/downstream)

**Alternatives**:

| Alternative | Why Not Chosen |
|------------|----------------|
| **Neo4j** | Paid (enterprise), Cypher proprietary |
| **JanusGraph** | Lower performance than Neo4j |
| **Amazon Neptune** | Vendor lock-in, cloud-only |
| **ArangoDB** | Multi-model complexity |

### ClickHouse 23+ (Time-Series/OLAP)

**Selection Rationale**:
- ✅ **Columnar Storage**: High compression (10–100x)
- ✅ **Fast Queries**: Billions of rows, sub-second queries
- ✅ **Aggregations**: Pre-aggregation via materialized views
- ✅ **TTL Support**: Automatic data cleanup
- ✅ **Partitioning**: Date/time based partitioning
- ✅ **Replication**: Built-in replication
- ✅ **SQL**: Standard SQL dialect

**Use Cases**:
- Network flow events (raw eBPF data)
- DNS queries, TCP connections
- HTTP requests, metrics
- Process events, syscall traces
- Aggregated request metrics

**Alternatives**:

| Alternative | Why Not Chosen |
|------------|----------------|
| **TimescaleDB** | PostgreSQL extension, slower |
| **InfluxDB** | Non-SQL, limited query capabilities |
| **Elasticsearch** | Resource-heavy, complex operations |
| **Prometheus** | Short retention, not for raw events |

### Redis 7+ (Cache & Real-time)

**Selection Rationale**:
- ✅ **In-Memory**: Microsecond latency
- ✅ **Pub/Sub**: Real-time event streaming
- ✅ **Data Structures**: Lists, sets, sorted sets, hashes
- ✅ **TTL**: Automatic expiration
- ✅ **Persistence**: RDB + AOF
- ✅ **Clustering**: Native clustering support
- ✅ **Sentinel**: Automatic failover

**Use Cases**:
- Session storage (JWT tokens)
- Real-time metrics cache
- Rate limiting counters
- Pub/Sub for WebSocket updates
- Distributed locks

---

## 🐳 Container & Orchestration

### Docker

**Selection Rationale**:
- ✅ **Industry Standard**: De facto containerization platform
- ✅ **Image Registry**: Docker Hub, private registries
- ✅ **Multi-Stage Builds**: Optimized images
- ✅ **BuildKit**: Fast, efficient builds

### Kubernetes / OpenShift

**Selection Rationale**:
- ✅ **Cloud-Native Standard**: Industry standard orchestration
- ✅ **Auto-Scaling**: HPA, VPA
- ✅ **Self-Healing**: Automatic restarts, health checks
- ✅ **Service Discovery**: Built-in DNS
- ✅ **Storage**: PersistentVolumes, StorageClasses
- ✅ **Security**: RBAC, NetworkPolicies, PodSecurityPolicies
- ✅ **OpenShift**: Enterprise features, operators, built-in monitoring

---

## 🔐 Authentication

### JWT (JSON Web Tokens)

**Selection Rationale**:
- ✅ **Stateless**: No server-side session required
- ✅ **Scalable**: Horizontal scaling friendly
- ✅ **Cross-Domain**: CORS-friendly
- ✅ **Standard**: RFC 7519
- ✅ **Libraries**: Mature libraries for every language

### OAuth 2.0 / OpenID Connect

**Selection Rationale**:
- ✅ **SSO**: Single Sign-On support
- ✅ **Enterprise**: Azure AD, Okta, Keycloak integration
- ✅ **Delegation**: Secure delegation of access
- ✅ **Standard**: Industry standard protocol

---

## 📊 Monitoring & Observability

### Recommended Stack (Optional)

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Metrics** | Prometheus | Time-series metrics |
| **Logs** | Loki / ELK | Centralized logging |
| **Tracing** | Jaeger / Tempo | Distributed tracing |
| **Dashboards** | Grafana | Visualization |
| **Alerting** | Alertmanager | Alert management |

---

## 🎯 Conclusion

The Flowfish technology stack follows modern cloud-native application development best practices:

**✅ Performance**: eBPF, FastAPI, ClickHouse, Redis  
**✅ Scalability**: Kubernetes, distributed databases  
**✅ Reliability**: PostgreSQL ACID, replication  
**✅ Developer Experience**: Python, TypeScript, React  
**✅ Maintainability**: Type safety, test frameworks  
**✅ Open Source**: No vendor lock-in, community support  

**Version**: 1.0.0  
**Last Updated**: January 2025

