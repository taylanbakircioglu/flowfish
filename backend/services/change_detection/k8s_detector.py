"""
Kubernetes API Detector Module

Detects infrastructure changes by polling the Kubernetes API
and comparing with stored state in PostgreSQL.

Detects:
- REPLICA_CHANGED: Deployment/StatefulSet replica count changed
- CONFIG_CHANGED: ConfigMap/Secret content changed
- IMAGE_CHANGED: Container image changed
- LABEL_CHANGED: Pod/Service labels changed
- SERVICE_PORT_CHANGED: Service port/targetPort/protocol/name changed
- SERVICE_SELECTOR_CHANGED: Service selector changed (affects routing)
- SERVICE_TYPE_CHANGED: Service type changed (ClusterIP/NodePort/LB)
- SERVICE_ADDED: New service created
- SERVICE_REMOVED: Service deleted
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog
import json

from .base_detector import BaseDetector, Change, ChangeSource, RiskLevel
from services.cluster_connection_manager import cluster_connection_manager
from database.postgresql import database

logger = structlog.get_logger(__name__)


class K8sDetector(BaseDetector):
    """
    Kubernetes API-based change detector.
    
    Polls K8s API every detection cycle (60s default) and compares
    current state with stored state in PostgreSQL.
    
    Changes detected are trustworthy and immediately valid.
    """
    
    # Per-namespace call threshold: above this, use all-namespaces + local filter
    _NS_CALL_THRESHOLD = 20

    # Batch removal safeguard: if more than this fraction of active stored
    # resources are missing from the K8s API response, treat as fetch error.
    _REMOVAL_FRACTION_THRESHOLD = 0.5
    _REMOVAL_MIN_ABSOLUTE = 5

    def __init__(self):
        super().__init__()
        self.source = ChangeSource.K8S_API
        self._last_fetch_had_error = False

    def _should_skip_removals(
        self,
        k8s_count: int,
        active_stored_count: int,
        removal_count: int,
        fetch_had_error: bool,
        resource_type: str,
        cluster_id: int,
    ) -> bool:
        """Return True if removal detection should be skipped (likely false positives).

        Prevents mass false-positive removals when the K8s API call returns
        incomplete results due to timeouts, RBAC issues, or gRPC errors.
        """
        if fetch_had_error:
            logger.warning(
                "Skipping removal detection due to fetch errors",
                resource_type=resource_type, cluster_id=cluster_id
            )
            return True

        if k8s_count == 0 and active_stored_count > 0:
            logger.warning(
                "K8s API returned 0 items but stored items exist — skipping removal detection",
                resource_type=resource_type,
                cluster_id=cluster_id,
                active_stored=active_stored_count,
            )
            return True

        if (
            removal_count > self._REMOVAL_MIN_ABSOLUTE
            and active_stored_count > 0
            and removal_count > active_stored_count * self._REMOVAL_FRACTION_THRESHOLD
        ):
            logger.warning(
                "Suspicious mass removal detected — skipping removal detection",
                resource_type=resource_type,
                cluster_id=cluster_id,
                removal_count=removal_count,
                active_stored=active_stored_count,
                k8s_count=k8s_count,
            )
            return True

        return False

    async def _fetch_scoped(
        self,
        fetch_fn,
        cluster_id: int,
        namespace_scope: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch resources respecting analysis scope.

        When namespace_scope is provided and small (≤ threshold), makes
        per-namespace API calls so the K8s API only returns relevant objects.
        For cluster-wide analyses or very large scopes, falls back to a
        single all-namespaces call + local filter.

        Sets ``self._last_fetch_had_error`` so callers can skip removal
        detection when data may be incomplete due to API failures.
        """
        self._last_fetch_had_error = False
        if namespace_scope and len(namespace_scope) <= self._NS_CALL_THRESHOLD:
            results: List[Dict[str, Any]] = []
            for ns in namespace_scope:
                try:
                    items = await fetch_fn(cluster_id, ns)
                    if items is None:
                        self._last_fetch_had_error = True
                        continue
                    results.extend(items)
                except Exception as e:
                    self._last_fetch_had_error = True
                    logger.warning(
                        "Scoped fetch failed for namespace",
                        namespace=ns, error=str(e)
                    )
            return results
        else:
            items = await fetch_fn(cluster_id, None)
            if items is None:
                self._last_fetch_had_error = True
                return []
            if namespace_scope:
                ns_set = set(namespace_scope)
                items = [i for i in items if i.get('namespace') in ns_set]
            return items

    async def _get_deployments_safe(
        self,
        cluster_id: int,
        namespace: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get deployments via ClusterConnectionManager. Returns None on error."""
        try:
            deployments = await cluster_connection_manager.get_deployments(cluster_id, namespace)

            for dep in deployments:
                dep["workload_type"] = "deployment"
                if "available_replicas" in dep and "ready_replicas" not in dep:
                    dep["ready_replicas"] = dep["available_replicas"]

            return deployments

        except Exception as e:
            logger.error(
                "Failed to get deployments via ClusterConnectionManager",
                cluster_id=cluster_id, namespace=namespace, error=str(e)
            )
            return None

    async def _get_statefulsets_safe(
        self,
        cluster_id: int,
        namespace: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get statefulsets via ClusterConnectionManager. Returns None on error."""
        try:
            statefulsets = await cluster_connection_manager.get_statefulsets(cluster_id, namespace)
            for sts in statefulsets:
                sts["workload_type"] = "statefulset"
            return statefulsets
        except Exception as e:
            logger.error(
                "Failed to get statefulsets via ClusterConnectionManager",
                cluster_id=cluster_id, namespace=namespace, error=str(e)
            )
            return None

    async def _get_all_workloads(
        self,
        cluster_id: int,
        namespace: Optional[str] = None,
        namespace_scope: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get both deployments and statefulsets, scoped to analysis namespaces.
        Sets ``_last_fetch_had_error`` if either sub-fetch encountered errors."""
        deployments = await self._fetch_scoped(
            self._get_deployments_safe, cluster_id, namespace_scope
        )
        dep_error = self._last_fetch_had_error
        statefulsets = await self._fetch_scoped(
            self._get_statefulsets_safe, cluster_id, namespace_scope
        )
        self._last_fetch_had_error = self._last_fetch_had_error or dep_error
        return deployments + statefulsets
    
    async def detect(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int] = None,
        run_number: Optional[int] = None,
        enabled_types: Optional[List[str]] = None,
        namespace_scope: Optional[List[str]] = None,
        **kwargs
    ) -> List[Change]:
        """
        Detect infrastructure changes from Kubernetes API.
        
        Args:
            cluster_id: The cluster to analyze
            analysis_id: The analysis ID for context
            run_id: Optional run ID for run-based tracking
            run_number: Optional run number
            enabled_types: List of enabled change types (filters results)
            namespace_scope: Optional list of namespaces to limit detection to
            
        Returns:
            List of detected Change objects
        """
        changes: List[Change] = []
        enabled = enabled_types or ['all']
        
        # Connection is handled by ClusterConnectionManager automatically
        # If connection fails, _get_deployments_safe returns [] and detection continues gracefully
        
        try:
            # Pre-fetch workloads once per cycle to avoid redundant K8s API calls
            # (used by workload, replica, image/spec, and label detection)
            workload_types_needed = (
                {'workload_added', 'workload_removed', 'replica_changed',
                 'image_changed', 'resource_changed', 'env_changed', 'spec_changed',
                 'label_changed'}
            )
            cached_workloads = None
            workload_fetch_had_error = False
            if 'all' in enabled or workload_types_needed & set(enabled):
                cached_workloads = await self._get_all_workloads(
                    cluster_id, namespace_scope=namespace_scope
                )
                workload_fetch_had_error = self._last_fetch_had_error

            # Detect workload additions and removals
            if 'all' in enabled or 'workload_added' in enabled or 'workload_removed' in enabled:
                workload_changes = await self._detect_workload_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope, enabled,
                    cached_workloads=cached_workloads,
                    fetch_had_error=workload_fetch_had_error
                )
                changes.extend(workload_changes)
            
            # Detect replica changes
            if 'all' in enabled or 'replica_changed' in enabled:
                replica_changes = await self._detect_replica_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    cached_workloads=cached_workloads
                )
                changes.extend(replica_changes)
            
            # Detect config changes
            if 'all' in enabled or 'config_changed' in enabled:
                config_changes = await self._detect_config_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope
                )
                changes.extend(config_changes)
            
            # Detect container spec changes (image, resource, env, spec_changed)
            spec_types = {'image_changed', 'resource_changed', 'env_changed', 'spec_changed'}
            if 'all' in enabled or spec_types & set(enabled):
                image_changes = await self._detect_image_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    cached_workloads=cached_workloads
                )
                changes.extend(image_changes)
            
            # Detect label changes
            if 'all' in enabled or 'label_changed' in enabled:
                label_changes = await self._detect_label_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    cached_workloads=cached_workloads
                )
                changes.extend(label_changes)
            
            # Detect service changes (port, selector, type, lifecycle)
            service_types = {
                'service_port_changed', 'service_selector_changed',
                'service_type_changed', 'service_added', 'service_removed'
            }
            if 'all' in enabled or service_types & set(enabled):
                svc_changes = await self._detect_service_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope, enabled
                )
                changes.extend(svc_changes)
            
            # Detect NetworkPolicy changes
            np_types = {'network_policy_added', 'network_policy_removed', 'network_policy_changed'}
            if 'all' in enabled or np_types & set(enabled):
                np_changes = await self._detect_hash_resource_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    resource_type='networkpolicy',
                    added_type='network_policy_added',
                    removed_type='network_policy_removed',
                    changed_type='network_policy_changed',
                    fetch_fn=self._get_network_policies_safe,
                    risk_add=RiskLevel.LOW.value,
                    risk_remove=RiskLevel.HIGH.value,
                    risk_change=RiskLevel.MEDIUM.value
                )
                changes.extend(np_changes)

            # Detect Ingress changes
            ing_types = {'ingress_added', 'ingress_removed', 'ingress_changed'}
            if 'all' in enabled or ing_types & set(enabled):
                ing_changes = await self._detect_hash_resource_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    resource_type='ingress',
                    added_type='ingress_added',
                    removed_type='ingress_removed',
                    changed_type='ingress_changed',
                    fetch_fn=self._get_ingresses_safe,
                    risk_add=RiskLevel.LOW.value,
                    risk_remove=RiskLevel.MEDIUM.value,
                    risk_change=RiskLevel.MEDIUM.value
                )
                changes.extend(ing_changes)

            # Detect OpenShift Route changes
            rt_types = {'route_added', 'route_removed', 'route_changed'}
            if 'all' in enabled or rt_types & set(enabled):
                rt_changes = await self._detect_hash_resource_changes(
                    cluster_id, analysis_id, run_id, run_number, namespace_scope,
                    resource_type='route',
                    added_type='route_added',
                    removed_type='route_removed',
                    changed_type='route_changed',
                    fetch_fn=self._get_routes_safe,
                    risk_add=RiskLevel.LOW.value,
                    risk_remove=RiskLevel.MEDIUM.value,
                    risk_change=RiskLevel.MEDIUM.value
                )
                changes.extend(rt_changes)

            by_type = {}
            for c in changes:
                by_type[c.change_type] = by_type.get(c.change_type, 0) + 1
            logger.info(
                "K8s detection completed",
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                total_changes=len(changes),
                by_type=by_type,
                namespace_scope_count=len(namespace_scope) if namespace_scope else 0,
                cached_workloads_count=len(cached_workloads) if cached_workloads else 0,
            )
            
        except Exception as e:
            logger.error("K8s detection failed", cluster_id=cluster_id, error=str(e))
        
        return changes
    
    async def _detect_workload_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        enabled_types: Optional[List[str]] = None,
        cached_workloads: Optional[List[Dict[str, Any]]] = None,
        fetch_had_error: bool = False
    ) -> List[Change]:
        """
        Detect workload additions and removals by comparing K8s API with PostgreSQL.
        
        Flow:
        1. Get current deployments from K8s API
        2. Get stored deployments from PostgreSQL workloads table
        3. Find new deployments (in K8s but not in PostgreSQL) -> workload_added
        4. Find removed deployments (in PostgreSQL but not in K8s) -> workload_removed
        5. Store new workloads to PostgreSQL for future comparison
        
        Args:
            namespace_scope: If provided, only detect changes in these namespaces
            enabled_types: List of enabled change types
            cached_workloads: Pre-fetched workloads to avoid redundant API calls
        """
        changes: List[Change] = []
        enabled = enabled_types or ['all']
        
        try:
            k8s_workloads = cached_workloads if cached_workloads is not None else \
                await self._get_all_workloads(cluster_id, namespace_scope=namespace_scope)
            
            # Group by type for stored-workload comparison
            workload_types = {'deployment', 'statefulset'}
            stored_workloads = {}
            for wt in workload_types:
                stored_workloads.update(await self._get_all_stored_workloads(cluster_id, wt, namespace_scope))
            
            # Create sets for comparison
            k8s_by_key = {f"{d['namespace']}/{d['name']}": d for d in k8s_workloads}
            k8s_keys = set(k8s_by_key.keys())
            stored_keys = set(stored_workloads.keys())
            
            # Detect new workloads (in K8s but not in PostgreSQL)
            if 'all' in enabled or 'workload_added' in enabled:
                new_workloads = k8s_keys - stored_keys
                for key in new_workloads:
                    wl = k8s_by_key.get(key)
                    if not wl:
                        continue
                    wl_type = wl.get('workload_type', 'deployment')
                    
                    blast_radius = await self._calculate_blast_radius(
                        cluster_id, wl['name'], wl['namespace']
                    )
                    
                    change = Change(
                        change_type='workload_added',
                        target=wl['name'],
                        namespace=wl['namespace'],
                        details=f"New {wl_type} created with {wl.get('replicas', 0)} replicas",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={},
                        after_state={
                            "replicas": wl.get('replicas', 0),
                            "labels": wl.get('labels', {})
                        },
                        affected_services=blast_radius,
                        blast_radius=blast_radius,
                        entity_type=wl_type,
                        risk_level=RiskLevel.LOW.value,
                        metadata={
                            "available_replicas": wl.get('available_replicas', 0),
                            "ready_replicas": wl.get('ready_replicas', 0)
                        }
                    )
                    changes.append(change)
                    
                    await self._store_new_workload(cluster_id, wl)
                    
                    logger.info(
                        "New workload detected and stored",
                        workload=wl['name'],
                        workload_type=wl_type,
                        namespace=wl['namespace'],
                        replicas=wl.get('replicas', 0)
                    )
            
            # Detect removed workloads (in PostgreSQL but not in K8s)
            if 'all' in enabled or 'workload_removed' in enabled:
                removal_candidates = [
                    k for k in (stored_keys - k8s_keys)
                    if stored_workloads[k].get('is_active', True)
                ]
                active_stored = sum(
                    1 for s in stored_workloads.values() if s.get('is_active', True)
                )
                skip = self._should_skip_removals(
                    k8s_count=len(k8s_workloads),
                    active_stored_count=active_stored,
                    removal_count=len(removal_candidates),
                    fetch_had_error=fetch_had_error,
                    resource_type='workload',
                    cluster_id=cluster_id,
                )
                if not skip:
                    for key in removal_candidates:
                        stored = stored_workloads[key]
                        namespace, name = key.split('/', 1)
                        wl_type = stored.get('workload_type', 'deployment')
                        
                        blast_radius = await self._calculate_blast_radius(
                            cluster_id, name, namespace
                        )
                        
                        change = Change(
                            change_type='workload_removed',
                            target=name,
                            namespace=namespace,
                            details=f"{wl_type.title()} removed (had {stored.get('replicas', 0)} replicas)",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"replicas": stored.get('replicas', 0)},
                            after_state={},
                            affected_services=blast_radius,
                            blast_radius=blast_radius,
                            entity_type=wl_type,
                            entity_id=stored.get('id'),
                            namespace_id=stored.get('namespace_id'),
                            risk_level=RiskLevel.HIGH.value if blast_radius > 2 else RiskLevel.MEDIUM.value,
                            metadata={}
                        )
                        changes.append(change)
                        
                        await self._mark_workload_inactive(stored.get('id'))
                        
                        logger.info(
                            "Workload removal detected",
                            workload=name,
                            workload_type=wl_type,
                            namespace=namespace,
                            previous_replicas=stored.get('replicas', 0)
                        )
            
            # Reactivate workloads that exist in K8s but are inactive in DB
            # (e.g. removed and re-created between cycles)
            for key in (k8s_keys & stored_keys):
                stored = stored_workloads[key]
                if not stored.get('is_active', True):
                    wl = k8s_by_key.get(key)
                    if wl:
                        await self._store_new_workload(cluster_id, wl)
                        if 'all' in enabled or 'workload_added' in enabled:
                            wl_type = wl.get('workload_type', 'deployment')
                            changes.append(Change(
                                change_type='workload_added',
                                target=wl['name'],
                                namespace=wl['namespace'],
                                details=f"{wl_type.title()} '{wl['name']}' re-created with {wl.get('replicas', 0)} replicas",
                                cluster_id=cluster_id,
                                analysis_id=analysis_id,
                                run_id=run_id,
                                run_number=run_number,
                                source=ChangeSource.K8S_API.value,
                                before_state={},
                                after_state={"replicas": wl.get('replicas', 0), "labels": wl.get('labels', {})},
                                entity_type=wl_type,
                                entity_id=stored.get('id'),
                                namespace_id=stored.get('namespace_id'),
                                risk_level=RiskLevel.LOW.value,
                                metadata={"reactivated": True}
                            ))
                            logger.info("Workload reactivated", workload=wl['name'], namespace=wl['namespace'])

            logger.debug(
                "Workload change detection completed",
                cluster_id=cluster_id,
                added=len([c for c in changes if c.change_type == 'workload_added']),
                removed=len([c for c in changes if c.change_type == 'workload_removed'])
            )
            
        except Exception as e:
            logger.error("Failed to detect workload changes", cluster_id=cluster_id, error=str(e))
        
        return changes
    
    async def _get_all_stored_workloads(
        self,
        cluster_id: int,
        workload_type: str,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """Get ALL stored workloads (including inactive) for proper comparison"""
        if namespace_scope:
            query = """
                SELECT 
                    w.id, w.name, w.workload_type, w.replicas, w.is_active,
                    n.name as namespace_name, w.namespace_id, w.metadata
                FROM workloads w
                JOIN namespaces n ON w.namespace_id = n.id
                WHERE w.cluster_id = :cluster_id 
                  AND w.workload_type = :workload_type
                  AND n.name = ANY(:namespaces)
            """
            params = {
                "cluster_id": cluster_id,
                "workload_type": workload_type,
                "namespaces": namespace_scope
            }
        else:
            query = """
                SELECT 
                    w.id, w.name, w.workload_type, w.replicas, w.is_active,
                    n.name as namespace_name, w.namespace_id, w.metadata
                FROM workloads w
                JOIN namespaces n ON w.namespace_id = n.id
                WHERE w.cluster_id = :cluster_id 
                  AND w.workload_type = :workload_type
            """
            params = {
                "cluster_id": cluster_id,
                "workload_type": workload_type
            }
        
        rows = await database.fetch_all(query, params)
        
        result = {}
        for row in rows:
            key = f"{row['namespace_name']}/{row['name']}"
            result[key] = dict(row)
        
        return result
    
    async def _mark_workload_inactive(self, workload_id: int) -> None:
        """Mark a workload as inactive when it's removed from K8s"""
        if not workload_id:
            return
        try:
            query = """
                UPDATE workloads 
                SET is_active = false, updated_at = NOW()
                WHERE id = :workload_id
            """
            await database.execute(query, {"workload_id": workload_id})
        except Exception as e:
            logger.warning("Failed to mark workload inactive", workload_id=workload_id, error=str(e))
    
    async def _store_new_workload(self, cluster_id: int, deployment: Dict) -> None:
        """
        Store a newly discovered workload to PostgreSQL.
        This creates the baseline for future change detection.
        Includes metadata snapshot so the next cycle can compare correctly.
        """
        try:
            # First, ensure namespace exists and get its ID
            namespace_query = """
                SELECT id FROM namespaces 
                WHERE cluster_id = :cluster_id AND name = :namespace
            """
            namespace_row = await database.fetch_one(namespace_query, {
                "cluster_id": cluster_id,
                "namespace": deployment['namespace']
            })
            
            if not namespace_row:
                create_ns_query = """
                    INSERT INTO namespaces (cluster_id, name, status, created_at, updated_at)
                    VALUES (:cluster_id, :name, 'Active', NOW(), NOW())
                    ON CONFLICT (cluster_id, name) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                """
                namespace_row = await database.fetch_one(create_ns_query, {
                    "cluster_id": cluster_id,
                    "name": deployment['namespace']
                })
            
            namespace_id = namespace_row['id']
            
            # Build metadata baseline depending on resource type
            wl_type = deployment.get('workload_type', 'deployment')
            metadata = {}
            if wl_type == 'service':
                metadata = {
                    "ports": deployment.get('ports', []),
                    "selector": deployment.get('selector') or {},
                    "type": deployment.get('type') or 'ClusterIP'
                }
            elif wl_type in ('deployment', 'statefulset'):
                if deployment.get('spec_hash'):
                    metadata["spec_hash"] = deployment['spec_hash']
                if deployment.get('containers'):
                    metadata["containers"] = deployment['containers']
                if deployment.get('labels'):
                    metadata["labels"] = deployment['labels']

            query = """
                INSERT INTO workloads (
                    cluster_id, namespace_id, name, workload_type, 
                    uid, labels, replicas, is_active, metadata,
                    first_seen, last_seen, created_at, updated_at
                )
                VALUES (
                    :cluster_id, :namespace_id, :name, :workload_type,
                    :uid, :labels, :replicas, true, CAST(:metadata AS jsonb),
                    NOW(), NOW(), NOW(), NOW()
                )
                ON CONFLICT (cluster_id, namespace_id, workload_type, name) 
                DO UPDATE SET 
                    is_active = true,
                    metadata = COALESCE(workloads.metadata, CAST('{}' AS jsonb)) || CAST(:metadata AS jsonb),
                    last_seen = NOW(),
                    updated_at = NOW()
            """
            
            await database.execute(query, {
                "cluster_id": cluster_id,
                "namespace_id": namespace_id,
                "name": deployment['name'],
                "workload_type": wl_type,
                "uid": deployment.get('uid', ''),
                "labels": json.dumps(deployment.get('labels', {})),
                "replicas": deployment.get('replicas', 0),
                "metadata": json.dumps(metadata)
            })
            
            logger.debug(
                "Workload stored for future comparison",
                cluster_id=cluster_id,
                name=deployment['name'],
                namespace=deployment['namespace'],
                workload_type=wl_type
            )
            
        except Exception as e:
            logger.warning(
                "Failed to store new workload",
                cluster_id=cluster_id,
                name=deployment.get('name'),
                error=str(e)
            )
    
    async def _detect_replica_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        cached_workloads: Optional[List[Dict[str, Any]]] = None
    ) -> List[Change]:
        """
        Detect replica count changes by comparing K8s API with PostgreSQL.
        
        Flow:
        1. Get current deployments from K8s API
        2. Get stored replica counts from PostgreSQL workloads table
        3. Compare and generate REPLICA_CHANGED events for differences
        4. Update PostgreSQL with new replica counts
        
        Args:
            namespace_scope: If provided, only detect changes in these namespaces
            cached_workloads: Pre-fetched workloads to avoid redundant API calls
        """
        changes: List[Change] = []
        
        try:
            k8s_workloads = cached_workloads if cached_workloads is not None else \
                await self._get_all_workloads(cluster_id, namespace_scope=namespace_scope)
            
            # Get stored state from PostgreSQL for both types
            stored_workloads = {}
            for wt in ('deployment', 'statefulset'):
                stored_workloads.update(await self._get_stored_workloads(cluster_id, wt, namespace_scope))
            
            for wl in k8s_workloads:
                key = f"{wl['namespace']}/{wl['name']}"
                stored = stored_workloads.get(key)
                
                if not stored:
                    continue
                
                k8s_replicas = wl.get('replicas', 0)
                stored_replicas = stored.get('replicas', 0)
                wl_type = wl.get('workload_type', 'deployment')
                
                if k8s_replicas != stored_replicas:
                    blast_radius = await self._calculate_blast_radius(
                        cluster_id, wl['name'], wl['namespace']
                    )
                    
                    change = Change(
                        change_type='replica_changed',
                        target=wl['name'],
                        namespace=wl['namespace'],
                        details=f"Replicas changed from {stored_replicas} to {k8s_replicas}",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={"replicas": stored_replicas},
                        after_state={"replicas": k8s_replicas},
                        affected_services=blast_radius,
                        blast_radius=blast_radius,
                        entity_type=wl_type,
                        entity_id=stored.get('id'),
                        namespace_id=stored.get('namespace_id'),
                        metadata={
                            "available_replicas": wl.get('available_replicas', 0),
                            "ready_replicas": wl.get('ready_replicas', 0)
                        }
                    )
                    
                    change.risk_level = self._assess_replica_risk(
                        stored_replicas, k8s_replicas, blast_radius
                    )
                    
                    changes.append(change)
                    await self._update_workload_replicas(stored['id'], k8s_replicas)
                    
                    logger.info(
                        "Replica change detected",
                        workload=wl['name'],
                        workload_type=wl_type,
                        namespace=wl['namespace'],
                        old_replicas=stored_replicas,
                        new_replicas=k8s_replicas
                    )
            
        except Exception as e:
            logger.error("Failed to detect replica changes", cluster_id=cluster_id, error=str(e))
        
        return changes
    
    async def _detect_config_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None
    ) -> List[Change]:
        """
        Detect ConfigMap/Secret changes via data hash comparison.
        Only the .data field is hashed -- metadata/status/managedFields are ignored
        to avoid false positives from OpenShift timestamp updates.
        Handles added, changed, and removed configs.
        """
        changes: List[Change] = []

        for resource_type in ('configmap', 'secret'):
            try:
                fetch_fn = self._get_configmaps_safe if resource_type == 'configmap' \
                    else self._get_secrets_safe
                k8s_items = await self._fetch_scoped(fetch_fn, cluster_id, namespace_scope)
                fetch_had_error = self._last_fetch_had_error

                stored = await self._get_all_stored_workloads(cluster_id, resource_type, namespace_scope)

                k8s_keys = {f"{i['namespace']}/{i['name']}" for i in k8s_items}
                stored_keys = set(stored.keys())
                k8s_by_key = {f"{i['namespace']}/{i['name']}": i for i in k8s_items}

                # New configs: store baseline (no change emitted on first sight)
                for key in (k8s_keys - stored_keys):
                    item = k8s_by_key.get(key)
                    if item:
                        await self._store_config_hash(cluster_id, item, resource_type)

                # Removed configs: mark inactive and emit change
                removal_candidates = [
                    k for k in (stored_keys - k8s_keys)
                    if stored[k].get('is_active', True)
                ]
                active_stored = sum(
                    1 for s in stored.values() if s.get('is_active', True)
                )
                skip_removals = self._should_skip_removals(
                    k8s_count=len(k8s_items),
                    active_stored_count=active_stored,
                    removal_count=len(removal_candidates),
                    fetch_had_error=fetch_had_error,
                    resource_type=resource_type,
                    cluster_id=cluster_id,
                )
                if not skip_removals:
                    for key in removal_candidates:
                        s = stored[key]
                        namespace, name = key.split('/', 1)
                        changes.append(Change(
                            change_type='config_changed',
                            target=name,
                            namespace=namespace,
                            details=f"{resource_type.title()} '{name}' removed",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"data_hash": (s.get('metadata') or {}).get('data_hash', '')},
                            after_state={},
                            entity_type=resource_type,
                            entity_id=s.get('id'),
                            namespace_id=s.get('namespace_id'),
                            risk_level=RiskLevel.MEDIUM.value,
                            metadata={"resource_type": resource_type, "removed": True}
                        ))
                        await self._mark_workload_inactive(s.get('id'))

                # Changed configs: compare data_hash
                hash_matches = 0
                hash_changes = 0
                for key in (k8s_keys & stored_keys):
                    item = k8s_by_key[key]
                    s = stored[key]
                    if not s.get('is_active', True):
                        await self._store_config_hash(cluster_id, item, resource_type)
                        continue

                    stored_meta = s.get('metadata') or {}
                    stored_hash = stored_meta.get('data_hash', 'empty')
                    current_hash = item.get('data_hash', 'empty')

                    if stored_hash != current_hash:
                        hash_changes += 1
                        logger.info(
                            "Config data change detected",
                            resource_type=resource_type,
                            name=item['name'],
                            namespace=item['namespace'],
                            stored_hash=stored_hash[:12] if stored_hash else 'None',
                            current_hash=current_hash[:12] if current_hash else 'None',
                        )
                        changes.append(Change(
                            change_type='config_changed',
                            target=item['name'],
                            namespace=item['namespace'],
                            details=f"{resource_type.title()} '{item['name']}' data changed",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"data_hash": stored_hash},
                            after_state={"data_hash": current_hash},
                            entity_type=resource_type,
                            entity_id=s.get('id'),
                            namespace_id=s.get('namespace_id'),
                            risk_level=RiskLevel.MEDIUM.value,
                            metadata={"resource_type": resource_type}
                        ))

                        await self._update_workload_metadata(
                            s.get('id'),
                            {"data_hash": current_hash}
                        )
                    else:
                        hash_matches += 1

                logger.debug(
                    "Config hash comparison completed",
                    resource_type=resource_type,
                    cluster_id=cluster_id,
                    total_compared=len(k8s_keys & stored_keys),
                    hash_matches=hash_matches,
                    hash_changes=hash_changes,
                    new_items=len(k8s_keys - stored_keys),
                )

            except Exception as e:
                logger.error(
                    f"Failed to detect {resource_type} changes",
                    cluster_id=cluster_id, error=str(e)
                )

        return changes

    async def _get_configmaps_safe(self, cluster_id: int, namespace: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Get configmaps via ClusterConnectionManager. Returns None on error."""
        try:
            return await cluster_connection_manager.get_configmaps(cluster_id, namespace)
        except Exception as e:
            logger.error("Failed to get configmaps", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return None

    async def _get_secrets_safe(self, cluster_id: int, namespace: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Get secrets via ClusterConnectionManager. Returns None on error."""
        try:
            return await cluster_connection_manager.get_secrets(cluster_id, namespace)
        except Exception as e:
            logger.error("Failed to get secrets", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return None

    async def _store_config_hash(self, cluster_id: int, item: Dict, resource_type: str) -> None:
        """Store initial config hash for future comparison."""
        try:
            namespace_query = """
                SELECT id FROM namespaces
                WHERE cluster_id = :cluster_id AND name = :namespace
            """
            ns_row = await database.fetch_one(namespace_query, {
                "cluster_id": cluster_id,
                "namespace": item['namespace']
            })
            if not ns_row:
                create_ns_query = """
                    INSERT INTO namespaces (cluster_id, name, status, created_at, updated_at)
                    VALUES (:cluster_id, :name, 'Active', NOW(), NOW())
                    ON CONFLICT (cluster_id, name) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                """
                ns_row = await database.fetch_one(create_ns_query, {
                    "cluster_id": cluster_id,
                    "name": item['namespace']
                })
                if not ns_row:
                    return

            query = """
                INSERT INTO workloads (
                    cluster_id, namespace_id, name, workload_type,
                    uid, labels, replicas, is_active, metadata,
                    first_seen, last_seen, created_at, updated_at
                )
                VALUES (
                    :cluster_id, :namespace_id, :name, :workload_type,
                    :uid, '{}', 0, true, CAST(:metadata AS jsonb),
                    NOW(), NOW(), NOW(), NOW()
                )
                ON CONFLICT (cluster_id, namespace_id, workload_type, name)
                DO UPDATE SET
                    is_active = true,
                    metadata = COALESCE(workloads.metadata, CAST('{}' AS jsonb)) || CAST(:metadata AS jsonb),
                    last_seen = NOW(),
                    updated_at = NOW()
            """
            await database.execute(query, {
                "cluster_id": cluster_id,
                "namespace_id": ns_row['id'],
                "name": item['name'],
                "workload_type": resource_type,
                "uid": item.get('uid', ''),
                "metadata": json.dumps({"data_hash": item.get('data_hash', 'empty')})
            })
        except Exception as e:
            logger.warning("Failed to store config hash", name=item.get('name'), error=str(e))
    
    async def _detect_image_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        cached_workloads: Optional[List[Dict[str, Any]]] = None
    ) -> List[Change]:
        """
        Detect container spec changes using layered hash comparison.
        
        Performance-optimized flow:
        1. Compare spec_hash (O(1)) -- most cycles will stop here
        2. If changed: compare image, resources, env per container
        3. Catch-all: spec_changed for anything else (probes, volumes, etc.)
        """
        changes: List[Change] = []

        try:
            k8s_workloads = cached_workloads if cached_workloads is not None else \
                await self._get_all_workloads(cluster_id, namespace_scope=namespace_scope)

            stored = {}
            for wt in ('deployment', 'statefulset'):
                stored.update(await self._get_stored_workloads(cluster_id, wt, namespace_scope))

            for wl in k8s_workloads:
                key = f"{wl['namespace']}/{wl['name']}"
                stored_wl = stored.get(key)
                if not stored_wl:
                    continue

                stored_meta = stored_wl.get('metadata') or {}
                current_spec_hash = wl.get('spec_hash', '')
                stored_spec_hash = stored_meta.get('spec_hash', '')

                if not current_spec_hash or not stored_spec_hash:
                    # First cycle or no spec data - store baseline and skip
                    if current_spec_hash:
                        update = {
                            "spec_hash": current_spec_hash,
                            "containers": wl.get('containers') or []
                        }
                        await self._update_workload_metadata(stored_wl.get('id'), update)
                    continue

                if current_spec_hash == stored_spec_hash:
                    continue

                # Spec changed -- detailed comparison
                wl_type = wl.get('workload_type', 'deployment')
                current_containers = {c['name']: c for c in wl.get('containers', [])}
                stored_containers = {c['name']: c for c in stored_meta.get('containers', [])}

                found_specific = False

                for cname, curr_c in current_containers.items():
                    prev_c = stored_containers.get(cname, {})

                    # Image change
                    if curr_c.get('image') and prev_c.get('image') and curr_c['image'] != prev_c['image']:
                        changes.append(Change(
                            change_type='image_changed',
                            target=wl['name'],
                            namespace=wl['namespace'],
                            details=f"Container '{cname}': image {prev_c['image']} -> {curr_c['image']}",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"image": prev_c['image']},
                            after_state={"image": curr_c['image']},
                            entity_type=wl_type,
                            entity_id=stored_wl.get('id'),
                            namespace_id=stored_wl.get('namespace_id'),
                            risk_level=RiskLevel.HIGH.value,
                            metadata={"container": cname}
                        ))
                        found_specific = True

                    # Resource change
                    curr_res = curr_c.get('resources', {})
                    prev_res = prev_c.get('resources', {})
                    if curr_res != prev_res and (curr_res or prev_res):
                        diff_parts = []
                        for section in ('requests', 'limits'):
                            cr = curr_res.get(section, {})
                            pr = prev_res.get(section, {})
                            for rk in set(list(cr.keys()) + list(pr.keys())):
                                if str(cr.get(rk, '')) != str(pr.get(rk, '')):
                                    diff_parts.append(f"{section}.{rk} {pr.get(rk, 'none')} -> {cr.get(rk, 'none')}")
                        if diff_parts:
                            changes.append(Change(
                                change_type='resource_changed',
                                target=wl['name'],
                                namespace=wl['namespace'],
                                details=f"Container '{cname}': {', '.join(diff_parts)}",
                                cluster_id=cluster_id,
                                analysis_id=analysis_id,
                                run_id=run_id,
                                run_number=run_number,
                                source=ChangeSource.K8S_API.value,
                                before_state={"resources": prev_res},
                                after_state={"resources": curr_res},
                                entity_type=wl_type,
                                entity_id=stored_wl.get('id'),
                                namespace_id=stored_wl.get('namespace_id'),
                                risk_level=RiskLevel.MEDIUM.value,
                                metadata={"container": cname}
                            ))
                            found_specific = True

                    # Env change
                    curr_env = curr_c.get('env_hash', '')
                    prev_env = prev_c.get('env_hash', '')
                    if curr_env and prev_env and curr_env != prev_env:
                        changes.append(Change(
                            change_type='env_changed',
                            target=wl['name'],
                            namespace=wl['namespace'],
                            details=f"Container '{cname}': environment variables changed",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"env_hash": prev_env},
                            after_state={"env_hash": curr_env},
                            entity_type=wl_type,
                            entity_id=stored_wl.get('id'),
                            namespace_id=stored_wl.get('namespace_id'),
                            risk_level=RiskLevel.MEDIUM.value,
                            metadata={"container": cname}
                        ))
                        found_specific = True

                # Catch-all: spec_changed if no specific field identified
                if not found_specific:
                    changes.append(Change(
                        change_type='spec_changed',
                        target=wl['name'],
                        namespace=wl['namespace'],
                        details=f"{wl_type.title()} '{wl['name']}': pod spec changed (probes/volumes/security)",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={"spec_hash": stored_spec_hash},
                        after_state={"spec_hash": current_spec_hash},
                        entity_type=wl_type,
                        entity_id=stored_wl.get('id'),
                        namespace_id=stored_wl.get('namespace_id'),
                        risk_level=RiskLevel.LOW.value,
                        metadata={}
                    ))

                # Update stored metadata (always set containers to keep in sync)
                update_meta = {
                    "spec_hash": current_spec_hash,
                    "containers": wl.get('containers') or []
                }
                await self._update_workload_metadata(stored_wl.get('id'), update_meta)

        except Exception as e:
            logger.error("Failed to detect spec changes", cluster_id=cluster_id, error=str(e))

        return changes
    
    async def _detect_label_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        cached_workloads: Optional[List[Dict[str, Any]]] = None
    ) -> List[Change]:
        """
        Detect label changes in deployments and statefulsets.
        
        Label changes can affect service routing and pod selection.
        """
        changes: List[Change] = []
        
        try:
            k8s_workloads = cached_workloads if cached_workloads is not None else \
                await self._get_all_workloads(cluster_id, namespace_scope=namespace_scope)
            
            # Get stored workloads with metadata for both types
            stored = {}
            for wt in ('deployment', 'statefulset'):
                stored.update(await self._get_stored_workloads(cluster_id, wt, namespace_scope))
            
            for dep in k8s_workloads:
                key = f"{dep.get('namespace', 'default')}/{dep.get('name', '')}"
                
                if key in stored:
                    stored_workload = stored[key]
                    stored_metadata = stored_workload.get('metadata') or {}
                    
                    # Get current labels (discover_deployments returns labels directly)
                    current_labels = dep.get('labels', {})
                    
                    # Get stored labels
                    stored_labels = stored_metadata.get('labels', {})
                    
                    # Compare labels
                    if current_labels != stored_labels:
                        namespace = dep.get('namespace', 'default')
                        name = dep.get('name', '')
                        
                        # Find added, removed, and changed labels
                        added = {k: v for k, v in current_labels.items() if k not in stored_labels}
                        removed = {k: v for k, v in stored_labels.items() if k not in current_labels}
                        changed = {k: (stored_labels[k], current_labels[k]) 
                                  for k in current_labels 
                                  if k in stored_labels and current_labels[k] != stored_labels[k]}
                        
                        # Calculate blast radius
                        blast_radius = await self._calculate_blast_radius(cluster_id, name, namespace)
                        
                        # Determine risk level
                        risk = RiskLevel.MEDIUM.value
                        if 'app' in changed or 'app' in added or 'app' in removed:
                            risk = RiskLevel.HIGH.value  # 'app' label changes affect service routing
                        
                        change = Change(
                            change_type='label_changed',
                            target=name,
                            namespace=namespace,
                            details=self._format_label_changes(added, removed, changed),
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"labels": stored_labels},
                            after_state={"labels": current_labels},
                            entity_type=dep.get('workload_type', 'deployment'),
                            entity_id=stored_workload.get('id'),
                            namespace_id=stored_workload.get('namespace_id'),
                            risk_level=risk,
                            affected_services=1,
                            blast_radius=blast_radius,
                            metadata={
                                "change_source": "k8s_api",
                                "labels_added": added,
                                "labels_removed": removed,
                                "labels_changed": changed
                            }
                        )
                        changes.append(change)
                        
                        # Update stored labels
                        await self._update_workload_metadata(
                            stored_workload.get('id'),
                            {'labels': current_labels}
                        )
            
            logger.debug("Label change detection completed", 
                        cluster_id=cluster_id, 
                        changes_found=len(changes))
                        
        except Exception as e:
            logger.error("Failed to detect label changes", 
                        cluster_id=cluster_id, 
                        error=str(e))
        
        return changes
    
    def _format_label_changes(
        self,
        added: Dict[str, str],
        removed: Dict[str, str],
        changed: Dict[str, tuple]
    ) -> str:
        """Format label changes as human-readable string"""
        parts = []
        if added:
            parts.append(f"Added: {', '.join(f'{k}={v}' for k, v in added.items())}")
        if removed:
            parts.append(f"Removed: {', '.join(f'{k}={v}' for k, v in removed.items())}")
        if changed:
            parts.append(f"Changed: {', '.join(f'{k}: {old}→{new}' for k, (old, new) in changed.items())}")
        return "; ".join(parts) if parts else "Labels modified"
    
    async def _update_workload_metadata(
        self,
        workload_id: int,
        updates: Dict[str, Any]
    ) -> None:
        """Update workload metadata in PostgreSQL"""
        try:
            # Merge with existing metadata
            # Note: Use CAST() instead of :: to avoid conflict with SQLAlchemy's :param syntax
            query = """
                UPDATE workloads 
                SET metadata = COALESCE(metadata, CAST('{}' AS jsonb)) || CAST(:updates AS jsonb),
                    updated_at = NOW()
                WHERE id = :workload_id
            """
            await database.execute(query, {
                "workload_id": workload_id,
                "updates": json.dumps(updates)
            })
        except Exception as e:
            logger.warning("Failed to update workload metadata", 
                          workload_id=workload_id, 
                          error=str(e))
    
    async def _get_stored_workloads(
        self,
        cluster_id: int,
        workload_type: str,
        namespace_scope: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """Get stored workloads from PostgreSQL indexed by namespace/name
        
        Args:
            namespace_scope: If provided, only return workloads in these namespaces
        """
        # Base query
        if namespace_scope:
            query = """
                SELECT 
                    w.id, w.name, w.workload_type, w.replicas, w.is_active,
                    n.name as namespace_name, w.namespace_id, w.metadata
                FROM workloads w
                JOIN namespaces n ON w.namespace_id = n.id
                WHERE w.cluster_id = :cluster_id 
                  AND w.workload_type = :workload_type
                  AND w.is_active = true
                  AND n.name = ANY(:namespaces)
            """
            params = {
                "cluster_id": cluster_id,
                "workload_type": workload_type,
                "namespaces": namespace_scope
            }
        else:
            query = """
                SELECT 
                    w.id, w.name, w.workload_type, w.replicas, w.is_active,
                    n.name as namespace_name, w.namespace_id, w.metadata
                FROM workloads w
                JOIN namespaces n ON w.namespace_id = n.id
                WHERE w.cluster_id = :cluster_id 
                  AND w.workload_type = :workload_type
                  AND w.is_active = true
            """
            params = {
                "cluster_id": cluster_id,
                "workload_type": workload_type
            }
        
        rows = await database.fetch_all(query, params)
        
        result = {}
        for row in rows:
            key = f"{row['namespace_name']}/{row['name']}"
            result[key] = dict(row)
        
        logger.debug(
            "Loaded stored workloads",
            cluster_id=cluster_id,
            workload_type=workload_type,
            namespace_scope=namespace_scope,
            count=len(result)
        )
        
        return result
    
    async def _calculate_blast_radius(
        self,
        cluster_id: int,
        workload_name: str,
        namespace: str
    ) -> int:
        """Calculate blast radius (affected services) for a workload within its namespace"""
        try:
            query = """
                SELECT COUNT(DISTINCT 
                    CASE 
                        WHEN sw.name = :workload_name THEN dw.id
                        WHEN dw.name = :workload_name THEN sw.id
                    END
                ) as affected_count
                FROM communications c
                JOIN workloads sw ON c.source_workload_id = sw.id
                JOIN workloads dw ON c.destination_workload_id = dw.id
                JOIN namespaces sn ON sw.namespace_id = sn.id
                JOIN namespaces dn ON dw.namespace_id = dn.id
                WHERE c.cluster_id = :cluster_id
                  AND (
                    (sw.name = :workload_name AND sn.name = :namespace)
                    OR (dw.name = :workload_name AND dn.name = :namespace)
                  )
                  AND c.is_active = true
            """
            
            result = await database.fetch_one(query, {
                "cluster_id": cluster_id,
                "workload_name": workload_name,
                "namespace": namespace
            })
            
            return result['affected_count'] if result else 0
            
        except Exception as e:
            logger.warning("Failed to calculate blast radius", error=str(e))
            return 0
    
    async def _update_workload_replicas(self, workload_id: int, new_replicas: int):
        """Update workload replica count in PostgreSQL"""
        try:
            # Store previous replicas in metadata for tracking
            update_query = """
                UPDATE workloads 
                SET 
                    replicas = :replicas,
                    metadata = jsonb_set(
                        COALESCE(metadata, '{}'::jsonb),
                        '{previous_replicas}',
                        to_jsonb(replicas)
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """
            await database.execute(update_query, {
                "id": workload_id,
                "replicas": new_replicas
            })
        except Exception as e:
            logger.warning("Failed to update workload replicas", workload_id=workload_id, error=str(e))
    
    # ==========================================
    # GENERIC HASH-BASED RESOURCE DETECTION
    # ==========================================

    async def _get_network_policies_safe(self, cluster_id: int, namespace: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Returns None on error so callers can skip removal detection."""
        try:
            items = await cluster_connection_manager.get_network_policies(cluster_id, namespace)
            for i in items:
                i['workload_type'] = 'networkpolicy'
            return items
        except Exception as e:
            logger.error("Failed to get network policies", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return None

    async def _get_ingresses_safe(self, cluster_id: int, namespace: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Returns None on error so callers can skip removal detection."""
        try:
            items = await cluster_connection_manager.get_ingresses(cluster_id, namespace)
            for i in items:
                i['workload_type'] = 'ingress'
            return items
        except Exception as e:
            logger.error("Failed to get ingresses", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return None

    async def _get_routes_safe(self, cluster_id: int, namespace: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Returns None on error so callers can skip removal detection."""
        try:
            items = await cluster_connection_manager.get_routes(cluster_id, namespace)
            for i in items:
                i['workload_type'] = 'route'
            return items
        except Exception as e:
            logger.error("Failed to get routes", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return None

    async def _detect_hash_resource_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]],
        resource_type: str,
        added_type: str,
        removed_type: str,
        changed_type: str,
        fetch_fn,
        risk_add: str,
        risk_remove: str,
        risk_change: str
    ) -> List[Change]:
        """Generic hash-based change detection for NetworkPolicy, Ingress, Route."""
        changes: List[Change] = []

        try:
            k8s_items = await self._fetch_scoped(fetch_fn, cluster_id, namespace_scope)
            fetch_had_error = self._last_fetch_had_error

            stored = await self._get_all_stored_workloads(cluster_id, resource_type, namespace_scope)

            k8s_keys = {f"{i['namespace']}/{i['name']}" for i in k8s_items}
            stored_keys = set(stored.keys())

            k8s_by_key = {f"{i['namespace']}/{i['name']}": i for i in k8s_items}

            # Added
            for key in (k8s_keys - stored_keys):
                item = k8s_by_key.get(key)
                if not item:
                    continue
                changes.append(Change(
                    change_type=added_type,
                    target=item['name'],
                    namespace=item['namespace'],
                    details=f"New {resource_type} '{item['name']}' created",
                    cluster_id=cluster_id,
                    analysis_id=analysis_id,
                    run_id=run_id,
                    run_number=run_number,
                    source=ChangeSource.K8S_API.value,
                    before_state={},
                    after_state={"spec_hash": item.get('spec_hash', '')},
                    entity_type=resource_type,
                    risk_level=risk_add,
                    metadata={}
                ))
                await self._store_config_hash(cluster_id, {
                    "name": item['name'],
                    "namespace": item['namespace'],
                    "uid": item.get('uid', ''),
                    "data_hash": item.get('spec_hash', '')
                }, resource_type)

            # Removed — safeguard against mass false-positive removals
            removal_candidates = [
                k for k in (stored_keys - k8s_keys)
                if stored[k].get('is_active', True)
            ]
            active_stored = sum(
                1 for s in stored.values() if s.get('is_active', True)
            )
            skip_removals = self._should_skip_removals(
                k8s_count=len(k8s_items),
                active_stored_count=active_stored,
                removal_count=len(removal_candidates),
                fetch_had_error=fetch_had_error,
                resource_type=resource_type,
                cluster_id=cluster_id,
            )
            if not skip_removals:
                for key in removal_candidates:
                    s = stored[key]
                    namespace, name = key.split('/', 1)
                    changes.append(Change(
                        change_type=removed_type,
                        target=name,
                        namespace=namespace,
                        details=f"{resource_type.title()} '{name}' removed",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={"spec_hash": (s.get('metadata') or {}).get('data_hash', '')},
                        after_state={},
                        entity_type=resource_type,
                        entity_id=s.get('id'),
                        namespace_id=s.get('namespace_id'),
                        risk_level=risk_remove,
                        metadata={}
                    ))
                    await self._mark_workload_inactive(s.get('id'))

            # Changed (spec_hash comparison)
            hash_matches = 0
            hash_changes = 0
            for item in k8s_items:
                key = f"{item['namespace']}/{item['name']}"
                s = stored.get(key)
                if not s or not s.get('is_active', True):
                    continue

                s_meta = s.get('metadata') or {}
                stored_hash = s_meta.get('data_hash', '')
                current_hash = item.get('spec_hash', '')

                if stored_hash and current_hash and stored_hash != current_hash:
                    hash_changes += 1
                    logger.info(
                        "Resource spec change detected",
                        resource_type=resource_type,
                        name=item['name'],
                        namespace=item['namespace'],
                        stored_hash=stored_hash[:12] if stored_hash else 'None',
                        current_hash=current_hash[:12] if current_hash else 'None',
                    )
                    changes.append(Change(
                        change_type=changed_type,
                        target=item['name'],
                        namespace=item['namespace'],
                        details=f"{resource_type.title()} '{item['name']}' spec changed",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={"spec_hash": stored_hash},
                        after_state={"spec_hash": current_hash},
                        entity_type=resource_type,
                        entity_id=s.get('id'),
                        namespace_id=s.get('namespace_id'),
                        risk_level=risk_change,
                        metadata={}
                    ))
                    await self._update_workload_metadata(s.get('id'), {"data_hash": current_hash})
                else:
                    hash_matches += 1

            logger.debug(
                "Hash resource comparison completed",
                resource_type=resource_type,
                cluster_id=cluster_id,
                k8s_count=len(k8s_items),
                stored_count=len(stored),
                new_items=len(k8s_keys - stored_keys),
                hash_matches=hash_matches,
                hash_changes=hash_changes,
            )

        except Exception as e:
            logger.error(f"Failed to detect {resource_type} changes", cluster_id=cluster_id, error=str(e))

        return changes

    # ==========================================
    # SERVICE CHANGE DETECTION
    # ==========================================

    async def _get_services_safe(
        self, cluster_id: int, namespace: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get services via ClusterConnectionManager. Returns None on error."""
        try:
            services = await cluster_connection_manager.get_services(cluster_id, namespace)
            for svc in services:
                svc["workload_type"] = "service"
            return services
        except Exception as e:
            logger.error("Failed to get services", cluster_id=cluster_id, error=str(e))
            return None

    async def _detect_service_changes(
        self,
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        enabled_types: Optional[List[str]] = None
    ) -> List[Change]:
        """
        Detect service changes: port, selector, type modifications and lifecycle events.
        Compares current K8s service state with stored state in PostgreSQL.
        """
        changes: List[Change] = []
        enabled = enabled_types or ['all']

        try:
            k8s_services = await self._fetch_scoped(
                self._get_services_safe, cluster_id, namespace_scope
            )
            fetch_had_error = self._last_fetch_had_error

            stored_services = await self._get_stored_workloads(cluster_id, 'service', namespace_scope)
            stored_all = await self._get_all_stored_workloads(cluster_id, 'service', namespace_scope)

            k8s_by_key = {f"{s['namespace']}/{s['name']}": s for s in k8s_services}
            k8s_keys = set(k8s_by_key.keys())
            stored_keys = set(stored_all.keys())

            # --- Service lifecycle ---
            if 'all' in enabled or 'service_added' in enabled:
                for key in (k8s_keys - stored_keys):
                    svc = k8s_by_key.get(key)
                    if not svc:
                        continue
                    changes.append(Change(
                        change_type='service_added',
                        target=svc['name'],
                        namespace=svc['namespace'],
                        details=f"New service created (type: {svc.get('type', 'ClusterIP')}, ports: {len(svc.get('ports', []))})",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.K8S_API.value,
                        before_state={},
                        after_state={
                            "type": svc.get('type', 'ClusterIP'),
                            "ports": svc.get('ports', []),
                            "selector": svc.get('selector', {})
                        },
                        entity_type="service",
                        risk_level=RiskLevel.LOW.value,
                        metadata={}
                    ))
                    await self._store_new_workload(cluster_id, svc)

            if 'all' in enabled or 'service_removed' in enabled:
                removal_candidates = [
                    k for k in (stored_keys - k8s_keys)
                    if stored_all[k].get('is_active', True)
                ]
                active_stored = sum(
                    1 for s in stored_all.values() if s.get('is_active', True)
                )
                skip = self._should_skip_removals(
                    k8s_count=len(k8s_services),
                    active_stored_count=active_stored,
                    removal_count=len(removal_candidates),
                    fetch_had_error=fetch_had_error,
                    resource_type='service',
                    cluster_id=cluster_id,
                )
                if not skip:
                    for key in removal_candidates:
                        stored = stored_all[key]
                        namespace, name = key.split('/', 1)
                        changes.append(Change(
                            change_type='service_removed',
                            target=name,
                            namespace=namespace,
                            details="Service removed",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"type": (stored.get('metadata') or {}).get('type', 'ClusterIP')},
                            after_state={},
                            entity_type="service",
                            entity_id=stored.get('id'),
                            namespace_id=stored.get('namespace_id'),
                            risk_level=RiskLevel.HIGH.value,
                            metadata={}
                        ))
                        await self._mark_workload_inactive(stored.get('id'))

            # --- Service property changes (port, selector, type) ---
            for svc in k8s_services:
                key = f"{svc['namespace']}/{svc['name']}"
                stored = stored_services.get(key)
                if not stored:
                    continue

                stored_meta = stored.get('metadata') or {}
                k8s_ports = svc.get('ports', [])
                stored_ports_raw = stored_meta.get('ports') or stored.get('ports') or []

                # -- Port changes --
                if 'all' in enabled or 'service_port_changed' in enabled:
                    port_changes = self._compare_service_ports(
                        svc['name'], svc['namespace'],
                        stored_ports_raw, k8s_ports,
                        cluster_id, analysis_id, run_id, run_number, stored
                    )
                    changes.extend(port_changes)

                # -- Selector changes --
                if 'all' in enabled or 'service_selector_changed' in enabled:
                    k8s_sel = svc.get('selector', {}) or {}
                    stored_sel = stored_meta.get('selector', {}) or {}
                    if k8s_sel != stored_sel:
                        changes.append(Change(
                            change_type='service_selector_changed',
                            target=svc['name'],
                            namespace=svc['namespace'],
                            details=self._format_selector_change(stored_sel, k8s_sel),
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"selector": stored_sel},
                            after_state={"selector": k8s_sel},
                            entity_type="service",
                            entity_id=stored.get('id'),
                            namespace_id=stored.get('namespace_id'),
                            risk_level=RiskLevel.HIGH.value,
                            metadata={}
                        ))

                # -- Type changes --
                if 'all' in enabled or 'service_type_changed' in enabled:
                    k8s_type = svc.get('type') or 'ClusterIP'
                    stored_type = stored_meta.get('type') or 'ClusterIP'
                    if k8s_type != stored_type:
                        changes.append(Change(
                            change_type='service_type_changed',
                            target=svc['name'],
                            namespace=svc['namespace'],
                            details=f"Service type changed from {stored_type} to {k8s_type}",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.K8S_API.value,
                            before_state={"type": stored_type},
                            after_state={"type": k8s_type},
                            entity_type="service",
                            entity_id=stored.get('id'),
                            namespace_id=stored.get('namespace_id'),
                            risk_level=RiskLevel.MEDIUM.value,
                            metadata={}
                        ))

                # Update stored metadata for this service
                if any(c.target == svc['name'] and c.namespace == svc['namespace'] for c in changes):
                    await self._update_workload_metadata(stored.get('id'), {
                        "ports": k8s_ports,
                        "selector": svc.get('selector', {}),
                        "type": svc.get('type', 'ClusterIP')
                    })

        except Exception as e:
            logger.error("Failed to detect service changes", cluster_id=cluster_id, error=str(e))

        return changes

    def _normalize_port_tuple(self, p: Dict) -> tuple:
        """Convert a port dict to a comparable tuple (port, target_port, protocol, name, app_protocol)."""
        raw_tp = p.get('target_port')
        target_port = str(raw_tp) if raw_tp is not None else str(p.get('port', ''))
        return (
            p.get('port'),
            target_port,
            p.get('protocol', 'TCP'),
            p.get('name', ''),
            p.get('app_protocol', '')
        )

    def _compare_service_ports(
        self,
        svc_name: str,
        svc_namespace: str,
        stored_ports: List[Dict],
        current_ports: List[Dict],
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        stored_workload: Dict
    ) -> List[Change]:
        """Compare service ports and generate detailed change events."""
        changes: List[Change] = []

        old_set = {self._normalize_port_tuple(p) for p in stored_ports}
        new_set = {self._normalize_port_tuple(p) for p in current_ports}

        if old_set == new_set:
            return changes

        # Index by (port, protocol) composite key to handle TCP/UDP on same port
        old_by_key = {(p.get('port'), p.get('protocol', 'TCP')): p for p in stored_ports}
        new_by_key = {(p.get('port'), p.get('protocol', 'TCP')): p for p in current_ports}

        details_parts = []
        all_keys = set(list(old_by_key.keys()) + list(new_by_key.keys()))
        for port_key in all_keys:
            port_num, proto = port_key
            old_p = old_by_key.get(port_key)
            new_p = new_by_key.get(port_key)

            if old_p and not new_p:
                name = old_p.get('name', '')
                label = f"'{name}' " if name else ''
                details_parts.append(f"port {label}({port_num}/{proto}) removed")
            elif new_p and not old_p:
                name = new_p.get('name', '')
                label = f"'{name}' " if name else ''
                details_parts.append(f"new port {label}({port_num}/{proto}) added")
            elif old_p and new_p:
                diffs = []
                for field in ('target_port', 'name', 'app_protocol'):
                    old_val = str(old_p.get(field, ''))
                    new_val = str(new_p.get(field, ''))
                    if old_val != new_val:
                        diffs.append(f"{field} {old_val} -> {new_val}")
                if diffs:
                    details_parts.append(f"port {port_num}/{proto}: {', '.join(diffs)}")

        if not details_parts:
            details_parts.append("port configuration changed")

        changes.append(Change(
            change_type='service_port_changed',
            target=svc_name,
            namespace=svc_namespace,
            details=f"Service '{svc_name}': {'; '.join(details_parts)}",
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            run_id=run_id,
            run_number=run_number,
            source=ChangeSource.K8S_API.value,
            before_state={"ports": stored_ports},
            after_state={"ports": current_ports},
            entity_type="service",
            entity_id=stored_workload.get('id'),
            namespace_id=stored_workload.get('namespace_id'),
            risk_level=RiskLevel.HIGH.value,
            metadata={"port_details": details_parts}
        ))
        return changes

    def _format_selector_change(self, old_sel: Dict, new_sel: Dict) -> str:
        """Format selector change as human-readable string."""
        added = {k: v for k, v in new_sel.items() if k not in old_sel}
        removed = {k: v for k, v in old_sel.items() if k not in new_sel}
        changed = {k: (old_sel[k], new_sel[k]) for k in new_sel if k in old_sel and new_sel[k] != old_sel[k]}
        parts = []
        if added:
            parts.append(f"added: {', '.join(f'{k}={v}' for k, v in added.items())}")
        if removed:
            parts.append(f"removed: {', '.join(f'{k}={v}' for k, v in removed.items())}")
        if changed:
            parts.append(f"changed: {', '.join(f'{k}: {o}->{n}' for k, (o, n) in changed.items())}")
        return f"Selector changed ({'; '.join(parts)})" if parts else "Selector changed"

    def _assess_replica_risk(
        self,
        old_replicas: int,
        new_replicas: int,
        blast_radius: int
    ) -> str:
        """Assess risk level for replica change"""
        # Scaling to 0 is critical
        if new_replicas == 0 and old_replicas > 0:
            return RiskLevel.CRITICAL.value
        
        # Large blast radius increases risk
        if blast_radius > 10:
            if new_replicas < old_replicas:
                return RiskLevel.HIGH.value
            return RiskLevel.MEDIUM.value
        
        if blast_radius > 5:
            if new_replicas < old_replicas:
                return RiskLevel.MEDIUM.value
            return RiskLevel.LOW.value
        
        return RiskLevel.LOW.value
