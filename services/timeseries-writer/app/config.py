"""Configuration for ClickHouse Writer Service

Supports all Inspektor Gadget event types.
All credentials MUST come from environment variables (Kubernetes secrets).
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "timeseries-writer"
    service_port: int = 5005
    log_level: str = "INFO"
    
    # RabbitMQ - credentials from RABBITMQ_USER, RABBITMQ_PASSWORD env vars
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = Field(default="", description="From RABBITMQ_USER env var")
    rabbitmq_password: str = Field(default="", description="From RABBITMQ_PASSWORD env var (secret)")
    rabbitmq_vhost: str = "/"
    
    # Queue names (must match ingestion-service bindings)
    # Core network events
    queue_network_flows: str = "flowfish.queue.network_flows.timeseries"
    queue_dns_queries: str = "flowfish.queue.dns_queries.timeseries"
    queue_tcp_connections: str = "flowfish.queue.tcp_connections.timeseries"
    # Process and file events
    queue_process_events: str = "flowfish.queue.process_events.timeseries"
    queue_file_events: str = "flowfish.queue.file_events.timeseries"
    # Security events
    queue_security_events: str = "flowfish.queue.security_events.timeseries"
    queue_oom_events: str = "flowfish.queue.oom_events.timeseries"
    # Socket, TLS, and mount events
    queue_bind_events: str = "flowfish.queue.bind_events.timeseries"
    queue_sni_events: str = "flowfish.queue.sni_events.timeseries"
    queue_mount_events: str = "flowfish.queue.mount_events.timeseries"
    # Workload metadata (pod info for IP -> name lookups)
    queue_workload_metadata: str = "flowfish.queue.workload_metadata.timeseries"
    
    # Change events (from Change Detection Worker -> ClickHouse)
    queue_change_events: str = "flowfish.queue.change_events.timeseries"
    change_events_consumer_enabled: bool = True  # Consume change events from RabbitMQ, write to ClickHouse
    
    # Workload sync to PostgreSQL (for change detection queries)
    workload_sync_enabled: bool = True  # Sync workload metadata to PostgreSQL for relational queries
    
    # PostgreSQL for workload sync (same as backend)
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    postgres_user: str = Field(default="flowfish", description="PostgreSQL user")
    postgres_password: str = Field(default="", description="PostgreSQL password")
    postgres_database: str = "flowfish"
    
    # ClickHouse - credentials from CLICKHOUSE_USER, CLICKHOUSE_PASSWORD env vars
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000
    clickhouse_user: str = Field(default="", description="From CLICKHOUSE_USER env var")
    clickhouse_password: str = Field(default="", description="From CLICKHOUSE_PASSWORD env var (secret)")
    clickhouse_database: str = "flowfish"
    
    # Redis - for deleted analysis cache
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = Field(default="", description="From REDIS_PASSWORD env var (secret)")
    redis_db: int = 0
    
    # Performance - Balanced for high-throughput while preventing RabbitMQ consumer timeout
    # Strategy: Smaller batches = faster flush cycles = quicker ACKs
    # Keep prefetch >= batch_size to maintain throughput pipeline
    batch_size: int = 2000      # Reduced from 5000 for faster flush cycles (still efficient for ClickHouse bulk)
    batch_timeout: float = 1.5  # seconds - balance between latency and throughput
    prefetch_count: int = 2000  # Match batch_size to maintain throughput (one batch always ready)
    
    # gRPC
    grpc_port: int = 5005
    grpc_max_workers: int = 10
    
    # Monitoring
    metrics_port: int = 9091
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

