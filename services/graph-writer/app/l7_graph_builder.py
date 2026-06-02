"""L7 (HTTP / gRPC / DNS) graph handlers — L7Workload nodes and L7_COMMUNICATES_WITH edges."""

import json
import logging
import time
import threading
from typing import Any, Dict, List, Tuple

from app.deleted_analysis_cache import deleted_analysis_cache

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BATCH_TIMEOUT_SEC = 2.0


def _endpoint_ns_workload(side: Any) -> Tuple[str, str]:
    if not isinstance(side, dict):
        return "unknown", "unknown"
    wl = (
        side.get("workload_name")
        or side.get("pod_name")
        or side.get("name")
        or side.get("ip")
        or "unknown"
    )
    ns = side.get("namespace") or "unknown"
    return str(ns), str(wl)


def _extract_src_dst(data: Dict[str, Any]) -> Tuple[str, str, str, str]:
    if isinstance(data.get("src"), dict):
        src_ns, src_wl = _endpoint_ns_workload(data["src"])
    else:
        src_ns = str(data.get("src_namespace") or "unknown")
        src_wl = str(
            data.get("src_workload") or data.get("src_pod") or data.get("src_workload_name") or "unknown"
        )
    if isinstance(data.get("dst"), dict):
        dst_ns, dst_wl = _endpoint_ns_workload(data["dst"])
    else:
        dst_ns = str(data.get("dst_namespace") or "unknown")
        dst_wl = str(
            data.get("dst_workload") or data.get("dst_pod") or data.get("dst_workload_name") or "unknown"
        )
    return src_ns, src_wl, dst_ns, dst_wl


def _l7_node_id(analysis_id: str, cluster_id: str, namespace: str, workload_name: str) -> str:
    return f"l7:{analysis_id}:{cluster_id}:{namespace}:{workload_name}"


def _latency_ms(data: Dict[str, Any]) -> float:
    v = data.get("latency_ms")
    if v is None:
        v = data.get("duration_ms")
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _extract_metadata(data: Dict[str, Any], side: str) -> Tuple[str, str, str, str, bool]:
    """Extract labels, annotations (as JSON strings), owner_kind, network_type, is_external."""
    endpoint = data.get(side) if isinstance(data.get(side), dict) else {}
    labels = data.get(f"{side}_labels") or endpoint.get("labels") or {}
    annotations = data.get(f"{side}_annotations") or endpoint.get("annotations") or {}
    owner_kind = str(data.get(f"{side}_owner_kind") or endpoint.get("owner_kind") or "")
    network_type = str(endpoint.get("network_type") or data.get(f"{side}_network_type") or "")
    is_external = endpoint.get("is_external", False) or data.get(f"{side}_is_external", False)
    labels_json = json.dumps(labels) if isinstance(labels, dict) else str(labels)
    annotations_json = json.dumps(annotations) if isinstance(annotations, dict) else str(annotations)
    return labels_json, annotations_json, owner_kind, network_type, bool(is_external)


class L7EdgeBuffer:
    """Thread-safe buffer that aggregates L7 edges and flushes in batch."""

    # When incoming namespace is "unknown", redirect to an existing enriched node
    # (same analysis + same workload name) so we never create duplicate nodes.
    # Namespace SET uses coalesce to never overwrite a resolved value with "unknown".
    # collect()+[0] avoids cartesian-product row multiplication when multiple
    # namespaces share the same workload name (e.g. enverify-api in two ns).
    _UNWIND_CYPHER = """
    UNWIND $rows AS row

    OPTIONAL MATCH (esrc:L7Workload)
    WHERE row.src_namespace = 'unknown'
      AND esrc.analysis_id = row.analysis_id
      AND esrc.cluster = row.cluster
      AND esrc.name = row.src_name
      AND esrc.namespace <> 'unknown'
    WITH row, collect(esrc.id)[0] AS esrc_id

    OPTIONAL MATCH (edst:L7Workload)
    WHERE row.dst_namespace = 'unknown'
      AND edst.analysis_id = row.analysis_id
      AND edst.cluster = row.cluster
      AND edst.name = row.dst_name
      AND edst.namespace <> 'unknown'
    WITH row, esrc_id, collect(edst.id)[0] AS edst_id

    WITH row,
      coalesce(esrc_id, row.src_id) AS eff_src_id,
      coalesce(edst_id, row.dst_id) AS eff_dst_id

    MERGE (src:L7Workload {id: eff_src_id})
    SET src.name = row.src_name,
        src.namespace = CASE WHEN row.src_namespace <> 'unknown' THEN row.src_namespace
                             ELSE coalesce(src.namespace, row.src_namespace) END,
        src.cluster = row.cluster,
        src.analysis_id = row.analysis_id, src.kind = row.src_kind,
        src.labels = row.src_labels, src.annotations = row.src_annotations,
        src.owner_kind = coalesce(nullIf(row.src_owner_kind, ''), src.owner_kind),
        src.network_type = coalesce(nullIf(row.src_network_type, ''), src.network_type),
        src.is_external = CASE WHEN row.src_network_type IS NOT NULL AND row.src_network_type <> '' THEN row.src_is_external ELSE coalesce(src.is_external, false) END,
        src.last_seen = datetime()

    MERGE (dst:L7Workload {id: eff_dst_id})
    SET dst.name = row.dst_name,
        dst.namespace = CASE WHEN row.dst_namespace <> 'unknown' THEN row.dst_namespace
                             ELSE coalesce(dst.namespace, row.dst_namespace) END,
        dst.cluster = row.cluster,
        dst.analysis_id = row.analysis_id, dst.kind = row.dst_kind,
        dst.labels = row.dst_labels, dst.annotations = row.dst_annotations,
        dst.owner_kind = coalesce(nullIf(row.dst_owner_kind, ''), dst.owner_kind),
        dst.network_type = coalesce(nullIf(row.dst_network_type, ''), dst.network_type),
        dst.is_external = CASE WHEN row.dst_network_type IS NOT NULL AND row.dst_network_type <> '' THEN row.dst_is_external ELSE coalesce(dst.is_external, false) END,
        dst.last_seen = datetime()

    WITH src, dst, row
    // v2.7.0 (Audit v4): MERGE key includes (http_method, http_path) so that
    // each distinct endpoint becomes its own edge. The previous {analysis_id}-
    // only key collapsed every request between (src, dst) into a single edge
    // and overwrote `http_path` on every upsert — Service Map and Integration
    // Hub therefore always showed the *last observed* path (typically the
    // health-check or another short path). Operators who want a single
    // aggregated edge for canvas rendering should query graph-query with
    // `aggregate=protocol`; the storage layer keeps per-path granularity so
    // both views are derivable.
    //
    // coalesce(...) on the key components guarantees Cypher gets a string
    // (Neo4j refuses null in MERGE key); empty string is a valid sentinel.
    MERGE (src)-[r:L7_COMMUNICATES_WITH {
        analysis_id: row.analysis_id,
        http_method: coalesce(row.http_method, ''),
        http_path: coalesce(row.http_path, '')
    }]->(dst)
    SET r.protocol = row.protocol,
        r.cluster_id = row.cluster_id, r.cluster_name = row.cluster_name,
        r.total_latency_ms = coalesce(r.total_latency_ms, 0.0) + row.latency_ms,
        r.request_count = coalesce(r.request_count, 0) + 1,
        r.error_count = coalesce(r.error_count, 0) + row.is_error,
        r.avg_latency_ms = r.total_latency_ms / r.request_count,
        r.last_seen = datetime(),
        // W3C distributed trace tracking — only update last_trace_id when a real
        // trace ID is observed; preserve previous value on empty observations so
        // edges retain trace context across heartbeats / non-traced requests.
        r.last_trace_id = CASE WHEN row.trace_id <> '' THEN row.trace_id
                               ELSE r.last_trace_id END,
        r.last_span_id = CASE WHEN row.trace_id <> '' THEN row.span_id
                              ELSE r.last_span_id END,
        r.trace_count = coalesce(r.trace_count, 0) + CASE WHEN row.trace_id <> '' THEN 1 ELSE 0 END
    """

    _DEDUP_CYPHER = """
    MATCH (stale:L7Workload)
    WHERE stale.namespace = 'unknown' AND stale.analysis_id IN $aids
    WITH stale
    MATCH (good:L7Workload)
    WHERE good.analysis_id = stale.analysis_id
      AND good.cluster = stale.cluster
      AND good.name = stale.name
      AND good.namespace <> 'unknown'
    WITH stale, good ORDER BY good.last_seen DESC
    WITH stale, collect(good.id)[0] AS good_id
    RETURN stale.id AS stale_id, good_id
    LIMIT 100
    """

    # v2.7.0 (Audit v4): migrate cyphers must use the SAME 3-property MERGE key
    # as the main upsert above (analysis_id, http_method, http_path). Without
    # this the dedup pass would collapse per-path edges back into a single
    # edge per (src, dst) — silently undoing the path-recovery fix every
    # `_DEDUP_EVERY_N_FLUSHES` cycles.
    _MIGRATE_OUT_CYPHER = """
    MATCH (s:L7Workload {id: $sid})-[r:L7_COMMUNICATES_WITH]->(t)
    MATCH (g:L7Workload {id: $gid})
    WITH r, g,
      CASE WHEN t.id = $sid THEN g ELSE t END AS target
    MERGE (g)-[nr:L7_COMMUNICATES_WITH {
        analysis_id: r.analysis_id,
        http_method: coalesce(r.http_method, ''),
        http_path: coalesce(r.http_path, '')
    }]->(target)
    ON CREATE SET nr = properties(r)
    ON MATCH SET nr.request_count = nr.request_count + coalesce(r.request_count, 0),
        nr.total_latency_ms = nr.total_latency_ms + coalesce(r.total_latency_ms, 0),
        nr.error_count = nr.error_count + coalesce(r.error_count, 0),
        nr.avg_latency_ms = CASE WHEN nr.request_count > 0 THEN nr.total_latency_ms / nr.request_count ELSE 0 END,
        nr.trace_count = coalesce(nr.trace_count, 0) + coalesce(r.trace_count, 0),
        nr.last_trace_id = CASE WHEN r.last_trace_id IS NOT NULL AND r.last_trace_id <> ''
                                 THEN r.last_trace_id ELSE nr.last_trace_id END,
        nr.last_span_id = CASE WHEN r.last_trace_id IS NOT NULL AND r.last_trace_id <> ''
                                THEN r.last_span_id ELSE nr.last_span_id END
    DELETE r
    """

    _MIGRATE_IN_CYPHER = """
    MATCH (s)-[r:L7_COMMUNICATES_WITH]->(stale:L7Workload {id: $sid})
    MATCH (g:L7Workload {id: $gid})
    WITH s, r, g
    MERGE (s)-[nr:L7_COMMUNICATES_WITH {
        analysis_id: r.analysis_id,
        http_method: coalesce(r.http_method, ''),
        http_path: coalesce(r.http_path, '')
    }]->(g)
    ON CREATE SET nr = properties(r)
    ON MATCH SET nr.request_count = nr.request_count + coalesce(r.request_count, 0),
        nr.total_latency_ms = nr.total_latency_ms + coalesce(r.total_latency_ms, 0),
        nr.error_count = nr.error_count + coalesce(r.error_count, 0),
        nr.avg_latency_ms = CASE WHEN nr.request_count > 0 THEN nr.total_latency_ms / nr.request_count ELSE 0 END,
        nr.trace_count = coalesce(nr.trace_count, 0) + coalesce(r.trace_count, 0),
        nr.last_trace_id = CASE WHEN r.last_trace_id IS NOT NULL AND r.last_trace_id <> ''
                                 THEN r.last_trace_id ELSE nr.last_trace_id END,
        nr.last_span_id = CASE WHEN r.last_trace_id IS NOT NULL AND r.last_trace_id <> ''
                                THEN r.last_span_id ELSE nr.last_span_id END
    DELETE r
    """

    # SAME_WORKLOAD relationships are migrated separately so that bridges
    # survive even when the stale node has zero outbound L7_COMMUNICATES_WITH
    # (the per-row FOREACH inside _MIGRATE_OUT_CYPHER would never fire if
    # there are no `r` rows). Idempotent — runs once per dedup pair.
    # `WITH DISTINCT g` between the two phases collapses the row stream from
    # the first OPTIONAL MATCH (one per outbound SW) so the inbound OPTIONAL
    # MATCH only runs once instead of N times.
    _MIGRATE_SW_CYPHER = """
    MATCH (g:L7Workload {id: $gid})
    WITH g
    OPTIONAL MATCH (s_out:L7Workload {id: $sid})-[sw_out:SAME_WORKLOAD]->(sw_dst)
    FOREACH (_ IN CASE WHEN sw_out IS NOT NULL THEN [1] ELSE [] END |
        MERGE (g)-[new_out:SAME_WORKLOAD]->(sw_dst)
        ON CREATE SET new_out = properties(sw_out)
        DELETE sw_out
    )
    WITH DISTINCT g
    OPTIONAL MATCH (sw_src)-[sw_in:SAME_WORKLOAD]->(s_in:L7Workload {id: $sid})
    FOREACH (_ IN CASE WHEN sw_in IS NOT NULL THEN [1] ELSE [] END |
        MERGE (sw_src)-[new_in:SAME_WORKLOAD]->(g)
        ON CREATE SET new_in = properties(sw_in)
        DELETE sw_in
    )
    """

    _MAX_BUFFER_SIZE = 50_000
    _DEDUP_EVERY_N_FLUSHES = 20

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: List[Dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._total_flushed = 0
        self._total_dropped = 0
        self._flush_count = 0
        self._seen_analysis_ids: set = set()

    def add(self, params: Dict[str, Any], graph_client: Any) -> None:
        with self._lock:
            if len(self._buffer) >= self._MAX_BUFFER_SIZE:
                self._total_dropped += 1
                # Rate-limit the drop log so a sustained overflow does
                # not flood the writer's stdout. Without this the only
                # signal a buffer overflow ever produced was an
                # in-process counter that no caller reads — a silent
                # data-loss bug. Logging every 1000th drop keeps the
                # signal visible without becoming spam.
                if self._total_dropped % 1000 == 1:
                    logger.warning(
                        "L7 edge buffer at capacity (max=%d); dropped %d events total — graph-query likely back-pressured or down",
                        self._MAX_BUFFER_SIZE,
                        self._total_dropped,
                    )
                return
            self._buffer.append(params)
            if len(self._buffer) >= BATCH_SIZE or (time.monotonic() - self._last_flush) >= BATCH_TIMEOUT_SEC:
                self._flush(graph_client)

    def flush_if_needed(self, graph_client: Any) -> None:
        with self._lock:
            if self._buffer and (time.monotonic() - self._last_flush) >= BATCH_TIMEOUT_SEC:
                self._flush(graph_client)

    def force_flush(self, graph_client: Any) -> None:
        """Unconditional flush used during graceful shutdown."""
        with self._lock:
            self._flush(graph_client)

    def snapshot_seen_analysis_ids(self) -> List[str]:
        """Return a thread-safe snapshot of analysis IDs seen since last dedup.

        Used by the SAME_WORKLOAD periodic so it can iterate analyses without
        racing with `_flush()` in the executor thread (which mutates the set
        under `_lock`). The set itself is intentionally not cleared here — the
        dedup pass owns its lifecycle (clears every N flushes).
        """
        with self._lock:
            return list(self._seen_analysis_ids)

    def _flush(self, graph_client: Any) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush = time.monotonic()
        self._flush_count += 1

        for row in batch:
            aid = row.get("analysis_id")
            if aid:
                self._seen_analysis_ids.add(aid)

        try:
            result = graph_client.execute_query(self._UNWIND_CYPHER, {"rows": batch})
            if not result.get("success"):
                logger.warning("L7 batch graph upsert failed (%d rows): %s", len(batch), result.get("error_msg"))
                self._requeue_with_bound(batch)
            else:
                self._total_flushed += len(batch)
        except Exception:
            logger.exception("L7 batch graph upsert exception (%d rows), re-queuing", len(batch))
            self._requeue_with_bound(batch)

        if self._flush_count % self._DEDUP_EVERY_N_FLUSHES == 0 and self._seen_analysis_ids:
            aids_snapshot = list(self._seen_analysis_ids)
            self._seen_analysis_ids.clear()
            # Run dedup outside the caller's lock via a daemon thread
            t = threading.Thread(
                target=self._dedup_stale_nodes,
                args=(graph_client, aids_snapshot),
                daemon=True,
            )
            t.start()

    def _requeue_with_bound(self, batch: List[Dict[str, Any]]) -> None:
        """Re-add a failed batch to the head of the buffer, bounded by
        `_MAX_BUFFER_SIZE`. Caller must already hold `_lock`.

        Without this bound, a sustained graph-query failure would
        unbounded-grow the in-memory buffer (each `_flush()` failure
        `extend()`s the batch back, and the early-drop guard in
        `add()` only protects the *append* path — `extend()` bypasses
        it). We intentionally keep the *newest* events: if we're back-
        pressured, the most recent picture is more useful for live
        observability than the oldest stale slice.
        """
        self._buffer.extend(batch)
        overflow = len(self._buffer) - self._MAX_BUFFER_SIZE
        if overflow > 0:
            self._buffer = self._buffer[overflow:]
            self._total_dropped += overflow
            logger.warning(
                "L7 edge buffer overflow after re-queue: dropped %d oldest events (total dropped=%d)",
                overflow,
                self._total_dropped,
            )

    def _dedup_stale_nodes(self, graph_client: Any, aids: List[str]) -> None:
        """Merge 'unknown'-namespace nodes into their enriched counterparts.

        Runs every N flushes in a background thread.  Migrates accumulated
        edge metrics so no data is lost, then removes the stale node.
        """
        try:
            result = graph_client.execute_query(self._DEDUP_CYPHER, {"aids": aids})
            pairs = result.get("records", [])
            if not pairs:
                return
            merged = 0
            for pair in pairs:
                sid, gid = pair["stale_id"], pair["good_id"]
                # Migrate L7_COMMUNICATES_WITH edges (outbound + inbound).
                graph_client.execute_query(self._MIGRATE_OUT_CYPHER, {"sid": sid, "gid": gid})
                graph_client.execute_query(self._MIGRATE_IN_CYPHER, {"sid": sid, "gid": gid})
                # Migrate SAME_WORKLOAD bridges in a separate pass so they
                # survive even when stale has no L7_COMMUNICATES_WITH edges
                # (per-row FOREACH inside the migrate cyphers would never
                # fire in that case, leaving SW bridges orphaned).
                graph_client.execute_query(self._MIGRATE_SW_CYPHER, {"sid": sid, "gid": gid})
                graph_client.execute_query(
                    "MATCH (n:L7Workload {id: $sid}) DETACH DELETE n", {"sid": sid}
                )
                merged += 1
            if merged:
                logger.info("L7 dedup: promoted %d unknown→enriched nodes", merged)
        except Exception:
            logger.debug("L7 dedup cycle failed (non-critical)", exc_info=True)

    @property
    def total_flushed(self) -> int:
        return self._total_flushed


l7_edge_buffer = L7EdgeBuffer()


def _run_l7_edge(
    graph_client: Any,
    message: Dict[str, Any],
    *,
    src_ns: str,
    src_wl: str,
    dst_ns: str,
    dst_wl: str,
    src_kind: str,
    dst_kind: str,
    protocol: str,
    http_method: str,
    http_path: str,
    is_error: int,
    src_labels: str = "{}",
    src_annotations: str = "{}",
    src_owner_kind: str = "",
    dst_labels: str = "{}",
    dst_annotations: str = "{}",
    dst_owner_kind: str = "",
    src_network_type: str = "",
    dst_network_type: str = "",
    src_is_external: bool = False,
    dst_is_external: bool = False,
) -> None:
    analysis_id = str(message.get("analysis_id") or "")
    cluster_id = str(message.get("cluster_id") or "")
    cluster_name = str(message.get("cluster_name") or cluster_id)
    cluster = cluster_id
    data = message.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    params = {
        "src_id": _l7_node_id(analysis_id, cluster_id, src_ns, src_wl),
        "src_name": src_wl,
        "src_namespace": src_ns,
        "dst_id": _l7_node_id(analysis_id, cluster_id, dst_ns, dst_wl),
        "dst_name": dst_wl,
        "dst_namespace": dst_ns,
        "cluster": cluster,
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "analysis_id": analysis_id,
        "src_kind": src_kind,
        "dst_kind": dst_kind,
        "protocol": protocol,
        "http_method": http_method,
        "http_path": http_path,
        "is_error": int(is_error),
        "latency_ms": _latency_ms(data),
        "src_labels": src_labels,
        "src_annotations": src_annotations,
        "src_owner_kind": src_owner_kind,
        "dst_labels": dst_labels,
        "dst_annotations": dst_annotations,
        "dst_owner_kind": dst_owner_kind,
        "src_network_type": src_network_type,
        "dst_network_type": dst_network_type,
        "src_is_external": src_is_external,
        "dst_is_external": dst_is_external,
        # W3C distributed trace context (empty string when not present)
        "trace_id": str(data.get("trace_id") or ""),
        "span_id": str(data.get("span_id") or ""),
    }
    l7_edge_buffer.add(params, graph_client)


def handle_l7_http_flow(message: dict, graph_client) -> None:
    analysis_id = message.get("analysis_id")
    if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
        return
    data = message.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    src_ns, src_wl, dst_ns, dst_wl = _extract_src_dst(data)
    if dst_wl == "unknown":
        host = str(data.get("host") or "")
        if host:
            dst_wl = host.split(".")[0] if "." in host else host
    status = data.get("http_status_code")
    if status is None:
        status = data.get("response_status")
    try:
        code = int(status) if status is not None else 0
    except (TypeError, ValueError):
        code = 0
    is_error = 1 if code >= 400 else 0
    method = str(data.get("http_method") or data.get("method") or "")
    path = str(data.get("http_path") or data.get("path") or "")
    s_labels, s_ann, s_ok, s_nt, s_ext = _extract_metadata(data, "src")
    d_labels, d_ann, d_ok, d_nt, d_ext = _extract_metadata(data, "dst")
    _run_l7_edge(
        graph_client,
        message,
        src_ns=src_ns,
        src_wl=src_wl,
        dst_ns=dst_ns,
        dst_wl=dst_wl,
        src_kind="http",
        dst_kind="http",
        protocol="HTTP",
        http_method=method,
        http_path=path,
        is_error=is_error,
        src_labels=s_labels,
        src_annotations=s_ann,
        src_owner_kind=s_ok,
        dst_labels=d_labels,
        dst_annotations=d_ann,
        dst_owner_kind=d_ok,
        src_network_type=s_nt,
        dst_network_type=d_nt,
        src_is_external=s_ext,
        dst_is_external=d_ext,
    )


def handle_l7_grpc_flow(message: dict, graph_client) -> None:
    analysis_id = message.get("analysis_id")
    if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
        return
    data = message.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    src_ns, src_wl, dst_ns, dst_wl = _extract_src_dst(data)
    st = data.get("grpc_status_code")
    if st is None:
        st = data.get("response_status")
    try:
        code = int(st) if st is not None else 0
    except (TypeError, ValueError):
        code = 0
    is_error = 1 if code != 0 else 0
    svc = str(data.get("grpc_service") or "")
    meth = str(data.get("grpc_method") or "")
    path = str(data.get("path") or "")
    s_labels, s_ann, s_ok, s_nt, s_ext = _extract_metadata(data, "src")
    d_labels, d_ann, d_ok, d_nt, d_ext = _extract_metadata(data, "dst")
    _run_l7_edge(
        graph_client,
        message,
        src_ns=src_ns,
        src_wl=src_wl,
        dst_ns=dst_ns,
        dst_wl=dst_wl,
        src_kind="grpc",
        dst_kind="grpc",
        protocol="GRPC",
        http_method=meth,
        http_path=path or svc,
        is_error=is_error,
        src_labels=s_labels,
        src_annotations=s_ann,
        src_owner_kind=s_ok,
        dst_labels=d_labels,
        dst_annotations=d_ann,
        dst_owner_kind=d_ok,
        src_network_type=s_nt,
        dst_network_type=d_nt,
        src_is_external=s_ext,
        dst_is_external=d_ext,
    )


def handle_l7_dns_flow(message: dict, graph_client, graph_builder=None) -> None:
    analysis_id = message.get("analysis_id")
    if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
        return
    data = message.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    src_ns, src_wl, _, _ = _extract_src_dst(data)
    qname_raw = str(data.get("query_name") or "unknown")
    if graph_builder and qname_raw != "unknown":
        qname = graph_builder._normalize_dns_name(qname_raw)
    else:
        qname = qname_raw
    dst_ns, dst_wl = "external", qname
    try:
        rcode = int(data.get("response_code")) if data.get("response_code") is not None else 0
    except (TypeError, ValueError):
        rcode = 0
    is_error = 1 if rcode != 0 else 0
    qtype = str(data.get("query_type") or "")
    s_labels, s_ann, s_ok, s_nt, s_ext = _extract_metadata(data, "src")
    _run_l7_edge(
        graph_client,
        message,
        src_ns=src_ns,
        src_wl=src_wl,
        dst_ns=dst_ns,
        dst_wl=dst_wl,
        src_kind="dns",
        dst_kind="dns",
        protocol="DNS",
        http_method=qtype,
        http_path=qname,
        is_error=is_error,
        src_labels=s_labels,
        src_annotations=s_ann,
        src_owner_kind=s_ok,
        src_network_type=s_nt,
        src_is_external=s_ext,
        dst_network_type="External-Network",
        dst_is_external=True,
    )
