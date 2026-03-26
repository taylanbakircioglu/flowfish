"""
Trace Manager - Manages eBPF trace collection lifecycle

Supports Inspektor Gadget v0.46.0+ via kubectl-gadget CLI
Supports remote clusters via dynamic kubeconfig generation
"""

import asyncio
import uuid
import tempfile
import os
import yaml
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

from app.config import settings
from app.protocols.client_factory import GadgetClientFactory
from app.protocols.abstract_gadget_client import AbstractGadgetClient, TraceConfig
from app.protocols.kubectl_gadget_client import KubectlGadgetClient
from app.rabbitmq_client import RabbitMQPublisher
from app.pod_discovery import PodDiscovery, PodIPCache

logger = structlog.get_logger()


def decrypt_if_needed(encrypted_value: str) -> str:
    """
    Decrypt value if encrypted (from database).
    Falls back to returning original value if decryption fails.
    """
    if not encrypted_value:
        return ""
    
    try:
        # Try to import Fernet from backend utils
        from cryptography.fernet import Fernet
        
        key = os.environ.get("FLOWFISH_ENCRYPTION_KEY", "")
        if not key:
            # No encryption key - value might be plain text
            return encrypted_value
        
        f = Fernet(key.encode() if isinstance(key, str) else key)
        decrypted = f.decrypt(encrypted_value.encode() if isinstance(encrypted_value, str) else encrypted_value)
        return decrypted.decode()
    except Exception as e:
        logger.debug("Decryption failed, using value as-is", error=str(e))
        return encrypted_value


def _sanitize_pem_certificate(cert: str) -> Optional[str]:
    """
    Sanitize PEM certificate(s) from UI input.
    
    Handles common issues from copy-paste:
    - Extra whitespace at start/end
    - Missing or malformed PEM headers
    - Windows line endings
    - Base64 content without PEM wrapper
    - Multiple certificates (CA chain bundle)
    - Mixed whitespace between certificates in a chain
    
    Returns:
        Properly formatted PEM certificate(s), or None if invalid
    """
    import base64
    import re
    
    if not cert:
        return None
    
    # Strip whitespace and normalize line endings
    cert = cert.strip().replace('\r\n', '\n').replace('\r', '\n')
    
    # Check if it looks like base64 without PEM headers
    if not cert.startswith('-----BEGIN'):
        # Remove any whitespace/newlines for base64 detection
        clean_b64 = re.sub(r'\s+', '', cert)
        
        try:
            decoded = base64.b64decode(clean_b64)
            # Check if decoded content looks like a DER certificate
            if decoded.startswith(b'\x30'):  # ASN.1 SEQUENCE
                # Wrap in PEM format
                formatted_b64 = '\n'.join([clean_b64[i:i+64] for i in range(0, len(clean_b64), 64)])
                cert = f"-----BEGIN CERTIFICATE-----\n{formatted_b64}\n-----END CERTIFICATE-----\n"
                logger.info("Converted base64 cert to PEM format")
            else:
                # It's plain PEM that was already base64 decoded
                cert = decoded.decode('utf-8').strip()
        except Exception:
            logger.warning("CA cert doesn't look like valid PEM or base64")
            return None
    
    # Handle multiple certificates (CA chain bundle)
    # Split by PEM boundaries and reconstruct properly
    cert_blocks = re.findall(
        r'-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----',
        cert
    )
    
    if not cert_blocks:
        logger.warning("CA cert missing PEM headers after sanitization")
        return None
    
    # Sanitize each certificate block
    sanitized_blocks = []
    for block in cert_blocks:
        # Extract just the base64 content
        lines = block.strip().split('\n')
        content_lines = [
            line.strip() 
            for line in lines 
            if line.strip() and not line.strip().startswith('-----')
        ]
        
        if content_lines:
            # Reconstruct with proper formatting
            formatted_block = "-----BEGIN CERTIFICATE-----\n"
            formatted_block += '\n'.join(content_lines)
            formatted_block += "\n-----END CERTIFICATE-----\n"
            sanitized_blocks.append(formatted_block)
    
    if not sanitized_blocks:
        logger.warning("No valid certificate blocks found")
        return None
    
    # Combine all certificates with proper spacing
    result = '\n'.join(sanitized_blocks)
    
    logger.info("Sanitized CA certificate(s)", cert_count=len(sanitized_blocks))
    
    return result


def create_remote_kubeconfig(
    api_server_url: str,
    token: str,
    ca_cert: Optional[str] = None,
    cluster_name: str = "remote-cluster",
    skip_tls_verify: bool = False
) -> str:
    """
    Create a temporary kubeconfig file for remote cluster access.
    
    Args:
        api_server_url: Kubernetes API server URL (e.g., https://api.cluster.example.com:6443)
        token: ServiceAccount token for authentication
        ca_cert: CA certificate (PEM format) for TLS verification
        cluster_name: Name to use for the cluster in kubeconfig
        skip_tls_verify: If True, skip TLS certificate verification
    
    Returns:
        Path to the temporary kubeconfig file
    """
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": cluster_name,
        "clusters": [{
            "name": cluster_name,
            "cluster": {
                "server": api_server_url
            }
        }],
        "contexts": [{
            "name": cluster_name,
            "context": {
                "cluster": cluster_name,
                "user": "flowfish-reader"
            }
        }],
        "users": [{
            "name": "flowfish-reader",
            "user": {
                "token": token
            }
        }]
    }
    
    # Add TLS configuration
    if skip_tls_verify:
        kubeconfig["clusters"][0]["cluster"]["insecure-skip-tls-verify"] = True
    elif ca_cert:
        # Sanitize CA cert (handle copy-paste issues from UI)
        sanitized_cert = _sanitize_pem_certificate(ca_cert)
        if sanitized_cert:
            # Write sanitized CA cert to temp file
            ca_file = tempfile.NamedTemporaryFile(
                mode='w', 
                delete=False, 
                suffix='.crt',
                prefix='flowfish-ca-'
            )
            ca_file.write(sanitized_cert)
            ca_file.close()
            kubeconfig["clusters"][0]["cluster"]["certificate-authority"] = ca_file.name
            logger.info("CA certificate written for TLS verification", path=ca_file.name)
        else:
            # CA cert invalid, fall back to skip TLS (with warning)
            logger.warning("CA cert invalid after sanitization, falling back to insecure-skip-tls-verify")
            kubeconfig["clusters"][0]["cluster"]["insecure-skip-tls-verify"] = True
    
    # Write kubeconfig to temp file
    kubeconfig_file = tempfile.NamedTemporaryFile(
        mode='w',
        delete=False,
        suffix='.kubeconfig',
        prefix='flowfish-remote-'
    )
    yaml.dump(kubeconfig, kubeconfig_file, default_flow_style=False)
    kubeconfig_file.close()
    
    logger.info("Created temporary kubeconfig for remote cluster",
               kubeconfig_path=kubeconfig_file.name,
               cluster_name=cluster_name,
               api_server=api_server_url,
               skip_tls=skip_tls_verify)
    
    return kubeconfig_file.name


class TraceSession:
    """Active trace collection session"""
    
    def __init__(
        self,
        session_id: str,
        task_id: str,
        analysis_id: int,
        cluster_id: int,
        client: AbstractGadgetClient,
        gadget_modules: list,
        scope: dict,
        gadget_namespace: str,  # REQUIRED: From UI via collection request
        pod_discovery: Optional[PodDiscovery] = None,
        temp_kubeconfig: Optional[str] = None  # Path to temp kubeconfig for cleanup
    ):
        self.session_id = session_id
        self.task_id = task_id
        self.analysis_id = analysis_id
        self.cluster_id = cluster_id
        self.client = client
        self.gadget_modules = gadget_modules
        self.scope = scope
        self.gadget_namespace = gadget_namespace  # From UI
        self.pod_discovery = pod_discovery  # For enriching events with pod names
        self.temp_kubeconfig = temp_kubeconfig  # For cleanup on session end
        
        self.status = "starting"
        self.started_at = datetime.utcnow()
        self.trace_ids = []
        self.collection_tasks = []
        self.events_collected = 0
        self.errors_count = 0
        self.last_event_at = None
        
        # Gadget startup errors (for user notification)
        self.gadget_errors: List[Dict[str, str]] = []  # [{gadget: name, error: message}]
    
    def cleanup_temp_files(self):
        """Clean up temporary files created for this session"""
        if self.temp_kubeconfig and os.path.exists(self.temp_kubeconfig):
            try:
                # Also try to clean up CA cert file if referenced in kubeconfig
                with open(self.temp_kubeconfig, 'r') as f:
                    kubeconfig = yaml.safe_load(f)
                    for cluster in kubeconfig.get('clusters', []):
                        ca_file = cluster.get('cluster', {}).get('certificate-authority')
                        if ca_file and os.path.exists(ca_file):
                            os.unlink(ca_file)
                            logger.debug("Cleaned up temp CA file", path=ca_file)
                
                os.unlink(self.temp_kubeconfig)
                logger.info("Cleaned up temp kubeconfig", path=self.temp_kubeconfig)
            except Exception as e:
                logger.warning("Failed to cleanup temp kubeconfig", 
                             path=self.temp_kubeconfig, error=str(e))
    
    def enrich_destination(self, dst_ip: str) -> tuple:
        """
        Enrich destination IP with pod name and namespace
        
        Returns (namespace, pod_name) - either can be None
        Safe fallback: returns (None, None) if discovery not available
        """
        if self.pod_discovery and self.pod_discovery.cache:
            return self.pod_discovery.cache.enrich_destination(dst_ip)
        return (None, None)


class TraceManager:
    """
    Manages eBPF trace collection sessions
    
    Responsibilities:
    - Create Gadget client based on protocol
    - Start/stop traces
    - Stream events from traces
    - Publish events to RabbitMQ
    - Track collection statistics
    """
    
    def __init__(self, rabbitmq_client: RabbitMQPublisher):
        self.rabbitmq = rabbitmq_client
        self.active_sessions: Dict[str, TraceSession] = {}
        logger.info("TraceManager initialized")
    
    async def start_collection(self, request) -> TraceSession:
        """
        Start eBPF trace collection
        
        Args:
            request: StartCollectionRequest from gRPC
        
        Returns:
            TraceSession
        """
        temp_kubeconfig = None
        
        try:
            session_id = str(uuid.uuid4())
            
            # Determine protocol - default to kubectl if not specified
            protocol = request.gadget_protocol or settings.gadget_protocol or 'kubectl'
            
            # Detect if this is a remote cluster connection
            # Remote clusters have cluster_api_url and cluster_token set
            is_remote = bool(request.cluster_api_url and request.cluster_token)
            
            logger.info("Starting collection session",
                       session_id=session_id,
                       task_id=request.task_id,
                       analysis_id=request.analysis_id,
                       cluster_id=request.cluster_id,
                       protocol=protocol,
                       is_remote_cluster=is_remote)
            
            # Determine kubeconfig for this session
            kubeconfig_path = settings.kubeconfig_path or None
            kubectl_context = settings.kubectl_context or None
            
            if is_remote:
                # Remote cluster - create dynamic kubeconfig
                logger.info("Remote cluster detected, creating dynamic kubeconfig",
                           api_server=request.cluster_api_url,
                           cluster_name=request.cluster_name)
                
                # Decrypt token and CA cert if encrypted
                token = decrypt_if_needed(request.cluster_token or request.gadget_token)
                ca_cert = decrypt_if_needed(request.gadget_ca_cert)
                
                if not token:
                    raise ValueError("Remote cluster token is required but not provided")
                
                temp_kubeconfig = create_remote_kubeconfig(
                    api_server_url=request.cluster_api_url,
                    token=token,
                    ca_cert=ca_cert if ca_cert else None,
                    cluster_name=request.cluster_name or f"cluster-{request.cluster_id}",
                    skip_tls_verify=not request.verify_ssl
                )
                kubeconfig_path = temp_kubeconfig
                kubectl_context = request.cluster_name or f"cluster-{request.cluster_id}"
            
            # Create Gadget client based on protocol
            if protocol in ('kubectl', 'kubectl-gadget', 'cli'):
                # Use kubectl-gadget CLI client (v0.46.0+)
                client = KubectlGadgetClient(
                    gadget_namespace=request.gadget_namespace,  # REQUIRED - from collection request
                    kubeconfig=kubeconfig_path,
                    context=kubectl_context,
                    gadget_image_version=settings.gadget_image_version,
                    gadget_registry=settings.gadget_registry,
                    gadget_image_prefix=settings.gadget_image_prefix,
                    timeout_seconds=settings.gadget_grpc_timeout
                )
            else:
                # Use factory for other protocols (grpc, http, agent)
                client = GadgetClientFactory.create_from_collection_request(request)
            
            # Connect to Gadget
            connected = await client.connect()
            if not connected:
                raise Exception("Failed to connect to Inspektor Gadget")
            
            # Start pod discovery for destination enrichment (best effort)
            # NOTE: We discover ALL namespaces, not just scope namespaces,
            # because we need to resolve external IPs that may be in other namespaces
            pod_discovery = None
            try:
                # Use the same kubeconfig as the gadget client (important for remote clusters!)
                pod_discovery = PodDiscovery(
                    kubeconfig=kubeconfig_path,
                    context=kubectl_context,
                    refresh_interval_seconds=settings.pod_discovery_refresh_interval,
                    cluster_manager_url=settings.cluster_manager_url
                )
                # Discover ALL pods in cluster for IP -> name resolution
                # External connections often go to pods in other namespaces
                await pod_discovery.start(namespaces=None)  # None = all namespaces
                
                # Count pods vs services in cache for debugging
                total_count = len(pod_discovery.cache._cache)
                service_count = sum(1 for v in pod_discovery.cache._cache.values() 
                                   if hasattr(v, 'owner_kind') and v.owner_kind == 'Service')
                pod_count = total_count - service_count
                
                logger.info("Pod discovery started for session",
                           session_id=session_id,
                           pod_count=pod_count,
                           service_count=service_count,
                           total_cache=total_count,
                           cache_ready=pod_discovery.is_cache_ready())
                
                # Publish pod metadata to workload_metadata queue (best effort)
                if pod_count > 0:
                    await self._publish_pod_metadata(
                        session_id=session_id,
                        analysis_id=request.analysis_id,
                        cluster_id=request.cluster_id,
                        pods=pod_discovery.cache.get_all_pods_as_dicts()
                    )
            except Exception as e:
                # Pod discovery is optional - log and continue
                logger.warning("Pod discovery failed, continuing without enrichment",
                              error=str(e))
                pod_discovery = None
            
            # Create session
            session = TraceSession(
                session_id=session_id,
                task_id=request.task_id,
                analysis_id=request.analysis_id,
                cluster_id=request.cluster_id,
                client=client,
                gadget_modules=request.gadget_modules,
                scope=self._scope_to_dict(request.scope),
                gadget_namespace=request.gadget_namespace,  # From UI
                pod_discovery=pod_discovery,
                temp_kubeconfig=temp_kubeconfig  # For cleanup on session end
            )
            
            self.active_sessions[session_id] = session
            
            # Start traces for each gadget module
            # Support multiple namespaces in scope
            scope_namespaces = list(request.scope.namespaces) if request.scope.namespaces else []
            
            # Map event type IDs to gadget names if needed
            EVENT_TYPE_TO_GADGET = {
                'network_flow': 'trace_network',
                'dns_query': 'trace_dns',
                'tcp_throughput': 'top_tcp',        # Required for bytes sent/received
                'tcp_retransmit': 'trace_tcpretrans',  # Required for network errors
                'process_exec': 'trace_exec',
                'file_operations': 'trace_open',
                'capability_checks': 'trace_capabilities',
                'oom_kills': 'trace_oomkill',
                'bind_events': 'trace_bind',
                'sni_events': 'trace_sni',
                'mount_events': 'trace_mount',
            }
            
            gadget_modules_normalized = []
            for g in request.gadget_modules:
                if g.startswith('trace_') or g.startswith('top_'):
                    gadget_modules_normalized.append(g)
                elif g in EVENT_TYPE_TO_GADGET:
                    gadget_modules_normalized.append(EVENT_TYPE_TO_GADGET[g])
                else:
                    gadget_modules_normalized.append(g)
            
            # CRITICAL FIX: Auto-add dependent gadgets for complete network metrics
            # When network_flow (trace_network/trace_tcp) is enabled, we MUST also enable:
            # - top_tcp: Required for bytes_sent/bytes_received metrics
            # - trace_tcpretrans: Required for network error detection
            # Without these, network flows will have 0 bytes and 0 errors
            network_gadgets = {'trace_network', 'trace_tcp', 'network_flow', 'network', 'network_traffic'}
            original_modules_lower = [g.lower() for g in request.gadget_modules]
            has_network = any(g in network_gadgets or g.lower() in network_gadgets for g in gadget_modules_normalized)
            
            if has_network:
                # Add top_tcp for byte transfer metrics if not already present
                if 'top_tcp' not in gadget_modules_normalized and 'tcp_throughput' not in original_modules_lower:
                    gadget_modules_normalized.append('top_tcp')
                    logger.info("Auto-added top_tcp gadget for byte transfer metrics")
                
                # Add trace_tcpretrans for network error detection if not already present
                if 'trace_tcpretrans' not in gadget_modules_normalized and 'tcp_retransmit' not in original_modules_lower:
                    gadget_modules_normalized.append('trace_tcpretrans')
                    logger.info("Auto-added trace_tcpretrans gadget for network error detection")
            
            # Remove duplicates
            gadget_modules_normalized = list(dict.fromkeys(gadget_modules_normalized))
            
            logger.info("Starting traces for gadget modules",
                       session_id=session_id,
                       original_modules=list(request.gadget_modules),
                       normalized_modules=gadget_modules_normalized)
            
            for gadget_module in gadget_modules_normalized:
                trace_config = TraceConfig(
                    analysis_id=str(request.analysis_id),
                    cluster_id=str(request.cluster_id),
                    trace_type=gadget_module,
                    # For multiple namespaces, pass all of them
                    namespace=scope_namespaces[0] if len(scope_namespaces) == 1 else None,
                    namespaces=scope_namespaces if len(scope_namespaces) > 1 else None,
                    pod_name=request.scope.pods[0] if request.scope.pods else None,
                    labels=dict(request.scope.labels) if request.scope.labels else None,
                    exclude_namespaces=list(request.scope.exclude_namespaces) if request.scope.exclude_namespaces else None,
                    exclude_pod_patterns=list(request.scope.exclude_pod_patterns) if request.scope.exclude_pod_patterns else None,
                    exclude_strategy=request.scope.exclude_strategy or None
                )
                
                trace_id = await client.start_trace(trace_config)
                session.trace_ids.append(trace_id)
                
                # Start event collection task
                task = asyncio.create_task(
                    self._collect_events(session, trace_id)
                )
                session.collection_tasks.append(task)
            
            # Check for gadget startup errors after all traces started
            # Wait once (not per-gadget) to detect failures
            if hasattr(client, 'check_startup_errors'):
                await client.check_startup_errors(wait_seconds=2.0)
            
            if hasattr(client, 'get_all_gadget_errors'):
                gadget_errors = client.get_all_gadget_errors()
                if gadget_errors:
                    session.gadget_errors = gadget_errors
                    logger.warning("Some gadgets failed to start",
                                  session_id=session_id,
                                  failed_gadgets=[e['gadget'] for e in gadget_errors])
            
            # Set status based on whether all gadgets started successfully
            if session.gadget_errors and len(session.gadget_errors) == len(request.gadget_modules):
                # All gadgets failed
                session.status = "failed"
                logger.error("All gadgets failed to start",
                            session_id=session_id,
                            errors=session.gadget_errors)
            elif session.gadget_errors:
                # Some gadgets failed
                session.status = "running_with_errors"
                logger.warning("Collection started with some gadget failures",
                              session_id=session_id,
                              working_gadgets=len(request.gadget_modules) - len(session.gadget_errors),
                              failed_gadgets=len(session.gadget_errors))
            else:
                session.status = "running"
            
            logger.info("Collection session started",
                       session_id=session_id,
                       trace_count=len(session.trace_ids),
                       status=session.status,
                       gadget_errors=len(session.gadget_errors) if session.gadget_errors else 0)
            
            return session
            
        except Exception as e:
            logger.error("Failed to start collection",
                        error=str(e),
                        task_id=request.task_id)
            raise
    
    async def stop_collection(self, session_id: str) -> bool:
        """
        Stop eBPF trace collection
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if stopped successfully
        """
        try:
            if session_id not in self.active_sessions:
                logger.warning("Session not found", session_id=session_id)
                return False
            
            session = self.active_sessions[session_id]
            
            logger.info("Stopping collection session",
                       session_id=session_id,
                       trace_count=len(session.trace_ids))
            
            # Stop all traces
            for trace_id in session.trace_ids:
                await session.client.stop_trace(trace_id)
            
            # Cancel all collection tasks
            for task in session.collection_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Disconnect client
            await session.client.disconnect()
            
            # Stop pod discovery
            if session.pod_discovery:
                await session.pod_discovery.stop()
            
            # Update session status
            session.status = "completed"
            
            # Clean up temporary files (kubeconfig, CA cert)
            session.cleanup_temp_files()
            
            # Remove from active sessions
            del self.active_sessions[session_id]
            
            logger.info("Collection session stopped",
                       session_id=session_id,
                       events_collected=session.events_collected)
            
            return True
            
        except Exception as e:
            logger.error("Failed to stop collection",
                        session_id=session_id,
                        error=str(e))
            return False
    
    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get collection session status"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        return {
            "session_id": session.session_id,
            "task_id": session.task_id,
            "status": session.status,
            "events_collected": session.events_collected,
            "errors_count": session.errors_count,
            "started_at": session.started_at.isoformat(),
            "last_event_at": session.last_event_at.isoformat() if session.last_event_at else None,
            "trace_count": len(session.trace_ids),
            "gadget_errors": session.gadget_errors if session.gadget_errors else []
        }
    
    async def _collect_events(self, session: TraceSession, trace_id: str):
        """Collect events from trace and publish to RabbitMQ"""
        try:
            logger.info("Starting event collection",
                       session_id=session.session_id,
                       trace_id=trace_id)
            
            # Token bucket rate limiter (if configured)
            import time as _time
            max_eps = settings.max_events_per_second
            bucket_tokens = float(max_eps) if max_eps > 0 else 0.0
            bucket_last_refill = _time.monotonic()
            dropped_count = 0
            
            # Pass PodIPCache for namespace-scoped analyses to include INCOMING traffic
            pod_ip_cache = session.pod_discovery.cache if session.pod_discovery else None
            
            async for event in session.client.stream_events(trace_id, pod_ip_cache=pod_ip_cache):
                try:
                    # Rate limiting: token bucket algorithm
                    if max_eps > 0:
                        now = _time.monotonic()
                        elapsed = now - bucket_last_refill
                        bucket_tokens = min(float(max_eps), bucket_tokens + elapsed * max_eps)
                        bucket_last_refill = now
                        
                        if bucket_tokens < 1.0:
                            dropped_count += 1
                            if dropped_count % 1000 == 1:
                                logger.warning("Rate limit: dropping events",
                                             session_id=session.session_id,
                                             dropped_total=dropped_count,
                                             max_eps=max_eps)
                            continue
                        bucket_tokens -= 1.0
                    
                    # Update session statistics
                    session.events_collected += 1
                    session.last_event_at = datetime.utcnow()
                    
                    # Publish to RabbitMQ
                    await self._publish_event(session, event)
                    
                    # Log every 100 events
                    if session.events_collected % 100 == 0:
                        logger.info("Events collected",
                                   session_id=session.session_id,
                                   count=session.events_collected)
                    
                except Exception as e:
                    session.errors_count += 1
                    logger.error("Event processing error",
                                session_id=session.session_id,
                                error=str(e))
            
            logger.info("Event collection ended",
                       session_id=session.session_id,
                       trace_id=trace_id,
                       events=session.events_collected)
                       
        except asyncio.CancelledError:
            logger.info("Event collection cancelled",
                       session_id=session.session_id,
                       trace_id=trace_id)
        except Exception as e:
            logger.error("Event collection failed",
                        session_id=session.session_id,
                        trace_id=trace_id,
                        error=str(e))
            session.status = "failed"
    
    async def _publish_event(self, session: TraceSession, event):
        """Publish event to RabbitMQ based on event type"""
        try:
            # Enrich event data with destination pod info (best effort)
            enriched_data = dict(event.data) if event.data else {}
            
            # Try to enrich destination IP with pod name and labels (for network events)
            # ALWAYS try to enrich metadata even if dst_pod is already set (from gadget)
            # because gadget only provides basic info, not labels/owner/etc.
            if session.pod_discovery and 'dst_ip' in enriched_data:
                dst_ip = enriched_data.get('dst_ip', '')
                # Enrich if: no dst_pod OR no metadata (dst_labels missing)
                needs_enrichment = dst_ip and (
                    not enriched_data.get('dst_pod') or 
                    not enriched_data.get('dst_labels')
                )
                if needs_enrichment:
                    # Lookup destination pod by IP - get full pod info
                    pod_info = session.pod_discovery.cache.lookup(dst_ip)
                    if pod_info:
                        # Core fields - update if not present
                        if not enriched_data.get('dst_pod'):
                            enriched_data['dst_pod'] = pod_info.name
                        if not enriched_data.get('dst_namespace'):
                            enriched_data['dst_namespace'] = pod_info.namespace
                        if not enriched_data.get('dst_node'):
                            enriched_data['dst_node'] = pod_info.node
                        # Metadata - always set from PodDiscovery (authoritative source)
                        enriched_data['dst_labels'] = pod_info.labels
                        enriched_data['dst_annotations'] = pod_info.annotations
                        enriched_data['dst_owner_kind'] = pod_info.owner_kind
                        enriched_data['dst_owner_name'] = pod_info.owner_name
                        # Extended metadata
                        enriched_data['dst_pod_uid'] = pod_info.uid
                        enriched_data['dst_host_ip'] = pod_info.host_ip
                        enriched_data['dst_container'] = pod_info.container_name
                        enriched_data['dst_image'] = pod_info.container_image
                        enriched_data['dst_service_account'] = pod_info.service_account
                        enriched_data['dst_phase'] = pod_info.phase
                        logger.debug("Enriched destination",
                                   dst_ip=dst_ip,
                                   dst_pod=pod_info.name,
                                   dst_namespace=pod_info.namespace,
                                   dst_owner=f"{pod_info.owner_kind}/{pod_info.owner_name}")
                    else:
                        # EXTENDED LOOKUP: Try node, DNS, CIDR when pod/service not found
                        resolved = await session.pod_discovery.lookup_extended(dst_ip)
                        if resolved:
                            if not enriched_data.get('dst_pod'):
                                enriched_data['dst_pod'] = resolved.name
                            if not enriched_data.get('dst_namespace'):
                                enriched_data['dst_namespace'] = resolved.namespace or 'external'
                            if resolved.owner_kind:
                                enriched_data['dst_owner_kind'] = resolved.owner_kind
                            if resolved.owner_name:
                                enriched_data['dst_owner_name'] = resolved.owner_name
                            if resolved.labels:
                                enriched_data['dst_labels'] = resolved.labels
                            # Mark the resolution source for debugging
                            enriched_data['dst_resolution_source'] = resolved.source
                            # Add network_type for frontend grouping/visualization
                            # This enables proper display of "Internal-Network" type traffic
                            # while maintaining unique nodes per destination IP
                            if resolved.network_type:
                                enriched_data['dst_network_type'] = resolved.network_type
                            logger.debug("Enriched destination (extended)",
                                       dst_ip=dst_ip,
                                       dst_name=resolved.name,
                                       source=resolved.source,
                                       network_type=resolved.network_type)
            
            # Also enrich source if available (especially important for accept events)
            # For accept events: src_ip is the external caller, may or may not be in cache
            # For connect events: src is the local pod, should be in cache
            if session.pod_discovery and 'src_ip' in enriched_data:
                src_ip = enriched_data.get('src_ip', '')
                # Enrich if: no labels OR no owner (metadata missing)
                needs_enrichment = src_ip and (
                    not enriched_data.get('labels') or 
                    not enriched_data.get('owner_kind')
                )
                if needs_enrichment:
                    pod_info = session.pod_discovery.cache.lookup(src_ip)
                    if pod_info:
                        # Core fields - update if not present
                        if not enriched_data.get('src_namespace'):
                            enriched_data['src_namespace'] = pod_info.namespace
                        if not enriched_data.get('src_pod'):
                            enriched_data['src_pod'] = pod_info.name
                        if not enriched_data.get('src_node'):
                            enriched_data['src_node'] = pod_info.node
                        # Metadata - always set from PodDiscovery (authoritative source)
                        enriched_data['labels'] = pod_info.labels
                        enriched_data['annotations'] = pod_info.annotations
                        enriched_data['owner_kind'] = pod_info.owner_kind
                        enriched_data['owner_name'] = pod_info.owner_name
                        # Extended metadata for source
                        enriched_data['src_pod_uid'] = pod_info.uid
                        enriched_data['src_host_ip'] = pod_info.host_ip
                        enriched_data['src_container'] = pod_info.container_name
                        enriched_data['src_image'] = pod_info.container_image
                        enriched_data['src_service_account'] = pod_info.service_account
                        enriched_data['src_phase'] = pod_info.phase
                        
                        logger.debug("Enriched source",
                                   src_ip=src_ip,
                                   src_pod=pod_info.name,
                                   src_namespace=pod_info.namespace,
                                   src_owner=f"{pod_info.owner_kind}/{pod_info.owner_name}")
                    else:
                        # EXTENDED LOOKUP: Try node, DNS, CIDR when pod/service not found
                        resolved = await session.pod_discovery.lookup_extended(src_ip)
                        if resolved:
                            if not enriched_data.get('src_pod'):
                                enriched_data['src_pod'] = resolved.name
                            if not enriched_data.get('src_namespace'):
                                enriched_data['src_namespace'] = resolved.namespace or 'external'
                            if resolved.owner_kind:
                                enriched_data['owner_kind'] = resolved.owner_kind
                            if resolved.owner_name:
                                enriched_data['owner_name'] = resolved.owner_name
                            if resolved.labels:
                                enriched_data['labels'] = resolved.labels
                            # Mark the resolution source for debugging
                            enriched_data['src_resolution_source'] = resolved.source
                            # Add network_type for frontend grouping/visualization
                            if resolved.network_type:
                                enriched_data['src_network_type'] = resolved.network_type
                            logger.debug("Enriched source (extended)",
                                       src_ip=src_ip,
                                       src_name=resolved.name,
                                       source=resolved.source,
                                       network_type=resolved.network_type)
            
            # Determine L7 application protocol based on service metadata
            # Priority: appProtocol > port name > well-known port
            if session.pod_discovery and 'dst_port' in enriched_data:
                dst_ip = enriched_data.get('dst_ip', '')
                dst_port = enriched_data.get('dst_port')
                if dst_ip and dst_port:
                    try:
                        port_num = int(dst_port) if isinstance(dst_port, str) else dst_port
                        app_protocol = session.pod_discovery.determine_app_protocol(dst_ip, port_num)
                        # Only set if not already set or if current is just TCP
                        current_protocol = enriched_data.get('protocol', '').upper()
                        if not current_protocol or current_protocol in ('TCP', 'UDP'):
                            enriched_data['app_protocol'] = app_protocol
                            if app_protocol not in ('TCP', 'UDP'):
                                logger.debug("Detected L7 protocol",
                                           dst_ip=dst_ip,
                                           dst_port=port_num,
                                           app_protocol=app_protocol)
                    except (ValueError, TypeError):
                        pass  # Invalid port, skip protocol detection
            
            # Build message with common fields
            # Multi-cluster support: format analysis_id as '{analysis_id}-{cluster_id}'
            # This enables pattern matching when querying: WHERE analysis_id LIKE '123-%'
            formatted_analysis_id = f"{session.analysis_id}-{session.cluster_id}"
            
            message = {
                "session_id": session.session_id,
                "task_id": session.task_id,
                "analysis_id": formatted_analysis_id,  # Formatted for multi-cluster support
                "cluster_id": session.cluster_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "data": enriched_data,
                "scope": session.scope
            }
            
            # Route to correct exchange based on event type
            event_type = event.event_type.lower()
            
            # Use the new unified routing method
            await self.rabbitmq.publish_by_event_type(event_type, message)
            
        except Exception as e:
            logger.error("Failed to publish event",
                        session_id=session.session_id,
                        event_type=event.event_type,
                        error=str(e))
    
    async def _publish_pod_metadata(
        self,
        session_id: str,
        analysis_id: int,
        cluster_id: int,
        pods: list
    ):
        """
        Publish pod metadata to RabbitMQ for storage in workload_metadata table
        
        This enables IP -> Pod name lookups in graph-writer and other services.
        """
        try:
            from datetime import datetime
            
            # Multi-cluster support: format analysis_id as '{analysis_id}-{cluster_id}'
            formatted_analysis_id = f"{analysis_id}-{cluster_id}"
            
            # Publish each pod as a workload_metadata message
            for pod in pods:
                message = {
                    "session_id": session_id,
                    "analysis_id": formatted_analysis_id,
                    "cluster_id": cluster_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "event_type": "workload_metadata",
                    "data": {
                        "namespace": pod.get("namespace", ""),
                        "workload_name": pod.get("owner_name", pod.get("pod_name", "")),
                        "workload_type": pod.get("owner_kind", "Pod"),
                        "pod_name": pod.get("pod_name", ""),
                        "pod_ip": pod.get("pod_ip", ""),
                        "node_name": pod.get("node_name", ""),
                        "labels": pod.get("labels", {}),
                        "owner_kind": pod.get("owner_kind", ""),
                        "owner_name": pod.get("owner_name", ""),
                    }
                }
                
                await self.rabbitmq.publish_by_event_type("workload_metadata", message)
            
            logger.info("Published pod metadata",
                       session_id=session_id,
                       pod_count=len(pods))
                       
        except Exception as e:
            # Non-critical - log and continue
            logger.warning("Failed to publish pod metadata",
                          error=str(e),
                          pod_count=len(pods))
    
    def _scope_to_dict(self, scope) -> dict:
        """Convert proto scope to dict"""
        result = {
            "scope_type": scope.scope_type,
            "namespaces": list(scope.namespaces),
            "deployments": list(scope.deployments),
            "pods": list(scope.pods),
            "labels": dict(scope.labels) if scope.labels else {}
        }
        if scope.exclude_namespaces:
            result["exclude_namespaces"] = list(scope.exclude_namespaces)
        if scope.exclude_pod_patterns:
            result["exclude_pod_patterns"] = list(scope.exclude_pod_patterns)
        if scope.exclude_strategy:
            result["exclude_strategy"] = scope.exclude_strategy
        return result

