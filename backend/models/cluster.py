"""
Cluster and namespace models
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from models.base import BaseModel


class Cluster(BaseModel):
    """Kubernetes/OpenShift cluster model"""
    
    __tablename__ = "clusters"
    
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    cluster_type = Column(String(50), nullable=False)  # 'kubernetes', 'openshift'
    api_url = Column(Text, nullable=False)
    kubeconfig_encrypted = Column(Text, nullable=True)  # Encrypted kubeconfig
    token_encrypted = Column(Text, nullable=True)  # Encrypted SA token
    ca_cert_encrypted = Column(Text, nullable=True)  # Encrypted CA certificate for remote clusters
    skip_tls_verify = Column(Boolean, default=False)  # Skip TLS verification for remote clusters
    
    # Inspector Gadget configuration
    gadget_namespace = Column(String(255), nullable=False)  # Namespace where Inspector Gadget is deployed (from UI)
    gadget_endpoint = Column(Text, nullable=True)  # Deprecated - kept for backward compatibility
    gadget_health_status = Column(String(50), default="unknown")  # 'healthy', 'degraded', 'unhealthy', 'unknown'
    gadget_version = Column(String(50), nullable=True)  # Detected IG version
    
    is_in_cluster = Column(Boolean, default=False)  # Is Flowfish running in this cluster?
    is_active = Column(Boolean, default=True, index=True)
    is_default = Column(Boolean, default=False, index=True)
    connection_type = Column(String(50), default="in-cluster")  # 'in-cluster', 'kubeconfig', 'token'
    kubernetes_version = Column(String(50), nullable=True)
    node_count = Column(Integer, nullable=True)
    pod_count = Column(Integer, nullable=True)
    namespace_count = Column(Integer, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    health_status = Column(String(50), default="unknown")  # 'healthy', 'degraded', 'unhealthy', 'unknown'
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    metadata = Column(JSONB, default={})
    
    # Relationships
    creator = relationship("User")
    namespaces = relationship("Namespace", back_populates="cluster", cascade="all, delete-orphan")
    workloads = relationship("Workload", back_populates="cluster", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="cluster", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="cluster", cascade="all, delete-orphan")
    
    def to_dict(self, include_sensitive: bool = False):
        """Convert to dictionary"""
        data = super().to_dict()
        
        if not include_sensitive:
            data.pop("kubeconfig_encrypted", None)
            data.pop("token_encrypted", None)
        
        return data


class Namespace(BaseModel):
    """Kubernetes namespace model"""
    
    __tablename__ = "namespaces"
    
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    uid = Column(String(255), nullable=True)  # Kubernetes UID
    labels = Column(JSONB, default={})
    annotations = Column(JSONB, default={})
    status = Column(String(50), default="Active")
    
    # Relationships
    cluster = relationship("Cluster", back_populates="namespaces")
    workloads = relationship("Workload", back_populates="namespace", cascade="all, delete-orphan")
    
    @property 
    def full_name(self) -> str:
        """Get cluster/namespace full name"""
        return f"{self.cluster.name}/{self.name}" if self.cluster else self.name
