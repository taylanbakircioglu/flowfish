"""Client for pulling events from flowfish-l7-collector.

Supports two modes:
- K8s API service proxy (remote clusters with kubeconfig)
- Direct HTTP (in-cluster, no special RBAC needed)
"""
import logging
import json
import urllib.request
import urllib.error
from urllib.parse import quote
from kubernetes import client, config as k8s_config

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # 20 MB


class CollectorClient:
    """Pulls events from flowfish-l7-collector via K8s API service proxy (remote)."""

    def __init__(self, kubeconfig_path: str, namespace: str):
        try:
            cfg = client.Configuration()
            k8s_config.load_kube_config(kubeconfig_path, client_configuration=cfg)
            # K8s proxy endpoints require path separators and query-string chars
            # to pass through unencoded so the API server forwards them correctly.
            cfg.safe_chars_for_path_param = '/+:?=&'
            self._api_client = client.ApiClient(cfg)
        except Exception as e:
            logger.error("Failed to load kubeconfig from %s: %s", kubeconfig_path, e)
            raise
        self._core_v1 = client.CoreV1Api(self._api_client)
        self._namespace = namespace
        self._consecutive_errors = 0

    @classmethod
    def from_incluster(cls, namespace: str) -> "DirectHTTPCollectorClient":
        """Factory: return a direct-HTTP client for in-cluster mode."""
        return DirectHTTPCollectorClient(namespace)

    def _proxy_get(self, path: str) -> dict:
        """GET via K8s service proxy, bypassing the client's str(dict) deserialisation."""
        resp = self._core_v1.connect_get_namespaced_service_proxy_with_path(
            name="flowfish-l7-collector:8080",
            namespace=self._namespace,
            path=path,
            _preload_content=False,
        )
        body = resp.data
        if isinstance(body, bytes):
            if len(body) > _MAX_RESPONSE_BYTES:
                raise ValueError(f"Proxy response exceeds {_MAX_RESPONSE_BYTES} bytes")
            body = body.decode("utf-8")
        elif isinstance(body, str) and len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"Proxy response exceeds {_MAX_RESPONSE_BYTES} bytes")
        return json.loads(body)

    def pull_events(self, cursor: str = "", limit: int = 500) -> dict:
        # Encode `cursor` so a future opaque-token cursor format
        # (UUID, base64, JWT, …) survives `&` / `?` characters
        # without splicing additional query parameters into the
        # proxied URL. Today the buffer hands back numeric strings,
        # but defense-in-depth keeps this resilient to that change.
        # `int(limit)` guards against any caller passing a non-int.
        safe_cursor = quote(str(cursor), safe="")
        path = f"api/v1/events?cursor={safe_cursor}&limit={int(limit)}"
        try:
            result = self._proxy_get(path)
            self._consecutive_errors = 0
            return result
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors <= 3 or self._consecutive_errors % 10 == 0:
                logger.error("collector_pull_error (attempt %d): %s", self._consecutive_errors, e)
            return {"events": [], "next_cursor": cursor, "has_more": False}

    def health_check(self) -> dict:
        try:
            return self._proxy_get("health")
        except Exception as e:
            logger.error("collector_health_error: %s", e)
            return {"status": "unhealthy", "error": str(e)}

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors


class DirectHTTPCollectorClient:
    """Pulls events from flowfish-l7-collector via direct HTTP (in-cluster).

    No K8s API proxy or special RBAC needed - uses Kubernetes DNS to reach
    the collector service directly.
    """

    def __init__(self, namespace: str, service_name: str = "flowfish-l7-collector", port: int = 8080):
        self._base_url = f"http://{service_name}.{namespace}.svc:{port}"
        self._namespace = namespace
        self._consecutive_errors = 0
        logger.info("DirectHTTPCollectorClient initialized: %s", self._base_url)

    def _get(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT)
        data = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(data) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"Response exceeds {_MAX_RESPONSE_BYTES} bytes")
        return json.loads(data.decode("utf-8"))

    def pull_events(self, cursor: str = "", limit: int = 500) -> dict:
        path = f"/api/v1/events?cursor={quote(str(cursor), safe='')}&limit={int(limit)}"
        try:
            result = self._get(path)
            self._consecutive_errors = 0
            return result
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors <= 3 or self._consecutive_errors % 10 == 0:
                logger.error(
                    "collector_direct_pull_error (attempt %d): %s %s",
                    self._consecutive_errors, self._base_url, e,
                )
            return {"events": [], "next_cursor": cursor, "has_more": False}

    def health_check(self) -> dict:
        try:
            return self._get("/health")
        except Exception as e:
            logger.error("collector_direct_health_error: %s %s", self._base_url, e)
            return {"status": "unhealthy", "error": str(e)}

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors
