"""
Cluster Management API Endpoints
REST API for cluster CRUD and validation
"""

from fastapi import APIRouter, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.grpc_clients import get_cluster_manager_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["clusters"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ClusterCreate(BaseModel):
    name: str = Field(..., description="Cluster name", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="Cluster description")
    environment: str = Field(..., description="Environment: production, staging, development, testing")
    provider: str = Field(..., description="Provider: kubernetes, openshift, eks, aks, gke, on-premise")
    region: Optional[str] = Field(None, description="Region/datacenter")
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)
    
    # Connection
    connection_type: str = Field(..., description="Connection type: in-cluster, kubeconfig, service-account")
    api_server_url: str = Field(..., description="Kubernetes API server URL")
    kubeconfig: Optional[str] = Field(None, description="Kubeconfig YAML content")
    token: Optional[str] = Field(None, description="Service account token")
    ca_cert: Optional[str] = Field(None, description="CA certificate")
    skip_tls_verify: bool = Field(False, description="Skip TLS verification (not recommended)")
    
    # Inspector Gadget
    gadget_namespace: str = Field(..., description="Namespace where Inspector Gadget is deployed (REQUIRED)")
    gadget_auto_detect: bool = Field(True, description="Auto-detect Inspector Gadget")
    gadget_endpoint: Optional[str] = Field(None, description="Manual Gadget endpoint (deprecated)")


class ClusterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


class ClusterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    environment: str
    provider: str
    region: Optional[str]
    tags: Dict[str, str]
    
    connection_type: str
    api_server_url: str
    skip_tls_verify: bool
    
    gadget_namespace: str
    gadget_endpoint: Optional[str]  # Deprecated
    gadget_auto_detect: bool
    gadget_version: Optional[str]
    gadget_capabilities: List[str]
    gadget_health_status: str
    gadget_last_check: Optional[datetime]
    
    status: str
    validation_status_json: Optional[str]
    last_sync: Optional[datetime]
    error_message: Optional[str]
    
    total_namespaces: int
    total_pods: int
    total_nodes: int
    k8s_version: Optional[str]
    
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]


class ClusterListResponse(BaseModel):
    clusters: List[ClusterResponse]
    total: int


class ValidationRequest(BaseModel):
    api_server_url: str
    connection_type: str = "kubeconfig"
    kubeconfig: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None
    skip_tls_verify: bool = False
    gadget_namespace: str  # REQUIRED from UI
    gadget_auto_detect: bool = True
    gadget_endpoint: Optional[str] = None  # Deprecated


class ValidationCheck(BaseModel):
    name: str
    status: str  # passed, warning, failed
    message: str
    timestamp: str
    details_json: Optional[str]


class ClusterInfo(BaseModel):
    total_namespaces: int
    total_pods: int
    total_nodes: int
    k8s_version: str


class GadgetInfo(BaseModel):
    endpoint: str
    version: Optional[str]
    capabilities: List[str]
    health_status: str
    namespace: Optional[str]
    daemonset: Optional[str]
    service: Optional[str]
    auto_detected: bool


class ValidationResponse(BaseModel):
    overall_status: str  # success, warning, error
    checks: List[ValidationCheck]
    warnings: List[str]
    errors: List[str]
    cluster_info: Optional[ClusterInfo]
    gadget_info: Optional[GadgetInfo]


class TestConnectionRequest(BaseModel):
    cluster_id: Optional[int] = None
    api_server_url: Optional[str] = None
    connection_type: Optional[str] = None
    kubeconfig: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None
    skip_tls_verify: bool = False
    gadget_namespace: Optional[str] = None  # Required for new clusters


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    error: Optional[str]
    cluster_info: Optional[ClusterInfo]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("", response_model=ClusterResponse, status_code=status.HTTP_201_CREATED)
async def create_cluster(cluster: ClusterCreate):
    """
    Create a new cluster with validation
    
    This endpoint:
    1. Validates cluster connection
    2. Detects Inspector Gadget (REQUIRED)
    3. Creates cluster record if validation passes
    """
    logger.info(f"Creating cluster: {cluster.name}")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        # Create cluster via gRPC
        response = await cluster_manager.CreateCluster(
            name=cluster.name,
            description=cluster.description or "",
            environment=cluster.environment,
            provider=cluster.provider,
            region=cluster.region or "",
            tags=cluster.tags,
            connection_type=cluster.connection_type,
            api_server_url=cluster.api_server_url,
            kubeconfig=cluster.kubeconfig or "",
            token=cluster.token or "",
            ca_cert=cluster.ca_cert or "",
            skip_tls_verify=cluster.skip_tls_verify,
            gadget_namespace=cluster.gadget_namespace,  # REQUIRED from UI
            gadget_auto_detect=cluster.gadget_auto_detect,
            gadget_endpoint=cluster.gadget_endpoint or ""  # Deprecated
        )
        
        return ClusterResponse(**_proto_to_dict(response))
        
    except Exception as e:
        logger.error(f"Failed to create cluster: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create cluster: {str(e)}"
        )


@router.get("", response_model=ClusterListResponse)
async def list_clusters(
    limit: int = 50,
    offset: int = 0,
    filter: Optional[str] = None,
    active_only: bool = False
):
    """List all clusters"""
    logger.info(f"Listing clusters (limit={limit}, offset={offset})")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        response = await cluster_manager.ListClusters(
            pagination={"limit": limit, "offset": offset},
            filter=filter or "",
            active_only=active_only
        )
        
        clusters = [ClusterResponse(**_proto_to_dict(c)) for c in response.clusters]
        
        return ClusterListResponse(
            clusters=clusters,
            total=response.total
        )
        
    except Exception as e:
        logger.error(f"Failed to list clusters: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list clusters: {str(e)}"
        )


@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(cluster_id: int):
    """Get cluster by ID"""
    logger.info(f"Getting cluster: {cluster_id}")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        response = await cluster_manager.GetCluster(id=cluster_id)
        
        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        return ClusterResponse(**_proto_to_dict(response))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cluster: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cluster: {str(e)}"
        )


@router.put("/{cluster_id}", response_model=ClusterResponse)
async def update_cluster(cluster_id: int, cluster: ClusterUpdate):
    """Update cluster"""
    logger.info(f"Updating cluster: {cluster_id}")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        # Build update request
        update_data = cluster.dict(exclude_unset=True)
        
        response = await cluster_manager.UpdateCluster(
            id=cluster_id,
            **update_data
        )
        
        return ClusterResponse(**_proto_to_dict(response))
        
    except Exception as e:
        logger.error(f"Failed to update cluster: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cluster: {str(e)}"
        )


@router.delete("/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cluster(cluster_id: int):
    """Delete cluster"""
    logger.info(f"Deleting cluster: {cluster_id}")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        await cluster_manager.DeleteCluster(id=cluster_id)
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to delete cluster: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete cluster: {str(e)}"
        )


@router.post("/validate", response_model=ValidationResponse)
async def validate_cluster(request: ValidationRequest):
    """
    Validate cluster configuration before creating
    
    This endpoint validates:
    - Kubernetes API connectivity
    - Authentication
    - Permissions
    - Inspector Gadget detection (CRITICAL)
    - Gadget health check
    """
    logger.info(f"Validating cluster: {request.api_server_url}")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        response = await cluster_manager.ValidateCluster(
            api_server_url=request.api_server_url,
            connection_type=request.connection_type,
            kubeconfig=request.kubeconfig or "",
            token=request.token or "",
            ca_cert=request.ca_cert or "",
            skip_tls_verify=request.skip_tls_verify,
            gadget_namespace=request.gadget_namespace,  # REQUIRED from UI
            gadget_auto_detect=request.gadget_auto_detect,
            gadget_endpoint=request.gadget_endpoint or ""  # Deprecated
        )
        
        return ValidationResponse(**_proto_to_dict(response))
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest):
    """Test cluster connection (quick check)"""
    logger.info("Testing cluster connection")
    
    try:
        cluster_manager = get_cluster_manager_client()
        
        response = await cluster_manager.TestConnection(
            cluster_id=request.cluster_id or 0,
            api_server_url=request.api_server_url or "",
            connection_type=request.connection_type or "",
            kubeconfig=request.kubeconfig or "",
            token=request.token or "",
            ca_cert=request.ca_cert or "",
            skip_tls_verify=request.skip_tls_verify
        )
        
        return TestConnectionResponse(**_proto_to_dict(response))
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return TestConnectionResponse(
            success=False,
            message="Connection test failed",
            error=str(e)
        )


@router.post("/upload-kubeconfig")
async def upload_kubeconfig(file: UploadFile = File(...)):
    """
    Upload kubeconfig file
    
    Returns the kubeconfig content as a string
    """
    try:
        contents = await file.read()
        kubeconfig = contents.decode('utf-8')
        
        return {
            "success": True,
            "filename": file.filename,
            "kubeconfig": kubeconfig
        }
        
    except Exception as e:
        logger.error(f"Failed to upload kubeconfig: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid kubeconfig file: {str(e)}"
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _proto_to_dict(proto_obj) -> Dict[str, Any]:
    """Convert proto object to dict"""
    # This is a placeholder - actual implementation depends on proto library
    # For now, assume proto has a dict-like interface
    result = {}
    
    for field in proto_obj.DESCRIPTOR.fields:
        value = getattr(proto_obj, field.name)
        
        # Convert timestamps
        if hasattr(value, 'ToDatetime'):
            result[field.name] = value.ToDatetime()
        else:
            result[field.name] = value
    
    return result
