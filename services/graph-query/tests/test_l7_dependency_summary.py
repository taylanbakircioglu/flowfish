"""Unit tests for ``GraphQueryEngine.get_l7_dependency_summary``.

These tests cover the Integration Hub L7 Audit v3 filter/aggregation
behaviour plus the Audit v4 per-path edge accounting:

1. Annotation exact match
2. Annotation fnmatch glob
3. Label key + value match
4. Multi-cluster — same workload name in two clusters appears as two nodes
5. Empty / malformed JSON annotations don't break the filter sweep
6. ``include_metadata=False`` strips labels/annotations/owner_kind from
   the response but still allows the engine to filter on them
7. ``filter_noise_annotations`` strips infrastructure annotations only
   when opted in
8. (v2.7.0 / Audit v4) Per-path edges between the same (src, dst) MUST
   count as ONE outbound peer — not N. The Neo4j storage layer now
   creates a separate L7_COMMUNICATES_WITH edge per (method, path);
   bucketing peers in a set inside the summary aggregator keeps
   dependency counts stable for the UI.

The tests run against the real engine code with ``execute_query`` swapped
out for a stub fixture (``mock_engine``) — no Neo4j required.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def _row(
    src_id: str,
    dst_id: str,
    *,
    src_name: str = "",
    src_namespace: str = "",
    src_cluster: str = "",
    dst_name: str = "",
    dst_namespace: str = "",
    dst_cluster: str = "",
    src_labels: Any = None,
    src_annotations: Any = None,
    src_owner_kind: str = "Deployment",
    dst_labels: Any = None,
    dst_annotations: Any = None,
    dst_owner_kind: str = "Deployment",
    request_count: int = 1,
    error_count: int = 0,
    protocol: str = "HTTP",
) -> Dict[str, Any]:
    """Build a Neo4j-shaped row matching the Cypher RETURN clause."""
    return {
        "src_id": src_id,
        "src_name": src_name or src_id,
        "src_namespace": src_namespace,
        "src_cluster": src_cluster,
        "dst_id": dst_id,
        "dst_name": dst_name or dst_id,
        "dst_namespace": dst_namespace,
        "dst_cluster": dst_cluster,
        "request_count": request_count,
        "error_count": error_count,
        "protocol": protocol,
        "src_labels": src_labels,
        "src_annotations": src_annotations,
        "src_owner_kind": src_owner_kind,
        "dst_labels": dst_labels,
        "dst_annotations": dst_annotations,
        "dst_owner_kind": dst_owner_kind,
    }


def _ids(workloads: List[Dict[str, Any]]) -> List[str]:
    return [w["id"] for w in workloads]


# ---------------------------------------------------------------------------
# 1. Annotation exact match — only workloads carrying the exact key/value
#    end up as ``is_matched=True``; neighbours are still returned with the
#    flag set to False so the operator keeps dependency context.
# ---------------------------------------------------------------------------


def test_annotation_exact_match_emits_is_matched_flag(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-api", "w-db",
            src_name="api", dst_name="db",
            src_namespace="test", dst_namespace="test",
            src_annotations=json.dumps({"example.com/project": "NBA"}),
            dst_annotations=json.dumps({"example.com/project": "OTHER"}),
        ),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        annotation_key="example.com/project",
        annotation_value="NBA",
    )

    assert resp["success"] is True
    matched = {w["id"]: w["is_matched"] for w in resp["workloads"]}
    assert matched == {"w-api": True, "w-db": False}
    assert resp["summary"]["total_matched"] == 1
    assert resp["summary"]["total_workloads"] == 2


# ---------------------------------------------------------------------------
# 2. Annotation fnmatch glob — ``*NBA*`` matches "platform/NBA-payments"
#    but not unrelated workloads.
# ---------------------------------------------------------------------------


def test_annotation_value_glob_match(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-nba", "w-other",
            src_name="nba-api", dst_name="other-api",
            src_annotations=json.dumps({"example.com/project": "platform/NBA-payments"}),
            dst_annotations=json.dumps({"example.com/project": "platform/CRM-core"}),
        ),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        annotation_key="example.com/project",
        annotation_value="*NBA*",
    )

    matched_ids = {w["id"] for w in resp["workloads"] if w.get("is_matched")}
    assert matched_ids == {"w-nba"}
    # Neighbour still in response so the operator can see the edge.
    assert _ids(resp["workloads"]) == ["w-nba", "w-other"]


# ---------------------------------------------------------------------------
# 3. Label key + value match — uses the JSON-encoded labels column the
#    graph-writer persists.
# ---------------------------------------------------------------------------


def test_label_key_value_match(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-frontend", "w-backend",
            src_name="frontend", dst_name="backend",
            src_labels=json.dumps({"app": "shop"}),
            dst_labels=json.dumps({"app": "billing"}),
        ),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        label_key="app",
        label_value="shop",
    )

    matched_ids = {w["id"] for w in resp["workloads"] if w.get("is_matched")}
    assert matched_ids == {"w-frontend"}
    # Neighbour kept for dependency context.
    assert {w["id"] for w in resp["workloads"]} == {"w-frontend", "w-backend"}


# ---------------------------------------------------------------------------
# 4. Multi-cluster — same workload name in two clusters MUST produce two
#    distinct nodes (cluster is part of the deduplication tuple).
# ---------------------------------------------------------------------------


def test_multi_cluster_same_name_split_by_cluster(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-east-payments", "w-east-db",
            src_name="payments", dst_name="db",
            src_namespace="shop", dst_namespace="shop",
            src_cluster="east", dst_cluster="east",
        ),
        _row(
            "w-west-payments", "w-west-db",
            src_name="payments", dst_name="db",
            src_namespace="shop", dst_namespace="shop",
            src_cluster="west", dst_cluster="west",
        ),
    ])

    resp = engine.get_l7_dependency_summary(analysis_id="A1")

    payments = [w for w in resp["workloads"] if w["name"] == "payments"]
    assert len(payments) == 2, "same-name workloads from different clusters must not collapse"
    clusters = {w["cluster"] for w in payments}
    assert clusters == {"east", "west"}


# ---------------------------------------------------------------------------
# 5. Empty / malformed annotation JSON — one corrupt row must not poison
#    the filter sweep for the rest of the namespace.
# ---------------------------------------------------------------------------


def test_malformed_annotations_do_not_break_filter(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-clean", "w-broken",
            src_name="clean", dst_name="broken",
            src_annotations=json.dumps({"example.com/project": "NBA"}),
            dst_annotations="{not-json",  # malformed
        ),
        _row(
            "w-empty", "w-clean",
            src_name="empty", dst_name="clean",
            src_annotations=None,  # missing
            dst_annotations=json.dumps({"example.com/project": "NBA"}),
        ),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        annotation_key="example.com/project",
        annotation_value="NBA",
    )

    assert resp["success"] is True
    matched_ids = {w["id"] for w in resp["workloads"] if w.get("is_matched")}
    # ``w-clean`` matches; ``w-broken`` and ``w-empty`` are neighbours kept
    # in the response with is_matched=False but parsed without raising.
    assert matched_ids == {"w-clean"}
    annotations_by_id = {w["id"]: w["annotations"] for w in resp["workloads"]}
    assert annotations_by_id["w-broken"] == {}
    assert annotations_by_id["w-empty"] == {}


# ---------------------------------------------------------------------------
# 6. ``include_metadata=False`` strips labels/annotations/owner_kind from
#    the response but the engine still filters on the underlying data.
# ---------------------------------------------------------------------------


def test_include_metadata_false_still_supports_server_side_filter(mock_engine):
    engine, set_rows = mock_engine
    set_rows([
        _row(
            "w-api", "w-db",
            src_name="api", dst_name="db",
            src_annotations=json.dumps({"example.com/project": "NBA"}),
            dst_annotations=json.dumps({"example.com/project": "OTHER"}),
        ),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        include_metadata=False,
        annotation_key="example.com/project",
        annotation_value="NBA",
    )

    matched_ids = {w["id"] for w in resp["workloads"] if w.get("is_matched")}
    assert matched_ids == {"w-api"}, "filter still runs even when metadata is hidden"
    for w in resp["workloads"]:
        assert "labels" not in w
        assert "annotations" not in w
        assert "owner_kind" not in w


# ---------------------------------------------------------------------------
# 7. ``filter_noise_annotations`` — only opt-in stripping; defaults to off.
# ---------------------------------------------------------------------------


def test_filter_noise_annotations_is_opt_in(mock_engine):
    engine, set_rows = mock_engine
    noisy = {
        "kubectl.kubernetes.io/last-applied-configuration": "{...}",
        "kubernetes.io/psp": "restricted",
        "example.com/project": "NBA",
    }
    set_rows([
        _row(
            "w-api", "w-db",
            src_name="api", dst_name="db",
            src_annotations=json.dumps(noisy),
            dst_annotations=json.dumps(noisy),
        ),
    ])

    # Default off → noise still present.
    resp_off = engine.get_l7_dependency_summary(analysis_id="A1")
    api_off = next(w for w in resp_off["workloads"] if w["id"] == "w-api")
    assert "kubectl.kubernetes.io/last-applied-configuration" in api_off["annotations"]
    assert "kubernetes.io/psp" in api_off["annotations"]
    assert api_off["annotations"]["example.com/project"] == "NBA"

    # Opt-in → noise stripped, operator-visible keys preserved.
    resp_on = engine.get_l7_dependency_summary(
        analysis_id="A1",
        filter_noise_annotations=True,
    )
    api_on = next(w for w in resp_on["workloads"] if w["id"] == "w-api")
    assert "kubectl.kubernetes.io/last-applied-configuration" not in api_on["annotations"]
    assert "kubernetes.io/psp" not in api_on["annotations"]
    assert api_on["annotations"] == {"example.com/project": "NBA"}


# ---------------------------------------------------------------------------
# 8. (v2.7.0 / Audit v4) Per-path edge accounting — five rows representing
#    one (src, dst) pair with five distinct (method, path) endpoints must
#    still produce outbound_count = 1 (one peer) and inbound_count = 1
#    (one caller). The request_count totals add up across edges.
#
#    Before the fix, this Cypher RETURN shape would inflate outbound_count
#    to 5 because the aggregator incremented a per-edge counter. UI consumers
#    would then report "5 dependencies" for a single downstream service.
# ---------------------------------------------------------------------------


def test_per_path_edges_collapse_to_single_peer_count(mock_engine):
    engine, set_rows = mock_engine
    # Same (src, dst) pair, five different endpoints — Neo4j now stores
    # one edge per (method, path), so the engine receives 5 rows.
    set_rows([
        _row("w-api", "w-db", src_name="api", dst_name="db",
             request_count=10, protocol="HTTP"),
        _row("w-api", "w-db", src_name="api", dst_name="db",
             request_count=20, protocol="HTTP"),
        _row("w-api", "w-db", src_name="api", dst_name="db",
             request_count=30, protocol="HTTP"),
        _row("w-api", "w-db", src_name="api", dst_name="db",
             request_count=40, protocol="HTTP"),
        _row("w-api", "w-db", src_name="api", dst_name="db",
             request_count=50, protocol="HTTP"),
    ])

    resp = engine.get_l7_dependency_summary(analysis_id="A1")

    api = next(w for w in resp["workloads"] if w["id"] == "w-api")
    db = next(w for w in resp["workloads"] if w["id"] == "w-db")

    # Distinct peer counting: api has ONE downstream (db), db has ONE caller (api).
    assert api["outbound_count"] == 1, "5 per-path edges to the same destination = 1 peer"
    assert api["inbound_count"] == 0
    assert db["inbound_count"] == 1, "5 per-path edges from the same caller = 1 peer"
    assert db["outbound_count"] == 0

    # Request counts still aggregate across all edges.
    assert api["request_count"] == 150
    assert db["request_count"] == 150


def test_per_path_edges_distinct_per_protocol(mock_engine):
    """Same (src, dst) pair with HTTP and gRPC traffic counts as TWO
    outbound peers — protocol is part of the peer identity in the
    distinct-set bucketing.
    """
    engine, set_rows = mock_engine
    set_rows([
        _row("w-api", "w-svc", src_name="api", dst_name="svc",
             request_count=5, protocol="HTTP"),
        _row("w-api", "w-svc", src_name="api", dst_name="svc",
             request_count=15, protocol="HTTP"),
        _row("w-api", "w-svc", src_name="api", dst_name="svc",
             request_count=7, protocol="GRPC"),
    ])

    resp = engine.get_l7_dependency_summary(analysis_id="A1")

    api = next(w for w in resp["workloads"] if w["id"] == "w-api")
    # Same destination, two protocols — counts as two peer relationships.
    assert api["outbound_count"] == 2


def test_per_path_edges_with_filter_active_keeps_peer_semantics(mock_engine):
    """The filter sweep that emits ``is_matched`` must not double-count
    matched workloads when per-path edges fan out.
    """
    engine, set_rows = mock_engine
    # Three per-path edges from the matched workload to the same dst.
    matched_ann = json.dumps({"example.com/project": "NBA"})
    other_ann = json.dumps({"example.com/project": "OTHER"})
    set_rows([
        _row("w-nba", "w-db", src_name="nba", dst_name="db",
             src_annotations=matched_ann, dst_annotations=other_ann,
             request_count=5),
        _row("w-nba", "w-db", src_name="nba", dst_name="db",
             src_annotations=matched_ann, dst_annotations=other_ann,
             request_count=10),
        _row("w-nba", "w-db", src_name="nba", dst_name="db",
             src_annotations=matched_ann, dst_annotations=other_ann,
             request_count=15),
    ])

    resp = engine.get_l7_dependency_summary(
        analysis_id="A1",
        annotation_key="example.com/project",
        annotation_value="NBA",
    )

    assert resp["summary"]["total_matched"] == 1
    assert resp["summary"]["total_workloads"] == 2
    nba = next(w for w in resp["workloads"] if w["id"] == "w-nba")
    assert nba["outbound_count"] == 1  # ONE downstream peer
    assert nba["request_count"] == 30  # sum across paths
