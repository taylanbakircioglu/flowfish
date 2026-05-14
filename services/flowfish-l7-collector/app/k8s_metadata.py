import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_pod_cache: Dict[str, dict] = {}
_name_cache: Dict[str, dict] = {}  # "namespace/workload_name" -> metadata
_node_cache: Dict[str, dict] = {}  # node IP -> node metadata
_service_cache: Dict[str, dict] = {}  # service ClusterIP -> service metadata
_hostname_cache: Dict[str, dict] = {}  # node hostname -> node metadata
_svc_name_cache: Dict[str, dict] = {}  # "name.namespace" -> service metadata
_all_namespaces: frozenset = frozenset()  # all known namespace names
_auto_cidrs: List[Tuple[str, str]] = []  # auto-detected (cidr_str, network_type)
_cache_ts: float = 0.0
_CACHE_TTL = 300  # 5 minutes
_BACKOFF_ON_FAILURE = 30  # seconds to wait before retrying after a failed refresh
_MAX_CACHE_ENTRIES = 50_000
_lock = threading.Lock()
_refresh_lock = threading.Lock()
_next_refresh_allowed: float = 0.0


_NOISY_LABEL_KEYS = frozenset({
    "pod-template-hash",
    "controller-revision-hash",
    "statefulset.kubernetes.io/pod-name",
    "rollouts-pod-template-hash",
})
_NOISY_ANNOTATION_PREFIXES = (
    "kubectl.kubernetes.io/",
    "kubernetes.io/",
    "openshift.io/",
    "k8s.ovn.org/",
    "cni.projectcalico.org/",
    "pv.kubernetes.io/",
)


def _filter_metadata(d: dict) -> dict:
    """Remove noisy/long keys from labels or annotations dict."""
    if not d:
        return {}
    result = {}
    for k, v in d.items():
        if k in _NOISY_LABEL_KEYS:
            continue
        if any(k.startswith(p) for p in _NOISY_ANNOTATION_PREFIXES):
            continue
        sv = str(v)
        if len(sv) > 500:
            continue
        result[k] = sv
    return result


def _ip_in_cidr(ip_int: int, cidr_str: str) -> bool:
    """Check if a 32-bit IP integer falls within a CIDR (e.g. '10.128.0.0/14')."""
    try:
        net_part, prefix_len = cidr_str.split('/')
        prefix_len = int(prefix_len)
        np = net_part.split('.')
        net_int = (int(np[0]) << 24) | (int(np[1]) << 16) | (int(np[2]) << 8) | int(np[3])
        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
        return (ip_int & mask) == (net_int & mask)
    except (ValueError, IndexError):
        return False


def _strip_port(addr: str) -> str:
    """Strip :port from address if Beyla embeds it.

    Handles both IPs (172.30.0.1:443) and hostnames (elasticsearch-master:9200).
    Leaves bare IPv6 (::1) unchanged.
    """
    if not addr:
        return addr
    if addr == "::1" or (addr.startswith("::") and "." not in addr):
        return addr
    if ":" in addr:
        host, _, tail = addr.rpartition(":")
        if tail.isdigit() and host:
            return host
    return addr


def classify_ip_network_type(ip: str) -> str:
    """Classify IP address into network type for visualization.

    Ported from graph_builder.py _classify_ip_network_type for L4/L7 consistency.
    MUST remain in sync with the L4 classification logic.
    Auto-detected CIDRs from node spec.podCIDR are checked for 10.x.x.x IPs
    that don't match static rules.
    """
    if not ip:
        return ''
    ip = _strip_port(ip)
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return ''
        parts_int = [int(p) for p in parts]
        if any(p < 0 or p > 255 for p in parts_int):
            return ''

        if parts_int[0] == 10:
            if 128 <= parts_int[1] <= 131:
                return 'Pod-Network'
            if parts_int[1] == 194:
                return 'Pod-Network'
            if parts_int[1] == 208:
                return 'Pod-Network'
            if parts_int[1] == 196:
                return 'Service-Network'
            if 96 <= parts_int[1] < 112:
                return 'Service-Network'
            if parts_int[1] == 244:
                return 'Pod-Network'
            if parts_int[1] == 42:
                return 'Pod-Network'
            if parts_int[1] == 43:
                return 'Service-Network'
            # Check auto-detected CIDRs before falling back to Internal-Network
            if _auto_cidrs:
                ip_int = (parts_int[0] << 24) | (parts_int[1] << 16) | (parts_int[2] << 8) | parts_int[3]
                for cidr_str, net_type in _auto_cidrs:
                    if _ip_in_cidr(ip_int, cidr_str):
                        return net_type
            return 'Internal-Network'

        if parts_int[0] == 172:
            if 16 <= parts_int[1] <= 31:
                if parts_int[1] == 30:
                    return 'Service-Network'
                return 'Private-Network'

        if parts_int[0] == 192 and parts_int[1] == 168:
            return 'Private-Network'

        if parts_int[0] == 127:
            return 'Internal-Network'
        if parts_int[0] == 169 and parts_int[1] == 254:
            return 'Internal-Network'
        if parts_int[0] == 0:
            return 'Internal-Network'
        if parts_int[0] >= 224:
            return 'Internal-Network'

        if parts_int[0] == 100 and 64 <= parts_int[1] <= 127:
            return 'Internal-Network'

        return 'External-Network'
    except (ValueError, IndexError):
        pass
    return ''


def get_namespace_for_network_type(network_type: str) -> str:
    """Return a consistent namespace for non-pod/service/node IPs.

    Mirrors L4 graph_builder._get_namespace_for_network_type for consistency.
    """
    mapping = {
        'Pod-Network': 'cluster-network',
        'Service-Network': 'cluster-network',
        'Node-Network': 'cluster-infra',
        'Internal-Network': 'internal-network',
        'Private-Network': 'internal-network',
        'External-Network': 'external',
        'External-IP': 'external',
        'SDN-Gateway': 'sdn-infrastructure',
        'OpenShift-SDN': 'sdn-infrastructure',
    }
    return mapping.get(network_type, 'unknown')


def _build_node_cache(v1) -> Tuple[Dict[str, dict], Dict[str, dict], List[Tuple[str, str]]]:
    """Build node IP cache, hostname cache, and collect auto-detected CIDRs."""
    new_node_cache: Dict[str, dict] = {}
    new_hostname_cache: Dict[str, dict] = {}
    detected_cidrs: List[Tuple[str, str]] = []
    try:
        nodes = v1.list_node(timeout_seconds=30)
        for node in nodes.items:
            hostname = node.metadata.name
            node_labels = _filter_metadata(node.metadata.labels or {})
            node_meta = {
                "pod_name": hostname,
                "namespace": "cluster-infra",
                "workload_name": hostname,
                "owner_kind": "Node",
                "network_type": "Node-Network",
                "labels": node_labels,
                "annotations": {},
            }
            # Hostname-based lookup (e.g. "worker5.example.com")
            new_hostname_cache[hostname] = node_meta
            # Also index by Hostname address type if different from metadata.name
            for addr in (node.status.addresses or []):
                if addr.type in ("InternalIP", "ExternalIP"):
                    new_node_cache[addr.address] = node_meta
                elif addr.type == "Hostname" and addr.address != hostname:
                    new_hostname_cache[addr.address] = node_meta
            # Auto-detect pod CIDRs (IPv4 only)
            pod_cidr = getattr(node.spec, 'pod_cidr', None)
            if pod_cidr and ':' not in pod_cidr:
                detected_cidrs.append((pod_cidr, "Pod-Network"))
            pod_cidrs = getattr(node.spec, 'pod_cidrs', None) or []
            for cidr in pod_cidrs:
                if cidr and ':' not in cidr and cidr != pod_cidr:
                    detected_cidrs.append((cidr, "Pod-Network"))
    except Exception as e:
        logger.warning("k8s_metadata_node_cache_failed: %s", e)
    return new_node_cache, new_hostname_cache, detected_cidrs


def _build_service_cache(v1) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Build service ClusterIP cache and name-based index ('name.namespace' -> metadata)."""
    new_svc_cache: Dict[str, dict] = {}
    new_svc_name_cache: Dict[str, dict] = {}
    try:
        _continue = None
        while True:
            svcs = v1.list_service_for_all_namespaces(
                limit=500, _continue=_continue, timeout_seconds=30
            )
            for svc in svcs.items:
                svc_name = svc.metadata.name
                svc_ns = svc.metadata.namespace
                wl_name = svc_name
                if svc_name == "kubernetes" and svc_ns == "default":
                    wl_name = "kubernetes-api"
                meta = {
                    "pod_name": svc_name,
                    "namespace": svc_ns,
                    "workload_name": wl_name,
                    "owner_kind": "Service",
                    "network_type": "Service-Network",
                    "labels": _filter_metadata(svc.metadata.labels or {}),
                    "annotations": {},
                }
                cip = svc.spec.cluster_ip
                if cip and cip not in ('None', ''):
                    new_svc_cache[cip] = meta
                # Name-based index for hostname resolution (e.g. "kafka.test-cdc-kafka")
                new_svc_name_cache[f"{svc_name}.{svc_ns}"] = meta
            _continue = svcs.metadata._continue
            if not _continue:
                break
    except Exception as e:
        logger.warning("k8s_metadata_service_cache_failed: %s", e)
    return new_svc_cache, new_svc_name_cache


def _refresh_cache() -> None:
    global _pod_cache, _name_cache, _node_cache, _service_cache, _auto_cidrs
    global _hostname_cache, _svc_name_cache, _all_namespaces
    global _cache_ts, _next_refresh_allowed
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        from kubernetes import client, config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        v1 = client.CoreV1Api()

        # Build pod cache
        new_pod_cache: Dict[str, dict] = {}
        _continue = None
        while True:
            pods = v1.list_pod_for_all_namespaces(
                limit=1000, _continue=_continue, timeout_seconds=30
            )
            for pod in pods.items:
                ip = pod.status.pod_ip
                if not ip:
                    continue
                owners = pod.metadata.owner_references or []
                workload_name = pod.metadata.name
                owner_kind = ""
                for owner in owners:
                    if owner.kind in ("ReplicaSet", "Deployment", "StatefulSet", "DaemonSet"):
                        workload_name = owner.name
                        owner_kind = owner.kind
                        if owner.kind == "ReplicaSet" and "-" in owner.name:
                            rs_parts = owner.name.rsplit("-", 1)
                            if len(rs_parts[1]) >= 5:
                                workload_name = rs_parts[0]
                                owner_kind = "Deployment"
                        break
                new_pod_cache[ip] = {
                    "pod_name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "workload_name": workload_name,
                    "owner_kind": owner_kind,
                    "labels": _filter_metadata(pod.metadata.labels or {}),
                    "annotations": _filter_metadata(pod.metadata.annotations or {}),
                }
            _continue = pods.metadata._continue
            if not _continue:
                break

        if len(new_pod_cache) > _MAX_CACHE_ENTRIES:
            logger.warning(
                "k8s_metadata_cache_truncated from=%d to=%d",
                len(new_pod_cache), _MAX_CACHE_ENTRIES,
            )
            keys = list(new_pod_cache.keys())[:_MAX_CACHE_ENTRIES]
            new_pod_cache = {k: new_pod_cache[k] for k in keys}

        # Build name cache from pod cache
        new_name_cache: Dict[str, dict] = {}
        for entry in new_pod_cache.values():
            ns = entry.get("namespace", "")
            wn = entry.get("workload_name", "")
            if ns and wn:
                key = f"{ns}/{wn}"
                if key not in new_name_cache:
                    new_name_cache[key] = entry

        # Build node cache + hostname cache + auto-detect CIDRs
        new_node_cache, new_hostname_cache, detected_cidrs = _build_node_cache(v1)
        seen_cidrs: set = set()
        unique_cidrs: List[Tuple[str, str]] = []
        for cidr_str, net_type in detected_cidrs:
            if cidr_str not in seen_cidrs:
                seen_cidrs.add(cidr_str)
                unique_cidrs.append((cidr_str, net_type))

        # Build service cache + name-based service index
        new_svc_cache, new_svc_name_cache = _build_service_cache(v1)

        # Collect all known namespaces for hostname parsing
        ns_set: set = set()
        for entry in new_pod_cache.values():
            ns = entry.get("namespace")
            if ns:
                ns_set.add(ns)
        for entry in new_svc_cache.values():
            ns = entry.get("namespace")
            if ns:
                ns_set.add(ns)
        new_all_namespaces = frozenset(ns_set)

        # Atomic swap of ALL caches under single lock
        with _lock:
            _pod_cache = new_pod_cache
            _name_cache = new_name_cache
            _node_cache = new_node_cache
            _hostname_cache = new_hostname_cache
            _svc_name_cache = new_svc_name_cache
            _service_cache = new_svc_cache
            _all_namespaces = new_all_namespaces
            _auto_cidrs = unique_cidrs
            _cache_ts = time.time()

        logger.info(
            "k8s_metadata_cache_refreshed pods=%d name_index=%d nodes=%d hostnames=%d services=%d svc_names=%d namespaces=%d auto_cidrs=%d",
            len(new_pod_cache), len(new_name_cache),
            len(new_node_cache), len(new_hostname_cache),
            len(new_svc_cache), len(new_svc_name_cache),
            len(new_all_namespaces), len(unique_cidrs),
        )
    except Exception as e:
        logger.warning("k8s_metadata_cache_refresh_failed: %s", e)
        _next_refresh_allowed = time.time() + _BACKOFF_ON_FAILURE
    finally:
        _refresh_lock.release()


def _maybe_refresh_background() -> None:
    """Trigger a background cache refresh if stale. Single-flight: only one
    refresh thread runs at a time, and on failure a backoff period is enforced."""
    now = time.time()
    if now - _cache_ts > _CACHE_TTL and now >= _next_refresh_allowed:
        t = threading.Thread(target=_refresh_cache, daemon=True)
        t.start()


def resolve_ip(ip: str) -> Optional[dict]:
    """Resolve IP to workload metadata via caches. Priority: pod > node > service.
    Returns None if not found in any cache (caller should use classify_ip_network_type as fallback)."""
    if not ip:
        return None
    _maybe_refresh_background()
    # Safety: strip embedded port (Beyla may send "ip:port" in address attrs)
    clean = _strip_port(ip)
    result = _pod_cache.get(clean)
    if result:
        return result
    result = _node_cache.get(clean)
    if result:
        return result
    result = _service_cache.get(clean)
    if result:
        return result
    return None


def resolve_hostname(hostname: str) -> Optional[dict]:
    """Resolve a hostname (non-IP) to workload metadata.

    Handles: node hostnames, K8s FQDNs (*.svc.cluster.local),
    service.namespace patterns, and short service names.
    Returns None for unrecognized hostnames (caller classifies as external).
    """
    if not hostname:
        return None
    _maybe_refresh_background()

    # 1. Node hostname exact match (e.g. "worker5.example.com")
    result = _hostname_cache.get(hostname)
    if result:
        return result

    # 2. K8s FQDN: <pod>.<svc>.<ns>.svc.cluster.local or <svc>.<ns>.svc.cluster.local
    if hostname.endswith('.svc.cluster.local'):
        stripped = hostname[: -len('.svc.cluster.local')]
        parts = stripped.split('.')
        if len(parts) >= 2:
            ns = parts[-1]
            svc = parts[-2]
            # Try name_cache (pod/workload level)
            result = _name_cache.get(f"{ns}/{svc}")
            if result:
                return result
            # Try service name cache
            result = _svc_name_cache.get(f"{svc}.{ns}")
            if result:
                return result
            # Return synthetic metadata with extracted namespace
            if ns in _all_namespaces:
                return {
                    "namespace": ns,
                    "workload_name": svc,
                    "pod_name": "",
                    "owner_kind": "Service",
                    "network_type": "Service-Network",
                    "labels": {},
                    "annotations": {},
                }

    # 3. service.namespace pattern (e.g. "kafka.test-cdc-kafka")
    if '.' in hostname:
        dot_idx = hostname.find('.')
        maybe_svc = hostname[:dot_idx]
        maybe_ns = hostname[dot_idx + 1:]
        # Check if the suffix is a known namespace
        if maybe_ns in _all_namespaces:
            result = _svc_name_cache.get(f"{maybe_svc}.{maybe_ns}")
            if result:
                return result
            result = _name_cache.get(f"{maybe_ns}/{maybe_svc}")
            if result:
                return result
            return {
                "namespace": maybe_ns,
                "workload_name": maybe_svc,
                "pod_name": "",
                "owner_kind": "",
                "network_type": "Pod-Network",
                "labels": {},
                "annotations": {},
            }

    # 4. Short service name (e.g. "sentry") — search service name cache
    for key, meta in _svc_name_cache.items():
        svc_part = key.split('.', 1)[0]
        if svc_part == hostname:
            return meta

    return None


def resolve_by_name(namespace: str, workload_name: str) -> Optional[dict]:
    """Resolve workload metadata by namespace + workload name.
    Fallback when IP-based lookup misses (service IPs, cold cache, NAT)."""
    if not namespace or not workload_name:
        return None
    _maybe_refresh_background()
    return _name_cache.get(f"{namespace}/{workload_name}")


def warm_cache() -> None:
    """Synchronously populate all caches. Call once at startup."""
    logger.info("k8s_metadata warming cache...")
    _refresh_cache()
    logger.info(
        "k8s_metadata warm complete, pods=%d nodes=%d services=%d",
        len(_pod_cache), len(_node_cache), len(_service_cache),
    )
