"""
Cluster Validation Logic
Validates cluster connection and Inspector Gadget availability
"""

import logging
import httpx
import yaml
import base64
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.config import ConfigException
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class ClusterValidator:
    """
    Validates Kubernetes cluster and Inspector Gadget
    
    Responsibilities:
    - Test Kubernetes API connectivity
    - Verify authentication and authorization
    - Check required permissions
    - Detect Inspector Gadget (REQUIRED)
    - Test Gadget health and capabilities
    - Gather cluster statistics
    """
    
    def __init__(self):
        self.timeout = 10.0  # seconds
        logger.info("ClusterValidator initialized")
    
    async def validate_cluster(
        self,
        api_server_url: str,
        connection_type: str = "kubeconfig",
        kubeconfig: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False,
        gadget_namespace: Optional[str] = None,  # REQUIRED from UI
        gadget_endpoint: Optional[str] = None,  # Deprecated
        gadget_auto_detect: bool = True
    ) -> Dict[str, Any]:
        """
        Run full cluster validation
        
        Args:
            api_server_url: Kubernetes API server URL
            connection_type: in-cluster, kubeconfig, service-account
            kubeconfig: Kubeconfig YAML content (for kubeconfig type)
            token: Service account token (for service-account type)
            ca_cert: CA certificate (for service-account type)
            skip_tls_verify: Skip TLS verification (NOT recommended for production)
            gadget_endpoint: Manual Inspector Gadget endpoint (optional)
            gadget_auto_detect: Auto-detect Gadget if endpoint not provided
        
        Returns:
            {
                "overall_status": "success" | "warning" | "error",
                "checks": [...],
                "warnings": [...],
                "errors": [],
                "cluster_info": {...},
                "gadget_info": {...}
            }
        """
        logger.info(f"Starting cluster validation for {api_server_url}")
        
        results = {
            "overall_status": "success",
            "checks": [],
            "warnings": [],
            "errors": [],
            "cluster_info": {},
            "gadget_info": None
        }
        
        # 1. Kubernetes API Reachability
        logger.info("Check 1/7: API Reachability")
        api_check, k8s_client = await self._check_api_reachability(
            api_server_url, connection_type, kubeconfig, token, ca_cert, skip_tls_verify
        )
        results["checks"].append(api_check)
        
        if api_check["status"] != "passed":
            results["overall_status"] = "error"
            results["errors"].append(api_check["message"])
            logger.error(f"API reachability failed: {api_check['message']}")
            return results
        
        # 2. Authentication & Authorization
        logger.info("Check 2/7: Authentication")
        auth_check = await self._check_authentication(k8s_client)
        results["checks"].append(auth_check)
        
        if auth_check["status"] != "passed":
            results["overall_status"] = "error"
            results["errors"].append(auth_check["message"])
            logger.error(f"Authentication failed: {auth_check['message']}")
            return results
        
        # 3. Required Permissions
        logger.info("Check 3/7: Required Permissions")
        perm_check = await self._check_permissions(k8s_client)
        results["checks"].append(perm_check)
        
        if perm_check["status"] == "failed":
            results["overall_status"] = "error"
            results["errors"].append(perm_check["message"])
        elif perm_check["status"] == "warning":
            results["warnings"].append(perm_check["message"])
            if results["overall_status"] == "success":
                results["overall_status"] = "warning"
        
        # 4. Inspector Gadget Detection (CRITICAL!)
        logger.info("Check 4/7: Inspector Gadget Detection (CRITICAL)")
        if gadget_namespace:
            # Namespace provided from UI - check directly in that namespace
            gadget_check = await self._detect_inspector_gadget(k8s_client, gadget_namespace)
        elif gadget_auto_detect and not gadget_endpoint:
            # Auto-detect in common namespaces
            gadget_check = await self._detect_inspector_gadget(k8s_client)
        else:
            # Manual endpoint provided (deprecated path)
            gadget_check = await self._validate_manual_gadget_endpoint(gadget_endpoint)
        
        results["checks"].append(gadget_check)
        
        if gadget_check["status"] == "failed":
            results["overall_status"] = "error"
            results["errors"].append(gadget_check["message"])
            results["errors"].append("⚠️  Inspector Gadget is REQUIRED for Flowfish")
            logger.error("Inspector Gadget not found - BLOCKING cluster addition")
            return results
        elif gadget_check["status"] == "warning":
            results["warnings"].append(gadget_check["message"])
            if results["overall_status"] == "success":
                results["overall_status"] = "warning"
        
        # Store Gadget info
        if "details" in gadget_check:
            results["gadget_info"] = gadget_check["details"]
        
        # 5. Inspector Gadget Health Check
        logger.info("Check 5/7: Inspector Gadget Health")
        if results["gadget_info"]:
            gadget_endpoint = results["gadget_info"].get("endpoint")
            health_check = await self._test_gadget_health(gadget_endpoint)
            results["checks"].append(health_check)
            
            if health_check["status"] == "warning":
                results["warnings"].append(health_check["message"])
                if results["overall_status"] == "success":
                    results["overall_status"] = "warning"
            
            # Update gadget_info with health results
            if "details" in health_check:
                results["gadget_info"].update(health_check["details"])
        
        # 6. Gather cluster statistics
        logger.info("Check 6/7: Gathering Cluster Statistics")
        stats_check = await self._gather_cluster_stats(k8s_client)
        results["checks"].append(stats_check)
        
        if "details" in stats_check:
            results["cluster_info"] = stats_check["details"]
        
        # 7. Version Compatibility Check
        logger.info("Check 7/7: Version Compatibility")
        version_check = await self._check_version_compatibility(
            results["cluster_info"].get("k8s_version"),
            results["gadget_info"].get("version") if results["gadget_info"] else None
        )
        results["checks"].append(version_check)
        
        if version_check["status"] == "warning":
            results["warnings"].append(version_check["message"])
            if results["overall_status"] == "success":
                results["overall_status"] = "warning"
        
        logger.info(f"Validation complete: {results['overall_status']}")
        return results
    
    async def _check_api_reachability(
        self, api_server_url, connection_type, kubeconfig, token, ca_cert, skip_tls_verify
    ):
        """Check if Kubernetes API is reachable"""
        try:
            k8s_client = self._get_k8s_client(
                connection_type, kubeconfig, token, ca_cert, skip_tls_verify
            )
            
            # Test connection with version API
            version_api = client.VersionApi(k8s_client)
            version_info = version_api.get_code()
            
            return {
                "name": "api_reachability",
                "status": "passed",
                "message": f"Kubernetes API is reachable (v{version_info.git_version})",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "version": version_info.git_version,
                    "platform": version_info.platform
                }
            }, k8s_client
            
        except ConfigException as e:
            return {
                "name": "api_reachability",
                "status": "failed",
                "message": f"Invalid kubeconfig: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }, None
        except ApiException as e:
            return {
                "name": "api_reachability",
                "status": "failed",
                "message": f"Kubernetes API error: {e.reason}",
                "timestamp": datetime.utcnow().isoformat()
            }, None
        except Exception as e:
            return {
                "name": "api_reachability",
                "status": "failed",
                "message": f"Cannot reach Kubernetes API: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }, None
    
    async def _check_authentication(self, k8s_client) -> Dict:
        """Check if authentication is valid"""
        try:
            # Try to list namespaces as auth test
            v1 = client.CoreV1Api(k8s_client)
            namespaces = v1.list_namespace(limit=1)
            
            return {
                "name": "authentication",
                "status": "passed",
                "message": "Authentication successful",
                "timestamp": datetime.utcnow().isoformat()
            }
        except ApiException as e:
            if e.status == 401:
                return {
                    "name": "authentication",
                    "status": "failed",
                    "message": "Authentication failed: Invalid credentials",
                    "timestamp": datetime.utcnow().isoformat()
                }
            elif e.status == 403:
                return {
                    "name": "authentication",
                    "status": "failed",
                    "message": "Authentication failed: Forbidden (check RBAC permissions)",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "name": "authentication",
                    "status": "failed",
                    "message": f"Authentication error: {e.reason}",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "name": "authentication",
                "status": "failed",
                "message": f"Authentication test failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _check_permissions(self, k8s_client) -> Dict:
        """Check required permissions"""
        required_permissions = [
            ("list", "namespaces", ""),
            ("list", "pods", ""),
            ("list", "services", ""),
            ("list", "deployments", "apps"),
            ("list", "nodes", "")
        ]
        
        auth_api = client.AuthorizationV1Api(k8s_client)
        missing_permissions = []
        
        try:
            for verb, resource, api_group in required_permissions:
                # Create SelfSubjectAccessReview
                body = client.V1SelfSubjectAccessReview(
                    spec=client.V1SelfSubjectAccessReviewSpec(
                        resource_attributes=client.V1ResourceAttributes(
                            verb=verb,
                            resource=resource,
                            group=api_group
                        )
                    )
                )
                
                try:
                    result = auth_api.create_self_subject_access_review(body)
                    if not result.status.allowed:
                        missing_permissions.append(f"{verb} {resource}")
                except:
                    # Ignore individual check failures
                    pass
            
            if missing_permissions:
                return {
                    "name": "permissions",
                    "status": "warning",
                    "message": f"Some permissions missing: {', '.join(missing_permissions)}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": {
                        "missing": missing_permissions
                    }
                }
            else:
                return {
                    "name": "permissions",
                    "status": "passed",
                    "message": "All required permissions are available",
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        except Exception as e:
            logger.warning(f"Permission check failed: {e}")
            return {
                "name": "permissions",
                "status": "warning",
                "message": "Could not verify all permissions (may work anyway)",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _detect_inspector_gadget(self, k8s_client, provided_namespace: Optional[str] = None) -> Dict:
        """
        Detect Inspector Gadget DaemonSet and endpoint
        
        Args:
            k8s_client: Kubernetes client
            provided_namespace: If provided from UI, only search in this namespace
        
        Strategy:
        1. If namespace provided, search only there
        2. Otherwise search for DaemonSet named "gadget" or "inspektor-gadget" in common namespaces
        3. Look for Service with label "app=inspektor-gadget"
        4. Construct endpoint and test health
        """
        try:
            apps_v1 = client.AppsV1Api(k8s_client)
            core_v1 = client.CoreV1Api(k8s_client)
            
            # Search namespaces - use provided namespace if given, otherwise search common ones
            if provided_namespace:
                search_namespaces = [provided_namespace]
                logger.info(f"Searching for Inspector Gadget in provided namespace: {provided_namespace}")
            else:
                search_namespaces = ["flowfish", "kube-system", "gadget", "inspektor-gadget", "monitoring"]
                logger.info(f"Auto-detecting Inspector Gadget in namespaces: {search_namespaces}")
            
            gadget_found = False
            gadget_namespace = None
            gadget_daemonset = None
            gadget_service = None
            
            for ns in search_namespaces:
                try:
                    # Check if namespace exists
                    core_v1.read_namespace(ns)
                    
                    # Search for DaemonSet
                    daemonsets = apps_v1.list_namespaced_daemon_set(ns)
                    for ds in daemonsets.items:
                        if "gadget" in ds.metadata.name.lower():
                            gadget_found = True
                            gadget_namespace = ns
                            gadget_daemonset = ds.metadata.name
                            logger.info(f"Found Gadget DaemonSet: {gadget_daemonset} in {gadget_namespace}")
                            break
                    
                    if gadget_found:
                        # Now find Service
                        try:
                            services = core_v1.list_namespaced_service(gadget_namespace)
                            for svc in services.items:
                                if "gadget" in svc.metadata.name.lower():
                                    gadget_service = svc.metadata.name
                                    logger.info(f"Found Gadget Service: {gadget_service}")
                                    break
                        except:
                            pass
                        break
                    
                except ApiException as e:
                    if e.status != 404:  # Namespace not found is OK
                        logger.debug(f"Error checking namespace {ns}: {e}")
                    continue
            
            if not gadget_found:
                return {
                    "name": "inspector_gadget",
                    "status": "failed",
                    "message": "❌ Inspector Gadget DaemonSet not found in cluster",
                    "timestamp": datetime.utcnow().isoformat(),
                    "help": "Install Inspector Gadget: kubectl gadget deploy"
                }
            
            # Construct endpoint (gRPC - no http:// prefix)
            if gadget_service:
                gadget_endpoint = f"{gadget_service}.{gadget_namespace}:16060"
            else:
                # Fallback: try common service names
                gadget_endpoint = f"inspektor-gadget.{gadget_namespace}:16060"
            
            logger.info(f"Constructed Gadget endpoint: {gadget_endpoint}")
            
            return {
                "name": "inspector_gadget",
                "status": "passed",
                "message": f"✅ Inspector Gadget found in {gadget_namespace}",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "namespace": gadget_namespace,
                    "daemonset": gadget_daemonset,
                    "service": gadget_service,
                    "endpoint": gadget_endpoint,
                    "auto_detected": True
                }
            }
        
        except Exception as e:
            logger.error(f"Gadget detection failed: {e}", exc_info=True)
            return {
                "name": "inspector_gadget",
                "status": "failed",
                "message": f"❌ Failed to detect Inspector Gadget: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _validate_manual_gadget_endpoint(self, endpoint: str) -> Dict:
        """Validate manually provided Gadget endpoint"""
        if not endpoint:
            return {
                "name": "inspector_gadget",
                "status": "failed",
                "message": "❌ Gadget endpoint not provided",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "name": "inspector_gadget",
            "status": "passed",
            "message": f"✅ Using manual Gadget endpoint",
            "timestamp": datetime.utcnow().isoformat(),
            "details": {
                "endpoint": endpoint,
                "auto_detected": False
            }
        }
    
    async def _test_gadget_health(self, endpoint: str) -> Dict:
        """Test Inspector Gadget health endpoint"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{endpoint}/health")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        version = data.get("version", "unknown")
                        capabilities = data.get("capabilities", [])
                        
                        # Check if network gadget is available (minimum requirement)
                        if "network" not in capabilities:
                            return {
                                "name": "gadget_health",
                                "status": "warning",
                                "message": "⚠️  Inspector Gadget healthy but 'network' gadget not available",
                                "timestamp": datetime.utcnow().isoformat(),
                                "details": {
                                    "healthy": True,
                                    "version": version,
                                    "capabilities": capabilities
                                }
                            }
                        
                        return {
                            "name": "gadget_health",
                            "status": "passed",
                            "message": f"✅ Inspector Gadget healthy (v{version})",
                            "timestamp": datetime.utcnow().isoformat(),
                            "details": {
                                "healthy": True,
                                "version": version,
                                "capabilities": capabilities,
                                "health_status": "healthy"
                            }
                        }
                    except:
                        # Health endpoint returned 200 but no JSON
                        return {
                            "name": "gadget_health",
                            "status": "passed",
                            "message": "✅ Inspector Gadget is reachable",
                            "timestamp": datetime.utcnow().isoformat(),
                            "details": {
                                "healthy": True,
                                "health_status": "healthy"
                            }
                        }
                else:
                    return {
                        "name": "gadget_health",
                        "status": "warning",
                        "message": f"⚠️  Inspector Gadget health check returned HTTP {response.status_code}",
                        "timestamp": datetime.utcnow().isoformat(),
                        "details": {
                            "healthy": False,
                            "health_status": "degraded"
                        }
                    }
        except httpx.TimeoutException:
            return {
                "name": "gadget_health",
                "status": "warning",
                "message": "⚠️  Inspector Gadget health check timeout (may be slow)",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "healthy": False,
                    "health_status": "unavailable"
                }
            }
        except Exception as e:
            return {
                "name": "gadget_health",
                "status": "warning",
                "message": f"⚠️  Inspector Gadget health check failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "healthy": False,
                    "health_status": "unavailable"
                }
            }
    
    async def _gather_cluster_stats(self, k8s_client) -> Dict:
        """Gather cluster statistics"""
        try:
            v1 = client.CoreV1Api(k8s_client)
            apps_v1 = client.AppsV1Api(k8s_client)
            version_api = client.VersionApi(k8s_client)
            
            # Get counts
            namespaces = v1.list_namespace()
            pods = v1.list_pod_for_all_namespaces(limit=10000)  # Get all pods
            nodes = v1.list_node()
            version_info = version_api.get_code()
            
            return {
                "name": "cluster_statistics",
                "status": "passed",
                "message": f"✅ Cluster stats gathered: {len(namespaces.items)} namespaces, {len(pods.items)} pods",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "total_namespaces": len(namespaces.items),
                    "total_pods": len(pods.items),
                    "total_nodes": len(nodes.items),
                    "k8s_version": version_info.git_version
                }
            }
        except Exception as e:
            logger.warning(f"Failed to gather cluster stats: {e}")
            return {
                "name": "cluster_statistics",
                "status": "warning",
                "message": f"⚠️  Could not gather full cluster statistics: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {}
            }
    
    async def _check_version_compatibility(
        self, k8s_version: Optional[str], gadget_version: Optional[str]
    ) -> Dict:
        """Check version compatibility"""
        warnings = []
        
        # Check Kubernetes version
        if k8s_version:
            try:
                # Extract version number (e.g., "v1.28.3" -> 1.28)
                version_parts = k8s_version.lstrip('v').split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1])
                
                if major < 1 or (major == 1 and minor < 24):
                    warnings.append(f"Kubernetes {k8s_version} is old (recommend >= v1.24)")
            except:
                pass
        
        # Check Gadget version
        if gadget_version:
            try:
                # Extract version (e.g., "v0.19.0" -> 0.19)
                version_parts = gadget_version.lstrip('v').split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1])
                
                if major == 0 and minor < 46:
                    warnings.append(f"Inspector Gadget {gadget_version} is below minimum supported version (requires >= v0.46.0)")
            except:
                pass
        
        if warnings:
            return {
                "name": "version_compatibility",
                "status": "warning",
                "message": f"⚠️  Version warnings: {'; '.join(warnings)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "name": "version_compatibility",
                "status": "passed",
                "message": "✅ Versions are compatible",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _get_k8s_client(
        self, connection_type, kubeconfig_content, token, ca_cert, skip_tls_verify
    ):
        """Get Kubernetes client based on connection type"""
        if connection_type == "in-cluster":
            # Load in-cluster config
            config.load_incluster_config()
            return client.ApiClient()
        
        elif connection_type == "kubeconfig":
            # Load from kubeconfig content
            if not kubeconfig_content:
                raise ValueError("Kubeconfig content is required for kubeconfig connection type")
            
            # Parse kubeconfig YAML
            kubeconfig_dict = yaml.safe_load(kubeconfig_content)
            
            # Load configuration from dict
            k8s_client = config.new_client_from_config_dict(kubeconfig_dict)
            return k8s_client
        
        elif connection_type == "service-account":
            # Load from token and CA cert
            if not token:
                raise ValueError("Token is required for service-account connection type")
            
            configuration = client.Configuration()
            configuration.api_key = {"authorization": f"Bearer {token}"}
            
            if ca_cert:
                # Write CA cert to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.crt') as f:
                    f.write(ca_cert)
                    configuration.ssl_ca_cert = f.name
            
            if skip_tls_verify:
                configuration.verify_ssl = False
            
            return client.ApiClient(configuration)
        
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")


# Singleton instance
_cluster_validator: Optional[ClusterValidator] = None


def get_cluster_validator() -> ClusterValidator:
    """Get or create global ClusterValidator instance"""
    global _cluster_validator
    if _cluster_validator is None:
        _cluster_validator = ClusterValidator()
    return _cluster_validator

