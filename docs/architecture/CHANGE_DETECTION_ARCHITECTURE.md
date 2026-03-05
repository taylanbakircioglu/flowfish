# Change Detection Architecture

## Overview

Flowfish Change Detection uses a **hybrid approach** combining two data sources to provide comprehensive infrastructure and behavioral change detection:

| Source | Data Type | Detection Method |
|--------|-----------|------------------|
| K8s API | Infrastructure state | Poll and compare |
| eBPF Events | Runtime behavior | Baseline diff |

This architecture ensures both infrastructure changes (replicas, configs) and behavioral changes (network connections) are detected and tracked.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Change Detection System                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Data Sources                                           │
├─────────────────────────────────┬────────────────────────────────────────────────┤
│                                 │                                                │
│  ┌─────────────────────────┐    │    ┌─────────────────────────────────────┐    │
│  │     Kubernetes API       │    │    │         ClickHouse                   │    │
│  │                         │    │    │     (network_flows table)            │    │
│  │  • Deployments          │    │    │                                      │    │
│  │  • StatefulSets         │    │    │  • Source Pod                        │    │
│  │  • ConfigMaps           │    │    │  • Dest Pod                          │    │
│  │  • Services             │    │    │  • Port                              │    │
│  │  • Labels               │    │    │  • Protocol                          │    │
│  └───────────┬─────────────┘    │    └─────────────────┬───────────────────┘    │
│              │                  │                      │                         │
└──────────────┼──────────────────┴──────────────────────┼─────────────────────────┘
               │                                         │
               │            ┌────────────────────────────┼───────────────────────┐
               │            │                            │                       │
               ▼            │            ▼               ▼                       │
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         Change Detection Worker                                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────────┐          ┌─────────────────────────┐             │
│   │     K8s Detector        │          │     eBPF Detector       │             │
│   │                         │          │                         │             │
│   │  Infrastructure Changes │          │   Behavioral Changes    │             │
│   │                         │          │                         │             │
│   │  ✓ replica_changed      │          │  ✓ connection_added     │             │
│   │  ✓ config_changed       │          │  ✓ connection_removed   │             │
│   │  ✓ image_changed        │          │  ✓ port_changed         │             │
│   │  ✓ resource_changed     │          │  ✓ traffic_anomaly      │             │
│   │  ✓ env_changed          │          │  ✓ dns_anomaly          │             │
│   │  ✓ spec_changed         │          │  ✓ process_anomaly      │             │
│   │  ✓ label_changed        │          │  ✓ error_anomaly        │             │
│   │  ✓ service_port_changed │          │                         │             │
│   │  ✓ service_selector_chg │          │                         │             │
│   │  ✓ service_type_changed │          │                         │             │
│   │  ✓ service_added/removed│          │                         │             │
│   │  ✓ network_policy_*     │          │                         │             │
│   │  ✓ ingress_*            │          │                         │             │
│   │  ✓ route_* (OpenShift)  │          │                         │             │
│   └───────────┬─────────────┘          └───────────┬─────────────┘             │
│               │                                    │                            │
│               │        ┌───────────────────────────┘                            │
│               │        │                                                        │
│               ▼        ▼                                                        │
│         ┌─────────────────────┐                                                │
│         │   Change Merger     │                                                │
│         │                     │                                                │
│         │  - Filter by types  │                                                │
│         │  - Assess risk      │                                                │
│         │  - Enrich metadata  │                                                │
│         └──────────┬──────────┘                                                │
│                    │                                                            │
└────────────────────┼────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              Storage Layer                                        │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         ClickHouse                                       │   │
│   │                     (change_events table)                                │   │
│   │                                                                          │   │
│   │  Columns: event_id, analysis_id, cluster_id, change_type, risk_level,   │   │
│   │           target_name, target_namespace, before_state, after_state,     │   │
│   │           affected_services, detected_at, source (k8s_api|ebpf_events)  │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Detection Strategies

### Baseline Strategy (Default)

Captures connections during the first N minutes as baseline, then compares current connections against that baseline.

**Timeline:**
```
|-------- baseline (first 10 min) --------|
                                          |---- current (last 5 min) ----|
                                                                         ^
                                                                    detection point
```

**Best for:**
- Long-running analyses
- Drift detection from known good state
- Compliance monitoring

**Algorithm:**
```python
baseline_connections = query_clickhouse(
    analysis_id, 
    start=analysis_start, 
    end=analysis_start + 10 minutes
)

current_connections = query_clickhouse(
    analysis_id,
    start=now - 5 minutes,
    end=now
)

added = current - baseline       # CONNECTION_ADDED events
removed = baseline - current     # CONNECTION_REMOVED events
```

### Rolling Window Strategy

Compares recent time window against previous window for real-time change detection.

**Timeline:**
```
|---- previous (5 min ago) ----|---- current (last 5 min) ----|
                                                              ^
                                                         detection point
```

**Best for:**
- Continuous monitoring
- Real-time alerting
- Security incident detection

### Run Comparison Strategy

Compares current analysis run against previous run for deployment validation.

**Timeline:**
```
|-------- Run N-1 (completed) --------|
                                      |-------- Run N (current) --------|
                                                                        ^
                                                                   detection point
```

**Best for:**
- Deployment validation
- Canary deployments
- A/B testing
- Release verification

## Change Types

### Pillar 1: Infrastructure Changes (K8s API) -- Deterministic

| Change Type | Detection Method | Risk Assessment |
|-------------|-----------------|-----------------|
| `replica_changed` | Compare Deployment/StatefulSet replicas vs PostgreSQL | Scale to 0 = Critical |
| `config_changed` | Track ConfigMap/Secret `.data` hash (metadata ignored for OpenShift) | Medium |
| `image_changed` | Compare container image refs via layered spec hash | High (deployment event) |
| `resource_changed` | Compare CPU/memory requests/limits per container | Medium |
| `env_changed` | Compare env var hash per container (values not logged) | Medium |
| `spec_changed` | Catch-all: any spec.template.spec change not covered above | Low |
| `label_changed` | Compare label maps | Low-Medium |
| `service_port_changed` | Compare port/targetPort/protocol/name tuples | High |
| `service_selector_changed` | Compare selector maps (affects routing) | High |
| `service_type_changed` | Compare ClusterIP/NodePort/LoadBalancer | Medium |
| `service_added` / `service_removed` | Lifecycle detection against stored state | Low / High |
| `network_policy_added` / `removed` / `changed` | Spec hash comparison (status ignored) | Low / High / Medium |
| `ingress_added` / `removed` / `changed` | Spec hash comparison (LB status ignored) | Low / Medium / Medium |
| `route_added` / `removed` / `changed` | Spec hash comparison (OpenShift, graceful fail) | Low / Medium / Medium |
| `workload_added` / `workload_removed` | Deployment/StatefulSet lifecycle | Low / Medium-High |

### Pillar 2: Behavioral Changes (eBPF) -- Deterministic + Statistical

| Change Type | Detection Method | Risk Assessment |
|-------------|-----------------|-----------------|
| `connection_added` | New connection not in baseline | Medium (new dependency) |
| `connection_removed` | Connection in baseline missing now | High (possible outage) |
| `port_changed` | Same pods, different port | Medium (config change) |
| `traffic_anomaly` | Volume 3x+ / latency 2.5x+ baseline | Variable |
| `dns_anomaly` | New domains, NXDOMAIN spikes | Medium |
| `process_anomaly` | New/suspicious process execution | High |
| `error_anomaly` | New error types or 2x+ error rate | Medium-High |

## Configuration Options

### Per-Analysis Settings

```typescript
interface AnalysisChangeDetectionConfig {
  change_detection_enabled: boolean;     // Default: true
  change_detection_strategy: 'baseline' | 'rolling_window' | 'run_comparison';
  change_detection_types: string[];      // ['all'] or specific types
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHANGE_DETECTION_INTERVAL` | `60` | Detection cycle interval (seconds) |
| `BASELINE_DURATION_MINUTES` | `10` | Baseline capture period |
| `CURRENT_WINDOW_MINUTES` | `5` | Current window for comparison |
| `ROLLING_WINDOW_MINUTES` | `5` | Window size for rolling strategy |

## Data Flow

### Detection Cycle

```
1. Worker wakes up (every 60s)
        │
        ▼
2. Fetch active analyses from PostgreSQL
   (WHERE status='running' AND change_detection_enabled=true)
        │
        ▼
3. For each analysis:
   │
   ├─► Check change_detection_types
   │   │
   │   ├─► K8s types enabled? → Run K8s Detector
   │   │                         │
   │   │                         └─► Get deployments via ClusterConnectionManager
   │   │                         └─► Compare with PostgreSQL baseline
   │   │                         └─► Generate changes
   │   │
   │   └─► eBPF types enabled? → Run eBPF Detector
   │                             │
   │                             └─► Query ClickHouse
   │                             └─► Apply strategy
   │                             └─► Generate changes
   │
   └─► Merge all changes
       │
       └─► Filter by enabled types
       └─► Assess risk levels
       └─► Write to ClickHouse
       └─► Notify critical changes (WebSocket)
```

### K8s Detector - Gateway Architecture (January 2026)

The K8s Detector uses `ClusterConnectionManager` for all Kubernetes API access.
ALL remote cluster API calls route through `cluster-manager` gRPC gateway.

**Architecture:**

```
change-detection-worker
        │
        ▼
    k8s_detector.py
        │
        └─► cluster_connection_manager.get_deployments()
                    │
            ┌───────┴───────┐
            ▼               ▼
    InClusterConnection   RemoteTokenConnection
            │                       │
            ▼                       ▼
    gRPC → cluster-manager    gRPC → cluster-manager
            │                       │
            ▼                       ▼
    ┌───────────────────────────────────┐
    │        cluster-manager Pod        │
    │   KubernetesClientFactory         │
    │      (cached clients, TTL 5min)   │
    │                                   │
    │   ┌──────────┐  ┌──────────────┐  │
    │   │In-Cluster│  │Remote Clients│  │
    │   │  Client  │  │(from DB creds)│  │
    │   └────┬─────┘  └──────┬───────┘  │
    └────────┼───────────────┼──────────┘
             │               │
             ▼               ▼
      Local K8s API    Remote K8s APIs
```

**Benefits:**
- Centralized K8s API access from single pod
- Unified credential decryption in cluster-manager
- Better network security (single egress point)
- Connection pooling and caching across requests

### ClickHouse Queries

**Baseline Connections:**
```sql
SELECT DISTINCT 
    source_pod, dest_pod, dest_port, protocol
FROM network_flows
WHERE analysis_id = {analysis_id}
  AND timestamp BETWEEN {analysis_start} 
                    AND {analysis_start} + INTERVAL 10 MINUTE
```

**Current Connections:**
```sql
SELECT DISTINCT 
    source_pod, dest_pod, dest_port, protocol
FROM network_flows
WHERE analysis_id = {analysis_id}
  AND timestamp > now() - INTERVAL 5 MINUTE
```

## API Reference

### Create Analysis with Change Detection

```bash
POST /api/v1/analyses
```

```json
{
  "name": "Production Analysis",
  "scope": { ... },
  "gadgets": { ... },
  "time_config": { ... },
  "change_detection_enabled": true,
  "change_detection_strategy": "baseline",
  "change_detection_types": ["all"]
}
```

### Get Changes

```bash
GET /api/v1/changes?analysis_id=123&change_types=connection_added,replica_changed
```

### Get Change Stats

```bash
GET /api/v1/changes/stats/summary?analysis_id=123&days=7
```

## Best Practices

1. **Start with Baseline**: Use baseline strategy for new analyses to establish normal behavior
2. **Use Rolling for Alerts**: Switch to rolling_window for continuous monitoring with alerting
3. **Run Comparison for Deployments**: Use run_comparison to validate deployments
4. **Filter Types Appropriately**: Only enable relevant change types to reduce noise
5. **Monitor Baseline Period**: Ensure baseline captures representative traffic

## Troubleshooting

### No changes detected

1. Verify `change_detection_enabled = true` on analysis
2. Check if analysis has `status = 'running'`
3. Verify `network_flows` has data for the analysis
4. Check if baseline period has completed (for baseline strategy)

### False positives

1. Extend baseline duration for more representative baseline
2. Use rolling_window strategy for dynamic environments
3. Filter to specific change types

### Performance issues

1. Reduce detection interval (increase to 120s or more)
2. Limit change types to essential ones
3. Use smaller time windows

---

**Version**: 2.0.0  
**Last Updated**: February 2026  
**Architecture**: Two-Pillar Hybrid (K8s API Infrastructure + eBPF Behavioral) Detection
