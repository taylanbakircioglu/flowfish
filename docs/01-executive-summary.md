# Flowfish - Executive Summary

## 🐟 Overview

**Flowfish** is a next-generation platform that automatically discovers, visualizes, and analyzes communication and dependencies between applications running in Kubernetes and OpenShift environments. Using eBPF (Extended Berkeley Packet Filter) technology with the Inspektor Gadget framework, it collects data at the kernel level and provides full visibility without requiring any changes at the application layer.

### Metaphor: Fish, Flow, Water

- **Fish** → Represents Kubernetes Pods
- **Flow** → Denotes network traffic and communication between Pods
- **Water** → The Kubernetes/OpenShift environment in which the entire system flows

## 🎯 Problem and Solution

### Problem

In modern microservice architectures:
- Inter-application dependencies are documented manually and quickly become outdated
- Visibility into service-to-service communication is limited
- Unexpected communication changes create security and stability risks
- It is difficult to test the effects of network policies in advance
- Long troubleshooting cycles are needed to understand service dependencies

### Solution: Flowfish

Flowfish addresses these challenges with the following capabilities:

1. **Automatic Discovery**: Automatically detects communication across all Pods, Deployments, StatefulSets, and Services using eBPF
2. **Real-Time Visibility**: Provides live dependency maps and traffic flows
3. **Historical Analysis**: Tracks and compares changes over time
4. **AI-Powered Anomaly Detection**: Automatically detects suspicious traffic patterns via LLM integration
5. **What-If Simulation**: Tests the impact of network policy changes before applying them

## 🚀 Core Capabilities

### 1. Universal Data Ingestion
Beyond eBPF, **data collection from multiple sources**:
- **Infrastructure**: eBPF, Kubernetes Events/Metrics, CNI plugins
- **Application**: Prometheus, Service Mesh (Istio/Linkerd), APM traces, Logs
- **External**: Cloud APIs, CI/CD systems, incident management tools

**Dependency Provenance** (origin tracking): Full data lineage for every dependency:
- Which source detected it (eBPF, Istio, Prometheus)
- When it was discovered and who validated it
- Confidence score (0–100%)
- Multi-source verification

### 2. Application Communication and Dependency Map
- Communication discovery at Pod, Deployment, StatefulSet, and Service level
- Detailed metrics such as port, protocol, request count, latency
- Interactive graph visualization (node–edge structure)
- Real-time and historical views
- Filtering by cluster, namespace, workload type, and labels
- Layered view (frontend → backend → database)
- Physical view (Node / Pod / Service based)

### 3. Disaster Recovery Posture Assessment
**Automatic DR assessment for stateful workloads**:
- **RPO (Recovery Point Objective)**: Backup frequency, last backup time
- **RTO (Recovery Time Objective)**: Estimated restore duration
- **Parity Check**: Primary–replica data consistency, replication lag
- **Backup TTL**: Retention period, compliance checks

**Automatic Detection**:
- StatefulSets (PostgreSQL, MongoDB, Redis, Kafka)
- PVC snapshot status
- Cross-region replication
- Velero/Stash backup job status

### 4. Analysis Wizard
Four-step intuitive wizard structure:
- **Step 1**: Scope selection (Cluster, Namespace, Deployment, Pod, Label)
- **Step 2**: Gadget module selection (Network, DNS, TCP, Process, Syscall, File)
- **Step 3**: Time and profile settings
- **Step 4**: Output and integration configuration

### 5. Change Detection & Anomaly Detection
- Detects new and lost connections
- Monitors traffic increases and decreases
- Analyzes suspicious patterns with AI
- Reports unknown service communication
- Alerts on policy violations (unexpected port/protocol)

### 6. Governance Automation & Policy-as-Code
**Automatic policy checks with CI/CD integration**:

**Pre-Deployment Checks:**
- Network policy coverage
- Breaking change detection
- Dependency health check
- Pod security standards compliance
- Resource limits validation

**Admission Controller**: Deployment-time validation via Kubernetes webhook

**CI/CD Plugins**: GitHub Actions, GitLab CI, Jenkins, ArgoCD, FluxCD

**Policy as Code**: Custom policy definitions in YAML:
```yaml
rules:
  - name: require-network-policy
    severity: critical
  - name: max-blast-radius
    condition: affectedServices < 10
```

### 7. Natural Language Queries & Explainable AI
**Ask in natural language, get AI-powered answers**:

**Example Queries:**
- "Show me all external connections from payment service"
- "Why is checkout-service slow today?"
- "What happens if I delete redis-cache?"
- "Find all services without network policies"

**Grounded AI Responses**:
- Data sources shown for every claim
- Evidence-based (eBPF, Kubernetes API, Prometheus)
- Confidence score (0–100%)
- Actionable recommendations
- Full traceability

**AI-Assisted Troubleshooting:**
- Interactive debugging
- Root cause analysis
- Step-by-step investigation
- Proactive insights and recommendations

### 8. Import / Export
Two supported formats:
- **Format 1 - CSV**: Human-readable, ideal for analysis
- **Format 2 - Graph JSON**: System format, Neo4j-compatible, re-importable

Features:
- Manual and automatic periodic export
- Single-file or batch import
- Merge or overwrite with existing map
- Snapshot versioning

### 9. Multi-Cluster / Multi-Domain
- Manage multiple Kubernetes/OpenShift clusters from a single interface
- Isolated or merged views
- Domain-based filtering
- Role-based access control

### 10. Comprehensive Dashboards
- **Main Dashboard**: Overall system metrics, anomaly counts, risk scores
- **Application Dependency**: Upstream/downstream view, critical dependencies
- **Traffic & Behavior**: Time-based traffic charts, normal vs. abnormal comparison
- **Security & Risk**: Open ports, unexpected communication, policy recommendations
- **Change Timeline**: Daily/weekly changes, topology drift rate
- **Audit & Activity**: User actions, analysis history, import/export logs

## 🏗️ Technical Architecture (Brief)

### Data Layer
- **ClickHouse**: High-performance OLAP database for metrics and time-series data
- **PostgreSQL**: Relational data (users, configuration, metadata)
- **Redis**: Cache and real-time metrics
- **Neo4j**: Graph database for dependency maps

### Application Layer
- **Backend**: Python + FastAPI
  - User management, RBAC
  - Analysis orchestration
  - Import/export operations
  - LLM integration
  - Scheduler
  - Graph & DB queries
- **Frontend**: ReactJS + Ant Design + Cytoscape.js

### Data Collection
- **Inspektor Gadget**: Runs as a DaemonSet on every node
- Passive by default; active only when analysis is started
- Kernel-level data collection with eBPF (near-zero overhead)

## 🔒 Security and Authorization

### Multi-Tenant Architecture
- Isolation by cluster and namespace
- Data separation and privacy guarantees

### RBAC Roles
- **Super Admin**: Full system control
- **Platform Admin**: Platform management
- **Security Analyst**: Security analysis and reporting
- **Developer**: Read-only access

### Authentication
- OAuth 2.0 / SSO integration
- Kubernetes Service Account Authentication
- API Key support

## 📊 Use Cases

### Scenario 1: Microservice Dependency Documentation
A development team deploys a new service. Flowfish automatically:
- Detects which services it connects to
- Shows which ports and protocols it uses
- Updates the dependency map
- Computes the risk score

### Scenario 2: Security Incident Detection
A pod suddenly connects to an unknown external IP. Flowfish:
- Detects the new connection immediately
- Runs anomaly analysis with the LLM
- Alerts the Security Analyst
- Reports the relevant pod and namespace information

### Scenario 3: Network Policy Testing
The platform team wants to apply a new network policy. With Flowfish:
- Current traffic patterns are recorded as a baseline
- Changes are tested with the policy simulator
- Affected connections are shown
- Post-apply changes are compared

### Scenario 4: Incident Troubleshooting
A service is down in production. Flowfish:
- Shows traffic changes over the last 24 hours
- Lists lost connections
- Checks the status of dependent services
- Helps find the root cause quickly

### Scenario 5: Change Advisory Process (CAP) Automation
The DevOps team wants to upgrade payment-service from v2.3 to v2.5. With Flowfish CAP integration:
- Automatic impact analysis: 12 upstream, 8 downstream services affected
- Breaking API change detected (checkout-service incompatible)
- Risk score: 65 (High) — Security Lead and Change Manager approval required
- Recommendations: Upgrade checkout-service first, use canary deployment
- Automatic Change Request created in ServiceNow
- After approvals: Automatic deployment + post-change validation
- If error rate exceeds 5%: Automatic rollback to v2.3

## 📈 Competitive Advantages

| Feature | Flowfish | Traditional APM | Service Mesh |
|---------|----------|-----------------|--------------|
| **Setup Complexity** | Low (DaemonSet) | Medium–High | High |
| **Application Change** | None | Agent install | Sidecar injection |
| **Performance Overhead** | Minimal (eBPF) | Medium | Medium–High |
| **Dependency Map** | ✅ Automatic | ❌ Manual | ✅ Automatic |
| **Historical Analysis** | ✅ Full history | ⚠️ Limited | ⚠️ Limited |
| **What-If Analysis** | ✅ Yes | ❌ No | ❌ No |
| **Multi-Cluster** | ✅ Native | ⚠️ Via add-on | ⚠️ Via add-on |
| **AI Anomaly Detection** | ✅ LLM integrated | ❌ No | ❌ No |

## 🎯 Target Users

### Primary
- **Platform/DevOps Teams**: Kubernetes/OpenShift infrastructure management
- **Security Operations Center (SOC)**: Security monitoring and anomaly detection
- **Site Reliability Engineers (SRE)**: System reliability and troubleshooting

### Secondary
- **Application Developers**: Understanding microservice dependencies
- **Compliance/Audit Teams**: Network communication auditing and reporting
- **Architecture Teams**: System design and documentation

## 🌟 Success Metrics

### Technical Metrics
- Dependency discovery accuracy: 99%+
- Real-time data latency: <5 seconds
- Graph query performance: <1 second
- Supported cluster size: 10,000+ pods

### Business Metrics
- 70% reduction in incident resolution time
- 90% reduction in manual documentation burden
- 80% improvement in security incident detection time
- 95% increase in confidence in network policies

## 🛣️ Roadmap (Summary)

### Phase 1 - MVP (0–3 months)
Core platform, automatic discovery, real-time map, wizard, basic dashboards

### Phase 2 - Advanced Features (4–6 months)
Historical analysis, anomaly detection, import/export, risk scores, multi-cluster

### Phase 3 - Enterprise Features (7–9 months)
What-if analysis, Change Simulation (CAP), advanced AI/ML, compliance reports, custom dashboards

## 📞 Contact and Support

**Project Name**: Flowfish  
**Version**: 1.0.0 (Design Phase)  
**Platform**: Kubernetes / OpenShift  
**License**: TBD (Enterprise/Commercial)

---

**With Flowfish, communication between your microservices is no longer invisible!** 🐟🌊

