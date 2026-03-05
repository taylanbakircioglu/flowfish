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
    kubeconfig_path: str = ""  # empty = use in-cluster config
    kubectl_context: str = ""  # empty = use current context
    
    # Cluster Manager gRPC - used for Pod/Service discovery
    cluster_manager_url: str = "cluster-manager:5001"  # gRPC endpoint
    
    # Performance
    batch_size: int = 100
    batch_timeout: float = 1.0  # seconds
    
    # Monitoring
    metrics_port: int = 9090
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

