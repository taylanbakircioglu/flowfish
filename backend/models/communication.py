"""
Communication model for workload interactions
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import relationship
from decimal import Decimal
from models.base import BaseModel
from typing import Dict, Any


class Communication(BaseModel):
    """Communication record between workloads"""
    
    __tablename__ = "communications"
    
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False, index=True)
    
    # Source
    source_namespace_id = Column(Integer, ForeignKey("namespaces.id"), nullable=True)
    source_workload_id = Column(Integer, ForeignKey("workloads.id"), nullable=True, index=True)
    source_ip = Column(INET, nullable=True)
    source_port = Column(Integer, nullable=True)
    
    # Destination
    destination_namespace_id = Column(Integer, ForeignKey("namespaces.id"), nullable=True)
    destination_workload_id = Column(Integer, ForeignKey("workloads.id"), nullable=True, index=True)
    destination_ip = Column(INET, nullable=False, index=True)
    destination_port = Column(Integer, nullable=False, index=True)
    
    # Communication details
    protocol = Column(String(50), nullable=False, index=True)  # 'TCP', 'UDP', 'HTTP', 'HTTPS', 'gRPC'
    
    # Temporal tracking
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False, index=True)
    
    # Traffic metrics
    request_count = Column(BigInteger, default=0)
    request_rate_per_second = Column(String(10), nullable=True)  # Decimal as string
    bytes_transferred = Column(BigInteger, default=0)
    
    # Latency metrics (milliseconds)
    avg_latency_ms = Column(String(10), nullable=True)  # Decimal as string
    p50_latency_ms = Column(String(10), nullable=True)
    p95_latency_ms = Column(String(10), nullable=True)
    p99_latency_ms = Column(String(10), nullable=True)
    
    # Error metrics
    error_count = Column(BigInteger, default=0)
    error_rate = Column(String(5), nullable=True)  # Percentage as string
    
    # Risk scoring
    risk_score = Column(Integer, default=0)  # 0-100
    risk_level = Column(String(20), default="low", index=True)  # 'low', 'medium', 'high', 'critical'
    importance_score = Column(Integer, default=0)
    
    # Classification flags
    is_cross_namespace = Column(Boolean, default=False, index=True)
    is_external = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    
    metadata = Column(JSONB, default={})
    
    # Relationships
    cluster = relationship("Cluster", back_populates="communications")
    source_namespace = relationship("Namespace", foreign_keys=[source_namespace_id])
    source_workload = relationship("Workload", foreign_keys=[source_workload_id], back_populates="outbound_communications")
    destination_namespace = relationship("Namespace", foreign_keys=[destination_namespace_id])
    destination_workload = relationship("Workload", foreign_keys=[destination_workload_id], back_populates="inbound_communications")
    
    @property
    def source_full_name(self) -> str:
        """Get source workload full name"""
        if self.source_workload:
            return self.source_workload.full_name
        elif self.source_ip:
            return str(self.source_ip)
        else:
            return "unknown"
    
    @property
    def destination_full_name(self) -> str:
        """Get destination workload full name"""
        if self.destination_workload:
            return self.destination_workload.full_name
        else:
            return f"{self.destination_ip}:{self.destination_port}"
    
    @property
    def connection_string(self) -> str:
        """Get connection string"""
        return f"{self.source_full_name} -> {self.destination_full_name} ({self.protocol}:{self.destination_port})"
    
    def get_latency_ms(self, percentile: str = "avg") -> float:
        """Get latency in milliseconds"""
        latency_map = {
            "avg": self.avg_latency_ms,
            "p50": self.p50_latency_ms, 
            "p95": self.p95_latency_ms,
            "p99": self.p99_latency_ms
        }
        
        latency_str = latency_map.get(percentile, self.avg_latency_ms)
        if latency_str:
            try:
                return float(latency_str)
            except (ValueError, TypeError):
                return 0.0
        return 0.0
    
    def get_request_rate(self) -> float:
        """Get request rate per second"""
        if self.request_rate_per_second:
            try:
                return float(self.request_rate_per_second)
            except (ValueError, TypeError):
                return 0.0
        return 0.0
    
    def get_error_rate(self) -> float:
        """Get error rate percentage"""
        if self.error_rate:
            try:
                return float(self.error_rate)
            except (ValueError, TypeError):
                return 0.0
        return 0.0
    
    def calculate_risk_score(self) -> int:
        """Calculate risk score based on factors"""
        score = 0
        
        # External communication (40 points)
        if self.is_external:
            score += 40
        
        # Cross-namespace communication (20 points)
        if self.is_cross_namespace:
            score += 20
        
        # Privileged ports (15 points)
        if self.destination_port and self.destination_port < 1024:
            score += 15
        
        # Unencrypted protocols (10 points)
        if self.protocol in ["HTTP", "FTP", "TELNET"]:
            score += 10
        
        # High request rate (10 points)
        if self.get_request_rate() > 1000:
            score += 10
        
        # High error rate (5 points)
        if self.get_error_rate() > 5.0:
            score += 5
        
        return min(score, 100)  # Cap at 100
    
    def get_risk_level(self) -> str:
        """Get risk level based on score"""
        score = self.risk_score or self.calculate_risk_score()
        
        if score < 30:
            return "low"
        elif score < 60:
            return "medium"
        elif score < 80:
            return "high"
        else:
            return "critical"
    
    def to_dict(self):
        """Convert to dictionary with computed fields"""
        data = super().to_dict()
        
        # Add computed properties
        data["source_full_name"] = self.source_full_name
        data["destination_full_name"] = self.destination_full_name
        data["connection_string"] = self.connection_string
        data["avg_latency_ms_float"] = self.get_latency_ms("avg")
        data["request_rate_float"] = self.get_request_rate()
        data["error_rate_float"] = self.get_error_rate()
        
        return data
