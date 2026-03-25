"""
Analysis models for wizard-created analyses
Supports multi-cluster analysis scenarios
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from models.base import BaseModel
from typing import Dict, Any, List, Optional
from enum import Enum


class AnalysisStatus(str, Enum):
    """Analysis status enumeration"""
    DRAFT = "draft"
    RUNNING = "running" 
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class Analysis(BaseModel):
    """
    Analysis configuration from wizard
    
    Supports both single-cluster and multi-cluster analysis:
    - cluster_id: Primary cluster (for backward compatibility)
    - cluster_ids: List of all cluster IDs (for multi-cluster)
    """
    
    __tablename__ = "analyses"
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Primary cluster (kept for backward compatibility)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False, index=True)
    
    # Multi-cluster support: array of cluster IDs
    # When multi-cluster, cluster_id is the "primary" cluster, and cluster_ids contains all selected clusters
    cluster_ids = Column(JSONB, nullable=True, default=[])  # List of cluster IDs for multi-cluster analysis
    is_multi_cluster = Column(Boolean, default=False, index=True)  # Flag for multi-cluster analysis
    
    # Wizard Step 1: Scope
    scope_type = Column(String(50), nullable=False)  # 'cluster', 'namespace', 'deployment', 'pod', 'label'
    scope_config = Column(JSONB, nullable=False)  # Scope details - now includes per-cluster scope if multi-cluster
    
    # Wizard Step 2: Gadget configuration
    gadget_config = Column(JSONB, nullable=False, default={})  # Gadget module configuration
    gadget_modules = Column(JSONB, nullable=False, default=[])  # Enabled gadgets (legacy, for backward compatibility)
    
    # Wizard Step 3: Time settings
    time_config = Column(JSONB, nullable=False)  # Time settings
    
    # Wizard Step 4: Output settings
    output_config = Column(JSONB, nullable=False)  # Dashboard, LLM, alerts
    
    # Status
    status = Column(String(50), default=AnalysisStatus.DRAFT, index=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    metadata = Column(JSONB, default={})
    
    # Change Detection Feature Toggle
    # When enabled, infrastructure changes are tracked during analysis
    # Default: True (enabled) - recommended for production environments
    change_detection_enabled = Column(Boolean, default=True, nullable=False)
    
    # Change Detection Strategy and Types (Sprint 6 - eBPF Hybrid Detection)
    # Strategy: baseline (compare against initial), rolling_window (compare recent periods), run_comparison (compare runs)
    change_detection_strategy = Column(String(50), default='baseline', nullable=False)
    # Types: ["all"] or specific types like ["replica_changed", "connection_added", "traffic_anomaly"]
    change_detection_types = Column(JSONB, default=['all'], nullable=False)
    
    # Execution timing - for auto-stop monitoring
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    
    # Scheduling support
    is_scheduled = Column(Boolean, default=False)
    schedule_expression = Column(String(100), nullable=True)
    schedule_duration_seconds = Column(Integer, nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    schedule_run_count = Column(Integer, default=0)
    max_scheduled_runs = Column(Integer, nullable=True)
    
    # Relationships
    cluster = relationship("Cluster", back_populates="analyses")
    creator = relationship("User")
    analysis_runs = relationship("AnalysisRun", back_populates="analysis", cascade="all, delete-orphan")
    
    def get_cluster_ids_list(self) -> List[int]:
        """Get list of all cluster IDs for this analysis"""
        if self.is_multi_cluster and self.cluster_ids:
            return self.cluster_ids
        return [self.cluster_id]
    
    def get_cluster_count(self) -> int:
        """Get number of clusters in this analysis"""
        return len(self.get_cluster_ids_list())
    
    def get_scope_summary(self) -> str:
        """Get human-readable scope summary"""
        cluster_prefix = ""
        if self.is_multi_cluster:
            cluster_count = self.get_cluster_count()
            cluster_prefix = f"[{cluster_count} Clusters] "
        
        if self.scope_type == "cluster":
            if self.is_multi_cluster:
                return f"{cluster_count} Clusters selected"
            return f"Cluster: {self.cluster.name if self.cluster else 'Unknown'}"
        elif self.scope_type == "namespace":
            namespaces = self.scope_config.get("namespaces", [])
            if len(namespaces) == 1:
                return f"{cluster_prefix}Namespace: {namespaces[0]}"
            else:
                return f"{cluster_prefix}Namespaces: {len(namespaces)} selected"
        elif self.scope_type == "deployment":
            deployments = self.scope_config.get("deployments", [])
            return f"{cluster_prefix}Deployments: {len(deployments)} selected"
        elif self.scope_type == "pod":
            pods = self.scope_config.get("pods", [])
            return f"{cluster_prefix}Pods: {len(pods)} selected"
        elif self.scope_type == "label":
            labels = self.scope_config.get("labels", {})
            return f"{cluster_prefix}Labels: {labels}"
        else:
            return f"{cluster_prefix}{self.scope_type}"
    
    def get_enabled_gadgets(self) -> List[str]:
        """Get list of enabled gadget modules"""
        return self.gadget_modules or []
    
    def get_time_mode(self) -> str:
        """Get analysis time mode"""
        return self.time_config.get("mode", "unknown")
    
    def is_continuous(self) -> bool:
        """Check if analysis runs continuously"""
        return self.get_time_mode() == "continuous"
    
    def get_duration_minutes(self) -> int:
        """Get analysis duration in minutes"""
        return self.time_config.get("duration_minutes", 0)
    
    def has_llm_enabled(self) -> bool:
        """Check if LLM analysis is enabled"""
        return self.output_config.get("llm_enabled", False)
    
    def get_enabled_dashboards(self) -> List[str]:
        """Get enabled dashboard list"""
        return self.output_config.get("dashboards", [])
    
    def has_change_detection_enabled(self) -> bool:
        """Check if change detection is enabled for this analysis"""
        return self.change_detection_enabled if self.change_detection_enabled is not None else True


class AnalysisRun(BaseModel):
    """Analysis execution run"""
    
    __tablename__ = "analysis_runs"
    
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False, index=True)
    run_number = Column(Integer, nullable=False)
    status = Column(String(50), default="running")  # 'running', 'completed', 'failed', 'cancelled'
    
    # Timing
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Metrics
    events_collected = Column(BigInteger, default=0)
    workloads_discovered = Column(Integer, default=0)
    communications_discovered = Column(Integer, default=0)
    anomalies_detected = Column(Integer, default=0)
    changes_detected = Column(Integer, default=0)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    logs = Column(JSONB, default=[])
    metadata = Column(JSONB, default={})
    
    # Relationships
    analysis = relationship("Analysis", back_populates="analysis_runs")
    
    @property
    def duration_formatted(self) -> str:
        """Get formatted duration"""
        if not self.duration_seconds:
            return "N/A"
        
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def is_running(self) -> bool:
        """Check if run is currently running"""
        return self.status == "running"
    
    def is_completed(self) -> bool:
        """Check if run completed successfully"""
        return self.status == "completed"
    
    def is_failed(self) -> bool:
        """Check if run failed"""
        return self.status == "failed"
    
    def get_discovery_summary(self) -> Dict[str, int]:
        """Get discovery metrics summary"""
        return {
            "events_collected": self.events_collected or 0,
            "workloads_discovered": self.workloads_discovered or 0,
            "communications_discovered": self.communications_discovered or 0,
            "anomalies_detected": self.anomalies_detected or 0,
            "changes_detected": self.changes_detected or 0
        }
    
    def add_log_entry(self, level: str, message: str, details: Dict[str, Any] = None):
        """Add log entry to run logs"""
        if not self.logs:
            self.logs = []
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        }
        
        if details:
            log_entry["details"] = details
        
        self.logs.append(log_entry)
        
        # Keep only last 100 log entries
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]
