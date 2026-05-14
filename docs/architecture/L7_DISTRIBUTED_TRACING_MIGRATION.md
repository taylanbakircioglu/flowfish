# L7 Distributed Tracing — Migration Runbook

This document covers rolling out W3C distributed tracing on top of the
existing L7 (Beyla) pipeline. The feature is gated by the
`L7_TRACING_ENABLED` environment variable on the writer services and by
`ebpf.track_request_headers: true` on each Beyla DaemonSet.

## What changed

- **Beyla** runs in passive mode: it reads existing `traceparent` HTTP
  headers off the wire (no header injection, no extra kernel privileges).
  Requires Beyla 3.x.
- **flowfish-l7-collector** extracts `trace_id`, `span_id`,
  `parent_span_id`, `span_name`, `span_kind` from each OTLP span and adds
  them to `data` so RabbitMQ messages carry trace context downstream.
- **timeseries-writer** writes those columns into
  `l7_http_flows`, `l7_grpc_flows`, `l7_dns_flows`. INSERT path falls back
  to legacy column list when the trace columns have not been migrated yet
  (handles deploy-order race).
- **graph-writer** stamps `last_trace_id`, `last_span_id`, `trace_count` on
  `L7_COMMUNICATES_WITH` relationships and runs a periodic SAME_WORKLOAD
  matcher (3 layers: trace_id, exact_name, hostname) that bridges
  `external` placeholder nodes to their cluster-resolved counterparts.
  Multi-cluster sub-analyses (analysis_id format `<parent>-<cluster_id>`)
  are matched via STARTS WITH on the parent prefix so cross-cluster bridges
  are detected even when each side carries a different sub-analysis ID.
- **l7-ingestion-service** is tracing-agnostic: it forwards spans regardless
  of the trace flag. (An earlier revision auto-injected `external` into
  `namespace_allow` when tracing was enabled; that was reverted because
  `_passes_namespace` already accepts source-side matches and the auto-inject
  over-included unrelated workloads whose destinations resolved to the
  synthetic `external` namespace.)
- **timeseries-query / backend / frontend** expose `/l7/traces/{trace_id}`
  and `/l7/traces` (recent traces), with a Trace Explorer page and a
  TraceWaterfall component reused from the Service Map's edge drawer.
- **Service Map** renders SAME_WORKLOAD bridges as dashed gray edges
  (no arrow, no label) so cross-cluster identity links are visible without
  competing visually with real traffic edges. Cluster name is displayed as
  a purple badge on each non-external workload node so multi-cluster maps
  visually distinguish identical workload names across clusters.

## Prerequisite check (per cluster)

```bash
oc get daemonset/flowfish-beyla -n <ns> -o jsonpath='{.spec.template.spec.containers[0].image}'
# Expect grafana/beyla:3.x or newer (track_request_headers needs >= 3.0)

oc get configmap/beyla-config -n <ns> -o yaml | grep -A2 ebpf:
# Expect ebpf.track_request_headers: true
```

If `ebpf:` block is missing, edit the ConfigMap or re-apply
`deployment/kubernetes-manifests/20-beyla.yaml`. **You must restart the
DaemonSet pods after editing the ConfigMap** — Beyla does not hot-reload:

```bash
oc rollout restart daemonset/flowfish-beyla -n <ns>
oc rollout status  daemonset/flowfish-beyla -n <ns>
```

During the restart Beyla Health on the cluster overview may appear
"degraded" briefly; this is expected.

## ClickHouse schema migration

The migration is idempotent (`ADD COLUMN IF NOT EXISTS`) and is applied by
the standard migration job (`deployment/kubernetes-manifests/03-migrations-job.yaml`)
on next deploy. To apply ad-hoc:

```sql
ALTER TABLE flowfish.l7_http_flows ADD COLUMN IF NOT EXISTS trace_id String DEFAULT '';
ALTER TABLE flowfish.l7_http_flows ADD COLUMN IF NOT EXISTS span_id String DEFAULT '';
ALTER TABLE flowfish.l7_http_flows ADD COLUMN IF NOT EXISTS parent_span_id String DEFAULT '';
ALTER TABLE flowfish.l7_http_flows ADD COLUMN IF NOT EXISTS span_name String DEFAULT '';
ALTER TABLE flowfish.l7_http_flows ADD COLUMN IF NOT EXISTS span_kind UInt8 DEFAULT 0;
ALTER TABLE flowfish.l7_http_flows ADD INDEX IF NOT EXISTS idx_trace_id trace_id TYPE bloom_filter GRANULARITY 4;
-- Repeat for l7_grpc_flows and l7_dns_flows.
```

## Neo4j schema migration

Two new indexes (idempotent, picked up by `08-neo4j-init.yaml`):

```cypher
CREATE INDEX l7_workload_composite IF NOT EXISTS
  FOR (w:L7Workload) ON (w.analysis_id, w.cluster, w.name);

CREATE INDEX l7_comm_trace IF NOT EXISTS
  FOR ()-[r:L7_COMMUNICATES_WITH]-() ON (r.last_trace_id);
```

## Deploy order

1. **Migrations** — apply ClickHouse + Neo4j changes first.
2. **Writers** — deploy `timeseries-writer` and `graph-writer` with
   `L7_TRACING_ENABLED=false` (default in production manifests). The
   writers tolerate missing columns by falling back to legacy INSERT.
3. **Beyla** — apply ConfigMap + DaemonSet restart cluster-by-cluster.
4. **Enable tracing** — flip `L7_TRACING_ENABLED=true` on the writers and
   roll restart, once the desired clusters have the new Beyla config.
5. **Frontend** is feature-flag-free: it just shows trace UI when the API
   returns trace data.

### Production activation checklist (after this commit)

This repo now ships with `L7_TRACING_ENABLED=true` on the three production
manifests (`11-timeseries-writer.yaml`, `15-graph-writer.yaml`,
`22-l7-ingestion-service.yaml`). Beyla DaemonSets must already have
`ebpf.track_request_headers: true` **before** the writers are rolled out,
otherwise the writers will turn the trace pipeline on but receive empty
`trace_id` columns (no breakage, just no data).

**Order on a live cluster:**

1. **Confirm Beyla per cluster** — every collected cluster must have
   `track_request_headers: true` *and* a Beyla DaemonSet rollout already
   completed:

   ```bash
   for ns in <hub-ns> <each-collected-cluster-ns>; do
     echo "=== $ns ===";
     oc -n $ns get cm beyla-config -o jsonpath='{.data.beyla-config\.yml}' \
       | grep -E 'track_request_headers|inject|request_inject'
     oc -n $ns rollout status daemonset/beyla --timeout=60s
   done
   ```

   Expect exactly one match: `track_request_headers: true`. Any
   `request_inject` / `routes:` line means somebody turned active mode
   on — back it out before continuing (Flowfish does **not** rely on
   active injection and we do not want production payloads rewritten).

2. **Apply migrations** — the SQL/Cypher inside is `IF NOT EXISTS` and
   safe to re-run. Note that a `Job` resource itself has an immutable
   spec, so if a previous run already exists you must delete the Job
   object before re-applying (the data inside ClickHouse / Neo4j is
   untouched by this delete):

   ```bash
   # ClickHouse trace columns (idempotent at the SQL level)
   oc -n <hub-ns> delete job migrations --ignore-not-found
   oc apply -f deployment/kubernetes-manifests/03-migrations-job.yaml
   oc -n <hub-ns> wait --for=condition=complete job/migrations --timeout=120s

   # Neo4j trace indexes (init resource is also re-runnable)
   oc apply -f deployment/kubernetes-manifests/08-neo4j-init.yaml
   ```

3. **Roll the three writers** (the order is independent, but rolling them
   together gives you a clean cutover):

   ```bash
   oc -n <hub-ns> rollout restart deploy/timeseries-writer
   oc -n <hub-ns> rollout restart deploy/graph-writer
   oc -n <hub-ns> rollout restart deploy/l7-ingestion-service
   oc -n <hub-ns> rollout status  deploy/timeseries-writer
   oc -n <hub-ns> rollout status  deploy/graph-writer
   oc -n <hub-ns> rollout status  deploy/l7-ingestion-service
   ```

4. **Smoke test** — start a fresh L4+L7 analysis from the UI, wait at
   least one full flush cycle (~10s), then run the three checks below.
   ClickHouse and Neo4j run as StatefulSets, so we resolve the pod by
   label rather than by `deploy/...` (which would not match):

   ```bash
   # 4a. ClickHouse: confirm trace_id is populated
   CH_POD=$(oc -n <hub-ns> get pod -l app=clickhouse -o name | head -1)
   oc -n <hub-ns> exec "$CH_POD" -- clickhouse-client -q \
     "SELECT count() AS rows, countIf(trace_id <> '') AS with_trace
        FROM flowfish.l7_http_flows
        WHERE timestamp > now() - INTERVAL 10 MINUTE"

   # 4b. Neo4j: confirm trace_count rolling up.
   # NOTE: pulling the password from the same secret graph-writer uses
   # avoids quoting / shell-expansion issues with special characters.
   NEO4J_POD=$(oc -n <hub-ns> get pod -l app=neo4j -o name | head -1)
   NEO4J_PW=$(oc -n <hub-ns> get secret flowfish-secrets \
     -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d)
   oc -n <hub-ns> exec "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PW" \
     "MATCH ()-[r:L7_COMMUNICATES_WITH]-() WHERE r.trace_count > 0
        RETURN count(r) AS edges_with_trace, sum(r.trace_count) AS total_traces"

   # 4c. Backend: a trace_id should appear in /l7/traces
   curl -s -H "Authorization: Bearer $TOKEN" \
     "https://flowfish.<host>/api/l7/traces?analysis_id=<id>&limit=5" | jq .
   ```

   If 4a returns `with_trace > 0` you are healthy. If `with_trace == 0`
   for more than a few minutes, see *Troubleshooting* below.

### Why this is safe to flip on production

The activation only changes Flowfish-internal pipeline behaviour. Nothing
in this commit changes what travels on the wire between your services:

| Concern | Effect |
|---|---|
| Latency on monitored services | None. Beyla reads `traceparent` from observed syscalls; it does not run in the request path. |
| Modification of HTTP/gRPC traffic | None. The Beyla ConfigMap explicitly excludes any `inject` / `routes` block. The writers only persist what Beyla reports. |
| Schema risk | Migrations are `IF NOT EXISTS` and `ADD COLUMN`-only. Existing readers ignore unknown columns. |
| Existing analyses | Backwards compatible. Old `L7_COMMUNICATES_WITH` edges are kept; `trace_count` defaults to 0 and only grows when new spans arrive carrying `trace_id`. |
| Rollback | Set `L7_TRACING_ENABLED=false` and roll the three writers — pipeline goes back to the pre-tracing path immediately. ClickHouse columns and Neo4j indexes stay. |

### Troubleshooting after activation

- **`l7_http_flows.trace_id` is always empty** → Beyla is running but
  upstream services are not propagating `traceparent`. Spot-check with:

  ```bash
  oc -n <ns> logs -l app=beyla --tail=200 | grep -i traceparent
  ```

  Services emitting OTel SDK or Spring Cloud Sleuth automatically
  propagate the header; legacy services that strip headers at a proxy
  will need that proxy reconfigured. This is *expected* — Beyla in
  passive mode cannot create trace context, only observe it.

- **`/l7/traces` is empty even though ClickHouse has trace_id rows** →
  the analysis_id filter on the endpoint is strict. Confirm you are
  querying the right analysis_id (or omit the filter to see global
  recent traces).

- **Trace Explorer "No traces found"** for a known-good trace_id →
  open the trace_id directly via the URL: `/trace-explorer?trace_id=...`.
  This bypasses the analysis filter and is the supported deep-link.

- **`graph-writer` log spam about `SAME_WORKLOAD migration timed out`** →
  This is the cross-cluster bridge maintenance loop. The Cypher uses
  composite indexes added by `08-neo4j-init.yaml`; if you see this,
  re-apply that manifest and the periodic flush picks the index up
  on the next iteration.

- **"Some Gadgets Failed to Start" warning on freshly (re)started
  clusters** → On a freshly rebooted IG DaemonSet the OCI artifact
  store and gRPC dial pool have to warm up; the first analysis after
  the restart can lose the race against the 8s startup wait for 1-3
  gadgets (commonly `trace_tcpretrans`, `trace_capabilities`,
  `trace_sni`). `ingestion-service` now auto-retries each failed
  gadget once after a short warm-path wait, so the operator should
  not see the warning anymore. If the warning still surfaces, either:
  (a) the retry budget (env `GADGET_STARTUP_RETRY_ATTEMPTS`, default 1)
      was exhausted — bump to 2 and roll the deployment, or
  (b) the failure is genuine (image missing, DS not ready) — see
      *(2)* and *(3)* of the "no stderr output" error message for
      diagnostics.

  ```bash
  # Inspect the retry path inline
  oc -n <hub-ns> logs deploy/ingestion-service --since=5m \
    | grep -E "Retrying transient|Gadget retry started|Gadget retry failed"
  ```

- **eBPF ring buffer sizing reference (IG ConfigMap
  `events-buffer-length`)** → Sized by pods/node ratio. Each tier
  carries **2x headroom** over the strictly-required size so a
  multi-gadget burst (11 gadgets × N pods) does not overflow the IG
  worker's perf-event rings. Tier table is identical in the install
  script (UI download), the upgrade script, and
  `09-inspektor-gadget-config.yaml`:

  | pods/node | `events-buffer-length` |
  |---|---|
  | ≤15      | 262144   (256K)        |
  | 16–40    | 524288   (512K)        |
  | 41–80    | 2097152  (2M)          |
  | 81–150   | 2097152  (2M)          |
  | 151–300  | 4194304  (4M)          |
  | 300+     | 4194304  (4M, kernel cap) |

  Floor by total pods: 500+ → min 1M, 1000+ → min 2M, 2000+ → min 4M.
  4M is the cap because Linux's `kernel.perf_event_max_sample_rate`
  and `kernel.perf_cpu_time_max_percent` start gating around there;
  going higher gives diminishing returns and increases drop-detection
  latency without reducing actual losses.

  To re-apply on an existing cluster (without reinstalling IG), use
  the in-place patch:

  ```bash
  NS=internal-flowfish
  CM=inspektor-gadget-config
  NEW_BUF=4194304   # pick your tier from the table above

  oc -n $NS get configmap $CM -o yaml \
    | sed "s/events-buffer-length:.*/events-buffer-length: ${NEW_BUF}/" \
    | oc apply -f -

  oc -n $NS rollout restart daemonset/inspektor-gadget
  oc -n $NS rollout status daemonset/inspektor-gadget --timeout=180s
  ```

- **IG DaemonSet container is SIGKILL'd (exit 137) during analysis
  startup; one or more gadgets exit with `returncode=-6` (SIGABRT)
  and `stderr=""`** → This is the IG overload pattern, not a
  cold-start race. Symptoms in the IG container's previous-run logs:

  ```
  level=warning msg="getting lost samples: %!w(*fmt.wrapError=&{lookup: bad file descriptor {N}})"
  level=warning msg="reading event: lost 295205 samples"
  ```

  followed by container `lastState.terminated.exitCode: 137` and a
  ContainerRuntimeRestart. The cause is launching all ~11 gadgets in
  a 2-second window: per-program perf-event ring buffers overflow
  faster than the IG worker can drain them, internal file
  descriptors get corrupted, the kubelet liveness probe fails, and
  the kubelet SIGKILLs the container. Whichever gadget was in the
  middle of its gRPC handshake at that moment exits with SIGABRT.

  Mitigation already wired in `ingestion-service`. The defaults below
  reflect worst-case observations on busy production clusters where the
  kprobe-heavy gadgets (trace_tcp, trace_open, trace_capabilities,
  trace_bind) were failing in a 4-gadget burst after every
  ingestion-service rolling update because the IG worker had not yet
  finished registering kernel kprobe attach points.

  | Env var | Default | Purpose |
  |---|---|---|
  | `GADGET_STARTUP_WAIT_SECONDS` | `8.0` | First-pass cold-start window |
  | `GADGET_STARTUP_STAGGER_SECONDS` | `1.0` | Spacing between gadget launches; raised from 0.5s to give the kprobe register path room on busy clusters |
  | `GADGET_STARTUP_RETRY_ATTEMPTS` | `2` | Transparent retries for transient failures; raised from 1 because heavy-load clusters frequently need a second retry once the IG pod has fully restarted post-SIGKILL |
  | `GADGET_RETRY_PRE_WAIT_SECONDS` | `12.0` | Base wait before retry attempt 1 |
  | `GADGET_RETRY_BACKOFF_MULTIPLIER` | `1.5` | Each retry past the first multiplies the pre-wait by this factor (12s → 18s → 27s) so back-to-back retries don't all collide with the same hot moment of the IG restart cycle |

  Total tolerance with defaults: a single full-overload analysis can
  spend up to **8 + 12 + 8 + 18 + 8 ≈ 54 seconds** waiting for the IG
  worker to settle before declaring a gadget genuinely broken. Bump
  `GADGET_RETRY_BACKOFF_MULTIPLIER` and/or `GADGET_STARTUP_RETRY_ATTEMPTS`
  if your registry is far/slow or if `oc -n <ns> get pod -l k8s-app=gadget`
  shows IG pods routinely taking longer than 30s to become Ready.

  Diagnostic recipe — confirm whether IG was the casualty:

  ```bash
  NS=internal-flowfish

  # IG pod restart counts and last-known exit code
  oc -n $NS get pod -l k8s-app=gadget -o custom-columns=\
    NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,\
    LAST_EXIT:.status.containerStatuses[0].lastState.terminated.exitCode

  # The "lost samples / bad fd" pattern from the previous run
  for p in $(oc -n $NS get pod -l k8s-app=gadget -o jsonpath='{.items[*].metadata.name}'); do
    echo "--- $p ---"
    oc -n $NS logs $p --previous --tail=60 2>/dev/null \
      | grep -E "lost samples|bad file descriptor" | tail -5
  done
  ```

### Stale RabbitMQ queue compatibility (one-time)

`timeseries-writer` and `graph-writer` declare the L7 queues with
`x-dead-letter-exchange: flowfish.l7.dlx`. Clusters that were originally
deployed before this argument existed will hit a
`PRECONDITION_FAILED — inequivalent arg 'x-dead-letter-exchange'` error
on first start of the new writer because RabbitMQ rejects re-declarations
that change queue arguments. The fix is a one-time queue purge:

```bash
oc exec -n <ns> $(oc get pod -n <ns> -l app=rabbitmq -o name | head -1) -- \
  rabbitmqctl delete_queue flowfish.queue.l7_http_flows.timeseries
oc exec -n <ns> $(oc get pod -n <ns> -l app=rabbitmq -o name | head -1) -- \
  rabbitmqctl delete_queue flowfish.queue.l7_grpc_flows.timeseries
oc exec -n <ns> $(oc get pod -n <ns> -l app=rabbitmq -o name | head -1) -- \
  rabbitmqctl delete_queue flowfish.queue.l7_dns_flows.timeseries

oc rollout restart deploy/timeseries-writer -n <ns>
```

The writers re-declare the queues with the DLX argument on next start.
No data loss — these queues are buffer-only and the upstream exchanges
continue to publish during the brief recreation window.

## Rollback

- **Code rollback**: revert the writer image; the trace columns remain in
  ClickHouse but are simply ignored by the legacy INSERT path.
- **Disable tracing without rollback**: set `L7_TRACING_ENABLED=false` and
  redeploy. Existing trace data is retained; no new trace data will be
  written until the flag is re-enabled.
- **Beyla rollback**: remove the `ebpf:` block from `beyla-config` and
  restart the DaemonSet. New spans will lose trace context but everything
  else continues to work.

## Sampling and filter caveats

Trace completeness depends on:

- **Sampling**: random sampling at the ingestion service can drop child
  spans, leading to "tek span" or "orphan span" warnings in the
  TraceWaterfall view.
- **HTTP filters**: `exclude_paths`, `path_pattern`, `status_codes`, and
  `namespace_allow` can drop spans within an otherwise complete trace.
- **External namespace**: calls from a workload in the user's allow-list to
  an unresolved external host (which Beyla labels `namespace="external"`)
  pass through `_passes_namespace` via the source-side match — there is no
  need to add `external` to the allow-list and doing so would over-include
  unrelated workloads whose destinations also resolve to `external`.
- **DNS spans**: DNS protocol cannot carry traceparent headers; DNS rows
  carry trace context only when present in the OTLP span itself, and the
  trace API endpoints exclude DNS from the unified view.

## Naming conflict (informational)

The codebase has two unrelated `trace_id` concepts:

- **Inspector Gadget L4 `trace_id`** (in `services/ingestion-service/app/trace_manager.py`):
  a session ID, not a W3C trace ID.
- **L7 OTLP/W3C `trace_id`** (this feature): a 16-byte hex string from
  `traceparent` headers.

The two never overlap in storage — L4 uses `network_flows`/`tcp_connections`
tables; L7 uses `l7_*_flows` tables.

## Loopback / self-monitoring filter (defense in depth)

### Symptom

Service Map shows an edge such as

```text
loopback/localhost → <flowfish-namespace>/<workload>
   GRPC /api.BuiltInGadgetManager/GetInfo
   req=14   avg_latency=246_920 ms
```

and aggregate gRPC latency on `/l7/communications/stats` reports values in
the seconds-to-minutes range even when real applications are sub-millisecond.

### Root cause

Beyla, when listening on every node, observes the long-running gadget gRPC
streams that Flowfish's own pods (`kubectl-gadget` →
Inspektor-Gadget worker) keep open during an analysis. Because the connection
stays open for the whole analysis window, Beyla emits each stream as a
single "request" whose duration equals the connection lifetime — minutes
rather than milliseconds.

The Flowfish L7 collector resolves these spans to the synthetic
namespace `loopback` (because Beyla reports `127.0.0.1` / `::1` as both
ends), and they then poison aggregate latency in the L7 service map and
trace stats.

### Mitigations (applied in three layers)

1. **Beyla discovery exclude (root cause)** — `deployment/kubernetes-manifests/20-beyla.yaml`
   and the install script generated by `backend/routers/clusters.py`
   exclude the Flowfish namespace from Beyla's discovery scope, so those
   spans never reach the collector. The list also includes a literal
   `gadget` entry: this is the Inspektor Gadget DaemonSet namespace for
   clusters that run IG separately. In the default Flowfish topology IG
   is co-located with Flowfish (`gadget-namespace: "<flowfish-ns>"` in
   `09-inspektor-gadget-config.yaml`), so the Flowfish-namespace exclude
   already covers it; the `gadget` entry is defensive coverage for
   operator-customised installs and is harmless when unused.

   Operators upgrading existing clusters must regenerate the Beyla
   ConfigMap and roll the DaemonSet. The ConfigMap stores the entire
   Beyla YAML as a single string in `data.beyla-config.yml`, so a JSON
   Patch list-append cannot be used — use one of the patterns below:

   ```bash
   # OPTION A (recommended): regenerate via the UI's Beyla install script
   #   1. Open Cluster Management → choose the cluster → "Reinstall Beyla"
   #   2. Save the generated bash script and run it (it re-applies the
   #      ConfigMap with the new exclude list and rolls the DaemonSet).

   # OPTION B: edit the ConfigMap in place via kubectl-edit
   oc -n <flowfish-ns> edit configmap beyla-config
   #   add the following two lines under `discovery.exclude_instrument:`
   #     - k8s_namespace: "<flowfish-ns>"
   #     - k8s_namespace: "gadget"
   oc -n <flowfish-ns> rollout restart daemonset/beyla

   # OPTION C: scripted (idempotent) — fetches, patches, re-applies
   oc -n <flowfish-ns> get configmap beyla-config -o yaml \
     | python3 -c '
   import sys, yaml
   doc = yaml.safe_load(sys.stdin)
   inner = yaml.safe_load(doc["data"]["beyla-config.yml"])
   excl = inner["discovery"]["exclude_instrument"]
   wanted = [{"k8s_namespace": "<flowfish-ns>"}, {"k8s_namespace": "gadget"}]
   for w in wanted:
       if w not in excl:
           excl.append(w)
   doc["data"]["beyla-config.yml"] = yaml.safe_dump(inner, sort_keys=False)
   yaml.safe_dump(doc, sys.stdout)
   ' | oc apply -f -
   oc -n <flowfish-ns> rollout restart daemonset/beyla
   ```

2. **Collector drop (defense)** — `services/flowfish-l7-collector/app/event_transformer.py`
   drops any span whose source or destination resolves to the synthetic
   `loopback` namespace before it is queued to RabbitMQ. This protects
   clusters that still run an older Beyla ConfigMap.

3. **Writer drop (final defense)** — `services/timeseries-writer/app/clickhouse_client.py`
   re-applies the same filter at the ClickHouse insertion path, covering
   stale collectors or operator-applied event sources.

### Verifying the mitigation

After re-rolling Beyla, start a new analysis and check:

```bash
# Should be 0 — no loopback edges in Service Map
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://<flowfish>/api/v1/l7/communications?analysis_id=<id>&limit=200" \
  | jq '[.data[] | select(.source_namespace=="loopback" or .destination_namespace=="loopback")] | length'

# Aggregate gRPC latency should now be sub-millisecond for real apps
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://<flowfish>/api/v1/l7/events/stats?analysis_id=<id>" \
  | jq '.grpc.avg_latency_ms'
```

### Cleaning historic loopback rows (optional)

The three filter layers above only protect *new* spans. Analyses that ran
before the fix retain their `loopback` rows in ClickHouse, so the Service
Map and Trace Explorer for those analyses still show the noise. To prune
the historic data run a `DELETE` mutation against each L7 table — the
operation is asynchronous so you may have to wait a few seconds before
the rows disappear from queries:

```sql
-- run inside the flowfish ClickHouse cluster (clickhouse-client / DBeaver)
ALTER TABLE flowfish.l7_http_flows
  DELETE WHERE src_namespace = 'loopback' OR dst_namespace = 'loopback';

ALTER TABLE flowfish.l7_grpc_flows
  DELETE WHERE src_namespace = 'loopback' OR dst_namespace = 'loopback';

ALTER TABLE flowfish.l7_dns_flows
  DELETE WHERE src_namespace = 'loopback' OR dst_namespace = 'loopback';

-- (optional) wait for mutations to finish before re-running the UI:
SELECT table, mutation_id, is_done, latest_failed_part
FROM   system.mutations
WHERE  database = 'flowfish' AND is_done = 0;
```

Skipping the cleanup is safe — the rows still exist but the filter
ensures no further loopback rows accumulate; you simply continue to see
the historical noise in the affected analyses' Service Map.

### Frontend cleanup

The Service Map (`frontend/src/pages/ServiceMap.tsx`) tags each node with
its namespace category — `application`, `system`, `infrastructure`
(`cluster-infra`, `sdn-infrastructure`) or `unresolved` (`unknown`,
`loopback`). The legacy "Dim system namespaces" toggle is now labelled
"Dim non-application namespaces" and de-emphasizes all three secondary
categories at once via `isSecondaryNamespace` in
`utils/serviceMapConstants.ts`.

---

## Enterprise APM-Style L7 Refactor (Phase 1–4) — Rollout Runbook

This section covers the rollout of the APM-style L7 refactor that builds
on top of the W3C tracing pipeline above. Four phases were delivered in
order; each can be deployed independently and is gated either by a
feature flag or by the presence of its ClickHouse migration.

### Phases at a glance

| Phase | What ships | Feature flag / Gate |
|-------|------------|---------------------|
| 1A | Trace Explorer redesign + 7 new filter params on `/l7/traces` (src/dst workload, operation, min latency, error_only, time range) | None — backward-compat additive |
| 1B | TraceWaterfall: service-colored bars, click-to-inspect span detail panel, JSON tree, tabbed layout (Spans / Errors / Logs / Related) | None |
| 2  | APM Services List + Service Detail with RED metrics (rate, errors, p50/p95/p99) | `clickhouse_005_add_apm_red_mvs.sql` |
| 3B | Related Traces tab (same-edge, same-pod) | `clickhouse_006_add_apm_indexes.sql` |
| 4  | PID-temporal `virtual_trace_id` correlation for un-instrumented services | `L7_PID_CORRELATION_ENABLED=true` + `clickhouse_007_add_l7_pid.sql` |

### Required ClickHouse migrations (manual)

There is no ClickHouse migration runner — `03-migrations-job.yaml`
handles only PostgreSQL. ClickHouse migrations under `schemas/migrations/`
are applied manually. Apply them in numeric order:

```bash
oc rsh -n <flowfish-ns> $(oc get pod -n <flowfish-ns> -l app=clickhouse -o name | head -1)

# Phase 2 — RED metrics MVs (5 MVs total: HTTP svc/ops, gRPC svc/ops, DNS svc)
clickhouse-client --user="$CLICKHOUSE_USER" --password="$CLICKHOUSE_PASSWORD" \
  --database=flowfish --multiquery < /tmp/clickhouse_005_add_apm_red_mvs.sql

# Phase 3B — bloom filter indexes for same-pod related-trace queries
clickhouse-client --user="$CLICKHOUSE_USER" --password="$CLICKHOUSE_PASSWORD" \
  --database=flowfish --multiquery < /tmp/clickhouse_006_add_apm_indexes.sql

# Phase 4 — pid/ppid/container_id/virtual_trace_id columns on HTTP+gRPC
clickhouse-client --user="$CLICKHOUSE_USER" --password="$CLICKHOUSE_PASSWORD" \
  --database=flowfish --multiquery < /tmp/clickhouse_007_add_l7_pid.sql
```

Each migration is idempotent (`IF NOT EXISTS` guards) and includes
verification queries inline. Until a migration is applied, the related
backend code automatically falls back to the previous behaviour:

- timeseries-writer detects `Unknown column` errors and disables the new
  INSERT path for that table until restart.
- timeseries-query `get_trace_spans`, `get_related_traces` catch the
  same error and re-issue the legacy trace_id-only query.

**Backfill semantics — important.** ClickHouse Materialized Views
populate from NEW inserts only. Migration 005's MVs therefore start
empty and fill up at most one 5-minute bucket after rollout. Implications:

- A new analysis started AFTER migration 005 → APM Services list
  populates within 5 minutes (one MV bucket cycle).
- An analysis that was STOPPED before migration 005 → APM Services list
  stays empty for that analysis. Trace Explorer (which reads the raw
  `l7_*_flows` tables, not the MVs) continues to work for those
  historical traces.
- Optional one-time backfill (operator decides per cluster — heavy on
  large historical tables, can saturate ClickHouse for tens of minutes):

  ```sql
  INSERT INTO flowfish.l7_http_red_svc_5min
  SELECT
      toStartOfFiveMinutes(timestamp) AS timestamp_5min,
      cluster_id, analysis_id, src_workload, dst_workload,
      src_namespace, dst_namespace,
      sumState(toUInt64(1)),
      sumState(toUInt64(if(http_status_code >= 400, 1, 0))),
      quantileTDigestState(latency_ms)
  FROM flowfish.l7_http_flows
  WHERE timestamp < now() - INTERVAL 5 MINUTE
  GROUP BY timestamp_5min, cluster_id, analysis_id,
           src_workload, dst_workload, src_namespace, dst_namespace;
  ```

  Repeat for the other 4 MVs (HTTP ops, gRPC svc/ops, DNS svc) using
  the same SELECT shape in `clickhouse_005_add_apm_red_mvs.sql`. Skip
  this step on production rollout — only run it if operators ask
  "why is APM data missing for analysis #N?".

### Phase 4 pre-flight checks

Phase 4 turns un-instrumented services into multi-hop traces by
correlating spans on (cluster, src_pod, container_id, pid, 50ms-window).
**Before flipping the feature flag** confirm:

1. **Beyla version ≥ 3.0** (process attributes were added in 3.x):

   ```bash
   oc -n <flowfish-ns> exec ds/beyla -- /beyla --version 2>&1 \
     | grep -oP '(?<=version )[0-9]+\.[0-9]+\.[0-9]+'
   # < 3.0.0 → Phase 4 unsupported on this cluster
   ```

2. **`process.pid` attribute reaches ClickHouse**. Beyla 3.x emits
   process attributes on trace spans automatically when the DaemonSet
   runs with `hostPID: true` (already set in `20-beyla.yaml`). The
   earlier attempt to opt in via an `attributes.select.process` block
   was removed because (a) it didn't match Beyla's actual config schema
   (`<metric_name>: { include: [...] }`) and (b) was redundant. After
   a brief test analysis, verify with:

   ```bash
   clickhouse-client --query "
     SELECT countIf(pid > 0) AS with_pid, count() AS total
     FROM flowfish.l7_http_flows
     WHERE timestamp >= now() - INTERVAL 5 MINUTE
   "
   # with_pid / total should approach 1.0 once writers are redeployed
   # with l7_pid_correlation_enabled=true
   ```

3. **ClickHouse version ≥ 21** for `AggregatingMergeTree` mutations
   (Phase 2's MVs are dropped/recreated when an analysis is deleted):

   ```bash
   oc -n <flowfish-ns> exec deploy/clickhouse -- clickhouse-server --version
   ```

### Feature flags

| Flag | Service | Default | Purpose |
|------|---------|---------|---------|
| `L7_ENABLED` | timeseries-writer | `false` | Master gate for L7 INSERT paths (Faz 3.1) |
| `L7_TRACING_ENABLED` | timeseries-writer | `false` | Populate `trace_id`/`span_id`/... columns |
| `L7_PID_CORRELATION_ENABLED` | timeseries-writer | `false` | Run PID correlator + populate `virtual_trace_id` |
| `L7_PID_CORRELATION_WINDOW_MS` | timeseries-writer | `50` | Bucketing window for PID correlator |

The flags are independent: enabling `L7_PID_CORRELATION_ENABLED` without
`L7_TRACING_ENABLED` is a no-op (the correlator only attaches a
virtual_trace_id when the trace columns themselves are being populated).

### Production rollout order

The recommended sequence keeps each step independently revertable:

1. **Apply migrations** (`005`, `006`, `007`) in a low-traffic window.
   Migrations are non-blocking but `MATERIALIZE INDEX` runs across
   historical partitions; size accordingly.

2. **Deploy the new code** (timeseries-query, timeseries-writer, backend,
   frontend) without flipping any new flag. Phase 1A/1B/2 work as soon
   as the migrations + code are in place. Phase 3B's APIs become
   available — Trace Waterfall's "Related Traces" tab populates on demand.

3. **Update Beyla ConfigMap** with `attributes.select.process.*` (already
   in `20-beyla.yaml`); restart Beyla DaemonSet:
   ```bash
   oc -n <flowfish-ns> rollout restart daemonset/beyla
   ```

4. **Run a 10-minute test analysis** and verify `pid > 0` ratio
   (pre-flight check #2). If the ratio is < 0.5 the Beyla build is
   probably older than expected; **stop here** and address before
   enabling Phase 4.

5. **Enable Phase 4** by setting `L7_PID_CORRELATION_ENABLED=true` on
   the timeseries-writer deployments and rolling them out:
   ```bash
   oc -n <flowfish-ns> set env deploy/timeseries-writer L7_PID_CORRELATION_ENABLED=true
   oc -n <flowfish-ns> rollout status deploy/timeseries-writer
   ```

### Rollback procedure

Each phase rolls back independently and **without data loss**:

| To roll back | Action |
|--------------|--------|
| Phase 4 only  | Set `L7_PID_CORRELATION_ENABLED=false`, restart writers. New rows have empty `virtual_trace_id`; old rows keep theirs (queries continue to work). |
| Phase 4 + columns | Above + drop columns (irreversible — data loss): `ALTER TABLE l7_http_flows DROP COLUMN virtual_trace_id, DROP COLUMN pid, DROP COLUMN ppid, DROP COLUMN container_id;` (and same for `l7_grpc_flows`) |
| Phase 3B | Drop the bloom indexes — query falls back to full partition scan (slower but correct): `ALTER TABLE l7_http_flows DROP INDEX idx_src_pod, DROP INDEX idx_dst_pod;` (and same for `l7_grpc_flows`/`l7_dns_flows`) |
| Phase 2  | Drop the 5 RED MVs and their target tables: `DROP VIEW l7_http_red_svc_5min_mv; DROP TABLE l7_http_red_svc_5min;` (×5). The APM Services / Service Detail pages will show "data warming up" / empty states. |
| Phase 1A | Frontend filter additions are URL-encoded; old bookmarks (without filters) keep working. Backend `/l7/traces` filter params are optional — drop any that misbehave by removing them from the request, no server change required. |
| Phase 1B | Revert `TraceWaterfall.tsx`. Both call sites (TraceExplorer + ServiceMap drawer) consume the same component; reverting auto-reverts both. |

### Monitoring after rollout

Watch for these signals during the first 24h:

```sql
-- 1. INSERT p99 latency on writers (write amplification from MVs)
SELECT
  toStartOfMinute(event_time) AS m,
  quantile(0.99)(query_duration_ms) AS p99
FROM system.query_log
WHERE event_date >= today()
  AND query LIKE 'INSERT INTO%l7_http_flows%'
  AND type = 'QueryFinish'
GROUP BY m ORDER BY m DESC LIMIT 30;
-- Threshold: p99 > 200ms over a 5-minute window → consider
-- async_insert=1 or temporarily disabling Phase 2 MVs.

-- 2. PID correlator coverage (Phase 4)
SELECT
  toStartOfMinute(timestamp) AS m,
  countIf(virtual_trace_id != '') AS virtual_rows,
  countIf(trace_id != '') AS w3c_rows,
  count() AS total
FROM flowfish.l7_http_flows
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY m ORDER BY m DESC;

-- 3. Related Traces query latency (Phase 3B)
SELECT
  quantile(0.5)(query_duration_ms) AS p50,
  quantile(0.95)(query_duration_ms) AS p95
FROM system.query_log
WHERE query LIKE '%idx_src_pod%' OR query LIKE '%idx_dst_pod%'
  AND event_date >= today();
```

### Known gaps (deferred / out-of-scope)

- **Cross-protocol PID stitching**: a request that enters service A as
  HTTP and exits to service B as gRPC produces spans on different
  RabbitMQ queues consumed by different writer instances. Each instance
  sees only its own protocol, so the correlator never co-bunches them.
  This is acceptable for the common case (single-protocol chains).
  Resolving it requires a shared correlator (Redis) and is tracked as
  Phase 5+ in the plan.
- **Recent Traces list does not surface virtual traces**: `get_recent_traces`
  filters on `trace_id != ''` and groups by `trace_id`. Phase 4 traces
  appear correctly when opened by virtual_trace_id but won't show in
  the Trace Explorer list. The Trace Detail deep-link still works.
  Updating the list to coalesce trace_id with virtual_trace_id is a
  small follow-up.
- **5-tuple correlation**: deferred to Phase 5+. Beyla passive mode
  emits ephemeral src_port values that rarely match across spans, so
  5-tuple is less reliable than PID correlation in practice.

