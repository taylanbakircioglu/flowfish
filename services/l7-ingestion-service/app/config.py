import os
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Settings:
    grpc_port: int = int(os.getenv("GRPC_PORT", "5006"))
    collector_poll_interval: int = int(os.getenv("COLLECTOR_POLL_INTERVAL", "2"))
    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "flowfish")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "flowfish_pass")
    rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST", "/")
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    sampling_rate: float = float(os.getenv("SAMPLING_RATE", "1.0"))
    max_events_per_second: int = int(os.getenv("MAX_EVENTS_PER_SECOND", "5000"))
    encryption_key: str = os.getenv("FLOWFISH_ENCRYPTION_KEY", "")
    max_session_duration: int = int(os.getenv("MAX_SESSION_DURATION", "86400"))
    # NOTE: an earlier revision exposed `l7_tracing_enabled` here to drive
    # auto-injection of the synthetic "external" namespace into per-session
    # allow-lists. That feature was removed (see grpc_server.py) because it
    # over-included unrelated workloads — _passes_namespace already accepts
    # source-side matches, so external boundary spans are kept without it.
    # The env var L7_TRACING_ENABLED is intentionally NOT consumed here any
    # more; the gating is owned by timeseries-writer / graph-writer where
    # the trace_id columns and trace_count properties live.

settings = Settings()
