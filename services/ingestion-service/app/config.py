"""Configuration for Ingestion Service

Supports all Inspektor Gadget v0.46.0+ event types with corresponding RabbitMQ exchanges.
All credentials MUST come from environment variables (Kubernetes secrets).
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional

from app.constants import GADGET_DEFAULT_VERSION


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "ingestion-service"
    service_version: str = "1.2.0"  # L7 protocol detection (appProtocol, port name)
    service_port: int = 5000
    log_level: str = "INFO"
    
    # RabbitMQ - credentials from RABBITMQ_USER, RABBITMQ_PASSWORD env vars
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = Field(default="", description="From RABBITMQ_USER env var")
    rabbitmq_password: str = Field(default="", description="From RABBITMQ_PASSWORD env var (secret)")
    rabbitmq_vhost: str = "/"
    
    # Exchanges - All Inspektor Gadget v0.46.0+ event types
    exchange_network_flows: str = "flowfish.network_flows"
    exchange_dns_queries: str = "flowfish.dns_queries"
    exchange_tcp_connections: str = "flowfish.tcp_connections"
    exchange_process_events: str = "flowfish.process_events"
    exchange_file_events: str = "flowfish.file_events"
    exchange_security_events: str = "flowfish.security_events"
    exchange_oom_events: str = "flowfish.oom_events"
    exchange_bind_events: str = "flowfish.bind_events"
    exchange_sni_events: str = "flowfish.sni_events"
    exchange_mount_events: str = "flowfish.mount_events"
    exchange_workload_metadata: str = "flowfish.workload_metadata"
    
    # Change Events Exchange (published by Change Detection Worker)
    exchange_change_events: str = "flowfish.change_events"
    
    # gRPC
    grpc_max_workers: int = 10
    grpc_port: int = 5000
    
    # Inspektor Gadget
    gadget_protocol: str = "kubectl"  # kubectl, grpc, http, agent
    gadget_grpc_timeout: int = 300  # seconds
    gadget_namespace: Optional[str] = None  # namespace where gadget is deployed (from request)
    gadget_image_version: str = GADGET_DEFAULT_VERSION  # from constants.py, overridable via env
    gadget_registry: str = ""  # OCI registry for gadget images (e.g., "harbor.example.com/flowfish")
    gadget_image_prefix: str = "gadget-"  # prefix for gadget images (e.g., gadget-trace_network)
    # Time we wait after `kubectl gadget run` before deciding a gadget failed
    # to start. The default 8s covers the cold-start path: first-run OCI image
    # pull from ghcr.io into the IG DaemonSet's local store + gRPC dial from
    # the kubectl-gadget client to the IG DS endpoint. With a 2s window we
    # were observing transient false-positives where the second analysis
    # attempt always succeeded because the image had been cached.
    gadget_startup_wait_seconds: float = 8.0
    # Number of transparent retries for transient cold-start failures.
    # The 8s startup wait covers most cases, but on freshly (re)started
    # clusters the IG DaemonSet warm-up race can still kill 1-3 gadgets
    # (typically the kprobe-heavy ones: trace_tcp, trace_open,
    # trace_capabilities, trace_bind). A second invocation succeeds
    # because the OCI artifact store and gRPC dial pool are now warm,
    # and the kernel kprobe table is no longer contended.
    #
    # Default 2 attempts (was 1 — bumped after observing 4-gadget burst
    # failures on heavy-load clusters where IG container OOMs/restarts
    # mid-startup, so the first retry hits a NEW cold pod). The retry is
    # implemented in `TraceManager._retry_failed_gadgets` and uses
    # progressive backoff: each attempt's pre-wait is multiplied by 1.5,
    # so attempt 1 waits gadget_retry_pre_wait_seconds, attempt 2 waits
    # 1.5x that, etc. Setting this to 0 disables retry and reproduces
    # the legacy behaviour where a transient cold-start surfaces an
    # alert that clears on operator-initiated restart.
    gadget_startup_retry_attempts: int = 2

    # Multiplier applied to gadget_retry_pre_wait_seconds on each retry
    # attempt past the first. With default 1.5x and base 12s the wait
    # progression is: 12s, 18s, 27s, ... Acts as exponential backoff so
    # repeated retries don't all hit the same hot moment in the IG pod
    # restart cycle. Set to 1.0 for constant backoff (legacy behaviour).
    gadget_retry_backoff_multiplier: float = 1.5

    # Stagger interval between consecutive `kubectl gadget run` launches
    # at session start. Field observation: launching ~11 gadgets within a
    # 2-second burst floods the IG DaemonSet's perf-event ring buffers
    # ("getting lost samples: bad file descriptor", "lost N samples"),
    # corrupts internal state, and trips the kubelet liveness probe →
    # IG container is SIGKILL'd (exit 137). Restarted IG pods are then
    # cold and our retry loop hits another race. Spacing launches by
    # ~1.0s gives the IG worker time to register each eBPF program,
    # attach perf maps, and drain the buffers before the next one lands.
    #
    # Default bumped 0.5s → 1.0s after observing kprobe-heavy gadgets
    # (trace_tcp / trace_open / trace_capabilities / trace_bind) racing
    # for kernel kprobe attach slots on a single IG worker — 0.5s left
    # the kprobe register path under-served on busy clusters. The new
    # 1.0s default adds ~5.5s to overall analysis startup for an
    # 11-gadget set, well under the UX budget. Set to 0 to disable
    # staggering (only safe on clusters with confirmed IG headroom).
    gadget_startup_stagger_seconds: float = 1.0

    # Extra wait inserted before the *retry* attempt (only when there are
    # failed gadgets) on top of the warm-path window in
    # check_startup_errors. We add this because, in the IG-overload
    # scenario above, the original IG pod is being SIGKILL'd while we
    # retry; the retry then hits a freshly-restarting IG pod that has
    # not yet attached its eBPF programs. 12s covers the typical
    # IG container restart + bootstrap path on OpenShift / RKE / EKS
    # nodes; bump if your IG image lives in a remote registry. Note:
    # this is the *base* wait — actual wait grows by
    # gadget_retry_backoff_multiplier on each attempt past the first.
    gadget_retry_pre_wait_seconds: float = 12.0
    kubeconfig_path: str = ""  # empty = use in-cluster config
    kubectl_context: str = ""  # empty = use current context
    
    # Cluster Manager gRPC - used for Pod/Service discovery
    cluster_manager_url: str = "cluster-manager:5001"  # gRPC endpoint
    
    # Performance
    batch_size: int = 100
    batch_timeout: float = 1.0  # seconds
    max_events_per_second: int = 0  # 0 = unlimited; when set, excess events are dropped
    
    # Pod Discovery
    pod_discovery_refresh_interval: int = 30  # seconds between pod list refreshes
    pod_discovery_error_backoff_max: int = 300  # max backoff on K8s API errors (seconds)
    
    # Monitoring
    metrics_port: int = 9090
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

