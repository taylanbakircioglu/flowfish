"""
OTLP span -> Flowfish intermediate event transformer (Layer 1).
Does NOT add analysis_id or cluster_id - those are added by L7 Ingestion Service (Layer 2).
"""
import json
import logging
import time
from typing import Optional, List

from app import k8s_metadata

logger = logging.getLogger(__name__)


def _get_attr(attributes: list, key: str) -> Optional[str]:
    for attr in attributes:
        if attr.key == key:
            v = attr.value
            if v.HasField("string_value"):
                return v.string_value
            if v.HasField("int_value"):
                return str(v.int_value)
            if v.HasField("double_value"):
                return str(v.double_value)
            if v.HasField("bool_value"):
                return str(v.bool_value).lower()
            if v.HasField("array_value"):
                parts = []
                for item in v.array_value.values:
                    if item.HasField("string_value"):
                        parts.append(item.string_value)
                    elif item.HasField("int_value"):
                        parts.append(str(item.int_value))
                    elif item.HasField("double_value"):
                        parts.append(str(item.double_value))
                    elif item.HasField("bool_value"):
                        parts.append(str(item.bool_value).lower())
                return ",".join(parts) if parts else None
    return None


def _get_int_attr(attributes: list, key: str, default: int = 0) -> int:
    val = _get_attr(attributes, key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _clean_ip(addr: str) -> tuple:
    """Strip :port suffix from addresses that Beyla may embed.

    Handles both IPs (172.30.0.1:443) and hostnames (elasticsearch-master:9200).
    Returns (clean_addr, extracted_port_or_0).
    """
    if not addr:
        return ("", 0)
    # Bare IPv6 loopback shorthand (e.g. "::1") — not a valid target
    if addr == "::1" or (addr.startswith("::") and "." not in addr):
        return ("", 0)
    # addr:port — works for both IPs and hostnames
    if ":" in addr:
        host, _, maybe_port = addr.rpartition(":")
        if maybe_port.isdigit() and host:
            return (host, int(maybe_port))
    return (addr, 0)


def _is_hostname(addr: str) -> bool:
    """Return True if addr looks like a hostname rather than a numeric IP."""
    return bool(addr) and any(c.isalpha() for c in addr)


# ---------------------------------------------------------------------------
# Phase 4 — Process context extraction (PID-temporal virtual_trace_id)
# ---------------------------------------------------------------------------
# Beyla emits per-process attributes either on the OTLP Resource (the more
# common case for k8s deployments) or on the individual Span (older builds).
# We probe the resource first because that is the more authoritative source —
# Beyla attaches process attrs from `attributes.select.process.*` to the
# resource bucket. If absent, we fall back to span attrs so legacy Beyla
# builds still get partial coverage.
#
# Returned values default to (0, 0, "") when the attribute is missing or the
# Beyla version doesn't ship process.* — the timeseries-writer's correlator
# will then leave virtual_trace_id empty (Phase 4D), preserving the existing
# behaviour for unstamped events.
def _extract_process_context(attrs: list, resource_attrs: list) -> dict:
    """Return {pid, ppid, container_id} extracted from OTLP attributes.

    Lookup order: resource_attrs > span attrs. Falls back to defaults if
    Beyla < 3.0 or `attributes.select.process.*` is not configured.
    """
    pid = _get_int_attr(resource_attrs, "process.pid", 0) or _get_int_attr(attrs, "process.pid", 0)
    ppid = _get_int_attr(resource_attrs, "process.parent_pid", 0) or _get_int_attr(
        attrs, "process.parent_pid", 0
    )
    container_id = (
        _get_attr(resource_attrs, "container.id")
        or _get_attr(resource_attrs, "k8s.container.id")
        or _get_attr(attrs, "container.id")
        or ""
    )
    return {
        "pid": pid,
        "ppid": ppid,
        "container_id": container_id,
    }


def _resolve_endpoint(ip: Optional[str], port: int, resource_attrs: list) -> dict:
    """Build src/dst endpoint dict from IP + resource attributes.

    Resolution priority: OTLP resource attrs > pod cache > node cache > service cache > IP classification.
    """
    # Beyla sometimes embeds port in address attrs (e.g. "172.30.0.1:443")
    if ip:
        clean, extracted_port = _clean_ip(ip)
        ip = clean
        if not port and extracted_port:
            port = extracted_port

    ns = _get_attr(resource_attrs, "k8s.namespace.name") or ""
    pod = _get_attr(resource_attrs, "k8s.pod.name") or ""
    workload = (
        _get_attr(resource_attrs, "k8s.deployment.name")
        or _get_attr(resource_attrs, "k8s.statefulset.name")
        or _get_attr(resource_attrs, "k8s.daemonset.name")
        or ""
    )

    meta = k8s_metadata.resolve_ip(ip) if ip else None
    if meta:
        ns = ns or meta.get("namespace", "")
        pod = pod or meta.get("pod_name", "")
        workload = workload or meta.get("workload_name", "")

    if not meta and ns and workload:
        meta = k8s_metadata.resolve_by_name(ns, workload)

    labels = meta.get("labels", {}) if meta else {}
    annotations = meta.get("annotations", {}) if meta else {}
    owner_kind = meta.get("owner_kind", "") if meta else ""
    network_type = meta.get("network_type", "") if meta else ""

    # If cache resolved (pod/node/service), network_type is already set.
    # For resolved pods with no explicit network_type, mark as Pod-Network.
    if meta and not network_type:
        network_type = "Pod-Network"

    # If IP not resolved by any cache, try loopback / CIDR / hostname resolution
    if not meta and ip:
        if ip in ("localhost", "127.0.0.1", "::1"):
            network_type = "Pod-Network"
            ns = ns or "loopback"
            workload = workload or "localhost"
        else:
            cidr_type = k8s_metadata.classify_ip_network_type(ip)
            if cidr_type:
                network_type = cidr_type
                ns = ns or k8s_metadata.get_namespace_for_network_type(cidr_type)
                workload = workload or ip
            elif _is_hostname(ip):
                meta = k8s_metadata.resolve_hostname(ip)
                if meta:
                    ns = ns or meta.get("namespace", "")
                    pod = pod or meta.get("pod_name", "")
                    workload = workload or meta.get("workload_name", "")
                    owner_kind = meta.get("owner_kind", "") or owner_kind
                    network_type = meta.get("network_type", "") or network_type
                    labels = meta.get("labels", {}) or labels
                    annotations = meta.get("annotations", {}) or annotations
                else:
                    network_type = "External-Network"
                    ns = ns or "external"
                    workload = workload or ip

    is_external = network_type in ('External-Network', 'External-IP')

    return {
        "ip": ip or "",
        "port": port,
        "namespace": ns,
        "pod_name": pod,
        "workload_name": workload or pod,
        "owner_kind": owner_kind,
        "labels": labels,
        "annotations": annotations,
        "network_type": network_type,
        "is_external": is_external,
    }


# Synthetic namespaces produced by `_resolve_endpoint` when an endpoint cannot
# be resolved to a real Kubernetes object. We drop spans where either side is
# `loopback` because pod-internal localhost traffic carries no distributed
# observability value (the producer and consumer live in the same address
# space) and Flowfish's own gadget gRPC streams generate large per-connection
# durations that visibly skew aggregate latency in Service Map / Trace
# Explorer. This is the upstream defense; timeseries-writer also re-applies
# the filter in case operators run a Beyla build that already emits
# `loopback` events from a stale cache. See:
#   docs/architecture/L7_DISTRIBUTED_TRACING_MIGRATION.md (Loopback filter)
_NOISE_NAMESPACES: frozenset = frozenset({"loopback"})


def _endpoint_namespace(endpoint: object) -> str:
    """Best-effort namespace extraction tolerant to upstream format drift.

    The `_build_*_event` functions always emit a dict for src/dst, but a
    misbehaving upstream could send a string or None and we should not
    propagate the AttributeError up the OTLP receiver loop (it would tear
    down the whole batch). Returns an empty string for any non-dict shape.
    """
    if not isinstance(endpoint, dict):
        return ""
    ns = endpoint.get("namespace")
    return ns if isinstance(ns, str) else ""


def _is_noise_event(event: object) -> bool:
    """Return True when an event represents pod-internal localhost traffic
    that should be discarded before being queued to RabbitMQ.

    Tolerates both the canonical nested format produced by `_build_*_event`
    (`data.src.namespace` / `data.dst.namespace`) and a hypothetical flat
    format (`data.src_namespace` / `data.dst_namespace`) that legacy or
    third-party producers could emit. Returns False for any malformed
    event so the caller treats it as a regular (passthrough) span.
    """
    if not isinstance(event, dict):
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    # Canonical nested form first (current Beyla flow), then flat fallback.
    src_ns = _endpoint_namespace(data.get("src")) or (
        data.get("src_namespace") if isinstance(data.get("src_namespace"), str) else ""
    )
    dst_ns = _endpoint_namespace(data.get("dst")) or (
        data.get("dst_namespace") if isinstance(data.get("dst_namespace"), str) else ""
    )
    return src_ns.lower() in _NOISE_NAMESPACES or dst_ns.lower() in _NOISE_NAMESPACES


def transform_spans(resource_spans_list) -> List[dict]:
    """Transform OTLP ResourceSpans into Flowfish intermediate events."""
    events = []
    dropped_noise = 0
    for rs in resource_spans_list:
        resource_attrs = list(rs.resource.attributes) if rs.resource else []
        for scope_span in rs.scope_spans:
            for span in scope_span.spans:
                event = _transform_single_span(span, resource_attrs)
                if not event:
                    continue
                if _is_noise_event(event):
                    dropped_noise += 1
                    continue
                events.append(event)
    if dropped_noise:
        logger.debug(
            "Dropped %d localhost-only spans (Flowfish self-monitoring noise)",
            dropped_noise,
        )
    return events


def _transform_single_span(span, resource_attrs: list) -> Optional[dict]:
    attrs = list(span.attributes)
    span_kind = span.kind  # 1=INTERNAL, 2=SERVER, 3=CLIENT, 4=PRODUCER, 5=CONSUMER

    # W3C OpenTelemetry Distributed Trace context extraction.
    # NOTE: This trace_id is the W3C standard distributed trace ID and is
    # independent of the Inspector Gadget "trace_id" used in the L4 pipeline
    # (services/ingestion-service/app/trace_manager.py — gadget session ID).
    # All-zero byte arrays are treated as invalid (no propagation observed).
    raw_trace = span.trace_id
    trace_id = raw_trace.hex() if raw_trace and any(raw_trace) else ""
    raw_span = span.span_id
    span_id = raw_span.hex() if raw_span and any(raw_span) else ""
    raw_parent = span.parent_span_id
    parent_span_id = raw_parent.hex() if raw_parent and any(raw_parent) else ""
    span_name = span.name or ""

    rpc_service = _get_attr(attrs, "rpc.service")
    rpc_method = _get_attr(attrs, "rpc.method")
    dns_question_name = _get_attr(attrs, "dns.question.name")
    http_method = _get_attr(attrs, "http.request.method")

    # Build event from existing classification logic
    if rpc_service or rpc_method:
        event = _build_grpc_event(span, attrs, resource_attrs, span_kind)
    elif dns_question_name:
        event = _build_dns_event(span, attrs, resource_attrs, span_kind)
    elif http_method or _get_attr(attrs, "url.path"):
        event = _build_http_event(span, attrs, resource_attrs, span_kind)
    else:
        # Span did not match HTTP/gRPC/DNS heuristics — drop.
        # Internal/custom spans are not represented in V1; surfaced via warning
        # in TraceWaterfall UI when viewing incomplete traces.
        return None

    # Inject W3C trace context fields into event.data.
    # _build_* functions remain unchanged; trace fields are non-destructive
    # additions and default to "" / 0 in ClickHouse when l7_tracing is disabled.
    if event:
        event["data"]["trace_id"] = trace_id
        event["data"]["span_id"] = span_id
        event["data"]["parent_span_id"] = parent_span_id
        event["data"]["span_name"] = span_name
        event["data"]["span_kind"] = span_kind

        # Phase 4 — attach process context for PID-temporal correlation.
        # DNS spans are deliberately not correlated (a DNS query is single-
        # RPC by definition; there is no peer span to stitch). Adding the
        # fields anyway would just bloat the DNS payload. event.data
        # consumers must therefore tolerate missing keys, which they
        # already do (`.get("pid", 0)` style access in the writer).
        if event.get("event_type") in ("l7_http_flow", "l7_grpc_flow"):
            proc = _extract_process_context(attrs, resource_attrs)
            event["data"]["pid"] = proc["pid"]
            event["data"]["ppid"] = proc["ppid"]
            event["data"]["container_id"] = proc["container_id"]
    return event


def _span_timestamp_ms(span) -> int:
    if span.start_time_unix_nano:
        return span.start_time_unix_nano // 1_000_000
    return int(time.time() * 1000)


def _span_duration_ms(span) -> float:
    if span.start_time_unix_nano and span.end_time_unix_nano:
        return (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000
    return 0.0


def _build_http_event(span, attrs, resource_attrs, span_kind) -> dict:
    src_ip = _get_attr(attrs, "client.address") or _get_attr(attrs, "net.peer.ip") or ""
    dst_ip = _get_attr(attrs, "server.address") or _get_attr(attrs, "net.host.ip") or ""
    src_port = _get_int_attr(attrs, "client.port")
    dst_port = _get_int_attr(attrs, "server.port") or _get_int_attr(attrs, "net.host.port", 0)
    # Beyla may embed port in address attr — extract before resolution
    src_ip, _sp = _clean_ip(src_ip)
    dst_ip, _dp = _clean_ip(dst_ip)
    if not src_port and _sp:
        src_port = _sp
    if not dst_port and _dp:
        dst_port = _dp

    if span_kind == 2:  # SERVER
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, resource_attrs)
        src_endpoint = _resolve_endpoint(src_ip, src_port, [])
    else:  # CLIENT or INTERNAL
        src_endpoint = _resolve_endpoint(src_ip, src_port, resource_attrs)
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, [])

    return {
        "event_type": "l7_http_flow",
        "timestamp": _span_timestamp_ms(span),
        "data": {
            "src": src_endpoint,
            "dst": dst_endpoint,
            "src_labels": src_endpoint.get("labels", {}),
            "dst_labels": dst_endpoint.get("labels", {}),
            "src_annotations": src_endpoint.get("annotations", {}),
            "dst_annotations": dst_endpoint.get("annotations", {}),
            "src_owner_kind": src_endpoint.get("owner_kind", ""),
            "dst_owner_kind": dst_endpoint.get("owner_kind", ""),
            "method": _get_attr(attrs, "http.request.method") or "UNKNOWN",
            "path": _get_attr(attrs, "url.path") or _get_attr(attrs, "http.route") or "/",
            "host": _get_attr(attrs, "server.address") or _get_attr(attrs, "http.host") or "",
            "response_status": _get_int_attr(attrs, "http.response.status_code", 0),
            "request_size": _get_int_attr(attrs, "http.request.body.size"),
            "response_size": _get_int_attr(attrs, "http.response.body.size"),
            "duration_ms": _span_duration_ms(span),
        },
    }


def _build_grpc_event(span, attrs, resource_attrs, span_kind) -> dict:
    src_ip = _get_attr(attrs, "client.address") or ""
    dst_ip = _get_attr(attrs, "server.address") or ""
    src_port = _get_int_attr(attrs, "client.port")
    dst_port = _get_int_attr(attrs, "server.port")
    src_ip, _sp = _clean_ip(src_ip)
    dst_ip, _dp = _clean_ip(dst_ip)
    if not src_port and _sp:
        src_port = _sp
    if not dst_port and _dp:
        dst_port = _dp

    if span_kind == 2:
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, resource_attrs)
        src_endpoint = _resolve_endpoint(src_ip, src_port, [])
    else:
        src_endpoint = _resolve_endpoint(src_ip, src_port, resource_attrs)
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, [])

    return {
        "event_type": "l7_grpc_flow",
        "timestamp": _span_timestamp_ms(span),
        "data": {
            "src": src_endpoint,
            "dst": dst_endpoint,
            "src_labels": src_endpoint.get("labels", {}),
            "dst_labels": dst_endpoint.get("labels", {}),
            "src_annotations": src_endpoint.get("annotations", {}),
            "dst_annotations": dst_endpoint.get("annotations", {}),
            "src_owner_kind": src_endpoint.get("owner_kind", ""),
            "dst_owner_kind": dst_endpoint.get("owner_kind", ""),
            "grpc_service": _get_attr(attrs, "rpc.service") or "",
            "grpc_method": _get_attr(attrs, "rpc.method") or "",
            "grpc_status_code": _get_int_attr(attrs, "rpc.grpc.status_code"),
            "grpc_status_message": _get_attr(attrs, "rpc.grpc.status_message") or "",
            "request_size": _get_int_attr(attrs, "http.request.body.size"),
            "response_size": _get_int_attr(attrs, "http.response.body.size"),
            "duration_ms": _span_duration_ms(span),
        },
    }


def _get_dns_answers(attrs: list) -> str:
    """Extract dns.answers as a JSON array of strings, handling array_value and string fallbacks."""
    for attr in attrs:
        if attr.key == "dns.answers":
            v = attr.value
            if v.HasField("array_value"):
                parts = []
                for item in v.array_value.values:
                    if item.HasField("string_value"):
                        parts.append(item.string_value)
                return json.dumps(parts)
            if v.HasField("string_value"):
                raw = v.string_value
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return raw
                except (json.JSONDecodeError, TypeError):
                    pass
                return json.dumps([raw]) if raw else "[]"
    return "[]"


def _build_dns_event(span, attrs, resource_attrs, span_kind) -> dict:
    src_ip = _get_attr(attrs, "client.address") or ""
    dst_ip = _get_attr(attrs, "server.address") or ""
    src_port = _get_int_attr(attrs, "client.port")
    dst_port = _get_int_attr(attrs, "server.port", 53)
    src_ip, _sp = _clean_ip(src_ip)
    dst_ip, _dp = _clean_ip(dst_ip)
    if not src_port and _sp:
        src_port = _sp
    if not dst_port and _dp:
        dst_port = _dp

    if span_kind == 2:
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, resource_attrs)
        src_endpoint = _resolve_endpoint(src_ip, src_port, [])
    else:
        src_endpoint = _resolve_endpoint(src_ip, src_port, resource_attrs)
        dst_endpoint = _resolve_endpoint(dst_ip, dst_port, [])

    return {
        "event_type": "l7_dns_flow",
        "timestamp": _span_timestamp_ms(span),
        "data": {
            "src": src_endpoint,
            "dst": dst_endpoint,
            "src_labels": src_endpoint.get("labels", {}),
            "dst_labels": dst_endpoint.get("labels", {}),
            "src_annotations": src_endpoint.get("annotations", {}),
            "dst_annotations": dst_endpoint.get("annotations", {}),
            "src_owner_kind": src_endpoint.get("owner_kind", ""),
            "dst_owner_kind": dst_endpoint.get("owner_kind", ""),
            "query_name": _get_attr(attrs, "dns.question.name") or "",
            "query_type": _get_attr(attrs, "dns.question.type") or "A",
            "response_code": _get_int_attr(attrs, "dns.response_code"),
            "response_ips": _get_dns_answers(attrs),
            "duration_ms": _span_duration_ms(span),
        },
    }
