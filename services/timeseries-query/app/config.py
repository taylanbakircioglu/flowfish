"""Configuration for Timeseries Query Service

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.

Version: 1.2.0 - Fixed deployment manifest tag replacement
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service info
    version: str = "1.0.0"
    service_name: str = "timeseries-query"
    host: str = "0.0.0.0"
    port: int = 8002
    log_level: str = "INFO"
    
    # gRPC (optional - for inter-service communication)
    grpc_port: int = 5004
    
    # ClickHouse - credentials from env vars
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000
    clickhouse_user: str = Field(default="default", description="From CLICKHOUSE_USER env var")
    clickhouse_password: str = Field(default="", description="From CLICKHOUSE_PASSWORD env var (secret)")
    clickhouse_database: str = "flowfish"
    
    # Query settings
    query_timeout: int = 60  # seconds (increased for large analyses)
    max_results: int = 100000  # Increased for large multi-cluster analyses
    default_limit: int = 1000  # Default pagination limit
    
    # Connection pool
    pool_size: int = 10
    
    # Caching (optional - for future Redis integration)
    cache_enabled: bool = False
    cache_ttl_seconds: int = 60
    
    # Monitoring
    metrics_port: int = 9096
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

