# Flowfish

Centralized multi-cluster Kubernetes observability platform — real-time dependency mapping, impact analysis, change detection, and security monitoring across all your clusters, powered by eBPF.

![Flowfish Showcase](docs/screenshots/flowfish-showcase.gif)

## Table of Contents

1. [Project Overview](#project-overview)
   - [What is Flowfish?](#what-is-flowfish)
   - [The Metaphor](#the-metaphor)
   - [Features at a Glance](#features-at-a-glance)
2. [Screenshots](#screenshots)
   - [Dashboard](#dashboard)
   - [Analysis](#analysis)
   - [Discovery](#discovery)
   - [Impact](#impact)
   - [Observability](#observability)
   - [Security](#security)
   - [Reports](#reports)
   - [Developer](#developer)
   - [Management](#management)
   - [Settings](#settings)
3. [Key Capabilities](#key-capabilities)
   - [eBPF-Based Data Collection](#ebpf-based-data-collection)
   - [Analysis Wizard & Lifecycle](#analysis-wizard--lifecycle)
   - [Real-Time Dependency Mapping](#real-time-dependency-mapping)
   - [Network Explorer](#network-explorer)
   - [Change Detection](#change-detection)
   - [Impact Simulation](#impact-simulation)
   - [Blast Radius Oracle](#blast-radius-oracle)
   - [AI Integration Hub](#ai-integration-hub)
   - [Pod & Deployment Annotations](#pod--deployment-annotations)
   - [Activity Monitor](#activity-monitor)
   - [Events Timeline](#events-timeline)
   - [Security Center](#security-center)
   - [Reports & Export](#reports--export)
   - [Developer Console](#developer-console)
   - [Multi-Cluster Management](#multi-cluster-management)
   - [User & Role Management](#user--role-management)
   - [System Settings](#system-settings)
   - [Dashboard Tabs](#dashboard-tabs)
4. [Architecture](#architecture)
   - [System Architecture](#system-architecture)
   - [Data Collection & Processing Flow](#data-collection--processing-flow)
   - [Change Detection Architecture](#change-detection-architecture)
   - [Data Architecture](#data-architecture)
   - [Component Details](#component-details)
5. [Technology Stack](#technology-stack)
6. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Docker Compose Quick Start](#docker-compose-quick-start)
   - [Kubernetes Deployment](#kubernetes-deployment)
   - [Default Credentials](#default-credentials)
7. [Configuration](#configuration)
   - [Backend Environment Variables](#backend-environment-variables)
   - [Frontend Environment Variables](#frontend-environment-variables)
   - [Database Configuration](#database-configuration)
8. [API Reference](#api-reference)
9. [Project Structure](#project-structure)
10. [Troubleshooting](#troubleshooting)
11. [Contributing](#contributing)
12. [License](#license)
13. [Author](#author)
14. [Support](#support)

---

## Project Overview

### What is Flowfish?

Flowfish is a **centralized, multi-cluster** cloud-native observability platform that **automatically discovers, visualizes, and analyzes** communication patterns and dependencies between applications running across your entire Kubernetes fleet — whether it is a single cluster or dozens spread across different providers. It supports **Amazon EKS**, **Google GKE**, **Azure AKS**, **OpenShift**, and any CNCF-conformant distribution from a single pane of glass. By leveraging **eBPF** (Extended Berkeley Packet Filter) technology through the Inspektor Gadget framework, Flowfish captures kernel-level network, process, file, and security events **without requiring any application-level changes** — delivering full-stack visibility with near-zero overhead.

Connect all your clusters to one Flowfish instance and gain a **unified view** of cross-cluster dependencies, security posture, and change patterns. Run simultaneous analyses across multiple clusters and namespaces, compare environments side by side, and detect inter-cluster communication flows — all from a single dashboard.

Unlike traditional APM tools that require agent installation or service meshes that demand sidecar injection, Flowfish deploys as a lightweight DaemonSet and begins collecting data the moment an analysis is started. The collected data feeds into a multi-database architecture — **Neo4j** for graph relationships, **ClickHouse** for time-series analytics, **PostgreSQL** for relational metadata, and **Redis** for real-time caching — enabling everything from interactive dependency maps to pre-deployment blast radius assessment.

### The Metaphor

- **Fish** — Kubernetes Pods, the living workloads swimming through your infrastructure
- **Flow** — Network traffic and communication streams between pods
- **Water** — The Kubernetes environment in which everything lives

### Features at a Glance

- **eBPF-Powered Data Collection** — Kernel-level capture via Inspektor Gadget DaemonSet with zero application changes required
- **Interactive Dependency Map** — Real-time graph visualization showing both in-cluster and external system dependencies (datacenter, public internet, SaaS APIs), with 18 layout algorithms, smart filtering (Public/DataCenter/Workload views), focus mode, and DNS enrichment
- **Guided Analysis Wizard** — Create analyses by selecting scope, gadget modules, timing, and data retention in a step-by-step flow
- **Concurrent Multi-Analysis** — Run multiple analyses simultaneously across different clusters and namespaces
- **Network Explorer** — Tabular deep-dive into flows, DNS queries, TLS/SNI connections, and services
- **Change Detection Engine** — Dual-source detection (Kubernetes API + eBPF) with three comparison strategies and 30+ change types
- **Impact Simulation** — What-if analysis for delete, scale-down, network isolation, port change, image update, and more with rollback planning
- **Blast Radius Oracle** — CI/CD-integrated pre-deployment impact assessment API with advisory risk scoring
- **Activity Monitor** — Real-time process, file, mount, and network I/O event tracking with process tree visualization
- **Events Timeline** — Unified view of all eBPF event types with anomaly indicators and time-range filtering
- **Security Center** — Security posture scoring, Linux capabilities audit, violations tracking, and OOM event monitoring
- **Reports & Export** — PDF, Excel, CSV, JSON reports with scheduling, quick templates, and custom report builder
- **Developer Console** — Dual-database query interface (ClickHouse SQL + Neo4j Cypher) with Monaco editor and query templates
- **Secure Multi-Cluster Management** — Add clusters from any Kubernetes distribution (EKS, GKE, AKS, OpenShift, vanilla K8s) with encrypted token storage, connection pooling, and one-click health checks
- **Role-Based Access Control** — User and role management with Admin, Viewer, and custom roles with granular permissions
- **Multi-Tab Dashboard** — Overview, Operations, Security, Network, Changes, and Workloads tabs with real-time metrics
- **CI/CD Pipeline Integration** — Blast radius checks for Azure DevOps, GitHub Actions, Jenkins, and GitLab CI
- **AI Integration Hub** — Three-step wizard (Configure → Preview → Integration Code) for dependency data integrations with ready-to-use code snippets for Azure DevOps, GitHub Actions, Jenkins, GitLab CI, Python, JavaScript, and cURL — includes a Blast Radius tab for pre-deployment risk assessment pipeline integration
- **Pod & Deployment Annotations** — Full annotation support including automatic merge of Deployment/StatefulSet annotations into pods, visible across Map, Network Explorer, Application Inventory, Impact Simulation, and AI Integration Hub
- **API Key Management** — Generate, expire, and revoke API keys for secure programmatic access alongside JWT authentication

---

## Screenshots

### Dashboard

The dashboard provides a centralized overview of all your connected clusters' health through six specialized tabs — aggregating metrics, events, and status from every cluster in one place.

**Overview** — Golden signals (latency, traffic, errors, saturation), smart insights panel (statistical anomaly detection, trend analysis, correlation alerts), and pod health grid:

![Dashboard Overview](docs/screenshots/dashboard-overview.png)

**Operations** — Real-time system health, analysis status, and event statistics:

![Dashboard Operations](docs/screenshots/dashboard-operations.png)

**Security** — Security posture score, threat radar, and violation breakdown:

![Dashboard Security](docs/screenshots/dashboard-security.png)

**Network** — Protocol distribution, top talkers, cross-namespace traffic matrix, DNS domains, and TLS hosts:

![Dashboard Network](docs/screenshots/dashboard-network.png)

**Changes** — Infrastructure and behavioral change tracking with trend charts:

![Dashboard Changes 1](docs/screenshots/dashboard-changes-1.png)

![Dashboard Changes 2](docs/screenshots/dashboard-changes-2.png)

**Workloads** — Kubernetes resource health overview with OOM event tracking:

![Dashboard Workloads](docs/screenshots/dashboard-workloads.png)

---

### Analysis

The analysis wizard guides you through creating a new eBPF data collection session.

**New Analysis — Scope & Gadget Selection**:

![New Analysis Wizard](docs/screenshots/new-analysis-1.png)

**Event Type Selection** — Choose which eBPF gadgets to activate (network, DNS, process, file, security, TLS/SNI, OOM, socket):

![Analysis Event Types 1](docs/screenshots/analysis-event-types-1.png)

![Analysis Event Types 2](docs/screenshots/analysis-event-types-2.png)

**Time & Sizing** — Configure duration, data limits, continuous vs. timed mode:

![Analysis Time Sizing 1](docs/screenshots/analysis-time-sizing-1.png)

![Analysis Time Sizing 2](docs/screenshots/analysis-time-sizing-2.png)

![Analysis Time Sizing 3](docs/screenshots/analysis-time-sizing-3.png)

**My Analyses** — List of all created analyses with status, scope, and controls:

![My Analyses](docs/screenshots/my-analyses.png)

---

### Discovery

**Dependency Map** — Interactive graph showing real-time workload communication with namespace grouping, color-coded clusters, protocol filters, and 18 layout algorithms:

![Dependency Map](docs/screenshots/dependency-map.png)

**Focus Mode** — Highlight a specific workload and its direct connections for targeted analysis:

![Dependency Map Focus](docs/screenshots/dependency-map-focus.png)

**Network Explorer** — Tabular view of flows, DNS queries, services, and TLS/SNI connections with search, filter, and CSV export:

![Network Explorer](docs/screenshots/network-explorer.png)

---

### Impact

**Impact Simulation** — Select a target workload and simulate changes (delete, scale down, network isolation, resource limit, port change, config change, image update) to see affected services, risk scores, and impact flow:

![Impact Simulation 1](docs/screenshots/impact-simulation-1.png)

![Impact Simulation 2](docs/screenshots/impact-simulation-2.png)

**Blast Radius Oracle** — Pre-deployment impact assessment with CI/CD integration, assessment history, and live test runner:

![Blast Radius Oracle 1](docs/screenshots/blast-radius-1.png)

![Blast Radius Oracle 2](docs/screenshots/blast-radius-2.png)

**Change Detection** — Timeline and table views of detected infrastructure changes with risk levels, type categorization, and export:

![Change Detection 1](docs/screenshots/change-detection-1.png)

![Change Detection 2](docs/screenshots/change-detection-2.png)

---

### Observability

**Activity Monitor** — Real-time process execution events, file operations, mount events, network I/O, with process tree view and namespace filtering:

![Activity Monitor](docs/screenshots/activity-monitor.png)

**Events Timeline** — Unified view of all eBPF event types with badge counts, anomaly detection indicators, time range filtering, and search:

![Events Timeline](docs/screenshots/events-timeline.png)

---

### Security

**Security Center** — Security posture scoring (0-100), Linux capabilities audit, violations, and OOM event tracking:

![Security Center - Overview](docs/screenshots/security-center-1.png)

![Security Center - Capabilities](docs/screenshots/security-center-2.png)

![Security Center - Violations](docs/screenshots/security-center-3.png)

![Security Center - OOM Events](docs/screenshots/security-center-4.png)

---

### Reports

**Reports** — Generate and download reports in PDF, Excel, CSV, and JSON formats. Quick templates for Security Audit, Network Analysis, Full Data Export, and Daily Summary. Scheduled reports with history:

![Reports](docs/screenshots/reports.png)

---

### Developer

**Developer Console** — Dual-database query interface with ClickHouse (SQL) and Neo4j (Cypher) support. Monaco editor with syntax highlighting, query templates, and results in table, JSON, or raw format:

![Developer Console](docs/screenshots/dev-console.png)

**API Documentation** — Interactive Swagger/OpenAPI documentation:

![API Documentation](docs/screenshots/APIs.png)

**AI Integration Hub** — Three-step wizard for dependency data integrations. Configure analysis scope and service identification method, preview dependency results with upstream/downstream statistics, and generate ready-to-use code snippets (Pipeline YAML, cURL, Python, JavaScript) with a dedicated Blast Radius tab for pre-deployment risk assessment:

![AI Integration Hub](docs/screenshots/ai-integration-hub.png)

---

### Management

**Cluster Management** — Add, edit, and monitor clusters across providers (Kubernetes, OpenShift, EKS, GKE, AKS). Environment tagging, gadget health monitoring, resource overview, and connection testing:

![Clusters 1](docs/screenshots/clusters-1.png)

![Clusters 2](docs/screenshots/clusters-2.png)

![Clusters 3](docs/screenshots/clusters-3.png)

**User & Role Management** — User CRUD with status, roles (Admin, Viewer, custom), activity logs, and audit trail:

![Users & Roles](docs/screenshots/users.png)

---

### Settings

**Settings** — Analysis configuration, email (SMTP), notifications, data retention, security, appearance themes, alert rules, system settings, audit logs, backup, and API key management:

![Settings](docs/screenshots/settings.png)

---

## Key Capabilities

### eBPF-Based Data Collection

Flowfish uses [Inspektor Gadget](https://github.com/inspektor-gadget/inspektor-gadget) as its data collection backbone. Inspektor Gadget is deployed as a Kubernetes DaemonSet and runs eBPF programs in the Linux kernel on every node, capturing events with near-zero overhead and without modifying any application code.

**How it works:**

1. The user creates an analysis through the wizard, selecting which namespaces/workloads to observe and which gadgets to activate
2. The backend instructs Inspektor Gadget to start the selected eBPF programs on the target nodes
3. Captured events are streamed to the Ingestion Service, which enriches them with Kubernetes metadata (pod name, namespace, labels, annotations, deployment owner). Annotations from owning Deployments and StatefulSets are automatically merged into pod metadata
4. Enriched events are published to RabbitMQ and written to ClickHouse (time-series), Neo4j (graph relationships), and PostgreSQL (metadata)

**Supported gadget modules:**

| Module | Gadget | Captures |
|--------|--------|----------|
| **Network Flow** | `trace_network` | TCP/UDP connections, source/dest IPs and ports, byte counts |
| **DNS Query** | `trace_dns` | DNS queries and responses, query types, latency |
| **TCP Throughput** | `top_tcp` | TCP throughput metrics, connection performance |
| **TCP Retransmit** | `trace_tcpretrans` | TCP retransmissions, connection quality |
| **Process** | `trace_exec` | Process creation/termination, command line, PID, exit code |
| **File I/O** | `trace_open` | File open/read/write events, paths, permissions |
| **Security** | `trace_capabilities` | Linux capabilities usage, privilege escalation attempts |
| **OOM** | `trace_oomkill` | Out-of-memory kill events, victim processes |
| **Socket** | `trace_bind` | Socket bind events, port usage |
| **TLS/SNI** | `trace_sni` | TLS handshakes, SNI hostnames |
| **Mount** | `trace_mount` | Volume mount/unmount operations |

**Key advantages over alternatives:**

- **Zero application changes** — No sidecars, no agent libraries, no code instrumentation
- **Minimal overhead** — eBPF runs in-kernel with <1-2% CPU impact
- **Privacy-first** — No data is collected until the user explicitly starts an analysis
- **Kubernetes-native** — DaemonSet deployment, automatic node coverage, pod-level granularity

---

### Analysis Wizard & Lifecycle

The analysis wizard provides a guided step-by-step flow to configure a new eBPF data collection session.

#### Step 1: Scope Selection

Define **what** to observe:

- **Name and description** for the analysis
- **Cluster mode**: Single cluster or multi-cluster (up to 5 clusters simultaneously)
- **Scope type**:
  - **Entire cluster** — Monitor all namespaces
  - **Namespace(s)** — Select specific namespaces (multi-select with cluster grouping)
  - Deployment, Pod, and Label selector scopes (planned)
- **Multi-cluster scope modes**:
  - **Unified scope** — Same namespaces across all selected clusters
  - **Per-cluster scope** — Different namespace selections per cluster (via tabs)
- **Change detection configuration**:
  - Enable/disable change detection
  - Strategy selection: Baseline, Rolling Window, or Run Comparison

#### Step 2: Gadget Modules

Choose **which** eBPF gadgets to activate. Each module displays its description, expected data volume, and performance impact. All modules are selected by default; at least one is required.

#### Step 3: Time & Sizing

Configure **how long** and **how much** data to collect:

| Mode | Description |
|------|-------------|
| **Continuous** | Runs indefinitely until manually stopped (with configurable auto-stop limit) |
| **Fixed Duration** | Runs for a specific period (minutes, hours, or days) |
| **Scheduled** | Runs during a specific time window (start time → end time) |

**Data retention policies:**
- **Unlimited** — No size cap
- **Stop on Limit** — Auto-stop when data reaches a threshold (50 MB – 10 GB)
- **Rolling Window** — Keep a fixed data size, rotating out old data (planned)

**Quick presets:** 10-Minute Test, 1-Hour Scan, Size-Limited (1 GB), Default (continuous + unlimited)

**Smart estimation panel** — As you configure the analysis, Flowfish dynamically calculates estimated event counts and data volume based on the **selected clusters**, **target namespaces**, **number of pods in scope**, and **active gadget modules**. The estimation panel displays projected events/hour, data size/hour, and time to reach common storage thresholds. These estimates adapt in real-time as you change the scope or toggle gadgets — giving you an accurate forecast before starting the collection. Actual event volumes vary significantly depending on workload traffic patterns, so estimates are approximations tailored to your specific selection.

#### Analysis Lifecycle

| Status | Description |
|--------|-------------|
| **Draft** | Created but not yet started |
| **Running** | Actively collecting eBPF data |
| **Running with Errors** | Collecting data but some gadgets failed (partial collection) |
| **Stopped** | Manually stopped by user |
| **Completed** | Finished (timed mode elapsed or auto-stop triggered) |
| **Failed** | Could not start or encountered fatal error |

**Concurrent execution:** Multiple analyses can run simultaneously across different clusters and namespaces. There is no frontend-enforced limit — each analysis operates independently with its own scope, gadgets, and timing.

**Run history:** Each analysis maintains a history of runs. The analysis list shows expandable rows with the last 5 runs, including start/stop times, events collected, and connections discovered.

**Auto-stop warnings:** When an analysis approaches its auto-stop limit, a WebSocket notification warns the user 2 minutes before shutdown.

---

### Real-Time Dependency Mapping

The dependency map is the visual centerpiece of Flowfish. Built with **React Flow**, it renders an interactive graph of all discovered workload communications — **not only between pods inside the cluster, but also to any external system** that cluster workloads communicate with. When a pod connects to a database in your datacenter, an external SaaS API, a CDN, or any other endpoint outside the cluster, that connection appears on the map automatically. DNS enrichment resolves raw IPs to domain names (e.g., `api.amazonaws.com` instead of `52.94.x.x`), making external dependencies immediately readable.

**Beyond the cluster boundary:**

The map classifies every discovered endpoint by network type:

| Node Type | How Identified | Visual |
|-----------|---------------|--------|
| **Pod-Network** | Cluster pods resolved via Kubernetes API | Green, circle |
| **Service-Network** | Kubernetes ClusterIP/NodePort services | Violet, rounded square |
| **DataCenter** | Private IPs (10.x, 172.x, 192.168.x) outside the cluster — databases, legacy systems, internal APIs | Cyan border |
| **Public / External** | Public internet IPs or DNS-enriched domains (e.g., `ghcr.io`, `api.stripe.com`) | Gold border |
| **SDN Gateway** | Software-defined networking gateways (OpenShift SDN, etc.) | Pink, hexagon |
| **Unresolved IP** | Raw IPs not matched to any known workload | Grey, dashed border |

This means Flowfish gives you a **complete picture** of where your traffic goes — internal microservice communication, datacenter backend systems, public cloud services, and third-party APIs — all in a single view.

**18 layout algorithms:**

| Category | Layouts |
|----------|---------|
| **Topological** | Hub (most connected center), Concentric (rings by connections), Star (central hub), Circle |
| **Organizational** | Cluster (by namespace), Owner (by deployment/StatefulSet), Tier (frontend → backend → DB) |
| **Analytical** | Network (pods center, external outer), Port (same port grouped), Error (error connections first), Flow (source left, target right) |
| **Geometric** | Force (organic physics), Grid (matrix), Tree (hierarchical), Mesh (hexagonal), Radial (expanding rings), Layered (horizontal bands), Organic |

**Filtering system:**

The map provides powerful filters designed for real-world operational workflows:

| Filter | Description |
|--------|-------------|
| **Analysis** | Select which analysis to visualize |
| **Cluster** | Multi-select clusters (multi-cluster analyses) |
| **Namespace** | Multi-select namespaces to focus on |
| **Public** | **Show only real public internet destinations** — public IPs (e.g., 142.x.x.x), DNS-enriched external endpoints (e.g., `api.stripe.com`), and ingress/gateway nodes. Private datacenter IPs are excluded. Ideal for identifying external SaaS dependencies and internet-facing traffic. |
| **DataCenter** | **Show only private IPs outside the cluster** — 10.x, 172.x, 192.168.x addresses that are NOT cluster pods. These represent datacenter systems like on-premise databases, legacy applications, message queues, and internal corporate services. Essential for mapping hybrid infrastructure dependencies. |
| **Workload View** | **Group pods by deployment/workload name** — Merges replica pods (e.g., `app-abc123`, `app-7fb889c6d4-xyz`) into a single node per workload. Same workload across clusters also merges. Dramatically simplifies large graphs by reducing hundreds of pod nodes to a manageable set of logical workload nodes. |
| **Unresolved IP** | Show nodes with raw IP addresses as names — useful for identifying dependencies that should use FQDN or service names |
| **Internal Traffic** | Show/hide localhost and 127.0.0.1 connections |
| **System Namespaces** | Hide `openshift-*`, `kube-*`, `default` |
| **Protocol Labels** | Show protocol on edges (HTTP, TCP, gRPC, etc.) |
| **Request Count** | Show traffic volume on edges |
| **Connection Limit** | 100, 200, 300, 500, 1K, 2K, 5K, or Max |
| **TLS Indicators** | Show TLS/encrypted connection badges |
| **Error Filter** | Show only connections with errors |
| **DNS Enrichment** | Show DNS, security, and OOM badges on nodes |

**Focus Mode** — Click any node to activate focus mode:
- Focused node: full opacity, scaled up with indigo glow
- Direct neighbors (1st degree): slightly dimmed, green glow
- Everything else: heavily dimmed (8% opacity)
- Connected edges highlighted; others nearly invisible
- "Clear Focus" button to exit

**Node details drawer** — Click a node to see:
- **Overview tab**: IP resolution, external connection banner, aggregated workload info, enrichment badges (DNS, TLS, Security, OOM)
- **Connections tab**: Inbound/outbound tables with source, target, protocol, port, request count, errors
- **Events tab**: Event statistics panel with breakdown by type (network, DNS, process, file, security, etc.)

**Namespace color coding** — Each namespace gets a distinct color from a curated palette. Namespace tags in the controls panel are clickable for quick highlighting. Multi-cluster mode adds cluster-colored borders.

**Export** — ZIP archive (nodes.csv + edges.csv + metadata.txt) or flat CSV with full source/target details, UTF-8 BOM for Excel compatibility.

**Real-time updates** — Graph data auto-refreshes every 10 seconds while an analysis is running. Manual refresh button available for on-demand updates.

**MiniMap** — Pannable and zoomable minimap for navigation in large graphs.

**Search** — Server-side search (3+ characters) queries Neo4j; client-side search matches name, IP, namespace, labels, owner, and image metadata.

---

### Network Explorer

The Network Explorer provides a structured, tabular deep-dive into raw collected data — complementing the visual dependency map with searchable, sortable, and exportable tables.

**Tabs:**

| Tab | Data | Key Columns |
|-----|------|-------------|
| **Flows** | Every observed network connection | Source pod/namespace, destination pod/namespace, protocol (TCP/UDP), source port, destination port, bytes sent/received, packet count, first/last seen timestamps |
| **Services** | Kubernetes services discovered during the analysis | Service name, namespace, type (ClusterIP/NodePort/LoadBalancer), ports, selector, associated endpoints, cluster |
| **DNS** | All DNS queries captured by the DNS gadget | Query domain, query type (A, AAAA, CNAME, SRV, MX), response code (NOERROR, NXDOMAIN, SERVFAIL), resolved IPs, query count, source pod/namespace |
| **TLS/SNI** | Encrypted connections captured via SNI inspection | SNI hostname (server name), source pod/namespace, destination IP, port, connection count, first/last seen |

**Features across all tabs:**
- Full-text search with minimum 3 characters
- Column-level sorting (click any column header)
- Namespace and pod filtering
- Pagination with configurable page size
- CSV export with UTF-8 BOM for Excel compatibility
- Analysis selector to switch between different collection runs

---

### Change Detection

Change Detection is a dual-source engine that combines **Kubernetes API polling** and **eBPF event analysis** to detect infrastructure and behavioral changes in real time.

#### Detection Sources

| Source | Detector | What It Catches |
|--------|----------|----------------|
| **Kubernetes API** | `K8sDetector` | Workload additions/removals, replica changes, image updates, config changes, label changes, resource limit changes, environment variable changes, service port/selector/type changes, network policy changes, ingress/route changes |
| **eBPF Events** | `EbpfDetector` | New/removed connections, port changes, traffic anomalies (3× baseline), latency spikes (2.5× baseline), DNS anomalies (NXDOMAIN spikes), suspicious process execution (nc, curl, nmap, etc.), error rate anomalies |

#### Comparison Strategies

| Strategy | Use Case | How It Works |
|----------|----------|-------------|
| **Baseline** | Long-running analyses, drift detection | Uses first 10 minutes as baseline, compares current 5-minute window against it; adapts for short analyses |
| **Rolling Window** | Continuous monitoring | Compares previous 5-minute window to current 5-minute window |
| **Run Comparison** | Deploy validation, A/B testing | Compares current analysis run against the previous run; falls back to baseline if no previous run exists |

#### Change Types (30+)

**Infrastructure (Kubernetes API):** `workload_added`, `workload_removed`, `replica_changed`, `config_changed`, `image_changed`, `resource_changed`, `env_changed`, `spec_changed`, `label_changed`, `service_port_changed`, `service_selector_changed`, `service_type_changed`, `service_added`, `service_removed`, `network_policy_added/removed/modified`, `ingress_added/removed/modified`, `route_added/removed/modified`

**Connections (eBPF):** `connection_added`, `connection_removed`, `port_changed`

**Anomalies (eBPF):** `traffic_anomaly`, `dns_anomaly`, `process_anomaly`, `error_anomaly`

#### Risk Assessment

Each change is automatically assigned a risk level:
- **Critical** — Replica scaled to zero, NXDOMAIN spikes, workload removal with large blast radius
- **High** — Workload removal, port changes, connection removal, image changes
- **Medium** — Config changes, label changes, error rate spikes
- **Low** — Additions, minor replica changes

#### Frontend Views

| Tab | Description |
|-----|-------------|
| **Timeline** | Chronological event stream with risk-colored markers, filterable by type and time range |
| **Analytics** | Charts: changes by type, by namespace, by risk level, trends over time |
| **Snapshot Comparison** | Before/after counts for workloads, connections, and namespaces between two time periods |
| **Run Comparison** | Side-by-side comparison of two analysis runs |

Real-time updates via WebSocket. Export to CSV, Excel, PDF, and JSON. Saved filter presets for quick access to common views.

---

### Impact Simulation

Impact Simulation answers the question: *"What would happen if I made this change?"* by traversing the Neo4j dependency graph to identify all directly and indirectly affected services.

#### Target Selection

Select a target from resources discovered during analysis (not from live cluster API):
- **Cluster → Analysis → Namespace (optional) → Target Type → Target**
- Target types: Deployment, Pod, Service, External Endpoint
- URL parameters supported for deep-linking from other pages

#### Simulation Change Types

| Type | Category | Description |
|------|----------|-------------|
| **Delete / Remove** | Destructive | Simulate complete removal of a workload |
| **Scale Down** | Scaling | Reduce replicas to zero, assess capacity impact |
| **Network Isolation** | Network | Simulate network policy blocking all traffic to/from workload |
| **Resource Limit Change** | Resource | Simulate CPU/memory constraint changes |
| **Port Change** | Network | Simulate changing a service port |
| **Configuration Change** | Configuration | Simulate ConfigMap or Secret modification |
| **Image Update** | Deployment | Simulate container image version change |
| **Apply Network Policy** | Network (Advanced) | Simulate applying a new network policy |
| **Remove Network Policy** | Network (Advanced) | Simulate removing an existing network policy |

#### Impact Calculation

The backend traverses the Neo4j dependency graph:

1. **Find target** — Match by name and namespace in the graph
2. **Direct dependencies (1-hop)** — All outgoing and incoming edges from the target node
3. **Indirect dependencies (2-hop)** — Edges from direct dependencies to other nodes
4. **Filter** — Remove infrastructure endpoints (Kubernetes API, DNS), deduplicate
5. **Score** — Calculate risk per affected service based on: dependency type (direct +0.3), request volume (log scale), critical namespace bonus (+0.15), well-known port bonus (+0.1), and change type severity

#### Impact Results

- **Summary**: Total affected, high/medium/low impact counts, blast radius, confidence score
- **Per-service detail**: Impact level, impact category (service outage, connectivity loss, cascade risk, performance degradation, security exposure, etc.), dependency type, recommendation, risk score, risk factors, and connection details (protocol, port, request count)
- **Impact flow diagram**: Target in center, direct dependencies above, indirect below, color-coded by impact level
- **No-dependency cases**: Intelligent detection of isolated workloads, external-only services, or unmatched graph nodes with actionable suggestions

#### Timeline & Rollback

- **Timeline tab**: Propagation phases — Immediate (0-5 min), Short-term (5-30 min), Long-term (30+ min)
- **Rollback tab**: Feasibility assessment (high/medium/low), estimated time, step-by-step rollback procedures with `kubectl` examples, complexity metrics

#### Scheduling & History

- Schedule simulations: once, daily, or weekly with notification before execution
- Auto-rollback option if failure thresholds are exceeded
- Full simulation history with replay capability

#### Chaos Engineering Templates

Pre-built templates for chaos experiments: Pod Termination, Network Partition, CPU Stress, Memory Pressure, Dependency Failure, Config Drift, DNS Failure, Rolling Restart Chaos — each with severity rating, prerequisites, and rollback time estimates.

---

### Blast Radius Oracle

The Blast Radius Oracle provides a **pre-deployment impact assessment API** designed for CI/CD pipeline integration. It is **advisory only** — Flowfish provides risk scores and recommendations, but never blocks deployments; the pipeline owns the decision.

#### How It Works

1. Pipeline calls the Flowfish blast radius API with change details
2. Flowfish traverses the Neo4j dependency graph to identify affected services
3. Risk score is calculated (0-100) and recommendation is returned
4. Pipeline decides whether to proceed based on configured thresholds

#### Risk Scoring Formula

| Factor | Max Points | Calculation |
|--------|-----------|-------------|
| **Change type severity** | 25 | delete: 25, network_policy: 20, scale/image: 10, config: 8, resource: 5 |
| **Direct dependencies** | 30 | `min(30, direct_count × 6)` |
| **Indirect dependencies** | 20 | `min(20, indirect_count × 2)` |
| **Critical services** | 15 | `min(15, critical_count × 5)` |
| **Business hours** | 10 | +10 if 9-18 UTC on weekdays |

| Risk Level | Score | Recommendation |
|------------|-------|---------------|
| **Critical** | ≥ 75 | `delay_suggested` |
| **High** | ≥ 50 | `review_required` |
| **Medium** | ≥ 25 | `proceed` |
| **Low** | < 25 | `proceed` |

#### API Response

```json
{
  "assessment_id": "br-20260301-143022",
  "risk_score": 62,
  "risk_level": "high",
  "confidence": 0.85,
  "blast_radius": {
    "total_affected": 8,
    "direct_dependencies": 3,
    "indirect_dependencies": 5,
    "critical_services": 1,
    "namespaces_affected": 2
  },
  "recommendation": "review_required",
  "suggested_actions": [
    {"priority": 1, "action": "Schedule during maintenance window", "reason": "High direct dependency count", "automatable": false},
    {"priority": 2, "action": "Prepare rollback plan", "reason": "Critical service in blast radius", "automatable": true}
  ],
  "advisory_only": true
}
```

#### CI/CD Integration Examples

**Azure DevOps:**
```yaml
- script: |
    RESULT=$(curl -s -X POST "$(FLOWFISH_URL)/api/v1/blast-radius/assess" \
      -H "Authorization: Bearer $(FLOWFISH_TOKEN)" \
      -H "Content-Type: application/json" \
      -d '{"cluster_id": $(CLUSTER_ID), "change": {"type": "image_update", "target": "payment-service", "namespace": "production"}}')
    echo "Risk Score: $(echo $RESULT | jq '.risk_score')"
    echo "##vso[task.setvariable variable=BLAST_RADIUS_SCORE]$(echo $RESULT | jq '.risk_score')"
  displayName: 'Blast Radius Check'
```

**GitHub Actions:**
```yaml
- name: Blast Radius Check
  run: |
    RESULT=$(curl -s -X POST "${{ secrets.FLOWFISH_URL }}/api/v1/blast-radius/assess" \
      -H "Authorization: Bearer ${{ secrets.FLOWFISH_TOKEN }}" \
      -H "Content-Type: application/json" \
      -d '{"cluster_id": ${{ env.CLUSTER_ID }}, "change": {"type": "image_update", "target": "payment-service", "namespace": "production"}}')
    echo "Risk: $(echo $RESULT | jq -r '.risk_level')"
```

**Jenkins:**
```groovy
stage('Blast Radius Check') {
    steps {
        script {
            def result = httpRequest(
                url: "${FLOWFISH_URL}/api/v1/blast-radius/assess",
                httpMode: 'POST',
                customHeaders: [[name: 'Authorization', value: "Bearer ${FLOWFISH_TOKEN}"]],
                requestBody: '{"cluster_id": ' + CLUSTER_ID + ', "change": {"type": "image_update", "target": "payment-service", "namespace": "production"}}'
            )
            def json = readJSON text: result.content
            if (json.risk_level == 'critical') {
                input message: "Critical blast radius detected. Proceed?"
            }
        }
    }
}
```

#### Live Test Runner

The UI includes a live test runner for ad-hoc assessments: select cluster, analysis, target service, namespace, and change type. Results display risk score dashboard, confidence, affected service counts, and suggested actions.

#### Assessment History

Full history of all assessments with assessment ID, timestamp, target, namespace, change type, risk score, risk level, affected count, and pipeline source. Click any entry for detailed JSON view.

The Overview tab also includes a cross-link to the **AI Integration Hub** for users who need dependency data integrations alongside blast radius assessments.

---

### AI Integration Hub

The AI Integration Hub provides a **three-step guided wizard** (Configure → Preview → Integration Code) for setting up dependency data integrations with AI code agents and CI/CD pipelines. It enables cross-project impact analysis by exposing Flowfish dependency data through a compact, categorized JSON API. The wizard also includes a Blast Radius tab for generating pre-deployment risk assessment pipeline snippets, with a cross-link to the Blast Radius Oracle page for interactive testing.

#### Use Case: Cross-Project Impact Analysis

When a pull request is opened in Project A, an AI code agent (running as a build validation job) can query Flowfish to discover all services that depend on Project A — across clusters and namespaces. The agent receives a structured JSON response with upstream/downstream dependencies grouped by category, including rich metadata (annotations, labels, git-repo URLs, team ownership) that enables it to assess cross-project impact.

#### Wizard Steps

| Step | Description |
|------|-------------|
| **Configure** | Select one or more analyses, choose a service identification method (Annotation, Label, Namespace + Deployment, Pod Name, or Advanced), configure search depth, and optionally run a live test query to validate results |
| **Preview & Validate** | View the dependency summary — upstream service metadata, downstream/caller statistics, matched services table with annotations and labels |
| **Integration Code** | Generate and copy ready-to-use code snippets across tabs: Pipeline (platform-specific YAML), cURL, Python, JavaScript, and Blast Radius (pre-deployment risk assessment integration) |

#### Supported Platforms

| Platform | Snippet Type |
|----------|-------------|
| **Azure DevOps** | YAML pipeline task with secret variable guidance |
| **GitHub Actions** | Workflow step with secrets integration |
| **Jenkins** | Groovy pipeline with `withCredentials` block |
| **GitLab CI** | YAML job with CI/CD variable integration |
| **Other (Generic)** | Shell script with `curl` and `--fail` flag |
| **Python** | `requests` library with proper parameter serialization |
| **JavaScript** | `fetch` API with error handling |
| **cURL** | Command-line snippet for quick testing |

The Integration Code step also includes a **Blast Radius** tab that generates pre-deployment risk assessment snippets (cURL and platform-specific pipeline YAML) for the `/api/v1/blast-radius/assess` endpoint, with a direct link to the Blast Radius Oracle page for interactive testing.

#### Authentication

The generated snippets use API Keys (`X-API-Key` header) for authentication. API keys can be created, expired, and revoked from **Settings > API Keys**. The snippets include a `FLOWFISH_API_KEY` placeholder variable for secure credential management.

#### Key API Endpoint

```
GET /api/v1/communications/dependencies/summary
  ?analysis_ids=1,2
  &namespace=my-app
  &annotation_key=git-repo
  &annotation_value=https://github.com/org/project-a
```

Returns a compact, grouped JSON response with:
- **Upstream service** metadata (annotations, labels, kind, namespace)
- **Downstream dependencies** grouped by service category (Database, Message Queue, Cache, API, etc.)
- **Callers** (services that depend on the upstream)
- **Matched services** list when multiple pods match the query

---

### Pod & Deployment Annotations

Flowfish captures and displays Kubernetes annotations alongside labels for every discovered pod. Annotations from owning **Deployments** and **StatefulSets** are automatically merged into pod metadata during ingestion — pod-level annotations take priority in case of conflicts.

This enables use cases such as:
- **Git repository tracking** — Annotations like `git-repo: https://github.com/org/service-a` set during CI/CD deployment
- **Team ownership** — Annotations like `team: payments-team` for organizational mapping
- **Pipeline metadata** — Who triggered the deployment, build number, commit SHA
- **Cross-project impact analysis** — AI agents use annotation data to identify which git repositories are affected

Annotations are visible across:
- **Dependency Map** — Node detail drawer with categorized, formatted annotations
- **Application Inventory** — Searchable annotation column with expandable detail view
- **Network Explorer** — Metadata column with annotations included in CSV exports
- **Impact Simulation** — Affected service annotations in results and exports
- **AI Integration Hub** — Annotations exposed in dependency summary API responses

Internal Kubernetes annotations (`kubectl.kubernetes.io/`, `kubernetes.io/`, `openshift.io/` prefixes) are filtered during ingestion to reduce noise, and values exceeding 500 characters are excluded.

---

### Activity Monitor

The Activity Monitor provides real-time visibility into kernel-level events captured by eBPF gadgets, organized into four dedicated tabs.

**Event category tabs:**

| Tab | Events Captured | Key Fields |
|-----|----------------|------------|
| **Processes** | Every process execution and termination | Full command line, PID, parent PID, exit code, user, duration, container |
| **File Operations** | File open, read, write, close, and delete events | Full path, operation type, permissions, access patterns, container |
| **Mounts** | Volume mount and unmount operations within containers | Mount point, filesystem type, options, container |
| **Network I/O** | Raw network send/receive events at the socket level | Source/dest IPs, ports, byte counts, protocol, timing |

**Filters and controls:**

- **Analysis selector** — Choose which running or completed analysis to inspect
- **Time range** — Presets: Last Hour, 6 Hours, 24 Hours, 7 Days, 30 Days, or custom range
- **Namespace filter** — Narrow events to a specific namespace
- **Quick filters** — All Events, Suspicious (flagged activity), Shells (shell processes), Network Tools (nc, curl, wget), Errors, High Activity
- **Search** — Full-text search across pods, processes, and file paths (3+ characters)
- **Group by** — Toggle between grouped (by process) and flat views
- **Auto-refresh** — Off, 5s, 10s, 30s, or 1 minute intervals

**Visualizations:**

- **Activity Timeline** — Bar chart with 60 time buckets, color-coded by event type (Process, File, Mount, Network), showing event density over time
- **Statistics row** — Live counters for Process Events, File Operations, Mount Events, Network I/O, Data Transferred, and Total Events
- **Process Tree** — Click any process to see its parent-child hierarchy in a tree modal, revealing how processes are spawned within containers
- **Related Events** — Click a process to see its associated file operations and network flows in a detail modal

**Export** — CSV or JSON with all event details.

---

### Events Timeline

The Events Timeline provides a **unified, chronological view** of every eBPF event type captured during an analysis — a single pane of glass for all kernel-level activity.

**Event types with live count badges:**

| Event Type | What It Shows |
|-----------|---------------|
| **Network Flow** | TCP/UDP connections with source/dest, ports, bytes, packets |
| **DNS Query** | DNS lookups with domain, query type, response code, latency |
| **Process** | Process exec/exit with command line, PID, exit code |
| **File I/O** | File operations with path, operation, permissions |
| **Security** | Linux capability usage, privilege escalation attempts |
| **OOM Kill** | Out-of-memory kills with victim, container, memory limit |
| **Socket Bind** | Socket bind events with port and protocol |
| **TLS/SNI** | TLS handshakes with SNI hostname and connection details |
| **Mount** | Volume mount/unmount operations |

**Filters and controls:**

- **Analysis and cluster selectors** — Choose analysis and, for multi-cluster analyses, filter by cluster
- **Event type multi-select** — Show/hide specific event types
- **Time range** — Presets (Last Hour, 6 Hours, 24 Hours, 7 Days, 30 Days) or custom
- **Namespace filter** — Narrow to a specific namespace
- **Quick filters** — All Events, Anomalies (flagged by statistical detection), Security, Network, Process/File, Errors, High Volume
- **Search** — Full-text search (3+ characters)
- **Auto-refresh** — Off, 5s, 10s, 30s, 1 minute

**View modes:**

- **Normal view** — Flat table of all events, sortable by any column, with expandable detail rows and JSON copy
- **Grouped view** — Events grouped by type showing count, latest event, sample events, and anomaly count per type
- **Timeline chart** — Bar chart with 60 time buckets, stacked by event type, showing event volume patterns over time

**Anomaly detection** — Statistical indicators (Z-score, deviation from baseline) flag events as anomalous. Anomaly badges appear on event type tags and individual events, making it easy to spot unusual patterns across DNS, network, process, file, security, and OOM events.

**Export** — CSV or JSON with full event details and metadata.

---

### Security Center

The Security Center provides a comprehensive security posture assessment based on eBPF-captured data.

**Security Score (0-100)** calculated from Linux capabilities usage, security violations, OOM frequency, external communication patterns, and unencrypted traffic ratio.

**Tabs:**

- **Capabilities** — Lists every Linux capability used by pods (e.g., `NET_ADMIN`, `SYS_PTRACE`, `DAC_OVERRIDE`) with per-capability risk assessment. Dangerous capabilities flagged as critical/high risk.
- **Violations** — Security policy violations: unauthorized connections, privilege escalation attempts, policy breaches.
- **OOM Events** — Out-of-memory kills with victim process, container, memory limit, and timestamp.

Risk color coding: Critical (red), High (orange), Medium (yellow), Low (green).

---

### Reports & Export

| Report Type | Description |
|-------------|-------------|
| **Dependency Report** | Full workload dependency graph with metrics |
| **Events Export** | Raw eBPF events for a given time range |
| **Network Flows** | All observed network connections |
| **DNS Queries** | Complete DNS query log |
| **Security Assessment** | Security posture report with risk scores |
| **Statistics Summary** | Aggregated metrics and trends |
| **Period Comparison** | Side-by-side comparison of two time periods |

**Formats:** PDF, CSV, JSON, Excel

**Quick Templates:** Security Audit, Network Analysis, Full Data Export, Daily Summary

**Additional tabs:** SLO/SLA Tracking, Trend Analysis, Custom Report Builder

**Scheduling:** Recurring reports (daily, weekly, monthly) delivered via email or saved to storage.

---

### Developer Console

Direct query access to Flowfish's two analytical databases:

- **ClickHouse (SQL)** — Time-series data: network flows, DNS queries, process events, file access, metrics
- **Neo4j (Cypher)** — Dependency graph: workload nodes, communication edges, traversals, shortest paths

**Monaco editor** with syntax highlighting, auto-completion, and error markers. Results in table, JSON, or raw format. Pre-built query templates for common tasks. Query history in local storage. Analysis and cluster scoping.

---

### Multi-Cluster Management

Flowfish supports managing multiple clusters from a single interface with enterprise-grade security. It is compatible with any CNCF-conformant Kubernetes distribution, including managed cloud offerings and on-premise installations.

#### Supported Providers

| Provider | Type | Notes |
|----------|------|-------|
| **Kubernetes** | Self-managed / on-premise | Any vanilla K8s distribution |
| **OpenShift** | Red Hat enterprise | Full support for OpenShift SDN and Routes |
| **Amazon EKS** | AWS managed Kubernetes | Default StorageClass: `gp2` / `gp3` |
| **Google GKE** | Google Cloud managed Kubernetes | Default StorageClass: `standard` |
| **Azure AKS** | Microsoft Azure managed Kubernetes | Default StorageClass: `managed-premium` |

> **Note:** Flowfish has been extensively tested on Kubernetes and OpenShift in production environments. EKS, GKE, and AKS support is available and functional — these providers use standard Kubernetes APIs, so all Flowfish features work as expected.

#### Environment Tags

Each cluster is tagged with an environment label for organizational clarity: **Production**, **Staging**, **Development**, **Testing**.

#### Adding a Cluster

The add-cluster flow is streamlined for minimal friction:

1. **Basic info** — Name, environment tag, provider selection (Kubernetes, OpenShift, EKS, GKE, AKS)
2. **Connection** — Choose connection type and provide credentials:

| Type | Use Case | Required |
|------|----------|----------|
| **In-Cluster** | Flowfish deployed inside the cluster | API URL auto-detected |
| **Token** | Remote cluster via ServiceAccount | API URL + Token |
| **Kubeconfig** | Remote cluster via kubeconfig file | Kubeconfig content |

3. **Test connection** — Validates both cluster connectivity and Inspektor Gadget health before saving
4. **Setup scripts** — One-click generation of install/uninstall scripts with provider-aware defaults (e.g., correct StorageClass for EKS/GKE/AKS/vSphere), optional custom StorageClass configuration

#### Security

- **Encrypted credential storage** — All tokens, CA certificates, and kubeconfig content are encrypted at rest using Fernet (AES-128-CBC) before being stored in PostgreSQL
- **Connection pooling** — Cluster connections are lazily created and cached; the Cluster Manager gRPC service acts as a gateway, so credentials never leave the backend
- **Health monitoring** — Periodic health checks verify cluster connectivity and Inspektor Gadget availability
- **No direct K8s API exposure** — All Kubernetes API calls are proxied through the Cluster Manager service, which decrypts credentials in memory only when needed

---

### User & Role Management

#### User Management

Create, edit, deactivate, and delete user accounts. The user table displays username, full name, email, active/inactive status, assigned roles, and last login timestamp. Each user has actions for editing profile, assigning roles, changing password, and deletion.

#### Built-in Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| **Admin** | Full system access | All permissions across all resources |
| **Operator** | Cluster and analysis operations | View all + create/edit/start clusters and analyses |
| **Analyst** | Analysis and reporting | View all + create analyses, export events, generate reports |
| **Viewer** | Read-only access | View dashboards, analyses, events, reports, clusters |

#### Custom Roles & Granular Permissions

Create custom roles with fine-grained permission assignment. Permissions are organized by resource:

| Resource | Available Permissions |
|----------|----------------------|
| **Dashboard** | View, Statistics |
| **Analysis** | View, Create, Start/Stop, Delete |
| **Clusters** | View, Create, Edit, Delete |
| **Events** | View, Export |
| **Reports** | View, Generate, Schedule, History |
| **Security** | View, Manage |
| **Users** | View, Create, Edit, Delete |
| **Roles** | View, Create, Edit, Delete |
| **Settings** | View, Edit |

#### Role Assignment

Roles are assigned via a dedicated "Assign Roles" action per user (multi-select). Only administrators can modify role assignments. Role changes take effect immediately.

#### Activity Logs & Audit Trail

Every user action is recorded in the activity log with: username, action type (login, logout, create, update, delete, start, stop, export, generate, schedule, assign, revoke), resource type and name, details (JSON), client IP address, user agent, success/failure status, and timestamp. The audit log is searchable, filterable, and exportable.

#### Role-Based UI

The frontend dynamically adapts based on the user's permissions. Users without create/start permissions see read-only views — action buttons (create analysis, start, stop, delete, manage clusters) are hidden or disabled.

---

### System Settings

| Category | Configuration |
|----------|---------------|
| **Analysis** | Auto-stop behavior, time limits, default duration presets, continuous mode limits |
| **Email** | SMTP server, sender address, authentication |
| **Notifications** | Alert channels, notification rules, severity thresholds |
| **Data Retention** | Per-database retention periods, automatic cleanup schedules |
| **Security** | Session timeout, password policies, API key management |
| **Appearance** | Light/dark theme, custom branding |
| **Alert Rules** | Custom alert conditions and actions |
| **System** | Log level, performance tuning, feature flags |
| **Audit Logs** | System audit trail viewing and export |
| **Backup** | Database backup scheduling and restore |
| **API Keys** | Generate and manage API access tokens |

---

### Dashboard Tabs

| Tab | Key Metrics |
|-----|------------|
| **Overview** | Golden signals (request rate, error rate, latency p50/p95/p99, saturation), smart insights (statistical anomaly detection, trend analysis, correlation alerts), pod health grid, top services by traffic, risk distribution |
| **Operations** | Active analyses, system component health, event ingestion rate, recent alerts, resource trends |
| **Security** | Aggregate security score, threat radar, top violations, capability heatmap, OOM kill trend |
| **Network** | Protocol distribution, top talkers, cross-namespace traffic matrix, top DNS domains, TLS host distribution |
| **Changes** | Change count by type, change timeline, risk-weighted score, most frequently changing workloads |
| **Workloads** | Resource health summary (Deployments, StatefulSets, DaemonSets), pod status distribution, OOM by workload, resource warnings |

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PRESENTATION LAYER                               │
│                                                                             │
│   ┌───────────────────────┐       ┌───────────────────────┐                 │
│   │   Nginx Ingress       │       │   React SPA           │                 │
│   │   (TLS Termination)   │──────▶│   (TypeScript +       │                 │
│   │                       │       │    Ant Design)         │                 │
│   └───────────────────────┘       └───────────┬───────────┘                 │
└───────────────────────────────────────────────┼─────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            APPLICATION LAYER                                │
│                                                                             │
│   ┌────────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│   │  FastAPI Backend    │  │  Analysis         │  │  Cluster Manager │       │
│   │  (REST + WebSocket) │  │  Orchestrator     │  │  (gRPC)          │       │
│   │                     │  │  (gRPC)           │  │                  │       │
│   └──┬──┬──┬──┬────────┘  └────────┬─────────┘  └──────────────────┘       │
│      │  │  │  │                     │                                       │
│      │  │  │  │  ┌─────────────────┐│  ┌──────────────────┐                 │
│      │  │  │  │  │  API Gateway    ││  │  Change Detection │                 │
│      │  │  │  │  │  (gRPC)         ││  │  Worker           │                 │
│      │  │  │  │  └─────────────────┘│  └──────────────────┘                 │
└──────┼──┼──┼──┼─────────────────────┼───────────────────────────────────────┘
       │  │  │  │                     │
       │  │  │  │                     ▼
       │  │  │  │  ┌──────────────────────────────────────────────────────┐
       │  │  │  │  │              DATA COLLECTION LAYER                   │
       │  │  │  │  │                                                      │
       │  │  │  │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
       │  │  │  │  │  │ IG Node 1   │ │ IG Node 2   │ │ IG Node N   │   │
       │  │  │  │  │  │ (eBPF)      │ │ (eBPF)      │ │ (eBPF)      │   │
       │  │  │  │  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │
       │  │  │  │  └─────────┼───────────────┼───────────────┼───────────┘
       │  │  │  │            │               │               │
       │  │  │  │            └───────────────┼───────────────┘
       │  │  │  │                            ▼
       │  │  │  │  ┌──────────────────────────────────────────────────────┐
       │  │  │  │  │              DATA INGESTION LAYER (Write Path)       │
       │  │  │  │  │                                                      │
       │  │  │  │  │  ┌─────────────────────────┐                        │
       │  │  │  │  │  │ Ingestion Service        │                        │
       │  │  │  │  │  │ (gRPC + K8s Enrichment)  │                        │
       │  │  │  │  │  └────────────┬─────────────┘                        │
       │  │  │  │  │               ▼                                      │
       │  │  │  │  │  ┌─────────────────────────┐                        │
       │  │  │  │  │  │ RabbitMQ                 │                        │
       │  │  │  │  │  │ (Event Routing)          │                        │
       │  │  │  │  │  └──────┬──────────┬────────┘                        │
       │  │  │  │  │         ▼          ▼                                 │
       │  │  │  │  │  ┌────────────┐ ┌─────────────────┐                  │
       │  │  │  │  │  │ Graph      │ │ Timeseries      │                  │
       │  │  │  │  │  │ Writer     │ │ Writer           │                  │
       │  │  │  │  │  └─────┬──────┘ └────────┬────────┘                  │
       │  │  │  │  └────────┼─────────────────┼──────────────────────────┘
       │  │  │  │           │  (write)        │  (write)
       │  │  │  │           ▼                 ▼
       │  │  │  │  ┌──────────────────────────────────────────────────────┐
       │  │  │  │  │              QUERY LAYER (Read Path)                  │
       │  │  │  │  │                                                      │
       │  │  │  │  │  ┌───────────────────┐  ┌────────────────────────┐  │
       │  │  │  │  │  │ Graph Query       │  │ Timeseries Query       │  │
       │  │  │  │  │  │ Service (REST)    │  │ Service (REST)         │  │
       │  │  │  │  │  │                   │  │                        │  │
       │  │  │  │  │  │ • Dependency map  │  │ • Event queries        │  │
       │  │  │  │  │  │ • Impact analysis │  │ • Event statistics     │  │
       │  │  │  │  │  │ • Blast radius    │  │ • Dev Console (SQL)    │  │
       │  │  │  │  │  │ • Dev Console     │  │ • Anomaly data         │  │
       │  │  │  │  │  │   (Cypher)        │  │ • Change event queries │  │
       │  │  │  │  │  └────────┬──────────┘  └───────────┬────────────┘  │
       │  │  │  │  └───────────┼─────────────────────────┼───────────────┘
       │  │  │  │              │  (read)                  │  (read)
       ▼  ▼  ▼  ▼              ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA STORAGE LAYER                               │
│                                                                             │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │ PostgreSQL   │  │ Neo4j        │  │ ClickHouse   │  │ Redis        │  │
│   │ (Metadata &  │  │ (Dependency  │  │ (Time-Series │  │ (Cache &     │  │
│   │  Config)     │  │  Graph)      │  │  Events)     │  │  Pub/Sub)    │  │
│   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Layer descriptions:**

| Layer | Components | Role |
|-------|-----------|------|
| **Presentation** | Nginx Ingress, React SPA | TLS termination, single-page application UI |
| **Application** | FastAPI, Analysis Orchestrator, Cluster Manager, API Gateway, Change Detection Worker | Business logic, orchestration, cluster ops, change analysis |
| **Data Collection** | Inspektor Gadget DaemonSet (per node) | Kernel-level eBPF capture of network, DNS, process, file, security events |
| **Data Ingestion** | Ingestion Service, RabbitMQ, Graph Writer, Timeseries Writer | K8s metadata enrichment, event routing, batch writes (write path) |
| **Query** | Graph Query Service, Timeseries Query Service | Database-agnostic query abstraction for Neo4j and ClickHouse (read path) |
| **Data Storage** | PostgreSQL, Neo4j, ClickHouse, Redis | Metadata, dependency graph, time-series analytics, caching |

---

### Data Collection & Processing Flow

```
  ┌──────┐     ┌──────────┐     ┌──────────────┐     ┌─────────────────────┐
  │ User │────▶│ Frontend │────▶│ Backend API  │────▶│ Analysis            │
  └──────┘     └──────────┘     │ (FastAPI)    │     │ Orchestrator (gRPC) │
   Create &     POST /analyses  └──────┬───────┘     └──────────┬──────────┘
   Start                               │                        │
   Analysis                             │ Save config            │ Start collection
                                        ▼                        ▼
                                  ┌───────────┐          ┌──────────────┐
                                  │PostgreSQL │          │Kubernetes API│
                                  └───────────┘          └──────┬───────┘
                                                                │ Resolve scope
                                                                ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                     DATA COLLECTION (per node)                          │
  │                                                                         │
  │   ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  │
  │   │ Inspektor Gadget  │  │ Inspektor Gadget  │  │ Inspektor Gadget  │  │
  │   │ Node 1 (eBPF)     │  │ Node 2 (eBPF)     │  │ Node N (eBPF)     │  │
  │   │                   │  │                   │  │                   │  │
  │   │ • Network flows   │  │ • DNS queries     │  │ • Process events  │  │
  │   │ • DNS queries     │  │ • TLS/SNI events  │  │ • File events     │  │
  │   │ • Process events  │  │ • Security events │  │ • Mount events    │  │
  │   └────────┬──────────┘  └────────┬──────────┘  └────────┬──────────┘  │
  └────────────┼──────────────────────┼──────────────────────┼─────────────┘
               │                      │                      │
               └──────────────────────┼──────────────────────┘
                                      │ gRPC stream
                                      ▼
               ┌──────────────────────────────────────────┐
               │ Ingestion Service                         │
               │ (gRPC + Kubernetes metadata enrichment)   │
               │                                           │
               │ • Resolve pod names, labels, owners       │
               │ • Classify network types (Pod/Svc/Ext)    │
               │ • DNS enrichment for external endpoints   │
               └─────────────────┬─────────────────────────┘
                                 │
                                 ▼
               ┌──────────────────────────────────────────┐
               │ RabbitMQ (Event Routing)                  │
               │                                           │
               │  graph_events ──────▶ Graph Writer ──────▶ Neo4j
               │                       (batch upsert)      (dependency graph)
               │                                           │
               │  ts_events ─────────▶ Timeseries Writer ─▶ ClickHouse
               │                       (batch insert)      (time-series events)
               └──────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │                  CHANGE DETECTION (periodic)                            │
  │                                                                         │
  │   Change Detection Worker                                               │
  │   │                                                                     │
  │   ├──▶ Neo4j ──── Query current graph snapshot                          │
  │   ├──▶ PostgreSQL ── Compare with previous snapshot                     │
  │   ├──▶ ClickHouse ── Query eBPF event metrics                           │
  │   │                                                                     │
  │   └──▶ RabbitMQ ──▶ change_events ──▶ ClickHouse + WebSocket (alerts)  │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │                  QUERY & VISUALIZATION (Read Path)                      │
  │                                                                         │
  │   User ──▶ Frontend ──▶ Backend API ──┬──▶ Graph Query Service ──▶ Neo4j│
  │                                       │    (dependency map, impact,     │
  │                                       │     blast radius, Cypher)       │
  │                                       │                                 │
  │                                       └──▶ Timeseries Query    ──▶ CH  │
  │                                            Service                      │
  │                                            (events, stats, SQL)         │
  │                                                                         │
  │   Dev Console ──▶ Graph Query Service ──▶ Cypher queries ──▶ Neo4j     │
  │                  Timeseries Query Svc ──▶ SQL queries ──▶ ClickHouse   │
  └─────────────────────────────────────────────────────────────────────────┘
```

---

### Change Detection Architecture

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                        DETECTION SOURCES                                │
  │                                                                         │
  │   ┌─────────────────────────────┐   ┌─────────────────────────────┐    │
  │   │ Kubernetes API              │   │ eBPF Events (ClickHouse)    │    │
  │   │                             │   │                             │    │
  │   │ • Deployments, ReplicaSets  │   │ • network_flows             │    │
  │   │ • Services, Endpoints       │   │ • dns_queries               │    │
  │   │ • NetworkPolicies           │   │ • process_events            │    │
  │   │ • Ingresses, Routes         │   │ • tls_events, file_events   │    │
  │   │ • ConfigMaps, Secrets       │   │ • security_events           │    │
  │   └──────────────┬──────────────┘   └──────────────┬──────────────┘    │
  └──────────────────┼─────────────────────────────────┼───────────────────┘
                     │                                 │
                     ▼                                 ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    CHANGE DETECTION WORKER                              │
  │                                                                         │
  │   ┌────────────────────────────────────────────────────────┐           │
  │   │ Periodic Scheduler (configurable interval)              │           │
  │   └──────┬─────────────────────────────────┬───────────────┘           │
  │          │                                 │                           │
  │          ▼                                 ▼                           │
  │   ┌──────────────────┐            ┌──────────────────┐                │
  │   │ K8s Detector     │            │ eBPF Detector    │                │
  │   │ (30+ change      │            │ (Connection &    │                │
  │   │  types)          │            │  anomaly changes)│                │
  │   └────────┬─────────┘            └────────┬─────────┘                │
  │            │                               │                           │
  │            └───────────────┬───────────────┘                           │
  │                            ▼                                           │
  │                 ┌─────────────────────┐    ┌────────────────────┐      │
  │                 │ Strategy Engine     │    │ Circuit Breaker    │      │
  │                 │                     │    │ (3 failures → skip)│      │
  │                 └──┬──────┬──────┬───┘    └────────────────────┘      │
  │                    │      │      │                                     │
  │                    ▼      ▼      ▼                                     │
  │   ┌─────────────┐ ┌─────────────┐ ┌──────────────┐                   │
  │   │ Baseline    │ │ Rolling     │ │ Run          │                   │
  │   │ Strategy    │ │ Window      │ │ Comparison   │                   │
  │   │             │ │             │ │              │                   │
  │   │ First 10min │ │ Prev 5min   │ │ Current run  │                   │
  │   │ baseline vs │ │ vs current  │ │ vs previous  │                   │
  │   │ current     │ │ 5min        │ │ run          │                   │
  │   └─────────────┘ └─────────────┘ └──────────────┘                   │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                      STORAGE & DELIVERY                                 │
  │                                                                         │
  │   RabbitMQ (change_events exchange)                                     │
  │       │                                                                 │
  │       ├──▶ Timeseries Writer ──▶ ClickHouse (change_events table)      │
  │       │                                                                 │
  │       └──▶ WebSocket ──▶ Real-time UI alerts (critical changes)        │
  └─────────────────────────────────────────────────────────────────────────┘
```

---

### Data Architecture

Flowfish uses a polyglot persistence strategy, choosing the optimal database for each data type:

| Database | Data Stored | Why This Database |
|----------|------------|-------------------|
| **PostgreSQL** | Users, roles, clusters (encrypted credentials), analyses, configurations, audit logs | ACID compliance, relational integrity, encrypted storage |
| **Neo4j** | Workload nodes (Pod, Deployment, Service), communication edges (COMMUNICATES_WITH, PART_OF, EXPOSES, DEPENDS_ON) | Native graph traversal for dependency chains, impact analysis, and blast radius calculation |
| **ClickHouse** | Network flows, DNS queries, TCP connections, process events, file access events, security events, change events | Columnar storage, sub-second analytics on billions of rows, date-partitioned for retention |
| **Redis** | Session cache, real-time metrics, WebSocket pub/sub, distributed locks (leader election), rate limiting | Microsecond latency, pub/sub for real-time updates |
| **RabbitMQ** | Event routing (ingestion → writers, change events → timeseries writer) | Reliable delivery, dead-letter queues, decoupled producers/consumers |

**Data flow:**

1. **eBPF events** (write) → Ingestion Service → RabbitMQ → Graph Writer (Neo4j) + Timeseries Writer (ClickHouse)
2. **Kubernetes metadata** (write) → Ingestion Service enrichment → stored alongside events
3. **Change events** (write) → Change Detection Worker → RabbitMQ → Timeseries Writer (ClickHouse)
4. **Graph queries** (read) → Backend → Graph Query Service → Neo4j (dependency map, impact simulation, blast radius, Dev Console Cypher)
5. **Time-series queries** (read) → Backend → Timeseries Query Service → ClickHouse (events timeline, activity monitor, reports, Dev Console SQL)
6. **Config/auth** → Backend → PostgreSQL (users, clusters, analyses)

---

### Component Details

| Component | Technology | Role | Replicas |
|-----------|-----------|------|----------|
| **Frontend** | React 18 + TypeScript + Ant Design + React Flow | Single-page application, graph visualization | 2+ (HPA) |
| **Backend** | Python 3.11+ + FastAPI | REST API, WebSocket, business logic, auth | 3+ (HPA) |
| **Analysis Orchestrator** | Python + gRPC | Analysis lifecycle, gadget coordination | 1-3 |
| **Cluster Manager** | Python + gRPC | Multi-cluster connection gateway, credential decryption | 1-2 |
| **API Gateway** | Python + gRPC | Request routing, rate limiting | 1-2 |
| **Ingestion Service** | Python + gRPC | Event enrichment, metadata resolution | 2-4 |
| **Graph Writer** | Python | Batch write enriched events to Neo4j | 1-2 |
| **Graph Query Service** | Python + FastAPI | Query abstraction for Neo4j: dependency graph, communications, impact analysis, blast radius, path finding, Dev Console (Cypher) | 1-2 |
| **Timeseries Writer** | Python | Batch write enriched events and change events to ClickHouse | 1-2 |
| **Timeseries Query Service** | Python + FastAPI | Query abstraction for ClickHouse: event queries (network, DNS, process, file, security, OOM, SNI, mount, bind), statistics, Dev Console (SQL) | 1-2 |
| **Change Detection Worker** | Python | Periodic K8s + eBPF change detection, circuit breaker, WebSocket alerts | 1 (leader election) |
| **Inspektor Gadget** | Go + eBPF | Kernel-level event capture | 1 per node (DaemonSet) |
| **PostgreSQL** | 15+ | User, cluster, analysis config (ACID) | 1 master + 1 replica |
| **Neo4j** | 5.x Community | Dependency graph | 1+ |
| **ClickHouse** | 23+ | Time-series events, change events | 1-3 |
| **Redis** | 7+ | Session cache, pub/sub, distributed locks | 1 master + replicas |
| **RabbitMQ** | 3.x | Event routing | 1-3 (HA) |

---

## Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| **Data Collection** | Inspektor Gadget + eBPF | Latest | Kubernetes-native, zero-overhead kernel-level capture |
| **Backend** | Python + FastAPI | 3.11+ / 0.100+ | Async-native, auto OpenAPI docs, rich ecosystem |
| **Frontend** | React + TypeScript | 18+ / 5+ | Industry standard, component-based, type-safe |
| **UI Framework** | Ant Design | 5+ | Enterprise-grade, 60+ components, WCAG compliant |
| **Graph Visualization** | React Flow (@xyflow/react) | Latest | Interactive graph with custom nodes, 18 layout algorithms |
| **Relational DB** | PostgreSQL | 15+ | ACID compliance, JSONB, full-text search |
| **Graph DB** | Neo4j | 5.x | Native graph storage, Cypher queries, fast traversals |
| **Time-Series DB** | ClickHouse | 23+ | Columnar storage, sub-second analytics on billions of rows |
| **Cache** | Redis | 7+ | In-memory, pub/sub, distributed locks |
| **Message Queue** | RabbitMQ | 3.x | Reliable event routing, dead-letter queues |
| **Container** | Docker | 20.10+ | Industry standard containerization |
| **Orchestration** | Kubernetes (EKS, GKE, AKS, OpenShift, vanilla) | 1.27+ | Cloud-native orchestration, auto-scaling, self-healing |
| **IPC** | gRPC + Protobuf | 3.x | High-performance inter-service communication |
| **Auth** | JWT + OAuth 2.0 | — | Stateless auth, SSO integration |

---

## Getting Started

### Prerequisites

| Requirement | Minimum | Recommended |
|------------|---------|-------------|
| Kubernetes | 1.27+ | 1.29+ |
| OpenShift | 4.13+ | 4.15+ |
| kubectl / oc | Matching cluster version | Latest |
| RAM | 16 GB | 32 GB |
| CPU | 4 cores | 8 cores |
| Storage | 50 GB | 200 GB SSD |
| Docker (for local) | 20.10+ | Latest |
| Docker Compose (for local) | 2.0+ | Latest |

---

### Docker Compose Quick Start

For local development and evaluation:

```bash
git clone https://github.com/taylanbakircioglu/flowfish.git
cd flowfish

docker-compose -f deployment/docker-compose/docker-compose.yml up -d

# Wait for health checks (1-2 minutes)
docker-compose -f deployment/docker-compose/docker-compose.yml ps

# Access the UI
open http://localhost:3000
```

**Services started:**

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | React UI |
| Backend | 8000 | FastAPI REST API |
| Cluster Manager | 5001 | K8s API gateway (gRPC) |
| PostgreSQL | 5432 | Relational database |
| Redis | 6379 | Cache |
| ClickHouse | 8123 (HTTP), 9000 (TCP) | Time-series database |
| Neo4j | 7474 (HTTP), 7687 (Bolt) | Graph database |

---

### Kubernetes / K3s Quick Start (Recommended)

Deploy all Flowfish services directly from Docker Hub images — no need to clone the repository:

```bash
# One-line install
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s install
```

Or step by step:

```bash
REPO="https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test"

kubectl apply -f $REPO/00-namespace.yaml
kubectl apply -f $REPO/01-rbac.yaml
kubectl apply -f $REPO/02-databases.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish-local --timeout=120s

kubectl apply -f $REPO/03-migrations.yaml
kubectl apply -f $REPO/04-backend.yaml
kubectl apply -f $REPO/05-cluster-manager.yaml
kubectl apply -f $REPO/06-analysis-orchestrator.yaml
kubectl apply -f $REPO/07-ingestion-service.yaml
kubectl apply -f $REPO/08-graph-query.yaml
kubectl apply -f $REPO/09-timeseries-query.yaml
kubectl apply -f $REPO/10-graph-writer.yaml
kubectl apply -f $REPO/11-timeseries-writer.yaml
kubectl apply -f $REPO/12-change-detection-worker.yaml
kubectl apply -f $REPO/13-frontend.yaml
kubectl apply -f $REPO/14-nginx-proxy.yaml

# Access the UI
# http://<NODE_IP>:30080
```

**Deployed services:**

| # | Service | Port | Purpose |
|---|---------|------|---------|
| 00 | Namespace | — | `flowfish-local` namespace |
| 01 | RBAC | — | ServiceAccount, ClusterRole, ClusterRoleBinding |
| 02 | Databases | 5432, 8123, 6379, 7474, 5672 | PostgreSQL, ClickHouse, Redis, Neo4j, RabbitMQ |
| 03 | Migrations | — | PostgreSQL schema + ClickHouse schema (Job) |
| 04 | Backend | 8000 | FastAPI REST API + WebSocket |
| 05 | Cluster Manager | 5001 | K8s API gateway (gRPC) |
| 06 | Analysis Orchestrator | 5002 | Analysis lifecycle (gRPC) |
| 07 | Ingestion Service | 5000 | Event ingestion (gRPC) |
| 08 | Graph Query | 8001 | Neo4j query service (REST) |
| 09 | Timeseries Query | 8002 | ClickHouse query service (REST) |
| 10 | Graph Writer | — | Neo4j batch writer (worker) |
| 11 | Timeseries Writer | — | ClickHouse batch writer (worker) |
| 12 | Change Detection | 8001 | Change detection worker |
| 13 | Frontend | 3000 | React UI |
| 14 | Nginx Proxy | 30080 (NodePort) | Reverse proxy (UI + API) |

**Uninstall:**

```bash
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s uninstall
```

---

### Production Kubernetes Deployment

The full production manifests in `deployment/kubernetes-manifests/` are numbered for ordered deployment and include template variables for customization:

```
01 - Namespace + RBAC
02 - RBAC (extended)
03 - ConfigMaps + Migrations
04 - Secrets
05 - PostgreSQL
06 - RabbitMQ + Redis
07 - Neo4j
08 - Backend + ClickHouse
09 - Frontend + Inspektor Gadget Config/CRDs
10 - Ingestion Service + Inspektor Gadget DaemonSet
11 - Ingress + Timeseries Writer
12 - Cluster Manager
13 - Analysis Orchestrator + Cluster Manager RBAC
14 - API Gateway
15-19 - Graph Writer, Graph Query, Timeseries Query, Change Detection Worker, Gadget Monitoring
```

#### Production Checklist

- [ ] Replace all default passwords in `04-secrets.yaml`
- [ ] Adjust PVC sizes based on expected data volume
- [ ] Review CPU/memory limits in each deployment
- [ ] Configure TLS at ingress with valid certificates
- [ ] Update `11-ingress.yaml` with your domain
- [ ] Deploy Prometheus + Grafana for monitoring
- [ ] Configure PostgreSQL and Neo4j backups
- [ ] Scale backend to 3+ replicas
- [ ] Apply restrictive network policies
- [ ] Verify Inspektor Gadget RBAC/SCC on all nodes

For OpenShift:

```bash
oc adm policy add-scc-to-user privileged -z gadget -n flowfish
```

See `deployment/kubernetes-manifests/INSPEKTOR_GADGET_MANUAL_SETUP.md` and `OPENSHIFT_GADGET_FIX.md` for detailed guides.

---

### Default Credentials

| Service | Username | Password | Notes |
|---------|----------|----------|-------|
| Flowfish UI | `admin` | `admin123` | Change immediately after first login |
| PostgreSQL | `flowfish` | `flowfish123` | Via `04-secrets.yaml` |
| Neo4j | `neo4j` | `flowfish123` | Via `04-secrets.yaml` |
| ClickHouse | `flowfish` | `flowfish123` | Via `04-secrets.yaml` |
| Redis | — | `redis123` | Via `04-secrets.yaml` |
| RabbitMQ | `flowfish` | `flowfish123` | Via `04-secrets.yaml` |

> **Warning:** All default credentials must be changed before production deployment.

---

## Configuration

### Backend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://flowfish:flowfish123@postgres:5432/flowfish` | PostgreSQL connection string |
| `REDIS_URL` | `redis://:redis123@redis:6379/0` | Redis connection string |
| `CLICKHOUSE_URL` | `http://flowfish:flowfish123@clickhouse:8123` | ClickHouse HTTP URL |
| `NEO4J_BOLT_URI` | `bolt://neo4j:7687` | Neo4j Bolt protocol URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `flowfish123` | Neo4j password |
| `SECRET_KEY` | `super-secret-key-change-me` | JWT signing key |
| `JWT_EXPIRATION_HOURS` | `1` | JWT token lifetime |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ENABLE_CHANGE_DETECTION` | `true` | Enable change detection worker |
| `CHANGE_DETECTION_INTERVAL` | `60` | Change detection interval (seconds) |

### Frontend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_APP_API_URL` | `http://localhost:8000` | Backend API URL |
| `REACT_APP_ENABLE_DARK_MODE` | `true` | Enable dark mode toggle |

### Database Configuration

**PostgreSQL** — Relational data: users, clusters, analyses, configurations, audit logs. Schema applied via migration jobs.

**Neo4j** — Dependency graph. Vertex types: Cluster, Namespace, Pod, Deployment, StatefulSet, Service. Edge types: COMMUNICATES_WITH, PART_OF, EXPOSES, DEPENDS_ON.

**ClickHouse** — Time-series events: network_flows, dns_queries, tcp_connections, process_events, file_access_events, syscall_events, change_events. Date-partitioned.

**Redis** — Session cache, metrics cache, rate limiting, pub/sub, distributed locks.

**RabbitMQ** — Event routing between Ingestion Service and writers. Dead-letter queues for failed messages.

---

## API Reference

Interactive docs at `http://localhost:8000/api/docs` (Swagger) or `http://localhost:8000/api/redoc` (ReDoc).

| Endpoint Group | Base Path | Description |
|---------------|-----------|-------------|
| **Auth** | `/api/v1/auth` | Login, logout, refresh, user info |
| **Users** | `/api/v1/users` | User management |
| **API Keys** | `/api/v1/settings/api-keys` | API key creation, listing, and revocation |
| **Clusters** | `/api/v1/clusters` | Cluster management, namespace listing |
| **Analyses** | `/api/v1/analyses` | Create, start, stop, delete analyses |
| **Dependencies** | `/api/v1/dependencies` | Graph queries, upstream/downstream |
| **Communications** | `/api/v1/communications` | Network flow data |
| **AI Integration** | `/api/v1/communications/dependencies/*` | Dependency summary, stream, batch, diff, and impact for AI agents and CI/CD pipelines |
| **Changes** | `/api/v1/changes` | Change detection events |
| **Blast Radius** | `/api/v1/blast-radius` | Pre-deployment assessment |
| **Simulation** | `/api/v1/simulation` | Impact simulation |
| **Export** | `/api/v1/export` | Data export |
| **Reports** | `/api/v1/reports` | Report generation |
| **Query** | `/api/v1/query` | Developer console queries |
| **Settings** | `/api/v1/settings` | System configuration |

---

## Project Structure

```
flowfish/
├── backend/                        # FastAPI backend application
│   ├── main.py                     # Application entry point
│   ├── routers/                    # API route handlers
│   ├── services/                   # Business logic
│   │   ├── cluster_connection_manager.py
│   │   ├── change_detection/       # Detection strategies & detectors
│   │   └── connections/            # Cluster connection types
│   ├── database/                   # DB connection helpers
│   ├── workers/                    # Background workers
│   └── repositories/              # Data access layer
├── frontend/                       # React TypeScript application
│   └── src/
│       ├── pages/                  # Page components
│       ├── components/             # Reusable UI components
│       ├── store/api/              # RTK Query API slices
│       └── hooks/                  # Custom React hooks
├── services/                       # gRPC microservices
│   ├── ingestion-service/          # Event ingestion & enrichment
│   ├── graph-writer/               # Neo4j batch writer
│   ├── timeseries-writer/          # ClickHouse batch writer
│   ├── cluster-manager/            # K8s connection gateway
│   ├── analysis-orchestrator/      # Analysis lifecycle
│   ├── graph-query/                # Graph query service
│   └── timeseries-query/           # Time-series query service
├── proto/                          # Protocol Buffer definitions
├── schemas/                        # Database schemas (SQL)
├── deployment/
│   ├── docker-compose/             # Docker Compose files
│   ├── local-test/                 # Local K8s/K3s quick-start manifests
│   └── kubernetes-manifests/       # Production K8s/OpenShift manifests
├── pipelines/                      # CI/CD pipeline scripts
├── scripts/                        # Utility scripts
├── docs/                           # Documentation & screenshots
└── version.json                    # Version metadata
```

---

## Troubleshooting

### UI Not Loading

```bash
kubectl logs -l app=frontend -n flowfish
kubectl get svc frontend -n flowfish
kubectl exec -it deploy/frontend -n flowfish -- curl -s http://backend:8000/api/v1/health
```

### No Data in Dependency Map

```bash
kubectl logs -l app=backend -n flowfish | grep "analysis"
kubectl get pods -n flowfish -l app=inspektor-gadget
kubectl logs -l app=ingestion-service -n flowfish --tail=50
```

### Database Connection Issues

```bash
kubectl exec -it postgresql-0 -n flowfish -- pg_isready -U flowfish
kubectl exec -it neo4j-0 -n flowfish -- curl -s http://localhost:7474
kubectl exec -it clickhouse-0 -n flowfish -- wget -qO- http://localhost:8123/ping
kubectl exec -it deploy/redis -n flowfish -- redis-cli -a redis123 ping
```

### Inspektor Gadget Not Starting

```bash
kubectl get ds -n flowfish
kubectl describe pod -l app=inspektor-gadget -n flowfish
# Common: Missing RBAC → apply 10-inspektor-gadget-rbac-cluster.yaml
# OpenShift: oc adm policy add-scc-to-user privileged -z gadget -n flowfish
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See the [LICENSE](LICENSE) file for the full text.

In summary: you are free to use, modify, and distribute this software, but any modified version — including use over a network (SaaS) — **must also be released under AGPL-3.0 with full source code**. Commercial redistribution as a proprietary product is not permitted.

---

## Author

**Taylan Bakırcıoğlu**

- LinkedIn: [linkedin.com/in/taylanbakircioglu](https://www.linkedin.com/in/taylanbakircioglu/)
- GitHub: [@taylanbakircioglu](https://github.com/taylanbakircioglu)
- Email: taylanb@outlook.com

---

## Support

- **Issues:** [GitHub Issues](https://github.com/taylanbakircioglu/flowfish/issues)
- **Discussions:** [GitHub Discussions](https://github.com/taylanbakircioglu/flowfish/discussions)

---

**Version:** 2.3.0 | **Last Updated:** March 2026
