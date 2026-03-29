"""
Change Detection Service - Core Business Logic

Provides change detection capabilities:
- Workload changes (added/removed/modified)
- Connection changes (added/removed)
- Configuration changes
- Blast radius calculation
- Risk assessment

This service orchestrates detection across PostgreSQL and Neo4j,
providing a unified change detection interface.

Now includes ACTIVE Kubernetes polling for real-time change detection.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import structlog
import json
import uuid

from database.postgresql import database
from database.neo4j import neo4j_service
from services.kubernetes_service import KubernetesService

logger = structlog.get_logger(__name__)


class ChangeType(str, Enum):
    """Change type enumeration matching frontend expectations"""
    # Legacy types
    WORKLOAD_ADDED = "workload_added"
    WORKLOAD_REMOVED = "workload_removed"
    NAMESPACE_CHANGED = "namespace_changed"
    # K8s API - Workloads
    REPLICA_CHANGED = "replica_changed"
    CONFIG_CHANGED = "config_changed"
    IMAGE_CHANGED = "image_changed"
    LABEL_CHANGED = "label_changed"
    RESOURCE_CHANGED = "resource_changed"
    ENV_CHANGED = "env_changed"
    SPEC_CHANGED = "spec_changed"
    # K8s API - Services
    SERVICE_PORT_CHANGED = "service_port_changed"
    SERVICE_SELECTOR_CHANGED = "service_selector_changed"
    SERVICE_TYPE_CHANGED = "service_type_changed"
    SERVICE_ADDED = "service_added"
    SERVICE_REMOVED = "service_removed"
    # K8s API - Network / Ingress / Route
    NETWORK_POLICY_ADDED = "network_policy_added"
    NETWORK_POLICY_REMOVED = "network_policy_removed"
    NETWORK_POLICY_CHANGED = "network_policy_changed"
    INGRESS_ADDED = "ingress_added"
    INGRESS_REMOVED = "ingress_removed"
    INGRESS_CHANGED = "ingress_changed"
    ROUTE_ADDED = "route_added"
    ROUTE_REMOVED = "route_removed"
    ROUTE_CHANGED = "route_changed"
    # eBPF - Connections
    CONNECTION_ADDED = "connection_added"
    CONNECTION_REMOVED = "connection_removed"
    PORT_CHANGED = "port_changed"
    # eBPF - Anomalies
    TRAFFIC_ANOMALY = "traffic_anomaly"
    DNS_ANOMALY = "dns_anomaly"
    PROCESS_ANOMALY = "process_anomaly"
    ERROR_ANOMALY = "error_anomaly"


class RiskLevel(str, Enum):
    """Risk level enumeration"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChangeDetectionService:
    """
    Core change detection logic:
    - Workload changes (added/removed/modified)
    - Connection changes (added/removed)
    - Configuration changes
    
    Now includes ACTIVE Kubernetes polling for real-time detection.
    """
    
    def __init__(self):
        self.db = database
        self.neo4j = neo4j_service
        self.k8s_service = KubernetesService()
        self._cluster_configured = set()  # Track which clusters are configured
    
    async def _ensure_cluster_configured(self, cluster_id: int) -> bool:
        """Configure Kubernetes client for cluster if not already done"""
        if cluster_id in self._cluster_configured:
            return True
        
        try:
            # Get cluster connection info from PostgreSQL
            # Note: Live database column names differ from schema file:
            # - api_server_url (not api_url)
            # - kubeconfig_encrypted (not kubeconfig)
            # - token_encrypted (not service_account_token)
            # - ca_cert_encrypted (not ca_cert)
            # - status='active' (not is_active=true)
            query = """
                SELECT id, name, api_server_url, kubeconfig_encrypted, token_encrypted, ca_cert_encrypted, skip_tls_verify
                FROM clusters WHERE id = :cluster_id AND status = 'active'
            """
            cluster = await self.db.fetch_one(query, {"cluster_id": cluster_id})
            
            if not cluster:
                logger.warning("Cluster not found or inactive", cluster_id=cluster_id)
                return False
            
            # Configure the K8s service for this cluster
            # Dictionary keys kept for internal compatibility with kubernetes_service.py
            self.k8s_service._cluster_configs[cluster_id] = {
                "api_url": cluster["api_server_url"],
                "kubeconfig": cluster.get("kubeconfig_encrypted"),
                "service_account_token": cluster.get("token_encrypted"),
                "ca_cert": cluster.get("ca_cert_encrypted"),
                "skip_tls_verify": cluster.get("skip_tls_verify", False)
            }
            
            self._cluster_configured.add(cluster_id)
            logger.info("Cluster configured for change detection", cluster_id=cluster_id)
            return True
            
        except Exception as e:
            logger.error("Failed to configure cluster", cluster_id=cluster_id, error=str(e))
            return False

    async def detect_all_changes(
        self, 
        cluster_id: int, 
        analysis_id: Optional[int] = None,
        since_minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Main detection function - detect all change types
        
        NOW POLLS KUBERNETES DIRECTLY and compares with stored state.
        
        Args:
            cluster_id: Cluster to analyze
            analysis_id: Optional analysis filter
            since_minutes: Look back window in minutes (for fallback DB checks)
            
        Returns:
            List of detected changes
        """
        since = datetime.utcnow() - timedelta(minutes=since_minutes)
        all_changes = []
        
        try:
            # Ensure cluster is configured for K8s API access
            if not await self._ensure_cluster_configured(cluster_id):
                logger.warning("Skipping change detection - cluster not configured", cluster_id=cluster_id)
                return []
            
            # ACTIVE K8s polling: Detect changes by comparing K8s state with stored state
            k8s_changes = await self.detect_changes_from_kubernetes(cluster_id, analysis_id)
            all_changes.extend(k8s_changes)
            
            # Also check connection changes from communications table (for new connections)
            connection_changes = await self.detect_connection_changes(cluster_id, since, analysis_id)
            all_changes.extend(connection_changes)
            
            logger.info(
                "Change detection completed",
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                total_changes=len(all_changes),
                k8s_changes=len(k8s_changes),
                connection_changes=len(connection_changes)
            )
            
        except Exception as e:
            logger.error("Change detection failed", cluster_id=cluster_id, error=str(e))
        
        return all_changes
    
    async def detect_changes_from_kubernetes(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Poll Kubernetes directly and compare with stored PostgreSQL state.
        
        Detects:
        - Replica changes (deployment/statefulset replicas differ)
        - Port changes (service ports differ)
        - New workloads (in K8s but not in DB)
        - Removed workloads (in DB but not in K8s)
        """
        changes = []
        
        try:
            # Get current deployments from Kubernetes
            k8s_deployments = await self.k8s_service.discover_deployments(cluster_id)
            
            # Get current services from Kubernetes
            k8s_services = await self.k8s_service.discover_services(cluster_id)
            
            # Get stored state from PostgreSQL
            stored_workloads = await self._get_stored_workloads(cluster_id)
            
            # Compare deployments
            deployment_changes = await self._compare_deployments(
                cluster_id, k8s_deployments, stored_workloads, analysis_id
            )
            changes.extend(deployment_changes)
            
            # Compare services (for port changes)
            service_changes = await self._compare_services(
                cluster_id, k8s_services, stored_workloads, analysis_id
            )
            changes.extend(service_changes)
            
            logger.debug(
                "K8s polling completed",
                cluster_id=cluster_id,
                k8s_deployments=len(k8s_deployments),
                k8s_services=len(k8s_services),
                changes_found=len(changes)
            )
            
        except Exception as e:
            logger.error("K8s polling failed", cluster_id=cluster_id, error=str(e))
        
        return changes
    
    async def _get_stored_workloads(self, cluster_id: int) -> Dict[str, Any]:
        """Get stored workloads from PostgreSQL indexed by namespace/name"""
        query = """
            SELECT 
                w.id, w.name, w.workload_type, w.replicas, w.ports, w.is_active,
                n.name as namespace_name, w.namespace_id, w.metadata
            FROM workloads w
            JOIN namespaces n ON w.namespace_id = n.id
            WHERE w.cluster_id = :cluster_id AND w.is_active = true
        """
        
        rows = await self.db.fetch_all(query, {"cluster_id": cluster_id})
        
        # Index by "namespace/name/type" for quick lookup
        result = {}
        for row in rows:
            key = f"{row['namespace_name']}/{row['name']}/{row['workload_type']}"
            result[key] = dict(row)
        
        return result
    
    async def _compare_deployments(
        self,
        cluster_id: int,
        k8s_deployments: List[Dict],
        stored_workloads: Dict[str, Any],
        analysis_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Compare K8s deployments with stored state"""
        changes = []
        now = datetime.utcnow()
        
        for k8s_dep in k8s_deployments:
            key = f"{k8s_dep['namespace']}/{k8s_dep['name']}/deployment"
            stored = stored_workloads.get(key)
            
            if not stored:
                # New deployment - not in our DB yet
                # This is handled by the collector, skip here
                continue
            
            # Check replica changes
            k8s_replicas = k8s_dep.get('replicas', 0)
            stored_replicas = stored.get('replicas', 0)
            
            if k8s_replicas != stored_replicas:
                change = {
                    "change_type": ChangeType.REPLICA_CHANGED.value,
                    "target": k8s_dep['name'],
                    "namespace": k8s_dep['namespace'],
                    "namespace_id": stored.get('namespace_id'),
                    "entity_type": "deployment",
                    "entity_id": stored.get('id'),
                    "details": f"Replicas changed from {stored_replicas} to {k8s_replicas}",
                    "detected_at": now,
                    "affected_services": await self.calculate_blast_radius_for_workload(
                        cluster_id, k8s_dep['name'], k8s_dep['namespace']
                    ),
                    "before_state": {"replicas": stored_replicas},
                    "after_state": {"replicas": k8s_replicas},
                    "metadata": {"analysis_id": analysis_id}
                }
                change["risk_level"] = self.assess_risk_level(change)
                changes.append(change)
                
                # Update PostgreSQL with new replica count
                await self._update_workload_replicas(stored['id'], k8s_replicas)
        
        return changes
    
    async def _compare_services(
        self,
        cluster_id: int,
        k8s_services: List[Dict],
        stored_workloads: Dict[str, Any],
        analysis_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Compare K8s services with stored state for port changes"""
        changes = []
        now = datetime.utcnow()
        
        for k8s_svc in k8s_services:
            key = f"{k8s_svc['namespace']}/{k8s_svc['name']}/service"
            stored = stored_workloads.get(key)
            
            if not stored:
                # New service - not in our DB yet
                continue
            
            # Get port lists
            k8s_ports = k8s_svc.get('ports', [])
            stored_ports_raw = stored.get('ports')
            
            # Parse stored ports (might be JSON string)
            if isinstance(stored_ports_raw, str):
                try:
                    stored_ports = json.loads(stored_ports_raw)
                except:
                    stored_ports = []
            elif stored_ports_raw:
                stored_ports = stored_ports_raw
            else:
                stored_ports = []
            
            # Compare ports (simplified - check if port numbers differ)
            k8s_port_set = {p.get('port') for p in k8s_ports if p.get('port')}
            stored_port_set = {p.get('port') for p in stored_ports if p.get('port')}
            
            if k8s_port_set != stored_port_set:
                added_ports = k8s_port_set - stored_port_set
                removed_ports = stored_port_set - k8s_port_set
                
                details = []
                if added_ports:
                    details.append(f"Added ports: {sorted(added_ports)}")
                if removed_ports:
                    details.append(f"Removed ports: {sorted(removed_ports)}")
                
                change = {
                    "change_type": ChangeType.SERVICE_PORT_CHANGED.value,
                    "target": k8s_svc['name'],
                    "namespace": k8s_svc['namespace'],
                    "namespace_id": stored.get('namespace_id'),
                    "entity_type": "service",
                    "entity_id": stored.get('id'),
                    "details": "; ".join(details),
                    "detected_at": now,
                    "affected_services": await self.calculate_blast_radius_for_workload(
                        cluster_id, k8s_svc['name'], k8s_svc['namespace']
                    ),
                    "before_state": {"ports": list(stored_port_set)},
                    "after_state": {"ports": list(k8s_port_set)},
                    "metadata": {"analysis_id": analysis_id}
                }
                change["risk_level"] = self.assess_risk_level(change)
                changes.append(change)
                
                # Update PostgreSQL with new ports
                await self._update_workload_ports(stored['id'], k8s_ports)
        
        return changes
    
    async def _update_workload_replicas(self, workload_id: int, new_replicas: int):
        """Update workload replica count in PostgreSQL"""
        try:
            query = """
                UPDATE workloads 
                SET replicas = :replicas, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """
            await self.db.execute(query, {"id": workload_id, "replicas": new_replicas})
        except Exception as e:
            logger.warning("Failed to update workload replicas", workload_id=workload_id, error=str(e))
    
    async def _update_workload_ports(self, workload_id: int, new_ports: List[Dict]):
        """Update workload ports in PostgreSQL"""
        try:
            query = """
                UPDATE workloads 
                SET ports = :ports, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """
            await self.db.execute(query, {"id": workload_id, "ports": json.dumps(new_ports)})
        except Exception as e:
            logger.warning("Failed to update workload ports", workload_id=workload_id, error=str(e))
    
    async def detect_workload_changes(
        self, 
        cluster_id: int,
        since: datetime,
        analysis_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect workload additions and removals from PostgreSQL
        
        Strategy:
        - New workloads: first_seen > since
        - Removed workloads: is_active = false AND last_seen > since
        """
        changes = []
        
        # Detect new workloads (first_seen within window)
        new_workloads_query = """
        SELECT 
            w.id,
            w.name,
            w.namespace_id,
            n.name as namespace_name,
            w.workload_type,
            w.replicas,
            w.image,
            w.first_seen,
            w.metadata
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id
          AND w.first_seen >= :since
          AND w.is_active = true
        ORDER BY w.first_seen DESC
        """
        
        new_workloads = await self.db.fetch_all(
            new_workloads_query,
            {"cluster_id": cluster_id, "since": since}
        )
        
        for workload in new_workloads:
            # Calculate blast radius for new workload
            affected_count = await self.calculate_blast_radius_for_workload(
                cluster_id, workload["name"], workload["namespace_name"]
            )
            
            change = {
                "change_type": ChangeType.WORKLOAD_ADDED.value,
                "target": workload["name"],
                "namespace": workload["namespace_name"],
                "namespace_id": workload["namespace_id"],
                "entity_type": "workload",
                "entity_id": workload["id"],
                "details": f"New {workload['workload_type']} deployment created" + (
                    f" with {workload['replicas']} replicas" if workload.get('replicas') else ""
                ),
                "detected_at": workload["first_seen"],
                "affected_services": affected_count,
                "before_state": None,
                "after_state": {
                    "name": workload["name"],
                    "type": workload["workload_type"],
                    "replicas": workload.get("replicas"),
                    "image": workload.get("image")
                },
                "metadata": workload.get("metadata", {})
            }
            
            change["risk_level"] = self.assess_risk_level(change)
            changes.append(change)
        
        # Detect removed workloads (recently became inactive)
        removed_workloads_query = """
        SELECT 
            w.id,
            w.name,
            w.namespace_id,
            n.name as namespace_name,
            w.workload_type,
            w.replicas,
            w.last_seen,
            w.metadata
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id
          AND w.is_active = false
          AND w.last_seen >= :since
        ORDER BY w.last_seen DESC
        """
        
        removed_workloads = await self.db.fetch_all(
            removed_workloads_query,
            {"cluster_id": cluster_id, "since": since}
        )
        
        for workload in removed_workloads:
            # For removed workloads, estimate affected from historical data
            affected_count = await self._estimate_affected_from_communications(
                cluster_id, workload["id"]
            )
            
            change = {
                "change_type": ChangeType.WORKLOAD_REMOVED.value,
                "target": workload["name"],
                "namespace": workload["namespace_name"],
                "namespace_id": workload["namespace_id"],
                "entity_type": "workload",
                "entity_id": workload["id"],
                "details": f"{workload['workload_type']} deployment deleted, 0 replicas remaining",
                "detected_at": workload["last_seen"],
                "affected_services": affected_count,
                "before_state": {
                    "name": workload["name"],
                    "type": workload["workload_type"],
                    "replicas": workload.get("replicas")
                },
                "after_state": None,
                "metadata": workload.get("metadata", {})
            }
            
            change["risk_level"] = self.assess_risk_level(change)
            changes.append(change)
        
        return changes
    
    async def detect_connection_changes(
        self, 
        cluster_id: int,
        since: datetime,
        analysis_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect connection additions and removals from PostgreSQL communications table
        """
        changes = []
        
        # Detect new connections (first_seen within window)
        new_connections_query = """
        SELECT 
            c.id,
            c.source_workload_id,
            c.destination_workload_id,
            c.destination_port,
            c.protocol,
            c.first_seen,
            c.request_count,
            sw.name as source_name,
            sn.name as source_namespace,
            dw.name as dest_name,
            dn.name as dest_namespace
        FROM communications c
        LEFT JOIN workloads sw ON c.source_workload_id = sw.id
        LEFT JOIN namespaces sn ON sw.namespace_id = sn.id
        LEFT JOIN workloads dw ON c.destination_workload_id = dw.id
        LEFT JOIN namespaces dn ON dw.namespace_id = dn.id
        WHERE c.cluster_id = :cluster_id
          AND c.first_seen >= :since
          AND c.is_active = true
        ORDER BY c.first_seen DESC
        """
        
        new_connections = await self.db.fetch_all(
            new_connections_query,
            {"cluster_id": cluster_id, "since": since}
        )
        
        for conn in new_connections:
            source_display = conn.get("source_name") or "unknown"
            dest_display = conn.get("dest_name") or "unknown"
            
            change = {
                "change_type": ChangeType.CONNECTION_ADDED.value,
                "target": f"{source_display} → {dest_display}",
                "namespace": conn.get("source_namespace") or conn.get("dest_namespace") or "unknown",
                "namespace_id": None,
                "entity_type": "communication",
                "entity_id": conn["id"],
                "details": f"New {conn['protocol']} connection on port {conn['destination_port']}",
                "detected_at": conn["first_seen"],
                "affected_services": 2,  # Source and destination
                "before_state": None,
                "after_state": {
                    "source": source_display,
                    "destination": dest_display,
                    "port": conn["destination_port"],
                    "protocol": conn["protocol"]
                },
                "metadata": {
                    "source_namespace": conn.get("source_namespace"),
                    "dest_namespace": conn.get("dest_namespace"),
                    "request_count": conn.get("request_count", 0)
                }
            }
            
            change["risk_level"] = self.assess_risk_level(change)
            changes.append(change)
        
        # Detect removed connections (recently became inactive)
        removed_connections_query = """
        SELECT 
            c.id,
            c.source_workload_id,
            c.destination_workload_id,
            c.destination_port,
            c.protocol,
            c.last_seen,
            sw.name as source_name,
            sn.name as source_namespace,
            dw.name as dest_name,
            dn.name as dest_namespace
        FROM communications c
        LEFT JOIN workloads sw ON c.source_workload_id = sw.id
        LEFT JOIN namespaces sn ON sw.namespace_id = sn.id
        LEFT JOIN workloads dw ON c.destination_workload_id = dw.id
        LEFT JOIN namespaces dn ON dw.namespace_id = dn.id
        WHERE c.cluster_id = :cluster_id
          AND c.is_active = false
          AND c.last_seen >= :since
        ORDER BY c.last_seen DESC
        """
        
        removed_connections = await self.db.fetch_all(
            removed_connections_query,
            {"cluster_id": cluster_id, "since": since}
        )
        
        for conn in removed_connections:
            source_display = conn.get("source_name") or "unknown"
            dest_display = conn.get("dest_name") or "unknown"
            
            change = {
                "change_type": ChangeType.CONNECTION_REMOVED.value,
                "target": f"{source_display} → {dest_display}",
                "namespace": conn.get("source_namespace") or conn.get("dest_namespace") or "unknown",
                "namespace_id": None,
                "entity_type": "communication",
                "entity_id": conn["id"],
                "details": f"Connection no longer observed on port {conn['destination_port']}",
                "detected_at": conn["last_seen"],
                "affected_services": 1,
                "before_state": {
                    "source": source_display,
                    "destination": dest_display,
                    "port": conn["destination_port"],
                    "protocol": conn["protocol"]
                },
                "after_state": None,
                "metadata": {
                    "source_namespace": conn.get("source_namespace"),
                    "dest_namespace": conn.get("dest_namespace")
                }
            }
            
            change["risk_level"] = self.assess_risk_level(change)
            changes.append(change)
        
        return changes
    
    async def detect_replica_changes(
        self, 
        cluster_id: int,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """
        Detect replica count changes from PostgreSQL workloads table
        
        Detects:
        - Workloads scaled to 0 (replicas = 0 but is_active = true)
        - Workloads with replica changes tracked in metadata
        - Recently updated workloads where replicas differ from metadata.previous_replicas
        """
        changes = []
        
        # Detect workloads scaled to 0 (still active but no replicas)
        scaled_down_query = """
        SELECT 
            w.id,
            w.name,
            w.namespace_id,
            n.name as namespace_name,
            w.workload_type,
            w.replicas,
            w.updated_at,
            w.metadata
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id
          AND w.is_active = true
          AND w.replicas = 0
          AND w.updated_at >= :since
          AND w.workload_type IN ('deployment', 'statefulset', 'replicaset')
        ORDER BY w.updated_at DESC
        """
        
        scaled_down = await self.db.fetch_all(
            scaled_down_query,
            {"cluster_id": cluster_id, "since": since}
        )
        
        for workload in scaled_down:
            # Check if we have previous replica count in metadata
            metadata = workload.get("metadata") or {}
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            previous_replicas = metadata.get("previous_replicas", "unknown")
            
            change = {
                "change_type": ChangeType.REPLICA_CHANGED.value,
                "target": workload["name"],
                "namespace": workload["namespace_name"],
                "namespace_id": workload["namespace_id"],
                "entity_type": "workload",
                "entity_id": workload["id"],
                "details": f"{workload['workload_type']} scaled down to 0 replicas",
                "detected_at": workload["updated_at"],
                "affected_services": await self.calculate_blast_radius_for_workload(
                    cluster_id, workload["name"], workload["namespace_name"]
                ),
                "before_state": {"replicas": previous_replicas},
                "after_state": {"replicas": 0},
                "metadata": metadata
            }
            
            change["risk_level"] = self.assess_risk_level(change)
            changes.append(change)
        
        # Also detect workloads with replica changes tracked in metadata
        replica_tracked_query = """
        SELECT 
            w.id,
            w.name,
            w.namespace_id,
            n.name as namespace_name,
            w.workload_type,
            w.replicas,
            w.updated_at,
            w.metadata
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id
          AND w.is_active = true
          AND w.updated_at >= :since
          AND w.metadata::text LIKE '%previous_replicas%'
        ORDER BY w.updated_at DESC
        """
        
        try:
            tracked = await self.db.fetch_all(
                replica_tracked_query,
                {"cluster_id": cluster_id, "since": since}
            )
            
            for workload in tracked:
                metadata = workload.get("metadata") or {}
                if isinstance(metadata, str):
                    import json
                    try:
                        metadata = json.loads(metadata)
                    except:
                        continue
                
                previous_replicas = metadata.get("previous_replicas")
                current_replicas = workload.get("replicas", 0)
                
                # Only create change if replicas actually differ
                if previous_replicas is not None and previous_replicas != current_replicas:
                    change = {
                        "change_type": ChangeType.REPLICA_CHANGED.value,
                        "target": workload["name"],
                        "namespace": workload["namespace_name"],
                        "namespace_id": workload["namespace_id"],
                        "entity_type": "workload",
                        "entity_id": workload["id"],
                        "details": f"Replica count changed from {previous_replicas} to {current_replicas}",
                        "detected_at": workload["updated_at"],
                        "affected_services": await self.calculate_blast_radius_for_workload(
                            cluster_id, workload["name"], workload["namespace_name"]
                        ),
                        "before_state": {"replicas": previous_replicas},
                        "after_state": {"replicas": current_replicas},
                        "metadata": metadata
                    }
                    
                    change["risk_level"] = self.assess_risk_level(change)
                    changes.append(change)
        except Exception as e:
            logger.warning("Failed to query tracked replica changes", error=str(e))
        
        return changes
    
    async def calculate_blast_radius_for_workload(
        self, 
        cluster_id: int,
        workload_name: str,
        namespace: str
    ) -> int:
        """
        Calculate how many services are affected by a workload change
        Uses Neo4j to find connected workloads
        """
        try:
            dependencies = self.neo4j.get_workload_dependencies(
                cluster_id=cluster_id,
                analysis_id=None,
                namespace=namespace,
                workload_name=workload_name
            )
            
            direct_count = len(dependencies.get("direct_dependencies", []))
            indirect_count = len(dependencies.get("indirect_dependencies", []))
            
            # Return direct dependencies count as primary affected services
            return direct_count
            
        except Exception as e:
            logger.warning(
                "Blast radius calculation failed",
                workload=workload_name,
                namespace=namespace,
                error=str(e)
            )
            return 0
    
    async def _estimate_affected_from_communications(
        self,
        cluster_id: int,
        workload_id: int
    ) -> int:
        """
        Estimate affected services from historical communication records
        """
        query = """
        SELECT COUNT(DISTINCT 
            CASE 
                WHEN c.source_workload_id = :workload_id THEN c.destination_workload_id
                ELSE c.source_workload_id
            END
        ) as affected_count
        FROM communications c
        WHERE c.cluster_id = :cluster_id
          AND (c.source_workload_id = :workload_id OR c.destination_workload_id = :workload_id)
        """
        
        result = await self.db.fetch_one(query, {
            "cluster_id": cluster_id,
            "workload_id": workload_id
        })
        
        return result.get("affected_count", 0) if result else 0
    
    def assess_risk_level(self, change: Dict[str, Any]) -> str:
        """
        Determine risk level based on change type and impact
        
        Risk Assessment Rules:
        - CRITICAL: Workload removal with >5 affected services, port changes with >5 affected
        - HIGH: Workload removal with >2 affected, port changes with >2 affected
        - MEDIUM: Connection removal, config changes, workload removal with <=2 affected
        - LOW: Additions (workload/connection), replica changes
        """
        change_type = change.get("change_type", "")
        affected_count = change.get("affected_services", 0)
        
        # High risk changes
        if change_type in [ChangeType.WORKLOAD_REMOVED.value, ChangeType.PORT_CHANGED.value]:
            if affected_count > 5:
                return RiskLevel.CRITICAL.value
            elif affected_count > 2:
                return RiskLevel.HIGH.value
            return RiskLevel.MEDIUM.value
        
        # Medium risk changes
        if change_type in [ChangeType.CONNECTION_REMOVED.value, ChangeType.CONFIG_CHANGED.value]:
            if affected_count > 5:
                return RiskLevel.HIGH.value
            return RiskLevel.MEDIUM.value
        
        # Low risk changes
        if change_type in [
            ChangeType.WORKLOAD_ADDED.value, 
            ChangeType.CONNECTION_ADDED.value, 
            ChangeType.REPLICA_CHANGED.value
        ]:
            return RiskLevel.LOW.value
        
        return RiskLevel.MEDIUM.value
    
    async def record_change_event(
        self,
        cluster_id: int,
        change: Dict[str, Any],
        analysis_id: Optional[int] = None,
        changed_by: str = "auto-discovery"
    ) -> Optional[str]:
        """
        Record a detected change by publishing to RabbitMQ -> ClickHouse
        
        NOTE: PostgreSQL change_events table removed. Events stored only in ClickHouse.
        NOTE: Checks change_detection_enabled flag on analysis before recording.
        
        Returns:
            Event ID (UUID string) on success, or None on failure/skipped
        """
        # Check if change detection is enabled for this analysis
        if analysis_id:
            try:
                analysis_check = await self.db.fetch_one(
                    "SELECT change_detection_enabled FROM analyses WHERE id = :id",
                    {"id": analysis_id}
                )
                if analysis_check and not analysis_check.get("change_detection_enabled", True):
                    logger.debug(
                        "Change detection disabled for analysis, skipping",
                        analysis_id=analysis_id,
                        change_type=change.get("change_type")
                    )
                    return None
            except Exception as e:
                # If we can't check, proceed anyway (default: enabled)
                logger.warning("Failed to check change_detection_enabled", error=str(e))
        
        try:
            from services.change_event_publisher import publish_change_event
            
            event_id = str(uuid.uuid4())
            
            # Build event for RabbitMQ -> ClickHouse
            rabbitmq_event = {
                "event_id": event_id,
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "change_type": change.get("change_type"),
                "risk_level": change.get("risk_level", "medium"),
                "target": change.get("target"),
                "target_name": change.get("target"),
                "namespace": change.get("namespace", ""),
                "target_namespace": change.get("namespace", ""),
                "entity_type": change.get("entity_type", "workload"),
                "entity_id": change.get("entity_id", 0),
                "namespace_id": change.get("namespace_id"),
                "before_state": change.get("before_state", {}),
                "after_state": change.get("after_state", {}),
                "affected_services": change.get("affected_services", 0),
                "blast_radius": change.get("blast_radius", 0),
                "changed_by": changed_by,
                "details": change.get("details", ""),
                "detected_at": change.get("detected_at", datetime.utcnow()).isoformat() if isinstance(change.get("detected_at"), datetime) else change.get("detected_at"),
                "metadata": change.get("metadata", {})
            }
            
            success = await publish_change_event(rabbitmq_event)
            
            if success:
                logger.info(
                    "Change event published to ClickHouse",
                    event_id=event_id,
                    change_type=change.get("change_type"),
                    target=change.get("target")
                )
                return event_id
            else:
                logger.warning(
                    "Failed to publish change event",
                    change_type=change.get("change_type"),
                    target=change.get("target")
                )
                return None
                
        except Exception as e:
            logger.error("Failed to record change event", error=str(e), change=change)
            return None
    
    async def get_changes_from_database(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        change_types: Optional[List[str]] = None,
        risk_levels: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fetch recorded changes from PostgreSQL
        
        Returns:
            Tuple of (changes list, total count)
        """
        # Build WHERE conditions
        conditions = ["ce.cluster_id = :cluster_id"]
        params = {"cluster_id": cluster_id, "limit": limit, "offset": offset}
        
        if analysis_id:
            conditions.append("ce.analysis_id = :analysis_id")
            params["analysis_id"] = analysis_id
        
        if start_time:
            conditions.append("ce.detected_at >= :start_time")
            params["start_time"] = start_time
        
        if end_time:
            conditions.append("ce.detected_at <= :end_time")
            params["end_time"] = end_time
        
        if change_types:
            conditions.append("ce.change_type = ANY(:change_types)")
            params["change_types"] = change_types
        
        if risk_levels:
            conditions.append("ce.risk_level = ANY(:risk_levels)")
            params["risk_levels"] = risk_levels
        
        where_clause = " AND ".join(conditions)
        
        # Get total count
        count_query = f"""
        SELECT COUNT(*) as total
        FROM change_events ce
        WHERE {where_clause}
        """
        
        count_result = await self.db.fetch_one(count_query, params)
        total = count_result.get("total", 0) if count_result else 0
        
        # Get paginated results
        data_query = f"""
        SELECT 
            ce.id,
            ce.detected_at as timestamp,
            ce.change_type,
            ce.target,
            ce.entity_type,
            ce.entity_id,
            n.name as namespace,
            ce.change_summary as details,
            ce.risk_level as risk,
            ce.affected_services,
            ce.changed_by,
            ce.before_state,
            ce.after_state,
            ce.metadata,
            ce.status
        FROM change_events ce
        LEFT JOIN namespaces n ON ce.namespace_id = n.id
        WHERE {where_clause}
        ORDER BY ce.detected_at DESC
        LIMIT :limit OFFSET :offset
        """
        
        rows = await self.db.fetch_all(data_query, params)
        
        changes = []
        for row in rows:
            change = {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "change_type": row["change_type"],
                "target": row["target"],
                "namespace": row.get("namespace", "unknown"),
                "details": row.get("details", ""),
                "risk": row.get("risk", "medium"),
                "affected_services": row.get("affected_services", 0),
                "changed_by": row.get("changed_by", "auto-discovery"),
                "metadata": row.get("metadata")
            }
            changes.append(change)
        
        return changes, total
    
    async def get_change_stats(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate statistics from recorded changes
        """
        conditions = ["cluster_id = :cluster_id"]
        params = {"cluster_id": cluster_id}
        
        if analysis_id:
            conditions.append("analysis_id = :analysis_id")
            params["analysis_id"] = analysis_id
        
        if start_time:
            conditions.append("detected_at >= :start_time")
            params["start_time"] = start_time
        
        if end_time:
            conditions.append("detected_at <= :end_time")
            params["end_time"] = end_time
        
        where_clause = " AND ".join(conditions)
        
        # Get counts by type
        type_query = f"""
        SELECT change_type, COUNT(*) as count
        FROM change_events
        WHERE {where_clause}
        GROUP BY change_type
        """
        
        type_results = await self.db.fetch_all(type_query, params)
        by_type = {r["change_type"]: r["count"] for r in type_results}
        
        # Get counts by risk
        risk_query = f"""
        SELECT risk_level, COUNT(*) as count
        FROM change_events
        WHERE {where_clause}
        GROUP BY risk_level
        """
        
        risk_results = await self.db.fetch_all(risk_query, params)
        by_risk = {r["risk_level"]: r["count"] for r in risk_results}
        
        # Get counts by namespace (build WHERE clause with table alias)
        ns_conditions = ["ce.cluster_id = :cluster_id"]
        if analysis_id:
            ns_conditions.append("ce.analysis_id = :analysis_id")
        if start_time:
            ns_conditions.append("ce.detected_at >= :start_time")
        if end_time:
            ns_conditions.append("ce.detected_at <= :end_time")
        
        ns_where_clause = " AND ".join(ns_conditions)
        
        namespace_query = f"""
        SELECT COALESCE(n.name, 'unknown') as namespace, COUNT(*) as count
        FROM change_events ce
        LEFT JOIN namespaces n ON ce.namespace_id = n.id
        WHERE {ns_where_clause}
        GROUP BY n.name
        """
        
        namespace_results = await self.db.fetch_all(namespace_query, params)
        by_namespace = {r["namespace"]: r["count"] for r in namespace_results}
        
        total_changes = sum(by_type.values())
        
        return {
            "total_changes": total_changes,
            "by_type": by_type,
            "by_risk": by_risk,
            "by_namespace": by_namespace
        }
    
    async def get_snapshot_comparison(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate before/after comparison based on changes.
        When analysis_id is provided, uses Neo4j for analysis-specific workload counts.
        """
        # Get current counts - use Neo4j for analysis-specific data when available
        if analysis_id:
            # Get analysis-specific workload count from Neo4j
            try:
                neo4j_workloads = neo4j_service.get_workloads(cluster_id=cluster_id, analysis_id=analysis_id)
                neo4j_communications = neo4j_service.get_communications(cluster_id=cluster_id, analysis_id=analysis_id)
                
                # Always use Neo4j results when analysis_id is provided (even if empty)
                # This ensures users see analysis-specific data, not cluster-wide fallback
                workload_count = len(neo4j_workloads) if neo4j_workloads is not None else 0
                connection_count = len(neo4j_communications) if neo4j_communications is not None else 0
                
                # Get unique namespaces from workloads
                namespaces = set()
                if neo4j_workloads:
                    for w in neo4j_workloads:
                        ns = w.get('namespace')
                        if ns:
                            namespaces.add(ns)
                namespace_count = len(namespaces)
                
                current = {
                    "workloads": workload_count,
                    "connections": connection_count,
                    "namespaces": namespace_count
                }
                logger.debug(
                    "Got analysis-specific counts from Neo4j",
                    analysis_id=analysis_id,
                    workloads=workload_count,
                    connections=connection_count,
                    namespaces=namespace_count
                )
            except Exception as e:
                logger.warning("Failed to get Neo4j counts, falling back to PostgreSQL", error=str(e))
                current = None
        else:
            current = None
        
        # Fallback to PostgreSQL cluster-wide counts
        if not current:
            current_counts_query = """
            SELECT 
                (SELECT COUNT(*) FROM workloads WHERE cluster_id = :cluster_id AND is_active = true) as workloads,
                (SELECT COUNT(*) FROM communications WHERE cluster_id = :cluster_id AND is_active = true) as connections,
                (SELECT COUNT(*) FROM namespaces WHERE cluster_id = :cluster_id) as namespaces
            """
            
            current = await self.db.fetch_one(current_counts_query, {"cluster_id": cluster_id})
            
            if not current:
                current = {"workloads": 0, "connections": 0, "namespaces": 0}
        
        # Get change counts within time range
        conditions = ["cluster_id = :cluster_id"]
        params = {"cluster_id": cluster_id}
        
        if analysis_id:
            conditions.append("analysis_id = :analysis_id")
            params["analysis_id"] = analysis_id
        
        if start_time:
            conditions.append("detected_at >= :start_time")
            params["start_time"] = start_time
        
        if end_time:
            conditions.append("detected_at <= :end_time")
            params["end_time"] = end_time
        
        where_clause = " AND ".join(conditions)
        
        delta_query = f"""
        SELECT 
            SUM(CASE WHEN change_type = 'workload_added' THEN 1 ELSE 0 END) as workloads_added,
            SUM(CASE WHEN change_type = 'workload_removed' THEN 1 ELSE 0 END) as workloads_removed,
            SUM(CASE WHEN change_type = 'connection_added' THEN 1 ELSE 0 END) as connections_added,
            SUM(CASE WHEN change_type = 'connection_removed' THEN 1 ELSE 0 END) as connections_removed
        FROM change_events
        WHERE {where_clause}
        """
        
        deltas = await self.db.fetch_one(delta_query, params)
        
        if not deltas:
            deltas = {
                "workloads_added": 0,
                "workloads_removed": 0,
                "connections_added": 0,
                "connections_removed": 0
            }
        
        # Calculate before state
        workloads_after = current.get("workloads", 0)
        connections_after = current.get("connections", 0)
        
        workloads_before = workloads_after - (deltas.get("workloads_added", 0) or 0) + (deltas.get("workloads_removed", 0) or 0)
        connections_before = connections_after - (deltas.get("connections_added", 0) or 0) + (deltas.get("connections_removed", 0) or 0)
        
        before = {
            "workloads": max(0, workloads_before),
            "connections": max(0, connections_before),
            "namespaces": current.get("namespaces", 0)
        }
        
        after = {
            "workloads": workloads_after,
            "connections": connections_after,
            "namespaces": current.get("namespaces", 0)
        }
        
        # Calculate summary
        added = (deltas.get("workloads_added", 0) or 0) + (deltas.get("connections_added", 0) or 0)
        removed = (deltas.get("workloads_removed", 0) or 0) + (deltas.get("connections_removed", 0) or 0)
        
        return {
            "before": before,
            "after": after,
            "summary": {
                "added": added,
                "removed": removed,
                "modified": 0  # Would need config/replica changes
            }
        }


    # =========================================================================
    # Sprint 5: Impact Analysis Methods
    # =========================================================================
    
    async def analyze_change_impact(
        self,
        cluster_id: int,
        change_id: Optional[int] = None,
        workload_name: Optional[str] = None,
        namespace: Optional[str] = None,
        change_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive impact analysis for a change
        
        Calculates:
        - Full blast radius (direct + indirect + cascade)
        - Impact categories (service_outage, connectivity_loss, cascade_risk)
        - Risk score based on affected services and criticality
        - Graph structure for visualization
        
        Args:
            cluster_id: Cluster to analyze
            change_id: Optional change event ID (will fetch details)
            workload_name: Target workload name
            namespace: Target namespace
            change_type: Type of change for risk assessment
            
        Returns:
            Comprehensive impact analysis result
        """
        logger.info(
            "Analyzing change impact",
            cluster_id=cluster_id,
            change_id=change_id,
            workload=workload_name,
            namespace=namespace
        )
        
        # If change_id provided, fetch the change details
        if change_id:
            change_details = await self._get_change_by_id(change_id)
            if change_details:
                workload_name = workload_name or change_details.get("target")
                namespace = namespace or change_details.get("namespace", "unknown")
                change_type = change_type or change_details.get("change_type")
        
        if not workload_name or not namespace:
            return {
                "error": "workload_name and namespace are required",
                "blast_radius": {"total": 0, "direct": 0, "indirect": 0, "cascade": 0},
                "affected_services": [],
                "impact_graph": {"nodes": [], "edges": []},
                "risk_score": 0,
                "impact_categories": {}
            }
        
        # Get workload dependencies from Neo4j
        dependencies = self.neo4j.get_workload_dependencies(
            cluster_id=cluster_id,
            analysis_id=None,
            namespace=namespace,
            workload_name=workload_name
        )
        
        direct_deps = dependencies.get("direct_dependencies", [])
        indirect_deps = dependencies.get("indirect_dependencies", [])
        
        # Calculate cascade impact (3rd level - services that depend on indirect)
        cascade_deps = await self._calculate_cascade_impact(
            cluster_id, 
            [d.get("id") for d in indirect_deps if d.get("id")]
        )
        
        # Build affected services list with categorization
        affected_services = self._categorize_affected_services(
            workload_name,
            namespace,
            direct_deps,
            indirect_deps,
            cascade_deps,
            change_type
        )
        
        # Build graph structure for visualization
        impact_graph = self._build_impact_graph(
            workload_name,
            namespace,
            direct_deps,
            indirect_deps,
            cascade_deps
        )
        
        # Calculate risk score
        risk_score = self._calculate_impact_risk_score(
            change_type,
            len(direct_deps),
            len(indirect_deps),
            len(cascade_deps),
            dependencies.get("has_external_connections", False)
        )
        
        # Categorize impacts
        impact_categories = self._categorize_impacts(
            change_type,
            direct_deps,
            indirect_deps
        )
        
        return {
            "target": {
                "workload": workload_name,
                "namespace": namespace,
                "change_type": change_type
            },
            "blast_radius": {
                "total": len(direct_deps) + len(indirect_deps) + len(cascade_deps),
                "direct": len(direct_deps),
                "indirect": len(indirect_deps),
                "cascade": len(cascade_deps)
            },
            "affected_services": affected_services,
            "impact_graph": impact_graph,
            "risk_score": risk_score,
            "risk_level": self._score_to_risk_level(risk_score),
            "impact_categories": impact_categories,
            "has_external_connections": dependencies.get("has_external_connections", False),
            "confidence": dependencies.get("confidence", 0.5),
            "recommendations": self._generate_impact_recommendations(
                change_type, risk_score, len(direct_deps), len(indirect_deps)
            )
        }
    
    async def _calculate_cascade_impact(
        self,
        cluster_id: int,
        indirect_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Calculate 3rd-level cascade impact
        Services that depend on the indirect dependencies
        """
        if not indirect_ids:
            return []
        
        try:
            # Query Neo4j for 3rd level dependencies
            cascade_query = """
            MATCH (indirect:Workload)-[comm:COMMUNICATES_WITH]-(cascade:Workload)
            WHERE indirect.id IN $indirect_ids
              AND NOT cascade.id IN $indirect_ids
            RETURN DISTINCT cascade.id as id,
                   cascade.name as name,
                   cascade.namespace as namespace,
                   cascade.kind as kind,
                   comm.port as port,
                   comm.request_count as request_count
            LIMIT 50
            """
            
            cascade_deps = self.neo4j._execute_query(cascade_query, {
                "indirect_ids": indirect_ids
            }) or []
            
            return cascade_deps
            
        except Exception as e:
            logger.warning("Cascade impact calculation failed", error=str(e))
            return []
    
    def _categorize_affected_services(
        self,
        target_workload: str,
        target_namespace: str,
        direct_deps: List[Dict],
        indirect_deps: List[Dict],
        cascade_deps: List[Dict],
        change_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Categorize affected services with impact level and category
        """
        affected = []
        
        # Determine impact characteristics based on change type
        is_removal = change_type in [
            ChangeType.WORKLOAD_REMOVED.value, 
            ChangeType.CONNECTION_REMOVED.value
        ]
        is_connectivity_change = change_type in [
            ChangeType.PORT_CHANGED.value,
            ChangeType.CONNECTION_REMOVED.value
        ]
        
        # Direct dependencies - highest impact
        for dep in direct_deps:
            direction = dep.get("direction", "unknown")
            
            # Incoming traffic = callers, Outgoing = dependencies
            if is_removal:
                if direction == "incoming":
                    impact_category = "service_outage"
                    impact_level = "high"
                else:
                    impact_category = "connectivity_loss"
                    impact_level = "high"
            elif is_connectivity_change:
                impact_category = "connectivity_loss"
                impact_level = "high"
            else:
                impact_category = "performance_degradation"
                impact_level = "medium"
            
            affected.append({
                "name": dep.get("name", "unknown"),
                "namespace": dep.get("namespace", "unknown"),
                "kind": dep.get("kind", "Deployment"),
                "dependency_type": "direct",
                "direction": direction,
                "port": dep.get("port"),
                "protocol": dep.get("protocol", "TCP"),
                "request_count": dep.get("request_count", 0),
                "impact_level": impact_level,
                "impact_category": impact_category,
                "is_external": dep.get("is_external", False)
            })
        
        # Indirect dependencies - medium impact (cascade risk)
        for dep in indirect_deps:
            affected.append({
                "name": dep.get("name", "unknown"),
                "namespace": dep.get("namespace", "unknown"),
                "kind": dep.get("kind", "Deployment"),
                "dependency_type": "indirect",
                "direction": "downstream",
                "port": dep.get("port"),
                "protocol": dep.get("protocol", "TCP"),
                "request_count": dep.get("request_count", 0),
                "impact_level": "medium",
                "impact_category": "cascade_risk",
                "is_external": dep.get("is_external", False)
            })
        
        # Cascade dependencies - low impact (potential cascade)
        for dep in cascade_deps:
            affected.append({
                "name": dep.get("name", "unknown"),
                "namespace": dep.get("namespace", "unknown"),
                "kind": dep.get("kind", "Deployment"),
                "dependency_type": "cascade",
                "direction": "downstream",
                "port": dep.get("port"),
                "protocol": dep.get("protocol", "TCP"),
                "request_count": dep.get("request_count", 0),
                "impact_level": "low",
                "impact_category": "cascade_risk",
                "is_external": dep.get("is_external", False)
            })
        
        return affected
    
    def _build_impact_graph(
        self,
        target_workload: str,
        target_namespace: str,
        direct_deps: List[Dict],
        indirect_deps: List[Dict],
        cascade_deps: List[Dict]
    ) -> Dict[str, Any]:
        """
        Build graph structure for frontend visualization
        
        Returns:
            { nodes: [...], edges: [...] }
        """
        nodes = []
        edges = []
        node_ids = set()
        
        # Target node (center)
        target_id = f"{target_namespace}/{target_workload}"
        nodes.append({
            "id": target_id,
            "name": target_workload,
            "namespace": target_namespace,
            "type": "target",
            "level": 0
        })
        node_ids.add(target_id)
        
        # Direct dependency nodes (level 1)
        for dep in direct_deps:
            dep_id = f"{dep.get('namespace', 'unknown')}/{dep.get('name', 'unknown')}"
            if dep_id not in node_ids:
                nodes.append({
                    "id": dep_id,
                    "name": dep.get("name", "unknown"),
                    "namespace": dep.get("namespace", "unknown"),
                    "type": "direct",
                    "level": 1,
                    "direction": dep.get("direction", "unknown"),
                    "is_external": dep.get("is_external", False)
                })
                node_ids.add(dep_id)
            
            # Edge from target to direct
            direction = dep.get("direction", "outgoing")
            if direction == "incoming":
                edges.append({
                    "source": dep_id,
                    "target": target_id,
                    "port": dep.get("port"),
                    "protocol": dep.get("protocol", "TCP"),
                    "request_count": dep.get("request_count", 0)
                })
            else:
                edges.append({
                    "source": target_id,
                    "target": dep_id,
                    "port": dep.get("port"),
                    "protocol": dep.get("protocol", "TCP"),
                    "request_count": dep.get("request_count", 0)
                })
        
        # Indirect dependency nodes (level 2)
        for dep in indirect_deps:
            dep_id = f"{dep.get('namespace', 'unknown')}/{dep.get('name', 'unknown')}"
            if dep_id not in node_ids:
                nodes.append({
                    "id": dep_id,
                    "name": dep.get("name", "unknown"),
                    "namespace": dep.get("namespace", "unknown"),
                    "type": "indirect",
                    "level": 2,
                    "is_external": dep.get("is_external", False)
                })
                node_ids.add(dep_id)
        
        # Cascade nodes (level 3) - limit to 10 for clarity
        for dep in cascade_deps[:10]:
            dep_id = f"{dep.get('namespace', 'unknown')}/{dep.get('name', 'unknown')}"
            if dep_id not in node_ids:
                nodes.append({
                    "id": dep_id,
                    "name": dep.get("name", "unknown"),
                    "namespace": dep.get("namespace", "unknown"),
                    "type": "cascade",
                    "level": 3,
                    "is_external": dep.get("is_external", False)
                })
                node_ids.add(dep_id)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "levels": 4 if cascade_deps else (3 if indirect_deps else 2)
            }
        }
    
    def _calculate_impact_risk_score(
        self,
        change_type: Optional[str],
        direct_count: int,
        indirect_count: int,
        cascade_count: int,
        has_external: bool
    ) -> float:
        """
        Calculate overall risk score (0-100)
        
        Factors:
        - Change type severity
        - Number of affected services at each level
        - External connectivity
        """
        # Base score from change type
        change_severity = {
            ChangeType.WORKLOAD_REMOVED.value: 40,
            ChangeType.PORT_CHANGED.value: 35,
            ChangeType.CONNECTION_REMOVED.value: 30,
            ChangeType.CONFIG_CHANGED.value: 20,
            ChangeType.REPLICA_CHANGED.value: 10,
            ChangeType.WORKLOAD_ADDED.value: 5,
            ChangeType.CONNECTION_ADDED.value: 5,
            ChangeType.NAMESPACE_CHANGED.value: 15
        }
        
        base_score = change_severity.get(change_type, 15) if change_type else 15
        
        # Add points for affected services
        # Direct: 5 points each, max 25
        direct_score = min(direct_count * 5, 25)
        
        # Indirect: 2 points each, max 15
        indirect_score = min(indirect_count * 2, 15)
        
        # Cascade: 1 point each, max 10
        cascade_score = min(cascade_count, 10)
        
        # External connectivity bonus
        external_score = 10 if has_external else 0
        
        total = base_score + direct_score + indirect_score + cascade_score + external_score
        
        return min(100, total)
    
    def _score_to_risk_level(self, score: float) -> str:
        """Convert risk score to risk level"""
        if score >= 70:
            return RiskLevel.CRITICAL.value
        elif score >= 50:
            return RiskLevel.HIGH.value
        elif score >= 25:
            return RiskLevel.MEDIUM.value
        return RiskLevel.LOW.value
    
    def _categorize_impacts(
        self,
        change_type: Optional[str],
        direct_deps: List[Dict],
        indirect_deps: List[Dict]
    ) -> Dict[str, int]:
        """
        Count services by impact category
        """
        categories = {
            "service_outage": 0,
            "connectivity_loss": 0,
            "cascade_risk": 0,
            "performance_degradation": 0
        }
        
        is_removal = change_type in [
            ChangeType.WORKLOAD_REMOVED.value,
            ChangeType.CONNECTION_REMOVED.value
        ]
        
        # Direct deps
        for dep in direct_deps:
            direction = dep.get("direction", "unknown")
            if is_removal:
                if direction == "incoming":
                    categories["service_outage"] += 1
                else:
                    categories["connectivity_loss"] += 1
            else:
                categories["performance_degradation"] += 1
        
        # Indirect deps = cascade risk
        categories["cascade_risk"] += len(indirect_deps)
        
        return categories
    
    def _generate_impact_recommendations(
        self,
        change_type: Optional[str],
        risk_score: float,
        direct_count: int,
        indirect_count: int
    ) -> List[str]:
        """
        Generate actionable recommendations based on impact analysis
        """
        recommendations = []
        
        if risk_score >= 70:
            recommendations.append("⚠️ CRITICAL: This change is high risk. Proceed with caution in production.")
            recommendations.append("Ensure all dependent services have backups before proceeding.")
        
        if direct_count > 5:
            recommendations.append(f"ℹ️ {direct_count} services will be directly affected. Consider staged rollout.")
        
        if indirect_count > 10:
            recommendations.append(f"ℹ️ {indirect_count} services may be indirectly affected. Enable cascade failure monitoring.")
        
        if change_type == ChangeType.WORKLOAD_REMOVED.value:
            recommendations.append("🗑️ Workload deletion is irreversible. Ensure dependent services handle graceful degradation.")
        
        if change_type == ChangeType.PORT_CHANGED.value:
            recommendations.append("🔌 Port change requires all clients to be updated. Use rolling updates.")
        
        if not recommendations:
            recommendations.append("✅ This change appears to be low risk.")
        
        return recommendations
    
    async def _get_change_by_id(self, change_id: int) -> Optional[Dict[str, Any]]:
        """Fetch change details by ID"""
        query = """
        SELECT 
            ce.id,
            ce.change_type,
            ce.target,
            n.name as namespace,
            ce.risk_level,
            ce.affected_services
        FROM change_events ce
        LEFT JOIN namespaces n ON ce.namespace_id = n.id
        WHERE ce.id = :change_id
        """
        
        result = await self.db.fetch_one(query, {"change_id": change_id})
        return dict(result) if result else None
    
    async def get_correlated_changes(
        self,
        cluster_id: int,
        change_id: int,
        time_window_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Find changes that are correlated with a given change
        
        Correlation criteria:
        - Same cluster, within time window
        - Same namespace or related workloads
        - Same changed_by (same deployment/user)
        
        Args:
            cluster_id: Cluster identifier
            change_id: Reference change ID
            time_window_minutes: Time window for correlation
            
        Returns:
            List of correlated changes
        """
        # Get the reference change
        ref_change = await self._get_change_by_id(change_id)
        if not ref_change:
            return []
        
        query = """
        WITH ref_change AS (
            SELECT 
                ce.id,
                ce.detected_at,
                ce.target,
                n.name as namespace,
                ce.changed_by
            FROM change_events ce
            LEFT JOIN namespaces n ON ce.namespace_id = n.id
            WHERE ce.id = :change_id
        )
        SELECT 
            ce.id,
            ce.detected_at as timestamp,
            ce.change_type,
            ce.target,
            n.name as namespace,
            ce.change_summary as details,
            ce.risk_level as risk,
            ce.affected_services,
            ce.changed_by,
            CASE 
                WHEN ce.changed_by = rc.changed_by THEN 'same_source'
                WHEN n.name = rc.namespace THEN 'same_namespace'
                ELSE 'time_proximity'
            END as correlation_type
        FROM change_events ce
        LEFT JOIN namespaces n ON ce.namespace_id = n.id
        CROSS JOIN ref_change rc
        WHERE ce.cluster_id = :cluster_id
          AND ce.id != :change_id
          AND ce.detected_at BETWEEN rc.detected_at - INTERVAL ':window minutes' 
                                 AND rc.detected_at + INTERVAL ':window minutes'
          AND (
            ce.changed_by = rc.changed_by  -- Same source
            OR n.name = rc.namespace       -- Same namespace
            OR ce.target LIKE '%' || SPLIT_PART(rc.target, '-', 1) || '%'  -- Related workload
          )
        ORDER BY 
            CASE 
                WHEN ce.changed_by = rc.changed_by THEN 1
                WHEN n.name = rc.namespace THEN 2
                ELSE 3
            END,
            ABS(EXTRACT(EPOCH FROM (ce.detected_at - rc.detected_at)))
        LIMIT 20
        """
        
        # Note: The interval syntax above is simplified - actual implementation
        # would need proper parameterization
        try:
            result = await self.db.fetch_all(query.replace(':window', str(time_window_minutes)), {
                "cluster_id": cluster_id,
                "change_id": change_id
            })
            return [dict(row) for row in result] if result else []
        except Exception as e:
            logger.warning("Correlation query failed", error=str(e))
            return []


# Service factory for dependency injection
def get_change_detection_service() -> ChangeDetectionService:
    """
    Factory function for ChangeDetectionService dependency injection
    
    Creates service with its dependencies.
    Can be overridden in tests.
    """
    return ChangeDetectionService()


# Export public API
__all__ = [
    "ChangeDetectionService",
    "ChangeType",
    "RiskLevel",
    "get_change_detection_service"
]
