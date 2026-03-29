"""
Cluster Manager Configuration

All credentials MUST come from environment variables (Kubernetes secrets).
No default passwords - service will fail to start if not configured.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "cluster-manager"
    GRPC_PORT: int = 5001
    
    # Database - DATABASE_URL from env var (secret)
    DATABASE_URL: str = Field(default="", description="From DATABASE_URL env var (secret)")
    
    # Redis - REDIS_URL from env var
    REDIS_URL: str = Field(default="redis://redis:6379/0", description="From REDIS_URL env var")
    
    # Kubernetes
    KUBERNETES_SERVICE_HOST: Optional[str] = None
    KUBERNETES_SERVICE_PORT: Optional[str] = None
    
    # Health check
    HEALTH_CHECK_INTERVAL: int = 30  # seconds
    
    # Cache
    CACHE_TTL: int = 60  # seconds
    
    # Debug
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
