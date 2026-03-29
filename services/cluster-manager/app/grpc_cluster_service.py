"""
gRPC Cluster Service Implementation
Handles cluster management operations with validation
"""

import logging
import json
from typing import Dict, Any
from datetime import datetime

# Proto imports (will be generated)
# from proto import cluster_manager_pb2, cluster_manager_pb2_grpc

from app.database import db_manager
from app.cluster_validator import get_cluster_validator
from app.config import settings

logger = logging.getLogger(__name__)


class ClusterManagerService:
    """
    gRPC service implementation for cluster management
    
    Implements:
    - CreateCluster (with validation)
    - ValidateCluster
    - TestConnection
    - DetectGadget
    - ListClusters, GetCluster, UpdateCluster, DeleteCluster
    """
    
    def __init__(self):
        self.validator = get_cluster_validator()
        logger.info("ClusterManagerService initialized")
    
    async def ValidateCluster(self, request, context):
        """
        Validate cluster connection and Inspector Gadget
        
        This is called during the "Add Cluster" wizard to validate
        configuration before actually creating the cluster record.
        """
        logger.info(f"ValidateCluster called for {request.api_server_url}")
        
        try:
            # Run validation
            validation_result = await self.validator.validate_cluster(
                api_server_url=request.api_server_url,
                connection_type=request.connection_type,
                kubeconfig=request.kubeconfig,
                token=request.token,
                ca_cert=request.ca_cert,
                skip_tls_verify=request.skip_tls_verify,
                gadget_namespace=getattr(request, 'gadget_namespace', None),  # REQUIRED from UI
                gadget_endpoint=request.gadget_endpoint,  # Deprecated
                gadget_auto_detect=request.gadget_auto_detect
            )
            
            # Convert to proto response
            response = self._validation_result_to_proto(validation_result)
            
            logger.info(f"Validation complete: {validation_result['overall_status']}")
            return response
            
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Validation error: {str(e)}")
            return None
    
    async def CreateCluster(self, request, context):
        """
        Create a new cluster (after validation)
        
        Steps:
        1. Validate cluster (ensure Gadget is present)
        2. Encrypt sensitive data (kubeconfig, token, ca_cert)
        3. Insert into database
        4. Return cluster record
        """
        logger.info(f"CreateCluster called: {request.name}")
        
        try:
            # Step 1: Validate first
            logger.info("Step 1: Validating cluster configuration...")
            validation_result = await self.validator.validate_cluster(
                api_server_url=request.api_server_url,
                connection_type=request.connection_type,
                kubeconfig=request.kubeconfig,
                token=request.token,
                ca_cert=request.ca_cert,
                skip_tls_verify=request.skip_tls_verify,
                gadget_endpoint=request.gadget_endpoint,
                gadget_auto_detect=request.gadget_auto_detect
            )
            
            # Check if validation passed (or at least not error)
            if validation_result["overall_status"] == "error":
                logger.error("Validation failed - cannot create cluster")
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Validation failed: {', '.join(validation_result['errors'])}")
                return None
            
            # Step 2: Encrypt sensitive data
            logger.info("Step 2: Encrypting sensitive data...")
            kubeconfig_encrypted = self._encrypt(request.kubeconfig) if request.kubeconfig else None
            token_encrypted = self._encrypt(request.token) if request.token else None
            ca_cert_encrypted = self._encrypt(request.ca_cert) if request.ca_cert else None
            
            # Step 3: Prepare cluster data
            logger.info("Step 3: Preparing cluster data...")
            gadget_info = validation_result.get("gadget_info", {})
            cluster_info = validation_result.get("cluster_info", {})
            
            cluster_data = {
                "name": request.name,
                "description": request.description,
                "environment": request.environment,
                "provider": request.provider,
                "region": request.region,
                "tags": dict(request.tags) if request.tags else {},
                "connection_type": request.connection_type,
                "api_server_url": request.api_server_url,
                "kubeconfig_encrypted": kubeconfig_encrypted,
                "ca_cert_encrypted": ca_cert_encrypted,
                "token_encrypted": token_encrypted,
                "skip_tls_verify": request.skip_tls_verify,
                "gadget_endpoint": gadget_info.get("endpoint", request.gadget_endpoint),
                "gadget_auto_detect": request.gadget_auto_detect,
                "gadget_version": gadget_info.get("version"),
                "gadget_capabilities": gadget_info.get("capabilities", []),
                "gadget_health_status": gadget_info.get("health_status", "unknown"),
                "gadget_last_check": datetime.utcnow(),
                "status": "active" if validation_result["overall_status"] == "success" else "warning",
                "validation_status": validation_result,
                "last_sync": datetime.utcnow(),
                "total_namespaces": cluster_info.get("total_namespaces", 0),
                "total_pods": cluster_info.get("total_pods", 0),
                "total_nodes": cluster_info.get("total_nodes", 0),
                "k8s_version": cluster_info.get("k8s_version"),
                "created_by": request.created_by if request.created_by else None,
                "updated_by": request.created_by if request.created_by else None
            }
            
            # Step 4: Insert into database
            logger.info("Step 4: Inserting cluster into database...")
            cluster = await db_manager.create_cluster(cluster_data)
            
            logger.info(f"✅ Cluster created: {cluster.name} (ID: {cluster.id})")
            
            # Convert to proto
            return self._cluster_to_proto(cluster)
            
        except Exception as e:
            logger.error(f"CreateCluster failed: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create cluster: {str(e)}")
            return None
    
    async def GetCluster(self, request, context):
        """Get cluster by ID"""
        try:
            cluster = await db_manager.get_cluster(request.id)
            
            if not cluster:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Cluster {request.id} not found")
                return None
            
            return self._cluster_to_proto(cluster)
            
        except Exception as e:
            logger.error(f"GetCluster failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None
    
    async def ListClusters(self, request, context):
        """List all clusters"""
        try:
            # Extract pagination
            limit = request.pagination.limit if request.pagination else 50
            offset = request.pagination.offset if request.pagination else 0
            
            # Query clusters
            clusters, total = await db_manager.list_clusters(
                limit=limit,
                offset=offset,
                filter_query=request.filter if request.filter else None,
                active_only=request.active_only
            )
            
            # Convert to proto
            cluster_protos = [self._cluster_to_proto(c) for c in clusters]
            
            return {
                "clusters": cluster_protos,
                "total": total
            }
            
        except Exception as e:
            logger.error(f"ListClusters failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None
    
    async def UpdateCluster(self, request, context):
        """Update existing cluster"""
        try:
            # Get existing cluster
            cluster = await db_manager.get_cluster(request.id)
            if not cluster:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Cluster {request.id} not found")
                return None
            
            # Prepare update data
            update_data = {}
            if request.name:
                update_data["name"] = request.name
            if request.description:
                update_data["description"] = request.description
            if request.environment:
                update_data["environment"] = request.environment
            if request.provider:
                update_data["provider"] = request.provider
            if request.region:
                update_data["region"] = request.region
            
            # Update database
            updated_cluster = await db_manager.update_cluster(request.id, update_data)
            
            return self._cluster_to_proto(updated_cluster)
            
        except Exception as e:
            logger.error(f"UpdateCluster failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None
    
    async def DeleteCluster(self, request, context):
        """Delete cluster"""
        try:
            await db_manager.delete_cluster(request.id)
            logger.info(f"Cluster {request.id} deleted")
            return {}  # Empty response
            
        except Exception as e:
            logger.error(f"DeleteCluster failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None
    
    async def TestConnection(self, request, context):
        """Test cluster connection (quick check)"""
        try:
            if request.cluster_id:
                # Test existing cluster
                cluster = await db_manager.get_cluster(request.cluster_id)
                if not cluster:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    return None
                
                # Decrypt credentials
                kubeconfig = self._decrypt(cluster.kubeconfig_encrypted) if cluster.kubeconfig_encrypted else None
                token = self._decrypt(cluster.token_encrypted) if cluster.token_encrypted else None
                ca_cert = self._decrypt(cluster.ca_cert_encrypted) if cluster.ca_cert_encrypted else None
                
                # Test connection
                result = await self.validator._check_api_reachability(
                    cluster.api_server_url,
                    cluster.connection_type,
                    kubeconfig,
                    token,
                    ca_cert,
                    cluster.skip_tls_verify
                )
            else:
                # Test new connection details
                result = await self.validator._check_api_reachability(
                    request.api_server_url,
                    request.connection_type,
                    request.kubeconfig,
                    request.token,
                    request.ca_cert,
                    request.skip_tls_verify
                )
            
            check_result, _ = result
            
            return {
                "success": check_result["status"] == "passed",
                "message": check_result["message"],
                "error": check_result.get("error", ""),
                "cluster_info": check_result.get("details", {})
            }
            
        except Exception as e:
            logger.error(f"TestConnection failed: {e}")
            return {
                "success": False,
                "message": "Connection test failed",
                "error": str(e)
            }
    
    async def DetectGadget(self, request, context):
        """Detect Inspector Gadget in cluster"""
        try:
            if request.cluster_id:
                # Detect in existing cluster
                cluster = await db_manager.get_cluster(request.cluster_id)
                if not cluster:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    return None
                
                # Get K8s client and detect
                # ... implementation similar to TestConnection
                pass
            else:
                # Detect using provided connection details
                pass
            
            # TODO: Implementation
            return {
                "found": False,
                "message": "Not implemented yet",
                "installation_help": "kubectl gadget deploy"
            }
            
        except Exception as e:
            logger.error(f"DetectGadget failed: {e}")
            return {
                "found": False,
                "message": "Detection failed",
                "error": str(e)
            }
    
    # Helper methods
    
    def _validation_result_to_proto(self, result: Dict) -> Dict:
        """Convert validation result to proto format"""
        checks_proto = []
        for check in result.get("checks", []):
            checks_proto.append({
                "name": check.get("name"),
                "status": check.get("status"),
                "message": check.get("message"),
                "timestamp": check.get("timestamp"),
                "details_json": json.dumps(check.get("details", {}))
            })
        
        cluster_info = result.get("cluster_info", {})
        gadget_info = result.get("gadget_info", {})
        
        return {
            "overall_status": result.get("overall_status"),
            "checks": checks_proto,
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "cluster_info": {
                "total_namespaces": cluster_info.get("total_namespaces", 0),
                "total_pods": cluster_info.get("total_pods", 0),
                "total_nodes": cluster_info.get("total_nodes", 0),
                "k8s_version": cluster_info.get("k8s_version", "")
            },
            "gadget_info": {
                "endpoint": gadget_info.get("endpoint", ""),
                "version": gadget_info.get("version", ""),
                "capabilities": gadget_info.get("capabilities", []),
                "health_status": gadget_info.get("health_status", "unknown"),
                "namespace": gadget_info.get("namespace", ""),
                "daemonset": gadget_info.get("daemonset", ""),
                "service": gadget_info.get("service", ""),
                "auto_detected": gadget_info.get("auto_detected", False)
            } if gadget_info else None
        }
    
    def _cluster_to_proto(self, cluster) -> Dict:
        """Convert database cluster to proto format"""
        return {
            "id": cluster.id,
            "name": cluster.name,
            "description": cluster.description,
            "environment": cluster.environment,
            "provider": cluster.provider,
            "region": cluster.region,
            "tags": cluster.tags or {},
            "connection_type": cluster.connection_type,
            "api_server_url": cluster.api_server_url,
            # Don't return encrypted credentials in proto
            "skip_tls_verify": cluster.skip_tls_verify,
            "gadget_endpoint": cluster.gadget_endpoint,
            "gadget_auto_detect": cluster.gadget_auto_detect,
            "gadget_version": cluster.gadget_version,
            "gadget_capabilities": cluster.gadget_capabilities or [],
            "gadget_health_status": cluster.gadget_health_status,
            "gadget_last_check": cluster.gadget_last_check.isoformat() if cluster.gadget_last_check else None,
            "status": cluster.status,
            "validation_status_json": json.dumps(cluster.validation_status) if cluster.validation_status else "{}",
            "last_sync": cluster.last_sync.isoformat() if cluster.last_sync else None,
            "error_message": cluster.error_message,
            "total_namespaces": cluster.total_namespaces,
            "total_pods": cluster.total_pods,
            "total_nodes": cluster.total_nodes,
            "k8s_version": cluster.k8s_version,
            "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
            "updated_at": cluster.updated_at.isoformat() if cluster.updated_at else None,
            "created_by": cluster.created_by,
            "updated_by": cluster.updated_by
        }
    
    def _encrypt(self, plaintext: str) -> str:
        """Encrypt sensitive data using Fernet (AES-128-CBC)"""
        import os
        try:
            from cryptography.fernet import Fernet
            key = os.environ.get("FLOWFISH_ENCRYPTION_KEY", "")
            if not key:
                logger.warning("FLOWFISH_ENCRYPTION_KEY not set, storing as base64 (not secure)")
                import base64
                return base64.b64encode(plaintext.encode()).decode()
            f = Fernet(key.encode() if isinstance(key, str) else key)
            return f.encrypt(plaintext.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt Fernet-encrypted data with backward compatibility"""
        import os
        if not ciphertext:
            return ""
        
        try:
            from cryptography.fernet import Fernet
            key = os.environ.get("FLOWFISH_ENCRYPTION_KEY", "")
            
            # Check if value looks like Fernet encrypted (starts with 'gAAAAA')
            if key and ciphertext.startswith('gAAAAA'):
                f = Fernet(key.encode() if isinstance(key, str) else key)
                return f.decrypt(ciphertext.encode()).decode()
            
            # Fall back to base64 for legacy data
            import base64
            try:
                return base64.b64decode(ciphertext.encode()).decode()
            except Exception:
                # If base64 fails, return as-is (might be plain text)
                return ciphertext
        except Exception as e:
            logger.warning(f"Decryption failed, returning as-is: {e}")
            return ciphertext

