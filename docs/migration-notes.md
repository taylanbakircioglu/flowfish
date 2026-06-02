# Migration Notes

Operational upgrade notes for Flowfish. See [`CHANGELOG.md`](../CHANGELOG.md) at the repository root for the full release history.

---

## v2.6.0 → v2.7.0

### Summary

This release fixes HTTP path visibility across the entire L7 pipeline.
Before v2.7.0 the Service Map and Integration Hub displayed `/` for
every outbound HTTP dependency (`url.path` only ever exists on SERVER
spans, Beyla CLIENT spans use `url.full`), and a Neo4j MERGE key that
collapsed every request between two workloads onto a single edge —
overwriting the previous path on every flush. Operators saw the same
Grafana data shown correctly in their own dashboards but only `/` in
Flowfish.

The fix is in five layers: span-parsing helper rewrite, MERGE key
extension to per-path granularity, dedup migration alignment, frontend
canvas bundling, and graph-query distinct-peer counting.

### Breaking changes

None for API consumers. **Behavioural change** for Neo4j edge counts
(see below) — automation that asserts "exactly one
`L7_COMMUNICATES_WITH` between `(src, dst)`" will need updating.

### What changed

| Layer | File | Change |
| --- | --- | --- |
| Span parsing | `services/flowfish-l7-collector/app/event_transformer.py` | `_extract_http_path` walks `url.path → http.route → url.full → http.target → http.url` with relative-path guard for malformed values. HTTP branch trigger extended to cover CLIENT-only spans (`url.full`, `http.url`, `http.target`). Method falls back to legacy `http.method`. |
| Graph write | `services/graph-writer/app/l7_graph_builder.py` | `L7_COMMUNICATES_WITH` MERGE key is now `(analysis_id, http_method, http_path)` with `coalesce(..., '')` to satisfy Cypher's null-in-MERGE-key restriction. `_MIGRATE_OUT_CYPHER` / `_MIGRATE_IN_CYPHER` use the same composite key so dedup doesn't collapse per-path edges. |
| Schema | `services/graph-writer/app/graph_client.py` | New relationship property indexes `l7_comm_method`, `l7_comm_path` (Neo4j 4.3+, `IF NOT EXISTS` so it's idempotent). |
| Graph read | `services/graph-query/app/graph_query_engine.py` | `get_l7_dependency_summary` aggregates **distinct peers**, not edges, so per-path multiplication doesn't inflate `inbound_count` / `outbound_count`. |
| Frontend canvas | `frontend/src/pages/ServiceMap.tsx` | Edge bundling: raw per-path edges grouped by `(source, target, protocol)` into a single React Flow edge. Bundle data includes a `paths` array. Edge CSV export expands `paths` so the CSV stays operator-useful. |
| Frontend table | `frontend/src/pages/IntegrationHub.tsx` | Edges Table rowKey extended with `(cluster, namespace, method, path)` to eliminate React rowKey collisions under per-path multiplication. |

### Required actions

| Audience | Action |
| --- | --- |
| Cluster operators (single release) | Roll out collector + graph-writer + graph-query + frontend **in the same release**. The collector now emits `http_path` for CLIENT spans; if graph-writer is still on v2.6.0 it will accept the new payload but write it to a single MERGE bucket — the per-path edges only materialise once graph-writer v2.7.0 is in. Indexes are created automatically on first start-up. |
| Cluster operators (existing analyses) | The fix only affects edges written **after** the upgrade. Old `L7_COMMUNICATES_WITH` rows in Neo4j retain their pre-fix shape (`/` paths, single edge per `(src, dst)`). To get clean data, re-run the analysis. Optional purge query is below. |
| Cluster operators (Neo4j capacity) | Per-path edges multiply edge count in proportion to per-source endpoint cardinality. A typical microservice with five outbound endpoints will go from ~1 edge to ~5 edges per source. Watch the cardinality observation queries below. |
| API consumers (read-only) | None — response shape is unchanged; `request_count` totals still aggregate correctly. |
| Frontend snippet/export consumers | Edge CSV now has one row per `(method, path)`. JSON export's `data.paths` array is the new structured per-path breakdown. |

#### Optional: purge old single-edge analyses

If you want the cleanest possible Neo4j state after upgrading, drop the
pre-v2.7.0 analyses that still have `/` paths and a single edge per
`(src, dst)`:

```cypher
// Identify candidates (read-only):
MATCH ()-[r:L7_COMMUNICATES_WITH]->()
WHERE r.http_path = '/' AND r.analysis_id IN $aids
RETURN r.analysis_id, count(*) AS edge_count
ORDER BY edge_count DESC;

// Purge after operator confirmation:
MATCH (n:L7Workload {analysis_id: $aid})
DETACH DELETE n;
```

The first query lists per-analysis edge counts where every edge has
`http_path = '/'` — these are the legacy analyses. The second deletes
all nodes (and via DETACH all edges) for a confirmed analysis id.
Replace `$aid` with the analysis you want to clean.

### PII / privacy implications of path strings

Real HTTP paths can contain personally identifiable or otherwise
sensitive data (account numbers, user IDs, tokens in path-style API
keys, session ids in legacy services). Before v2.7.0 the fall-through
to `/` silently mitigated this; in v2.7.0 actual paths are persisted
in Neo4j (`L7_COMMUNICATES_WITH.http_path`) and ClickHouse (`l7_http_flows.http_path`).

Mitigations:

1. **Beyla SERVER-side templating** is configurable via `routes.unmatched`
   (`low-cardinality` collapses numeric ids to `{:id}`). This applies to
   spans Beyla classifies as SERVER. CLIENT spans (`url.full`) are NOT
   templated by Beyla — operators who need that have to filter paths in
   the `flowfish-l7-collector` (out of scope for v2.7.0; track as
   follow-up).
2. **Tighten the `l7_capture_filter` per analysis** if you want to
   exclude PII-prone services from L7 collection altogether. The wizard
   already supports namespace/workload allow-lists.
3. **Treat Neo4j and ClickHouse exports as data-classified per the most
   sensitive namespace included.** L7 tables include enough URL
   structure to reconstruct API traffic patterns.

### Cardinality observability

The MERGE key change means every distinct `(method, path)` between two
workloads is now a separate edge. For most services this multiplies
edge count by 3–15x. Use these queries periodically to spot pathological
cases (services with thousands of unique paths usually mean unbounded
ids in path segments).

```cypher
// Top-20 sources by per-target path variant count:
MATCH (s)-[r:L7_COMMUNICATES_WITH]->(t)
WHERE r.analysis_id = $aid
WITH s, t, count(DISTINCT r.http_path) AS path_variants,
     sum(r.request_count) AS total_req
WHERE path_variants > 1
RETURN s.name AS source, t.name AS target,
       path_variants, total_req
ORDER BY path_variants DESC
LIMIT 20;

// Sources emitting >50 unique paths to a single target (likely needs
// templating in Beyla routes config):
MATCH (s)-[r:L7_COMMUNICATES_WITH]->(t)
WHERE r.analysis_id = $aid
WITH s, t, count(DISTINCT r.http_path) AS path_variants
WHERE path_variants > 50
RETURN s.name, s.namespace, t.name, t.namespace, path_variants
ORDER BY path_variants DESC;

// Total edge count by analysis — track this before/after the upgrade
// to size Neo4j storage:
MATCH ()-[r:L7_COMMUNICATES_WITH]->()
WHERE r.analysis_id = $aid
RETURN count(*) AS edge_count;
```

When `path_variants > 50` for a single source, extend the Beyla
`routes.patterns` for that service to template the high-cardinality
segment — the routes config feeds the `http.route` attribute which the
collector picks before `url.path`, so adding a pattern there collapses
the variants to one templated edge.

### Verification scenarios

After deploying v2.7.0, run the following smoke tests:

1. **CLIENT span path recovery.** Pick a known outgoing HTTP dependency
   (e.g. your service → Elasticsearch). In the Service Map drawer for
   that source workload, verify the Connections tab shows the real
   downstream path (`/_bulk`, `/_search`, …) instead of `/`.
2. **Per-path edge fan-out.** Open the Integration Hub Edges table for
   a busy gateway. Verify multiple rows for the same `(source, target,
   protocol)` differing only by `method` / `path`. No React "duplicate
   key" console warnings.
3. **Canvas bundling.** Open the Service Map canvas for the same
   gateway. Verify the high-fan-out dependency renders as ONE edge with
   a `N paths` label suffix, not as N stacked arrows.
4. **CSV / JSON export integrity.** Click **Export → CSV** on the
   Service Map. Verify one CSV row per `(method, path)`. Click
   **Export → JSON** — verify each edge has a `paths` array.
5. **Dependency count stability.** Pull `GET
   /api/v1/l7/dependencies/summary?analysis_id=...` for any analysis.
   Verify `outbound_count` reflects distinct downstream services, not
   total edges (a gateway talking to one service over 50 paths must
   show `outbound_count = 1`).
6. **Backward-compat regression.** Confirm legacy analyses created
   before the upgrade still render — they will continue to show a
   single edge with `/` per dependency (no data migration is performed
   automatically).

---

## v2.5.0 → v2.6.0

### Summary

This release closes the L7 parity gap in the Integration Hub. L7 dependency summaries can now be filtered by annotation, label, owner/workload name and pod name (matching the L4 surface), and the Integration Hub fans BOTH-mode analyses out to L4 and L7 endpoints in parallel.

The release is **backwards compatible** for all existing API consumers. No data migration is required.

### Breaking changes

None.

### API surface changes

#### `GET /api/v1/l7/dependencies/summary`

New optional parameters:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `annotation_key` | string | — | fnmatch glob supported |
| `annotation_value` | string | — | fnmatch glob supported |
| `label_key` | string | — | fnmatch glob supported |
| `label_value` | string | — | fnmatch glob supported |
| `owner_name` | string | — | Server-side alias for `workload_name`; `workload_name` takes precedence when both are supplied |
| `pod_name` | string | — | Case-insensitive substring match against `L7Workload.name` |
| `workload_name` | string | — | Case-insensitive substring match against `L7Workload.name` |
| `filter_noise_annotations` | boolean | `false` | Strips infrastructure annotation prefixes (`kubectl.kubernetes.io/`, `kubernetes.io/`, `openshift.io/`) from the response |

Response shape additions:

- Every workload entry now includes `is_matched: boolean`.
  - With no filter active: `is_matched=true` on every entry (no neighbour expansion).
  - With any filter active: matched workloads are `is_matched=true`; their immediate neighbours are returned with `is_matched=false` so callers retain dependency context.
- The Neo4j query LIMIT is multiplied by 10 internally when a filter is active so post-filtering does not truncate results. Callers can still set their own `limit` upstream.

#### `GET /api/v1/l7/dependencies/tree-summary`

New optional parameter:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `workload_name_exact` | boolean | `true` | Default preserves existing exact-match behaviour. Set `false` for case-insensitive substring match (mirrors L4 `owner_name` semantics). |

#### OpenAPI

- `analysis_id` on both L7 endpoints is now typed as `string` to match the multi-cluster sub-analysis prefix already used at runtime.
- The `namespace` and `include_metadata` parameters on `/l7/dependencies/summary` are now explicitly listed in the spec (the runtime already supported them).

### Frontend / Integration Hub changes

- The dedicated **L7 Workload Search** card has been removed. The unified Service Identification card now handles every analysis level.
- **Namespace** is now an orthogonal field — it applies to every identification method (annotation, label, namespace + deployment / workload, pod name, advanced), not just `namespace_deployment`.
- The `namespace_deployment` method label has been renamed to *Namespace + Deployment / Workload* for clarity across L4 and L7.
- BOTH-mode analyses fan out to L4 and L7 endpoints in parallel and render two preview tabs plus an L4/L7 snippet toggle.
- Snippet builders emit the full filter surface (annotation/label/owner_name/pod_name) for L4 and L7 alike. L7 tree snippets now always set `workload_name_exact=false`.

### Behavioural changes operators should know

| Behaviour | v2.5.0 | v2.6.0 |
| --- | --- | --- |
| `GET /l7/dependencies/summary` with annotation filter | Filter parameters ignored; full namespace result returned. | Cypher `CONTAINS` pre-filter + Python `fnmatch` post-filter; only matched workloads + immediate neighbours returned. |
| Integration Hub with `analysis_level=both` | L4 endpoint only; L7 data missing in Preview and snippets. | Both endpoints queried in parallel; Network/Application tabs in Preview; L4/L7 toggle in Integration Code. |
| Integration Hub Service Identification card visibility | Hidden for L7 analyses (only the L7 Workload Search card shown). | Always visible. |
| `tree-summary` workload_name semantic | Exact match only. | Default exact (`workload_name_exact=true`); opt-in substring (`workload_name_exact=false`). The Integration Hub explicitly opts in. |

### Required actions

| Audience | Action |
| --- | --- |
| Cluster operators | None — drop-in upgrade. |
| API consumers (read-only) | None — defaults preserve existing behaviour. |
| API consumers using the L7 `tree-summary` substring trick | Explicitly pass `workload_name_exact=false`. |
| Integration Hub snippet copy/paste users | Re-copy snippets after upgrading; new identification parameters are emitted. |

### Verification scenarios

After deploying v2.6.0, run the following smoke tests against any cluster:

1. **L7 annotation filter parity.** Start a BOTH analysis, then in the Integration Hub configure `annotation_key=mycompany.com/project`, `annotation_value=NBA`. Verify the workload count on the *Application Dependencies (L7)* tab matches what the Service Map renders for the same filter.
2. **Pure L7 with namespace.** Start an L7-only analysis, pick *Namespace + Deployment / Workload*, fill in a namespace + workload name. Verify the Preview lists matched workloads + neighbours and that the Integration Code emits the L7 query string.
3. **Partial failure.** Temporarily scale `graph-query` down (or simulate by blocking `/l7/*` at the gateway), launch a BOTH-mode query, and verify the L4 tab renders while the L7 tab shows an inline error banner.
4. **Multi-cluster annotation.** With two clusters connected, run the annotation filter scenario and verify workloads from both clusters appear with the correct `cluster` field. Frontend deduplication uses the `(cluster, namespace, name)` tuple — re-confirm there are no duplicates.
5. **Backward compatibility.** Call `GET /api/v1/l7/dependencies/tree-summary` from any existing pipeline without `workload_name_exact`; verify the response matches v2.5.0 exact-match behaviour.

---

## Older releases

Pre-v2.5.0 release notes are not tracked in this file.
