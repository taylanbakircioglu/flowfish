"""gRPC server for L7 collection sessions (Beyla / flowfish-l7-collector bridge)."""

from __future__ import annotations

import logging
import random
import re
import sys
import threading
import time
from concurrent import futures
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import fnmatch
import grpc
import redis
from pathlib import Path

# Generated stubs live next to the service in Docker (/app) or at repo root in dev.
_here = Path(__file__).resolve()
_proto_parent: Optional[Path] = None
for i in range(len(_here.parents)):
    cand = _here.parents[i]
    if (cand / "l7_ingestion_service_pb2.py").is_file():
        _proto_parent = cand
        break
if _proto_parent and str(_proto_parent) not in sys.path:
    sys.path.insert(0, str(_proto_parent))

import l7_ingestion_service_pb2 as l7_pb2
import l7_ingestion_service_pb2_grpc as l7_pb2_grpc

from app.collector_client import CollectorClient
from app.config import settings
from app.kubeconfig_manager import KubeconfigManager
from app.rabbitmq_client import L7RabbitMQPublisher

logger = logging.getLogger(__name__)

PROTOCOL_TO_EVENT: Dict[str, str] = {
    "http": "l7_http_flow",
    "grpc": "l7_grpc_flow",
    "dns": "l7_dns_flow",
}


def _redis_client() -> redis.Redis:
    kw: Dict[str, Any] = {
        "host": settings.redis_host,
        "port": settings.redis_port,
        "decode_responses": True,
    }
    if settings.redis_password:
        kw["password"] = settings.redis_password
    return redis.Redis(**kw)


def _analysis_deleted_key(analysis_id: str) -> str:
    return f"flowfish:deleted_analysis:{analysis_id}"


def _cursor_key(analysis_id: str, cluster_id: str) -> str:
    return f"flowfish:l7:cursor:{analysis_id}:{cluster_id}"


class TokenBucket:
    """Simple token bucket for max_events_per_second."""

    def __init__(self, rate_per_sec: float) -> None:
        self.rate = max(0.0, float(rate_per_sec))
        self.tokens = self.rate
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, n: float = 1.0) -> bool:
        if self.rate <= 0:
            return True
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


@dataclass
class L7CollectionSession:
    analysis_id: str
    cluster_id: str
    cluster_name: str
    collector_client: CollectorClient
    namespace_allow: List[str]
    namespace_deny: List[str]
    sampling_rate: float
    protocols: List[str]
    status: str
    error_message: str
    counters: Dict[str, int]
    last_cursor: str
    lock: threading.Lock
    service_filter: str
    http_methods: List[str]
    status_codes: List[str]
    path_pattern: str
    exclude_paths: str
    kubeconfig_manager: Optional[KubeconfigManager]
    publisher: L7RabbitMQPublisher
    redis: redis.Redis
    poll_interval: float
    max_events_per_second: int
    stop_event: threading.Event = field(default_factory=threading.Event)
    poll_thread: Optional[threading.Thread] = None
    session_id: str = ""
    started_at: float = field(default_factory=time.time)
    max_duration_seconds: int = 86400

    def inc(self, key: str, n: int = 1) -> None:
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + n


class L7DataIngestionServicer(l7_pb2_grpc.L7DataIngestionServicer):
    def __init__(self) -> None:
        self._sessions_lock = threading.Lock()
        self._by_key: Dict[Tuple[str, str], L7CollectionSession] = {}
        self._publisher: Optional[L7RabbitMQPublisher] = None
        self._publisher_lock = threading.Lock()
        self._redis = _redis_client()

    def _publisher_singleton(self) -> L7RabbitMQPublisher:
        with self._publisher_lock:
            if self._publisher is None:
                self._publisher = L7RabbitMQPublisher()
            return self._publisher

    def _session_key(self, analysis_id: str, cluster_id: str) -> Tuple[str, str]:
        return (analysis_id, cluster_id)

    def HealthCheck(self, request, context):
        return l7_pb2.HealthCheckResponse(healthy=True, message="ok")

    def StartL7Collection(self, request, context):
        analysis_id = request.analysis_id or ""
        cluster_id = request.cluster_id or ""
        if not analysis_id or not cluster_id:
            return l7_pb2.StartL7CollectionResponse(
                success=False,
                message="analysis_id and cluster_id are required",
                session_id="",
            )
        key = self._session_key(analysis_id, cluster_id)

        session_id = f"l7-{analysis_id}-{cluster_id}-{int(time.time() * 1000)}"
        beyla_ns = request.beyla_namespace or "default"

        is_incluster = not request.cluster_token and not request.cluster_api_url
        mgr = None
        if is_incluster:
            logger.info(
                "in-cluster mode detected (no token/api_url) — using pod ServiceAccount "
                "analysis=%s cluster=%s",
                analysis_id, cluster_id,
            )
            try:
                collector_client = CollectorClient.from_incluster(beyla_ns)
            except Exception as e:
                logger.exception("incluster_client_failed")
                return l7_pb2.StartL7CollectionResponse(
                    success=False,
                    message=f"in-cluster K8s client failed: {e}",
                    session_id="",
                )
        else:
            mgr = KubeconfigManager(
                api_server_url=request.cluster_api_url,
                token_encrypted=request.cluster_token or "",
                ca_cert_encrypted=request.cluster_ca_cert or "",
                skip_tls_verify=request.skip_tls_verify,
                encryption_key=settings.encryption_key,
                cluster_name=request.cluster_name or f"cluster-{cluster_id}",
            )
            try:
                kc_path = mgr.write_kubeconfig()
            except Exception as e:
                logger.exception("kubeconfig_failed")
                mgr.cleanup()
                return l7_pb2.StartL7CollectionResponse(
                    success=False,
                    message=str(e),
                    session_id="",
                )
            collector_client = CollectorClient(kc_path, beyla_ns)

        sampling = request.sampling_rate if request.sampling_rate > 0 else settings.sampling_rate
        max_eps = (
            request.max_events_per_second
            if request.max_events_per_second > 0
            else settings.max_events_per_second
        )

        try:
            publisher = self._publisher_singleton()
        except Exception as e:
            logger.exception("rabbitmq_publisher_init_failed")
            if mgr:
                mgr.cleanup()
            return l7_pb2.StartL7CollectionResponse(
                success=False,
                message=f"RabbitMQ publisher failed: {e}",
                session_id="",
            )

        session = L7CollectionSession(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            cluster_name=request.cluster_name or "",
            collector_client=collector_client,
            namespace_allow=list(request.namespace_allow),
            namespace_deny=list(request.namespace_deny),
            sampling_rate=float(sampling),
            protocols=list(request.protocols),
            status="running",
            error_message="",
            counters={
                "events_published": 0,
                "events_dropped": 0,
                "http_events": 0,
                "grpc_events": 0,
                "dns_events": 0,
            },
            last_cursor="",
            lock=threading.Lock(),
            service_filter=request.service_filter or "",
            http_methods=[m.upper() for m in request.http_methods],
            status_codes=list(request.status_codes),
            path_pattern=request.path_pattern or "",
            exclude_paths=request.exclude_paths or "",
            kubeconfig_manager=mgr,
            publisher=publisher,
            redis=self._redis,
            poll_interval=float(settings.collector_poll_interval),
            max_events_per_second=int(max_eps),
            session_id=session_id,
            max_duration_seconds=settings.max_session_duration,
        )

        # Restore cursor
        try:
            cur = self._redis.get(_cursor_key(analysis_id, cluster_id))
            if cur:
                session.last_cursor = cur
        except Exception as e:
            logger.warning("redis_cursor_read_failed: %s", e)

        # Atomic check-and-register under lock to prevent TOCTOU race
        with self._sessions_lock:
            if key in self._by_key:
                if mgr:
                    mgr.cleanup()
                return l7_pb2.StartL7CollectionResponse(
                    success=False,
                    message="collection already running for this analysis/cluster",
                    session_id=self._by_key[key].session_id,
                )
            self._by_key[key] = session

        t = threading.Thread(
            target=self._poll_events,
            args=(session,),
            name=f"l7-poll-{session_id}",
            daemon=True,
        )
        session.poll_thread = t
        t.start()

        return l7_pb2.StartL7CollectionResponse(
            success=True,
            message="started",
            session_id=session_id,
        )

    def StopL7Collection(self, request, context):
        key = self._session_key(request.analysis_id, request.cluster_id)
        with self._sessions_lock:
            session = self._by_key.pop(key, None)
        if not session:
            return l7_pb2.StopL7CollectionResponse(
                success=False,
                message="session not found",
                total_events=0,
            )
        session.stop_event.set()
        if session.poll_thread:
            session.poll_thread.join(timeout=30)
            if session.poll_thread.is_alive():
                logger.warning(
                    "Poll thread %s did not terminate within 30s (will exit on next loop iteration)",
                    session.session_id,
                )
        if session.kubeconfig_manager:
            session.kubeconfig_manager.cleanup()
        total = session.counters.get("events_published", 0)
        return l7_pb2.StopL7CollectionResponse(
            success=True,
            message="stopped",
            total_events=total,
        )

    def GetL7CollectionStatus(self, request, context):
        key = self._session_key(request.analysis_id, request.cluster_id)
        with self._sessions_lock:
            session = self._by_key.get(key)
        if not session:
            return l7_pb2.L7CollectionStatus(
                analysis_id=request.analysis_id,
                cluster_id=request.cluster_id,
                status="not_found",
            )
        return self._status_proto(session)

    def ListL7CollectionStatus(self, request, context):
        aid = request.analysis_id or ""
        out: List[l7_pb2.L7CollectionStatus] = []
        with self._sessions_lock:
            for session in self._by_key.values():
                if aid and session.analysis_id != aid:
                    continue
                out.append(self._status_proto(session))
        return l7_pb2.ListL7StatusResponse(statuses=out)

    def _status_proto(self, session: L7CollectionSession) -> l7_pb2.L7CollectionStatus:
        with session.lock:
            c = dict(session.counters)
            err = session.error_message
            st = session.status
        return l7_pb2.L7CollectionStatus(
            analysis_id=session.analysis_id,
            cluster_id=session.cluster_id,
            status=st,
            events_published=c.get("events_published", 0),
            http_events=c.get("http_events", 0),
            grpc_events=c.get("grpc_events", 0),
            dns_events=c.get("dns_events", 0),
            error_message=err,
        )

    def _poll_events(self, session: L7CollectionSession) -> None:
        try:
            bucket = TokenBucket(float(session.max_events_per_second))
            protocol_filter: Optional[Set[str]] = None
            if session.protocols:
                protocol_filter = set()
                for p in session.protocols:
                    p = p.lower().strip()
                    et = PROTOCOL_TO_EVENT.get(p)
                    if et:
                        protocol_filter.add(et)
                if not protocol_filter:
                    logger.warning(
                        "All requested protocols %s are unknown — no events will pass filter",
                        session.protocols,
                    )
                    # Keep the empty set so the filter blocks everything rather
                    # than falling through (empty set is falsy in Python, so we
                    # must treat it as an active filter below).

            compiled_path: Optional[re.Pattern] = None
            if session.path_pattern:
                try:
                    compiled_path = re.compile(session.path_pattern)
                except re.error as e:
                    session.status = "error"
                    session.error_message = f"invalid path_pattern: {e}"
                    return

            exclude_parts = [
                s.strip() for s in session.exclude_paths.split(",") if s.strip()
            ]

            consecutive_errors = 0
            max_backoff = 60.0
            while not session.stop_event.is_set():
                try:
                    elapsed = time.time() - session.started_at
                    if elapsed > session.max_duration_seconds:
                        logger.warning(
                            "Session %s exceeded max duration (%ds), auto-stopping",
                            session.session_id, session.max_duration_seconds,
                        )
                        session.status = "stopped"
                        session.error_message = "max duration exceeded"
                        break

                    if session.redis.get(_analysis_deleted_key(session.analysis_id)):
                        session.status = "stopped"
                        session.error_message = "analysis deleted"
                        break

                    resp = session.collector_client.pull_events(
                        cursor=session.last_cursor, limit=500
                    )
                    events = resp.get("events") or []
                    next_cursor = resp.get("next_cursor") or session.last_cursor
                    consecutive_errors = 0

                    publish_ok_count = 0
                    publish_fail_count = 0
                    for ev in events:
                        if session.stop_event.is_set():
                            break
                        if not isinstance(ev, dict):
                            continue
                        if protocol_filter is not None and ev.get("event_type") not in protocol_filter:
                            continue
                        if not self._passes_namespace(session, ev):
                            continue
                        if not self._passes_l7_filters(
                            ev,
                            session.service_filter,
                            session.http_methods,
                            session.status_codes,
                            compiled_path,
                            exclude_parts,
                        ):
                            continue
                        if session.sampling_rate < 1.0 and random.random() > session.sampling_rate:
                            continue
                        if not bucket.consume(1.0):
                            continue

                        enriched = dict(ev)
                        enriched["analysis_id"] = session.analysis_id
                        enriched["cluster_id"] = session.cluster_id
                        enriched["cluster_name"] = session.cluster_name

                        published = session.publisher.publish(enriched)
                        if published:
                            et = ev.get("event_type", "")
                            publish_ok_count += 1
                            session.inc("events_published")
                            if et == "l7_http_flow":
                                session.inc("http_events")
                            elif et == "l7_grpc_flow":
                                session.inc("grpc_events")
                            elif et == "l7_dns_flow":
                                session.inc("dns_events")
                        else:
                            publish_fail_count += 1
                            session.inc("events_dropped")

                    if publish_fail_count > 0 and publish_ok_count == 0 and events:
                        # All events in this page failed to publish (e.g. RMQ
                        # down or all unknown event types). Still advance the
                        # cursor to prevent an infinite stuck loop on the same
                        # page. The events are already counted as dropped.
                        logger.warning(
                            "All %d events in page failed to publish — advancing cursor to prevent stuck loop",
                            publish_fail_count,
                        )
                    session.last_cursor = next_cursor
                    try:
                        session.redis.set(
                            _cursor_key(session.analysis_id, session.cluster_id),
                            session.last_cursor,
                        )
                    except Exception as e:
                        logger.warning("redis_cursor_write_failed: %s", e)

                    if not resp.get("has_more"):
                        time.sleep(session.poll_interval)
                    elif not events:
                        time.sleep(min(session.poll_interval, 1.0))
                    else:
                        time.sleep(0)
                except Exception as e:
                    consecutive_errors += 1
                    backoff = min(session.poll_interval * (2 ** consecutive_errors), max_backoff)
                    if consecutive_errors <= 5 or consecutive_errors % 20 == 0:
                        logger.exception("l7_poll_error (attempt %d, backoff %.1fs)", consecutive_errors, backoff)
                    else:
                        logger.warning("l7_poll_error (attempt %d): %s", consecutive_errors, e)
                    session.error_message = str(e)
                    time.sleep(backoff)

            session.status = "stopped"
        finally:
            skey = self._session_key(session.analysis_id, session.cluster_id)
            with self._sessions_lock:
                # Only remove if this session is still the registered one (avoid
                # evicting a newer session that replaced us via a second Start).
                if self._by_key.get(skey) is session:
                    del self._by_key[skey]
            if session.kubeconfig_manager:
                session.kubeconfig_manager.cleanup()

    # Note: an earlier revision of this file auto-injected 'external' into the
    # namespace_allow list when distributed tracing was enabled, on the
    # mistaken assumption that boundary spans (workload -> external host)
    # would otherwise be dropped. They are NOT dropped — _passes_namespace
    # accepts an event when EITHER the source OR the destination namespace
    # matches an entry, so a request from `<user-ns>` to an unresolved
    # external host (which Beyla labels `namespace="external"`) already
    # passes via the source side. The auto-injection had the unintended
    # effect of also accepting requests from any other namespace whose
    # destination resolved to "external", which leaks unrelated workloads
    # into the analysis. Removed in favour of letting the operator's
    # explicit allow-list speak for itself.

    def _passes_namespace(self, session: L7CollectionSession, event: dict) -> bool:
        data = event.get("data") or {}
        src = (data.get("src") or {}) if isinstance(data.get("src"), dict) else {}
        dst = (data.get("dst") or {}) if isinstance(data.get("dst"), dict) else {}
        ns_src = (src.get("namespace") or "").strip()
        ns_dst = (dst.get("namespace") or "").strip()

        for deny in session.namespace_deny:
            d = deny.strip()
            if not d:
                continue
            if "*" in d or "?" in d:
                if (ns_src and fnmatch.fnmatch(ns_src, d)) or (ns_dst and fnmatch.fnmatch(ns_dst, d)):
                    return False
            elif d == ns_src or d == ns_dst:
                return False

        if not session.namespace_allow:
            return True
        allowed = [a.strip() for a in session.namespace_allow if a.strip()]
        if not allowed:
            return True
        for a in allowed:
            if "*" in a or "?" in a:
                if (ns_src and fnmatch.fnmatch(ns_src, a)) or (ns_dst and fnmatch.fnmatch(ns_dst, a)):
                    return True
            elif a == ns_src or a == ns_dst:
                return True
        return False

    def _passes_l7_filters(
        self,
        event: dict,
        service_filter: str,
        http_methods: List[str],
        status_codes: List[str],
        path_pattern: Optional[re.Pattern],
        exclude_parts: List[str],
    ) -> bool:
        et = event.get("event_type")
        data = event.get("data") or {}
        if not isinstance(data, dict):
            data = {}

        svc_blob = " ".join(
            [
                str(data.get("host", "")),
                str((data.get("src") or {}).get("workload_name", "")),
                str((data.get("dst") or {}).get("workload_name", "")),
                str(data.get("grpc_service", "")),
                str(data.get("query_name", "")),
            ]
        ).lower()
        if service_filter and service_filter.lower() not in svc_blob:
            return False

        if et == "l7_http_flow":
            method = str(data.get("method", "")).upper()
            if http_methods and method not in http_methods:
                return False
            code = str(data.get("response_status", ""))
            if status_codes and code not in status_codes:
                return False
            path = str(data.get("path", ""))
            for ex in exclude_parts:
                if ex and ex in path:
                    return False
            if path_pattern and not path_pattern.search(path):
                return False

        return True


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
    servicer = L7DataIngestionServicer()
    l7_pb2_grpc.add_L7DataIngestionServicer_to_server(servicer, server)
    bound_port = server.add_insecure_port(f"[::]:{settings.grpc_port}")
    if bound_port == 0:
        logger.error("Failed to bind gRPC port %s – is it already in use?", settings.grpc_port)
        raise RuntimeError(f"Cannot bind gRPC port {settings.grpc_port}")
    server.start()
    logger.info("l7-ingestion-service listening on %s", bound_port)
    return server, servicer
