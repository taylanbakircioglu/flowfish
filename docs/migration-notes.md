# Migration Notes

Operational upgrade notes for Flowfish.

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
