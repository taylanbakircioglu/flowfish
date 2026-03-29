"""
Flowfish Change Detection Worker - Standalone Application

This is the entry point for the Change Detection Worker when running
as a separate Pod/container. It provides a scalable, independent
change detection service.

Features:
- Runs as a standalone microservice
- Horizontally scalable (multiple replicas)
- Leader election for coordination
- Health check endpoints
- Graceful shutdown
- Metrics exposure

Environment Variables:
- CHANGE_DETECTION_ENABLED: Enable/disable detection (default: true when standalone)
- CHANGE_DETECTION_INTERVAL: Detection interval in seconds (default: 60)
- CHANGE_DETECTION_LOOKBACK_MINUTES: How far back to look (default: 5)
- WORKER_INSTANCE_ID: Unique instance identifier (auto-generated if not set)
- LEADER_ELECTION_ENABLED: Enable leader election for single-active worker (default: false)

Database Configuration (same as backend):
- DATABASE_URL: PostgreSQL connection string
- NEO4J_URI: Neo4j connection string
- REDIS_URL: Redis connection string (for leader election)
"""

import asyncio
import json
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import logging
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Configure standard logging first
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Startup message (plain print for guaranteed visibility)
print("=" * 60)
print("CHANGE DETECTION WORKER - INITIALIZING")
print("=" * 60)

# Worker instance configuration
WORKER_INSTANCE_ID = os.getenv("WORKER_INSTANCE_ID", str(uuid.uuid4())[:8])
LEADER_ELECTION_ENABLED = os.getenv("LEADER_ELECTION_ENABLED", "false").lower() == "true"

# Global state
worker_state = {
    "started_at": None,
    "is_leader": True,  # Default to leader if election disabled
    "detection_cycles": 0,
    "last_detection": None,
    "errors": 0
}


class StandaloneChangeDetectionWorker:
    """
    Standalone Change Detection Worker
    
    Extends the base worker with:
    - Leader election support
    - Metrics collection
    - Health reporting
    """
    
    def __init__(self):
        self.instance_id = WORKER_INSTANCE_ID
        self.leader_election_enabled = LEADER_ELECTION_ENABLED
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._detection_service = None
        self._service_registry = None  # ServicePortRegistry for intelligent port filtering
        
        # Configuration
        self.DETECTION_INTERVAL = int(os.getenv("CHANGE_DETECTION_INTERVAL", "60"))
        self.LOOKBACK_MINUTES = int(os.getenv("CHANGE_DETECTION_LOOKBACK_MINUTES", "5"))
        self.CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CHANGE_DETECTION_CIRCUIT_BREAKER_THRESHOLD", "3"))
        self.CIRCUIT_BREAKER_RESET_TIME = int(os.getenv("CHANGE_DETECTION_CIRCUIT_BREAKER_RESET", "300"))
        
        # Maximum changes per cycle to avoid overwhelming the system
        # If more changes detected, only the most important ones are recorded
        self.MAX_CHANGES_PER_CYCLE = int(os.getenv("CHANGE_DETECTION_MAX_CHANGES", "100"))
        
        # State tracking
        self._failure_counts = {}
        self._circuit_open_until = {}
        self._last_detection = {}
        self._baseline_established = {}  # Track which analyses have completed baseline
        
        logger.info(
            "Worker instance initialized",
            instance_id=self.instance_id,
            leader_election=self.leader_election_enabled,
            interval=self.DETECTION_INTERVAL
        )
    
    @property
    def service_registry(self):
        """
        Lazy-load ServicePortRegistry.
        
        This registry caches Kubernetes Service definitions to:
        - Identify valid service ports
        - Map Pod IPs to Services
        - Filter out ephemeral port noise
        """
        if self._service_registry is None:
            try:
                from services.change_detection import ServicePortRegistry
                self._service_registry = ServicePortRegistry()
                logger.info("ServicePortRegistry initialized")
            except ImportError as e:
                logger.warning("ServicePortRegistry not available", error=str(e))
        return self._service_registry
    
    @property
    def detection_service(self):
        """Lazy-load detection service (legacy - kept for compatibility)"""
        if self._detection_service is None:
            from services.change_detection_service import get_change_detection_service
            self._detection_service = get_change_detection_service()
        return self._detection_service
    
    @property
    def k8s_detector(self):
        """Lazy-load K8s detector"""
        if not hasattr(self, '_k8s_detector') or self._k8s_detector is None:
            from services.change_detection import K8sDetector
            self._k8s_detector = K8sDetector()
        return self._k8s_detector
    
    @property
    def ebpf_detector(self):
        """Lazy-load eBPF detector"""
        if not hasattr(self, '_ebpf_detector') or self._ebpf_detector is None:
            from services.change_detection import eBPFDetector
            self._ebpf_detector = eBPFDetector()
        return self._ebpf_detector
    
    async def start(self):
        """Start the worker"""
        if self._running:
            logger.warning("Worker already running")
            return
        
        self._running = True
        worker_state["started_at"] = datetime.now(timezone.utc).isoformat()
        
        # Start leader election if enabled
        if self.leader_election_enabled:
            asyncio.create_task(self._leader_election_loop())
        
        # Start detection loop
        self._task = asyncio.create_task(self._detection_loop())
        
        logger.info(
            "Worker started",
            instance_id=self.instance_id,
            interval=self.DETECTION_INTERVAL
        )
    
    async def stop(self):
        """Stop the worker gracefully"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Worker stopped", instance_id=self.instance_id)
    
    async def _leader_election_loop(self):
        """Leader election using Redis (if enabled)"""
        try:
            from database.redis import redis_client
            
            lock_key = "flowfish:change_detection:leader"
            lock_ttl = self.DETECTION_INTERVAL * 2  # TTL = 2x detection interval
            
            while self._running:
                try:
                    # Try to acquire leader lock
                    acquired = await redis_client.set(
                        lock_key,
                        self.instance_id,
                        ex=lock_ttl,
                        nx=True
                    )
                    
                    if acquired:
                        worker_state["is_leader"] = True
                        logger.debug("Acquired leader lock", instance_id=self.instance_id)
                    else:
                        # Check if we're still the leader
                        current_leader = await redis_client.get(lock_key)
                        if current_leader and current_leader.decode() == self.instance_id:
                            # Refresh lock
                            await redis_client.expire(lock_key, lock_ttl)
                            worker_state["is_leader"] = True
                        else:
                            worker_state["is_leader"] = False
                            logger.debug(
                                "Not leader",
                                instance_id=self.instance_id,
                                current_leader=current_leader.decode() if current_leader else None
                            )
                    
                except Exception as e:
                    logger.warning("Leader election error", error=str(e))
                    # Continue as leader on error to avoid complete stop
                    worker_state["is_leader"] = True
                
                await asyncio.sleep(self.DETECTION_INTERVAL / 2)
                
        except ImportError:
            logger.warning("Redis not available, disabling leader election")
            worker_state["is_leader"] = True
    
    async def _detection_loop(self):
        """Main detection loop"""
        # Initial delay
        await asyncio.sleep(5)
        
        while self._running:
            try:
                # Only run if leader (or election disabled)
                if worker_state["is_leader"]:
                    await self._run_detection_cycle()
                else:
                    logger.debug("Skipping detection (not leader)", instance_id=self.instance_id)
                
            except Exception as e:
                worker_state["errors"] += 1
                logger.error("Detection cycle failed", error=str(e))
            
            await asyncio.sleep(self.DETECTION_INTERVAL)
    
    async def _run_detection_cycle(self):
        """Run a single detection cycle with hybrid K8s + eBPF detection"""
        from database.postgresql import database
        from datetime import timedelta
        from services.change_detection import K8S_CHANGE_TYPES, EBPF_CHANGE_TYPES
        import json
        
        # Get active analyses with multi-cluster support, detection settings, and current run info
        # Try with new columns first, fallback to basic query if columns don't exist yet
        # Include namespaces and scope_config for namespace-scoped change detection
        query_with_strategy = """
        SELECT a.id, a.name, a.cluster_id, a.cluster_ids, a.is_multi_cluster, a.status, 
               a.started_at, a.change_detection_enabled, a.namespaces, a.scope_config,
               a.change_detection_strategy, a.change_detection_types,
               r.id as run_id, r.run_number
        FROM analyses a
        LEFT JOIN analysis_runs r ON a.id = r.analysis_id AND r.status = 'running'
        WHERE a.status = 'running' AND a.is_active = true
        ORDER BY a.id
        """
        
        # Fallback query without change_detection columns (for pre-migration compatibility)
        # Defaults: change_detection_enabled=true, strategy=baseline, types=all
        query_basic = """
        SELECT a.id, a.name, a.cluster_id, a.cluster_ids, a.is_multi_cluster, a.status, 
               a.started_at, true as change_detection_enabled, a.scope_config,
               NULL as namespaces,
               'baseline' as change_detection_strategy, '["all"]' as change_detection_types,
               r.id as run_id, r.run_number
        FROM analyses a
        LEFT JOIN analysis_runs r ON a.id = r.analysis_id AND r.status = 'running'
        WHERE a.status = 'running' AND a.is_active = true
        ORDER BY a.id
        """
        
        try:
            # Try new schema first
            analyses = await database.fetch_all(query_with_strategy)
        except Exception as e:
            if "change_detection_enabled" in str(e) or "namespaces" in str(e) or "change_detection_strategy" in str(e) or "UndefinedColumn" in str(e):
                # Fallback to basic query (migration not yet applied)
                logger.warning("Using fallback query - some columns not yet migrated")
                try:
                    analyses = await database.fetch_all(query_basic)
                except Exception as e2:
                    logger.error("Failed to fetch analyses (fallback)", error=str(e2))
                    return
            else:
                logger.error("Failed to fetch analyses", error=str(e))
                return
        
        if not analyses:
            logger.debug("No active analyses")
            worker_state["last_detection"] = datetime.now(timezone.utc).isoformat()
            return
        
        logger.info(
            "Starting detection cycle",
            instance_id=self.instance_id,
            analysis_count=len(analyses)
        )
        
        changes_total = 0
        
        for analysis in analyses:
            analysis_id = analysis["id"]
            
            # Skip if change detection is disabled for this analysis
            if analysis.get("change_detection_enabled") is False:
                logger.debug("Change detection disabled for analysis", analysis_id=analysis_id)
                continue
            
            # Get detection settings
            strategy = analysis.get("change_detection_strategy") or "baseline"
            enabled_types_raw = analysis.get("change_detection_types")
            if isinstance(enabled_types_raw, str):
                enabled_types = json.loads(enabled_types_raw)
            elif isinstance(enabled_types_raw, list):
                enabled_types = enabled_types_raw
            else:
                enabled_types = ["all"]
            
            # Get analysis start time for baseline calculation
            analysis_start = analysis.get("started_at")
            if analysis_start is None:
                analysis_start = datetime.now(timezone.utc) - timedelta(hours=1)
            # Ensure timezone-aware datetime
            elif analysis_start.tzinfo is None:
                analysis_start = analysis_start.replace(tzinfo=timezone.utc)
            
            # Check if analysis was restarted - reset baseline if so
            if analysis_id in self._baseline_established:
                baseline_time = self._baseline_established[analysis_id]
                if analysis_start > baseline_time:
                    # Analysis was restarted after baseline was established
                    del self._baseline_established[analysis_id]
                    logger.info(
                        "Analysis restarted - baseline will be re-established",
                        analysis_id=analysis_id,
                        previous_baseline=baseline_time.isoformat(),
                        new_start=analysis_start.isoformat()
                    )
            
            # Get current run info (for run-based tracking)
            run_id = analysis.get("run_id") or 0
            run_number = analysis.get("run_number") or 1
            
            # Get all cluster IDs for multi-cluster support
            cluster_ids = []
            if analysis.get("is_multi_cluster") and analysis.get("cluster_ids"):
                # Parse cluster_ids JSON array
                raw_cluster_ids = analysis["cluster_ids"]
                if isinstance(raw_cluster_ids, str):
                    cluster_ids = json.loads(raw_cluster_ids)
                elif isinstance(raw_cluster_ids, list):
                    cluster_ids = raw_cluster_ids
            
            # Fallback to single cluster_id if no multi-cluster
            if not cluster_ids:
                cluster_ids = [analysis["cluster_id"]]
            
            # Parse namespace scope for filtering
            # Priority: 1) namespaces column, 2) scope_config.namespaces, 3) scope_config.per_cluster_scope
            namespace_scope = []
            raw_namespaces = analysis.get("namespaces")
            
            if raw_namespaces:
                # Use namespaces column if available
                if isinstance(raw_namespaces, str):
                    namespace_scope = json.loads(raw_namespaces)
                elif isinstance(raw_namespaces, list):
                    namespace_scope = raw_namespaces
            
            # Fallback: extract from scope_config if namespaces column is empty
            if not namespace_scope:
                scope_config = analysis.get("scope_config")
                if scope_config:
                    if isinstance(scope_config, str):
                        scope_config = json.loads(scope_config)
                    
                    # Try direct namespaces array (namespace scope type)
                    if scope_config.get("namespaces"):
                        namespace_scope = scope_config["namespaces"]
                    # Try per_cluster_scope for multi-cluster
                    elif scope_config.get("per_cluster_scope"):
                        all_namespaces = set()
                        for cluster_scope in scope_config["per_cluster_scope"].values():
                            if isinstance(cluster_scope, dict) and cluster_scope.get("namespaces"):
                                all_namespaces.update(cluster_scope["namespaces"])
                        if all_namespaces:
                            namespace_scope = list(all_namespaces)
                    # Derive namespaces from deployment/pod items (format: "namespace/name")
                    elif scope_config.get("deployments") or scope_config.get("pods"):
                        derived_ns = set()
                        for items_key in ("deployments", "pods"):
                            items = scope_config.get(items_key, [])
                            if items:
                                for item in items:
                                    if isinstance(item, str) and "/" in item:
                                        derived_ns.add(item.split("/", 1)[0])
                        if derived_ns:
                            namespace_scope = list(derived_ns)
                            logger.info(
                                "Derived namespace_scope from scope_config items",
                                analysis_id=analysis_id,
                                scope_type=scope_config.get("scope_type"),
                                namespace_scope=namespace_scope
                            )
            
            # Cluster-wide fallback: populate namespace_scope from cluster namespaces
            # Only for cluster scope or when no other scope information is available
            if not namespace_scope:
                try:
                    from services.cluster_connection_manager import cluster_connection_manager
                    primary_cluster_id = cluster_ids[0] if cluster_ids else analysis["cluster_id"]
                    ns_resp = await cluster_connection_manager.get_namespaces(primary_cluster_id)
                    system_prefixes = ('kube-', 'openshift-', 'calico-', 'tigera-')
                    namespace_scope = [
                        ns['name'] for ns in ns_resp
                        if not ns.get('name', '').startswith(system_prefixes)
                    ]
                    logger.info(
                        "Cluster-wide: populated namespace_scope from cluster",
                        analysis_id=analysis_id,
                        namespace_count=len(namespace_scope)
                    )
                except Exception as e:
                    logger.warning(
                        "Could not populate namespace_scope for cluster-wide analysis, using analysis_id filter",
                        analysis_id=analysis_id,
                        error=str(e)
                    )

            logger.debug(
                "Processing analysis with hybrid detection",
                analysis_id=analysis_id,
                strategy=strategy,
                enabled_types=enabled_types,
                cluster_count=len(cluster_ids),
                namespace_scope=namespace_scope
            )
            
            all_changes = []
            
            # K8s Detection - Infrastructure changes (per cluster)
            if self._should_run_k8s_detection(enabled_types):
                for cluster_id in cluster_ids:
                    if self._is_circuit_open(cluster_id):
                        continue
                    
                    try:
                        k8s_changes = await self.k8s_detector.detect(
                            cluster_id=cluster_id,
                            analysis_id=str(analysis_id),
                            run_id=run_id,
                            run_number=run_number,
                            enabled_types=enabled_types,
                            namespace_scope=namespace_scope
                        )
                        all_changes.extend(k8s_changes)
                        
                        logger.debug(
                            "K8s detection completed",
                            analysis_id=analysis_id,
                            cluster_id=cluster_id,
                            changes=len(k8s_changes)
                        )
                        
                        self._failure_counts[cluster_id] = 0
                        
                    except Exception as e:
                        logger.error(
                            "K8s detection failed",
                            analysis_id=analysis_id,
                            cluster_id=cluster_id,
                            error=str(e)
                        )
                        self._record_failure(cluster_id)
            
            # eBPF Detection - Behavioral changes (analysis-wide)
            if self._should_run_ebpf_detection(enabled_types):
                try:
                    # Use first cluster_id for eBPF detection (analysis context)
                    primary_cluster_id = cluster_ids[0] if cluster_ids else 0
                    
                    # Refresh ServicePortRegistry for intelligent port filtering
                    # This loads K8s Service definitions to identify valid service ports
                    if self.service_registry:
                        try:
                            await self.service_registry.refresh(
                                cluster_id=primary_cluster_id,
                                namespaces=namespace_scope
                            )
                            # Set registry on eBPF detector for service-level aggregation
                            self.ebpf_detector.set_service_registry(self.service_registry)
                            
                            logger.debug(
                                "ServicePortRegistry refreshed for eBPF detection",
                                cluster_id=primary_cluster_id,
                                namespace_scope=namespace_scope,
                                stats=self.service_registry.get_stats()
                            )
                        except Exception as e:
                            logger.warning(
                                "ServicePortRegistry refresh failed - using fallback port filtering",
                                error=str(e)
                            )
                    
                    # Multi-cluster format: '{analysis_id}-{cluster_id}' matches ingestion pipeline
                    formatted_analysis_id = f"{analysis_id}-{primary_cluster_id}"
                    ebpf_changes = await self.ebpf_detector.detect(
                        cluster_id=primary_cluster_id,
                        analysis_id=formatted_analysis_id,
                        strategy=strategy,
                        run_id=run_id,
                        run_number=run_number,
                        enabled_types=enabled_types,
                        analysis_start=analysis_start,
                        namespace_scope=namespace_scope
                    )
                    all_changes.extend(ebpf_changes)
                    
                    logger.debug(
                        "eBPF detection completed",
                        analysis_id=analysis_id,
                        strategy=strategy,
                        changes=len(ebpf_changes)
                    )
                    
                except Exception as e:
                    logger.error(
                        "eBPF detection failed",
                        analysis_id=analysis_id,
                        error=str(e)
                    )
            
            # Filter by enabled types if not "all"
            if "all" not in enabled_types:
                all_changes = [c for c in all_changes if c.change_type in enabled_types]
            
            # Check if this is the first cycle (baseline establishment)
            is_first_cycle = analysis_id not in self._baseline_established
            
            if is_first_cycle:
                # First cycle: establish baseline without reporting changes
                # The K8s detector already stored workloads to PostgreSQL
                self._baseline_established[analysis_id] = datetime.now(timezone.utc)
                
                baseline_by_type = {}
                for c in all_changes:
                    baseline_by_type[c.change_type] = baseline_by_type.get(c.change_type, 0) + 1
                logger.info(
                    "Baseline established (first cycle - changes not reported)",
                    analysis_id=analysis_id,
                    suppressed_changes=len(all_changes),
                    by_type=baseline_by_type,
                    namespace_scope=namespace_scope[:5] if namespace_scope else [],
                    namespace_count=len(namespace_scope) if namespace_scope else 0,
                )
            elif all_changes:
                # Subsequent cycles: write changes to ClickHouse and notify
                try:
                    # Apply change limit to avoid overwhelming the system
                    if len(all_changes) > self.MAX_CHANGES_PER_CYCLE:
                        # Prioritize changes by risk level and type
                        # Critical/High risk first, then infrastructure changes, then behavioral
                        def change_priority(c):
                            risk_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
                            # Infrastructure changes (K8s) are higher priority
                            type_order = {
                                'workload_added': 0, 'workload_removed': 0,
                                'service_selector_changed': 0, 'service_removed': 0,
                                'replica_changed': 1, 'config_changed': 1, 'image_changed': 1,
                                'service_port_changed': 1, 'service_type_changed': 1,
                                'resource_changed': 1, 'env_changed': 1, 'spec_changed': 1,
                                'service_added': 2, 'label_changed': 2, 'namespace_changed': 2,
                                'network_policy_changed': 2, 'network_policy_added': 2, 'network_policy_removed': 2,
                                'ingress_changed': 2, 'ingress_added': 2, 'ingress_removed': 2,
                                'route_changed': 2, 'route_added': 2, 'route_removed': 2,
                                'connection_added': 3, 'connection_removed': 3,
                                'dns_anomaly': 4, 'process_anomaly': 4,
                                'traffic_anomaly': 5, 'error_anomaly': 5,
                                'port_changed': 6,
                            }
                            risk = risk_order.get(getattr(c, 'risk_level', 'medium'), 2)
                            ctype = type_order.get(getattr(c, 'change_type', ''), 5)
                            return (risk, ctype)
                        
                        all_changes.sort(key=change_priority)
                        original_count = len(all_changes)
                        all_changes = all_changes[:self.MAX_CHANGES_PER_CYCLE]
                        
                        logger.warning(
                            "Change limit applied - too many changes detected",
                            analysis_id=analysis_id,
                            original_count=original_count,
                            limited_to=len(all_changes),
                            max_limit=self.MAX_CHANGES_PER_CYCLE
                        )
                    
                    # Write to ClickHouse via timeseries writer
                    primary_cid = cluster_ids[0] if cluster_ids else analysis.get("cluster_id", 0)
                    new_changes = await self._write_changes_to_clickhouse(
                        all_changes, analysis_id, primary_cid
                    )
                    
                    changes_total += len(new_changes)
                    
                    # Notify critical changes via WebSocket
                    await self._notify_changes(analysis_id, new_changes)
                    
                    logger.info(
                        "Changes detected and written",
                        analysis_id=analysis_id,
                        total_changes=len(new_changes),
                        types=[c.change_type for c in new_changes]
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to write changes",
                        analysis_id=analysis_id,
                        error=str(e)
                    )
            
            self._last_detection[analysis_id] = datetime.now(timezone.utc)
        
        # Cleanup stale state for analyses no longer active
        active_ids = {a["id"] for a in analyses}
        stale_baseline = [aid for aid in self._baseline_established if aid not in active_ids]
        stale_detection = [aid for aid in self._last_detection if aid not in active_ids]
        for aid in stale_baseline:
            del self._baseline_established[aid]
        for aid in stale_detection:
            del self._last_detection[aid]
        if stale_baseline or stale_detection:
            logger.debug(
                "Cleaned up stale analysis state",
                stale_baselines=len(stale_baseline),
                stale_detections=len(stale_detection)
            )

        worker_state["detection_cycles"] += 1
        worker_state["last_detection"] = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "Detection cycle completed",
            instance_id=self.instance_id,
            changes_detected=changes_total
        )
    
    async def _filter_and_record_changes(self, changes, cluster_id, analysis_id):
        """
        Filter duplicates and record new changes.
        
        NOTE: PostgreSQL change_events table was removed. 
        Deduplication now done via ClickHouse query.
        Changes are written via RabbitMQ -> Timeseries Writer -> ClickHouse.
        """
        if not changes:
            return []
        
        # Get recent changes from ClickHouse to avoid duplicates
        try:
            from database.clickhouse import get_clickhouse_client
            ch_client = get_clickhouse_client()
            
            # Query recent changes from ClickHouse
            query = """
            SELECT target_name, change_type, detected_at, target_namespace
            FROM change_events
            WHERE cluster_id = %(cluster_id)s
              AND analysis_id = %(analysis_id)s
              AND detected_at >= now() - INTERVAL 15 MINUTE
            """
            
            formatted_aid = f"{analysis_id}-{cluster_id}"
            result = ch_client.execute(query, {
                'cluster_id': cluster_id,
                'analysis_id': formatted_aid
            })
            
            recent_keys = set()
            for r in result:
                try:
                    ts = r[2].strftime('%Y%m%d%H%M') if r[2] else ''
                    ns = r[3] if len(r) > 3 else ''
                    recent_keys.add(f"{r[0]}:{ns}:{r[1]}:{ts}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Could not query recent changes for dedup", error=str(e))
            recent_keys = set()
        
        # Filter and publish new changes
        new_changes = []
        from services.change_event_publisher import publish_change_event
        
        for change in changes:
            # Handle both dict and Change object
            if hasattr(change, 'to_dict'):
                change_dict = change.to_dict()
            else:
                change_dict = change
            
            target = change_dict.get('target') or change_dict.get('target_name', '')
            target_ns = change_dict.get('namespace') or change_dict.get('target_namespace', '')
            change_type = change_dict.get('change_type', '')
            detected_at = change_dict.get('detected_at') or datetime.now(timezone.utc)
            if isinstance(detected_at, str):
                try:
                    detected_at = datetime.fromisoformat(detected_at.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    detected_at = datetime.now(timezone.utc)
            elif hasattr(detected_at, 'tzinfo') and detected_at.tzinfo is None:
                detected_at = detected_at.replace(tzinfo=timezone.utc)
            
            key = f"{target}:{target_ns}:{change_type}:{detected_at.strftime('%Y%m%d%H%M')}"
            
            if key not in recent_keys:
                # Publish to RabbitMQ -> ClickHouse
                change_dict['cluster_id'] = cluster_id
                change_dict['analysis_id'] = f"{analysis_id}-{cluster_id}"
                change_dict['changed_by'] = f"worker-{self.instance_id}"
                
                success = await publish_change_event(change_dict)
                if success:
                    new_changes.append(change)
                    recent_keys.add(key)  # Prevent duplicates within same batch
        
        return new_changes
    
    async def _notify_changes(self, analysis_id, changes):
        """Send WebSocket notifications for changes"""
        if not changes:
            return
        
        try:
            import httpx
            
            # Send to backend's internal broadcast endpoint
            backend_url = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")
            
            async with httpx.AsyncClient() as client:
                for change in changes:
                    # Handle both Change objects and dicts
                    risk_level = getattr(change, 'risk_level', None) or change.get('risk_level', '')
                    change_type = getattr(change, 'change_type', None) or change.get('change_type', '')
                    target = getattr(change, 'target', None) or change.get('target', '')
                    
                    if risk_level == "critical":
                        payload = {
                            "type": "critical_change",
                            "analysis_id": analysis_id,
                            "analysis_name": "",
                            "remaining_minutes": 0,
                            "message": f"Critical change detected: {change_type} - {target}"
                        }
                        
                        try:
                            await client.post(
                                f"{backend_url}/api/v1/ws/broadcast",
                                json=payload,
                                timeout=5.0
                            )
                        except:
                            pass  # Best effort
                            
        except ImportError:
            pass
    
    def _should_run_k8s_detection(self, enabled_types: list) -> bool:
        """Check if K8s detection should run based on enabled types"""
        from services.change_detection import K8S_CHANGE_TYPES
        
        if 'all' in enabled_types:
            return True
        return any(t in K8S_CHANGE_TYPES for t in enabled_types)
    
    def _should_run_ebpf_detection(self, enabled_types: list) -> bool:
        """Check if eBPF detection should run based on enabled types"""
        from services.change_detection import EBPF_CHANGE_TYPES
        
        if 'all' in enabled_types:
            return True
        return any(t in EBPF_CHANGE_TYPES for t in enabled_types)
    
    async def _write_changes_to_clickhouse(self, changes: list, analysis_id: int, cluster_id: int = 0) -> list:
        """
        Write detected changes to ClickHouse via RabbitMQ.

        Changes are published to the change_events queue and consumed
        by the Timeseries Writer service.
        """
        import json

        if not changes:
            return []

        try:
            # Use the module-level async publish function
            from services.change_event_publisher import publish_change_event

            written_changes = []
            for change in changes:
                # Convert Change object to dict for publishing
                change_dict = change.to_dict() if hasattr(change, 'to_dict') else change

                # Multi-cluster format: '{analysis_id}-{cluster_id}'
                change_dict['analysis_id'] = f"{analysis_id}-{cluster_id}" if cluster_id else str(analysis_id)

                # Publish to RabbitMQ (async function)
                success = await publish_change_event(change_dict)
                if success:
                    written_changes.append(change)
                else:
                    logger.warning("Failed to publish change event", change_type=change_dict.get('change_type'))
            
            logger.debug(
                "Changes published to RabbitMQ",
                analysis_id=analysis_id,
                count=len(written_changes)
            )
            
            return written_changes
            
        except Exception as e:
            logger.error(
                "Failed to publish changes to RabbitMQ",
                analysis_id=analysis_id,
                error=str(e)
            )
            
            # Fallback: Try direct ClickHouse write
            return await self._write_changes_direct(changes, analysis_id, cluster_id)
    
    async def _write_changes_direct(self, changes: list, analysis_id: int, cluster_id: int = 0) -> list:
        """
        Fallback: Write changes directly to ClickHouse if RabbitMQ is unavailable.
        """
        try:
            from clickhouse_driver import Client
            
            ch_client = Client(
                host=os.getenv('CLICKHOUSE_HOST', 'clickhouse'),
                port=int(os.getenv('CLICKHOUSE_PORT', '9000')),
                user=os.getenv('CLICKHOUSE_USER', 'flowfish'),
                password=os.getenv('CLICKHOUSE_PASSWORD', ''),
                database=os.getenv('CLICKHOUSE_DATABASE', 'flowfish'),
            )
            
            for change in changes:
                change_dict = change.to_dict() if hasattr(change, 'to_dict') else change
                
                ch_client.execute(
                    """
                    INSERT INTO change_events (
                        event_id, timestamp, detected_at, cluster_id, analysis_id,
                        run_id, run_number, change_type, risk_level,
                        target_name, target_namespace, target_type,
                        entity_id, namespace_id,
                        before_state, after_state, affected_services,
                        blast_radius, changed_by, details, metadata
                    ) VALUES
                    """,
                    [(
                        change_dict.get('event_id', ''),
                        change_dict.get('timestamp', datetime.now(timezone.utc)),
                        change_dict.get('detected_at', datetime.now(timezone.utc)),
                        change_dict.get('cluster_id', 0),
                        f"{analysis_id}-{cluster_id}" if cluster_id else str(analysis_id),
                        change_dict.get('run_id', 0),
                        change_dict.get('run_number', 1),
                        change_dict.get('change_type', ''),
                        change_dict.get('risk_level', 'medium'),
                        change_dict.get('target_name', change_dict.get('target', '')),
                        change_dict.get('target_namespace', change_dict.get('namespace', '')),
                        change_dict.get('target_type', 'workload'),
                        change_dict.get('entity_id', 0),
                        change_dict.get('namespace_id', 0),
                        json.dumps(change_dict.get('before_state', {}), default=str),
                        json.dumps(change_dict.get('after_state', {}), default=str),
                        change_dict.get('affected_services', 0),
                        change_dict.get('blast_radius', 0),
                        change_dict.get('changed_by', 'auto-discovery'),
                        change_dict.get('details', ''),
                        json.dumps(change_dict.get('metadata', {}), default=str)
                    )]
                )
            
            logger.debug(
                "Changes written directly to ClickHouse",
                analysis_id=analysis_id,
                count=len(changes)
            )
            
            return changes
            
        except Exception as e:
            logger.error(
                "Direct ClickHouse write failed",
                analysis_id=analysis_id,
                error=str(e)
            )
            return []
    
    def _record_failure(self, cluster_id):
        """Record failure for circuit breaker"""
        self._failure_counts[cluster_id] = self._failure_counts.get(cluster_id, 0) + 1
        
        if self._failure_counts[cluster_id] >= self.CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_open_until[cluster_id] = datetime.now(timezone.utc) + timedelta(
                seconds=self.CIRCUIT_BREAKER_RESET_TIME
            )
            logger.warning(
                "Circuit breaker opened",
                cluster_id=cluster_id,
                instance_id=self.instance_id
            )
    
    def _is_circuit_open(self, cluster_id):
        """Check circuit breaker status"""
        if cluster_id not in self._circuit_open_until:
            return False
        
        if datetime.now(timezone.utc) >= self._circuit_open_until[cluster_id]:
            del self._circuit_open_until[cluster_id]
            self._failure_counts[cluster_id] = 0
            return False
        
        return True
    
    def get_status(self):
        """Get worker status"""
        return {
            "instance_id": self.instance_id,
            "running": self._running,
            "is_leader": worker_state["is_leader"],
            "leader_election_enabled": self.leader_election_enabled,
            "config": {
                "detection_interval": self.DETECTION_INTERVAL,
                "lookback_minutes": self.LOOKBACK_MINUTES,
                "circuit_breaker_threshold": self.CIRCUIT_BREAKER_THRESHOLD
            },
            "stats": {
                "started_at": worker_state["started_at"],
                "detection_cycles": worker_state["detection_cycles"],
                "last_detection": worker_state["last_detection"],
                "errors": worker_state["errors"]
            },
            "circuits_open": {
                cid: ts.isoformat()
                for cid, ts in self._circuit_open_until.items()
            }
        }


# Global worker instance
worker = StandaloneChangeDetectionWorker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    print("🔄 LIFESPAN: Starting Change Detection Worker...")
    logger.info(
        "🔄 Starting Change Detection Worker...",
        instance_id=WORKER_INSTANCE_ID
    )
    
    # Test database connections
    try:
        print("🔄 LIFESPAN: Testing PostgreSQL connection...")
        from database.postgresql import test_connection
        pg_ok = await test_connection()
        if pg_ok:
            print("✅ LIFESPAN: PostgreSQL connected")
            logger.info("✅ PostgreSQL connected")
        else:
            print("⚠️ LIFESPAN: PostgreSQL connection failed")
            logger.warning("⚠️ PostgreSQL connection failed")
    except Exception as e:
        print(f"❌ LIFESPAN: Database connection failed: {e}")
        logger.error("❌ Database connection failed", error=str(e))
    
    # Start worker
    try:
        print("🔄 LIFESPAN: Starting worker...")
        await worker.start()
        print("🚀 LIFESPAN: Change Detection Worker started!")
        logger.info("🚀 Change Detection Worker started!")
    except Exception as e:
        print(f"❌ LIFESPAN: Worker start failed: {e}")
        logger.error("❌ Worker start failed", error=str(e))
        import traceback
        traceback.print_exc()
    
    yield
    
    # Shutdown
    print("🛑 LIFESPAN: Stopping Change Detection Worker...")
    logger.info("🛑 Stopping Change Detection Worker...")
    await worker.stop()
    print("👋 LIFESPAN: Change Detection Worker stopped")
    logger.info("👋 Change Detection Worker stopped")


# Create FastAPI app for health checks and metrics
app = FastAPI(
    title="Flowfish Change Detection Worker",
    description="Standalone change detection worker for Flowfish platform",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
@app.get("/healthz")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    status = worker.get_status()
    
    is_healthy = status["running"]
    
    # Check if detection loop is alive (not stuck)
    if status["is_leader"] and status["stats"]["detection_cycles"] > 0:
        last = status["stats"]["last_detection"]
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - last_dt).total_seconds()
            # Unhealthy only if detection loop is truly stuck (5x interval)
            if age_seconds > worker.DETECTION_INTERVAL * 5:
                is_healthy = False
    
    return JSONResponse(
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "instance_id": WORKER_INSTANCE_ID,
            "is_leader": status["is_leader"],
            "detection_cycles": status["stats"]["detection_cycles"],
            "last_detection": status["stats"]["last_detection"]
        },
        status_code=200 if is_healthy else 503
    )


@app.get("/ready")
@app.get("/readyz")
async def readiness_check():
    """Readiness check for Kubernetes"""
    status = worker.get_status()
    
    return JSONResponse(
        content={
            "ready": status["running"],
            "instance_id": WORKER_INSTANCE_ID
        },
        status_code=200 if status["running"] else 503
    )


@app.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint"""
    status = worker.get_status()
    
    metrics_text = f"""# HELP flowfish_change_worker_detection_cycles_total Total detection cycles
# TYPE flowfish_change_worker_detection_cycles_total counter
flowfish_change_worker_detection_cycles_total{{instance="{WORKER_INSTANCE_ID}"}} {status["stats"]["detection_cycles"]}

# HELP flowfish_change_worker_errors_total Total errors
# TYPE flowfish_change_worker_errors_total counter
flowfish_change_worker_errors_total{{instance="{WORKER_INSTANCE_ID}"}} {status["stats"]["errors"]}

# HELP flowfish_change_worker_is_leader Whether this instance is the leader
# TYPE flowfish_change_worker_is_leader gauge
flowfish_change_worker_is_leader{{instance="{WORKER_INSTANCE_ID}"}} {1 if status["is_leader"] else 0}

# HELP flowfish_change_worker_running Whether the worker is running
# TYPE flowfish_change_worker_running gauge
flowfish_change_worker_running{{instance="{WORKER_INSTANCE_ID}"}} {1 if status["running"] else 0}

# HELP flowfish_change_worker_circuits_open Number of open circuit breakers
# TYPE flowfish_change_worker_circuits_open gauge
flowfish_change_worker_circuits_open{{instance="{WORKER_INSTANCE_ID}"}} {len(status["circuits_open"])}
"""
    
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=metrics_text, media_type="text/plain")


@app.get("/status")
async def get_status():
    """Detailed status endpoint"""
    return worker.get_status()


@app.post("/trigger/{analysis_id}")
async def trigger_detection(analysis_id: int):
    """
    Manually trigger detection for an analysis.
    
    Uses the new hybrid K8s + eBPF detector architecture.
    """
    from database.postgresql import database
    from datetime import timedelta
    import json
    
    # Get analysis info with detection settings
    # Try with new columns first, fallback if not migrated yet
    # Include scope_config for namespace extraction fallback
    query_with_strategy = """
        SELECT a.id, a.cluster_id, a.cluster_ids, a.is_multi_cluster, a.status,
               a.started_at, a.change_detection_enabled, a.scope_config,
               a.change_detection_strategy, a.change_detection_types, a.namespaces,
               r.id as run_id, r.run_number
        FROM analyses a
        LEFT JOIN analysis_runs r ON a.id = r.analysis_id AND r.status = 'running'
        WHERE a.id = :analysis_id
    """
    
    query_basic = """
        SELECT a.id, a.cluster_id, a.cluster_ids, a.is_multi_cluster, a.status,
               a.started_at, true as change_detection_enabled, a.scope_config,
               'baseline' as change_detection_strategy, '["all"]' as change_detection_types,
               NULL as namespaces,
               r.id as run_id, r.run_number
        FROM analyses a
        LEFT JOIN analysis_runs r ON a.id = r.analysis_id AND r.status = 'running'
        WHERE a.id = :analysis_id
    """
    
    try:
        analysis = await database.fetch_one(query_with_strategy, {"analysis_id": analysis_id})
    except Exception as e:
        if "change_detection_enabled" in str(e) or "namespaces" in str(e) or "change_detection_strategy" in str(e) or "UndefinedColumn" in str(e):
            logger.warning("Using fallback query for trigger - columns not yet migrated")
            analysis = await database.fetch_one(query_basic, {"analysis_id": analysis_id})
        else:
            raise
    
    if not analysis:
        return JSONResponse(
            content={"error": f"Analysis {analysis_id} not found"},
            status_code=404
        )
    
    if analysis["status"] != "running":
        return JSONResponse(
            content={"error": f"Analysis {analysis_id} is not running"},
            status_code=400
        )
    
    if analysis.get("change_detection_enabled") is False:
        return JSONResponse(
            content={"error": f"Change detection is disabled for analysis {analysis_id}"},
            status_code=400
        )
    
    try:
        # Parse detection settings
        strategy = analysis.get("change_detection_strategy") or "baseline"
        enabled_types_raw = analysis.get("change_detection_types")
        if isinstance(enabled_types_raw, str):
            enabled_types = json.loads(enabled_types_raw)
        elif isinstance(enabled_types_raw, list):
            enabled_types = enabled_types_raw
        else:
            enabled_types = ["all"]
        
        # Get cluster IDs (needed before namespace scope derivation)
        cluster_ids = []
        if analysis.get("is_multi_cluster") and analysis.get("cluster_ids"):
            raw = analysis["cluster_ids"]
            cluster_ids = json.loads(raw) if isinstance(raw, str) else raw
        if not cluster_ids:
            cluster_ids = [analysis["cluster_id"]]
        
        # Parse namespace scope with fallback to scope_config
        namespace_scope = []
        namespaces_raw = analysis.get("namespaces")
        
        if namespaces_raw:
            if isinstance(namespaces_raw, str):
                namespace_scope = json.loads(namespaces_raw)
            elif isinstance(namespaces_raw, list):
                namespace_scope = namespaces_raw
        
        # Fallback: extract from scope_config if namespaces is empty
        if not namespace_scope:
            scope_config = analysis.get("scope_config")
            if scope_config:
                if isinstance(scope_config, str):
                    scope_config = json.loads(scope_config)
                
                if scope_config.get("namespaces"):
                    namespace_scope = scope_config["namespaces"]
                elif scope_config.get("per_cluster_scope"):
                    all_namespaces = set()
                    for cluster_scope in scope_config["per_cluster_scope"].values():
                        if isinstance(cluster_scope, dict) and cluster_scope.get("namespaces"):
                            all_namespaces.update(cluster_scope["namespaces"])
                    if all_namespaces:
                        namespace_scope = list(all_namespaces)
                elif scope_config.get("deployments") or scope_config.get("pods"):
                    derived_ns = set()
                    for items_key in ("deployments", "pods"):
                        items = scope_config.get(items_key, [])
                        if items:
                            for item in items:
                                if isinstance(item, str) and "/" in item:
                                    derived_ns.add(item.split("/", 1)[0])
                    if derived_ns:
                        namespace_scope = list(derived_ns)
                        logger.info(
                            "Trigger: derived namespace_scope from scope_config items",
                            analysis_id=analysis_id,
                            namespace_scope=namespace_scope
                        )
        
        # Cluster-wide fallback: populate namespace_scope from cluster namespaces
        if not namespace_scope:
            try:
                from services.cluster_connection_manager import cluster_connection_manager
                primary_cluster_id = cluster_ids[0] if cluster_ids else analysis["cluster_id"]
                ns_resp = await cluster_connection_manager.get_namespaces(primary_cluster_id)
                system_prefixes = ('kube-', 'openshift-', 'calico-', 'tigera-')
                namespace_scope = [
                    ns['name'] for ns in ns_resp
                    if not ns.get('name', '').startswith(system_prefixes)
                ]
                logger.info(
                    "Trigger: cluster-wide namespace_scope populated",
                    analysis_id=analysis_id,
                    namespace_count=len(namespace_scope)
                )
            except Exception as e:
                logger.warning(
                    "Trigger: could not populate namespace_scope",
                    analysis_id=analysis_id,
                    error=str(e)
                )
        
        analysis_start = analysis.get("started_at")
        if analysis_start is None:
            analysis_start = datetime.now(timezone.utc) - timedelta(hours=1)
        # Ensure timezone-aware datetime
        elif analysis_start.tzinfo is None:
            analysis_start = analysis_start.replace(tzinfo=timezone.utc)
        
        run_id = analysis.get("run_id") or 0
        run_number = analysis.get("run_number") or 1
        
        all_changes = []
        
        # K8s Detection
        from services.change_detection import K8S_CHANGE_TYPES, EBPF_CHANGE_TYPES
        
        if 'all' in enabled_types or any(t in K8S_CHANGE_TYPES for t in enabled_types):
            for cluster_id in cluster_ids:
                try:
                    k8s_changes = await worker.k8s_detector.detect(
                        cluster_id=cluster_id,
                        analysis_id=str(analysis_id),
                        run_id=run_id,
                        run_number=run_number,
                        enabled_types=enabled_types,
                        namespace_scope=namespace_scope
                    )
                    all_changes.extend(k8s_changes)
                except Exception as e:
                    logger.warning("K8s detection failed for cluster", cluster_id=cluster_id, error=str(e))
        
        # eBPF Detection
        if 'all' in enabled_types or any(t in EBPF_CHANGE_TYPES for t in enabled_types):
            try:
                primary_cluster_id = cluster_ids[0] if cluster_ids else 0
                
                # Refresh ServicePortRegistry for intelligent port filtering
                if worker.service_registry:
                    try:
                        await worker.service_registry.refresh(
                            cluster_id=primary_cluster_id,
                            namespaces=namespace_scope
                        )
                        worker.ebpf_detector.set_service_registry(worker.service_registry)
                    except Exception as e:
                        logger.warning("ServicePortRegistry refresh failed", error=str(e))
                
                formatted_analysis_id = f"{analysis_id}-{primary_cluster_id}"
                ebpf_changes = await worker.ebpf_detector.detect(
                    cluster_id=primary_cluster_id,
                    analysis_id=formatted_analysis_id,
                    strategy=strategy,
                    run_id=run_id,
                    run_number=run_number,
                    enabled_types=enabled_types,
                    analysis_start=analysis_start,
                    namespace_scope=namespace_scope
                )
                all_changes.extend(ebpf_changes)
            except Exception as e:
                logger.warning("eBPF detection failed", error=str(e))
        
        # Check if this is the first detection (baseline establishment)
        is_first_cycle = analysis_id not in worker._baseline_established
        
        if is_first_cycle:
            # First detection: establish baseline without reporting changes
            worker._baseline_established[analysis_id] = datetime.now(timezone.utc)
            
            return {
                "analysis_id": analysis_id,
                "changes_detected": 0,
                "instance_id": WORKER_INSTANCE_ID,
                "message": "Baseline established (first detection - changes not reported)",
                "baseline_workloads": len([c for c in all_changes if c.change_type == 'workload_added']),
                "baseline_labels": len([c for c in all_changes if c.change_type == 'label_changed'])
            }
        
        # Apply enabled_types filter (same as main detection cycle)
        if 'all' not in enabled_types:
            all_changes = [c for c in all_changes if c.change_type in enabled_types]
        
        # Limit changes to prevent overload
        if len(all_changes) > worker.MAX_CHANGES_PER_CYCLE:
            logger.warning(
                "Trigger: change limit applied",
                analysis_id=analysis_id,
                original_count=len(all_changes),
                limited_to=worker.MAX_CHANGES_PER_CYCLE
            )
            all_changes = all_changes[:worker.MAX_CHANGES_PER_CYCLE]
        
        # Filter and record (subsequent detections)
        new_changes = await worker._filter_and_record_changes(
            all_changes, cluster_ids[0], analysis_id
        )
        
        return {
            "analysis_id": analysis_id,
            "changes_detected": len(new_changes),
            "instance_id": WORKER_INSTANCE_ID,
            "changes": [c.to_dict() if hasattr(c, 'to_dict') else c for c in new_changes[:10]]
        }
        
    except Exception as e:
        logger.error("Manual trigger failed", error=str(e))
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    # For local development
    uvicorn.run(
        "worker_main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
