# Change Detection Worker

## Overview

The Change Detection Worker is a **standalone, scalable microservice** that detects infrastructure and behavioral changes in Kubernetes clusters using a **hybrid detection approach**:

- **K8s API Detector**: Polls Kubernetes API for infrastructure state changes (replicas, configs, images, resources, env, services, network policies, ingresses, routes)
- **eBPF Event Detector**: Analyzes eBPF events from ClickHouse for behavioral changes (connections, ports) and anomalies (traffic, DNS, process, error)

**ClickHouse-only Architecture**: All change events are stored exclusively in ClickHouse. PostgreSQL is used only for analysis metadata and workflow state.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Change Detection Worker                              │
│                        (Separate Pod/Deployment)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐          ┌─────────────────────┐                  │
│  │   K8s Detector      │          │   eBPF Detector     │                  │
│  │  (Infrastructure)   │          │   (Behavioral)      │                  │
│  │                     │          │                     │                  │
│  │  • replica_changed  │          │  • connection_added │                  │
│  │  • config_changed   │          │  • connection_removed│                 │
│  │  • image_changed    │          │  • port_changed     │                  │
│  │  • resource_changed │          │  • traffic_anomaly  │                  │
│  │  • env_changed      │          │  • dns_anomaly      │                  │
│  │  • spec_changed     │          │  • process_anomaly  │                  │
│  │  • label_changed    │          │  • error_anomaly    │                  │
│  │  • service_*        │          │                     │                  │
│  │  • network_policy_* │          │                     │                  │
│  │  • ingress_*        │          │                     │                  │
│  │  • route_*          │          │                     │                  │
│  └──────────┬──────────┘          └──────────┬──────────┘                  │
│             │                                │                              │
│             └───────────┬────────────────────┘                              │
│                         │                                                   │
│                         ▼                                                   │
│                ┌─────────────────┐                                         │
│                │  Change Merger  │                                         │
│                │  (All Changes)  │                                         │
│                └────────┬────────┘                                         │
│                         │                                                   │
└─────────────────────────┼───────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   K8s API    │   │  ClickHouse  │   │    Redis     │
│   (Source)   │   │  (Storage)   │   │   (Leader    │
│              │   │              │   │   Election)  │
└──────────────┘   └──────────────┘   └──────────────┘
```

## Detection Methods

### K8s API Detector (Infrastructure Changes)

The K8s Detector polls the Kubernetes API every detection cycle (default: 60 seconds) and compares the current state with the stored state in PostgreSQL.

| Change Type | Description | Detection Method |
|-------------|-------------|------------------|
| `replica_changed` | Deployment/StatefulSet replica count changed | Compare K8s API vs PostgreSQL |
| `config_changed` | ConfigMap/Secret content changed | `.data` hash comparison (OpenShift-safe) |
| `image_changed` | Container image updated | Layered spec hash per container |
| `resource_changed` | CPU/memory requests/limits changed | Per-container resource diff |
| `env_changed` | Environment variables changed | Env hash (values not logged) |
| `spec_changed` | Pod spec catch-all (probes, volumes) | spec_hash comparison |
| `label_changed` | Pod/Service labels modified | Label set comparison |
| `service_port_changed` | Service port/targetPort/protocol | Port tuple comparison |
| `service_selector_changed` | Service selector changed | Selector map diff |
| `service_type_changed` | Service type changed | Direct comparison |
| `service_added` / `removed` | Service lifecycle | K8s vs PostgreSQL |
| `network_policy_*` | NetworkPolicy lifecycle + spec | Spec hash comparison |
| `ingress_*` | Ingress lifecycle + spec | Spec hash (status ignored) |
| `route_*` | OpenShift Route lifecycle + spec | Spec hash (graceful fail) |

### eBPF Event Detector (Behavioral Changes + Anomalies)

The eBPF Detector queries ClickHouse tables (`network_flows`, `dns_queries`, `process_events`) for behavioral changes and statistical anomalies.

| Change Type | Description | Detection Method |
|-------------|-------------|------------------|
| `connection_added` | New connection appeared | Compare baseline vs current window |
| `connection_removed` | Connection disappeared | Compare baseline vs current window |
| `port_changed` | Same source/dest, different port | Track port changes per pair |
| `traffic_anomaly` | Volume 3x+ or latency 2.5x+ | Statistical threshold |
| `dns_anomaly` | New DNS domains, NXDOMAIN spikes | Baseline domain diff |
| `process_anomaly` | New/suspicious process execution | Process allowlist |
| `error_anomaly` | New error types or 2x+ rate | Error rate threshold |

## Detection Strategies

Users can select a detection strategy when creating an analysis:

### Baseline Strategy (Default)

Captures connections during the first N minutes as baseline, then detects deviations.

```
|-------- baseline (first 10 min) --------|
                                          |---- current (last 5 min) ----|
```

**Best for**: Long-running analyses, drift detection

### Rolling Window Strategy

Continuously compares recent time window vs previous window for real-time detection.

```
|---- previous (5 min ago) ----|---- current (last 5 min) ----|
```

**Best for**: Continuous monitoring, alerting

### Run Comparison Strategy

Compares current run against previous run. Ideal for deployment validation.

```
|-------- Run N-1 --------|
                          |-------- Run N (current) --------|
```

**Best for**: Deployment validation, canary deployments, A/B testing

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHANGE_DETECTION_ENABLED` | `true` | Enable/disable detection |
| `CHANGE_DETECTION_INTERVAL` | `60` | Detection interval (seconds) |
| `CHANGE_DETECTION_LOOKBACK_MINUTES` | `5` | How far back to look for changes |
| `LEADER_ELECTION_ENABLED` | `false` | Enable leader election for HA |
| `WORKER_INSTANCE_ID` | auto | Unique instance identifier |
| `CIRCUIT_BREAKER_THRESHOLD` | `3` | Failures before circuit opens |
| `CIRCUIT_BREAKER_RESET` | `300` | Seconds before circuit resets |

### Per-Analysis Configuration

Each analysis can have individual change detection settings:

| Field | Default | Description |
|-------|---------|-------------|
| `change_detection_enabled` | `true` | Enable/disable for this analysis |
| `change_detection_strategy` | `baseline` | Detection strategy to use |
| `change_detection_types` | `["all"]` | Types of changes to track |

## Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Detection Cycle (60s)                            │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    1. Get Active Analyses                               │
│                       (PostgreSQL)                                      │
│                                                                        │
│    SELECT id, cluster_ids, change_detection_strategy,                  │
│           change_detection_types FROM analyses                          │
│    WHERE status = 'running' AND change_detection_enabled = true        │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│   2a. K8s API Detection      │    │   2b. eBPF Event Detection   │
│       (Per Cluster)          │    │       (Per Analysis)         │
│                              │    │                              │
│   - Poll K8s deployments     │    │   - Query ClickHouse         │
│   - Compare with PostgreSQL  │    │     network_flows            │
│   - Detect replica changes   │    │   - Apply strategy           │
│   - Update stored state      │    │   - Compare time windows     │
└──────────────────────────────┘    └──────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     3. Merge All Changes                                │
│                                                                        │
│    - Filter by enabled types                                           │
│    - Assess risk levels                                                │
│    - Enrich with metadata                                              │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   4. Write to ClickHouse                                │
│                                                                        │
│    Via RabbitMQ → Timeseries Writer → ClickHouse change_events         │
│    (Fallback: Direct ClickHouse write)                                 │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  5. Notify Critical Changes                             │
│                                                                        │
│    POST to Backend /ws/broadcast for WebSocket notification            │
└────────────────────────────────────────────────────────────────────────┘
```

## ClickHouse Queries

### Baseline Connections Query

```sql
-- Get baseline connections (first 10 minutes of analysis)
SELECT DISTINCT 
    source_pod, dest_pod, dest_port, protocol
FROM network_flows
WHERE analysis_id = {analysis_id}
  AND timestamp BETWEEN {analysis_start} AND {analysis_start} + INTERVAL 10 MINUTE
```

### Current Connections Query

```sql
-- Get current connections (last 5 minutes)
SELECT DISTINCT 
    source_pod, dest_pod, dest_port, protocol
FROM network_flows
WHERE analysis_id = {analysis_id}
  AND timestamp > now() - INTERVAL 5 MINUTE
```

### Change Detection Result

```
added = current_connections - baseline_connections    → connection_added
removed = baseline_connections - current_connections  → connection_removed
```

## API Endpoints

### Health Check

```bash
GET /health
GET /healthz
```

Returns:
```json
{
  "status": "healthy",
  "instance_id": "abc123",
  "is_leader": true,
  "detection_cycles": 42,
  "last_detection": "2025-01-08T10:30:00Z"
}
```

### Readiness Check

```bash
GET /ready
GET /readyz
```

### Prometheus Metrics

```bash
GET /metrics
```

Metrics:
- `flowfish_change_worker_detection_cycles_total`
- `flowfish_change_worker_errors_total`
- `flowfish_change_worker_is_leader`
- `flowfish_change_worker_running`
- `flowfish_change_worker_circuits_open`
- `flowfish_change_worker_k8s_detections_total`
- `flowfish_change_worker_ebpf_detections_total`

### Manual Trigger

```bash
POST /trigger/{analysis_id}
```

Manually trigger change detection for a specific analysis.

## Deployment

### Single Instance (Simple Mode)

```yaml
spec:
  replicas: 1
  env:
  - name: LEADER_ELECTION_ENABLED
    value: "false"
```

### Multiple Instances (High Availability)

```yaml
spec:
  replicas: 3
  env:
  - name: LEADER_ELECTION_ENABLED
    value: "true"
```

## Troubleshooting

### No changes detected

1. **Check analysis settings**: Ensure `change_detection_enabled = true`
2. **Check enabled types**: Verify `change_detection_types` includes expected types
3. **Check eBPF data**: Query ClickHouse `network_flows` for the analysis
4. **Check K8s connectivity**: Verify cluster API is accessible

### K8s detection not working

1. Verify cluster configuration in PostgreSQL `clusters` table
2. Check API server URL and credentials
3. Review worker logs for K8s API errors

### eBPF detection not working

1. Ensure ClickHouse is accessible
2. Verify `network_flows` table has data for the analysis
3. Check strategy time windows (baseline may not be populated yet)

### Changes not appearing in UI

1. Check RabbitMQ connectivity
2. Verify timeseries-writer is consuming messages
3. Query ClickHouse `change_events` table directly

## Data Retention

Change events follow **analysis lifecycle-based retention**:

- **No TTL**: Change events are never automatically deleted based on time
- **Analysis Cascade**: When an analysis is deleted, all change events are removed:
  - ClickHouse: `DELETE FROM change_events WHERE analysis_id = ?`

---

**Version**: 3.0.0  
**Last Updated**: January 2026  
**Architecture**: Hybrid K8s API + eBPF Detection, ClickHouse-only Storage
