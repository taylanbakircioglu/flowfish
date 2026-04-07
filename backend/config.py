"""
Flowfish Backend Configuration
Environment variables and application settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from typing import List, Optional
import os
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # =========================================================================
    # Application Settings
    # =========================================================================
    
    APP_NAME: str = Field(default="Flowfish Platform", description="Application name")
    ENVIRONMENT: str = Field(default="development", description="Environment (development, staging, production)")
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    
    # =========================================================================
    # Server Settings
    # =========================================================================
    
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    
    # =========================================================================
    # Database Connections
    # =========================================================================
    
    # PostgreSQL
    DATABASE_URL: str = Field(
        description="PostgreSQL connection URL",
        example="postgresql://user:pass@localhost:5432/flowfish"
    )
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_POOL_TIMEOUT: int = Field(default=30, description="Database connection timeout")
    
    # Redis
    REDIS_URL: str = Field(
        description="Redis connection URL",
        example="redis://localhost:6379/0"
    )
    REDIS_POOL_SIZE: int = Field(default=10, description="Redis connection pool size")
    
    # ClickHouse
    # NOTE: Credentials must come from environment variables or secrets
    # No default passwords in production code
    CLICKHOUSE_URL: str = Field(
        description="ClickHouse connection URL",
        example="http://localhost:8123"
    )
    CLICKHOUSE_USER: str = Field(
        default="default",  # ClickHouse default user (no password)
        description="ClickHouse user (from CLICKHOUSE_USER env var)"
    )
    CLICKHOUSE_PASSWORD: str = Field(
        default="",  # Empty = no auth or use default user
        description="ClickHouse password (from CLICKHOUSE_PASSWORD env var or secret)"
    )
    CLICKHOUSE_DATABASE: str = Field(
        default="flowfish",
        description="ClickHouse database name"
    )
    
    # Neo4j
    NEO4J_BOLT_URI: str = Field(
        description="Neo4j Bolt URI",
        example="bolt://localhost:7687"
    )
    NEO4J_HTTP_URI: str = Field(
        default="http://localhost:7474",
        description="Neo4j HTTP URI (for browser access)"
    )
    NEO4J_USER: str = Field(default="neo4j", description="Neo4j user")
    NEO4J_PASSWORD: str = Field(description="Neo4j password")
    NEO4J_DATABASE: str = Field(default="neo4j", description="Neo4j database name")
    
    # =========================================================================
    # Security Settings
    # =========================================================================
    
    SECRET_KEY: str = Field(description="JWT secret key")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    JWT_EXPIRATION_HOURS: int = Field(default=8, description="JWT token expiration in hours")
    
    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Allowed CORS origins (comma-separated)"
    )
    
    # Trusted hosts
    TRUSTED_HOSTS: Optional[str] = Field(
        default=None,
        description="Trusted hosts (comma-separated)"
    )
    
    # =========================================================================
    # Kubernetes Settings
    # =========================================================================
    
    # Kubernetes API
    KUBECONFIG_PATH: Optional[str] = Field(default=None, description="Path to kubeconfig file")
    IN_CLUSTER_CONFIG: bool = Field(default=True, description="Use in-cluster Kubernetes config")
    
    # Inspektor Gadget
    # NOTE: GADGET_NAMESPACE is now per-cluster, stored in database, provided from UI
    GADGET_IMAGE: str = Field(
        default="ghcr.io/inspektor-gadget/inspektor-gadget:v0.50.1",  # ring buffer fix + socket cleanup
        description="Inspektor Gadget image (used for version reference only)"
    )
    GADGET_SUPPORTED_VERSION: str = Field(
        default="v0.50.1",
        description="Latest supported gadget version (for upgrade badge in UI)"
    )
    GADGET_MIN_SUPPORTED_VERSION: str = Field(
        default="v0.46.0",
        description="Minimum supported gadget version for Flowfish compatibility"
    )
    
    # =========================================================================
    # Service Endpoints
    # NOTE: These MUST be configured via environment variables in production.
    # Default values are ONLY for local development. 
    # In Kubernetes/OpenShift, set via ConfigMap (03-configmaps.yaml)
    # =========================================================================
    
    # gRPC Service Endpoints
    CLUSTER_MANAGER_GRPC: str = Field(
        default="cluster-manager:5001",
        description="Cluster Manager gRPC endpoint. Set via ConfigMap in production.",
        json_schema_extra={"env": "CLUSTER_MANAGER_GRPC"}
    )
    ANALYSIS_ORCHESTRATOR_GRPC: str = Field(
        default="analysis-orchestrator:5002",
        description="Analysis Orchestrator gRPC endpoint. Set via ConfigMap in production.",
        json_schema_extra={"env": "ANALYSIS_ORCHESTRATOR_GRPC"}
    )
    INGESTION_SERVICE_GRPC: str = Field(
        default="ingestion-service:5000",
        description="Ingestion Service gRPC endpoint. Set via ConfigMap in production.",
        json_schema_extra={"env": "INGESTION_SERVICE_GRPC"}
    )
    
    # HTTP Service Endpoints
    GRAPH_QUERY_URL: str = Field(
        default="http://graph-query:8001",
        description="Graph Query Service HTTP endpoint. Set via ConfigMap in production.",
        json_schema_extra={"env": "GRAPH_QUERY_URL"}
    )
    TIMESERIES_QUERY_URL: str = Field(
        default="http://timeseries-query:8002",
        description="Timeseries Query Service HTTP endpoint. Set via ConfigMap in production.",
        json_schema_extra={"env": "TIMESERIES_QUERY_URL"}
    )
    
    # =========================================================================
    # Feature Flags
    # =========================================================================
    
    ENABLE_LLM_ANALYSIS: bool = Field(default=False, description="Enable LLM-powered anomaly detection")
    ENABLE_ANOMALY_DETECTION: bool = Field(default=True, description="Enable anomaly detection")
    ENABLE_CHANGE_DETECTION: bool = Field(default=True, description="Enable change detection")
    ENABLE_WEBHOOK: bool = Field(default=True, description="Enable webhook notifications")
    
    # Change Detection Architecture (ClickHouse-only mode)
    # NOTE: PostgreSQL change_events table removed. All events stored in ClickHouse.
    RUN_BASED_FILTERING_ENABLED: bool = Field(
        default=True, 
        description="Enable run-based filtering UI components"
    )
    
    # =========================================================================
    # RabbitMQ Settings (for Change Events Publisher)
    # =========================================================================
    
    RABBITMQ_HOST: str = Field(default="rabbitmq", description="RabbitMQ host")
    RABBITMQ_PORT: int = Field(default=5672, description="RabbitMQ port")
    RABBITMQ_USER: str = Field(default="", description="RabbitMQ user")
    RABBITMQ_PASSWORD: str = Field(default="", description="RabbitMQ password")
    RABBITMQ_VHOST: str = Field(default="/", description="RabbitMQ virtual host")
    
    # =========================================================================
    # LLM Integration (Optional)
    # =========================================================================
    
    LLM_PROVIDER: str = Field(default="openai", description="LLM provider (openai, anthropic, azure)")
    LLM_API_KEY: Optional[str] = Field(default=None, description="LLM API key")
    LLM_MODEL: str = Field(default="gpt-4", description="LLM model name")
    LLM_TEMPERATURE: float = Field(default=0.7, description="LLM temperature")
    LLM_MAX_TOKENS: int = Field(default=2000, description="LLM max tokens")
    LLM_TIMEOUT_SECONDS: int = Field(default=30, description="LLM request timeout")
    
    # =========================================================================
    # Data Collection Settings
    # =========================================================================
    
    DEFAULT_COLLECTION_INTERVAL_SECONDS: int = Field(
        default=5, 
        description="Default eBPF data collection interval"
    )
    MAX_CONCURRENT_ANALYSES: int = Field(
        default=5, 
        description="Maximum concurrent analyses"
    )
    DATA_RETENTION_DAYS: int = Field(
        default=30, 
        description="Data retention period in days"
    )
    
    # =========================================================================
    # Performance Settings
    # =========================================================================
    
    # Rate limiting
    RATE_LIMIT_PER_HOUR: int = Field(default=1000, description="API rate limit per hour")
    RATE_LIMIT_BURST: int = Field(default=100, description="Rate limit burst size")
    
    # Cache settings
    CACHE_TTL_SECONDS: int = Field(default=300, description="Default cache TTL")
    
    # =========================================================================
    # Cluster Health Monitoring
    # =========================================================================
    
    CLUSTER_HEALTH_CHECK_INTERVAL: int = Field(
        default=120, 
        description="Gadget health check interval in seconds (2 minutes) - lightweight check"
    )
    CLUSTER_RESOURCE_SYNC_INTERVAL: int = Field(
        default=600, 
        description="Cluster resource sync interval in seconds (10 minutes) - heavy operation"
    )
    CLUSTER_HEALTH_CIRCUIT_BREAKER_THRESHOLD: int = Field(
        default=5, 
        description="Number of failures before circuit breaker opens"
    )
    CLUSTER_HEALTH_CIRCUIT_BREAKER_RESET: int = Field(
        default=300, 
        description="Seconds before trying a failed cluster again (5 minutes)"
    )
    
    # =========================================================================
    # Export/Import Settings
    # =========================================================================
    
    MAX_EXPORT_RECORDS: int = Field(default=1000000, description="Maximum records per export")
    EXPORT_STORAGE_PATH: str = Field(default="/tmp/exports", description="Export file storage path")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @model_validator(mode='after')
    def validate_production_config(self) -> 'Settings':
        """Validate that critical settings are properly configured in production"""
        if self.ENVIRONMENT.lower() == 'production':
            # Service endpoints that must be explicitly configured
            service_endpoints = {
                'CLUSTER_MANAGER_GRPC': self.CLUSTER_MANAGER_GRPC,
                'ANALYSIS_ORCHESTRATOR_GRPC': self.ANALYSIS_ORCHESTRATOR_GRPC,
                'INGESTION_SERVICE_GRPC': self.INGESTION_SERVICE_GRPC,
                'GRAPH_QUERY_URL': self.GRAPH_QUERY_URL,
                'TIMESERIES_QUERY_URL': self.TIMESERIES_QUERY_URL,
            }
            
            # Default values that indicate unconfigured service
            default_patterns = ['localhost', '127.0.0.1']
            
            warnings = []
            for name, value in service_endpoints.items():
                # Check if value looks like a default/development value
                if any(pattern in value for pattern in default_patterns):
                    warnings.append(f"  - {name}: {value}")
            
            if warnings:
                logger.warning(
                    f"⚠️  PRODUCTION WARNING: The following service endpoints appear to use "
                    f"development defaults. Ensure these are configured via ConfigMap:\n" + 
                    "\n".join(warnings)
                )
        
        return self


# Create settings instance
settings = Settings()

# Derived settings
def get_database_url() -> str:
    """Get PostgreSQL database URL"""
    return settings.DATABASE_URL

def get_redis_url() -> str:
    """Get Redis URL with password if set"""
    return settings.REDIS_URL

def get_clickhouse_config() -> dict:
    """Get ClickHouse configuration"""
    return {
        "host": settings.CLICKHOUSE_URL.replace("http://", "").replace("https://", "").split(":")[0],
        "port": int(settings.CLICKHOUSE_URL.split(":")[-1]) if ":" in settings.CLICKHOUSE_URL else 8123,
        "user": settings.CLICKHOUSE_USER,
        "password": settings.CLICKHOUSE_PASSWORD,
        "database": settings.CLICKHOUSE_DATABASE
    }

def get_neo4j_config() -> dict:
    """Get Neo4j configuration"""
    return {
        "uri": settings.NEO4J_BOLT_URI,
        "user": settings.NEO4J_USER,
        "password": settings.NEO4J_PASSWORD,
        "database": settings.NEO4J_DATABASE,
        "http_uri": settings.NEO4J_HTTP_URI
    }

def log_service_endpoints():
    """Log configured service endpoints for debugging/verification"""
    logger.info("=" * 60)
    logger.info("🔧 Service Endpoints Configuration")
    logger.info("=" * 60)
    logger.info(f"  Environment: {settings.ENVIRONMENT}")
    logger.info(f"  Cluster Manager gRPC: {settings.CLUSTER_MANAGER_GRPC}")
    logger.info(f"  Analysis Orchestrator gRPC: {settings.ANALYSIS_ORCHESTRATOR_GRPC}")
    logger.info(f"  Ingestion Service gRPC: {settings.INGESTION_SERVICE_GRPC}")
    logger.info(f"  Graph Query HTTP: {settings.GRAPH_QUERY_URL}")
    logger.info(f"  Timeseries Query HTTP: {settings.TIMESERIES_QUERY_URL}")
    logger.info("=" * 60)
    logger.info("💡 To override, set environment variables or update ConfigMap")
    logger.info("=" * 60)

# Export settings for import
__all__ = [
    "settings", 
    "get_database_url", 
    "get_redis_url", 
    "get_clickhouse_config", 
    "get_neo4j_config",
    "log_service_endpoints"
]
