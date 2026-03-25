# Flowfish Metadata Enrichment Architecture

## Overview

Flowfish enriches network flow events with Kubernetes metadata to provide meaningful context in the Live Map visualization. This document describes the complete data flow from eBPF event capture to frontend display.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              KUBERNETES CLUSTER                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                     Inspektor Gadget DaemonSet                               │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │    │
│  │  │ trace_tcp    │  │ trace_dns    │  │ trace_exec   │  │ trace_*      │     │    │
│  │  │ (eBPF)       │  │ (eBPF)       │  │ (eBPF)       │  │ (eBPF)       │     │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │    │
│  │         │                 │                 │                 │              │    │
│  │         └─────────────────┴─────────────────┴─────────────────┘              │    │
│  │                                    │                                         │    │
│  │                                    ▼                                         │    │
│  │                       ┌─────────────────────┐                                │    │
│  │                       │  JSON Event Stream  │                                │    │
│  │                       │  (stdout)           │                                │    │
│  │                       └──────────┬──────────┘                                │    │
│  └──────────────────────────────────┼───────────────────────────────────────────┘    │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         ingestion-service                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐ │   │
│  │  │                    kubectl_gadget_client.py                              │ │   │
│  │  │  ┌────────────────────────────────────────────────────────────────────┐ │ │   │
│  │  │  │ _normalize_event()                                                  │ │ │   │
│  │  │  │ • Parse k8s context (namespace, pod, container, node)              │ │ │   │
│  │  │  │ • Extract src_ip, dst_ip, src_port, dst_port                       │ │ │   │
│  │  │  │ • Handle accept vs connect events:                                  │ │ │   │
│  │  │  │   - connect: k8s context = SOURCE (outgoing)                       │ │ │   │
│  │  │  │   - accept:  k8s context = DESTINATION (incoming), swap src/dst    │ │ │   │
│  │  │  │ • Set direction: "inbound" or "outbound"                           │ │ │   │
│  │  │  └────────────────────────────────────────────────────────────────────┘ │ │   │
│  │  └─────────────────────────────────────────────────────────────────────────┘ │   │
│  │                                     │                                         │   │
│  │                                     ▼                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐ │   │
│  │  │                        trace_manager.py                                  │ │   │
│  │  │  ┌────────────────────────────────────────────────────────────────────┐ │ │   │
│  │  │  │ PodDiscovery (pod_discovery.py)                                     │ │ │   │
│  │  │  │ • Runs `kubectl get pods -A -o json` or gRPC ListPods every 30s   │ │ │   │
│  │  │  │ • Builds IP → Pod metadata cache                                    │ │ │   │
│  │  │  │ • Extracts: name, namespace, labels, annotations,                  │ │ │   │
│  │  │  │   ownerReferences, pod_uid, host_ip, container, image,            │ │ │   │
│  │  │  │   service_account, phase                                           │ │ │   │
│  │  │  │ • Enriches pods with Deployment/StatefulSet annotations            │ │ │   │
│  │  │  │   (owner annotations merged; pod annotations take priority)        │ │ │   │
│  │  │  └────────────────────────────────────────────────────────────────────┘ │ │   │
│  │  │                                     │                                   │ │   │
│  │  │  ┌────────────────────────────────────────────────────────────────────┐ │ │   │
│  │  │  │ _publish_event()                                                    │ │ │   │
│  │  │  │ • Enrich dst_ip: lookup in PodDiscovery cache → dst_pod, dst_ns,   │ │ │   │
│  │  │  │   dst_labels, dst_owner_kind, dst_owner_name, ...                  │ │ │   │
│  │  │  │ • Enrich src_ip: lookup in PodDiscovery cache → src_pod, src_ns,   │ │ │   │
│  │  │  │   labels, owner_kind, owner_name, ...                              │ │ │   │
│  │  │  │ • Important for accept events where src is external                │ │ │   │
│  │  │  └────────────────────────────────────────────────────────────────────┘ │ │   │
│  │  └─────────────────────────────────────────────────────────────────────────┘ │   │
│  │                                     │                                         │   │
│  │                                     ▼                                         │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐ │   │
│  │  │                     event_transformer.py                                 │ │   │
│  │  │  • transform_network_flow(): Build structured message                   │ │   │
│  │  │  • Include all src_* and dst_* fields                                   │ │   │
│  │  │  • Include labels, owner info, metadata                                 │ │   │
│  │  └─────────────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                              RabbitMQ                                         │   │
│  │  ┌───────────────────────────────┐  ┌───────────────────────────────────┐    │   │
│  │  │ flowfish.network_flows        │  │ flowfish.workload_metadata        │    │   │
│  │  │ (network flow events)         │  │ (pod metadata updates)            │    │   │
│  │  └───────────────────────────────┘  └───────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                    │                                    │                            │
│                    ▼                                    ▼                            │
│  ┌─────────────────────────────────┐  ┌────────────────────────────────────────┐   │
│  │     timeseries-writer           │  │          graph-writer                   │   │
│  │  • Write to ClickHouse          │  │  ┌────────────────────────────────────┐ │   │
│  │  • network_flows table          │  │  │ graph_builder.py                   │ │   │
│  │  • workload_metadata table      │  │  │ • Build vertices with all metadata │ │   │
│  │                                 │  │  │ • src_labels, dst_labels (JSON)    │ │   │
│  │                                 │  │  │ • owner_kind, owner_name           │ │   │
│  │                                 │  │  │ • pod_uid, host_ip, container, ... │ │   │
│  │                                 │  │  └────────────────────────────────────┘ │   │
│  │                                 │  │                    │                     │   │
│  │                                 │  │  ┌────────────────────────────────────┐ │   │
│  │                                 │  │  │ graph_client.py                    │ │   │
│  │                                 │  │  │ upsert_edge():                     │ │   │
│  │                                 │  │  │ • MERGE nodes with full metadata   │ │   │
│  │                                 │  │  │ • SET labels, owner, pod_uid, etc. │ │   │
│  │                                 │  │  │ • Use CASE WHEN to prefer new data │ │   │
│  │                                 │  │  └────────────────────────────────────┘ │   │
│  └─────────────────────────────────┘  └────────────────────────────────────────┘   │
│                    │                                    │                            │
│                    ▼                                    ▼                            │
│  ┌─────────────────────────────────┐  ┌────────────────────────────────────────┐   │
│  │          ClickHouse             │  │              Neo4j                      │   │
│  │  ┌───────────────────────────┐  │  │  ┌────────────────────────────────────┐ │   │
│  │  │ network_flows             │  │  │  │ Workload nodes                     │ │   │
│  │  │ • src_namespace, src_pod  │  │  │  │ • id, name, namespace, kind        │ │   │
│  │  │ • dst_namespace, dst_pod  │  │  │  │ • labels (JSON string)             │ │   │
│  │  │ • protocol, direction     │  │  │  │ • owner_kind, owner_name           │ │   │
│  │  │ • bytes, packets, latency │  │  │  │ • pod_uid, host_ip, container      │ │   │
│  │  └───────────────────────────┘  │  │  │ • image, service_account, phase    │ │   │
│  │  ┌───────────────────────────┐  │  │  └────────────────────────────────────┘ │   │
│  │  │ workload_metadata         │  │  │  ┌────────────────────────────────────┐ │   │
│  │  │ • Full pod metadata       │  │  │  │ COMMUNICATES_WITH edges            │ │   │
│  │  │ • labels, annotations     │  │  │  │ • protocol, port, request_count   │ │   │
│  │  └───────────────────────────┘  │  │  │ • first_seen, last_seen            │ │   │
│  └─────────────────────────────────┘  │  └────────────────────────────────────┘ │   │
│                                       └────────────────────────────────────────┘   │
│                                                         │                            │
│                                                         ▼                            │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                             graph-query                                       │   │
│  │  graph_query_engine.py                                                        │   │
│  │  • get_dependency_graph(): Cypher query for nodes and edges                  │   │
│  │  • Return: source_*, destination_* including labels, owner, metadata         │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                               backend                                         │   │
│  │  routers/communications.py                                                    │   │
│  │  • DependencyNode model: id, name, kind, namespace, labels, owner_*, etc.    │   │
│  │  • get_dependency_graph(): Parse JSON labels, map all fields                 │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                                │
│                                     ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                               frontend                                        │   │
│  │  LiveMap.tsx                                                                  │   │
│  │  • Cytoscape.js graph visualization                                          │   │
│  │  • Node detail drawer: Shows all metadata                                    │   │
│  │  • Label filter: Full-text search on labels                                  │   │
│  │  • Namespace/Pod filters                                                      │   │
│  │  • External node handling with 🌐 icon                                       │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Details

### 1. eBPF Event Capture (Inspektor Gadget)

```
trace_tcp events produce:
{
  "type": "connect" | "accept" | "close",
  "k8s": {
    "namespace": "flowfish",
    "podName": "backend-xxx",
    "containerName": "backend"
  },
  "src": { "addr": "10.128.1.1" },
  "dst": { "addr": "10.128.2.2" },
  "sport": 54321,
  "dport": 5432
}
```

### 2. Event Direction Handling

**Critical: Accept vs Connect**

| Event Type | k8s Context | Direction | src → dst |
|------------|-------------|-----------|-----------|
| `connect`  | SOURCE      | outbound  | pod → external |
| `accept`   | DESTINATION | inbound   | external → pod |

For `accept` events, the code swaps src/dst to represent the logical flow:
```python
# kubectl_gadget_client.py
if event_type == "accept":
    # Swap to represent: external_client → our_pod
    normalized["src_ip"] = remote_ip
    normalized["dst_ip"] = pod_ip
    normalized["dst_namespace"] = k8s.namespace
    normalized["dst_pod"] = k8s.pod
    normalized["src_namespace"] = ""  # Will be enriched
    normalized["src_pod"] = ""        # Will be enriched
    normalized["direction"] = "inbound"
```

### 3. Metadata Enrichment (PodDiscovery)

PodDiscovery maintains an IP → Pod metadata cache:

```python
@dataclass
class PodInfo:
    name: str              # "backend-5f8f69d45c-7j28g"
    namespace: str         # "flowfish"
    ip: str               # "10.128.22.50"
    node: str             # "worker1.internal.example.local"
    labels: Dict[str, str] # {"app": "haproxy-openmanager", "component": "backend"}
    annotations: Dict[str, str]  # {"git-repo": "https://github.com/org/backend", ...}
    owner_kind: str       # "ReplicaSet"
    owner_name: str       # "backend-5f8f69d45c"
    uid: str              # "abc123-def456"
    host_ip: str          # "192.168.1.10"
    container_name: str   # "backend"
    container_image: str  # "registry/backend:v1.0"
    service_account: str  # "default"
    phase: str            # "Running"
```

### 4. Neo4j Node Properties

All metadata is stored on Neo4j nodes:

```cypher
(:Workload {
  id: "cluster1/flowfish/backend-xxx",
  name: "backend-5f8f69d45c-7j28g",
  namespace: "flowfish",
  kind: "Pod",
  labels: '{"app":"haproxy-openmanager","component":"backend"}',
  annotations: '{"git-repo":"https://github.com/org/backend","team":"payments"}',
  owner_kind: "ReplicaSet",
  owner_name: "backend-5f8f69d45c",
  ip: "10.128.22.50",
  pod_uid: "abc123",
  host_ip: "192.168.1.10",
  container: "backend",
  image: "registry/backend:v1.0",
  service_account: "default",
  phase: "Running"
})
```

### 5. Frontend Display

Node detail drawer shows:
- **Pod Name**: backend-5f8f69d45c-7j28g
- **Namespace**: flowfish
- **Owner**: Deployment/backend (resolved from ReplicaSet)
- **Node**: worker1.internal.example.local
- **Labels**: app=haproxy-openmanager, component=backend
- **Annotations**: git-repo=https://github.com/org/backend, team=payments (categorized, formatted JSON values)
- **Container**: backend
- **Image**: registry/backend:v1.0
- **Phase**: Running

## External Traffic Handling

External traffic (from outside the cluster) appears when:
1. A pod receives connections from external IPs (`accept` events)
2. The source IP is not in the PodDiscovery cache

In this case:
- Source shows as IP address with 🌐 icon
- Namespace shows as "external"
- No additional metadata available

## Deployment/StatefulSet Annotation Merge

Pods often lack annotations that are set on their owning Deployment or StatefulSet (e.g., `git-repo`, `team`, pipeline metadata). Flowfish automatically merges owner-level annotations into pod metadata during ingestion.

### How It Works

1. After discovering pods (via gRPC `ListPods` or `kubectl get pods`), the Ingestion Service calls `_enrich_with_owner_annotations()`
2. It fetches Deployment and StatefulSet annotations via gRPC `ListDeployments`/`ListStatefulSets` (or kubectl as fallback)
3. For each pod, it resolves the owning Deployment/StatefulSet name using:
   - Pod labels (`app`, `app.kubernetes.io/name`) for direct match
   - Stripping `pod-template-hash` from ReplicaSet names for ReplicaSet-owned pods
   - Direct `owner_name` for StatefulSets and DaemonSets
4. Owner annotations are merged into pod annotations: `{**owner_annotations, **pod_annotations}`
   - **Pod annotations always take priority** in case of key conflicts

### Annotation Filtering

Both pod-level and owner-level annotations are filtered before storage:
- **Excluded prefixes**: `kubectl.kubernetes.io/`, `kubernetes.io/`, `openshift.io/`
- **Excluded values**: Annotations with values exceeding 500 characters
- This keeps the data focused on custom, application-relevant annotations

### Proto Definition

The `DeploymentInfo` and `StatefulSetInfo` protobuf messages include an `annotations` field:
```protobuf
message DeploymentInfo {
    // ... other fields ...
    map<string, string> annotations = 11;
}
```

## Troubleshooting

### Missing Metadata
If metadata is missing for some nodes:
1. Check if the node was created via edge upsert (destination-only)
2. Verify PodDiscovery is running and refreshing
3. Check Neo4j node properties directly

### Missing Inbound Traffic
If incoming connections are not visible:
1. Verify `accept` events are being captured by trace_tcp
2. Check that direction handling is correctly swapping src/dst
3. Look for "direction": "inbound" in event data

### Labels Empty
If labels show as `{}`:
1. Check if labels are being passed in edge cache
2. Verify graph_client.py is setting labels with CASE WHEN
3. Ensure PodDiscovery extracted labels correctly

### Annotations Empty
If annotations show as `{}`:
1. Verify the gRPC discovery path includes annotations in `PodInfo` proto message
2. Check that `_filter_annotations()` in grpc_server.py is not filtering out the target annotations
3. For deployment-level annotations, verify `_enrich_with_owner_annotations()` is running and the owner resolution logic matches the pod's Deployment/StatefulSet
4. Internal annotations (`kubectl.kubernetes.io/`, `kubernetes.io/`, `openshift.io/`) are intentionally filtered — only custom annotations are stored

