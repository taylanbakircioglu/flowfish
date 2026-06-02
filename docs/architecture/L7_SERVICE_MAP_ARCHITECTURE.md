# L7 Application Level Service Map - Architecture

## Overview

The L7 Service Map extends Flowfish's network observability from L4 (TCP/UDP) to L7 (HTTP/gRPC/DNS) using Grafana Beyla, an eBPF-based application observability tool. This enables full API gateway chain resolution (e.g., `A → APISIX → B`) that L4 eBPF cannot provide.

## Why Beyla?

- **eBPF-based**: Same kernel-level approach as Inspector Gadget, no sidecar/proxy needed
- **Apache 2.0 license**: Fully open source (unlike Kubeshark)
- **Multi-arch**: AMD64 + ARM64 support (~50MB image)
- **DaemonSet deployment**: Same pattern as Inspector Gadget
- **Rich L7 data**: HTTP method/path/status, gRPC service/method, DNS queries

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Target Kubernetes Cluster                      │
│                                                                   │
│  ┌─────────────────┐    OTLP push    ┌──────────────────────┐   │
│  │ Beyla DaemonSet  │ ──────────────► │ flowfish-l7-collector │   │
│  │ (eBPF L7 capture)│   port 4318     │ (OTLP receiver +     │   │
│  └─────────────────┘                  │  Pull API port 8080) │   │
│                                        └──────────────────────┘   │
└───────────────────────────────┬──────────────────────────────────┘
                                │ K8s API Service Proxy
                                │ (Flowfish → Cluster, one-way)
┌───────────────────────────────▼──────────────────────────────────┐
│                    Flowfish Central Platform                       │
│                                                                   │
│  ┌─────────────────┐         ┌─────────────────────┐            │
│  │ L7 Ingestion    │ ──────► │ RabbitMQ            │            │
│  │ Service          │  pub    │ flowfish.l7.*       │            │
│  │ (polling + enrich)│        └───────┬─────────────┘            │
│  └─────────────────┘                 │                           │
│                              ┌───────▼─────────┐                │
│                              │ Timeseries Writer│                │
│                              │ + Graph Writer   │                │
│                              │ (L7_ENABLED=true)│                │
│                              └───────┬─────────┘                │
│                      ┌───────────────┴───────────────┐          │
│                      ▼                               ▼          │
│              ┌──────────────┐               ┌──────────────┐    │
│              │ClickHouse    │               │ Neo4j        │    │
│              │l7_http_flows │               │ L7Workload   │    │
│              │l7_grpc_flows │               │ L7_COMM_WITH │    │
│              │l7_dns_flows  │               └──────────────┘    │
│              └──────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow - Two-Layer Event Transformation

### Layer 1 - flowfish-l7-collector (in-cluster)
- Receives OTLP spans from Beyla
- Transforms to intermediate Flowfish event format
- Does NOT add analysis_id or cluster_id
- Exposes pull API for Flowfish to consume

#### HTTP Path Extraction (v2.7.0+, Audit v4)

The transformer recovers the HTTP request path from a span by walking the
OpenTelemetry HTTP semantic-convention lookup chain. This is necessary
because Beyla emits **different attributes for SERVER and CLIENT spans**:

| Span kind | Stable attr (Beyla ≥ 3) | Legacy attr (OTel < 1.21) | Notes |
|-----------|-------------------------|---------------------------|-------|
| SERVER    | `url.path`              | `http.target`             | Path component only. `http.route` carries the templated form when the server framework exposes it. |
| CLIENT    | `url.full`              | `http.url`                | Absolute URL — transformer parses the path component out via `urllib.parse.urlsplit`. |

Lookup order inside `event_transformer._extract_http_path`:

1. `url.path` — server, stable
2. `http.route` — server, templated form (used when only this exists)
3. `url.full` — client, stable (path parsed out)
4. `http.target` — server, legacy (query string stripped)
5. `http.url` — client, legacy (path parsed out)
6. `"/"` — fallback (preserves historical edge shape)

Relative-path guard: `urlsplit("garbage").path` returns `"garbage"` because
the stdlib treats bare tokens as relative URLs. The helper only accepts the
parsed path when (`scheme` is present) **or** (`path` starts with `/`) —
otherwise it falls through to the next attribute. This prevents malformed
`url.full` payloads from poisoning the per-path edge MERGE key in Neo4j.

The HTTP branch trigger in `_transform_single_span` was widened in v2.7.0
to include `url.full`, `http.url`, and `http.target` so CLIENT spans no
longer get dropped silently. gRPC and DNS heuristics still take priority
to prevent misclassification.

### Layer 2 - L7 Ingestion Service (Flowfish central)
- Polls events via K8s API Service Proxy
- Adds analysis_id, cluster_id, cluster_name
- Applies namespace filters, L7 capture filters, sampling
- Publishes final events to RabbitMQ

## Key Design Decisions

1. **Complete isolation**: L7 pipeline uses separate tables, exchanges, queues, and node labels
2. **Same access model**: Uses K8s API Service Proxy like Inspector Gadget (cluster → Flowfish is never required)
3. **Feature flag**: `L7_ENABLED` controls writer consumers; `l7_enabled` in settings controls frontend visibility
4. **Beyla cluster-wide, Flowfish filters**: Beyla captures all namespaces; per-analysis filtering happens in L7 Ingestion Service

## Components

| Component | Type | Purpose |
|-----------|------|---------|
| Beyla DaemonSet | In-cluster | eBPF L7 traffic capture |
| flowfish-l7-collector | In-cluster | OTLP receiver + Pull API bridge |
| L7 Ingestion Service | Central | Polling, enrichment, RabbitMQ publishing |
| Timeseries Writer (L7) | Central | ClickHouse l7_* table inserts |
| Graph Writer (L7) | Central | Neo4j L7Workload graph updates |
| Graph Query (L7) | Central | L7 dependency graph queries |
| Timeseries Query (L7) | Central | L7 event queries and histograms |
| ServiceMap.tsx | Frontend | L7 service dependency visualization |

### RBAC Requirements

The L7 Collector ServiceAccount requires a ClusterRole with:
- `pods` - get, list (pod IP → workload resolution)
- `nodes` - get, list (node IP resolution, `spec.podCIDR` auto-detection)
- `services` - get, list (service ClusterIP resolution)

The install script also creates a namespace-scoped Role for `services/proxy` (allowing the L7 Ingestion Service to pull events via K8s API proxy).

## API Endpoints

### Backend (proxy to query services)
- `GET /api/v1/l7/communications` - L7 communication list
- `GET /api/v1/l7/dependencies/graph` - L7 dependency graph
- `GET /api/v1/l7/communications/stats` - L7 statistics
- `GET /api/v1/l7/communications/error-stats` - L7 error breakdown
- `GET /api/v1/l7/dependencies/summary` - Per-workload summary
- `GET /api/v1/l7/dependencies/tree-summary` - Tree-based dependencies
- `GET /api/v1/l7/events/http` - HTTP flow events
- `GET /api/v1/l7/events/grpc` - gRPC flow events
- `GET /api/v1/l7/events/dns` - DNS flow events
- `GET /api/v1/l7/events/stats` - Cross-protocol stats
- `GET /api/v1/l7/events/histogram` - HTTP 5-min histogram
- `GET /api/v1/settings/beyla` - Beyla configuration
- `PUT /api/v1/settings/beyla` - Update Beyla configuration

### Cluster Management
- `GET /clusters/beyla-install-script` - General Beyla install script
- `GET /clusters/{id}/beyla-install-script` - Cluster-specific install script
- `GET /clusters/{id}/beyla-upgrade-script` - Beyla upgrade script

## Database Schema

### ClickHouse (L7 tables)
- `l7_http_flows` - HTTP method, path, status, latency, sizes
- `l7_grpc_flows` - gRPC service, method, status
- `l7_dns_flows` - DNS query name, type, response
- `l7_http_flows_5min_mv` - 5-minute aggregation materialized view

> **Design Decision**: `network_type` is NOT stored in ClickHouse L7 tables. The enriched `namespace` and `workload_name` (which already encode network classification context, e.g., "cluster-infra" for nodes) are stored. `network_type` is only persisted in Neo4j for graph visualization. This avoids ClickHouse schema migration and keeps time-series queries simple.

### PostgreSQL (new columns)
- `clusters.beyla_namespace` - Beyla deployment namespace
- `clusters.beyla_health_status` - Health status
- `clusters.beyla_version` - Detected version
- `clusters.beyla_last_check` - Last health check timestamp
- `analyses.analysis_level` - 'l4', 'l7', or 'both'
- `analyses.l7_config` - L7 capture configuration (JSON)

### Neo4j (new labels)
- `L7Workload` nodes (separate from L4 `Workload`)
  - Properties: `id`, `name`, `namespace`, `cluster`, `analysis_id`, `kind`, `labels` (JSON string), `annotations` (JSON string), `owner_kind`, `network_type`, `is_external`, `last_seen`
  - Indexes: `l7_workload_owner_kind`, `l7_workload_network_type`
- `L7_COMMUNICATES_WITH` relationships

#### Per-Path Edge Model (v2.7.0+, Audit v4)

Each `L7_COMMUNICATES_WITH` relationship represents a **single (source, target,
analysis_id, http_method, http_path) tuple**. The graph-writer's MERGE
key was extended in v2.7.0 from `{analysis_id}` to the full 3-property
composite key:

```cypher
MERGE (src)-[r:L7_COMMUNICATES_WITH {
    analysis_id: row.analysis_id,
    http_method: coalesce(row.http_method, ''),
    http_path: coalesce(row.http_path, '')
}]->(dst)
```

Before this change every request between `(src, dst)` was upserted onto a
single edge, with `r.http_path` overwriting the previous value on each
flush — so the Service Map and Integration Hub effectively showed a
random recent path (typically the most frequent low-cardinality endpoint
such as `/health`). The new key keeps one edge per endpoint, so high-fan-out
clients (e.g. an API gateway that reaches `/users/{id}`, `/orders/{id}`,
`/payments/{txn}`) materialise as a small set of stable edges.

`coalesce(..., '')` ensures the MERGE key never contains `null` (Cypher
refuses null in MERGE keys); empty string is a valid sentinel for spans
that genuinely lack method/path metadata.

**Relationship indexes** (Neo4j 4.3+):
- `l7_comm_analysis ON (r.analysis_id)` — existing, drives per-analysis filters
- `l7_comm_protocol ON (r.protocol)` — existing
- `l7_comm_method ON (r.http_method)` — added v2.7.0
- `l7_comm_path ON (r.http_path)` — added v2.7.0

**Dedup migration:** `_MIGRATE_OUT_CYPHER` and `_MIGRATE_IN_CYPHER` use the
same 3-property MERGE key when re-pointing edges from `namespace='unknown'`
placeholders to real workloads. Without this the dedup pass would
silently collapse per-path edges back to a single edge every
`_DEDUP_EVERY_N_FLUSHES` cycles, re-introducing the bug.

#### Aggregation in graph-query

`get_l7_dependency_summary` keeps **distinct-peer sets** internally so the
per-path edge multiplication does not inflate `inbound_count` /
`outbound_count` in the API response. A workload that talks to one
downstream service over five endpoints shows `outbound_count = 1` (with
`request_count` totalled across all five edges).

## Metadata Enrichment

L7 workloads are enriched with Kubernetes metadata via the `k8s_metadata` cache in `flowfish-l7-collector`. The cache resolves IPs using multiple sources:

1. **Pod IP cache** (highest priority): Pod metadata including labels, annotations, owner_kind
2. **Node IP cache**: Worker node IPs → `namespace: "cluster-infra"`, `owner_kind: "Node"`, `network_type: "Node-Network"`
3. **Service ClusterIP cache**: Service VIPs → `namespace: <service_ns>`, `owner_kind: "Service"`, `network_type: "Service-Network"`
4. **CIDR classification** (fallback): Unresolved IPs classified using L4-consistent CIDR rules (Pod-Network, Service-Network, Internal-Network, External-Network, etc.)

### Hostname Resolution

When Beyla sends hostnames instead of IPs (e.g., `worker5.example.com`, `kafka.example-ns`, `svc.ns.svc.cluster.local`), the `resolve_hostname()` function resolves them through a 4-tier pipeline:

1. **Node hostname** — exact match against `_hostname_cache` (e.g., `worker5.example.com` → Node-Network)
2. **K8s FQDN** — `*.svc.cluster.local` parsed to extract namespace and service name
3. **service.namespace** — `name.namespace` pattern matched against known namespaces and service name cache
4. **Short service name** — single-word hostname (e.g., `sentry`) scanned in service name cache

Hostnames and IPs with embedded ports (e.g., `elasticsearch-master:9200`, `172.30.0.1:443`) are port-stripped before resolution. Loopback addresses (`localhost`, `127.0.0.1`, `::1`) are classified as `Pod-Network` with `namespace: "loopback"`. Unrecognized hostnames are classified as `External-Network` with `namespace: "external"`. Empty namespace/workload values are normalised to `"unknown"` in both Neo4j (graph-writer) and ClickHouse (timeseries-writer) for query consistency.

### Unknown Node Dedup

Neo4j node IDs include namespace (`l7:{aid}:{cid}:{ns}:{workload}`). When the same endpoint is initially unresolved (`unknown`) and later enriched, a duplicate node could form. The graph-writer handles this at two levels:

1. **Write-time redirect**: The UNWIND Cypher checks if an enriched node already exists (same analysis, cluster, workload name) before creating an `unknown` duplicate, redirecting the edge to the existing node. Cluster filtering prevents cross-cluster mismatches in multi-cluster analyses.
2. **Periodic promotion**: Every 20 flushes, a background thread finds `unknown` nodes that have enriched counterparts within the same cluster, picks the most recently seen good node, migrates all edge metrics (including self-loops), and deletes the stale node.

### IP Classification (network_type)
The `classify_ip_network_type()` function in `k8s_metadata.py` mirrors the L4 `graph_builder.py` classification for consistency:
- `10.128-131.x.x` → Pod-Network (OpenShift default)
- `10.194.x.x`, `10.208.x.x` → Pod-Network (OpenShift additional)
- `10.96-111.x.x` → Service-Network (K8s default)
- `172.30.x.x` → Service-Network (OpenShift service)
- `100.64-127.x.x` → Internal-Network (CGNAT/OVN)
- Public IPs → External-Network

### CIDR Auto-Detection
The collector auto-detects pod CIDRs from `node.spec.podCIDR` during cache refresh (IPv4 only, IPv6 skipped, deduplicated). Auto-detected CIDRs are actively used by `classify_ip_network_type()` as a fallback for `10.x.x.x` IPs that don't match static rules — preventing them from being misclassified as `Internal-Network`. Headless services (`clusterIP: "None"`) are filtered from the service cache.

### Dependency Guard
All filters use **dimmed mode** instead of hiding: filtered-out nodes are shown at low opacity (0.15) with edges preserved. This prevents losing critical dependencies (e.g., kube-dns connections).

### Key Features
- **Label/annotation-based filtering** in both the `summary` and `tree-summary` APIs (`label_key`, `label_value`, `annotation_key`, `annotation_value`). Filter values support fnmatch globs (`*`, `?`, `[seq]`) for L4 parity. v2.6.0+
- **Owner-name / pod-name filtering** in `summary` (`owner_name` alias for `workload_name`, `pod_name`). v2.6.0+
- **`is_matched` flag** in `summary` response so callers can tell originally matched workloads from their neighbours when a filter is active. v2.6.0+
- **`workload_name_exact` flag** in `tree-summary` (default true for backward compatibility) — set false for case-insensitive substring match. v2.6.0+
- **`filter_noise_annotations` flag** in `summary` opts in to stripping infrastructure annotations from the response (matches the L4 summary aggregator behaviour). v2.6.0+
- **Owner kind visibility** (Deployment, StatefulSet, DaemonSet, Node, Service) in the Service Map drawer and Integration Hub tables
- **Noisy key filtering**: Infrastructure labels (`pod-template-hash`, `controller-revision-hash`) and annotations (`kubectl.kubernetes.io/*`, `kubernetes.io/*`, `openshift.io/*`) are automatically removed
- **Multi-protocol filtering**: Backend supports `protocols` (comma-separated) with backward-compatible `protocol` (single) parameter
- **Error breakdown**: Stats bar tooltip and drawer panel show HTTP status code distribution

### API Parameters for Metadata

| Endpoint | Parameters |
|---|---|
| `/l7/dependencies/graph` | `protocols` (comma-separated, e.g. `http,grpc`), `protocol` (single, backward compat), `namespaces` (comma-separated), `include_metadata` (bool, default true) |
| `/l7/dependencies/summary` | `namespace`, `include_metadata` (bool, default true), `annotation_key`, `annotation_value`, `label_key`, `label_value`, `owner_name` (alias for `workload_name`), `pod_name`, `workload_name`, `filter_noise_annotations` (bool, default false). Filter values support fnmatch globs (`*`, `?`, `[seq]`). When any filter is active, matched workloads are tagged `is_matched=true` and immediate neighbours `is_matched=false` so callers retain dependency context. |
| `/l7/dependencies/tree-summary` | `label_key`, `label_value`, `annotation_key`, `annotation_value`, `include_metadata`, `workload_name_exact` (bool, default true — set false for case-insensitive substring, matching the L4 `owner_name` semantic) |
| `/l7/communications/error-stats` | `namespace` |

## Service Map Layouts

The Service Map supports multiple layout algorithms:

| Layout | Description |
|---|---|
| Dagre (Top→Bottom) | Hierarchical DAG layout (default) |
| Dagre (Left→Right) | Horizontal DAG layout |
| Namespace Cluster | Groups nodes by namespace in grid cells |
| Concentric | Places high-degree nodes at center, expanding outward |
| Organic / Spiral | Golden-angle phyllotaxis pattern |
| Error-Centric | Places high-error-rate nodes at center |

### Canvas Edge Bundling (v2.7.0+)

The Neo4j per-path edge model means a single dependency between two
workloads can materialise as tens of raw edges (one per HTTP endpoint).
React Flow renders one visual edge per `Edge` object, so passing the raw
edges to the canvas would stack tens of arrows on top of each other and
make the labels unreadable.

`ServiceMap.tsx` therefore bundles raw edges by `(source_id, target_id,
protocol)` in `rfEdges`. Each bundle becomes **one** React Flow edge with:

- **Aggregated label** — total requests, request-weighted average latency,
  protocol, and `N paths` suffix when the bundle covers more than one
  endpoint.
- **`data.paths` array** — full per-path breakdown carried alongside the
  aggregate so the drawer can show individual `(method, path,
  request_count, error_count, avg_latency_ms)` rows without an extra
  backend round-trip.
- **Primary endpoint** — `data.httpMethod` / `data.httpPath` are still
  populated from the heaviest path so legacy code paths (CSV/JSON
  export, third-party integrations) keep working.

The CSV edge export expands `data.paths` into one row per endpoint so an
operator running `Export → CSV` still sees every path. JSON export
spreads `data` verbatim, so consumers automatically see the `paths`
array as a structured field.

The drawer's "Connections" tab iterates `rawEdges` (un-bundled) so the
operator sees one row per `(peer, protocol, method, path)` — the
expected behaviour for a detailed view.

`request_count` totals are computed correctly in both the bundled and
un-bundled paths because every raw edge contributes its own
`request_count`; bundling sums them.
