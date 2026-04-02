"""Configuration for Graph Writer Service

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "graph-writer"
    log_level: str = "INFO"
    
    # RabbitMQ - credentials from RABBITMQ_USER, RABBITMQ_PASSWORD env vars
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = Field(default="", description="From RABBITMQ_USER env var")
    rabbitmq_password: str = Field(default="", description="From RABBITMQ_PASSWORD env var (secret)")
    rabbitmq_vhost: str = "/"
    
    # Queue names (must match ingestion-service bindings)
    queue_network_flows: str = "flowfish.queue.network_flows.graph"
    queue_dns_queries: str = "flowfish.queue.dns_queries.graph"
    queue_tcp_connections: str = "flowfish.queue.tcp_connections.graph"
    queue_bind_events: str = "flowfish.queue.bind_events.graph"
    queue_sni_events: str = "flowfish.queue.sni_events.graph"
    
    # Prefetch count for consumer
    prefetch_count: int = 100
    
    # Neo4j - credentials from NEO4J_USER, NEO4J_PASSWORD env vars
    neo4j_bolt_uri: str = "bolt://neo4j:7687"
    neo4j_http_uri: str = "http://neo4j:7474"
    neo4j_user: str = Field(default="neo4j", description="From NEO4J_USER env var")
    neo4j_password: str = Field(default="", description="From NEO4J_PASSWORD env var (secret)")
    neo4j_database: str = "neo4j"
    
    # Redis - for deleted analysis cache
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = Field(default="", description="From REDIS_PASSWORD env var (secret)")
    redis_db: int = 0
    
    # Graph settings
    batch_size: int = 500  # Batch insert size (increased for performance)
    flush_interval: int = 2  # seconds (reduced for faster processing)
    filter_localhost: bool = False  # If True, filter localhost traffic at graph-writer level
    # Note: Frontend also has a toggle to filter localhost. Set this to False to let frontend handle it.
    
    # DNS search domain normalization — comma-separated list of custom search
    # domains to strip from DNS names before creating graph nodes.
    # Typically matches the search list from /etc/resolv.conf on cluster nodes.
    # Example: DNS_SEARCH_DOMAINS=mycompany.local,internal.mycompany.local
    dns_search_domains: str = Field(default="", description="From DNS_SEARCH_DOMAINS env var")
    
    # Kubernetes (for workload discovery)
    k8s_in_cluster: bool = True
    k8s_config_path: str = "~/.kube/config"
    
    # Monitoring
    metrics_port: int = 9094
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

