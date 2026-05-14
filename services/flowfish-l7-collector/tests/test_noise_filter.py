"""Tests for the upstream loopback drop in
`services/flowfish-l7-collector/app/event_transformer.py`.

This is the first of three filter layers (collector → writer → Beyla
discovery). Failures here would re-enable the original bug where Beyla
surfaces Flowfish's own gadget gRPC streams as multi-minute "single
requests" in Service Map metrics, so the helper is unit-tested
independently of the Kubernetes metadata cache.
"""

import os
import sys
import types
import unittest

# Stub the k8s_metadata module imported by event_transformer; the noise
# helpers don't touch it but `from app import k8s_metadata` runs at import
# time. The build_*_event functions are NOT covered by this file.
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
    _endpoint_namespace,
    _is_noise_event,
)


class TestEndpointNamespace(unittest.TestCase):
    def test_dict_with_namespace(self):
        self.assertEqual(_endpoint_namespace({'namespace': 'app'}), 'app')

    def test_dict_without_namespace(self):
        self.assertEqual(_endpoint_namespace({}), '')

    def test_dict_namespace_is_none(self):
        self.assertEqual(_endpoint_namespace({'namespace': None}), '')

    def test_non_dict_returns_empty(self):
        self.assertEqual(_endpoint_namespace(None), '')
        self.assertEqual(_endpoint_namespace('string'), '')
        self.assertEqual(_endpoint_namespace([{'namespace': 'app'}]), '')
        self.assertEqual(_endpoint_namespace(42), '')


class TestIsNoiseEvent(unittest.TestCase):

    def test_nested_src_loopback(self):
        ev = {'data': {'src': {'namespace': 'loopback'}, 'dst': {'namespace': 'app'}}}
        self.assertTrue(_is_noise_event(ev))

    def test_nested_dst_loopback(self):
        ev = {'data': {'src': {'namespace': 'app'}, 'dst': {'namespace': 'loopback'}}}
        self.assertTrue(_is_noise_event(ev))

    def test_nested_case_insensitive(self):
        ev = {'data': {'src': {'namespace': 'LOOPBACK'}, 'dst': {'namespace': 'app'}}}
        self.assertTrue(_is_noise_event(ev))

    def test_flat_format_fallback(self):
        # The current Beyla flow always nests src/dst, but a hypothetical
        # legacy or third-party producer could emit the flat shape.
        ev = {'data': {'src_namespace': 'loopback', 'dst_namespace': 'app'}}
        self.assertTrue(_is_noise_event(ev))

    def test_normal_pod_to_pod(self):
        ev = {'data': {'src': {'namespace': 'app'}, 'dst': {'namespace': 'redis'}}}
        self.assertFalse(_is_noise_event(ev))

    def test_external_destination_passes(self):
        ev = {'data': {'src': {'namespace': 'app'}, 'dst': {'namespace': 'external'}}}
        self.assertFalse(_is_noise_event(ev))

    def test_unknown_namespace_is_not_noise(self):
        # `unknown` indicates Beyla cache miss, not pod-internal traffic.
        ev = {'data': {'src': {'namespace': 'unknown'}, 'dst': {'namespace': 'app'}}}
        self.assertFalse(_is_noise_event(ev))

    def test_malformed_event_is_safe(self):
        self.assertFalse(_is_noise_event({}))
        self.assertFalse(_is_noise_event(None))
        self.assertFalse(_is_noise_event('not-a-dict'))
        self.assertFalse(_is_noise_event({'data': None}))
        self.assertFalse(_is_noise_event({'data': 'not-a-dict'}))
        self.assertFalse(_is_noise_event({'data': {'src': 'not-a-dict'}}))
        self.assertFalse(_is_noise_event({'data': {'src': {'namespace': 123}}}))


if __name__ == '__main__':
    unittest.main()
