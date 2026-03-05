"""Configuration for API Gateway Service

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings - credentials from env vars"""
    
    # Service
    service_name: str = "flowfish-api-gateway"
    api_version: str = "v1"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    
    # CORS
    cors_origins: list = ["http://localhost:3000", "http://localhost:8080"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]
    
    # JWT Authentication - secret from SECRET_KEY env var
    secret_key: str = Field(default="", description="From SECRET_KEY env var (secret)")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # PostgreSQL - credentials from env vars
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    postgres_user: str = Field(default="", description="From POSTGRES_USER env var")
    postgres_password: str = Field(default="", description="From POSTGRES_PASSWORD env var (secret)")
    postgres_database: str = "flowfish"
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
    
    # Microservices gRPC endpoints
    cluster_manager_host: str = "cluster-manager"
    cluster_manager_port: int = 5001
    
    analysis_orchestrator_host: str = "analysis-orchestrator"
    analysis_orchestrator_port: int = 5002
    
    ingestion_service_host: str = "ingestion-service"
    ingestion_service_port: int = 5000
    
    # HTTP Service endpoints
    graph_query_url: str = "http://graph-query:8001"
    
    # Monitoring
    metrics_port: int = 9090
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

