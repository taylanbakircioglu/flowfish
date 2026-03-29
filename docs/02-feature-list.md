# Flowfish - Detailed Feature List

This document describes all Flowfish platform features in detail, organized by phase.

## 📋 Table of Contents

- [Phase 1: MVP (Minimum Viable Product)](#phase-1-mvp-minimum-viable-product)
- [Phase 2: Advanced Features](#phase-2-advanced-features)
- [Phase 3: Enterprise Features](#phase-3-enterprise-features)

---

## Phase 1: MVP (Minimum Viable Product)

**Target Timeline**: 0-3 months  
**Status**: Design Phase  
**Goal**: Complete core platform infrastructure and core features

### 1.1. Inspektor Gadget Integration and Data Collection

#### 1.1.1. Inspektor Gadget Installation
- ✅ Deployed to Kubernetes/OpenShift cluster as a DaemonSet
- ✅ Automatic loading of eBPF programs on each node
- ✅ Kernel compatibility checks and version management
- ✅ Resource limits and requests definition
- ✅ Health checks and liveness probes

#### 1.1.2. Gadget Modules
**Network Traffic Gadget:**
- TCP/UDP connection tracking
- Source/destination IP and port information
- Packet count and byte transfer metrics
- Connection duration tracking

**DNS Gadget:**
- DNS query and response logging
- Query type (A, AAAA, CNAME, etc.)
- Response code tracking
- Latency measurement

**TCP Connections Gadget:**
- TCP connection lifecycle (SYN, ACK, FIN)
- Connection state tracking
- Retransmission count
- Window size monitoring

**Process Events Gadget:**
- Process creation and termination
- Process tree (parent-child relationship)
- Binary path and arguments
- User and group information

**Syscall Tracking Gadget:**
- Network-related syscalls (socket, connect, bind, listen)
- File-related syscalls (open, read, write)
- Syscall frequency and latency
- Error rate tracking

**File Access Gadget:**
- File open/read/write events
- File path and permissions
- Access patterns
- Security-sensitive file monitoring

#### 1.1.3. Data Collection Control
- ✅ No data collection by default (privacy-first)
- ✅ Active only when the user starts an analysis
- ✅ Scope-based collection (cluster, namespace, workload selection)
- ✅ Start/stop analysis control
- ✅ Resource usage monitoring and throttling

### 1.2. Kubernetes Resource Discovery and Communication Detection

#### 1.2.1. Workload Discovery
**Pod Discovery:**
- Pod name, namespace, labels, annotations
- Container list and image information
- Node placement information
- Owner reference (Deployment, StatefulSet, etc.)
- Pod IP and port bindings
- Resource requests and limits

**Deployment Discovery:**
- Deployment name, namespace, labels
- Replica count (desired vs actual)
- Selector labels
- Strategy (RollingUpdate, Recreate)
- Deployment conditions and status

**StatefulSet Discovery:**
- StatefulSet name, namespace, labels
- Replica count and pod naming pattern
- Persistent Volume Claims
- Service name association
- Update strategy

**Service Discovery:**
- Service name, namespace, labels
- Service type (ClusterIP, NodePort, LoadBalancer)
- Cluster IP and external IP
- Port mappings (port, targetPort, protocol)
- Selector labels
- Endpoint addresses

#### 1.2.2. Communication Discovery
**Connection Tracking:**
- Source workload (pod/deployment/service)
- Destination workload
- Source IP:Port → Destination IP:Port
- Protocol (TCP, UDP, HTTP, HTTPS, gRPC, etc.)
- First seen timestamp
- Last seen timestamp
- Request count and frequency (requests/second)
- Average payload size (bytes)
- Average latency (milliseconds) - optional
- Namespace crossing detection
- Cluster crossing detection (multi-cluster)

**Metadata Enrichment:**
- Kubernetes labels and annotations
- Service mesh labels (Istio, Linkerd)
- Custom tags
- Application tier (frontend, backend, database)
- Environment (production, staging, development)

#### 1.2.3. Risk & Importance Scoring
**Risk Factors:**
- Cross-namespace communication (medium risk)
- External egress traffic (high risk)
- Unknown destination IP (high risk)
- Privileged port usage (<1024)
- Unexpected protocol usage
- High request frequency

**Risk Levels:**
- 🟢 Low (0-30): Normal internal communication
- 🟡 Medium (31-60): Cross-namespace, elevated ports
- 🔴 High (61-100): External, unknown, privileged

**Importance Factors:**
- Request frequency
- Number of dependent services
- Critical service labels
- Production environment
- SLA tier

#### 1.2.4. Pod & Deployment Annotations
- Full annotation support, including automatic merge of Deployment/StatefulSet annotations into pods
- Annotation filtering for internal Kubernetes prefixes

### 1.3. Real-Time Dependency Map

#### 1.3.1. Graph Data Model
**Vertex (Node) Types:**
- Pod node
- Deployment node
- StatefulSet node
- Service node
- Namespace node (grouping)

**Edge (Relationship) Types:**
- COMMUNICATES_WITH (directed edge)
- PART_OF (pod → deployment/statefulset)
- EXPOSES (service → deployment/statefulset)
- RUNS_ON (pod → node) - optional

**Node Properties:**
- Name, namespace, type
- Labels, annotations
- Status (running, pending, failed)
- Resource usage (CPU, memory)
- Creation timestamp

**Edge Properties:**
- Port, protocol
- Request count
- Latency (avg, p50, p95, p99)
- First/last seen
- Data transfer (bytes in/out)
- Error rate
- Risk score

#### 1.3.2. Graph Visualization
**Cytoscape.js Integration:**
- Node rendering (different shapes: pod=circle, deployment=square, service=diamond)
- Node coloring (namespace-based, status-based, risk-based)
- Edge rendering (thickness by request count, color by protocol)
- Edge animation (live traffic flow)
- Layout algorithms:
  - Hierarchical (tier-based: frontend → backend → database)
  - Force-directed (physics simulation)
  - Circular
  - Grid
  - Manual positioning

**Interactivity:**
- Node click → Detail panel
- Node hover → Quick info tooltip
- Edge click → Communication details
- Multi-select (Ctrl+Click)
- Zoom and pan
- Minimap navigator
- Search and filtering

**Export:**
- PNG/JPG image export
- SVG vector export
- JSON export
- PDF export

### 1.4. Cluster and Namespace Management

#### 1.4.1. Multi-Cluster Support
**Cluster Management:**
- Add cluster (Kubernetes, OpenShift)
- Connection types:
  - In-cluster (platform runs inside the cluster itself)
  - Kubeconfig file
  - Service Account token
  - API server URL + credentials
- Cluster health monitoring
- Cluster metadata:
  - Name, description
  - Kubernetes version
  - Node count
  - Pod count
  - Namespace count

**Cluster Selector:**
- Top navigation bar dropdown
- Quick cluster switching
- Default cluster configuration
- Cluster-specific dashboards

#### 1.4.2. Namespace Management
- Namespace list and filtering
- Namespace metadata display
- Namespace-based access control
- Namespace label management
- Cross-namespace communication tracking

### 1.5. Analysis Wizard

#### Step 1: Scope Selection
**Selectable Levels:**

**Cluster-level:**
- Cover all namespaces
- Cluster-wide visibility
- Use case: Full platform analysis

**Namespace-level:**
- Select specific namespace(s)
- Multiple namespace selection
- Use case: Application-specific analysis

**Workload-level:**
- Specific Deployment(s)
- Specific StatefulSet(s)
- Specific Pod(s)
- Use case: Targeted troubleshooting

**Label-based (Advanced):**
- Label selector (app=frontend, tier=backend)
- Multiple label combinations
- Exclude labels
- Use case: Complex filtering

**Hierarchical Selection:**
- When a namespace is selected → all workloads under it are included automatically
- When a Deployment is selected → replica pods are included automatically

#### Step 2: Gadget Module Selection
**Module List:**
- ☑️ Network Traffic (TCP/UDP connections)
- ☑️ DNS Queries
- ☑️ TCP Connection State
- ☑️ Process Events
- ☑️ Syscall Tracking
- ☑️ File Access

**Per Module:**
- Enable/Disable toggle
- Configuration options:
  - Sampling rate (1/1, 1/10, 1/100)
  - Filter rules (port ranges, protocols)
  - Data retention period
- Estimated resource usage display
- Recommended presets (Light, Medium, Heavy)

#### Step 3: Time & Profile Settings
**Analysis Modes:**

**Continuous Analysis:**
- Runs continuously after start
- Real-time data collection
- Stopped with Stop button
- Use case: Production monitoring

**Time-bound Analysis:**
- Start time, end time selection
- Duration: 5 min, 15 min, 1 hour, 4 hours, 24 hours
- Automatic stop
- Use case: Troubleshooting, incident analysis

**Scheduled Analysis (Periodic):**
- Scheduling via cron expression
- Daily, weekly, monthly presets
- Timezone selection
- Use case: Regular audits, compliance

**Baseline Creation Mode (Profile Creation):**
- Learn “normal” traffic profile over a defined period
- Minimum duration: 24 hours
- Recommended: 7 days
- Use case: Anomaly detection baseline

**Profile Settings:**
- Select existing baseline
- Create baseline
- Update baseline
- Compare with baseline

#### Step 4: Output & Integration
**Dashboard Selection:**
- ☑️ Main Dashboard
- ☑️ Application Dependency Dashboard
- ☑️ Traffic & Behavior Dashboard
- ☑️ Security & Risk Dashboard
- ☑️ Change Timeline Dashboard

**LLM Analysis:**
- ☑️ Enable LLM anomaly detection
- LLM provider selection:
  - OpenAI GPT-4
  - Azure OpenAI
  - Anthropic Claude
  - Custom endpoint (OpenAI-compatible)
- API key configuration
- Analysis frequency (15 min, 30 min, 1 hour)
- Prompt customization

**Alarm & Webhook:**
- ☑️ Enable alerting
- Webhook URL configuration
- Alert conditions:
  - New connections
  - Lost connections
  - Anomaly detected
  - Risk score threshold
  - Traffic spike (% increase)
- Alert format (JSON, Slack, Teams, PagerDuty)

**Report Settings:**
- ☑️ Auto-generate reports
- Report format (PDF, HTML, JSON)
- Report frequency (daily, weekly, monthly)
- Email recipients
- Storage location (S3, Azure Blob, local)

### 1.6. Core Dashboards

#### 1.6.1. Main Dashboard (Home/Overview)
**Metrics:**
- Total application count (pods, deployments, services)
- Total connection count (active vs historical)
- Active anomaly count
- Active change event count
- Most communicating services (top 10)
- Highest risk score applications (top 10)
- Cluster health overview
- Namespace distribution pie chart

**Widgets:**
- Real-time traffic rate (requests/second)
- Total data transfer (MB/s in/out)
- Protocol distribution (TCP, UDP, HTTP, gRPC)
- Top source namespaces
- Top destination namespaces
- Recent alerts timeline

#### 1.6.2. Live Map Dashboard
**Main View:**
- Interactive graph visualization
- Real-time updates (5-second refresh)
- Smooth animations
- Node clustering by namespace
- Edge bundling for clarity

**Controls:**
- Layout selection (dropdown)
- Filter panel (slide-out)
- Search box
- Zoom controls (+/-)
- Fit to screen button
- Lock/unlock node positions
- Show/hide labels
- Show/hide edge labels

**Filter Options:**
- Namespace multi-select
- Workload type (pod, deployment, service)
- Protocol filter
- Risk level filter
- Request count threshold
- Latency threshold
- Time range

**Detail Panel:**
- Selected node information
- Incoming connections list
- Outgoing connections list
- Resource usage charts
- Labels and annotations
- Logs link (integration with logging system)
- Metrics link (integration with Prometheus/Grafana)

### 1.7. User Management and RBAC

#### 1.7.1. User Management
**User CRUD:**
- Create user (username, email, password)
- Update user profile
- Delete user (soft delete)
- User status (active, inactive, locked)
- Password reset (self-service + admin)
- User groups

**User Profile:**
- First name, last name
- Email address
- Avatar/profile picture
- Timezone
- Language preference
- Notification preferences

#### 1.7.2. Role-Based Access Control
**Predefined Roles:**

**Super Admin:**
- Full system access
- User management
- Cluster management
- System configuration
- Audit log access
- LLM configuration
- Billing & usage monitoring

**Platform Admin:**
- Cluster management (add/remove)
- Namespace management
- Integration configuration
- Dashboard management
- User role assignment (except Super Admin)
- Audit log access (read-only)

**Security Analyst:**
- View all dashboards
- Anomaly detection management
- Change detection management
- Risk score configuration
- Security reports
- Alert configuration
- Export data (CSV, JSON)

**Developer (Read-Only):**
- View dashboards (limited)
- View dependency maps
- View application inventory
- View own namespace only
- No configuration access
- No export capability

**Custom Roles:**
- Create custom roles
- Permission matrix selection
- Role naming and description
- Role assignment

#### 1.7.3. Permissions
**Granular Permissions:**
- `clusters.view`, `clusters.create`, `clusters.edit`, `clusters.delete`
- `namespaces.view`, `namespaces.create`, `namespaces.edit`, `namespaces.delete`
- `analyses.view`, `analyses.create`, `analyses.edit`, `analyses.delete`, `analyses.execute`
- `dependencies.view`, `dependencies.export`
- `anomalies.view`, `anomalies.manage`
- `changes.view`, `changes.manage`
- `users.view`, `users.create`, `users.edit`, `users.delete`
- `roles.view`, `roles.create`, `roles.edit`, `roles.delete`
- `settings.view`, `settings.edit`
- `audit.view`

### 1.8. Authentication

#### 1.8.1. OAuth 2.0 / SSO
**Supported Providers:**
- Google OAuth
- Microsoft Azure AD / Entra ID
- Okta
- Auth0
- Keycloak
- GitHub
- GitLab

**Configuration:**
- Client ID and Client Secret
- Authorization endpoint
- Token endpoint
- User info endpoint
- Scope configuration
- Redirect URI

**Flow:**
1. User clicks "Login with [Provider]"
2. Redirect to provider
3. User authenticates
4. Callback to Flowfish with auth code
5. Exchange code for access token
6. Fetch user info
7. Create/update user in Flowfish
8. Generate JWT token
9. Redirect to dashboard

#### 1.8.2. Kubernetes Service Account
**In-Cluster Authentication:**
- Service Account token mount
- Automatic user creation from SA
- Namespace-based role mapping
- Label-based permission mapping

**External Cluster:**
- Kubeconfig import
- Token extraction
- User mapping based on cluster role
- Certificate authentication

#### 1.8.3. JWT Token Management
- Access token (short-lived, 1 hour)
- Refresh token (long-lived, 7 days)
- Token revocation
- Token blacklist (Redis)
- Session management

#### 1.8.4. API Key Management
- API key creation, expiration, and revocation for programmatic access alongside JWT authentication

### 1.9. Core API Endpoints

**Authentication:**
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

**Clusters:**
- `GET /api/v1/clusters`
- `POST /api/v1/clusters`
- `GET /api/v1/clusters/{id}`
- `PUT /api/v1/clusters/{id}`
- `DELETE /api/v1/clusters/{id}`

**Namespaces:**
- `GET /api/v1/clusters/{id}/namespaces`
- `GET /api/v1/clusters/{id}/namespaces/{namespace}`

**Workloads:**
- `GET /api/v1/clusters/{id}/workloads`
- `GET /api/v1/clusters/{id}/pods`
- `GET /api/v1/clusters/{id}/deployments`
- `GET /api/v1/clusters/{id}/statefulsets`
- `GET /api/v1/clusters/{id}/services`

**Analyses:**
- `GET /api/v1/analyses`
- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{id}`
- `PUT /api/v1/analyses/{id}`
- `DELETE /api/v1/analyses/{id}`
- `POST /api/v1/analyses/{id}/start`
- `POST /api/v1/analyses/{id}/stop`

**Communications:**
- `GET /api/v1/communications`
- `GET /api/v1/communications/{id}`

**Dependencies:**
- `GET /api/v1/dependencies/graph`
- `GET /api/v1/dependencies/map`

---
## Phase 2: Advanced Features

**Target Timeline**: 4-6 months  
**Status**: Planning Phase  
**Goal**: Advanced analysis and integration features

### 2.1. Historical Dependency Map and Timeline

#### 2.1.1. Historical Map
**Time Travel Capability:**
- Time slider control (drag to select time)
- Date/time picker (specific timestamp)
- Time range selection (from - to)
- Playback mode (animation)
- Speed control (1x, 2x, 5x, 10x)

**Historical Data Storage:**
- ClickHouse time-series data
- Graph snapshots (daily, weekly, monthly)
- Snapshot comparison
- Diff visualization (added/removed/changed)

**Use Cases:**
- Incident investigation: "What was the network topology at 03:00 AM?"
- Change impact analysis: "What changed after deployment?"
- Capacity planning: "How did traffic grow over last 3 months?"
- Compliance audit: "Show all communications in Q1 2024"

#### 2.1.2. Timeline Dashboard
**Visualization:**
- Horizontal timeline with events
- Event types:
  - New connection detected
  - Connection lost
  - Traffic spike
  - Anomaly detected
  - Deployment event
  - Configuration change
- Event markers with tooltips
- Event filtering by type
- Event search

**Integration:**
- Kubernetes events (deployments, rollouts, failures)
- Git commits (CI/CD integration)
- Change tickets (Jira, ServiceNow)
- Incident tickets
- Maintenance windows

### 2.2. Change Detection

#### 2.2.1. Change Types
**Connection Changes:**
- ➕ New connections (added)
- ➖ Lost connections (removed)
- 🔄 Modified connections (port/protocol change)
- 📈 Traffic increase (>50% increase)
- 📉 Traffic decrease (>50% decrease)

**Workload Changes:**
- New pods deployed
- Pods terminated
- Deployment scaled up/down
- Service configuration changed
- Labels/annotations modified

**Network Changes:**
- New external endpoints
- DNS resolution changes
- Certificate changes
- Network policy updates

#### 2.2.2. Change Detection Rules
**Rule Configuration:**
- Threshold settings (traffic increase %, connection count)
- Time window (compare last 1 hour vs previous 1 hour)
- Baseline comparison (current vs baseline)
- Whitelist (ignore expected changes)
- Blacklist (always alert on specific changes)

**Notification:**
- Real-time alerts
- Daily digest email
- Slack/Teams notification
- PagerDuty integration
- Webhook POST

#### 2.2.3. Change Dashboard
**Metrics:**
- Total changes today/week/month
- Changes by type (pie chart)
- Changes by namespace (bar chart)
- Change trend (line chart)
- Top changing workloads

**Change List:**
- Sortable table
- Filter by type, namespace, time
- Drill-down to details
- Mark as reviewed
- Add comments

### 2.3. Anomaly Detection (LLM Integration)

#### 2.3.1. LLM Configuration
**Supported LLM Providers:**
- OpenAI (GPT-4, GPT-4-turbo)
- Azure OpenAI Service
- Anthropic Claude (3.5 Sonnet, Opus)
- AWS Bedrock
- Google Vertex AI
- Self-hosted (OpenAI-compatible API)

**Configuration Parameters:**
- API endpoint URL
- API key / credentials
- Model selection
- Temperature (0.0 - 1.0)
- Max tokens
- Request timeout
- Rate limiting
- Cost tracking

#### 2.3.2. Anomaly Detection Pipeline
**Data Preparation:**
1. Baseline data export (JSON format)
2. Recent data export (last 15 min / 1 hour)
3. Change diff calculation
4. Context enrichment (labels, metadata, previous incidents)

**LLM Prompt Structure:**
```
System: You are a Kubernetes network security analyst...

Baseline Network Communication (Last 7 days):
[JSON data]

Recent Network Communication (Last 15 minutes):
[JSON data]

Changes Detected:
[Diff data]

Task: Analyze the recent communication pattern and identify any anomalies, 
security concerns, or unexpected behaviors. For each anomaly, provide:
1. Anomaly score (0-100)
2. Severity (low, medium, high, critical)
3. Description
4. Affected workloads
5. Recommended action
6. Confidence level (%)
```

**LLM Response Parsing:**
- JSON response extraction
- Anomaly score normalization
- Severity mapping
- Action item extraction
- Confidence threshold filtering (>70%)

#### 2.3.3. Anomaly Types
**Network Anomalies:**
- Unknown destination IP (external)
- Unusual port usage
- Protocol violation
- Unexpected connection direction (ingress from untrusted)
- DNS exfiltration patterns
- Beaconing behavior (periodic external connections)

**Behavioral Anomalies:**
- Traffic spike (sudden increase)
- Traffic drop (unexpected decrease)
- Latency anomaly (sudden slowdown)
- Error rate increase
- Retry storm
- Connection churn (frequent connect/disconnect)

**Security Anomalies:**
- Privilege escalation attempt
- Lateral movement
- Data exfiltration (high outbound traffic)
- Cryptomining pattern (CPU + network)
- Unauthorized service access
- Compliance violation

#### 2.3.4. Anomaly Dashboard
**Overview:**
- Active anomalies count
- Anomalies by severity (pie chart)
- Anomaly trend (last 24 hours)
- Top affected namespaces
- Top affected workloads

**Anomaly List:**
- Sortable table (severity, score, time)
- Filter by severity, type, namespace
- Status: new, investigating, resolved, false-positive
- Assign to user
- Add comments and notes
- Link to incident ticket

**Anomaly Details:**
- Anomaly score and severity
- AI-generated description
- Affected workloads (graph visualization)
- Related connections
- Timeline (when detected, how long)
- LLM reasoning (show prompt + response)
- Recommended actions
- Playbook suggestions
- Similar past anomalies

### 2.4. Import / Export

#### 2.4.1. Export Formats

**Format 1: CSV (Human-Readable)**
```csv
source_cluster,source_namespace,source_workload,source_type,destination_cluster,destination_namespace,destination_workload,destination_type,port,protocol,request_count,avg_latency_ms,first_seen,last_seen,risk_score
cluster-prod,frontend,web-app,deployment,cluster-prod,backend,api-service,service,8080,HTTP,125430,45.3,2024-01-15T10:00:00Z,2024-01-15T18:00:00Z,25
```

**Fields:**
- Source: cluster, namespace, workload name, workload type
- Destination: cluster, namespace, workload name, workload type
- Communication: port, protocol
- Metrics: request_count, avg_latency_ms, bytes_transferred
- Timestamps: first_seen, last_seen
- Analysis: risk_score, importance_score

**Use Cases:**
- Excel analysis
- Data science / ML
- Reporting
- Compliance audit

**Format 2: Graph JSON (System Format)**
```json
{
  "version": "1.0",
  "exported_at": "2024-01-15T18:30:00Z",
  "cluster_id": "cluster-prod",
  "snapshot_id": "snapshot-20240115-183000",
  "nodes": [
    {
      "id": "node-1",
      "type": "deployment",
      "name": "web-app",
      "namespace": "frontend",
      "labels": {"app": "web", "tier": "frontend"},
      "metadata": {...}
    },
    ...
  ],
  "edges": [
    {
      "id": "edge-1",
      "source": "node-1",
      "target": "node-2",
      "type": "COMMUNICATES_WITH",
      "port": 8080,
      "protocol": "HTTP",
      "metrics": {...}
    },
    ...
  ],
  "metadata": {
    "total_nodes": 150,
    "total_edges": 420,
    "time_range": {...}
  }
}
```

**Properties:**
- Neo4j-compatible format
- Full node and edge details
- Metadata and metrics
- Versioned format
- Re-importable

#### 2.4.2. Export Operations
**Manual Export:**
- Export button in UI
- Format selection (CSV / Graph JSON)
- Scope selection:
  - Current view
  - Specific namespace
  - Entire cluster
  - Time range
- Download immediately

**Scheduled Export:**
- Cron schedule configuration
- Format selection
- Destination:
  - Local file system
  - S3 bucket
  - Azure Blob Storage
  - Google Cloud Storage
  - FTP/SFTP server
- Retention policy (keep last N files)
- Notification on completion

**API Export:**
- `GET /api/v1/export/csv?cluster_id=X&namespace=Y&time_range=...`
- `GET /api/v1/export/graph?cluster_id=X&format=json`
- Streaming response for large datasets
- Compression support (gzip)
- Authentication via API key

#### 2.4.3. Import Operations
**Single File Import:**
- Upload CSV or Graph JSON
- Validation:
  - Schema validation
  - Data type checking
  - Duplicate detection
  - Missing reference checking
- Preview before import
- Import mode selection:
  - Merge (add to existing)
  - Overwrite (replace existing)
  - Create new snapshot
- Progress indicator
- Error handling and rollback

**Batch Import:**
- Upload multiple files
- Zip archive support
- Parallel processing
- Batch validation
- Batch import report (success/failure per file)

**Import Options:**
- Timestamp handling:
  - Use original timestamps
  - Use import timestamp
  - Offset timestamps
- Conflict resolution:
  - Keep existing
  - Overwrite with imported
  - Create duplicate with suffix
  - Prompt user
- Namespace mapping (rename on import)
- Label filtering (import only matching labels)

#### 2.4.4. Snapshot Versioning
**Snapshot Management:**
- Automatic snapshot creation:
  - Daily snapshots (keep 30 days)
  - Weekly snapshots (keep 12 weeks)
  - Monthly snapshots (keep 12 months)
- Manual snapshot creation
- Snapshot naming and tagging
- Snapshot metadata:
  - Creation time
  - Cluster state
  - Node/edge counts
  - Storage size
- Snapshot comparison tool
- Snapshot restore

**Version Control:**
- Import creates new version
- Version numbering (v1.0, v1.1, v2.0)
- Version tags (production, staging, backup)
- Version diff tool
- Version rollback

### 2.5. Risk Scores

#### 2.5.1. Risk Scoring Model
**Risk Factors (Weighted):**
- External communication (weight: 40)
  - Internet egress: +40
  - Unknown IP: +30
  - Public cloud IPs: +20
- Cross-namespace communication (weight: 20)
  - Different namespace: +20
  - System namespace: +30
- Port usage (weight: 15)
  - Privileged ports (<1024): +15
  - Non-standard ports: +10
- Protocol (weight: 10)
  - Unencrypted (HTTP, FTP): +10
  - Unknown protocol: +15
- Request patterns (weight: 10)
  - Very high frequency: +10
  - Irregular patterns: +15
- Security context (weight: 5)
  - Privileged pod: +5
  - Root user: +5

**Calculation:**
```
Risk Score = Σ (Factor Value × Factor Weight) / Total Weight × 100
Range: 0-100
```

**Risk Levels:**
- 🟢 Low (0-30): Normal, expected traffic
- 🟡 Medium (31-60): Review recommended
- 🟠 High (61-80): Action required
- 🔴 Critical (81-100): Immediate attention

#### 2.5.2. Importance Scoring
**Importance Factors:**
- Request volume (requests/hour)
- Number of dependents (how many services depend on this)
- Criticality labels (critical=true, tier=1)
- SLA tier (platinum, gold, silver)
- Production environment
- Customer-facing service

**Importance Levels:**
- ⬇️ Low: <5 dependents, non-prod
- ➡️ Medium: 5-20 dependents, staging
- ⬆️ High: 20-50 dependents, prod
- 🔥 Critical: >50 dependents, customer-facing

#### 2.5.3. Risk Dashboard
**Metrics:**
- Total services by risk level (stacked bar)
- High-risk services list
- Risk trend over time
- Risk by namespace
- Risk by protocol
- Risk by destination type

**Risk Mitigation:**
- Recommended network policies
- Port restrictions
- TLS enforcement recommendations
- Firewall rules

### 2.6. Baseline Creation

#### 2.6.1. Baseline Creation
**Learning Period:**
- Minimum: 24 hours
- Recommended: 7 days
- Maximum: 30 days

**Data Collection:**
- All communications
- Request patterns (frequency, volume)
- Latency patterns
- Error rates
- Active hours (time-of-day patterns)
- Day-of-week patterns

**Baseline Profiles:**
- Per namespace
- Per workload
- Per environment (prod, staging, dev)

#### 2.6.2. Baseline Storage
**Profile Data:**
```json
{
  "baseline_id": "baseline-2024-01-15",
  "created_at": "2024-01-15T00:00:00Z",
  "learning_period_days": 7,
  "namespace": "backend",
  "workload": "api-service",
  "communication_patterns": [
    {
      "destination": "database-service",
      "port": 5432,
      "protocol": "PostgreSQL",
      "avg_requests_per_hour": 1250,
      "std_dev": 180,
      "avg_latency_ms": 12.5,
      "active_hours": [8, 9, 10, ..., 22]
    }
  ],
  "allowed_destinations": [...],
  "typical_protocols": [...],
  "typical_ports": [...]
}
```

#### 2.6.3. Baseline Comparison
**Deviation Detection:**
- Request volume deviation (>2 standard deviations)
- New destinations (not in baseline)
- New protocols (not in baseline)
- New ports (not in baseline)
- Latency spike (>3x baseline average)
- Off-hours activity (outside baseline active hours)

**Comparison Dashboard:**
- Current vs baseline (side-by-side)
- Deviation score per workload
- Top deviations list
- Deviation timeline
- Drill-down to specific deviations

### 2.7. Advanced Filtering and Layered View

#### 2.7.1. Advanced Filters
**Multi-dimensional Filtering:**
- Namespace (multi-select, regex)
- Workload type (pod, deployment, service, statefulset)
- Labels (key-value pairs, AND/OR logic)
- Annotations (key-value pairs)
- Node (which k8s node)
- Risk level (low, medium, high, critical)
- Protocol (TCP, UDP, HTTP, HTTPS, gRPC, etc.)
- Port range (1-1024, 8000-9000)
- Request count range (>1000, <100)
- Latency range (>100ms, <10ms)
- Time range (custom date/time picker)

**Filter Presets:**
- Save current filters as preset
- Load saved preset
- Share preset with team
- System presets:
  - High-risk communications
  - External traffic only
  - Cross-namespace only
  - Production only
  - Slow connections (high latency)

#### 2.7.2. Logical View (Tier-based)
**Application Tiers:**
- Frontend tier (web, mobile-api)
- Backend tier (api, microservices)
- Data tier (database, cache)
- Integration tier (message queue, event bus)
- External tier (3rd party APIs, CDN)

**Auto-classification:**
- Based on labels (tier=frontend)
- Based on naming (web-*, api-*, db-*)
- Based on connections (talks to DB → backend)
- Manual override

**Visualization:**
- Hierarchical layout (top-to-bottom: frontend → backend → data)
- Tier grouping (collapse/expand)
- Inter-tier connections emphasized
- Intra-tier connections dimmed

#### 2.7.3. Physical View
**Node-based Layout:**
- Group pods by Kubernetes node
- Show node capacity (CPU, memory)
- Show pod distribution
- Highlight cross-node traffic
- Show node-to-node bandwidth

**Namespace-based Layout:**
- Group by namespace (boundaries)
- Show namespace network policies
- Highlight cross-namespace traffic
- Show namespace quotas

**Zone/Region Layout (Multi-cluster):**
- Group by availability zone
- Group by region
- Show cross-zone/region traffic
- Show latency by distance

### 2.8. Multi-Cluster / Multi-Domain Support

#### 2.8.1. Domain Management
**Domain Definition:**
- Domain name (e.g., "Production US-East", "Staging EU")
- Cluster list (multiple clusters per domain)
- Description and metadata
- Domain tags

**Domain Types:**
- Single-cluster domain
- Multi-cluster domain (same region)
- Multi-region domain
- Hybrid domain (on-prem + cloud)

#### 2.8.2. Cross-Domain Communication
**Discovery:**
- Cross-cluster service calls (via Istio, Linkerd)
- External endpoints shared between clusters
- DNS-based routing between clusters
- Ingress/egress gateway tracking

**Visualization:**
- Domain boundaries on graph
- Cross-domain edges (thicker, different color)
- Domain selector filter
- Multi-domain view (all domains on one graph)

#### 2.8.3. Unified Dashboard
**Views:**
- Isolated view (single cluster)
- Domain view (all clusters in domain)
- Global view (all domains)

**Aggregation:**
- Total metrics across clusters
- Per-cluster breakdown
- Cross-cluster traffic summary
- Domain-level risk scores

### 2.9. Webhook and SIEM Integration

#### 2.9.1. Webhook Configuration
**Webhook Events:**
- Anomaly detected
- High-risk connection detected
- Change detected (new/lost connection)
- Analysis started/completed
- Import completed
- Threshold breach (custom metrics)

**Webhook Payload:**
```json
{
  "event_type": "anomaly_detected",
  "event_id": "evt-12345",
  "timestamp": "2024-01-15T18:30:00Z",
  "cluster_id": "cluster-prod",
  "namespace": "backend",
  "severity": "high",
  "anomaly": {
    "score": 85,
    "description": "Unusual external connection detected",
    "affected_workload": "api-service",
    "destination_ip": "203.0.113.45",
    "recommended_action": "Block IP and investigate"
  },
  "metadata": {...}
}
```

**Webhook Delivery:**
- HTTP POST request
- Retry logic (exponential backoff)
- Timeout configuration
- Signature verification (HMAC)
- Custom headers support

#### 2.9.2. SIEM Integration
**Supported SIEM Platforms:**
- Splunk (HTTP Event Collector)
- Elasticsearch (Logstash compatible)
- Azure Sentinel (Log Analytics API)
- IBM QRadar (syslog)
- ArcSight (CEF format)
- Generic syslog

**Log Forwarding:**
- Real-time event streaming
- Batch log export
- CEF (Common Event Format)
- JSON format
- Syslog format

**Event Types:**
- Network communication events
- Anomaly events
- Change events
- Security events
- Audit events

### 2.10. Integration Hub
- Four-step guided wizard (Integration Type → Configure → Preview → Integration Code) with two integration paths: Dependency Analysis and Blast Radius Gate
- Configure step: analysis selection, service identification method (Annotation, Label, Namespace + Deployment, Pod Name, Advanced), search depth, live test query
- Preview step: per-service dependency breakdown with expandable matched services, downstream/callers by category, hop distance visualization for multi-depth queries, and aggregate summary
- Integration Code step: tabbed snippet generation (Pipeline YAML, cURL, Python, JavaScript, Blast Radius)
- Dedicated pipeline platforms with platform-specific templates: Azure DevOps, GitHub Actions, GitLab CI, Jenkins, and Other (Generic)
- Blast Radius tab: pre-deployment risk assessment snippets with cross-link to Blast Radius Oracle page
- Theme-aware UI with Ant Design token-based colors for light/dark mode consistency

---
## Phase 3: Enterprise Features

**Target Timeline**: 7-9 months  
**Status**: Conceptual Phase  
**Goal**: Enterprise-ready features and advanced AI/ML capabilities

### 3.1. Policy Simulation (What-If Analysis)

#### 3.1.1. Network Policy Simulation
**Simulation Wizard:**
- Current policy view
- Proposed policy editor (YAML)
- Validation (syntax check)
- Impact analysis:
  - Which connections will be blocked
  - Which workloads will be affected
  - Risk assessment (breaking changes)
- Side-by-side comparison

**Test Scenarios:**
- Block all external traffic
- Block cross-namespace traffic
- Allow-list specific ports
- Deny-list specific IPs
- Require mTLS for specific services

**Simulation Results:**
- Blocked connections count
- Affected workloads list
- Estimated impact (low, medium, high)
- Recommended adjustments
- Rollback plan

#### 3.1.2. Deployment Impact Simulation
**What-If Questions:**
- "What if I delete this deployment?"
- "What if I scale down this service?"
- "What if I update this service's port?"
- "What if I move this pod to another namespace?"

**Impact Analysis:**
- Dependent services list
- Communication breakdown
- Cascading failures prediction
- Alternative routing suggestions

### 3.2. Change Simulation (CAP Integration)

#### 3.2.1. Change Impact Assessment
**Enterprise process integration for change simulation**

**Supported Change Types:**
- **Application Changes:**
  - Container image update (version change)
  - Environment variable changes
  - Resource limits update (CPU, memory)
  - Replica count change (scaling)
  - ConfigMap/Secret updates
  
- **Configuration Changes:**
  - Service port changes
  - Ingress rule updates
  - Volume mount changes
  - Deployment strategy changes
  
- **Infrastructure Changes:**
  - Node maintenance (drain/cordon)
  - Namespace migration
  - Storage class changes
  - Network policy updates

**Impact Analysis Dimensions:**

**1. Dependency Impact:**
- **Upstream Dependencies:**
  - Services that call this service
  - Expected impact on each upstream service
  - Traffic volume that will be affected
  - Alternative routing availability
  
- **Downstream Dependencies:**
  - Services called by this service
  - Compatibility check with downstream versions
  - API version compatibility
  - Breaking changes detection

**2. Traffic Impact:**
- Current traffic patterns (requests/sec)
- Expected traffic interruption duration
- Peak traffic hours conflict check
- Capacity reduction during change
- Estimated downtime window

**3. Data Impact:**
- StatefulSet data migration needs
- PVC mount point changes
- Database schema compatibility
- Data backup requirements
- Data consistency checks

**4. Risk Assessment:**
- **Risk Score (0-100):**
  - Change complexity: 30 points
  - Number of affected services: 25 points
  - Production environment: 20 points
  - Peak hour deployment: 15 points
  - Rollback difficulty: 10 points

- **Risk Categories:**
  - 🟢 Low Risk (0-30): Minor config changes, non-prod
  - 🟡 Medium Risk (31-60): Version updates, moderate impact
  - 🟠 High Risk (61-80): Major version jumps, many dependents
  - 🔴 Critical Risk (81-100): Breaking changes, production-critical services

**5. Blast Radius:**
- Direct impact: Immediate affected services
- Indirect impact: 2nd and 3rd degree dependencies
- Total affected pods count
- Total affected namespaces
- Cross-cluster impact (if multi-cluster)
- Estimated user impact (if available)

#### 3.2.2. Change Advisory Process (CAP) Workflow

**CAP Integration:**

**Change Request Creation:**
```yaml
Change Request:
  ID: CR-2024-001234
  Title: "Update payment-service to v2.5.0"
  Type: Application Update
  Priority: Normal / High / Emergency
  Requester: john.doe@company.com
  Planned Window: 2024-01-20 02:00-04:00 UTC
  
  Current State:
    - Service: payment-service
    - Version: v2.3.1
    - Replicas: 5
    - Dependencies: 12 upstream, 8 downstream
  
  Proposed Change:
    - New Version: v2.5.0
    - Configuration: [env var updates]
    - Resource Changes: [CPU +20%]
  
  Impact Assessment:
    - Risk Score: 65 (High)
    - Affected Services: 12
    - Estimated Downtime: 2 minutes
    - Traffic Impact: 15,000 req/min
    - Rollback Time: < 5 minutes
```

**Approval Workflow:**
```
1. Change Request Submitted
   ↓
2. Automated Impact Analysis (Flowfish)
   - Dependency graph analysis
   - Risk scoring
   - Blast radius calculation
   ↓
3. Pre-Approval Checks
   - No conflicting changes in same window
   - Maintenance window validation
   - Resource availability check
   ↓
4. Stakeholder Notification
   - Notify owners of affected services
   - Auto-generated impact report
   - Request for comments
   ↓
5. Approval Process
   - Technical Lead: Review impact
   - Security Team: Security implications (if high risk)
   - Change Manager: Final approval
   ↓
6. Scheduled Execution
   - Pre-change validation
   - Execute change
   - Post-change validation
   ↓
7. Post-Implementation Review
   - Success/failure status
   - Actual vs predicted impact
   - Lessons learned
```

**Approval Matrix:**

| Risk Level | Approver 1 | Approver 2 | Approver 3 | Emergency Override |
|------------|-----------|-----------|-----------|-------------------|
| Low | Tech Lead | - | - | Tech Lead |
| Medium | Tech Lead | Team Manager | - | Tech Lead + Manager |
| High | Tech Lead | Security Lead | Change Manager | C-Level |
| Critical | Tech Lead | Security Lead | Change Manager + C-Level | Emergency Board |

#### 3.2.3. Change Simulation Dashboard

**Pre-Change Analysis View:**

```
┌─────────────────────────────────────────────────────────────┐
│ Change Request: CR-2024-001234                              │
│ Status: Pending Approval                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Change Summary                                       │    │
│ │                                                      │    │
│ │ Service: payment-service                            │    │
│ │ Type: Image Update                                   │    │
│ │ From: v2.3.1 → To: v2.5.0                          │    │
│ │ Scheduled: 2024-01-20 02:00 UTC                     │    │
│ │ Risk Score: 65 (High Risk) 🟠                       │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Impact Analysis                                      │    │
│ │                                                      │    │
│ │ Directly Affected: 12 services                      │    │
│ │ Indirectly Affected: 23 services                    │    │
│ │ Total Pods Affected: 67                             │    │
│ │ Estimated Downtime: 2-3 minutes                     │    │
│ │ Traffic Impact: 15,000 req/min                      │    │
│ │                                                      │    │
│ │ [View Dependency Graph] [View Traffic Impact]      │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Affected Services (Top 5)                           │    │
│ │                                                      │    │
│ │ 1. 🔴 checkout-service (Critical Dependency)        │    │
│ │    Impact: API breaking change detected            │    │
│ │    Mitigation: Update checkout-service first       │    │
│ │                                                      │    │
│ │ 2. 🟡 order-service (Medium Impact)                 │    │
│ │    Impact: Increased latency expected              │    │
│ │    Mitigation: Monitor performance                 │    │
│ │                                                      │    │
│ │ 3. 🟢 notification-service (Low Impact)             │    │
│ │    Impact: Minimal, async communication            │    │
│ │                                                      │    │
│ │ ... [View All 12 Affected Services]                 │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Risk Factors                                         │    │
│ │                                                      │    │
│ │ ✓ Breaking API changes detected                     │    │
│ │ ✓ Production environment                            │    │
│ │ ✓ High traffic service (>10K req/min)              │    │
│ │ ⚠ Scheduled during business hours                   │    │
│ │ ✓ Multiple dependencies affected                    │    │
│ │ ✓ Rollback plan validated                           │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Recommendations                                      │    │
│ │                                                      │    │
│ │ 🔸 Consider deploying to staging first              │    │
│ │ 🔸 Update checkout-service API compatibility        │    │
│ │ 🔸 Schedule during low-traffic window (02:00 UTC)   │    │
│ │ 🔸 Prepare rollback script (automated)              │    │
│ │ 🔸 Enable canary deployment (10% traffic)           │    │
│ │ 🔸 Monitor error rates closely                      │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Approval Status                                      │    │
│ │                                                      │    │
│ │ ✅ Tech Lead: Approved (John Smith)                 │    │
│ │ ⏳ Security Lead: Pending Review                    │    │
│ │ ⏳ Change Manager: Pending Approval                 │    │
│ │                                                      │    │
│ │ Required: 3/3 approvals                             │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ [ Simulate Again ] [ Request Approval ] [ Edit Change ]    │
└─────────────────────────────────────────────────────────────┘
```

#### 3.2.4. Integration with CAP Tools

**ServiceNow Integration:**
- Automatic Change Request creation
- Impact assessment attachment
- Approval workflow synchronization
- Status updates (approved/rejected/completed)
- CMDB data enrichment

**Jira Integration:**
- Change ticket creation
- Custom fields mapping
- Approval workflow via Jira
- Comment synchronization
- Change history tracking

**PagerDuty Integration:**
- Change event creation
- On-call engineer notification
- Incident correlation
- Change rollback alerts

**Slack/Teams Integration:**
- Change approval notifications
- Interactive approval buttons
- Impact summary in channels
- Stakeholder mentions
- Post-change status updates

#### 3.2.5. Change Validation Checks

**Pre-Change Validation:**
- ✅ Image exists in registry
- ✅ Configuration syntax valid
- ✅ Resource limits within quota
- ✅ No conflicting changes scheduled
- ✅ Rollback plan prepared
- ✅ Monitoring alerts configured

**Post-Change Validation:**
- ✅ All pods running
- ✅ Health checks passing
- ✅ Error rate within threshold (<1%)
- ✅ Latency within SLA (p95 < 500ms)
- ✅ Dependent services responding
- ✅ No increase in 5xx errors

**Automated Rollback Triggers:**
- Error rate > 5%
- Pod crash loop
- Health check failures > 3
- Latency spike > 200% baseline
- Manual rollback request
- Timeout (change not completing in 30 min)

#### 3.2.6. Change History & Analytics

**Change Tracking:**
- All changes logged
- Before/after state snapshots
- Actual vs predicted impact comparison
- Success/failure rate
- Average approval time
- Rollback frequency

**Analytics Dashboard:**
- Changes per week/month
- Success rate by service
- Risk distribution
- Most frequently changed services
- Change velocity trends
- Downtime caused by changes
- MTTR (Mean Time To Recover)

**Compliance Reports:**
- All changes audit trail
- Approval evidence
- Change window compliance
- Emergency change justifications
- SOX/SOC2 compliance reports

### 3.2. Universal Data Ingestion & Enrichment

#### 3.2.1. Multi-Source Data Ingestion

**Extended Data Sources:**

Beyond eBPF, Flowfish collects data from many sources for full visibility:

**Infrastructure Data Sources:**
- ✅ **eBPF (Inspektor Gadget)**: Network, process, syscall events (primary)
- ✅ **Kubernetes Events**: Pod crashes, deployments, scaling events
- ✅ **Kubernetes Metrics**: Resource usage (CPU, memory, disk, network)
- ✅ **Node Metrics**: Node health, capacity, conditions
- ✅ **CNI Plugins**: Calico, Cilium, Weave network policies and flows

**Application Data Sources:**
- ✅ **Prometheus Metrics**: Application-level metrics (RED, USE, golden signals)
- ✅ **Service Mesh**: Istio, Linkerd telemetry (L7 metrics, mTLS status)
- ✅ **APM Traces**: Jaeger, Zipkin distributed traces
- ✅ **Application Logs**: Structured logs (JSON) for error correlation
- ✅ **Custom Metrics**: StatsD, OpenMetrics endpoint scraping

**External Data Sources:**
- ✅ **Cloud Provider APIs**: AWS, Azure, GCP (load balancers, managed services)
- ✅ **CI/CD Systems**: GitLab, Jenkins, ArgoCD (deployment events)
- ✅ **Incident Management**: PagerDuty, Opsgenie (incident correlation)
- ✅ **Configuration Management**: Git commits, Terraform changes

#### 3.2.2. Dependency Graph with Provenance

**Provenance Tracking:**

Full provenance for each dependency edge:

```json
{
  "edge": {
    "source": "payment-service",
    "target": "database-postgres",
    "type": "COMMUNICATES_WITH"
  },
  "provenance": {
    "discovered_by": "inspektor-gadget",
    "detection_method": "eBPF TCP tracking",
    "first_seen": "2024-01-15T10:30:00Z",
    "confidence_score": 0.99,
    "data_sources": [
      {
        "source": "eBPF network tracer",
        "timestamp": "2024-01-15T10:30:00Z",
        "sample_count": 15420
      },
      {
        "source": "Istio telemetry",
        "timestamp": "2024-01-15T10:32:00Z",
        "tls_verified": true
      }
    ],
    "validated_by": "john.doe@company.com",
    "validated_at": "2024-01-16T09:00:00Z"
  }
}
```

**Provenance Features:**
- **Multi-Source Verification**: Validate the same dependency from different sources
- **Confidence Scoring**: Confidence score per dependency (0.0-1.0)
- **Historical Tracking**: First detection, changes, validations
- **Manual Validation**: Users can approve/reject dependencies

### 3.3. Disaster Recovery Posture Assessment

#### 3.3.1. Stateful Workload DR Checks

**Automatic DR Posture Discovery:**

Flowfish automatically detects stateful applications and evaluates DR posture.

**DR Metrics:**

**RPO (Recovery Point Objective):**
- Backup frequency is detected
- Last backup time is checked
- Calculated RPO: Time elapsed since last backup

**RTO (Recovery Time Objective):**
- Restore time estimates
- Automated failover capability
- Calculated RTO: Estimated restore duration

**Parity Check:**
- Primary vs replica data consistency
- Replication lag monitoring
- Split-brain detection

**DR Posture Dashboard:**

```
Overall DR Score: 75/100 🟡 (Needs Improvement)

Critical Issues:
🔴 postgres-primary: No backup in 36 hours
   RPO: >36h (Target: 1h)
   Action: Enable automated backups

🔴 redis-cache: No replication configured
   RTO: >2h (Target: 5min)
   Action: Configure Redis Sentinel
```

**Integration:**
- **Velero**: Kubernetes backup/restore status
- **Stash**: Backup job status
- **Cloud Provider**: EBS snapshots, Azure Disk snapshots

### 3.4. Advanced Governance Automation

#### 3.4.1. CI/CD Pipeline Integration

**Pre-Deployment Checks:**

Flowfish runs automated pre-deployment checks integrated with CI/CD:

**Policy Checks:**
- ✅ **Network Policy Coverage**: Is there a network policy for the new service?
- ✅ **Security Context**: Compliant with pod security standards?
- ✅ **Resource Limits**: Are CPU/memory limits defined?
- ✅ **Breaking Changes**: Any API breaking changes?
- ✅ **Dependency Health**: Are dependent services healthy?

**Admission Controller (Webhook):**

Deployment-time validation via Kubernetes admission webhook:

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: flowfish-validator
webhooks:
- name: validate.flowfish.io
  rules:
  - operations: ["CREATE", "UPDATE"]
    apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
```

**GitOps Integration:**

Pre-sync policy checks with ArgoCD, FluxCD:

```yaml
# ArgoCD Pre-Sync Hook
apiVersion: batch/v1
kind: Job
metadata:
  name: flowfish-presync-check
  annotations:
    argocd.argoproj.io/hook: PreSync
```

**CI/CD Platform Plugins:**

**GitHub Actions:**
```yaml
- name: Flowfish Policy Check
  uses: flowfish/github-action@v1
  with:
    manifests: k8s/*.yaml
    fail-on: critical
```

#### 3.4.2. Policy as Code

**Custom Policy Definition:**

```yaml
apiVersion: policy.flowfish.io/v1
kind: GovernancePolicy
metadata:
  name: production-standards
spec:
  rules:
  - name: require-network-policy
    severity: high
    condition: deployment.networkPolicy.exists == true
    
  - name: dependency-health-check
    severity: critical
    condition: all dependencies.health == "healthy"
```

**Policy Enforcement:**
- **Blocking**: Deployment blocked on critical policy violations
- **Warning**: High/Medium violations produce warnings
- **Audit**: All violations are logged

### 3.5. Explainable AI & Natural Language Queries

#### 3.5.1. Natural Language Query Interface

**Conversational Interface:**

Users can ask questions in natural language:

**Example Queries:**

```
"Show me all external connections from payment service"
→ Executes graph query, returns results with evidence

"Which services depend on the database?"
→ Upstream dependency query

"What changed in the last 24 hours?"
→ Change detection timeline

"Why is checkout-service slow today?"
→ Performance analysis + anomaly correlation

"What happens if I delete redis-cache?"
→ Impact simulation query

"Find all services without network policies"
→ Governance compliance query
```

#### 3.5.2. Grounded AI Responses

**Explainable AI with Evidence:**

Every AI answer is **supported by evidence**:

```
User: "Is payment-service secure?"

AI Response:
Security Assessment: ⚠️ Medium Risk (55/100)

Findings:
1. ✅ Network Policy: Configured correctly
   Evidence: NetworkPolicy 'payment-policy' exists
   Source: Kubernetes API, verified 2024-01-20
   
2. 🔴 Unencrypted Connection: HTTP to internal-api
   Evidence: eBPF traced 1,200 HTTP connections
   Source: Inspektor Gadget network tracer
   Recommendation: Enable TLS

Confidence: 95%
Data Sources: eBPF, Kubernetes API, Istio
```

**Key Features:**
- ✅ **Evidence-Based**: Source shown for every claim
- ✅ **Source Attribution**: Which data source it came from
- ✅ **Confidence Scores**: AI confidence level
- ✅ **Actionable**: Concrete recommendations

#### 3.5.3. AI-Assisted Troubleshooting

**Interactive Debugging:**

```
User: "Payment API is failing, help me debug"

AI: Let me investigate...

Step 1: Checking payment-service health
✅ Pods: 5/5 running, healthy

Step 2: Analyzing recent changes
⚠️ Found: payment-service updated v2.3→v2.5, 2 hours ago

Step 3: Checking dependencies
🔴 Issue: checkout-service returning 502 errors
   Started: 2 hours ago (matches deployment)

Root Cause: API version mismatch after upgrade

Recommendations:
1. Rollback payment-service to v2.3
2. Update checkout-service to v2/validate endpoint

Would you like me to create rollback CR?
[ Yes ] [ No ]
```

### 3.6. Advanced AI/ML-Based Analysis

#### 3.6.1. Predictive Analytics
**Traffic Forecasting:**
- Request volume prediction (next 1 hour, 24 hours, 7 days)
- Resource usage prediction
- Capacity planning recommendations
- Scaling suggestions

**Anomaly Prediction:**
- Predict potential anomalies based on patterns
- Pre-emptive alerting
- Root cause prediction

#### 3.2.2. Recommendation Engine
**Automated Recommendations:**
- Network policy suggestions (least-privilege)
- Service mesh configuration
- Resource allocation (CPU, memory)
- Scaling recommendations
- Security hardening steps

**ML Models:**
- Time-series forecasting (Prophet, LSTM)
- Clustering (DBSCAN for similar services)
- Classification (normal vs anomalous)
- Reinforcement learning (optimal policy suggestions)

### 3.3. Automated Remediation Suggestions

#### 3.3.1. Auto-Remediation
**Remediatable Issues:**
- High-risk external connections → Block via NetworkPolicy
- Unencrypted traffic → Enforce TLS
- Cross-namespace violations → Update policies
- Resource exhaustion → Scale up

**Remediation Workflow:**
1. Issue detected
2. Remediation action suggested
3. User approval required (or auto-approve for low-risk)
4. Action executed (kubectl apply)
5. Verification (did it work?)
6. Rollback if failed

#### 3.3.2. Playbook Automation
**Runbook Integration:**
- Pre-defined playbooks for common scenarios
- Triggered by specific anomalies/changes
- Step-by-step execution
- Human-in-the-loop approval gates
- Audit log of all actions

### 3.4. Compliance and Audit Reports

#### 3.4.1. Compliance Frameworks
**Supported Standards:**
- PCI DSS (network segmentation)
- HIPAA (data flow auditing)
- SOC 2 (access controls)
- ISO 27001 (security monitoring)
- GDPR (data locality)

**Compliance Checks:**
- Automated compliance scanning
- Policy violations detection
- Compliance score per namespace
- Remediation guidance
- Evidence collection for audits

#### 3.4.2. Audit Reports
**Report Types:**
- Daily activity report
- Weekly security summary
- Monthly compliance report
- Quarterly trend analysis
- Annual review report
- Custom reports (user-defined)

**Report Contents:**
- Executive summary
- Key metrics and trends
- Anomalies and incidents
- Changes and deployments
- Compliance status
- Recommendations
- Detailed appendices

**Report Formats:**
- PDF (formatted, printable)
- HTML (web-viewable)
- JSON (machine-readable)
- Excel (data analysis)

**Distribution:**
- Email delivery
- Slack/Teams notification
- S3/Blob storage upload
- Report portal (web-based)

### 3.5. Advanced Visualization

#### 3.5.1. 3D Graph Visualization
**3D Layout:**
- Three.js based rendering
- Z-axis for time dimension or hierarchy
- Orbital controls (rotate, zoom, pan)
- Node stacking (multiple pods in one view)
- Enhanced visual appeal

#### 3.5.2. Logical Layer View
**Application Layers:**
- Layer 7: Application (microservices)
- Layer 6: Presentation (API gateways)
- Layer 5: Session (service mesh)
- Layer 4: Transport (load balancers)
- Layer 3: Network (ingress/egress)
- Layer 2: Data Link (CNI)
- Layer 1: Physical (nodes)

**Layer-based Filtering:**
- Show only specific layers
- Highlight layer boundaries
- Layer-to-layer communication emphasis

#### 3.5.3. Heat Maps
**Heatmap Types:**
- Traffic intensity heatmap (request volume)
- Latency heatmap (response time)
- Error rate heatmap
- Time-of-day heatmap (hourly patterns)
- Day-of-week heatmap

**Visualization:**
- Color gradients (green → yellow → red)
- Interactive hover (show exact values)
- Exportable as image

### 3.6. Custom Dashboard Builder

#### 3.6.1. Dashboard Customization
**Widget Library:**
- Metrics cards (single value)
- Time-series charts (line, area)
- Bar charts, pie charts
- Tables (sortable, filterable)
- Graph visualizations
- Heatmaps
- Text/markdown widgets
- Image widgets

**Drag-and-Drop:**
- Visual editor
- Grid layout system
- Widget resizing
- Widget positioning
- Widget duplication
- Widget templates

#### 3.6.2. Dashboard Sharing
**Sharing Options:**
- Public link (read-only, time-limited)
- Team sharing (specific users/groups)
- Embed code (iframe)
- PDF export
- Schedule snapshot emails

**Dashboard Templates:**
- Pre-built templates library
- Community-contributed templates
- Import/export templates (JSON)

---

## 📊 Feature Comparison Matrix

| Feature | Phase 1 (MVP) | Phase 2 (Advanced) | Phase 3 (Enterprise) |
|---------|-------------|------------------|-------------------|
| **Data Collection** | ✅ eBPF/Inspektor Gadget | ✅ | ✅ |
| **Automatic Discovery** | ✅ Real-time | ✅ Real-time + Historical | ✅ |
| **Graph Visualization** | ✅ Basic (2D) | ✅ Advanced (filtering) | ✅ 3D + Layers |
| **Analysis Wizard** | ✅ 4-step | ✅ | ✅ |
| **Dashboards** | ✅ Main + Live Map | ✅ + 5 advanced | ✅ + Custom builder |
| **RBAC** | ✅ 4 roles | ✅ + Custom roles | ✅ |
| **Authentication** | ✅ OAuth/SSO, K8s SA | ✅ | ✅ |
| **API Key Management** | ✅ | ✅ | ✅ |
| **Pod & Deployment Annotations** | ✅ | ✅ | ✅ |
| **Integration Hub** | ❌ | ✅ | ✅ |
| **Multi-Cluster** | ❌ | ✅ | ✅ |
| **Change Detection** | ❌ | ✅ | ✅ |
| **Anomaly Detection** | ❌ | ✅ LLM | ✅ LLM + ML models |
| **Import/Export** | ❌ | ✅ CSV + JSON | ✅ |
| **Risk Scores** | ❌ | ✅ | ✅ |
| **Baseline** | ❌ | ✅ | ✅ |
| **What-If Analysis** | ❌ | ❌ | ✅ |
| **Change Simulation (CAP)** | ❌ | ❌ | ✅ |
| **Universal Data Ingestion** | ✅ eBPF | ✅ + Prometheus | ✅ + Service Mesh, APM, Logs |
| **Dependency Provenance** | ❌ | ⚠️ Basic | ✅ Full multi-source |
| **DR Posture Checks** | ❌ | ❌ | ✅ RPO/RTO/Parity |
| **Governance Automation** | ❌ | ❌ | ✅ CI/CD + Admission Control |
| **Natural Language Queries** | ❌ | ❌ | ✅ |
| **Explainable AI** | ❌ | ⚠️ Basic | ✅ Grounded responses |
| **Auto-Remediation** | ❌ | ❌ | ✅ |
| **Compliance Reports** | ❌ | ❌ | ✅ |
| **Predictive Analytics** | ❌ | ❌ | ✅ |
| **SIEM Integration** | ❌ | ✅ | ✅ |
| **CAP Tool Integration** | ❌ | ❌ | ✅ ServiceNow, Jira |
| **API** | ✅ Core | ✅ Advanced | ✅ Full |

---

## 🎯 Success Criteria

### Phase 1 (MVP) Success Criteria
- [ ] Inspektor Gadget deployed and running successfully
- [ ] Data collection works on clusters with at least 1000 pods
- [ ] Graph visualization can render 500 nodes + 1000 edges
- [ ] Real-time updates run with <5 second latency
- [ ] Four user roles implemented and working
- [ ] OAuth SSO integration works with at least one provider
- [ ] Analysis wizard can create analyses in 4 steps

### Phase 2 Success Criteria
- [ ] Historical data stored and queryable for 30 days
- [ ] Change detection operates at 95% accuracy
- [ ] LLM anomaly detection responds within 10 seconds
- [ ] Import/export can handle 10MB+ files
- [ ] Multi-cluster can manage 5+ clusters
- [ ] Webhook can send 1000+ events/hour

### Phase 3 Success Criteria
- [ ] What-if simulation returns results in <30 seconds
- [ ] Change simulation (CAP) 95%+ accuracy
- [ ] Predictive analytics 80%+ accuracy
- [ ] DR posture assessment for 100+ stateful workloads
- [ ] Policy as Code with 50+ custom policies
- [ ] Natural language queries 90%+ intent recognition
- [ ] Grounded AI responses 95%+ evidence-backed
- [ ] CI/CD integration with 5+ platforms (GitHub, GitLab, Jenkins, ArgoCD, FluxCD)
- [ ] Compliance reports can be generated for 10 different frameworks
- [ ] Custom dashboard supports 50+ widgets

---

**Last Updated**: January 2025  
**Version**: 1.0.0  
**Status**: Design Documentation

