"""Tests for the PID-temporal `virtual_trace_id` correlator
(`services/timeseries-writer/app/virtual_trace_correlator.py`).

The correlator is the only piece of code that *creates* a synthetic
trace identifier when W3C `trace_id` is absent (Phase 4D). A regression
here would either silently drop Phase 4 spans (no virtual_trace_id
attached) or, worse, collide unrelated requests under the same id —
both produce wrong waterfalls in the Trace Explorer. Pure-function +
no I/O so unit tests are cheap and stable.
"""

from __future__ import annotations

import os
import sys
import unittest

# Make the writer's `app` package importable without spinning up the rest
# of the runtime (no env vars, no clickhouse_driver, no pydantic).
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from app import virtual_trace_correlator as vtc  # noqa: E402


def _evt(
    *,
    ts: int = 1_700_000_000_000,
    cluster: str = "c1",
    pod: str = "ns/svc-a-pod1",
    pid: int = 1234,
    container_id: str = "abc123",
    trace_id: str = "",
) -> dict:
    """Build a minimal event matching the shape produced by
    `flowfish-l7-collector` after `event_transformer`.
    """
    return {
        "timestamp": ts,
        "cluster_id": cluster,
        "data": {
            "src": {"pod_name": pod},
            "pid": pid,
            "container_id": container_id,
            "trace_id": trace_id,
        },
    }


class CorrelateTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Happy paths
    # ------------------------------------------------------------------
    def test_two_events_same_window_get_same_id(self):
        e1 = _evt(ts=1_700_000_000_000, pid=42)
        e2 = _evt(ts=1_700_000_000_020, pid=42)  # +20ms < 50ms window
        n = vtc.correlate([e1, e2], window_ms=50)
        self.assertEqual(n, 2)
        self.assertNotEqual(e1["data"]["virtual_trace_id"], "")
        self.assertEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    def test_id_is_16_byte_hex(self):
        e = _evt()
        vtc.correlate([e])
        vt = e["data"]["virtual_trace_id"]
        self.assertEqual(len(vt), 32, "16-byte hex matches W3C trace_id width")
        # All hex chars
        int(vt, 16)  # raises if non-hex

    def test_id_is_deterministic_across_runs(self):
        e1 = _evt(ts=1_700_000_000_000, pid=42)
        e2 = _evt(ts=1_700_000_000_000, pid=42)
        vtc.correlate([e1])
        vtc.correlate([e2])
        self.assertEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    # ------------------------------------------------------------------
    # Boundary / negative cases
    # ------------------------------------------------------------------
    def test_different_window_yields_different_id(self):
        e1 = _evt(ts=1_700_000_000_000, pid=42)
        e2 = _evt(ts=1_700_000_000_060, pid=42)  # +60ms > 50ms window
        vtc.correlate([e1, e2], window_ms=50)
        self.assertNotEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    def test_different_pid_yields_different_id(self):
        e1 = _evt(pid=100)
        e2 = _evt(pid=101)
        vtc.correlate([e1, e2])
        self.assertNotEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    def test_different_pod_yields_different_id(self):
        e1 = _evt(pod="ns/svc-a-pod1")
        e2 = _evt(pod="ns/svc-a-pod2")
        vtc.correlate([e1, e2])
        self.assertNotEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    def test_different_cluster_yields_different_id(self):
        # Same PID + pod across clusters — must NOT collide.
        e1 = _evt(cluster="c1")
        e2 = _evt(cluster="c2")
        vtc.correlate([e1, e2])
        self.assertNotEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )

    # ------------------------------------------------------------------
    # Skip semantics
    # ------------------------------------------------------------------
    def test_real_trace_id_preserved(self):
        e = _evt(trace_id="abcdef1234567890abcdef1234567890")
        n = vtc.correlate([e])
        self.assertEqual(n, 0)
        self.assertNotIn("virtual_trace_id", e["data"])
        self.assertEqual(e["data"]["trace_id"], "abcdef1234567890abcdef1234567890")

    def test_zero_pid_skipped(self):
        e = _evt(pid=0)
        n = vtc.correlate([e])
        self.assertEqual(n, 0)
        self.assertNotIn("virtual_trace_id", e["data"])

    def test_negative_pid_skipped(self):
        e = _evt(pid=-1)
        n = vtc.correlate([e])
        self.assertEqual(n, 0)

    def test_missing_src_pod_skipped(self):
        e = _evt(pod="")
        n = vtc.correlate([e])
        self.assertEqual(n, 0)

    def test_missing_timestamp_skipped(self):
        e = _evt()
        e["timestamp"] = 0
        n = vtc.correlate([e])
        self.assertEqual(n, 0)

    def test_invalid_pid_string_skipped(self):
        e = _evt()
        e["data"]["pid"] = "not-a-number"
        n = vtc.correlate([e])
        self.assertEqual(n, 0)

    def test_non_dict_event_ignored(self):
        # Passing a non-dict shouldn't throw; the correlator must be
        # defensive against malformed batches from RabbitMQ.
        n = vtc.correlate([None, "garbage", 42, _evt()])
        self.assertEqual(n, 1)

    def test_empty_iterable(self):
        self.assertEqual(vtc.correlate([]), 0)
        self.assertEqual(vtc.correlate(None), 0)

    # ------------------------------------------------------------------
    # _to_ms tolerance
    # ------------------------------------------------------------------
    def test_to_ms_int(self):
        self.assertEqual(vtc._to_ms(123456789), 123456789)

    def test_to_ms_iso_string(self):
        ms = vtc._to_ms("2026-04-29T12:00:00")
        self.assertGreater(ms, 0)

    def test_to_ms_iso_string_with_z(self):
        # `Z` suffix tolerated even on Python <3.11.
        ms = vtc._to_ms("2026-04-29T12:00:00Z")
        self.assertGreater(ms, 0)

    def test_to_ms_invalid_string_returns_zero(self):
        self.assertEqual(vtc._to_ms("not a date"), 0)

    def test_to_ms_none_returns_zero(self):
        self.assertEqual(vtc._to_ms(None), 0)

    # ------------------------------------------------------------------
    # Container-id disambiguation (sidecar safety)
    # ------------------------------------------------------------------
    def test_different_container_id_yields_different_id(self):
        # Two containers sharing pod + PID-namespace shouldn't collide.
        # In practice PID namespaces are per-container so this almost
        # never triggers, but the bucket key honours container_id
        # defensively in case a future Beyla version reports host PIDs.
        e1 = _evt(container_id="cont-a")
        e2 = _evt(container_id="cont-b")
        vtc.correlate([e1, e2])
        self.assertNotEqual(
            e1["data"]["virtual_trace_id"], e2["data"]["virtual_trace_id"]
        )


if __name__ == "__main__":
    unittest.main()
