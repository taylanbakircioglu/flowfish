"""SAME_WORKLOAD cross-cluster L7Workload deduplication.

When applications span multiple clusters (Cluster X service A → Cluster Y
gateway → External service B), Beyla creates separate L7Workload nodes in
each cluster: an "external" placeholder in cluster X (representing the
remote target) and an enriched node in cluster Y (representing the local
workload). This module bridges the two via SAME_WORKLOAD relationships so
the Service Map can render the call chain as a single dependency.

Three matching layers, applied in order of confidence:
    1. trace_id-based   — both edges share W3C trace_id (HIGH confidence)
    2. exact-name-based — workloads share (analysis_id, name) across clusters (MEDIUM)
    3. hostname-based   — external workload name matches a service hostname (MEDIUM)

All layers only operate on `external` namespace placeholder nodes to avoid
disturbing locally-resolved L7Workload pairs. The periodic task runs after
the existing dedup pass to avoid lock contention on the same nodes.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# All layers below match an analysis_id either exactly OR as a multi-cluster
# parent prefix ($aid_prefix = "$aid-"). This handles both single-analysis
# pipelines and multi-cluster pipelines where each cluster gets its own
# sub-analysis ID like "<parent>-<cluster_id>". Without prefix matching, a
# cross-cluster bridge (cluster X external --> cluster Y local) could never be
# detected because each side carries a different sub-analysis ID.

# Layer 1: trace_id-based matching (highest confidence).
# An external placeholder (ext) inbound edge shares trace_id with a local
# enriched workload (local) outbound edge in a different cluster.
# Additional name check defends against trace_id collisions across unrelated
# workloads in the same analysis.
# count(DISTINCT ext) is used so the metric reflects "ext nodes bridged" rather
# than the cartesian product of (r1, r2) match rows.
_LAYER_TRACE_CYPHER = """
MATCH (ext:L7Workload)
WHERE (ext.analysis_id = $aid OR ext.analysis_id STARTS WITH $aid_prefix)
  AND ext.namespace = 'external'
  AND NOT (ext)-[:SAME_WORKLOAD]->()
WITH ext
MATCH (src:L7Workload)-[r1:L7_COMMUNICATES_WITH]->(ext)
WHERE r1.last_trace_id IS NOT NULL AND r1.last_trace_id <> ''
WITH ext, r1.last_trace_id AS tid
MATCH (local:L7Workload)-[r2:L7_COMMUNICATES_WITH]->(:L7Workload)
WHERE (local.analysis_id = $aid OR local.analysis_id STARTS WITH $aid_prefix)
  AND local.cluster <> ext.cluster
  AND local.namespace <> 'external'
  AND local.namespace <> 'unknown'
  AND r2.last_trace_id = tid
  AND local.name = ext.name
MERGE (ext)-[sw:SAME_WORKLOAD]->(local)
ON CREATE SET sw.confidence = 'high',
              sw.matched_by = 'trace_id',
              sw.last_trace_id = tid,
              sw.created_at = datetime()
RETURN count(DISTINCT ext) AS merged_count
"""

# Layer 2: exact name match (medium confidence).
# External placeholder named "apisix" in cluster X matches a local workload
# named "apisix" in cluster Y. Skipped when ext already has a SAME_WORKLOAD
# (preserving Layer 1 results).
# Uses head(collect(local)) per ext to deterministically pick exactly one
# bridge target (most-recently-seen). Without this, `WITH ext, local LIMIT 1`
# would limit to ONE bridge across the whole query (global limit) rather than
# one bridge per ext, and ambiguous names could still produce a single match.
_LAYER_EXACT_NAME_CYPHER = """
MATCH (ext:L7Workload)
WHERE (ext.analysis_id = $aid OR ext.analysis_id STARTS WITH $aid_prefix)
  AND ext.namespace = 'external'
  AND NOT (ext)-[:SAME_WORKLOAD]->()
WITH ext
MATCH (local:L7Workload)
WHERE (local.analysis_id = $aid OR local.analysis_id STARTS WITH $aid_prefix)
  AND local.name = ext.name
  AND local.cluster <> ext.cluster
  AND local.namespace <> 'external'
  AND local.namespace <> 'unknown'
WITH ext, local ORDER BY local.last_seen DESC
WITH ext, head(collect(local)) AS local
WHERE local IS NOT NULL
MERGE (ext)-[sw:SAME_WORKLOAD]->(local)
ON CREATE SET sw.confidence = 'medium',
              sw.matched_by = 'exact_name',
              sw.created_at = datetime()
RETURN count(DISTINCT ext) AS merged_count
"""

# Layer 3: hostname-based (medium confidence).
# External placeholder name like "api.example.com" matches the leftmost label
# of a local workload's hostname (e.g. local workload "api" with annotated
# hostname "api.example.com"). Avoids collapsing FQDN externals that map to
# unrelated short-named local services.
_LAYER_HOSTNAME_CYPHER = """
MATCH (ext:L7Workload)
WHERE (ext.analysis_id = $aid OR ext.analysis_id STARTS WITH $aid_prefix)
  AND ext.namespace = 'external'
  AND NOT (ext)-[:SAME_WORKLOAD]->()
  AND ext.name CONTAINS '.'
WITH ext, split(ext.name, '.')[0] AS host_label
MATCH (local:L7Workload)
WHERE (local.analysis_id = $aid OR local.analysis_id STARTS WITH $aid_prefix)
  AND local.name = host_label
  AND local.cluster <> ext.cluster
  AND local.namespace <> 'external'
  AND local.namespace <> 'unknown'
WITH ext, local ORDER BY local.last_seen DESC
WITH ext, head(collect(local)) AS local
WHERE local IS NOT NULL
MERGE (ext)-[sw:SAME_WORKLOAD]->(local)
ON CREATE SET sw.confidence = 'medium',
              sw.matched_by = 'hostname',
              sw.created_at = datetime()
RETURN count(DISTINCT ext) AS merged_count
"""


def _derive_parent_aids(analysis_ids: list) -> list:
    """Derive parent analysis IDs from a list of single or multi-cluster IDs.

    Multi-cluster sub-analyses are tagged with "<parent>-<cluster_id>" so a
    cross-cluster bridge needs to be checked at the parent level. Single
    analyses (no dash) are kept as-is. Returns a deduplicated list, preserving
    the original order so layer counts roll up deterministically.
    """
    seen: set = set()
    parents: list = []
    for aid in analysis_ids:
        if not aid:
            continue
        # Multi-cluster sub-analysis IDs use "<parent>-<cluster_id>" format.
        # Take the first segment (split on the FIRST '-' only, in case parent
        # itself contains dashes).
        parent = aid.split("-", 1)[0] if "-" in aid else aid
        if parent not in seen:
            seen.add(parent)
            parents.append(parent)
    return parents


def run_same_workload_periodic(graph_client: Any, analysis_ids: list) -> dict:
    """Apply all three SAME_WORKLOAD matching layers for the given analysis IDs.

    Idempotent: re-running on the same data doesn't create duplicates because
    each layer guards via `NOT (ext)-[:SAME_WORKLOAD]->()`.
    Returns counts per layer for observability.

    For multi-cluster analyses, sub-analysis IDs like "<parent>-<cluster_id>"
    are reduced to their parent so cross-cluster bridges (cluster X --> cluster
    Y) are discovered. Each Cypher layer also matches `analysis_id = $aid OR
    analysis_id STARTS WITH $aid_prefix` to span both single-analysis and
    multi-cluster pipelines.
    """
    if not analysis_ids:
        return {"trace_id": 0, "exact_name": 0, "hostname": 0}

    parent_aids = _derive_parent_aids(analysis_ids)
    counts = {"trace_id": 0, "exact_name": 0, "hostname": 0}
    for aid in parent_aids:
        params = {"aid": aid, "aid_prefix": f"{aid}-"}
        try:
            r1 = graph_client.execute_query(_LAYER_TRACE_CYPHER, params)
            counts["trace_id"] += _records_count(r1)
            r2 = graph_client.execute_query(_LAYER_EXACT_NAME_CYPHER, params)
            counts["exact_name"] += _records_count(r2)
            r3 = graph_client.execute_query(_LAYER_HOSTNAME_CYPHER, params)
            counts["hostname"] += _records_count(r3)
        except Exception:
            logger.exception("SAME_WORKLOAD periodic failed for analysis_id=%s", aid)
            continue

    total = sum(counts.values())
    if total > 0:
        logger.info(
            "SAME_WORKLOAD bridges created: trace=%d exact_name=%d hostname=%d (total=%d)",
            counts["trace_id"], counts["exact_name"], counts["hostname"], total,
        )
    return counts


def _records_count(result: Any) -> int:
    """Extract merged_count from execute_query result."""
    if not isinstance(result, dict) or not result.get("success"):
        return 0
    records = result.get("records", []) or []
    if not records:
        return 0
    first = records[0]
    if isinstance(first, dict):
        v = first.get("merged_count", 0)
    else:
        try:
            v = first[0]
        except (TypeError, IndexError):
            v = 0
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0
