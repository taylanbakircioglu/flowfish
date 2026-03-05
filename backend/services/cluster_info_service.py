"""
Cluster Information Service
Fetches real-time information from Kubernetes clusters
"""
import httpx
import asyncio
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import base64
import tempfile
import os
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()


class ClusterInfoService:
    """Service to fetch cluster information"""
    
    def __init__(self):
        # Increased timeout for remote clusters (can be slow due to network latency)
        # Large clusters with 1000+ pods may take 30-60 seconds to respond
        self.timeout = 60
    
    def _create_k8s_config(
        self,
        api_server_url: str,
        token: str,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> tuple[client.Configuration, Optional[str]]:
        """
        Create Kubernetes client configuration.
        
        Returns:
            Tuple of (configuration, temp_ca_file_path)
            Caller is responsible for cleaning up temp file if path is returned.
        """
        configuration = client.Configuration()
        configuration.host = api_server_url
        configuration.api_key = {"authorization": f"Bearer {token}"}
        temp_ca_file = None
        
        if skip_tls_verify:
            configuration.verify_ssl = False
            # Also disable SSL warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        elif ca_cert:
            # Sanitize CA cert: handle whitespace and format issues from UI copy-paste
            try:
                sanitized_cert = self._sanitize_pem_certificate(ca_cert)
                if not sanitized_cert:
                    logger.warning("CA cert is empty after sanitization, falling back to skip TLS verify")
                    configuration.verify_ssl = False
                else:
                    # Write sanitized CA cert to temp file
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.crt') as f:
                        f.write(sanitized_cert)
                        temp_ca_file = f.name
                    configuration.ssl_ca_cert = temp_ca_file
                    logger.debug("CA cert written to temp file", path=temp_ca_file)
            except Exception as e:
                logger.error("Failed to process CA cert", error=str(e))
                # Fall back to skip TLS verify
                configuration.verify_ssl = False
        
        return configuration, temp_ca_file
    
    def _sanitize_pem_certificate(self, cert: str) -> Optional[str]:
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
        # (user might have copied just the base64 content)
        if not cert.startswith('-----BEGIN'):
            # Remove any whitespace/newlines for base64 detection
            clean_b64 = re.sub(r'\s+', '', cert)
            
            # Check if it's valid base64
            try:
                decoded = base64.b64decode(clean_b64)
                # Check if decoded content looks like a DER certificate
                if decoded.startswith(b'\x30'):  # ASN.1 SEQUENCE
                    # Wrap in PEM format
                    # Re-format base64 with 64-char lines
                    formatted_b64 = '\n'.join([clean_b64[i:i+64] for i in range(0, len(clean_b64), 64)])
                    cert = f"-----BEGIN CERTIFICATE-----\n{formatted_b64}\n-----END CERTIFICATE-----\n"
                    logger.info("Converted base64 cert to PEM format")
                else:
                    # It's plain PEM that was already base64 decoded
                    cert = decoded.decode('utf-8').strip()
            except Exception:
                # Not base64, might be plain text that got corrupted
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
    
    def _cleanup_temp_file(self, file_path: Optional[str]) -> None:
        """Safely cleanup temporary file"""
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                logger.warning("Failed to cleanup temp file", path=file_path, error=str(e))
    
    async def get_cluster_info(
        self,
        connection_type: str,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """
        Fetch cluster information
        
        Returns:
            {
                "total_nodes": int,
                "total_pods": int,
                "total_namespaces": int,
                "k8s_version": str,
                "error": str (if failed)
            }
        """
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            # Normalize connection type (support both in-cluster and in_cluster)
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            logger.info("Getting cluster info", connection_type=normalized_type)
            
            # Create Kubernetes client based on connection type
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                v1 = client.CoreV1Api()
                version_api = client.VersionApi()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"error": "Kubeconfig required"}
                
                # Write kubeconfig to temp file
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    v1 = client.CoreV1Api()
                    version_api = client.VersionApi()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                
                api_client = client.ApiClient(configuration)
                v1 = client.CoreV1Api(api_client)
                version_api = client.VersionApi(api_client)
            
            else:
                logger.warning("Unknown connection type", connection_type=normalized_type)
                return {"error": f"Unknown connection type: {normalized_type}"}
            
            # Fetch cluster info using run_in_executor to avoid blocking event loop
            # K8s client is synchronous, so we run it in thread pool
            # Fetch each resource separately for better error handling
            loop = asyncio.get_event_loop()
            
            total_nodes = 0
            total_pods = 0
            total_namespaces = 0
            k8s_version = None
            errors = []
            
            # Fetch nodes
            def _fetch_nodes():
                return v1.list_node(timeout_seconds=self.timeout)
            try:
                nodes = await loop.run_in_executor(None, _fetch_nodes)
                total_nodes = len(nodes.items)
                logger.info("Fetched nodes", count=total_nodes)
            except ApiException as e:
                errors.append(f"nodes: {e.status} {e.reason}")
                logger.error("Failed to fetch nodes", status=e.status, reason=e.reason)
            except Exception as e:
                errors.append(f"nodes: {str(e)}")
                logger.error("Failed to fetch nodes", error=str(e))
            
            # Fetch namespaces
            def _fetch_namespaces():
                return v1.list_namespace(timeout_seconds=self.timeout)
            try:
                namespaces = await loop.run_in_executor(None, _fetch_namespaces)
                total_namespaces = len(namespaces.items)
                logger.info("Fetched namespaces", count=total_namespaces)
            except ApiException as e:
                errors.append(f"namespaces: {e.status} {e.reason}")
                logger.error("Failed to fetch namespaces", status=e.status, reason=e.reason)
            except Exception as e:
                errors.append(f"namespaces: {str(e)}")
                logger.error("Failed to fetch namespaces", error=str(e))
            
            # Fetch pods - this can be slow on large clusters
            def _fetch_pods():
                return v1.list_pod_for_all_namespaces(timeout_seconds=self.timeout)
            try:
                pods = await loop.run_in_executor(None, _fetch_pods)
                total_pods = len(pods.items)
                logger.info("Fetched pods", count=total_pods)
            except ApiException as e:
                errors.append(f"pods: {e.status} {e.reason}")
                logger.error("Failed to fetch pods", status=e.status, reason=e.reason)
            except Exception as e:
                errors.append(f"pods: {str(e)}")
                logger.error("Failed to fetch pods", error=str(e))
            
            # Fetch version
            def _fetch_version():
                return version_api.get_code()
            try:
                version_info = await loop.run_in_executor(None, _fetch_version)
                k8s_version = version_info.git_version if hasattr(version_info, 'git_version') else 'unknown'
                logger.info("Fetched k8s version", version=k8s_version)
            except Exception as e:
                errors.append(f"version: {str(e)}")
                logger.error("Failed to fetch k8s version", error=str(e))
            
            # Return results even if some failed
            error_msg = "; ".join(errors) if errors else None
            if errors:
                logger.warning("Cluster info fetched with errors", errors=errors, 
                              nodes=total_nodes, pods=total_pods, namespaces=total_namespaces)
            
            return {
                "total_nodes": total_nodes,
                "total_pods": total_pods,
                "total_namespaces": total_namespaces,
                "k8s_version": k8s_version,
                "error": error_msg
            }
            
        except ApiException as e:
            logger.error("Kubernetes API error", status=e.status, reason=e.reason)
            return {
                "total_nodes": 0,
                "total_pods": 0,
                "total_namespaces": 0,
                "k8s_version": None,
                "error": f"Kubernetes API error: {e.status} - {e.reason}"
            }
        except Exception as e:
            logger.error("Failed to fetch cluster info", error=str(e), connection_type=connection_type)
            return {
                "total_nodes": 0,
                "total_pods": 0,
                "total_namespaces": 0,
                "k8s_version": None,
                "error": f"Failed to fetch cluster info: {str(e)}"
            }
        finally:
            # Cleanup temp files
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)
    
    async def check_gadget_health(self, gadget_endpoint: Optional[str] = None, 
                                   gadget_namespace: Optional[str] = None) -> Dict:
        """
        Comprehensive Inspector Gadget health check.
        
        Checks multiple indicators:
        1. DaemonSet pod status (ready/total)
        2. Pod restart count (high restarts = instability)
        3. Pod conditions (Ready, ContainersReady)
        4. Recent errors in logs (eBPF/capability issues)
        
        Args:
            gadget_endpoint: Optional gRPC endpoint (kept for backward compatibility)
            gadget_namespace: Namespace where Gadget is deployed
        
        Returns:
            {
                "health_status": "healthy" | "degraded" | "unhealthy" | "unknown",
                "version": str | None,
                "error": str | None,
                "pods_ready": int,
                "pods_total": int,
                "details": {
                    "total_restarts": int,
                    "ebpf_capable": bool,
                    "issues": list[str]
                }
            }
        """
        try:
            logger.info("Starting Gadget health check", 
                       endpoint=gadget_endpoint, 
                       provided_namespace=gadget_namespace)
            
            # Extract namespace from endpoint if not provided
            if not gadget_namespace and gadget_endpoint:
                # Parse: inspektor-gadget.pilot-flowfish.svc.cluster.local:16060
                # Remove port first
                endpoint_no_port = gadget_endpoint.split(':')[0]
                parts = endpoint_no_port.replace('http://', '').replace('https://', '').split('.')
                logger.debug("Parsing endpoint", parts=parts)
                if len(parts) >= 2:
                    gadget_namespace = parts[1]
            
            if not gadget_namespace:
                logger.error("gadget_namespace is required but not provided")
                return {
                    "health_status": "unknown",
                    "version": None,
                    "error": "gadget_namespace is required but not provided",
                    "pods_ready": 0,
                    "pods_total": 0,
                    "details": {"total_restarts": 0, "ebpf_capable": False, "issues": ["gadget_namespace not configured"]}
                }
            
            logger.info("Checking Gadget health (comprehensive)", 
                       namespace=gadget_namespace,
                       endpoint=gadget_endpoint)
            
            # Use in-cluster config
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except config.ConfigException:
                    logger.warning("Could not load Kubernetes config for Gadget health check")
                    return {
                        "health_status": "unknown",
                        "version": None,
                        "error": "Kubernetes config not available",
                        "pods_ready": 0,
                        "pods_total": 0,
                        "details": {"total_restarts": 0, "ebpf_capable": False, "issues": ["K8s config unavailable"]}
                    }
            
            apps_v1 = client.AppsV1Api()
            v1 = client.CoreV1Api()
            
            def comprehensive_check():
                issues = []
                total_restarts = 0
                ebpf_capable = True
                version = None
                
                try:
                    # 1. Check DaemonSet status
                    ds = apps_v1.read_namespaced_daemon_set(
                        name="inspektor-gadget",
                        namespace=gadget_namespace
                    )
                    
                    desired = ds.status.desired_number_scheduled or 0
                    ready = ds.status.number_ready or 0
                    
                    # Get version from container image
                    if ds.spec.template.spec.containers:
                        image = ds.spec.template.spec.containers[0].image
                        if ':' in image:
                            version = image.split(':')[-1]
                    
                    if desired == 0:
                        issues.append("No nodes scheduled for DaemonSet")
                    elif ready < desired:
                        issues.append(f"Only {ready}/{desired} pods ready")
                    
                    # 2. Check individual pods for restarts and conditions
                    pods = v1.list_namespaced_pod(
                        namespace=gadget_namespace,
                        label_selector="app=inspektor-gadget"
                    )
                    
                    for pod in pods.items:
                        # Check restart count
                        if pod.status.container_statuses:
                            for cs in pod.status.container_statuses:
                                total_restarts += cs.restart_count
                                
                                # Check if container is in waiting state with error
                                if cs.state.waiting:
                                    reason = cs.state.waiting.reason
                                    if reason in ['CrashLoopBackOff', 'Error', 'ImagePullBackOff']:
                                        issues.append(f"Pod {pod.metadata.name}: {reason}")
                                        ebpf_capable = False
                                
                                # Check last termination reason
                                if cs.last_state.terminated:
                                    term_reason = cs.last_state.terminated.reason
                                    if term_reason == 'Error':
                                        exit_code = cs.last_state.terminated.exit_code
                                        if exit_code != 0:
                                            issues.append(f"Pod {pod.metadata.name} crashed (exit {exit_code})")
                        
                        # Check pod conditions
                        if pod.status.conditions:
                            for condition in pod.status.conditions:
                                if condition.type == 'Ready' and condition.status != 'True':
                                    if condition.message and 'privilege' in condition.message.lower():
                                        issues.append("Insufficient privileges for eBPF")
                                        ebpf_capable = False
                    
                    # High restart count indicates instability
                    if total_restarts > len(pods.items) * 3:  # More than 3 restarts per pod average
                        issues.append(f"High restart count: {total_restarts}")
                        ebpf_capable = False
                    
                    # 3. Quick log check for common eBPF errors (last pod only for efficiency)
                    if pods.items:
                        try:
                            logs = v1.read_namespaced_pod_log(
                                name=pods.items[0].metadata.name,
                                namespace=gadget_namespace,
                                tail_lines=50
                            )
                            
                            # Check for CRITICAL eBPF errors only (more specific patterns)
                            # These are definitive failures, not warnings
                            critical_error_indicators = [
                                ('permission denied', 'eBPF permission denied'),
                                ('operation not permitted', 'eBPF operation not permitted'),
                                ('failed to load bpf', 'Failed to load eBPF program'),
                                ('seccomp: blocking', 'Seccomp blocking eBPF'),
                            ]
                            
                            logs_lower = logs.lower()
                            for indicator, message in critical_error_indicators:
                                if indicator in logs_lower:
                                    if message not in issues:
                                        issues.append(message)
                                    ebpf_capable = False
                            
                            # Check for positive indicators (Gadget is working)
                            # If pods are ready and any of these appear, gadget is functional
                            positive_indicators = [
                                'gadget tracer manager',
                                'starting tracer',
                                'tracer started',
                                'listening on',
                                'grpc server started',
                                'ready to serve'
                            ]
                            
                            # If pods are ready and we see positive indicators, trust that
                            if ready == desired and ready > 0:
                                for indicator in positive_indicators:
                                    if indicator in logs_lower:
                                        ebpf_capable = True
                                        break
                                # If all pods ready but no positive indicator, still assume working
                                # (logs might have rotated or not include startup messages)
                                if ready == desired:
                                    ebpf_capable = True
                                    
                        except Exception as log_err:
                            logger.debug("Could not read Gadget logs", error=str(log_err))
                    
                    return {
                        "desired": desired,
                        "ready": ready,
                        "version": version,
                        "total_restarts": total_restarts,
                        "ebpf_capable": ebpf_capable,
                        "issues": issues,
                        "error": None
                    }
                    
                except ApiException as e:
                    if e.status == 404:
                        return {
                            "desired": 0, "ready": 0, "version": None,
                            "total_restarts": 0, "ebpf_capable": False,
                            "issues": ["DaemonSet not found"],
                            "error": "DaemonSet not found"
                        }
                    return {
                        "desired": 0, "ready": 0, "version": None,
                        "total_restarts": 0, "ebpf_capable": False,
                        "issues": [f"API error: {e.reason}"],
                        "error": f"API error: {e.reason}"
                    }
                except Exception as e:
                    return {
                        "desired": 0, "ready": 0, "version": None,
                        "total_restarts": 0, "ebpf_capable": False,
                        "issues": [str(e)],
                        "error": str(e)
                    }
            
            result = await asyncio.to_thread(comprehensive_check)
            
            if result["error"] and "not found" in result["error"].lower():
                return {
                    "health_status": "unknown",
                    "version": None,
                    "error": result["error"],
                    "pods_ready": 0,
                    "pods_total": 0,
                    "details": {
                        "total_restarts": 0,
                        "ebpf_capable": False,
                        "issues": result["issues"]
                    }
                }
            
            desired = result["desired"]
            ready = result["ready"]
            version = result["version"]
            ebpf_capable = result["ebpf_capable"]
            issues = result["issues"]
            
            # Determine health status based on multiple factors
            # PRIORITY: If all pods are ready, gadget is HEALTHY (trust K8s readiness probes)
            if desired == 0:
                health_status = "unknown"
            elif ready == desired and ready > 0:
                # All pods ready = gadget is working
                # Even if there are minor issues (RBAC warnings, signature warnings), it's functional
                if not issues:
                    health_status = "healthy"
                else:
                    # Has warnings but all pods ready = degraded (not unhealthy)
                    health_status = "degraded"
            elif ready > 0 and ready >= desired * 0.8:
                # At least 80% of pods ready = degraded
                health_status = "degraded"
            elif ready > 0:
                # Some pods ready but less than 80% = unhealthy
                health_status = "unhealthy"
            else:
                health_status = "unhealthy"
            
            logger.info("Gadget comprehensive health check completed", 
                       health_status=health_status, 
                       pods_ready=ready, 
                       pods_total=desired,
                       ebpf_capable=ebpf_capable,
                       issues_count=len(issues),
                       version=version)
            
            return {
                "health_status": health_status,
                "version": version,
                "error": "; ".join(issues) if issues else None,
                "pods_ready": ready,
                "pods_total": desired,
                "details": {
                    "total_restarts": result["total_restarts"],
                    "ebpf_capable": ebpf_capable,
                    "issues": issues
                }
            }
            
        except Exception as e:
            import traceback
            logger.error("Gadget health check error", 
                        error=str(e), 
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc())
            return {
                "health_status": "unknown",
                "version": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "pods_ready": 0,
                "pods_total": 0,
                "details": {
                    "total_restarts": 0,
                    "ebpf_capable": False,
                    "issues": [f"{type(e).__name__}: {str(e)}"]
                }
            }


    async def get_namespaces(
        self,
        connection_type: str,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """Fetch list of namespaces from cluster"""
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                v1 = client.CoreV1Api()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"namespaces": [], "error": "Kubeconfig required"}
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    v1 = client.CoreV1Api()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"namespaces": [], "error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                v1 = client.CoreV1Api(client.ApiClient(configuration))
            else:
                return {"namespaces": [], "error": f"Unknown connection type: {normalized_type}"}
            
            # Run sync K8s call in executor to avoid blocking event loop
            def _fetch_namespaces():
                return v1.list_namespace(timeout_seconds=self.timeout)
            
            loop = asyncio.get_event_loop()
            namespaces = await loop.run_in_executor(None, _fetch_namespaces)
            
            ns_list = []
            for ns in namespaces.items:
                ns_list.append({
                    "name": ns.metadata.name,
                    "labels": ns.metadata.labels or {},
                    "status": ns.status.phase if ns.status else "Unknown",
                    "created_at": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
                })
            
            logger.info("Retrieved namespaces from cluster", count=len(ns_list))
            return {"namespaces": ns_list, "error": None}
            
        except Exception as e:
            logger.error("Failed to get namespaces", error=str(e))
            return {"namespaces": [], "error": str(e)}
        finally:
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)
    
    async def get_deployments(
        self,
        connection_type: str,
        namespace: Optional[str] = None,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """Fetch list of deployments from cluster"""
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                apps_v1 = client.AppsV1Api()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"deployments": [], "error": "Kubeconfig required"}
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    apps_v1 = client.AppsV1Api()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"deployments": [], "error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                apps_v1 = client.AppsV1Api(client.ApiClient(configuration))
            else:
                return {"deployments": [], "error": f"Unknown connection type: {normalized_type}"}
            
            # Run sync K8s call in executor to avoid blocking event loop
            def _fetch_deployments():
                if namespace:
                    return apps_v1.list_namespaced_deployment(namespace, timeout_seconds=self.timeout)
                else:
                    return apps_v1.list_deployment_for_all_namespaces(timeout_seconds=self.timeout)
            
            loop = asyncio.get_event_loop()
            deployments = await loop.run_in_executor(None, _fetch_deployments)
            
            deploy_list = []
            for deploy in deployments.items:
                deploy_list.append({
                    "name": deploy.metadata.name,
                    "namespace": deploy.metadata.namespace,
                    "uid": deploy.metadata.uid,
                    "labels": deploy.metadata.labels or {},
                    "replicas": deploy.spec.replicas or 0,
                    "ready_replicas": deploy.status.ready_replicas or 0,
                    "created_at": deploy.metadata.creation_timestamp.isoformat() if deploy.metadata.creation_timestamp else None
                })
            
            logger.info("Retrieved deployments from cluster", count=len(deploy_list), namespace=namespace)
            return {"deployments": deploy_list, "error": None}
            
        except Exception as e:
            logger.error("Failed to get deployments", error=str(e))
            return {"deployments": [], "error": str(e)}
        finally:
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)
    
    async def get_labels(
        self,
        connection_type: str,
        namespace: Optional[str] = None,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """Get unique labels from pods in cluster"""
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                v1 = client.CoreV1Api()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"labels": [], "error": "Kubeconfig required"}
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    v1 = client.CoreV1Api()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"labels": [], "error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                v1 = client.CoreV1Api(client.ApiClient(configuration))
            else:
                return {"labels": [], "error": f"Unknown connection type: {normalized_type}"}
            
            # Run sync K8s call in executor to avoid blocking event loop
            def _fetch_pods_for_labels():
                if namespace:
                    return v1.list_namespaced_pod(namespace, timeout_seconds=self.timeout)
                else:
                    return v1.list_pod_for_all_namespaces(timeout_seconds=self.timeout)
            
            loop = asyncio.get_event_loop()
            pods = await loop.run_in_executor(None, _fetch_pods_for_labels)
            
            # Collect unique label keys and their values
            label_map = {}
            for pod in pods.items:
                if pod.metadata.labels:
                    for key, value in pod.metadata.labels.items():
                        # Skip Kubernetes internal labels
                        if key.startswith('pod-template-hash') or key.startswith('controller-revision-hash'):
                            continue
                        if key not in label_map:
                            label_map[key] = set()
                        label_map[key].add(value)
            
            labels_list = [
                {"key": key, "values": sorted(list(values))}
                for key, values in sorted(label_map.items())
            ]
            
            logger.info("Retrieved labels from cluster", count=len(labels_list))
            return {"labels": labels_list, "error": None}
            
        except Exception as e:
            logger.error("Failed to get labels", error=str(e))
            return {"labels": [], "error": str(e)}
        finally:
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)

    async def get_pods(
        self,
        connection_type: str,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """Fetch list of pods from cluster"""
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                v1 = client.CoreV1Api()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"pods": [], "error": "Kubeconfig required"}
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    v1 = client.CoreV1Api()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"pods": [], "error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                v1 = client.CoreV1Api(client.ApiClient(configuration))
            else:
                return {"pods": [], "error": f"Unknown connection type: {normalized_type}"}
            
            # Run sync K8s call in executor to avoid blocking event loop
            def _fetch_pods():
                if namespace:
                    if label_selector:
                        return v1.list_namespaced_pod(namespace, label_selector=label_selector, timeout_seconds=self.timeout)
                    else:
                        return v1.list_namespaced_pod(namespace, timeout_seconds=self.timeout)
                else:
                    if label_selector:
                        return v1.list_pod_for_all_namespaces(label_selector=label_selector, timeout_seconds=self.timeout)
                    else:
                        return v1.list_pod_for_all_namespaces(timeout_seconds=self.timeout)
            
            loop = asyncio.get_event_loop()
            pods = await loop.run_in_executor(None, _fetch_pods)
            
            pod_list = []
            for pod in pods.items:
                # Get first container image (for gadget pods, there's typically one container)
                container_image = None
                if pod.spec and pod.spec.containers:
                    container_image = pod.spec.containers[0].image
                
                pod_list.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "uid": pod.metadata.uid,
                    "status": pod.status.phase if pod.status else "Unknown",
                    "node_name": pod.spec.node_name if pod.spec else None,
                    "labels": pod.metadata.labels or {},
                    "ip": pod.status.pod_ip if pod.status else None,
                    "image": container_image,
                    "created_at": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                })
            
            logger.info("Retrieved pods from cluster", count=len(pod_list), namespace=namespace)
            return {"pods": pod_list, "error": None}
            
        except Exception as e:
            logger.error("Failed to get pods", error=str(e))
            return {"pods": [], "error": str(e)}
        finally:
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)

    async def get_services(
        self,
        connection_type: str,
        namespace: Optional[str] = None,
        api_server_url: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False
    ) -> Dict:
        """Fetch list of services from cluster"""
        temp_ca_file = None
        kubeconfig_path = None
        
        try:
            normalized_type = connection_type.replace('_', '-').lower() if connection_type else ""
            
            if normalized_type == "in-cluster":
                config.load_incluster_config()
                v1 = client.CoreV1Api()
            elif normalized_type == "kubeconfig":
                if not kubeconfig:
                    return {"services": [], "error": "Kubeconfig required"}
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                    f.write(kubeconfig)
                    kubeconfig_path = f.name
                try:
                    config.load_kube_config(config_file=kubeconfig_path)
                    v1 = client.CoreV1Api()
                finally:
                    self._cleanup_temp_file(kubeconfig_path)
                    kubeconfig_path = None
            elif normalized_type == "token":
                if not api_server_url or not token:
                    return {"services": [], "error": "API server URL and token required"}
                
                configuration, temp_ca_file = self._create_k8s_config(
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
                v1 = client.CoreV1Api(client.ApiClient(configuration))
            else:
                return {"services": [], "error": f"Unknown connection type: {normalized_type}"}
            
            # Run sync K8s call in executor to avoid blocking event loop
            def _fetch_services():
                if namespace:
                    return v1.list_namespaced_service(namespace, timeout_seconds=self.timeout)
                else:
                    return v1.list_service_for_all_namespaces(timeout_seconds=self.timeout)
            
            loop = asyncio.get_event_loop()
            services = await loop.run_in_executor(None, _fetch_services)
            
            svc_list = []
            for svc in services.items:
                ports = []
                if svc.spec.ports:
                    for p in svc.spec.ports:
                        ports.append({
                            "port": p.port,
                            "protocol": p.protocol,
                            "target_port": str(p.target_port) if p.target_port else None
                        })
                
                svc_list.append({
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "uid": svc.metadata.uid,
                    "type": svc.spec.type if svc.spec else "ClusterIP",
                    "cluster_ip": svc.spec.cluster_ip if svc.spec else None,
                    "ports": ports,
                    "labels": svc.metadata.labels or {},
                    "selector": svc.spec.selector or {} if svc.spec else {},
                    "created_at": svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else None
                })
            
            logger.info("Retrieved services from cluster", count=len(svc_list), namespace=namespace)
            return {"services": svc_list, "error": None}
            
        except Exception as e:
            logger.error("Failed to get services", error=str(e))
            return {"services": [], "error": str(e)}
        finally:
            self._cleanup_temp_file(temp_ca_file)
            self._cleanup_temp_file(kubeconfig_path)

    async def check_gadget_health_remote(
        self,
        gadget_endpoint: str,
        timeout: float = 10.0
    ) -> Dict:
        """
        Check Inspector Gadget health for REMOTE clusters via TCP socket.
        
        Inspector Gadget uses gRPC (not HTTP), so we perform a TCP connection
        check to verify the endpoint is reachable and accepting connections.
        
        Args:
            gadget_endpoint: gRPC endpoint (e.g., 10.0.0.1:16060 or host:16060)
            timeout: Connection timeout in seconds
            
        Returns:
            {
                "health_status": "healthy" | "unhealthy" | "unknown",
                "reachable": bool,
                "error": str | None,
                "details": dict
            }
        """
        import socket
        import asyncio
        
        try:
            # Normalize endpoint - remove http:// prefix if present (gRPC doesn't use HTTP URLs)
            endpoint = gadget_endpoint
            if endpoint.startswith('http://'):
                endpoint = endpoint[7:]
            elif endpoint.startswith('https://'):
                endpoint = endpoint[8:]
            endpoint = endpoint.rstrip('/')
            
            # Parse host:port
            if ':' in endpoint:
                host, port_str = endpoint.rsplit(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    port = 16060
            else:
                host = endpoint
                port = 16060
            
            logger.info("Checking remote gadget health via TCP", host=host, port=port)
            
            # Perform async TCP connection check
            reachable = False
            details = {}
            
            try:
                # Use asyncio to create a non-blocking socket connection
                loop = asyncio.get_event_loop()
                
                def _check_socket():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(timeout)
                    try:
                        result = sock.connect_ex((host, port))
                        return result == 0
                    finally:
                        sock.close()
                
                reachable = await loop.run_in_executor(None, _check_socket)
                
                if reachable:
                    details["tcp_check"] = {
                        "reachable": True,
                        "host": host,
                        "port": port,
                        "protocol": "gRPC"
                    }
                else:
                    details["tcp_check"] = {
                        "reachable": False,
                        "error": f"Connection refused to {host}:{port}"
                    }
                    
            except socket.timeout:
                details["tcp_check"] = {"reachable": False, "error": "Connection timeout"}
            except socket.gaierror as e:
                details["tcp_check"] = {"reachable": False, "error": f"DNS resolution failed: {e}"}
            except Exception as e:
                details["tcp_check"] = {"reachable": False, "error": str(e)}
            
            if reachable:
                return {
                    "health_status": "healthy",
                    "reachable": True,
                    "error": None,
                    "endpoint": endpoint,
                    "details": details
                }
            else:
                # Build detailed error message
                error_details = []
                for check, result in details.items():
                    if not result.get("reachable"):
                        error_details.append(f"{check}: {result.get('error', 'unreachable')}")
                
                error_msg = f"Inspector Gadget endpoint is not reachable at {endpoint}"
                if error_details:
                    error_msg += f" ({'; '.join(error_details)})"
                
                return {
                    "health_status": "unhealthy",
                    "reachable": False,
                    "error": error_msg,
                    "endpoint": endpoint,
                    "details": details
                }
                    
        except Exception as e:
            logger.error("Remote gadget health check failed", endpoint=gadget_endpoint, error=str(e))
            return {
                "health_status": "unknown",
                "reachable": False,
                "error": f"Health check failed: {str(e)}",
                "endpoint": gadget_endpoint,
                "details": {}
            }


# Singleton instance
cluster_info_service = ClusterInfoService()
