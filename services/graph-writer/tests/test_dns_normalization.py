"""Tests for DNS search domain normalization in GraphBuilder."""

import os
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Stub out pydantic_settings before importing app modules
_pydantic_settings = types.ModuleType('pydantic_settings')
_pydantic_settings.BaseSettings = type('BaseSettings', (), {})

class _Field:
    def __call__(self, **kw):
        return kw.get('default', '')

_pydantic = types.ModuleType('pydantic')
_pydantic.Field = _Field()

sys.modules.setdefault('pydantic_settings', _pydantic_settings)
sys.modules.setdefault('pydantic', _pydantic)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.graph_builder import GraphBuilder


class TestNormalizeDnsName(unittest.TestCase):

    def setUp(self):
        self.gb = GraphBuilder()

    # -- Trailing dot ---------------------------------------------------------

    def test_trailing_dot_removed(self):
        self.assertEqual(self.gb._normalize_dns_name('auth.docker.io.'), 'auth.docker.io')

    def test_multiple_trailing_dots(self):
        self.assertEqual(self.gb._normalize_dns_name('host.com...'), 'host.com')

    # -- Kubernetes .cluster.local suffix ------------------------------------

    def test_cluster_local_stripped(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.cluster.local'),
            'auth.docker.io')

    def test_svc_cluster_local_stripped(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.svc.cluster.local'),
            'auth.docker.io')

    def test_ns_svc_cluster_local_stripped(self):
        """<domain>.<namespace>.svc.cluster.local → <domain>"""
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.intprod-harbor-ha.svc.cluster.local'),
            'auth.docker.io')

    def test_registry_docker_cluster_local(self):
        self.assertEqual(
            self.gb._normalize_dns_name('registry-1.docker.io.cluster.local'),
            'registry-1.docker.io')

    # -- Real K8s service DNS kept as-is -------------------------------------

    def test_real_k8s_service_kept(self):
        name = 'my-service.my-namespace.svc.cluster.local'
        self.assertEqual(self.gb._normalize_dns_name(name), name)

    def test_real_k8s_pod_dns_kept(self):
        name = '10-128-1-5.my-service.my-namespace.svc.cluster.local'
        self.assertEqual(self.gb._normalize_dns_name(name), name)

    def test_short_k8s_name_kept(self):
        """Single-label + .cluster.local is not a valid external domain."""
        name = 'kubernetes.cluster.local'
        self.assertEqual(self.gb._normalize_dns_name(name), name)

    # -- Custom search domains (DNS_SEARCH_DOMAINS env) ----------------------

    @patch.dict(os.environ, {'DNS_SEARCH_DOMAINS': 'acme.corp,internal.acme.corp'})
    def test_custom_search_domain_stripped(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.acme.corp'),
            'auth.docker.io')

    @patch.dict(os.environ, {'DNS_SEARCH_DOMAINS': 'acme.corp,internal.acme.corp'})
    def test_custom_search_domain_internal_stripped(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.internal.acme.corp'),
            'auth.docker.io')

    @patch.dict(os.environ, {'DNS_SEARCH_DOMAINS': 'acme.corp'})
    def test_real_internal_domain_not_stripped(self):
        """my-db.acme.corp is a real domain, not an artifact (base has no TLD)."""
        self.assertEqual(
            self.gb._normalize_dns_name('my-db.acme.corp'),
            'my-db.acme.corp')

    @patch.dict(os.environ, {'DNS_SEARCH_DOMAINS': ''})
    def test_empty_env_no_custom_stripping(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.acme.corp'),
            'auth.docker.io.acme.corp')

    # -- Multi-level TLDs ---------------------------------------------------

    def test_com_tr_domain_cluster_local(self):
        self.assertEqual(
            self.gb._normalize_dns_name('api.example.com.tr.cluster.local'),
            'api.example.com.tr')

    @patch.dict(os.environ, {'DNS_SEARCH_DOMAINS': 'myorg.local'})
    def test_com_tr_domain_custom(self):
        self.assertEqual(
            self.gb._normalize_dns_name('api.example.com.tr.myorg.local'),
            'api.example.com.tr')

    # -- Edge cases ----------------------------------------------------------

    def test_empty_string(self):
        self.assertEqual(self.gb._normalize_dns_name(''), '')

    def test_none_returns_none(self):
        self.assertIsNone(self.gb._normalize_dns_name(None))

    def test_plain_domain_unchanged(self):
        self.assertEqual(self.gb._normalize_dns_name('google.com'), 'google.com')

    def test_subdomain_unchanged(self):
        self.assertEqual(
            self.gb._normalize_dns_name('api.github.com'),
            'api.github.com')

    def test_ip_address_unchanged(self):
        self.assertEqual(self.gb._normalize_dns_name('10.128.0.1'), '10.128.0.1')

    def test_no_dots_unchanged(self):
        self.assertEqual(self.gb._normalize_dns_name('localhost'), 'localhost')

    # -- Combined: trailing dot + K8s suffix ---------------------------------

    def test_trailing_dot_and_cluster_local(self):
        self.assertEqual(
            self.gb._normalize_dns_name('auth.docker.io.cluster.local.'),
            'auth.docker.io')

    # -- process_dns_query integration smoke test ----------------------------

    def test_process_dns_query_normalizes(self):
        event = {
            'analysis_id': 'test-1',
            'cluster_id': 'c1',
            'data': {
                'namespace': 'mynamespace',
                'pod_name': 'my-pod',
                'query_name': 'registry-1.docker.io.cluster.local',
                'query_type': 'A',
                'response_ips': ['52.1.2.3'],
            }
        }
        vertices, _ = self.gb.process_dns_query(event)
        dst_vertex = next((v for v in vertices if v['tag'] == 'ExternalEndpoint'), None)
        self.assertIsNotNone(dst_vertex)
        self.assertEqual(dst_vertex['properties']['name'], 'registry-1.docker.io')
        self.assertEqual(dst_vertex['properties']['dns_name'], 'registry-1.docker.io')

    def test_process_dns_query_nxdomain_then_noerror_gets_ip(self):
        """NXDOMAIN artifact creates vertex first, NOERROR should update with resolved IP."""
        gb = GraphBuilder()

        nxdomain_event = {
            'analysis_id': 'test-1', 'cluster_id': 'c1',
            'data': {
                'namespace': 'ns', 'pod_name': 'pod-a',
                'query_name': 'api.github.com.cluster.local',
                'query_type': 'A',
            }
        }
        v1, _ = gb.process_dns_query(nxdomain_event)
        dst1 = next((v for v in v1 if v['tag'] == 'ExternalEndpoint'), None)
        self.assertIsNotNone(dst1, "NXDOMAIN should still create vertex")
        self.assertEqual(dst1['properties']['ip'], '')
        self.assertEqual(dst1['properties']['network_type'], '')

        noerror_event = {
            'analysis_id': 'test-1', 'cluster_id': 'c1',
            'data': {
                'namespace': 'ns', 'pod_name': 'pod-a',
                'query_name': 'api.github.com',
                'query_type': 'A',
                'response_ips': ['140.82.121.6'],
            }
        }
        v2, _ = gb.process_dns_query(noerror_event)
        dst2 = next((v for v in v2 if v['tag'] == 'ExternalEndpoint'), None)
        self.assertIsNotNone(dst2, "NOERROR should re-emit vertex with resolved IP")
        self.assertEqual(dst2['properties']['ip'], '140.82.121.6')
        self.assertNotEqual(dst2['properties']['network_type'], '')
        self.assertEqual(dst2['properties']['name'], 'api.github.com')

    def test_process_dns_query_skips_real_k8s(self):
        event = {
            'analysis_id': 'test-1',
            'cluster_id': 'c1',
            'data': {
                'namespace': 'mynamespace',
                'pod_name': 'my-pod',
                'query_name': 'redis.default.svc.cluster.local',
            }
        }
        vertices, _ = self.gb.process_dns_query(event)
        self.assertEqual(vertices, [])

    # -- process_sni_event integration smoke test ----------------------------

    def test_process_sni_normalizes(self):
        event = {
            'analysis_id': 'test-1',
            'cluster_id': 'c1',
            'data': {
                'namespace': 'mynamespace',
                'pod_name': 'my-pod',
                'sni_name': 'api.github.com.',
                'dst_ip': '1.2.3.4',
            }
        }
        vertices, _ = self.gb.process_sni_event(event)
        dst = next((v for v in vertices if v['tag'] == 'ExternalEndpoint'), None)
        self.assertIsNotNone(dst)
        self.assertEqual(dst['properties']['name'], 'api.github.com')


class TestHasKnownTld(unittest.TestCase):

    def setUp(self):
        self.gb = GraphBuilder()

    def test_known_single_tld(self):
        self.assertTrue(self.gb._has_known_tld('auth.docker.io'))
        self.assertTrue(self.gb._has_known_tld('google.com'))
        self.assertTrue(self.gb._has_known_tld('example.org'))
        self.assertTrue(self.gb._has_known_tld('myapp.dev'))

    def test_known_multi_level_tld(self):
        self.assertTrue(self.gb._has_known_tld('example.com.tr'))
        self.assertTrue(self.gb._has_known_tld('bbc.co.uk'))
        self.assertTrue(self.gb._has_known_tld('example.com.au'))

    def test_unknown_tld(self):
        self.assertFalse(self.gb._has_known_tld('my-service.mynamespace'))
        self.assertFalse(self.gb._has_known_tld('something.fakeextension'))

    def test_no_dot(self):
        self.assertFalse(self.gb._has_known_tld('localhost'))
        self.assertFalse(self.gb._has_known_tld(''))

    def test_single_label(self):
        self.assertFalse(self.gb._has_known_tld('com'))


if __name__ == '__main__':
    unittest.main()
