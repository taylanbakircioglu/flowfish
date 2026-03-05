"""Configuration for Analysis Orchestrator Service

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "flowfish-analysis-orchestrator"
    service_port: int = 5002
    log_level: str = "INFO"
    
    # gRPC
    grpc_port: int = 5002
    grpc_max_workers: int = 10
    
    # PostgreSQL - credentials from env vars
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    postgres_user: str = Field(default="", description="From POSTGRES_USER env var")
    postgres_password: str = Field(default="", description="From POSTGRES_PASSWORD env var (secret)")
    postgres_database: str = "flowfish"
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
    
    # Neo4j - credentials from env vars
    neo4j_bolt_uri: str = "bolt://neo4j:7687"
    neo4j_http_uri: str = "http://neo4j:7474"
    neo4j_user: str = Field(default="neo4j", description="From NEO4J_USER env var")
    neo4j_password: str = Field(default="", description="From NEO4J_PASSWORD env var (secret)")
    neo4j_database: str = "neo4j"
    
    # ClickHouse - credentials from env vars
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000
    clickhouse_http_port: int = 8123  # HTTP interface for queries
    clickhouse_user: str = Field(default="", description="From CLICKHOUSE_USER env var")
    clickhouse_password: str = Field(default="", description="From CLICKHOUSE_PASSWORD env var (secret)")
    clickhouse_database: str = "flowfish"
    
    # Auto-stop monitor settings
    auto_stop_check_interval: int = 15  # seconds between limit checks (faster response)
    
    # Backend service (for settings API and WebSocket broadcast)
    # Note: Using different name to avoid conflict with Kubernetes auto-generated BACKEND_PORT env var
    backend_service_host: str = Field(default="backend", alias="BACKEND_SERVICE_HOST")
    backend_service_port: int = Field(default=8000, alias="BACKEND_SERVICE_PORT")
    
    # Inspector Gadget (gRPC, no http:// prefix)
    gadget_endpoint: str = "inspektor-gadget:16060"
    ingestion_service_endpoint: str = "ingestion-service:5000"
    
    # Query Services (HTTP)
    timeseries_query_url: str = "http://timeseries-query:8002"
    graph_query_url: str = "http://graph-query:8001"
    
    # Cluster Manager gRPC
    cluster_manager_host: str = "cluster-manager"
    cluster_manager_port: int = 5001
    
    # Scheduler
    scheduler_timezone: str = "UTC"
    
    # Monitoring
    metrics_port: int = 9093
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True  # Allow both alias and field name


settings = Settings()

