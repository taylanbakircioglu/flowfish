# Changelog

All notable changes to Flowfish are documented in this file.

The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.8.0] - 2026-06

### Security

- **nginx pinned to patched 1.31.1-alpine** across the frontend image
  (`frontend/Dockerfile`, `Dockerfile.production`, `Dockerfile.simple`)
  and the local-test manifests (poolslip advisory). The floating
  `nginx:alpine` tag previously resolved to the vulnerable 1.31.0.

### Fixed — RabbitMQ queue-declaration resilience

- **graph-writer** and **timeseries-writer** no longer crash (graph-writer)
  or spin in the reconnect handler (timeseries-writer) when a queue already
  exists with arguments that differ from the declaration — e.g. a legacy
  queue created without `x-dead-letter-exchange`. The consumers now catch
  the `PRECONDITION_FAILED` and bind to the existing queue as-is. graph-writer
  additionally uses a dedicated channel per consumer, so one queue's argument
  mismatch can no longer tear down the other consumers.

---

## [2.7.0] - 2026-05

### Fixed — L7 HTTP Path Visibility (Audit v4)

Real HTTP paths now appear in the Service Map, Integration Hub, JSON
exports, and CSV exports. Before this release every outbound HTTP
dependency rendered as `/` because:

1. `event_transformer._build_http_event` only read `url.path` /
   `http.route` — both server-side attributes. OpenTelemetry HTTP
   semconv exposes `url.full` on CLIENT spans, which Beyla uses for
   every outgoing call. The transformer silently fell back to `/`.
2. The graph-writer Neo4j MERGE key was `{analysis_id}` only, so
   multiple endpoints between two workloads collapsed onto a single
   `L7_COMMUNICATES_WITH` edge — with `http_path` overwritten on every
   upsert.

### Added — Per-path edge model

- **`event_transformer._extract_http_path`** — walks the OTel HTTP
  semconv lookup chain (`url.path → http.route → url.full →
  http.target → http.url`). Uses `urllib.parse.urlsplit` for the
  client-side attributes and rejects malformed URLs via a
  relative-path guard so garbage `url.full` payloads cannot poison the
  per-path edge MERGE key.
- **`_transform_single_span` HTTP branch widening** — CLIENT-only
  spans (`url.full`, `http.url`, `http.target`) now trigger the HTTP
  branch instead of being dropped. gRPC / DNS still take priority.
- **Per-path Neo4j edges** — `L7_COMMUNICATES_WITH` MERGE key
  extended to `{analysis_id, http_method, http_path}` with `coalesce(..., '')`
  so empty values don't violate Cypher's null-in-MERGE-key rule. Edge
  attributes (`request_count`, `error_count`, `total_latency_ms`,
  trace context) are now stable per endpoint.
- **Dedup migration alignment** — `_MIGRATE_OUT_CYPHER` and
  `_MIGRATE_IN_CYPHER` use the same 3-property MERGE key when
  re-pointing edges off `namespace='unknown'` placeholders so the
  periodic dedup pass does not collapse per-path edges.
- **Relationship property indexes** — `l7_comm_method` (`ON
  (r.http_method)`) and `l7_comm_path` (`ON (r.http_path)`) on
  `L7_COMMUNICATES_WITH` (Neo4j 4.3+, idempotent `IF NOT EXISTS`).
- **Distinct-peer aggregation** — `graph_query_engine.get_l7_dependency_summary`
  counts distinct destination/source workloads instead of edges, so
  per-path multiplication does not inflate `inbound_count` /
  `outbound_count` in API responses or the Integration Hub UI.
- **Frontend canvas edge bundling** — `ServiceMap.tsx` groups per-path
  edges by `(source, target, protocol)` before passing them to React
  Flow. Each bundle becomes one visual edge with a `N paths` label
  suffix and the full per-path breakdown in `data.paths`. Edge CSV
  export expands `paths` so one CSV row corresponds to one
  `(method, path)`.
- **Integration Hub Edges Table** — rowKey extended to include
  `(cluster, namespace, method, path)` so per-path multiplication
  cannot trigger React duplicate-key warnings.

### Tests

- **`services/flowfish-l7-collector/tests/test_event_transformer.py`** —
  19 unit tests covering the OTel lookup order, server vs. client
  attribute split, query/fragment stripping, malformed-URL guard,
  legacy method fallback, and the gRPC/DNS branch isolation.
- **`services/graph-query/tests/test_l7_dependency_summary.py`** —
  3 new scenarios pin the distinct-peer accounting (per-path collapse
  to single peer, protocol-as-peer-identity, filter+per-path
  interaction).

### Migration notes (v2.6.0 → v2.7.0)

See [`docs/migration-notes.md`](docs/migration-notes.md#v260--v270)
for the full table including deployment order, optional purge query
for old single-edge analyses, PII implications of per-path storage,
and Cypher cardinality observation queries with Beyla `routes.patterns`
guidance.

### Required actions

| Audience | Action |
| --- | --- |
| Cluster operators | Roll out collector + graph-writer + graph-query + frontend in the same release. Neo4j indexes are created automatically. |
| Operators upgrading from v2.5.0 / v2.6.0 | Old analyses retain pre-fix data (`/` paths, single edge per `(src, dst)`); re-run analyses you want correct paths for. Optional Cypher purge query in migration notes. |
| API consumers (read-only) | None — response shapes are unchanged. |
| Frontend snippet/CSV consumers | Re-export after upgrade; edge CSV now has one row per endpoint and JSON edges carry a structured `paths` array. |

---

## [2.6.0] - 2026-05

### Added — Integration Hub L7 parity

- **L7 dependency summary filters.** `GET /api/v1/l7/dependencies/summary` now accepts the same identification surface as the L4 summary endpoint:
  - `annotation_key`, `annotation_value`
  - `label_key`, `label_value`
  - `owner_name` (alias for `workload_name`)
  - `pod_name`
  - `workload_name`
  - `filter_noise_annotations` (boolean, default `false`)
  - All filter values support fnmatch globs (`*`, `?`, `[seq]`).
- **`is_matched` flag** on every workload entry in the L7 summary response so callers can distinguish workloads matched by the filter (`is_matched=true`) from their immediate neighbours pulled in for context (`is_matched=false`).
- **`workload_name_exact` flag** on `GET /api/v1/l7/dependencies/tree-summary`. Default `true` to preserve previous exact-match semantics; the Integration Hub frontend explicitly sends `workload_name_exact=false` to align with L4's case-insensitive substring behaviour.
- **Integration Hub BOTH analysis level.** When the operator picks an analysis with `analysis_level=both`:
  - Step 1 fans the configured form out to L4 and L7 endpoints in parallel via `Promise.allSettled`.
  - Step 2 (Preview) renders two tabs — *Network Dependencies (L4)* and *Application Dependencies (L7)* — each with its own error banner on partial failure.
  - Step 3 (Integration Code) shows a top-level L4/L7 toggle that swaps the active snippet set.
  - The L4 leg covers every selected analysis; the L7 leg targets the first analysis with a toast warning when extra analyses are dropped (L7 endpoints are single-analysis).
- **Service Identification card visibility.** The card now renders on every analysis level (L4, L7, BOTH). The standalone "L7 Workload Search" card has been removed; the unified card handles every method.
- **`Namespace` is an orthogonal field.** It applies to every identification method (annotation, label, namespace+deployment/workload, pod name, advanced) rather than only `namespace_deployment`.
- **`namespace_deployment` label renamed** to *Namespace + Deployment / Workload* for clarity between L4 and L7.
- **OpenAPI spec updates** for the two endpoints (`analysis_id` is now `string`, new parameters documented).

### Changed

- `services/graph-query/app/graph_query_engine.py`: `_NOISE_ANNOTATION_PREFIXES`, `_filter_summary_annotations`, `_parse_metadata_field`, and `_glob_match_metadata` are now module-level helpers shared by the L4 and L7 paths.
- `services/graph-query/app/graph_query_engine.py`: `get_l7_dependency_summary` pre-filters with Cypher `CONTAINS` (quote-wrapped for JSON-encoded strings) and post-filters with Python `fnmatch` to match L4 parity. The Neo4j query LIMIT is multiplied by 10 when a filter is active so that post-filtering does not truncate results.
- `services/graph-query/app/graph_query_engine.py`: `find_l7_workload_dependencies` accepts `workload_name_exact` and uses the shared `_glob_match_metadata` helper.
- `backend/routers/l7_communications.py`: proxy forwards all new parameters and aliases `owner_name → workload_name` (with `workload_name` taking precedence when both are supplied).
- `frontend/src/utils/snippetBuilders.ts`: L7 cURL / Python / JS / Java / Pipeline snippets emit the full filter surface; L7 tree snippets always set `workload_name_exact=false`.

### Migration notes (v2.5.0 → v2.6.0)

| Topic | What changes | Required action |
| --- | --- | --- |
| `GET /l7/dependencies/summary` | New optional parameters listed above. Existing callers without any filter receive the unchanged response shape **plus** `is_matched=true` on every workload (no neighbour-expansion when no filter is active). | None for unchanged callers. |
| `GET /l7/dependencies/tree-summary` | New optional `workload_name_exact` parameter, default `true`. | None — the default keeps existing behaviour. Clients that previously relied on substring matching (only the Integration Hub did so) must explicitly pass `workload_name_exact=false`. |
| L7 Workload Search card | Removed from the Integration Hub UI; the unified Service Identification card now exposes the same `workload_name` field through the *Namespace + Deployment / Workload* method. | None for API consumers; UI bookmarks should re-pin the Integration Hub page. |
| `analysis_id` on L7 endpoints | OpenAPI type corrected to `string` to match the multi-cluster sub-analysis prefix already used at runtime. | None — backend was already accepting strings; only the schema is corrected. |
| Pipeline snippets | The Integration Hub now generates the same identification parameters for L4 and L7 snippets when `analysis_level=both`. | Re-copy snippets after upgrading if your pipeline relies on the L7 query string. |

### Deprecated

- The standalone L7 workload search input (Integration Hub) is removed in favour of the unified identification card. The underlying API endpoints are unchanged.

### Fixed

- L7 Integration Hub returning empty results for namespaces that worked in the Service Map. The mismatch was caused by the L7 summary endpoint not accepting annotation/label/owner_name filters and the frontend not routing BOTH-mode queries through both L4 and L7 endpoints.

---

## [2.5.0] - 2026-04

Baseline release prior to the Integration Hub L7 parity work.
