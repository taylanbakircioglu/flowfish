"""
Workload models (Pod, Deployment, Service, StatefulSet)
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import relationship
from models.base import BaseModel


class Workload(BaseModel):
    """Kubernetes workload model (Pod, Deployment, Service, StatefulSet)"""
    
    __tablename__ = "workloads"
    
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False, index=True)
    namespace_id = Column(Integer, ForeignKey("namespaces.id"), nullable=False, index=True)
    workload_type = Column(String(50), nullable=False, index=True)  # 'pod', 'deployment', 'statefulset', 'service'
    name = Column(String(255), nullable=False, index=True)
    uid = Column(String(255), nullable=True)  # Kubernetes UID
    labels = Column(JSONB, default={})
    annotations = Column(JSONB, default={})
    
    # Ownership
    owner_kind = Column(String(100), nullable=True)  # e.g., 'Deployment', 'StatefulSet'
    owner_name = Column(String(255), nullable=True)
    owner_uid = Column(String(255), nullable=True)
    
    # Network
    ip_address = Column(INET, nullable=True, index=True)
    ports = Column(JSONB, default=[])  # [{"port": 8080, "protocol": "TCP"}]
    
    # Deployment info
    replicas = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)  # 'Running', 'Pending', 'Failed', etc.
    containers = Column(JSONB, default=[])  # [{"name": "app", "image": "nginx:1.20"}]
    node_name = Column(String(255), nullable=True)
    
    # Temporal tracking
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    metadata = Column(JSONB, default={})
    
    # Relationships
    cluster = relationship("Cluster", back_populates="workloads")
    namespace = relationship("Namespace", back_populates="workloads")
    
    # Communications where this workload is source
    outbound_communications = relationship(
        "Communication",
        foreign_keys="Communication.source_workload_id",
        back_populates="source_workload"
    )
    
    # Communications where this workload is destination
    inbound_communications = relationship(
        "Communication", 
        foreign_keys="Communication.destination_workload_id",
        back_populates="destination_workload"
    )
    
    @property
    def full_name(self) -> str:
        """Get full workload name with namespace"""
        return f"{self.namespace.name}/{self.name}" if self.namespace else self.name
    
    @property
    def display_name(self) -> str:
        """Get display name with type"""
        return f"{self.name} ({self.workload_type})"
    
    def get_label(self, label_key: str, default: str = "") -> str:
        """Get label value"""
        if not self.labels:
            return default
        return self.labels.get(label_key, default)
    
    def has_label(self, label_key: str, label_value: str = None) -> bool:
        """Check if workload has specific label"""
        if not self.labels:
            return False
        if label_value is None:
            return label_key in self.labels
        return self.labels.get(label_key) == label_value
    
    def get_container_images(self) -> List[str]:
        """Get list of container images"""
        if not self.containers:
            return []
        return [container.get("image", "") for container in self.containers if container.get("image")]
    
    def get_exposed_ports(self) -> List[Dict[str, Any]]:
        """Get exposed ports"""
        if not self.ports:
            return []
        return self.ports
    
    def is_stateful(self) -> bool:
        """Check if workload is stateful"""
        return self.workload_type in ["statefulset"] or self.has_label("workload-type", "database")
    
    def get_tier(self) -> str:
        """Get application tier from labels"""
        # Try common tier labels
        tier_labels = ["tier", "app.kubernetes.io/tier", "layer"]
        
        for label in tier_labels:
            if self.has_label(label):
                return self.get_label(label)
        
        # Infer from name/type
        name_lower = self.name.lower()
        if any(x in name_lower for x in ["web", "frontend", "ui", "nginx"]):
            return "frontend"
        elif any(x in name_lower for x in ["api", "backend", "service"]):
            return "backend"
        elif any(x in name_lower for x in ["db", "database", "postgres", "mysql", "mongo", "redis"]):
            return "database"
        elif any(x in name_lower for x in ["cache", "redis", "memcache"]):
            return "cache"
        else:
            return "unknown"
