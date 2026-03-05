"""Configuration for Graph Query Service

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "graph-query"
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"
    
    # gRPC
    grpc_port: int = 5003
    
    # Neo4j - credentials from env vars
    neo4j_bolt_uri: str = "bolt://neo4j:7687"
    neo4j_http_uri: str = "http://neo4j:7474"
    neo4j_user: str = Field(default="neo4j", description="From NEO4J_USER env var")
    neo4j_password: str = Field(default="", description="From NEO4J_PASSWORD env var (secret)")
    neo4j_database: str = "neo4j"
    
    # Query settings
    query_timeout: int = 60  # seconds (increased for large multi-cluster analyses)
    max_results: int = 5000  # Max edges per query type (optimized for browser performance)
    
    # Monitoring
    metrics_port: int = 9095
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

