"""
kubectl gadget CLI client for Inspektor Gadget v0.46.0+
Uses subprocess to run kubectl gadget commands
"""

import asyncio
import fnmatch
import json
import subprocess
import shutil
from typing import List, AsyncIterator, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
import structlog
import uuid
import os
import signal

from .abstract_gadget_client import (
    AbstractGadgetClient,
    Protocol,
    AuthMethod,
    TraceConfig,
    HealthStatus,
    Event
)
from app.constants import GADGET_DEFAULT_VERSION

if TYPE_CHECKING:
    from app.pod_discovery import PodIPCache

logger = structlog.get_logger()


class KubectlGadgetClient(AbstractGadgetClient):
    """
    kubectl gadget CLI client for Inspektor Gadget v0.46.0+
    
    This client spawns kubectl gadget commands as subprocesses
    and streams the JSON output as events.
    
    Features:
    - Works with Inspektor Gadget v0.46.0+
    - No direct gRPC connection needed
    - Uses kubectl context for authentication
    - Supports all gadget types
    
    Requirements:
    - kubectl and kubectl-gadget plugin installed
    - Valid kubeconfig with cluster access
    """
    
    TRACE_TYPE_TO_GADGET = {
        # Network traces - using trace_tcp since trace_network doesn't exist as OCI artifact
        "network": "trace_tcp",
        "network_traffic": "trace_tcp",
        "network_flow": "trace_tcp",
        "trace_network": "trace_tcp",  # Alias for backwards compatibility
        
        # DNS traces
        "dns": "trace_dns",
        "dns_query": "trace_dns",
        "dns_queries": "trace_dns",
        "trace_dns": "trace_dns",
        
        # TCP traces - all TCP events go to network_flow
        # NOTE: tcp_lifecycle removed - Inspektor Gadget trace_tcp doesn't produce
        # TCP state transition events, only connect/accept/close
        "tcp": "trace_tcp",
        "tcp_connections": "trace_tcp",
        "tcp_connection": "trace_tcp",
        "trace_tcp": "trace_tcp",
        
        # TCP Retransmit traces - for network error detection
        "tcp_retransmit": "trace_tcpretrans",
        "tcpretrans": "trace_tcpretrans",
        "trace_tcpretrans": "trace_tcpretrans",
        
        # Process traces
        "process": "trace_exec",
        "process_exec": "trace_exec",
        "process_events": "trace_exec",
        "process_event": "trace_exec",
        "exec": "trace_exec",
        "trace_exec": "trace_exec",
        
        # File traces
        "file": "trace_open",
        "file_access": "trace_open",
        "file_event": "trace_open",
        "file_events": "trace_open",
        "file_operations": "trace_open",  # From analysis-orchestrator
        "open": "trace_open",
        "trace_open": "trace_open",
        
        # Security/Capabilities traces
        "security": "trace_capabilities",
        "capabilities": "trace_capabilities",
        "capability_checks": "trace_capabilities",
        "security_event": "trace_capabilities",
        "trace_capabilities": "trace_capabilities",
        
        # OOM traces
        "oom": "trace_oomkill",
        "oomkill": "trace_oomkill",
        "oom_kills": "trace_oomkill",  # From analysis-orchestrator
        "oom_event": "trace_oomkill",
        "trace_oomkill": "trace_oomkill",
        
        # Bind traces
        "bind": "trace_bind",
        "bind_event": "trace_bind",
        "bind_events": "trace_bind",  # From analysis-orchestrator
        "trace_bind": "trace_bind",
        
        # SNI traces
        "sni": "trace_sni",
        "sni_event": "trace_sni",
        "sni_events": "trace_sni",  # From analysis-orchestrator
        "trace_sni": "trace_sni",
        
        # Mount traces
        "mount": "trace_mount",
        "mount_event": "trace_mount",
        "mount_events": "trace_mount",  # From analysis-orchestrator
        "trace_mount": "trace_mount",
        
        # Top gadgets for throughput/metrics data
        "top_tcp": "top_tcp",           # TCP throughput (bytes sent/received)
        "tcp_throughput": "top_tcp",    # Alias
        "network_bytes": "top_tcp",     # Alias for byte transfer data
    }
    
    def __init__(
        self,
        gadget_namespace: str,  # REQUIRED - from UI (must be first, no default)
        kubeconfig: Optional[str] = None,
        context: Optional[str] = None,
        kubectl_path: str = "kubectl",
        gadget_image_version: str = GADGET_DEFAULT_VERSION,
        gadget_registry: str = "",
        gadget_image_prefix: str = "gadget-",
        timeout_seconds: int = 30,
        **kwargs
    ):
        super().__init__(
            endpoint="kubectl-gadget",
            protocol=Protocol.AGENT,
            auth_method=AuthMethod.KUBECONFIG,
            use_tls=False,
            timeout_seconds=timeout_seconds,
            **kwargs
        )
        
        # Validate required gadget_namespace
        if not gadget_namespace:
            raise ValueError("gadget_namespace is required but not provided. "
                           "Ensure the cluster has a valid Inspector Gadget namespace configured.")
        
        self.kubeconfig = kubeconfig or os.environ.get("KUBECONFIG")
        self.context = context
        self.kubectl_path = kubectl_path
        self.gadget_namespace = gadget_namespace
        self.gadget_image_version = gadget_image_version
        self.gadget_registry = gadget_registry  # e.g., "harbor.example.com/flowfish"
        self.gadget_image_prefix = gadget_image_prefix  # e.g., "gadget-"
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.active_traces: Dict[str, Dict[str, Any]] = {}
        
        # Verify kubectl-gadget is available
        self._kubectl_gadget_available = self._check_kubectl_gadget()
        
        logger.info("KubectlGadgetClient initialized",
                   kubeconfig=self.kubeconfig,
                   context=self.context,
                   gadget_image_version=self.gadget_image_version,
                   gadget_registry=self.gadget_registry or "default (ghcr.io)",
                   gadget_image_prefix=self.gadget_image_prefix,
                   gadget_available=self._kubectl_gadget_available)
    
    def _check_kubectl_gadget(self) -> bool:
        """Check if kubectl-gadget plugin is available"""
        try:
            result = subprocess.run(
                [self.kubectl_path, "gadget", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info("kubectl-gadget available", version=result.stdout.strip())
                return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("kubectl-gadget not available", error=str(e))
            return False
    
    def _build_kubectl_cmd(self, args: List[str]) -> List[str]:
        """Build regular kubectl command with context/kubeconfig at START"""
        cmd = [self.kubectl_path]
        
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            cmd.extend(["--context", self.context])
        
        cmd.extend(args)
        return cmd
    
    def _build_gadget_cmd(self, gadget_args: List[str]) -> List[str]:
        """
        Build kubectl gadget command with context/kubeconfig at END
        
        For kubectl plugins, flags must come AFTER plugin name:
        - WRONG: kubectl --kubeconfig /tmp/k.yaml gadget run ...
        - RIGHT: kubectl gadget run ... --kubeconfig /tmp/k.yaml
        """
        cmd = [self.kubectl_path, "gadget"]
        cmd.extend(gadget_args)
        
        # Add kubeconfig/context at the END for plugin mode
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            cmd.extend(["--context", self.context])
        
        return cmd
    
    async def connect(self) -> bool:
        """Verify kubectl-gadget is available"""
        try:
            if not self._kubectl_gadget_available:
                self._kubectl_gadget_available = self._check_kubectl_gadget()
            
            if not self._kubectl_gadget_available:
                logger.error("kubectl-gadget plugin not available")
                self.connected = False
                return False
            
            # Verify kubectl can access the cluster by checking pods in gadget namespace
            # Note: Using pods instead of nodes because nodes require cluster-wide RBAC
            cmd = self._build_kubectl_cmd([
                "get", "pods", 
                "-n", self.gadget_namespace,
                "-l", "k8s-app=gadget",  # Inspektor Gadget pods
                "-o", "name", 
                "--no-headers"
            ])
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            )
            
            if result.returncode == 0:
                self.connected = True
                gadget_pods = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
                logger.info("kubectl-gadget ready", gadget_pods=gadget_pods, gadget_namespace=self.gadget_namespace)
                return True
            else:
                logger.error("kubectl cluster connection failed", stderr=result.stderr)
                self.connected = False
                return False
                
        except Exception as e:
            logger.error("kubectl-gadget connection failed", error=str(e))
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Stop all active traces and cleanup"""
        try:
            # Stop all active processes
            for trace_id in list(self.active_processes.keys()):
                await self.stop_trace(trace_id)
            
            self.connected = False
            logger.info("kubectl-gadget client disconnected")
            return True
            
        except Exception as e:
            logger.error("disconnect failed", error=str(e))
            return False
    
    async def start_trace(self, config: TraceConfig) -> str:
        """Start a gadget trace using kubectl gadget run"""
        try:
            trace_id = f"trace-{config.analysis_id}-{uuid.uuid4().hex[:8]}"
            
            # DEBUG: Always log trace start to verify code is running (v2)
            logger.warning("=== TRACE_START_V2 === trace_type=%s analysis_id=%s",
                          config.trace_type, config.analysis_id)
            
            # Map trace type to gadget name
            gadget_name = self.TRACE_TYPE_TO_GADGET.get(
                config.trace_type.lower(),
                f"trace_{config.trace_type.lower()}"
            )
            
            # DEBUG: Log gadget name mapping result
            logger.warning("=== GADGET_MAPPED_V2 === trace_type=%s -> gadget_name=%s",
                          config.trace_type, gadget_name)
            
            # Build full image reference with optional registry
            if self.gadget_registry:
                # Use flat naming: registry/prefix+gadget:tag
                # e.g., harbor.example.com/flowfish/gadget-trace_network:latest
                image_ref = f"{self.gadget_registry}/{self.gadget_image_prefix}{gadget_name}:{self.gadget_image_version}"
            else:
                # Use default (ghcr.io/inspektor-gadget/gadget)
                image_ref = f"{gadget_name}:{self.gadget_image_version}"
            
            # Build gadget args list (everything after 'kubectl gadget')
            gadget_args = [
                "run",
                image_ref,
                "--gadget-namespace", self.gadget_namespace,
                "-o", "json"
            ]
            
            # ============================================================
            # NAMESPACE SCOPE STRATEGY: Always collect cluster-wide, filter later
            # ============================================================
            # Previously: Single namespace scope used `-n namespace` which caused
            # the gadget to ONLY trace pods in that namespace. This missed all
            # INCOMING traffic from other namespaces (e.g., API gateway → app).
            #
            # NEW APPROACH: Always use -A (all namespaces) and filter in stream_events()
            # This allows us to capture:
            # - Outgoing traffic FROM target namespace
            # - Incoming traffic TO target namespace (from any other namespace)
            #
            # The filtering logic in stream_events() checks both source AND destination
            # namespaces, including events where either endpoint is in target namespace.
            # ============================================================
            target_namespaces = None
            if config.namespaces and len(config.namespaces) >= 1:
                # One or more target namespaces - collect all, filter later
                gadget_args.append("-A")
                target_namespaces = set(config.namespaces)
                logger.info("Namespace-scoped trace (cluster-wide collection)", 
                           target_namespaces=list(target_namespaces))
            elif config.namespace:
                # Single namespace scope - collect all, filter later
                gadget_args.append("-A")
                target_namespaces = {config.namespace}
                logger.info("Namespace-scoped trace (cluster-wide collection)", 
                           target_namespace=config.namespace)
            else:
                gadget_args.append("-A")  # All namespaces, no filtering
            
            # Add pod filter
            if config.pod_name:
                gadget_args.extend(["--podname", config.pod_name])
            
            # Add label filters
            if config.labels:
                for key, value in config.labels.items():
                    gadget_args.extend(["-l", f"{key}={value}"])
            
            # Build final command with kubeconfig/context at END (required for kubectl plugins)
            cmd = self._build_gadget_cmd(gadget_args)
            
            # Log with emphasis for top_tcp (byte transfer gadget)
            if gadget_name == "top_tcp":
                logger.warning("🔵 STARTING top_tcp gadget (byte transfer metrics)",
                              trace_id=trace_id,
                              image_ref=image_ref,
                              cmd=" ".join(cmd))
            else:
                logger.info("Starting kubectl gadget trace",
                           trace_id=trace_id,
                           gadget=gadget_name,
                           cmd=" ".join(cmd))
            
            # Start subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            self.active_processes[trace_id] = process
            self.active_traces[trace_id] = {
                "trace_id": trace_id,
                "gadget_name": gadget_name,
                "config": config,
                "started_at": datetime.utcnow().isoformat(),
                "events_collected": 0,
                "process": process,
                "target_namespaces": target_namespaces,  # For multi-namespace filtering
                "startup_error": None,  # Will be set if gadget fails to start (checked later)
                "startup_warning": None  # Will be set if gadget has issues
            }
            
            # NOTE: Don't wait here - errors will be checked later via check_startup_errors()
            # This prevents blocking when starting multiple gadgets
            
            logger.info("kubectl gadget trace started",
                       trace_id=trace_id,
                       gadget=gadget_name,
                       pid=process.pid)
            
            # Quick stderr check for immediate failures (non-blocking)
            import select
            if hasattr(select, 'select') and process.stderr:
                # Check if stderr has data available (non-blocking)
                import time
                time.sleep(0.5)  # Brief wait for immediate errors
                try:
                    # Read any available stderr without blocking
                    import fcntl
                    import os as os_module
                    fd = process.stderr.fileno()
                    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os_module.O_NONBLOCK)
                    try:
                        stderr_data = process.stderr.read(2000)
                        if stderr_data and stderr_data.strip():
                            logger.warning("Gadget stderr output (early)",
                                          trace_id=trace_id,
                                          gadget=gadget_name,
                                          stderr=stderr_data[:500])
                    except (IOError, BlockingIOError):
                        pass  # No stderr data yet
                    finally:
                        fcntl.fcntl(fd, fcntl.F_SETFL, fl)  # Restore flags
                except Exception as e:
                    pass  # Ignore stderr check errors
            
            return trace_id
            
        except Exception as e:
            logger.error("Failed to start kubectl gadget trace", error=str(e))
            raise
    
    async def stream_events(
        self, 
        trace_id: str,
        pod_ip_cache: Optional["PodIPCache"] = None
    ) -> AsyncIterator[Event]:
        """Stream events from kubectl gadget output
        
        Args:
            trace_id: Trace identifier
            pod_ip_cache: Optional PodIPCache for resolving destination IPs to namespaces.
                         Used for namespace-scoped analyses to include INCOMING traffic.
        """
        if trace_id not in self.active_traces:
            raise ValueError(f"Trace {trace_id} not found")
        
        trace_info = self.active_traces[trace_id]
        process = trace_info["process"]
        config = trace_info["config"]
        target_namespaces = trace_info.get("target_namespaces")  # Set of namespaces or None
        
        try:
            logger.info("Starting event stream", 
                       trace_id=trace_id,
                       target_namespaces=list(target_namespaces) if target_namespaces else None,
                       has_pod_ip_cache=pod_ip_cache is not None)
            
            # Read stdout line by line
            while process.poll() is None:
                line = await asyncio.get_event_loop().run_in_executor(
                    None,
                    process.stdout.readline
                )
                
                if not line:
                    await asyncio.sleep(0.01)
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse JSON event
                try:
                    event_data = json.loads(line)
                    
                    # ============================================================
                    # HANDLE LIST OUTPUT FROM top_tcp AND OTHER AGGREGATION GADGETS
                    # ============================================================
                    # top_tcp gadget returns aggregated data as a JSON array (list)
                    # where each element represents a connection's throughput data.
                    # We need to iterate over the list and yield each element as
                    # a separate event.
                    # ============================================================
                    if isinstance(event_data, list):
                        gadget_name = trace_info["gadget_name"]
                        # Log first occurrence for debugging
                        if not hasattr(self, '_list_output_logged'):
                            self._list_output_logged = {}
                        if gadget_name not in self._list_output_logged:
                            self._list_output_logged[gadget_name] = True
                            logger.info("Gadget returned list output (aggregated data)",
                                       gadget=gadget_name,
                                       trace_id=trace_id,
                                       list_length=len(event_data),
                                       sample=str(event_data[0])[:200] if event_data else "empty")
                        
                        # Process each item in the list
                        for item in event_data:
                            if not isinstance(item, dict):
                                logger.debug("Skipping non-dict item in list", item_type=type(item).__name__)
                                continue
                            
                            # Process this item as an event (recursive logic extracted below)
                            # Filter by namespace if needed
                            if target_namespaces:
                                source_ns = None
                                if "k8s" in item and isinstance(item["k8s"], dict):
                                    source_ns = item["k8s"].get("namespace", "")
                                else:
                                    source_ns = item.get("k8s.namespace", item.get("namespace", ""))
                                
                                source_in_target = source_ns in target_namespaces if source_ns else False
                                
                                dst_in_target = False
                                if not source_in_target:
                                    dst_ip = self._extract_dst_ip(item)
                                    if dst_ip and pod_ip_cache:
                                        dst_ns = pod_ip_cache.get_namespace(dst_ip)
                                        dst_in_target = dst_ns in target_namespaces if dst_ns else False
                                
                                if not source_in_target and not dst_in_target:
                                    continue  # Skip this item
                            
                            # Conservative exclusion filter (both src & dst must be excluded)
                            if self._should_exclude_event(item, config, pod_ip_cache):
                                continue

                            event_type = self._determine_event_type(item, gadget_name)
                            normalized_data = self._normalize_event(item, gadget_name)
                            
                            # Log first few top_tcp events from list
                            if gadget_name == "top_tcp":
                                if not hasattr(self, '_top_tcp_list_event_count'):
                                    self._top_tcp_list_event_count = 0
                                self._top_tcp_list_event_count += 1
                                if self._top_tcp_list_event_count <= 5:
                                    logger.info("top_tcp event (from list)",
                                               event_num=self._top_tcp_list_event_count,
                                               bytes_sent=normalized_data.get("bytes_sent"),
                                               bytes_received=normalized_data.get("bytes_received"),
                                               src_ip=normalized_data.get("src_ip", "")[:30],
                                               dst_ip=normalized_data.get("dst_ip", "")[:30])
                            
                            event = Event(
                                timestamp=item.get("timestamp", datetime.utcnow().isoformat()),
                                trace_id=trace_id,
                                analysis_id=config.analysis_id,
                                cluster_id=config.cluster_id,
                                event_type=event_type,
                                data=normalized_data
                            )
                            
                            self.active_traces[trace_id]["events_collected"] += 1
                            yield event
                        
                        continue  # Move to next line after processing list
                    
                    # ============================================================
                    # NAMESPACE FILTERING with INCOMING TRAFFIC SUPPORT
                    # ============================================================
                    # Include event if EITHER:
                    # 1. Source pod (k8s.namespace) is in target namespaces (OUTGOING traffic)
                    # 2. Destination pod is in target namespaces (INCOMING traffic)
                    #
                    # This fixes the issue where namespace-scoped analyses miss
                    # connections FROM other namespaces TO the target namespace.
                    #
                    # Example:
                    # - Target namespace: prod-auth-service
                    # - Event: prod-api-gateway → prod-auth-service
                    # - k8s.namespace = prod-api-gateway (source)
                    # - OLD: DROPPED (source not in target)
                    # - NEW: INCLUDED (destination is in target)
                    # ============================================================
                    if target_namespaces:
                        # 1. Check source namespace (pod generating the event)
                        source_ns = None
                        if "k8s" in event_data and isinstance(event_data["k8s"], dict):
                            source_ns = event_data["k8s"].get("namespace", "")
                        else:
                            source_ns = event_data.get("k8s.namespace", event_data.get("namespace", ""))
                        
                        source_in_target = source_ns in target_namespaces if source_ns else False
                        
                        # 2. Check destination namespace (resolve dst_ip to namespace)
                        dst_in_target = False
                        dst_ip = None
                        dst_ns = None
                        if not source_in_target:
                            # Source not in target - check destination
                            dst_ip = self._extract_dst_ip(event_data)
                            if dst_ip and pod_ip_cache:
                                dst_ns = pod_ip_cache.get_namespace(dst_ip)
                                dst_in_target = dst_ns in target_namespaces if dst_ns else False
                        
                        # DEBUG: Log filtering decisions periodically
                        if not hasattr(self, '_filter_stats'):
                            self._filter_stats = {'total': 0, 'accepted_source': 0, 'accepted_dst': 0, 'dropped': 0, 'no_cache': 0, 'no_dst_ns': 0}
                        self._filter_stats['total'] += 1
                        
                        # Include event if EITHER source OR destination is in target namespace
                        if source_in_target:
                            self._filter_stats['accepted_source'] += 1
                        elif dst_in_target:
                            self._filter_stats['accepted_dst'] += 1
                            # Log first few incoming traffic events for debugging
                            if self._filter_stats['accepted_dst'] <= 5:
                                logger.info("🔵 INCOMING traffic captured",
                                           source_ns=source_ns, dst_ip=dst_ip, dst_ns=dst_ns,
                                           target_namespaces=list(target_namespaces))
                        else:
                            self._filter_stats['dropped'] += 1
                            if not pod_ip_cache:
                                self._filter_stats['no_cache'] += 1
                            elif dst_ip and not dst_ns:
                                self._filter_stats['no_dst_ns'] += 1
                            # Log first few dropped events for debugging  
                            if self._filter_stats['dropped'] <= 5:
                                logger.debug("Event filtered out",
                                            source_ns=source_ns, dst_ip=dst_ip, dst_ns=dst_ns,
                                            has_cache=pod_ip_cache is not None)
                            continue
                        
                        # Log stats every 1000 events
                        if self._filter_stats['total'] % 1000 == 0:
                            logger.info("📊 Namespace filter stats",
                                       total=self._filter_stats['total'],
                                       accepted_source=self._filter_stats['accepted_source'],
                                       accepted_dst=self._filter_stats['accepted_dst'],
                                       dropped=self._filter_stats['dropped'],
                                       no_cache=self._filter_stats['no_cache'],
                                       no_dst_ns=self._filter_stats['no_dst_ns'],
                                       cache_size=len(pod_ip_cache._cache) if pod_ip_cache else 0)
                    
                    # Conservative exclusion filter (both src & dst must be excluded)
                    if self._should_exclude_event(event_data, config, pod_ip_cache):
                        if not hasattr(self, '_exclusion_stats'):
                            self._exclusion_stats = {'dropped': 0}
                        self._exclusion_stats['dropped'] += 1
                        if self._exclusion_stats['dropped'] <= 5:
                            logger.debug("Event excluded by system pod filter",
                                        trace_id=trace_id,
                                        exclude_ns=config.exclude_namespaces,
                                        exclude_pods=config.exclude_pod_patterns)
                        if self._exclusion_stats['dropped'] % 1000 == 0:
                            logger.info("Exclusion filter stats",
                                       total_dropped=self._exclusion_stats['dropped'])
                        continue

                    # Extract event type from gadget output
                    gadget_name = trace_info["gadget_name"]
                    event_type = self._determine_event_type(event_data, gadget_name)
                    
                    # Normalize event data (pass gadget_name for gadget-specific handling)
                    normalized_data = self._normalize_event(event_data, gadget_name)
                    
                    # DEBUG: Log first few top_tcp events to verify bytes data
                    if gadget_name == "top_tcp":
                        if not hasattr(self, '_top_tcp_event_count'):
                            self._top_tcp_event_count = 0
                        self._top_tcp_event_count += 1
                        if self._top_tcp_event_count <= 5:
                            logger.info("📊 top_tcp event received",
                                       event_num=self._top_tcp_event_count,
                                       raw_sent=event_data.get("sent"),
                                       raw_received=event_data.get("received"),
                                       raw_sent_raw=event_data.get("sent_raw"),
                                       raw_received_raw=event_data.get("received_raw"),
                                       normalized_bytes_sent=normalized_data.get("bytes_sent"),
                                       normalized_bytes_received=normalized_data.get("bytes_received"),
                                       src=str(event_data.get("src", ""))[:50],
                                       dst=str(event_data.get("dst", ""))[:50])
                        elif self._top_tcp_event_count == 100:
                            logger.info("📊 top_tcp: 100 events processed so far")
                    
                    # DEBUG: Log first few trace_tcpretrans events to verify error data
                    if gadget_name == "trace_tcpretrans":
                        if not hasattr(self, '_tcpretrans_event_count'):
                            self._tcpretrans_event_count = 0
                        self._tcpretrans_event_count += 1
                        if self._tcpretrans_event_count <= 5:
                            logger.info("⚠️ trace_tcpretrans event received",
                                       event_num=self._tcpretrans_event_count,
                                       raw_type=event_data.get("type"),
                                       raw_state=event_data.get("state"),
                                       raw_reason=event_data.get("reason"),
                                       normalized_error_count=normalized_data.get("error_count"),
                                       normalized_retransmit_count=normalized_data.get("retransmit_count"),
                                       normalized_error_type=normalized_data.get("error_type"))
                    
                    event = Event(
                        timestamp=event_data.get("timestamp", datetime.utcnow().isoformat()),
                        trace_id=trace_id,
                        analysis_id=config.analysis_id,
                        cluster_id=config.cluster_id,
                        event_type=event_type,
                        data=normalized_data
                    )
                    
                    self.active_traces[trace_id]["events_collected"] += 1
                    yield event
                    
                except json.JSONDecodeError:
                    # Skip non-JSON lines (headers, progress, etc.)
                    logger.debug("Skipping non-JSON line", line=line[:100])
                    continue
            
            # Process exited
            stderr = process.stderr.read() if process.stderr else ""
            gadget_name = trace_info.get("gadget_name", "unknown")
            events_collected = trace_info.get("events_collected", 0)
            
            if process.returncode != 0:
                logger.warning("kubectl gadget process exited with error",
                              trace_id=trace_id,
                              gadget=gadget_name,
                              returncode=process.returncode,
                              events_collected=events_collected,
                              stderr=stderr[:500])
            elif events_collected == 0:
                # Gadget exited successfully but collected no events
                logger.warning("⚠️ Gadget collected ZERO events",
                              trace_id=trace_id,
                              gadget=gadget_name,
                              returncode=process.returncode,
                              stderr=stderr[:500] if stderr else "no stderr")
                
        except asyncio.CancelledError:
            logger.info("Event stream cancelled", trace_id=trace_id)
            raise
        except Exception as e:
            logger.error("Event stream error", trace_id=trace_id, error=str(e))
            raise
    
    def _matches_exclusion(self, namespace: Optional[str], pod: Optional[str],
                            exclude_namespaces: List[str], exclude_pod_patterns: List[str]) -> bool:
        """
        Check if a namespace/pod matches any exclusion pattern.
        Returns True if the endpoint should be considered "excluded".
        A match on EITHER namespace OR pod pattern is sufficient.
        """
        if namespace and exclude_namespaces:
            for pattern in exclude_namespaces:
                if fnmatch.fnmatch(namespace, pattern):
                    return True
        if pod and exclude_pod_patterns:
            for pattern in exclude_pod_patterns:
                if fnmatch.fnmatch(pod, pattern):
                    return True
        return False

    def _should_exclude_event(self, event_data: dict, config: TraceConfig,
                               pod_ip_cache: Optional["PodIPCache"] = None) -> bool:
        """
        Conservative exclusion: drop event only if BOTH source AND destination
        match an exclusion pattern. This preserves all app-to-system and
        system-to-app relationships in the dependency graph.
        
        Returns True if the event should be dropped.
        """
        exc_ns = config.exclude_namespaces
        exc_pods = config.exclude_pod_patterns
        if not exc_ns and not exc_pods:
            return False

        # --- Source info (always in k8s context) ---
        if "k8s" in event_data and isinstance(event_data["k8s"], dict):
            src_ns = event_data["k8s"].get("namespace", "")
            src_pod = event_data["k8s"].get("podName", event_data["k8s"].get("name", ""))
        else:
            src_ns = event_data.get("k8s.namespace", event_data.get("namespace", ""))
            src_pod = event_data.get("k8s.podName", event_data.get("pod", ""))

        src_excluded = self._matches_exclusion(src_ns, src_pod, exc_ns or [], exc_pods or [])
        if not src_excluded:
            return False  # source is NOT excluded → keep event regardless of dst

        # --- Destination info (resolve from IP via pod_ip_cache) ---
        dst_ip = self._extract_dst_ip(event_data)
        dst_ns = None
        dst_pod = None
        if dst_ip and pod_ip_cache:
            dst_info = pod_ip_cache.lookup(dst_ip)
            if dst_info:
                dst_ns = dst_info.namespace
                dst_pod = dst_info.name

        dst_excluded = self._matches_exclusion(dst_ns, dst_pod, exc_ns or [], exc_pods or [])
        return dst_excluded  # drop only if BOTH are excluded

    def _extract_dst_ip(self, event_data: dict) -> Optional[str]:
        """
        Extract destination IP from event data.
        
        Handles multiple gadget formats:
        - trace_tcp: dst (string or object with addr/ip)
        - top_tcp: dst.addr
        - trace_network: daddr
        
        Args:
            event_data: Raw event from gadget
            
        Returns:
            Destination IP address or None
        """
        # Try dst field first (trace_tcp, top_tcp)
        dst_val = event_data.get("dst", event_data.get("daddr", ""))
        
        if dst_val:
            if isinstance(dst_val, dict):
                # Nested object: {addr: "10.128.x.x", port: 8080}
                return dst_val.get("addr", dst_val.get("ip", ""))
            elif isinstance(dst_val, str):
                return dst_val
        
        # Fallback: addr field (some trace_tcp formats)
        addr = event_data.get("addr", "")
        if addr:
            return addr
        
        return None
    
    def _determine_event_type(self, event_data: dict, gadget_name: str) -> str:
        """Determine event type from gadget name"""
        # Map gadget name to event type
        # NOTE: trace_tcp produces connect/accept/close events which are all
        # treated as network_flow. Inspektor Gadget doesn't produce TCP state
        # transition events (oldstate/newstate), so tcp_lifecycle is not used.
        gadget_to_event = {
            "trace_network": "network_flow",
            "trace_tcp": "network_flow",  # TCP connect/accept/close → network_flow
            "top_tcp": "network_flow",    # TCP throughput with bytes → network_flow
            "trace_tcpretrans": "network_flow",  # TCP retransmit/errors → network_flow
            "trace_dns": "dns_query",
            "trace_exec": "process_event",
            "trace_open": "file_event",
            "trace_capabilities": "security_event",
            "trace_oomkill": "oom_event",
            "trace_bind": "bind_event",
            "trace_sni": "sni_event",
            "trace_mount": "mount_event",
        }
        
        return gadget_to_event.get(gadget_name, f"{gadget_name}_event")
    
    def _normalize_event(self, event_data: dict, gadget_name: str = "") -> dict:
        """
        Normalize kubectl gadget JSON output to standard format.
        
        Args:
            event_data: Raw event data from gadget
            gadget_name: Name of the gadget (e.g., "trace_tcpretrans", "top_tcp")
                        Used for gadget-specific handling like retransmit detection.
        
        IMPORTANT: All values must be primitives (str, int, float, bool, list of primitives).
        Nested dicts are NOT allowed as they cause issues with Neo4j and ClickHouse.
        """
        normalized = {}
        
        # Helper to extract primitive value from potentially nested structure
        def get_primitive(obj, default=""):
            """Extract primitive value, handling nested objects"""
            if obj is None:
                return default
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                # Try to extract addr/ip/name from nested object
                if 'addr' in obj:
                    return str(obj['addr'])
                if 'ip' in obj:
                    return str(obj['ip'])
                if 'name' in obj:
                    return str(obj['name'])
                # Convert dict to JSON string if can't extract
                import json
                return json.dumps(obj, default=str)
            if isinstance(obj, list):
                # Keep list if all items are primitives
                if all(isinstance(i, (str, int, float, bool, type(None))) for i in obj):
                    return obj
                import json
                return json.dumps(obj, default=str)
            return str(obj)
        
        # K8s context - v0.46.0+ format
        # Handle nested k8s fields
        if "k8s" in event_data and isinstance(event_data["k8s"], dict):
            k8s = event_data["k8s"]
            normalized["namespace"] = get_primitive(k8s.get("namespace", ""))
            normalized["pod"] = get_primitive(k8s.get("podName", k8s.get("name", k8s.get("pod", ""))))
            normalized["container"] = get_primitive(k8s.get("containerName", k8s.get("container", "")))
            normalized["node"] = get_primitive(k8s.get("node", ""))
            # Extract labels as JSON string if present
            if "labels" in k8s:
                normalized["k8s_labels"] = get_primitive(k8s.get("labels", ""))
            
            # IMPORTANT: For network flows, the k8s context is the SOURCE pod
            # Copy to src_* fields so timeseries-writer can find them
            normalized["src_namespace"] = normalized["namespace"]
            normalized["src_pod"] = normalized["pod"]
            normalized["src_container"] = normalized["container"]
        else:
            # Handle flat fields
            normalized["namespace"] = get_primitive(event_data.get("k8s.namespace", event_data.get("namespace", "")))
            normalized["pod"] = get_primitive(event_data.get("k8s.podName", event_data.get("pod", "")))
            normalized["container"] = get_primitive(event_data.get("k8s.containerName", event_data.get("container", "")))
            normalized["node"] = get_primitive(event_data.get("k8s.node", event_data.get("node", "")))
            
            # Also copy to src_* fields for network flows
            normalized["src_namespace"] = normalized["namespace"]
            normalized["src_pod"] = normalized["pod"]
            normalized["src_container"] = normalized["container"]
        
        # Process fields - Inspektor Gadget v0.35.0+ uses nested "proc" object
        # Check both top-level and nested proc object for backwards compatibility
        proc_data = event_data.get("proc", {}) if isinstance(event_data.get("proc"), dict) else {}
        
        normalized["pid"] = get_primitive(
            proc_data.get("pid") or event_data.get("pid", 0), 0
        )
        normalized["ppid"] = get_primitive(
            proc_data.get("ppid") or event_data.get("ppid", 0), 0
        )  # Parent PID for process tree
        normalized["comm"] = get_primitive(
            proc_data.get("comm") or event_data.get("comm", "")
        )
        normalized["uid"] = get_primitive(
            proc_data.get("uid") or event_data.get("uid", 0), 0
        )
        normalized["gid"] = get_primitive(
            proc_data.get("gid") or event_data.get("gid", 0), 0
        )
        
        # Process execution fields (trace_exec specific)
        # Also check proc object for these fields
        normalized["exe"] = get_primitive(
            proc_data.get("exepath") or proc_data.get("exe") or 
            event_data.get("exepath") or event_data.get("exe", "")
        )
        normalized["args"] = (
            proc_data.get("args") if isinstance(proc_data.get("args"), list) else
            event_data.get("args", []) if isinstance(event_data.get("args"), list) else []
        )
        normalized["cwd"] = get_primitive(
            proc_data.get("cwd") or event_data.get("cwd", "")
        )
        
        # Network fields - handle trace_tcp, trace_network, and top_tcp formats
        # trace_tcp uses: src (object or string), dst, sport, dport, proto
        # top_tcp uses: src.addr, src.port, dst.addr, dst.port, sent_raw, received_raw
        src_val = event_data.get("src", event_data.get("saddr", ""))
        dst_val = event_data.get("dst", event_data.get("daddr", ""))
        
        if src_val or dst_val or "addr" in event_data:
            # Extract IP from potentially nested object
            if isinstance(src_val, dict):
                normalized["src_ip"] = get_primitive(src_val.get("addr", src_val.get("ip", "")))
                # top_tcp: port is inside src object
                if "port" in src_val:
                    normalized["src_port"] = get_primitive(src_val.get("port", 0), 0)
            else:
                normalized["src_ip"] = get_primitive(src_val)
            
            if isinstance(dst_val, dict):
                normalized["dst_ip"] = get_primitive(dst_val.get("addr", dst_val.get("ip", "")))
                # top_tcp: port is inside dst object
                if "port" in dst_val:
                    normalized["dst_port"] = get_primitive(dst_val.get("port", 0), 0)
            else:
                normalized["dst_ip"] = get_primitive(dst_val)
            
            # For trace_tcp, addr field contains the remote IP
            if "addr" in event_data and not normalized.get("dst_ip"):
                normalized["dst_ip"] = get_primitive(event_data.get("addr", ""))
            
            # Fallback for trace_tcp format (sport/dport at top level)
            if "src_port" not in normalized:
                normalized["src_port"] = get_primitive(event_data.get("sport", event_data.get("src_port", 0)), 0)
            if "dst_port" not in normalized:
                normalized["dst_port"] = get_primitive(event_data.get("dport", event_data.get("port", event_data.get("dst_port", 0))), 0)
            normalized["protocol"] = get_primitive(event_data.get("proto", event_data.get("protocol", "TCP")))
            
            # Byte transfer data (from top_tcp gadget)
            # top_tcp provides: sent, received (or sent_raw, received_raw in some versions)
            if "sent_raw" in event_data or "received_raw" in event_data:
                normalized["bytes_sent"] = get_primitive(event_data.get("sent_raw", 0), 0)
                normalized["bytes_received"] = get_primitive(event_data.get("received_raw", 0), 0)
            # Also check for sent/received without _raw suffix (current gadget versions)
            elif "sent" in event_data or "received" in event_data:
                normalized["bytes_sent"] = get_primitive(event_data.get("sent", 0), 0)
                normalized["bytes_received"] = get_primitive(event_data.get("received", 0), 0)
            
            # TCP Retransmit data (from trace_tcpretrans gadget)
            # trace_tcpretrans output fields: state, type, reason, tcpflags
            if "state" in event_data and ("retrans" in str(event_data.get("type", "")).lower() or 
                                          gadget_name == "trace_tcpretrans"):
                normalized["retransmit_count"] = 1  # Each event is one retransmit
                normalized["error_count"] = 1
                # Error type from state or type field
                tcp_state = get_primitive(event_data.get("state", ""))
                tcp_type = get_primitive(event_data.get("type", ""))
                tcp_reason = get_primitive(event_data.get("reason", ""))
                
                # Known valid error type keywords (whitelist approach)
                VALID_KEYWORDS = {
                    'LOSS', 'RETRANS', 'TIMEOUT', 'SPURIOUS', 'FAST', 'RTO', 'TLP',
                    'SYNACK', 'SYN', 'FIN', 'PROBE', 'KEEPALIVE',
                    'ESTABLISHED', 'SYN_SENT', 'SYN_RECV', 'FIN_WAIT1', 'FIN_WAIT2',
                    'TIME_WAIT', 'CLOSE', 'CLOSE_WAIT', 'LAST_ACK', 'LISTEN', 'CLOSING',
                }
                
                # Helper to check if value is a valid error type keyword
                def is_valid_error_type(val):
                    if not val:
                        return False
                    val_str = str(val).upper().strip()
                    # Check if it's a known valid keyword
                    return val_str in VALID_KEYWORDS
                
                if is_valid_error_type(tcp_reason):
                    normalized["error_type"] = f"RETRANSMIT_{tcp_reason}".upper()
                elif is_valid_error_type(tcp_type) and tcp_type.lower() not in ('retrans', 'retransmit'):
                    normalized["error_type"] = f"RETRANSMIT_{tcp_type}".upper()
                elif is_valid_error_type(tcp_state):
                    normalized["error_type"] = f"RETRANSMIT_{tcp_state}".upper()
                else:
                    # Default to simple RETRANSMIT if no valid qualifier
                    normalized["error_type"] = "RETRANSMIT"
                
                # TCP flags if available
                if "tcpflags" in event_data:
                    normalized["tcp_flags"] = get_primitive(event_data.get("tcpflags", ""))
            
            # CRITICAL: Handle accept vs connect events differently
            # For trace_tcp:
            #   - "connect": Pod initiates outgoing connection → k8s context = SOURCE
            #   - "accept": Pod receives incoming connection → k8s context = DESTINATION
            # The raw event always has src/dst from eBPF perspective, we need to 
            # flip them for accept to represent the logical flow direction
            event_type = get_primitive(event_data.get("type", ""))
            if event_type == "accept":
                # For accept: the pod is the SERVER (destination), not the source
                # Swap src <-> dst to represent logical flow: external → pod
                orig_src_ip = normalized.get("src_ip", "")
                orig_src_port = normalized.get("src_port", 0)
                orig_dst_ip = normalized.get("dst_ip", "")
                orig_dst_port = normalized.get("dst_port", 0)
                
                # Now: src = external client, dst = our pod
                normalized["src_ip"] = orig_dst_ip or orig_src_ip  # Remote client IP
                normalized["src_port"] = orig_dst_port or orig_src_port
                normalized["dst_ip"] = orig_src_ip or orig_dst_ip  # Our pod IP  
                normalized["dst_port"] = orig_src_port or orig_dst_port
                
                # The k8s context is the DESTINATION for accept events
                normalized["dst_namespace"] = normalized.get("namespace", "")
                normalized["dst_pod"] = normalized.get("pod", "")
                normalized["dst_container"] = normalized.get("container", "")
                normalized["dst_node"] = normalized.get("node", "")
                
                # Source is external (will be enriched by PodDiscovery if in-cluster)
                normalized["src_namespace"] = ""
                normalized["src_pod"] = ""
                normalized["src_container"] = ""
                
                # Set direction for clarity
                normalized["direction"] = "inbound"
            else:
                # connect/close - k8s context is SOURCE (already set above)
                normalized["direction"] = "outbound"
        
        # DNS fields - trace_dns format
        if "qr" in event_data or "name" in event_data or "qtype" in event_data:
            normalized["query_name"] = get_primitive(event_data.get("name", event_data.get("qname", "")))
            normalized["query_type"] = get_primitive(event_data.get("qtype", "A"))
            normalized["response_code"] = get_primitive(event_data.get("rcode", "NOERROR"))
            # DNS answers might be a list
            answers = event_data.get("answers", event_data.get("anaddr", []))
            normalized["answers"] = get_primitive(answers, [])
        
        # TCP state fields
        if "oldstate" in event_data or "newstate" in event_data:
            normalized["old_state"] = get_primitive(event_data.get("oldstate", ""))
            normalized["new_state"] = get_primitive(event_data.get("newstate", ""))
        
        # File fields - trace_open, trace_read, trace_write
        if "fname" in event_data or "path" in event_data or "filename" in event_data:
            normalized["path"] = get_primitive(event_data.get("fname", event_data.get("path", event_data.get("filename", ""))))
            normalized["flags"] = get_primitive(event_data.get("flags", 0), 0)
            normalized["mode"] = get_primitive(event_data.get("mode", 0), 0)
        
        # Security/Capability fields - trace_capabilities
        if "cap" in event_data or "capability" in event_data or "capName" in event_data:
            normalized["capability"] = get_primitive(event_data.get("capName", event_data.get("cap", event_data.get("capability", ""))))
            normalized["syscall"] = get_primitive(event_data.get("syscall", ""))
            normalized["verdict"] = get_primitive(event_data.get("verdict", event_data.get("audit", "allowed")))
        
        # OOM fields - trace_oomkill
        if "fpid" in event_data or "fcomm" in event_data:
            normalized["killed_pid"] = get_primitive(event_data.get("fpid", event_data.get("tpid", 0)), 0)
            normalized["killed_comm"] = get_primitive(event_data.get("fcomm", event_data.get("tcomm", "")))
            normalized["memory_pages_total"] = get_primitive(event_data.get("pages", 0), 0)
        
        # Bind fields - trace_bind
        if "addr" in event_data and "port" in event_data:
            # addr for bind is the bound address
            normalized["bind_addr"] = get_primitive(event_data.get("addr", "0.0.0.0"))
            normalized["bind_port"] = get_primitive(event_data.get("port", 0), 0)
            normalized["interface"] = get_primitive(event_data.get("if", event_data.get("interface", "")))
        
        # SNI fields - trace_sni
        if "name" in event_data and ("tls" in str(event_data) or "sni" in str(event_data).lower()):
            normalized["sni_name"] = get_primitive(event_data.get("name", ""))
        
        # Mount fields - trace_mount
        if "src" in event_data and "dest" in event_data and "type" in event_data:
            normalized["mount_source"] = get_primitive(event_data.get("src", ""))
            normalized["mount_target"] = get_primitive(event_data.get("dest", event_data.get("target", "")))
            normalized["fs_type"] = get_primitive(event_data.get("type", event_data.get("fs", "")))
            normalized["mount_flags"] = get_primitive(event_data.get("flags", ""))
            normalized["mount_opts"] = get_primitive(event_data.get("opts", event_data.get("data", "")))
        
        # Event type/subtype (e.g., trace_tcp produces "accept", "connect", "close")
        if "type" in event_data:
            normalized["event_subtype"] = get_primitive(event_data.get("type", ""))
        
        # Timestamp from gadget
        if "timestamp" in event_data:
            normalized["gadget_timestamp"] = get_primitive(event_data.get("timestamp", ""))
        
        # Error fields
        if "error" in event_data or "ret" in event_data:
            normalized["error_code"] = get_primitive(event_data.get("error", event_data.get("ret", 0)), 0)
        
        # Add remaining PRIMITIVE fields only (skip nested objects)
        skip_fields = {"k8s", "src", "dst", "runtime"}  # Known nested object fields
        for key, value in event_data.items():
            if key not in normalized and key not in skip_fields and not key.startswith("k8s."):
                # Only add if primitive
                if isinstance(value, (str, int, float, bool)):
                    normalized[key] = value
                elif isinstance(value, list) and all(isinstance(i, (str, int, float, bool, type(None))) for i in value):
                    normalized[key] = value
                # Skip nested objects - don't convert to JSON here
        
        return normalized
    
    async def stop_trace(self, trace_id: str) -> bool:
        """Stop kubectl gadget process"""
        try:
            if trace_id not in self.active_processes:
                logger.warning("Trace not found for stopping", trace_id=trace_id)
                return False
            
            process = self.active_processes[trace_id]
            
            # Send SIGTERM to process group
            try:
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass  # Process already dead
            
            # Wait for process to terminate
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            
            # Cleanup
            trace_info = self.active_traces.pop(trace_id, {})
            self.active_processes.pop(trace_id, None)
            
            logger.info("kubectl gadget trace stopped",
                       trace_id=trace_id,
                       events_collected=trace_info.get("events_collected", 0))
            
            return True
            
        except Exception as e:
            logger.error("Failed to stop trace", trace_id=trace_id, error=str(e))
            self.active_processes.pop(trace_id, None)
            self.active_traces.pop(trace_id, None)
            return False
    
    async def health_check(self) -> HealthStatus:
        """Check kubectl-gadget health"""
        start_time = datetime.utcnow()
        
        try:
            # Get version (use _build_gadget_cmd for correct flag placement)
            cmd = self._build_gadget_cmd(["version", "-o", "json"])
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            )
            
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if result.returncode == 0:
                try:
                    version_info = json.loads(result.stdout)
                    version = version_info.get("clientVersion", {}).get("gitVersion", "unknown")
                except:
                    version = result.stdout.strip()[:50]
                
                return HealthStatus(
                    healthy=True,
                    version=version,
                    endpoint="kubectl-gadget",
                    protocol="cli",
                    latency_ms=latency_ms,
                    details={
                        "kubectl_available": True,
                        "gadget_plugin": True,
                        "active_traces": len(self.active_traces),
                        "kubeconfig": self.kubeconfig or "default"
                    }
                )
            else:
                return HealthStatus(
                    healthy=False,
                    endpoint="kubectl-gadget",
                    protocol="cli",
                    latency_ms=latency_ms,
                    error=result.stderr[:200]
                )
                
        except Exception as e:
            return HealthStatus(
                healthy=False,
                endpoint="kubectl-gadget",
                protocol="cli",
                error=str(e)
            )
    
    async def get_capabilities(self) -> List[str]:
        """Get available gadgets"""
        try:
            cmd = self._build_gadget_cmd(["list-gadgets"])
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            )
            
            if result.returncode == 0:
                # Parse gadget list from output
                gadgets = []
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("NAME") and not line.startswith("-"):
                        parts = line.split()
                        if parts:
                            gadgets.append(parts[0])
                return gadgets
            
            # Fallback: return known gadgets
            return list(self.TRACE_TYPE_TO_GADGET.values())
            
        except Exception as e:
            logger.error("Failed to get capabilities", error=str(e))
            return list(self.TRACE_TYPE_TO_GADGET.values())
    
    def _parse_gadget_error(self, stderr: str, gadget_name: str) -> str:
        """
        Parse gadget stderr output and return user-friendly error message.
        
        Handles common errors:
        - Image pull failures (ghcr.io timeout)
        - Permission denied
        - Resource not found
        - Network errors
        """
        if not stderr:
            return f"Gadget '{gadget_name}' failed to start (unknown error)"
        
        stderr_lower = stderr.lower()
        
        # Image pull failures (most common for air-gapped environments)
        if "pulling image" in stderr_lower or "failed to perform" in stderr_lower:
            if "timeout" in stderr_lower or "i/o timeout" in stderr_lower:
                return (
                    f"Gadget '{gadget_name}' failed: Cannot pull image from ghcr.io (network timeout). "
                    "The cluster may not have internet access to GitHub Container Registry. "
                    "Contact your administrator to configure internal registry or allow ghcr.io access."
                )
            elif "unauthorized" in stderr_lower or "403" in stderr_lower:
                return (
                    f"Gadget '{gadget_name}' failed: Unauthorized to pull image. "
                    "Check registry credentials or use internal registry."
                )
            else:
                return f"Gadget '{gadget_name}' failed: Image pull error - {stderr[:200]}"
        
        # Permission errors
        if "permission denied" in stderr_lower or "forbidden" in stderr_lower:
            return (
                f"Gadget '{gadget_name}' failed: Permission denied. "
                "The service account may not have required RBAC permissions."
            )
        
        # eBPF specific errors
        if "ebpf" in stderr_lower or "bpf" in stderr_lower:
            return (
                f"Gadget '{gadget_name}' failed: eBPF error. "
                "The cluster nodes may not support required eBPF features."
            )
        
        # Generic error with truncated stderr
        return f"Gadget '{gadget_name}' failed: {stderr[:300]}"
    
    def get_trace_errors(self) -> Dict[str, str]:
        """
        Get startup errors for all active traces.
        
        Returns:
            Dict mapping trace_id to error message (only for failed traces)
        """
        errors = {}
        for trace_id, trace_info in self.active_traces.items():
            if trace_info.get("startup_error"):
                gadget_name = trace_info.get("gadget_name", "unknown")
                errors[gadget_name] = trace_info["startup_error"]
        return errors
    
    async def check_startup_errors(self, wait_seconds: float = 2.0) -> None:
        """
        Wait briefly and check all active traces for startup errors.
        
        This should be called ONCE after all traces are started, not per-trace.
        This prevents blocking for N*wait_seconds when starting N gadgets.
        
        Args:
            wait_seconds: Time to wait for gadgets to fail (default 2s)
        """
        await asyncio.sleep(wait_seconds)
        
        for trace_id, trace_info in self.active_traces.items():
            if trace_info.get("startup_error"):
                continue  # Already has error
            
            process = trace_info.get("process")
            if process and process.poll() is not None:
                # Process exited
                stderr = process.stderr.read() if process.stderr else ""
                if process.returncode != 0:
                    gadget_name = trace_info.get("gadget_name", "unknown")
                    error_msg = self._parse_gadget_error(stderr, gadget_name)
                    trace_info["startup_error"] = error_msg
                    logger.warning("Gadget startup failed (detected in check)",
                                  trace_id=trace_id,
                                  gadget=gadget_name,
                                  returncode=process.returncode,
                                  error=error_msg)
    
    def get_all_gadget_errors(self) -> List[Dict[str, str]]:
        """
        Get all gadget errors in a list format for API response.
        
        NOTE: Call check_startup_errors() first to populate errors.
        
        Returns:
            List of {gadget: name, error: message} dicts
        """
        errors = []
        for trace_id, trace_info in self.active_traces.items():
            if trace_info.get("startup_error"):
                errors.append({
                    "gadget": trace_info.get("gadget_name", "unknown"),
                    "error": trace_info["startup_error"],
                    "trace_id": trace_id
                })
        return errors

