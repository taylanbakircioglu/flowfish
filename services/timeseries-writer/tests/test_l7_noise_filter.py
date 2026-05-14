"""Tests for the L7 self-monitoring (loopback) filter in
`services/timeseries-writer/app/clickhouse_client.py`.

The filter is the second layer of defense against Beyla observing
Flowfish's own gadget gRPC streams; the upstream collector and the Beyla
ConfigMap exclude_instrument list cover the same ground. A regression
here would silently re-pollute the Service Map with multi-minute
"single requests", so the filter is unit-tested independently of the
ClickHouse driver.
"""

import os
import sys
import types
import unittest

# Stub out heavyweight runtime dependencies before importing the module.
# `clickhouse_driver` is not installable on every dev environment and the
# pydantic_settings stack pulls in environment loading we don't need for a
# pure-function unit test.
_pydantic_settings = types.ModuleType('pydantic_settings')


class _BaseSettings:
    """Minimal stand-in that swallows kwargs without doing env loading."""

    def __init__(self, **_kw):
        pass


_pydantic_settings.BaseSettings = _BaseSettings
_pydantic_settings.SettingsConfigDict = dict
sys.modules.setdefault('pydantic_settings', _pydantic_settings)

_pydantic = types.ModuleType('pydantic')
_pydantic.Field = lambda **kw: kw.get('default', '')
_pydantic.ConfigDict = dict
sys.modules.setdefault('pydantic', _pydantic)

# clickhouse_driver only used at runtime by the Client class; the noise
# filter helpers don't touch it. A trivial stub is enough for import.
_ch_driver = types.ModuleType('clickhouse_driver')
_ch_driver.Client = type('Client', (), {})
_ch_errors = types.ModuleType('clickhouse_driver.errors')
_ch_errors.Error = type('Error', (Exception,), {})
sys.modules.setdefault('clickhouse_driver', _ch_driver)
sys.modules.setdefault('clickhouse_driver.errors', _ch_errors)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.clickhouse_client import (  # noqa: E402
    _filter_l7_noise,
    _is_l7_self_monitoring,
    _l7_endpoint_namespace,
)


class TestEndpointNamespaceExtraction(unittest.TestCase):
    """`_l7_endpoint_namespace` must accept both flat and nested formats
    and degrade gracefully on malformed input."""

    def test_flat_top_level(self):
        data = {'src_namespace': 'app-prod', 'dst_namespace': 'redis-prod'}
        self.assertEqual(_l7_endpoint_namespace(data, 'src'), 'app-prod')
        self.assertEqual(_l7_endpoint_namespace(data, 'dst'), 'redis-prod')

    def test_nested(self):
        data = {'src': {'namespace': 'app-prod'}, 'dst': {'namespace': 'redis-prod'}}
        self.assertEqual(_l7_endpoint_namespace(data, 'src'), 'app-prod')
        self.assertEqual(_l7_endpoint_namespace(data, 'dst'), 'redis-prod')

    def test_flat_takes_precedence_over_nested(self):
        data = {
            'src_namespace': 'app-prod',
            'src': {'namespace': 'should-be-ignored'},
        }
        self.assertEqual(_l7_endpoint_namespace(data, 'src'), 'app-prod')

    def test_missing_returns_empty(self):
        self.assertEqual(_l7_endpoint_namespace({}, 'src'), '')

    def test_non_dict_endpoint_is_safe(self):
        # Hypothetical upstream regression: src serialised as a string
        data = {'src': 'not-a-dict', 'dst': ['neither', 'is', 'this']}
        self.assertEqual(_l7_endpoint_namespace(data, 'src'), '')
        self.assertEqual(_l7_endpoint_namespace(data, 'dst'), '')

    def test_empty_string_falls_through_to_nested(self):
        # Flat is empty → fall back to nested
        data = {'src_namespace': '', 'src': {'namespace': 'real-ns'}}
        self.assertEqual(_l7_endpoint_namespace(data, 'src'), 'real-ns')


class TestIsL7SelfMonitoring(unittest.TestCase):
    """`_is_l7_self_monitoring` must catch `loopback` on either side
    irrespective of message format and is the contract the writer's
    insertion path relies on."""

    def test_flat_src_loopback(self):
        msg = {'data': {'src_namespace': 'loopback', 'dst_namespace': 'app'}}
        self.assertTrue(_is_l7_self_monitoring(msg))

    def test_flat_dst_loopback_uppercase(self):
        msg = {'data': {'src_namespace': 'app', 'dst_namespace': 'LOOPBACK'}}
        self.assertTrue(_is_l7_self_monitoring(msg))

    def test_nested_src_loopback(self):
        msg = {'data': {'src': {'namespace': 'loopback'}, 'dst': {'namespace': 'app'}}}
        self.assertTrue(_is_l7_self_monitoring(msg))

    def test_nested_dst_loopback_mixed_case(self):
        msg = {'data': {'src': {'namespace': 'app'}, 'dst': {'namespace': 'LoopBack'}}}
        self.assertTrue(_is_l7_self_monitoring(msg))

    def test_normal_traffic_passes_through(self):
        msg = {'data': {'src_namespace': 'app', 'dst_namespace': 'redis'}}
        self.assertFalse(_is_l7_self_monitoring(msg))

    def test_external_destination_is_not_noise(self):
        msg = {'data': {'src_namespace': 'app', 'dst_namespace': 'external'}}
        self.assertFalse(_is_l7_self_monitoring(msg))

    def test_unknown_namespace_is_not_noise(self):
        # `unknown` is unresolved metadata, not pod-internal traffic;
        # only `loopback` is dropped at this layer.
        msg = {'data': {'src_namespace': 'unknown', 'dst_namespace': 'app'}}
        self.assertFalse(_is_l7_self_monitoring(msg))

    def test_missing_data_is_safe(self):
        self.assertFalse(_is_l7_self_monitoring({}))

    def test_non_dict_msg_is_safe(self):
        self.assertFalse(_is_l7_self_monitoring(None))
        self.assertFalse(_is_l7_self_monitoring("not-a-dict"))
        self.assertFalse(_is_l7_self_monitoring(42))
        self.assertFalse(_is_l7_self_monitoring([{'data': {'src_namespace': 'loopback'}}]))

    def test_non_dict_data_is_safe(self):
        self.assertFalse(_is_l7_self_monitoring({'data': 'not-a-dict'}))
        self.assertFalse(_is_l7_self_monitoring({'data': None}))
        self.assertFalse(_is_l7_self_monitoring({'data': 42}))


class TestFilterL7Noise(unittest.TestCase):
    """`_filter_l7_noise` must preserve order and drop only the noise rows."""

    def test_drops_only_noise(self):
        batch = [
            {'data': {'src_namespace': 'loopback', 'dst_namespace': 'app'}},   # drop
            {'data': {'src_namespace': 'app', 'dst_namespace': 'redis'}},       # keep
            {'data': {'src': {'namespace': 'loopback'}, 'dst': {'namespace': 'app'}}},  # drop
            {'data': {'src_namespace': 'app', 'dst_namespace': 'external'}},    # keep
        ]
        kept = _filter_l7_noise(batch, 'HTTP')
        self.assertEqual(len(kept), 2)
        # Surviving rows preserve the original input order.
        self.assertEqual(kept[0]['data']['dst_namespace'], 'redis')
        self.assertEqual(kept[1]['data']['dst_namespace'], 'external')

    def test_empty_batch_is_passthrough(self):
        self.assertEqual(_filter_l7_noise([], 'HTTP'), [])

    def test_no_noise_returns_same_batch(self):
        batch = [
            {'data': {'src_namespace': 'app', 'dst_namespace': 'redis'}},
            {'data': {'src_namespace': 'app', 'dst_namespace': 'external'}},
        ]
        kept = _filter_l7_noise(batch, 'gRPC')
        self.assertEqual(len(kept), 2)

    def test_all_noise_returns_empty(self):
        batch = [
            {'data': {'src_namespace': 'loopback', 'dst_namespace': 'app'}},
            {'data': {'src': {'namespace': 'loopback'}, 'dst': {'namespace': 'app'}}},
        ]
        self.assertEqual(_filter_l7_noise(batch, 'DNS'), [])


if __name__ == '__main__':
    unittest.main()
