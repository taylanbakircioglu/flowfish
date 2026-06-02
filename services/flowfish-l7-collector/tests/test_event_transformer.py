"""Tests for HTTP path / method extraction in
`services/flowfish-l7-collector/app/event_transformer.py` (Audit v4).

Background: until v2.7.0 the transformer extracted HTTP path only from
`url.path` / `http.route`. Both attributes exist only on SERVER spans per
OpenTelemetry HTTP semantic conventions, so every CLIENT span (outgoing
HTTP call) silently fell back to `/`. This left the Service Map and
Integration Hub displaying `/` for every external dependency even though
Beyla's own Prometheus exporter showed the correct routes — different
export paths, different attribute handling.

These tests pin the new extraction order and the relative-path guard
that protects Neo4j edges from being poisoned by malformed `url.full`
values.
"""

import os
import sys
import types
import unittest

# Stub the k8s_metadata module imported by event_transformer; the path
# helper doesn't touch it but the `from app import k8s_metadata` line
# runs at module import.
_app_pkg = types.ModuleType('app')
_app_pkg.__path__ = ['app']
sys.modules.setdefault('app', _app_pkg)

_k8s = types.ModuleType('app.k8s_metadata')
for _fn in (
    'resolve_ip', 'resolve_by_name', 'classify_ip_network_type',
    'get_namespace_for_network_type', 'resolve_hostname',
):
    setattr(_k8s, _fn, lambda *a, **kw: None)
sys.modules.setdefault('app.k8s_metadata', _k8s)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.event_transformer import (  # noqa: E402
    _extract_http_path,
    _transform_single_span,
)


# ---------------------------------------------------------------------------
# Minimal protobuf-style fakes
# ---------------------------------------------------------------------------
# event_transformer._get_attr expects attribute objects shaped like
# OTLP protobuf KeyValue messages: `attr.key` (string) and `attr.value`
# (AnyValue) where `value.HasField("string_value")` is checked before
# `value.string_value`. We don't import the full opentelemetry_proto
# package here — that's a heavyweight dependency the unit tests should
# not require — so we hand-roll the smallest object graph that satisfies
# `_get_attr`'s string-value path.
class _FakeValue:
    def __init__(self, string_value):
        self.string_value = string_value

    def HasField(self, name):  # noqa: N802 — protobuf API name
        return name == 'string_value'


class _FakeAttr:
    def __init__(self, key, string_value):
        self.key = key
        self.value = _FakeValue(string_value)


def _attrs(**kwargs):
    """Helper: build an attribute list from key=value pairs."""
    return [_FakeAttr(k.replace('__', '.'), v) for k, v in kwargs.items()]


# ---------------------------------------------------------------------------
# _extract_http_path direct tests
# ---------------------------------------------------------------------------
class TestExtractHttpPath(unittest.TestCase):
    """Pins the lookup order and relative-path guard documented on
    `_extract_http_path`.
    """

    # 1. SERVER span — OTel stable `url.path` wins
    def test_server_url_path(self):
        attrs = _attrs(url__path='/api/v1/users')
        self.assertEqual(_extract_http_path(attrs), '/api/v1/users')

    # 2. SERVER span — `http.route` used when only it is present
    def test_server_http_route(self):
        attrs = _attrs(http__route='/api/v1/users/{id}')
        self.assertEqual(_extract_http_path(attrs), '/api/v1/users/{id}')

    # 2b. `url.path` beats `http.route` when both are present (raw over
    # template — operator typically wants the actual path, with route
    # available as fallback for templated services).
    def test_url_path_beats_http_route(self):
        attrs = _attrs(
            url__path='/api/v1/users/42',
            http__route='/api/v1/users/{id}',
        )
        self.assertEqual(_extract_http_path(attrs), '/api/v1/users/42')

    # 3. CLIENT span — OTel stable `url.full` parsed for path component.
    # This is the regression class fixed in v2.7.0 (Audit v4): every
    # outbound HTTP call landed here and produced `/` before the fix.
    def test_client_url_full_query_stripped(self):
        attrs = _attrs(url__full='http://elastic:9200/_bulk?refresh=true')
        self.assertEqual(_extract_http_path(attrs), '/_bulk')

    # 4. CLIENT span — legacy `http.url` (OTel < 1.21) parsed for path
    def test_client_legacy_http_url(self):
        attrs = _attrs(http__url='https://api.example.com/v2/data')
        self.assertEqual(_extract_http_path(attrs), '/v2/data')

    # 5. Legacy `http.target = "path?query"` — strip query
    def test_legacy_http_target_query_stripped(self):
        attrs = _attrs(http__target='/users?page=1')
        self.assertEqual(_extract_http_path(attrs), '/users')

    # 6. No HTTP attributes at all → `"/"` fallback (preserves
    # historical shape for spans that genuinely have no path).
    def test_no_attributes_fallback(self):
        self.assertEqual(_extract_http_path([]), '/')

    # 9. Malformed `url.full` — relative-path guard kicks in.
    # urlsplit('garbage').path returns 'garbage' (treated as a bare
    # relative URL). Without the guard the transformer would poison
    # Neo4j edges with garbage path values.
    def test_malformed_url_full_falls_back(self):
        attrs = _attrs(url__full='garbage-not-a-url')
        self.assertEqual(_extract_http_path(attrs), '/')

    # 10. `url.full` with a non-HTTP scheme — still produces a valid
    # path. The transformer is HTTP-aware but `_extract_http_path`
    # itself is scheme-agnostic so the caller's filtering decides
    # whether the event ends up labelled HTTP.
    def test_url_full_ftp_scheme(self):
        attrs = _attrs(url__full='ftp://files.example/data.bin')
        self.assertEqual(_extract_http_path(attrs), '/data.bin')

    # 11. Fragment stripped automatically by urlsplit
    def test_url_full_fragment_stripped(self):
        attrs = _attrs(url__full='https://example.com/path#section')
        self.assertEqual(_extract_http_path(attrs), '/path')

    # Edge case: empty `url.path` value — should fall through to
    # subsequent attributes rather than returning ''.
    def test_empty_url_path_falls_through(self):
        attrs = _attrs(
            url__path='',                                  # falsy
            url__full='http://example.com/api/v1/health',  # winner
        )
        self.assertEqual(_extract_http_path(attrs), '/api/v1/health')

    # Edge case: `url.full = "http://host"` (no path) → relative-path
    # guard rejects empty path, falls through to "/"
    def test_url_full_no_path_falls_back(self):
        attrs = _attrs(url__full='http://host-only')
        self.assertEqual(_extract_http_path(attrs), '/')


# ---------------------------------------------------------------------------
# _transform_single_span — HTTP branch trigger coverage
# ---------------------------------------------------------------------------
# These tests verify the v2.7.0 branch-widening change: spans carrying
# only `url.full` (CLIENT pattern) used to be dropped because the
# selector checked `url.path` alone. The fix added `url.full`,
# `http.url`, `http.target` as alternate triggers.
class _FakeSpan:
    """Minimal span shape consumed by `_transform_single_span`."""

    def __init__(self, attributes, span_kind=3):  # 3 = CLIENT
        self.attributes = attributes
        self.kind = span_kind
        self.trace_id = b''
        self.span_id = b''
        self.parent_span_id = b''
        self.name = ''
        self.start_time_unix_nano = 1_000_000_000  # 1 sec since epoch
        self.end_time_unix_nano = 1_010_000_000    # +10 ms


class TestTransformSingleSpanBranching(unittest.TestCase):
    """gRPC and DNS branches must continue to win when their tell-tale
    attributes are present; the HTTP branch is now wider but still
    last in priority order.
    """

    # 12. gRPC span with both `rpc.service` AND `url.full` — gRPC branch
    # wins (rpc.* is checked first). Without this ordering, a Beyla
    # build that ever attached `url.full` to a gRPC span would
    # misclassify the event as HTTP and lose service/method metadata.
    def test_grpc_with_url_full_takes_grpc_branch(self):
        attrs = _attrs(
            rpc__service='helloworld.Greeter',
            rpc__method='SayHello',
            url__full='http://example.com/grpc',
        )
        ev = _transform_single_span(_FakeSpan(attrs), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['event_type'], 'l7_grpc_flow')

    # DNS branch wins over HTTP for the same reason
    def test_dns_with_url_path_takes_dns_branch(self):
        attrs = _attrs(
            dns__question__name='example.com',
            url__path='/should-be-ignored',
        )
        ev = _transform_single_span(_FakeSpan(attrs, span_kind=3), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['event_type'], 'l7_dns_flow')

    # CLIENT span with only `url.full` triggers HTTP branch
    # (regression fix — used to be dropped because `url.path` was the
    # only HTTP trigger checked).
    def test_client_url_full_only_triggers_http(self):
        attrs = _attrs(url__full='http://elastic:9200/_bulk')
        ev = _transform_single_span(_FakeSpan(attrs), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['event_type'], 'l7_http_flow')
        self.assertEqual(ev['data']['path'], '/_bulk')

    # Legacy `http.url` likewise triggers HTTP branch
    def test_legacy_http_url_triggers_http(self):
        attrs = _attrs(http__url='https://api.example.com/v1/things')
        ev = _transform_single_span(_FakeSpan(attrs), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['event_type'], 'l7_http_flow')
        self.assertEqual(ev['data']['path'], '/v1/things')

    # 7. SERVER span method — stable `http.request.method` wins
    def test_http_method_stable(self):
        attrs = _attrs(
            http__request__method='POST',
            url__path='/login',
        )
        ev = _transform_single_span(_FakeSpan(attrs, span_kind=2), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['data']['method'], 'POST')

    # 8. Method legacy fallback — only `http.method` available
    def test_http_method_legacy_fallback(self):
        attrs = _attrs(
            http__method='GET',
            url__path='/legacy',
        )
        ev = _transform_single_span(_FakeSpan(attrs, span_kind=2), resource_attrs=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev['data']['method'], 'GET')

    # Span with no HTTP / gRPC / DNS attrs at all → dropped
    def test_unknown_span_dropped(self):
        attrs = _attrs(custom__attr='value')
        ev = _transform_single_span(_FakeSpan(attrs), resource_attrs=[])
        self.assertIsNone(ev)


if __name__ == '__main__':
    unittest.main()
