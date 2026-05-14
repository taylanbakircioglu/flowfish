"""PID-temporal virtual_trace_id correlator (Phase 4D).

When a service does NOT propagate W3C `traceparent` headers (no OTel SDK,
no Sleuth/Brave instrumentation, no Apisix tracing), Beyla emits a
single-hop span per request whose `trace_id` field is empty. Such spans
cannot be threaded into a multi-hop trace by trace_id alone.

This module provides a deterministic, side-effect-free fallback: events
that share the same producer process *and* fall within a small temporal
window are bundled into a single "virtual trace" identified by a sha1
hash. The hash is stable across writers and replays — the same
(cluster, src_pod, container, pid, window) tuple always yields the same
hex string, so duplicate batches don't multiply trace IDs.

Behavioural guarantees:
  * Events that already carry a real W3C `trace_id` are left untouched.
    The correlator never overwrites real distributed-trace context.
  * Events with `pid <= 0` (kernel threads, raw sockets, missing
    attribute) are skipped — they end up with empty virtual_trace_id.
  * Events without a resolvable `src_pod` are skipped. Without a stable
    pod identifier the bucket key would collapse across pods on the
    same node (PIDs are node-local, not cluster-unique).

Bucket key:
    "{cluster_id}|{src_pod}|{container_id}|{pid}|{window_index}"
where window_index = floor(timestamp_ms / window_ms). The container_id
is included to disambiguate multi-container pods (sidecars share the
pod's network namespace but have different container_ids).

Hash:
    sha1(bucket_key.utf-8).hexdigest()[:32]   — 16-byte hex (matches
    W3C trace_id width so downstream queries can OR the two columns
    without type-cast acrobatics).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _to_ms(ts: Any) -> int:
    """Best-effort conversion of an event timestamp to epoch milliseconds.

    Tolerated input shapes:
      * int / float — assumed to already be milliseconds (transformer
        emits `start_time_unix_nano // 1_000_000`).
      * ISO-8601 string — parsed via datetime.fromisoformat.
      * datetime — converted via .timestamp().
    Returns 0 on any failure so the caller can skip the event safely.
    """
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, datetime):
        try:
            return int(ts.timestamp() * 1000)
        except (OverflowError, OSError, ValueError):
            return 0
    if isinstance(ts, str):
        # Strip a trailing 'Z' if present — fromisoformat doesn't accept it
        # in Python < 3.11.
        norm = ts.rstrip("Z")
        try:
            return int(datetime.fromisoformat(norm).timestamp() * 1000)
        except (ValueError, TypeError):
            return 0
    return 0


def _src_pod(data: Dict[str, Any]) -> str:
    """Pull src_pod out of either the nested {src: {pod_name}} or the
    flat src_pod shape. The transformer emits the nested form but legacy
    or out-of-band producers may use the flat one.
    """
    src = data.get("src")
    if isinstance(src, dict):
        return str(src.get("pod_name") or src.get("pod") or "")
    flat = data.get("src_pod")
    return str(flat) if isinstance(flat, str) else ""


def correlate(events: Iterable[Dict[str, Any]], window_ms: int = 50) -> int:
    """Mutate eligible events in-place, attaching `data.virtual_trace_id`.

    Returns the number of events that received a virtual_trace_id (zero
    when the batch is empty or no event carried PID metadata). Events
    that already have a real `trace_id` are intentionally not counted —
    they keep their real trace.
    """
    if window_ms <= 0:
        window_ms = 50
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        data = ev.get("data")
        if not isinstance(data, dict):
            continue
        # Never overwrite a real W3C trace.
        if data.get("trace_id"):
            continue
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0:
            continue
        src_pod = _src_pod(data)
        if not src_pod:
            continue
        ts_ms = _to_ms(ev.get("timestamp"))
        if ts_ms <= 0:
            continue
        cluster = str(ev.get("cluster_id") or "")
        container_id = str(data.get("container_id") or "")
        bucket_idx = ts_ms // window_ms
        key = f"{cluster}|{src_pod}|{container_id}|{pid}|{bucket_idx}"
        buckets.setdefault(key, []).append(data)

    correlated = 0
    for key, group in buckets.items():
        # 16-byte hex matches the W3C trace_id width on l7_*_flows tables —
        # downstream queries can OR `trace_id` and `virtual_trace_id`
        # without column-width casts.
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]
        for d in group:
            d["virtual_trace_id"] = digest
            correlated += 1
    if correlated:
        logger.debug(
            "PID correlator: assigned virtual_trace_id to %d events across %d buckets (window=%dms)",
            correlated,
            len(buckets),
            window_ms,
        )
    return correlated


__all__ = ["correlate"]
