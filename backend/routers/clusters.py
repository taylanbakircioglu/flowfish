"""
Clusters router - Simplified for MVP
"""

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import structlog
import asyncio

from database.postgresql import database
from services.cluster_cache_service import cluster_cache_service
from services.cluster_connection_manager import cluster_connection_manager
from utils.encryption import encrypt_data

logger = structlog.get_logger()

router = APIRouter()

# Path to kubernetes manifests
MANIFESTS_PATH = Path(__file__).parent.parent.parent / "deployment" / "kubernetes-manifests"

# Pydantic schemas
class ClusterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    environment: Optional[str] = "production"
    provider: Optional[str] = "kubernetes"
    region: Optional[str] = "default"
    connection_type: str  # 'in-cluster', 'kubeconfig', 'token'
    api_server_url: Optional[str] = None
    kubeconfig: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None
    gadget_namespace: str  # Namespace where gadget is deployed (REQUIRED from UI)
    gadget_endpoint: Optional[str] = None  # Deprecated - not used anymore
    skip_tls_verify: Optional[bool] = False

class ClusterUpdate(BaseModel):
    """
    Schema for updating cluster configuration.
    All fields are optional - only provided fields will be updated.
    Sensitive fields (token, kubeconfig, ca_cert) are only updated if explicitly provided.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None  # production, staging, development
    provider: Optional[str] = None  # kubernetes, openshift, eks, gke, aks
    region: Optional[str] = None
    api_server_url: Optional[str] = None
    gadget_namespace: Optional[str] = None  # Namespace where gadget is deployed
    status: Optional[str] = None  # 'active', 'inactive', 'maintenance'
    skip_tls_verify: Optional[bool] = None
    # Sensitive fields - only update if explicitly provided (not empty string)
    token: Optional[str] = None
    kubeconfig: Optional[str] = None
    ca_cert: Optional[str] = None

class ClusterResponse(BaseModel):
    id: int
    name: str = "unnamed"
    description: Optional[str] = None
    environment: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    connection_type: Optional[str] = None
    api_server_url: Optional[str] = None
    gadget_namespace: Optional[str] = None
    gadget_endpoint: Optional[str] = None  # Deprecated
    gadget_health_status: Optional[str] = None
    gadget_version: Optional[str] = None
    status: Optional[str] = None
    total_nodes: Optional[int] = None
    total_pods: Optional[int] = None
    total_namespaces: Optional[int] = None
    k8s_version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@router.get("/clusters")
async def get_clusters(is_active: Optional[bool] = None):
    """Get list of clusters"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_namespace, gadget_endpoint,
               gadget_health_status, gadget_version, status,
               total_nodes, total_pods, total_namespaces,
               k8s_version, created_at, updated_at
        FROM clusters
        WHERE status != 'deleted'
        """
        
        params = {}
        
        if is_active is not None:
            query += " AND status = 'active'"
        
        query += " ORDER BY created_at DESC"
        
        clusters = await database.fetch_all(query, params)
        
        logger.info("Retrieved clusters", count=len(clusters))
        
        return {
            "clusters": [dict(cluster) for cluster in clusters],
            "count": len(clusters)
        }
        
    except Exception as e:
        logger.error("Get clusters failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve clusters: {str(e)}"
        )


@router.post("/clusters", status_code=status.HTTP_201_CREATED)
async def create_cluster(cluster_data: ClusterCreate):
    """Create new cluster and fetch its information"""
    try:
        # Check if cluster with same name exists
        existing = await database.fetch_one(
            "SELECT id, name, status FROM clusters WHERE name = :name",
            {"name": cluster_data.name}
        )
        
        if existing:
            if existing["status"] == "deleted":
                # Reactivate deleted cluster - update instead of insert
                logger.info("Reactivating deleted cluster", 
                           cluster_id=existing["id"], name=cluster_data.name)
                update_query = """
                UPDATE clusters SET
                    description = :description,
                    environment = :environment,
                    provider = :provider,
                    region = :region,
                    connection_type = :connection_type,
                    api_server_url = :api_server_url,
                    kubeconfig_encrypted = :kubeconfig,
                    token_encrypted = :token,
                    ca_cert_encrypted = :ca_cert,
                    gadget_namespace = :gadget_namespace,
                    skip_tls_verify = :skip_tls_verify,
                    status = 'active',
                    gadget_health_status = 'unknown',
                    updated_at = NOW()
                WHERE id = :cluster_id
                RETURNING id
                """
                # Encrypt sensitive data before saving
                encrypted_kubeconfig = encrypt_data(cluster_data.kubeconfig) if cluster_data.kubeconfig else None
                encrypted_token = encrypt_data(cluster_data.token) if cluster_data.token else None
                encrypted_ca_cert = encrypt_data(cluster_data.ca_cert) if cluster_data.ca_cert else None
                
                params = {
                    "cluster_id": existing["id"],
                    "description": cluster_data.description or "",
                    "environment": cluster_data.environment or "production",
                    "provider": cluster_data.provider or "kubernetes",
                    "region": cluster_data.region or "default",
                    "connection_type": cluster_data.connection_type,
                    "api_server_url": cluster_data.api_server_url,
                    "kubeconfig": encrypted_kubeconfig,
                    "token": encrypted_token,
                    "ca_cert": encrypted_ca_cert,
                    "gadget_namespace": cluster_data.gadget_namespace,  # Required from UI
                    "skip_tls_verify": cluster_data.skip_tls_verify or False
                }
                result = await database.fetch_one(update_query, params)
                cluster_id = result['id']
            else:
                # Active cluster with same name exists
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cluster with name '{cluster_data.name}' already exists (ID: {existing['id']}). Use a different name or delete the existing cluster first."
                )
        else:
            # Insert new cluster
            insert_query = """
            INSERT INTO clusters (
                name, description, environment, provider, region,
                connection_type, api_server_url, kubeconfig_encrypted,
                token_encrypted, ca_cert_encrypted, gadget_namespace,
                skip_tls_verify, status, gadget_health_status, created_at
            )
            VALUES (
                :name, :description, :environment, :provider, :region,
                :connection_type, :api_server_url, :kubeconfig,
                :token, :ca_cert, :gadget_namespace,
                :skip_tls_verify, 'active', 'unknown', NOW()
            )
            RETURNING id
            """
            
            # Encrypt sensitive data before saving
            encrypted_kubeconfig = encrypt_data(cluster_data.kubeconfig) if cluster_data.kubeconfig else None
            encrypted_token = encrypt_data(cluster_data.token) if cluster_data.token else None
            encrypted_ca_cert = encrypt_data(cluster_data.ca_cert) if cluster_data.ca_cert else None
            
            params = {
                "name": cluster_data.name,
                "description": cluster_data.description or "",
                "environment": cluster_data.environment or "production",
                "provider": cluster_data.provider or "kubernetes",
                "region": cluster_data.region or "default",
                "connection_type": cluster_data.connection_type,
                "api_server_url": cluster_data.api_server_url,
                "kubeconfig": encrypted_kubeconfig,
                "token": encrypted_token,
                "ca_cert": encrypted_ca_cert,
                "gadget_namespace": cluster_data.gadget_namespace,  # Required from UI
                "skip_tls_verify": cluster_data.skip_tls_verify or False
            }
            
            result = await database.fetch_one(insert_query, params)
            cluster_id = result['id']
        
        logger.info("Cluster created/updated", cluster_id=cluster_id, name=cluster_data.name)
        
        # Schedule background task to fetch cluster info (non-blocking)
        # This prevents health check timeouts during cluster creation
        async def _fetch_cluster_info_background(cid: int, name: str):
            """Background task to fetch cluster info without blocking the request"""
            try:
                logger.info("Background: Fetching cluster info", cluster_id=cid, cluster_name=name)
                
                cluster_info = await cluster_connection_manager.get_cluster_info(cid)
                gadget_health = await cluster_connection_manager.check_gadget_health(cid)
                
                if not cluster_info.get("error"):
                    update_query = """
                    UPDATE clusters
                    SET total_nodes = :total_nodes,
                        total_pods = :total_pods,
                        total_namespaces = :total_namespaces,
                        k8s_version = :k8s_version,
                        gadget_health_status = :gadget_health_status,
                        gadget_version = :gadget_version,
                        updated_at = NOW()
                    WHERE id = :cluster_id
                    """
                    
                    await database.execute(update_query, {
                        "cluster_id": cid,
                        "total_nodes": cluster_info.get("total_nodes", 0),
                        "total_pods": cluster_info.get("total_pods", 0),
                        "total_namespaces": cluster_info.get("total_namespaces", 0),
                        "k8s_version": cluster_info.get("k8s_version"),
                        "gadget_health_status": gadget_health.get("health_status", "unknown"),
                        "gadget_version": gadget_health.get("version")
                    })
                    
                    logger.info("Background: Cluster info updated", cluster_id=cid)
                else:
                    error_msg = cluster_info.get("error", "Unknown error")
                    logger.warning("Background: Cluster info fetch returned error", 
                                  cluster_id=cid, error=error_msg)
                    try:
                        await database.execute(
                            """UPDATE clusters SET
                                gadget_health_status = 'unknown',
                                error_message = :error_msg,
                                updated_at = NOW()
                            WHERE id = :cluster_id""",
                            {"cluster_id": cid, "error_msg": str(error_msg)[:500]}
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Background: Failed to fetch cluster info", 
                            cluster_id=cid, 
                            error=str(e))
                try:
                    await database.execute(
                        """UPDATE clusters SET
                            gadget_health_status = 'unknown',
                            error_message = :error_msg,
                            updated_at = NOW()
                        WHERE id = :cluster_id""",
                        {"cluster_id": cid, "error_msg": str(e)[:500]}
                    )
                except Exception:
                    pass
        
        # Start background task - don't await, let it run independently
        asyncio.create_task(_fetch_cluster_info_background(cluster_id, cluster_data.name))
        
        # Fetch the complete cluster record
        cluster = await database.fetch_one(
            """SELECT id, name, description, environment, provider, region,
                      connection_type, api_server_url, gadget_namespace, gadget_endpoint,
                      gadget_health_status, gadget_version, status,
                      total_nodes, total_pods, total_namespaces,
                      k8s_version, created_at, updated_at
               FROM clusters WHERE id = :cluster_id""",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            logger.error("Cluster not found after creation", cluster_id=cluster_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cluster created but could not be retrieved"
            )
        
        return {
            "message": "Cluster created successfully",
            "cluster": dict(cluster)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create cluster failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create cluster: {str(e)}"
        )


# NOTE: Static paths like /clusters/gadget-install-script and /clusters/test-connection
# MUST be defined BEFORE dynamic paths like /clusters/{cluster_id}
# Otherwise FastAPI will try to match "gadget-install-script" as a cluster_id


def generate_uninstall_script(cli_tool: str, provider_upper: str) -> str:
    """Generate uninstall script for Flowfish components"""
    return f'''#!/bin/bash
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Flowfish Uninstall Script for {provider_upper:<12}                                ║
# ║                                                                           ║
# ║  This script SAFELY removes ONLY:                                         ║
# ║  - Inspector Gadget (DaemonSet, Service, ConfigMap, RBAC)                ║
# ║  - Flowfish ServiceAccount and RBAC                                       ║
# ║  - SCC (OpenShift only, if not used by other namespaces)                 ║
# ║                                                                           ║
# ║  ✅ SAFE: The NAMESPACE will NOT be deleted!                              ║
# ║  ✅ SAFE: Other workloads in the namespace will NOT be affected!         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   chmod +x uninstall-flowfish.sh
#   ./uninstall-flowfish.sh <namespace>
#   ./uninstall-flowfish.sh              # Interactive mode
#

CLI_TOOL="{cli_tool}"

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
BOLD='\\033[1m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[SUCCESS]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARNING]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}
print_header() {{ echo -e "\\n${{CYAN}}${{BOLD}}═══ $1 ═══${{NC}}\\n"; }}

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         Flowfish Uninstall Script for {provider_upper:<12}                        ║"
echo "║                                                                           ║"
echo "║  ⚠️  This will remove Inspector Gadget and Flowfish ServiceAccount        ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Pre-flight Checks
# ═══════════════════════════════════════════════════════════════════════════
print_header "Pre-flight Checks"

if ! command -v $CLI_TOOL &> /dev/null; then
    print_error "$CLI_TOOL CLI is not installed or not in PATH"
    exit 1
fi
print_success "$CLI_TOOL CLI found"

if ! $CLI_TOOL whoami &> /dev/null; then
    print_error "Not logged in. Please run '$CLI_TOOL login' first."
    exit 1
fi
CURRENT_USER=$($CLI_TOOL whoami)
print_success "Logged in as: $CURRENT_USER"

# Get namespace
if [ -n "$1" ]; then
    NAMESPACE="$1"
    print_status "Using namespace from parameter: $NAMESPACE"
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    read -p "Enter namespace to uninstall Flowfish from: " NAMESPACE
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════
# Safety Check - Verify this is a Flowfish namespace
# ═══════════════════════════════════════════════════════════════════════════
print_header "Safety Verification"

# Check if Inspector Gadget or Flowfish resources exist in this namespace
GADGET_EXISTS=$($CLI_TOOL get daemonset inspektor-gadget -n $NAMESPACE 2>/dev/null && echo "yes" || echo "no")
SA_EXISTS=$($CLI_TOOL get sa flowfish-remote-reader -n $NAMESPACE 2>/dev/null && echo "yes" || echo "no")

if [ "$GADGET_EXISTS" = "no" ] && [ "$SA_EXISTS" = "no" ]; then
    print_error "No Flowfish or Inspector Gadget resources found in namespace '$NAMESPACE'"
    print_warning "This namespace does not appear to have Flowfish installed."
    print_warning "Aborting to prevent accidental deletion of unrelated resources."
    exit 1
fi

print_success "Flowfish resources detected in namespace '$NAMESPACE'"

# Confirmation
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ ⚠️  WARNING: The following will be DELETED from namespace '$NAMESPACE':      │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
if [ "$GADGET_EXISTS" = "yes" ]; then
    echo "│   - DaemonSet: inspektor-gadget                                             │"
    echo "│   - Service: inspektor-gadget                                               │"
    echo "│   - ConfigMap: inspektor-gadget-config                                      │"
    echo "│   - ServiceAccount: inspektor-gadget                                        │"
fi
if [ "$SA_EXISTS" = "yes" ]; then
    echo "│   - ServiceAccount: flowfish-remote-reader                                  │"
    echo "│   - Secret: flowfish-remote-reader-token                                    │"
fi
echo "│   - ClusterRole: inspektor-gadget (if no other bindings)                    │"
echo "│   - ClusterRole: flowfish-remote-reader (if no other bindings)              │"
echo "│   - ClusterRoleBinding: inspektor-gadget-$NAMESPACE                          │"
echo "│   - ClusterRoleBinding: flowfish-remote-reader-$NAMESPACE                    │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ ✅ SAFE: The namespace '$NAMESPACE' will NOT be deleted!                     │"
echo "│ ✅ SAFE: Other workloads in this namespace will NOT be affected!            │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_warning "Uninstall cancelled."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
# Uninstall Process
# ═══════════════════════════════════════════════════════════════════════════
print_header "Removing Flowfish Components"

# Remove namespace-scoped resources first
print_status "Removing Inspector Gadget DaemonSet..."
$CLI_TOOL delete daemonset inspektor-gadget -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "DaemonSet removed"

print_status "Removing Inspector Gadget Service..."
$CLI_TOOL delete service inspektor-gadget -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Service removed"

print_status "Removing Inspector Gadget ConfigMap..."
$CLI_TOOL delete configmap inspektor-gadget-config -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "ConfigMap removed"

print_status "Removing Inspector Gadget ServiceAccount..."
$CLI_TOOL delete sa inspektor-gadget -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Gadget ServiceAccount removed"

print_status "Removing Flowfish ServiceAccount..."
$CLI_TOOL delete sa flowfish-remote-reader -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Flowfish ServiceAccount removed"

print_status "Removing Flowfish Token Secret..."
$CLI_TOOL delete secret flowfish-remote-reader-token -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Token Secret removed"

print_status "Removing Flowfish Gadget Access Role..."
$CLI_TOOL delete role flowfish-gadget-access -n $NAMESPACE --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete rolebinding flowfish-gadget-access -n $NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Gadget Access Role removed"

# Remove cluster-scoped resources
print_header "Removing Cluster-scoped Resources"

print_status "Removing ClusterRoleBinding for Gadget..."
$CLI_TOOL delete clusterrolebinding inspektor-gadget-$NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Gadget ClusterRoleBinding removed"

print_status "Removing ClusterRoleBinding for Flowfish..."
$CLI_TOOL delete clusterrolebinding flowfish-remote-reader-$NAMESPACE --ignore-not-found=true 2>/dev/null
print_success "Flowfish ClusterRoleBinding removed"

# Check if ClusterRoles are still in use by other namespaces
GADGET_BINDINGS=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="inspektor-gadget")].metadata.name}}' 2>/dev/null)
if [ -z "$GADGET_BINDINGS" ]; then
    print_status "Removing ClusterRole inspektor-gadget (no longer in use)..."
    $CLI_TOOL delete clusterrole inspektor-gadget --ignore-not-found=true 2>/dev/null
    print_success "Gadget ClusterRole removed"
else
    print_warning "ClusterRole inspektor-gadget still in use by other namespaces, skipping..."
fi

FLOWFISH_BINDINGS=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="flowfish-remote-reader")].metadata.name}}' 2>/dev/null)
if [ -z "$FLOWFISH_BINDINGS" ]; then
    print_status "Removing ClusterRole flowfish-remote-reader (no longer in use)..."
    $CLI_TOOL delete clusterrole flowfish-remote-reader --ignore-not-found=true 2>/dev/null
    print_success "Flowfish ClusterRole removed"
else
    print_warning "ClusterRole flowfish-remote-reader still in use by other namespaces, skipping..."
fi

# Remove SCC (OpenShift only) - check if still in use
if [ "$CLI_TOOL" = "oc" ]; then
    # Check if SCC is used by other ServiceAccounts
    SCC_USERS=$($CLI_TOOL get scc inspektor-gadget-scc -o jsonpath='{{.users}}' 2>/dev/null | grep -v "$NAMESPACE" || echo "")
    if [ -z "$SCC_USERS" ]; then
        print_status "Removing SCC inspektor-gadget-scc (no longer in use)..."
        $CLI_TOOL adm policy remove-scc-from-user inspektor-gadget-scc -z inspektor-gadget -n $NAMESPACE 2>/dev/null || true
        $CLI_TOOL delete scc inspektor-gadget-scc --ignore-not-found=true 2>/dev/null
        print_success "SCC removed"
    else
        print_warning "SCC inspektor-gadget-scc still in use by other namespaces, skipping..."
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# Completion
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                           ║"
echo "║   ✅ UNINSTALL COMPLETE                                                   ║"
echo "║                                                                           ║"
echo "║   Flowfish components have been removed from namespace '$NAMESPACE'       ║"
echo "║                                                                           ║"
echo "║   ✅ Namespace '$NAMESPACE' was preserved (NOT deleted)                    ║"
echo "║   ✅ Other workloads in this namespace were NOT affected                  ║"
echo "║                                                                           ║"
echo "║   Note: The Trace CRD was NOT removed as it may be used by other         ║"
echo "║   Inspector Gadget installations. To remove it manually:                  ║"
echo "║   $CLI_TOOL delete crd traces.gadget.kinvolk.io                            ║"
echo "║                                                                           ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
'''


@router.get("/clusters/gadget-install-script", response_class=PlainTextResponse)
async def get_gadget_install_script(
    provider: str = Query("openshift", description="Kubernetes provider: openshift, kubernetes"),
    mode: str = Query("install", description="Script mode: install or uninstall"),
    registry: str = Query("ghcr.io/inspektor-gadget/inspektor-gadget", description="Gadget image registry (e.g., harbor.example.com/flowfish/inspektor-gadget)"),
    version: str = Query("v0.48.0", description="Gadget version tag"),
    storage_class: str = Query("", description="StorageClass name for persistent gadget data (e.g., standard, gp2, managed-premium). If empty, uses emptyDir (data lost on pod restart)")
):
    """
    Generate setup or uninstall script for remote cluster integration.
    
    Install mode:
    1. Installs Inspector Gadget for eBPF event collection
    2. Creates a read-only ServiceAccount for Flowfish
    3. Generates authentication token (1 year validity)
    4. Outputs all connection details for Flowfish UI
    5. (Optional) Creates PersistentVolumeClaims with specified StorageClass
    
    Uninstall mode:
    - Safely removes only Flowfish-related resources
    - Validates namespace before deletion
    
    Registry examples:
    - ghcr.io/inspektor-gadget/inspektor-gadget (default, official)
    - harbor.example.com/flowfish/inspektor-gadget (internal Harbor)
    
    StorageClass examples:
    - standard (GKE default)
    - gp2, gp3 (AWS EKS)
    - managed-premium (Azure AKS)
    - thin, thick (vSphere)
    - Leave empty to use emptyDir (ephemeral storage)
    """
    try:
        is_openshift = provider.lower() == "openshift"
        cli_tool = "oc" if is_openshift else "kubectl"
        
        # Return uninstall script if requested
        if mode == "uninstall":
            return generate_uninstall_script(cli_tool, provider.upper())
        
        # Embedded YAML contents - no file dependencies
        yaml_contents = {
            "crds": """---
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: traces.gadget.kinvolk.io
  annotations:
    controller-gen.kubebuilder.io/version: v0.9.2
spec:
  group: gadget.kinvolk.io
  names:
    kind: Trace
    listKind: TraceList
    plural: traces
    singular: trace
  scope: Cluster
  versions:
  - name: v1alpha1
    schema:
      openAPIV3Schema:
        description: Trace is the Schema for the traces API
        properties:
          apiVersion:
            type: string
          kind:
            type: string
          metadata:
            type: object
          spec:
            properties:
              filter:
                properties:
                  containerName:
                    type: string
                  labels:
                    additionalProperties:
                      type: string
                    type: object
                  namespace:
                    type: string
                  podname:
                    type: string
                type: object
              gadget:
                type: string
              node:
                type: string
              output:
                properties:
                  mode:
                    type: string
                type: object
              parameters:
                additionalProperties:
                  type: string
                type: object
              runMode:
                type: string
            required:
            - gadget
            type: object
          status:
            properties:
              operationError:
                type: string
              operationWarning:
                type: string
              output:
                type: string
              state:
                type: string
            type: object
        type: object
    served: true
    storage: true
    subresources:
      status: {}
""",
            "config": """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: inspektor-gadget-config
  namespace: NAMESPACE_PLACEHOLDER
  labels:
    app: inspektor-gadget
data:
  config.yaml: |
    events-buffer-length: 16384
    # Auto-detected by init container at pod startup. Supported platforms:
    #   K3s/RKE2:  /run/k3s/containerd/containerd.sock
    #   MicroK8s:  /var/snap/microk8s/common/run/containerd.sock
    #   Standard:  /run/containerd/containerd.sock
    containerd-socketpath: CONTAINERD_SOCKET_AUTO
    crio-socketpath: /run/crio/crio.sock
    docker-socketpath: /run/docker.sock
    podman-socketpath: /run/podman/podman.sock
    gadget-namespace: "NAMESPACE_PLACEHOLDER"
    daemon-log-level: info
    operator:
      kubemanager:
        fallback-podinformer: true
        hook-mode: auto
      oci:
        allowed-gadgets: []
        disallow-pulling: false
        verify-image: false
      otel-metrics:
        otel-metrics-listen: false
        otel-metrics-listen-address: 0.0.0.0:2224
""",
            "rbac": """---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: inspektor-gadget
rules:
# Core resources - for kubernetes enricher
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces", "configmaps", "services", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["create", "update", "patch", "delete"]
# Apps resources - for owner reference enrichment
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
# Batch resources - REQUIRED for kubernetes enricher to resolve owner references
# Without this, gadget crashes when processing containers from Jobs/CronJobs
# causing core dump files (core-ocihookgadget-*) that fill up node disks
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch"]
# Gadget traces CRD
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: inspektor-gadget-NAMESPACE_PLACEHOLDER
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: inspektor-gadget
subjects:
- kind: ServiceAccount
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
""",
            "daemonset": """---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
  labels:
    app: inspektor-gadget
    k8s-app: inspektor-gadget
spec:
  selector:
    matchLabels:
      app: inspektor-gadget
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: inspektor-gadget
        k8s-app: gadget
      annotations:
        # NOTE: AppArmor annotation deprecated in K8s 1.30+, using securityContext.appArmorProfile
        prometheus.io/scrape: "true"
        prometheus.io/port: "2223"
        prometheus.io/path: "/metrics"
    spec:
      hostPID: true
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      serviceAccountName: inspektor-gadget
      nodeSelector:
        kubernetes.io/os: linux
      # Exclude master/control-plane/infra nodes (CSI storage typically not available)
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/control-plane
                operator: DoesNotExist
              - key: node-role.kubernetes.io/master
                operator: DoesNotExist
              - key: node-role.kubernetes.io/infra
                operator: DoesNotExist
      tolerations:
      - effect: NoSchedule
        operator: Exists
      - effect: NoExecute
        operator: Exists
      initContainers:
      - name: detect-runtime
        image: busybox:1.36
        command: ['sh', '-c']
        args:
        - |
          if [ -S /host/run/k3s/containerd/containerd.sock ]; then
            SOCKET="/run/k3s/containerd/containerd.sock"
            echo "Detected K3s/RKE2 containerd socket"
          elif [ -S /host/run/containerd/containerd.sock ]; then
            SOCKET="/run/containerd/containerd.sock"
            echo "Detected standard containerd socket"
          elif [ -S /host/var/snap/microk8s/common/run/containerd.sock ]; then
            SOCKET="/host/var/snap/microk8s/common/run/containerd.sock"
            echo "Detected MicroK8s containerd socket"
          else
            SOCKET="/run/containerd/containerd.sock"
            echo "WARNING: No containerd socket found at known paths, using default"
          fi
          echo "Using containerd socket: $SOCKET"
          sed "s|CONTAINERD_SOCKET_AUTO|$SOCKET|g" /config-template/config.yaml > /config-generated/config.yaml
        volumeMounts:
        - name: run
          mountPath: /host/run
          readOnly: true
        - name: var
          mountPath: /host/var
          readOnly: true
        - name: config
          mountPath: /config-template
          readOnly: true
        - name: config-generated
          mountPath: /config-generated
      containers:
      - name: gadget
        image: GADGET_IMAGE_PLACEHOLDER
        imagePullPolicy: Always
        terminationMessagePolicy: FallbackToLogsOnError
        # NOTE: Only -serve flag! -service-host breaks kubectl gadget connectivity
        # kubectl gadget connects via Kubernetes API, not gRPC port
        # This applies to BOTH in-cluster and remote clusters
        command:
        - /bin/gadgettracermanager
        - -serve
        lifecycle:
          preStop:
            exec:
              command:
              - /cleanup
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: GADGET_POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: GADGET_IMAGE
          value: "GADGET_IMAGE_PLACEHOLDER"
        - name: HOST_ROOT
          value: "/host"
        - name: IG_EXPERIMENTAL
          value: "false"
        securityContext:
          readOnlyRootFilesystem: true
          # AppArmor profile - K8s 1.30+ format (replaces deprecated annotation)
          appArmorProfile:
            type: Unconfined
          seLinuxOptions:
            type: spc_t
          capabilities:
            drop:
            - ALL
            add:
            - SYS_ADMIN
            - SYSLOG
            - SYS_PTRACE
            - SYS_RESOURCE
            - IPC_LOCK
            - NET_RAW
            - NET_ADMIN
        startupProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          failureThreshold: 12
          periodSeconds: 5
        readinessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        livenessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        resources:
          requests:
            cpu: 100m
            memory: 512Mi
          limits:
            cpu: "1"
            memory: 12Gi
        volumeMounts:
        - name: bin
          mountPath: /host/bin
          readOnly: true
        - name: etc
          mountPath: /host/etc
        - name: opt
          mountPath: /host/opt
        - name: usr
          mountPath: /host/usr
          readOnly: true
        - name: run
          mountPath: /host/run
          readOnly: true
        - name: var
          mountPath: /host/var
          readOnly: true
        - name: proc
          mountPath: /host/proc
          readOnly: true
        - name: run
          mountPath: /run
        - name: debugfs
          mountPath: /sys/kernel/debug
        - name: cgroup
          mountPath: /sys/fs/cgroup
          readOnly: true
        - name: bpffs
          mountPath: /sys/fs/bpf
        - name: oci
          mountPath: /var/lib/ig
        - name: config-generated
          mountPath: /etc/ig
          readOnly: true
        - name: wasm-cache
          mountPath: /var/run/ig/wasm-cache
      volumes:
      - name: bin
        hostPath:
          path: /bin
      - name: etc
        hostPath:
          path: /etc
      - name: opt
        hostPath:
          path: /opt
      - name: usr
        hostPath:
          path: /usr
      - name: proc
        hostPath:
          path: /proc
      - name: run
        hostPath:
          path: /run
      - name: var
        hostPath:
          path: /var
      - name: cgroup
        hostPath:
          path: /sys/fs/cgroup
      - name: bpffs
        hostPath:
          path: /sys/fs/bpf
      - name: debugfs
        hostPath:
          path: /sys/kernel/debug
      - name: oci
        emptyDir: {}
      - name: config
        configMap:
          name: inspektor-gadget-config
          defaultMode: 0400
      - name: config-generated
        emptyDir: {}
      - name: wasm-cache
        emptyDir: {}
---
# ClusterIP service (optional - kubectl gadget uses K8s API, not this service)
apiVersion: v1
kind: Service
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
  labels:
    app: inspektor-gadget
spec:
  type: ClusterIP
  ports:
  - name: grpc
    port: 16060
    targetPort: 16060
    protocol: TCP
  selector:
    app: inspektor-gadget
"""
        }
        
        provider_upper = provider.upper()
        
        # Generate comprehensive setup script
        # Determine storage class parameter for script
        storage_class_default = storage_class if storage_class else ""
        
        script = f'''#!/bin/bash
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Flowfish Remote Cluster Setup Script for {provider_upper:<12}                    ║
# ║                                                                           ║
# ║  This script:                                                             ║
# ║  1. Installs Inspector Gadget for eBPF event collection                   ║
# ║  2. Creates a READ-ONLY ServiceAccount for Flowfish                       ║
# ║  3. Generates authentication token                                        ║
# ║  4. Outputs connection details for Flowfish UI                            ║
# ║  5. (Optional) Configures persistent storage with StorageClass            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   chmod +x setup-flowfish-remote.sh
#   ./setup-flowfish-remote.sh <namespace> [registry] [version] [storage_class]
#   ./setup-flowfish-remote.sh                                    # Interactive mode
#
# Examples:
#   # Using official registry with emptyDir (default - ephemeral storage):
#   ./setup-flowfish-remote.sh flowfish
#
#   # Using internal Harbor registry with persistent storage:
#   ./setup-flowfish-remote.sh flowfish harbor.example.com/flowfish/inspektor-gadget v0.48.0 standard
#
#   # Using only storage class (with default registry and version):
#   ./setup-flowfish-remote.sh flowfish "" "" gp2
#
# Arguments:
#   namespace     - Target namespace (required)
#   registry      - Gadget image registry (default: {registry})
#   version       - Gadget version tag (default: {version})
#   storage_class - StorageClass for persistent data (optional, uses emptyDir if not specified)
#
# StorageClass Examples:
#   - standard     (GKE default)
#   - gp2, gp3     (AWS EKS)
#   - managed-premium (Azure AKS)
#   - thin, thick  (vSphere)
#
# Requirements:
#   - {cli_tool} CLI installed and logged in
#   - cluster-admin privileges (for RBAC and CRD creation)
#   - Target namespace must exist
#

# Don't use set -e, we handle errors manually for better UX

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════
CLI_TOOL="{cli_tool}"
SA_NAME="flowfish-remote-reader"

# Default values (can be overridden by arguments)
DEFAULT_REGISTRY="{registry}"
DEFAULT_VERSION="{version}"
DEFAULT_STORAGE_CLASS="{storage_class_default}"

# Parse arguments
NAMESPACE="${{1:-}}"
GADGET_REGISTRY="${{2:-$DEFAULT_REGISTRY}}"
GADGET_VERSION="${{3:-$DEFAULT_VERSION}}"
STORAGE_CLASS="${{4:-$DEFAULT_STORAGE_CLASS}}"

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
BOLD='\\033[1m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[SUCCESS]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARNING]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}
print_header() {{ echo -e "\\n${{CYAN}}${{BOLD}}═══ $1 ═══${{NC}}\\n"; }}

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         Flowfish Remote Cluster Setup for {provider_upper:<12}                   ║"
echo "║                                                                           ║"
echo "║  🔒 Security: Creates READ-ONLY access (no write permissions)            ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Pre-flight Checks
# ═══════════════════════════════════════════════════════════════════════════
print_header "Pre-flight Checks"

if ! command -v $CLI_TOOL &> /dev/null; then
    print_error "$CLI_TOOL CLI is not installed or not in PATH"
    exit 1
fi
print_success "$CLI_TOOL CLI found"

if ! $CLI_TOOL whoami &> /dev/null; then
    print_error "Not logged in. Please run '$CLI_TOOL login' first."
    exit 1
fi
CURRENT_USER=$($CLI_TOOL whoami)
print_success "Logged in as: $CURRENT_USER"

# Check for cluster-admin
if ! $CLI_TOOL auth can-i create clusterrole &> /dev/null; then
    print_error "You need cluster-admin privileges to run this script"
    exit 1
fi
print_success "Cluster-admin privileges confirmed"

# Interactive mode if arguments not provided
if [ -z "$NAMESPACE" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${{CYAN}}Namespace:${{NC}} Target namespace where Flowfish components will be installed"
    echo -e "  Example: flowfish, prod-flowfish"
    read -p "Enter namespace: " NAMESPACE
    echo ""
    echo -e "${{CYAN}}Registry:${{NC}} Container registry for Inspektor Gadget image"
    echo -e "  Example: harbor.example.com/flowfish/inspektor-gadget"
    echo -e "  Default: $DEFAULT_REGISTRY"
    read -p "Enter registry (press Enter for default): " INPUT_REGISTRY
    GADGET_REGISTRY="${{INPUT_REGISTRY:-$DEFAULT_REGISTRY}}"
    echo ""
    echo -e "${{CYAN}}Version:${{NC}} Inspektor Gadget version tag"
    echo -e "  Example: v0.46.0, v0.48.0"
    echo -e "  Default: $DEFAULT_VERSION"
    read -p "Enter version (press Enter for default): " INPUT_VERSION
    GADGET_VERSION="${{INPUT_VERSION:-$DEFAULT_VERSION}}"
    echo ""
    echo -e "${{CYAN}}Storage Class:${{NC}} StorageClass for persistent gadget data (OCI images, WASM cache)"
    echo -e "  This prevents gadget from filling up node's local disk (emptyDir)"
    echo -e "  Leave empty to use emptyDir (ephemeral storage - data lost on pod restart)"
    echo -e "  Examples: standard (GKE), gp2/gp3 (AWS), managed-premium (Azure)"
    if [ -n "$DEFAULT_STORAGE_CLASS" ]; then
        echo -e "  Default: $DEFAULT_STORAGE_CLASS"
    fi
    read -p "Enter storage class (press Enter for emptyDir): " INPUT_STORAGE_CLASS
    STORAGE_CLASS="${{INPUT_STORAGE_CLASS:-$DEFAULT_STORAGE_CLASS}}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
print_status "Configuration:"
print_status "  Namespace:     $NAMESPACE"
print_status "  Registry:      $GADGET_REGISTRY"
print_status "  Version:       $GADGET_VERSION"
if [ -n "$STORAGE_CLASS" ]; then
    print_status "  Storage Class: $STORAGE_CLASS (persistent storage)"
else
    print_status "  Storage Class: (none - using emptyDir)"
fi
echo ""

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    print_status "Create it with: $CLI_TOOL create namespace $NAMESPACE"
    exit 1
fi
print_success "Namespace '$NAMESPACE' exists"

# ═══════════════════════════════════════════════════════════════════════════
# Storage Class Validation (if specified)
# ═══════════════════════════════════════════════════════════════════════════
USE_PERSISTENT_STORAGE=false
if [ -n "$STORAGE_CLASS" ]; then
    print_header "Storage Class Validation"
    
    # Check Kubernetes version (ephemeral volumes require 1.23+)
    print_status "Checking Kubernetes version compatibility..."
    K8S_VERSION=$($CLI_TOOL version -o json 2>/dev/null | grep -o '"gitVersion": "[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -z "$K8S_VERSION" ]; then
        K8S_VERSION=$($CLI_TOOL version --short 2>/dev/null | grep -i server | awk '{{print $NF}}')
    fi
    
    if [ -n "$K8S_VERSION" ]; then
        print_status "Kubernetes version: $K8S_VERSION"
        K8S_MAJOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f1)
        K8S_MINOR=$(echo "$K8S_VERSION" | cut -d. -f2)
        
        if [ "$K8S_MAJOR" -lt 1 ] || ([ "$K8S_MAJOR" -eq 1 ] && [ "$K8S_MINOR" -lt 23 ]); then
            print_error "Kubernetes version $K8S_VERSION does not support ephemeral volumes!"
            print_error "Ephemeral volumes require Kubernetes 1.23 or newer."
            print_warning "Falling back to emptyDir storage..."
            STORAGE_CLASS=""
        else
            print_success "Kubernetes version is compatible (1.23+ required)"
        fi
    else
        print_warning "Could not determine Kubernetes version. Proceeding with StorageClass..."
    fi
fi

if [ -n "$STORAGE_CLASS" ]; then
    print_status "Checking if StorageClass '$STORAGE_CLASS' exists..."
    if ! $CLI_TOOL get storageclass "$STORAGE_CLASS" &> /dev/null; then
        print_error "StorageClass '$STORAGE_CLASS' not found!"
        echo ""
        print_status "Available StorageClasses in cluster:"
        $CLI_TOOL get storageclass -o custom-columns=NAME:.metadata.name,PROVISIONER:.provisioner,RECLAIMPOLICY:.reclaimPolicy,DEFAULT:.metadata.annotations."storageclass\.kubernetes\.io/is-default-class" 2>/dev/null || \
            $CLI_TOOL get storageclass 2>/dev/null || echo "  (unable to list storage classes)"
        echo ""
        print_warning "Options:"
        print_warning "  1. Use a valid StorageClass from the list above"
        print_warning "  2. Re-run without storage class (uses emptyDir)"
        exit 1
    fi
    print_success "StorageClass '$STORAGE_CLASS' exists"
    
    # Check if StorageClass supports dynamic provisioning
    PROVISIONER=$($CLI_TOOL get storageclass "$STORAGE_CLASS" -o jsonpath='{{.provisioner}}' 2>/dev/null)
    print_status "Provisioner: $PROVISIONER"
    
    # Check volume binding mode
    BINDING_MODE=$($CLI_TOOL get storageclass "$STORAGE_CLASS" -o jsonpath='{{.volumeBindingMode}}' 2>/dev/null)
    if [ "$BINDING_MODE" = "WaitForFirstConsumer" ]; then
        print_success "Volume binding mode: WaitForFirstConsumer (recommended for DaemonSet)"
    elif [ -n "$BINDING_MODE" ]; then
        print_warning "Volume binding mode: $BINDING_MODE"
        print_warning "Consider using WaitForFirstConsumer for better node affinity"
    fi
    
    USE_PERSISTENT_STORAGE=true
    print_success "Persistent storage will be configured with StorageClass: $STORAGE_CLASS"
    echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# PART 1: Inspector Gadget Installation
# ═══════════════════════════════════════════════════════════════════════════
print_header "Part 1: Inspector Gadget Installation"

# Step 1: Apply Trace CRD
print_status "1/6 - Applying Trace CRD..."
cat <<'CRD_EOF' | $CLI_TOOL apply -f -
{yaml_contents["crds"]}
CRD_EOF
print_success "Trace CRD applied"

# Step 2: Create Security Context Constraint (OpenShift only)
if [ "$CLI_TOOL" = "oc" ]; then
    print_status "2/6 - Creating Security Context Constraint (SCC)..."
    cat <<'SCC_EOF' | $CLI_TOOL apply -f -
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: inspektor-gadget-scc
  labels:
    app.kubernetes.io/name: inspektor-gadget
allowHostDirVolumePlugin: true
allowHostIPC: false
allowHostNetwork: true
allowHostPID: true
allowHostPorts: true
allowPrivilegeEscalation: true
allowPrivilegedContainer: true
allowedCapabilities:
  - SYS_ADMIN
  - SYSLOG
  - SYS_PTRACE
  - SYS_RESOURCE
  - IPC_LOCK
  - NET_RAW
  - NET_ADMIN
defaultAddCapabilities: null
fsGroup:
  type: RunAsAny
priority: null
readOnlyRootFilesystem: true
requiredDropCapabilities: null
runAsUser:
  type: RunAsAny
seLinuxContext:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
volumes:
  - configMap
  - downwardAPI
  - emptyDir
  - ephemeral
  - hostPath
  - persistentVolumeClaim
  - projected
  - secret
SCC_EOF
    print_success "SCC created"
else
    print_status "2/6 - Skipping SCC (not OpenShift)..."
fi

# Step 3: Apply RBAC for Gadget
print_status "3/6 - Applying Gadget RBAC..."
cat <<'RBAC_EOF' | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | $CLI_TOOL apply -f -
{yaml_contents["rbac"]}
RBAC_EOF
print_success "Gadget RBAC applied"

# Step 4: Bind SCC to ServiceAccount (OpenShift only)
if [ "$CLI_TOOL" = "oc" ]; then
    print_status "4/6 - Binding SCC to ServiceAccount..."
    $CLI_TOOL adm policy add-scc-to-user inspektor-gadget-scc -z inspektor-gadget -n $NAMESPACE 2>/dev/null || true
    print_success "SCC bound to ServiceAccount"
else
    print_status "4/6 - Skipping SCC binding (not OpenShift)..."
fi

# Step 5: Create ConfigMap
print_status "5/6 - Creating ConfigMap..."
cat <<'CONFIG_EOF' | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | $CLI_TOOL apply -f -
{yaml_contents["config"]}
CONFIG_EOF
print_success "ConfigMap created"

# Step 6: Deploy DaemonSet
print_status "6/6 - Deploying DaemonSet..."
GADGET_IMAGE="${{GADGET_REGISTRY}}:${{GADGET_VERSION}}"
print_status "Using Gadget image: $GADGET_IMAGE"

if [ "$USE_PERSISTENT_STORAGE" = true ]; then
    print_status "Configuring with persistent storage (StorageClass: $STORAGE_CLASS)"
    cat <<DAEMONSET_PVC_EOF | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | sed "s|GADGET_IMAGE_PLACEHOLDER|$GADGET_IMAGE|g" | sed "s|STORAGE_CLASS_PLACEHOLDER|$STORAGE_CLASS|g" | $CLI_TOOL apply -f -
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
  labels:
    app: inspektor-gadget
    k8s-app: inspektor-gadget
spec:
  selector:
    matchLabels:
      app: inspektor-gadget
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: inspektor-gadget
        k8s-app: gadget
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "2223"
        prometheus.io/path: "/metrics"
    spec:
      hostPID: true
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      serviceAccountName: inspektor-gadget
      nodeSelector:
        kubernetes.io/os: linux
      # Exclude master/control-plane/infra nodes (CSI storage typically not available)
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/control-plane
                operator: DoesNotExist
              - key: node-role.kubernetes.io/master
                operator: DoesNotExist
              - key: node-role.kubernetes.io/infra
                operator: DoesNotExist
      tolerations:
      - effect: NoSchedule
        operator: Exists
      - effect: NoExecute
        operator: Exists
      initContainers:
      - name: detect-runtime
        image: busybox:1.36
        command: ['sh', '-c']
        args:
        - |
          if [ -S /host/run/k3s/containerd/containerd.sock ]; then
            SOCKET="/run/k3s/containerd/containerd.sock"
            echo "Detected K3s/RKE2 containerd socket"
          elif [ -S /host/run/containerd/containerd.sock ]; then
            SOCKET="/run/containerd/containerd.sock"
            echo "Detected standard containerd socket"
          elif [ -S /host/var/snap/microk8s/common/run/containerd.sock ]; then
            SOCKET="/host/var/snap/microk8s/common/run/containerd.sock"
            echo "Detected MicroK8s containerd socket"
          else
            SOCKET="/run/containerd/containerd.sock"
            echo "WARNING: No containerd socket found at known paths, using default"
          fi
          echo "Using containerd socket: $SOCKET"
          sed "s|CONTAINERD_SOCKET_AUTO|$SOCKET|g" /config-template/config.yaml > /config-generated/config.yaml
        volumeMounts:
        - name: run
          mountPath: /host/run
          readOnly: true
        - name: var
          mountPath: /host/var
          readOnly: true
        - name: config
          mountPath: /config-template
          readOnly: true
        - name: config-generated
          mountPath: /config-generated
      containers:
      - name: gadget
        image: GADGET_IMAGE_PLACEHOLDER
        imagePullPolicy: Always
        terminationMessagePolicy: FallbackToLogsOnError
        command:
        - /bin/gadgettracermanager
        - -serve
        lifecycle:
          preStop:
            exec:
              command:
              - /cleanup
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: GADGET_POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: GADGET_IMAGE
          value: "GADGET_IMAGE_PLACEHOLDER"
        - name: HOST_ROOT
          value: "/host"
        - name: IG_EXPERIMENTAL
          value: "false"
        securityContext:
          readOnlyRootFilesystem: true
          appArmorProfile:
            type: Unconfined
          seLinuxOptions:
            type: spc_t
          capabilities:
            drop:
            - ALL
            add:
            - SYS_ADMIN
            - SYSLOG
            - SYS_PTRACE
            - SYS_RESOURCE
            - IPC_LOCK
            - NET_RAW
            - NET_ADMIN
        startupProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          failureThreshold: 12
          periodSeconds: 5
        readinessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        livenessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        resources:
          requests:
            cpu: 100m
            memory: 512Mi
          limits:
            cpu: "1"
            memory: 12Gi
        volumeMounts:
        - name: bin
          mountPath: /host/bin
          readOnly: true
        - name: etc
          mountPath: /host/etc
        - name: opt
          mountPath: /host/opt
        - name: usr
          mountPath: /host/usr
          readOnly: true
        - name: run
          mountPath: /host/run
          readOnly: true
        - name: var
          mountPath: /host/var
          readOnly: true
        - name: proc
          mountPath: /host/proc
          readOnly: true
        - name: run
          mountPath: /run
        - name: debugfs
          mountPath: /sys/kernel/debug
        - name: cgroup
          mountPath: /sys/fs/cgroup
          readOnly: true
        - name: bpffs
          mountPath: /sys/fs/bpf
        - name: oci
          mountPath: /var/lib/ig
        - name: config-generated
          mountPath: /etc/ig
          readOnly: true
        - name: wasm-cache
          mountPath: /var/run/ig/wasm-cache
      volumes:
      - name: bin
        hostPath:
          path: /bin
      - name: etc
        hostPath:
          path: /etc
      - name: opt
        hostPath:
          path: /opt
      - name: usr
        hostPath:
          path: /usr
      - name: proc
        hostPath:
          path: /proc
      - name: run
        hostPath:
          path: /run
      - name: var
        hostPath:
          path: /var
      - name: cgroup
        hostPath:
          path: /sys/fs/cgroup
      - name: bpffs
        hostPath:
          path: /sys/fs/bpf
      - name: debugfs
        hostPath:
          path: /sys/kernel/debug
      # Persistent storage for OCI images (gadget programs)
      - name: oci
        ephemeral:
          volumeClaimTemplate:
            metadata:
              labels:
                app: inspektor-gadget
                volume-type: oci-storage
            spec:
              accessModes: ["ReadWriteOnce"]
              storageClassName: "STORAGE_CLASS_PLACEHOLDER"
              resources:
                requests:
                  storage: 10Gi
      - name: config
        configMap:
          name: inspektor-gadget-config
          defaultMode: 0400
      - name: config-generated
        emptyDir: {{}}
      # Persistent storage for WASM cache
      - name: wasm-cache
        ephemeral:
          volumeClaimTemplate:
            metadata:
              labels:
                app: inspektor-gadget
                volume-type: wasm-cache
            spec:
              accessModes: ["ReadWriteOnce"]
              storageClassName: "STORAGE_CLASS_PLACEHOLDER"
              resources:
                requests:
                  storage: 5Gi
---
apiVersion: v1
kind: Service
metadata:
  name: inspektor-gadget
  namespace: NAMESPACE_PLACEHOLDER
  labels:
    app: inspektor-gadget
spec:
  type: ClusterIP
  ports:
  - name: grpc
    port: 16060
    targetPort: 16060
    protocol: TCP
  selector:
    app: inspektor-gadget
DAEMONSET_PVC_EOF
    print_success "DaemonSet deployed with persistent storage"
    print_status "Ephemeral PVCs will be created automatically per pod"
else
    print_status "Configuring with emptyDir (ephemeral storage)"
    cat <<'DAEMONSET_EOF' | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | sed "s|GADGET_IMAGE_PLACEHOLDER|$GADGET_IMAGE|g" | $CLI_TOOL apply -f -
{yaml_contents["daemonset"]}
DAEMONSET_EOF
    print_success "DaemonSet deployed with emptyDir storage"
fi

# Restart pods to pick up SCC
print_status "Restarting Gadget pods to apply SCC..."
$CLI_TOOL delete pods -l app=inspektor-gadget -n $NAMESPACE --ignore-not-found=true 2>/dev/null || true
sleep 3

# Wait for pods
print_status "Waiting for Gadget pods to be ready (timeout: 180s)..."
if $CLI_TOOL wait --for=condition=ready pod -l app=inspektor-gadget -n "$NAMESPACE" --timeout=180s 2>/dev/null; then
    print_success "All Gadget pods are ready!"
else
    print_warning "Timeout waiting for pods. Check with: $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# PART 2: Flowfish Read-Only ServiceAccount
# ═══════════════════════════════════════════════════════════════════════════
print_header "Part 2: Flowfish Read-Only ServiceAccount"

print_status "Creating ServiceAccount '$SA_NAME'..."
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: $SA_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: flowfish
    app.kubernetes.io/component: remote-reader
    app.kubernetes.io/purpose: readonly-access
EOF
print_success "ServiceAccount created"

print_status "Creating ClusterRole with READ-ONLY permissions..."
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flowfish-remote-reader
  labels:
    app.kubernetes.io/name: flowfish
    app.kubernetes.io/purpose: readonly-access
rules:
  # Core resources - READ ONLY
  - apiGroups: [""]
    resources: ["pods", "nodes", "namespaces", "services", "events", "endpoints"]
    verbs: ["get", "list", "watch"]
  # Apps resources - READ ONLY
  - apiGroups: ["apps"]
    resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]
  # Batch resources - READ ONLY
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  # Networking - READ ONLY
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies", "ingresses"]
    verbs: ["get", "list", "watch"]
  # Inspector Gadget traces - READ ONLY
  - apiGroups: ["gadget.kinvolk.io"]
    resources: ["traces"]
    verbs: ["get", "list", "watch"]
EOF
print_success "ClusterRole created (READ-ONLY permissions only)"

# Create namespace-scoped Role for kubectl gadget access
# This allows portforward/exec ONLY in the gadget namespace (not cluster-wide)
print_status "Creating namespace-scoped Role for kubectl gadget access..."
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: flowfish-gadget-access
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: flowfish
    app.kubernetes.io/purpose: gadget-communication
rules:
  # Required for kubectl gadget to communicate with Inspector Gadget pods
  # These permissions are ONLY valid in this namespace (not cluster-wide)
  - apiGroups: [""]
    resources: ["pods/portforward"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: flowfish-gadget-access
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: flowfish
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: flowfish-gadget-access
subjects:
  - kind: ServiceAccount
    name: $SA_NAME
    namespace: $NAMESPACE
EOF
print_success "Namespace-scoped Role created (pods/portforward, pods/exec in $NAMESPACE only)"

print_status "Creating ClusterRoleBinding..."
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flowfish-remote-reader-$NAMESPACE
  labels:
    app.kubernetes.io/name: flowfish
    app.kubernetes.io/purpose: readonly-access
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flowfish-remote-reader
subjects:
  - kind: ServiceAccount
    name: $SA_NAME
    namespace: $NAMESPACE
EOF
print_success "ClusterRoleBinding created"

# ═══════════════════════════════════════════════════════════════════════════
# PART 3: Generate Connection Details
# ═══════════════════════════════════════════════════════════════════════════
print_header "Part 3: Generating Connection Details"

# Get API Server URL
print_status "Getting API Server URL..."
API_SERVER=$($CLI_TOOL config view --minify -o jsonpath='{{.clusters[0].cluster.server}}')
print_success "API Server: $API_SERVER"

# Generate Token - use Secret-based method for OpenShift compatibility
print_status "Creating token Secret for ServiceAccount..."
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: $SA_NAME-token
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/managed-by: flowfish
    app.kubernetes.io/component: remote-reader
  annotations:
    kubernetes.io/service-account.name: $SA_NAME
type: kubernetes.io/service-account-token
EOF

print_status "Waiting for token to be generated..."
sleep 5

SA_TOKEN=$($CLI_TOOL get secret $SA_NAME-token -n $NAMESPACE -o jsonpath='{{.data.token}}' 2>/dev/null | base64 -d 2>/dev/null)
if [ -z "$SA_TOKEN" ]; then
    print_warning "Token not in Secret yet. Trying oc create token..."
    SA_TOKEN=$($CLI_TOOL create token $SA_NAME -n $NAMESPACE --duration=8760h 2>/dev/null || echo "")
fi

if [ -z "$SA_TOKEN" ]; then
    print_error "Could not generate ServiceAccount token!"
    echo ""
    echo "Manual token generation command:"
    echo "  $CLI_TOOL create token $SA_NAME -n $NAMESPACE --duration=8760h"
    echo ""
else
    print_success "Token generated successfully"
fi

# Get CA Certificate
print_status "Getting CA Certificate..."

# First, get the API server URL to extract CA from connection
API_SERVER=$($CLI_TOOL config view --minify -o jsonpath='{{.clusters[0].cluster.server}}' 2>/dev/null || echo "")
API_HOST=$(echo "$API_SERVER" | sed -e 's|https://||' -e 's|:.*||')
API_PORT=$(echo "$API_SERVER" | sed -e 's|.*:||' -e 's|/.*||')
[ -z "$API_PORT" ] && API_PORT="6443"

# We'll collect CA certs from multiple sources and combine them
# This ensures compatibility with different cluster configurations:
# - Self-signed (OpenShift internal CAs)
# - Corporate PKI (external CA like BankSubCA2)
# - Public CA (DigiCert, Let's Encrypt - usually in system trust store)
# - Hybrid (both internal and external CAs needed)

CA_CERTS_COLLECTED=""

# ─────────────────────────────────────────────────────────────────────────────
# Source 1: API Server TLS Connection (for corporate/external PKI)
# ─────────────────────────────────────────────────────────────────────────────
# This gets the ACTUAL CA chain that signed the API server certificate
# Critical for corporate PKI where internal CAs don't match external certs
if command -v openssl &> /dev/null && [ -n "$API_HOST" ]; then
    print_status "Checking API server certificate chain..."
    
    # Get ALL certificates from the TLS handshake (full chain)
    ALL_CERTS=$(echo | openssl s_client -connect "$API_HOST:$API_PORT" -servername "$API_HOST" -showcerts 2>/dev/null | \
        sed -n '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/p')
    
    # Count certificates in chain
    CERT_COUNT=$(echo "$ALL_CERTS" | grep -c "BEGIN CERTIFICATE" || echo "0")
    
    if [ "$CERT_COUNT" -gt 1 ]; then
        # Multiple certs = chain provided, skip first (leaf) and keep CA certs
        CHAIN_CERTS=$(echo "$ALL_CERTS" | awk 'BEGIN{{n=0}} /-----BEGIN CERTIFICATE-----/{{n++}} n>1{{print}}')
        if [ -n "$CHAIN_CERTS" ]; then
            CA_CERTS_COLLECTED="$CHAIN_CERTS"
            print_success "CA chain retrieved from API server ($((CERT_COUNT-1)) CA cert(s))"
        fi
    elif [ "$CERT_COUNT" -eq 1 ]; then
        # Single cert = server doesn't send chain, try to get CA from AIA extension
        ISSUER=$(echo "$ALL_CERTS" | openssl x509 -noout -issuer 2>/dev/null | sed 's/issuer=//')
        print_warning "API server sends only leaf certificate"
        print_warning "Issuer: $ISSUER"
        
        # Try to extract CA URL from AIA (Authority Information Access) extension
        AIA_URL=$(echo "$ALL_CERTS" | openssl x509 -noout -text 2>/dev/null | \
            grep -A1 "CA Issuers" | grep -oE 'http://[^[:space:]]+\.crt' | head -1)
        
        if [ -n "$AIA_URL" ]; then
            print_status "Found CA download URL in certificate: $AIA_URL"
            print_status "Attempting to download issuer CA..."
            
            # Download the CA certificate (might be DER or PEM format)
            CA_TEMP_FILE=$(mktemp)
            if curl -sSf -o "$CA_TEMP_FILE" "$AIA_URL" 2>/dev/null; then
                # Check if it's DER format (binary) and convert to PEM
                if file "$CA_TEMP_FILE" 2>/dev/null | grep -q "data"; then
                    # Binary/DER format - convert to PEM
                    ISSUER_CA=$(openssl x509 -inform DER -in "$CA_TEMP_FILE" -outform PEM 2>/dev/null)
                else
                    # Already PEM format
                    ISSUER_CA=$(cat "$CA_TEMP_FILE")
                fi
                
                if [ -n "$ISSUER_CA" ] && echo "$ISSUER_CA" | grep -q "BEGIN CERTIFICATE"; then
                    CA_CERTS_COLLECTED="$ISSUER_CA"
                    ISSUER_CN=$(echo "$ISSUER_CA" | openssl x509 -noout -subject 2>/dev/null | sed 's/.*CN = //' | sed 's/,.*//')
                    print_success "Downloaded issuer CA: $ISSUER_CN"
                    
                    # Try to get the root CA if this is an intermediate
                    ROOT_AIA=$(echo "$ISSUER_CA" | openssl x509 -noout -text 2>/dev/null | \
                        grep -A1 "CA Issuers" | grep -oE 'http://[^[:space:]]+\.crt' | head -1)
                    if [ -n "$ROOT_AIA" ] && [ "$ROOT_AIA" != "$AIA_URL" ]; then
                        print_status "Found root CA URL: $ROOT_AIA"
                        ROOT_TEMP=$(mktemp)
                        if curl -sSf -o "$ROOT_TEMP" "$ROOT_AIA" 2>/dev/null; then
                            if file "$ROOT_TEMP" 2>/dev/null | grep -q "data"; then
                                ROOT_CA=$(openssl x509 -inform DER -in "$ROOT_TEMP" -outform PEM 2>/dev/null)
                            else
                                ROOT_CA=$(cat "$ROOT_TEMP")
                            fi
                            if [ -n "$ROOT_CA" ] && echo "$ROOT_CA" | grep -q "BEGIN CERTIFICATE"; then
                                CA_CERTS_COLLECTED="$CA_CERTS_COLLECTED
$ROOT_CA"
                                ROOT_CN=$(echo "$ROOT_CA" | openssl x509 -noout -subject 2>/dev/null | sed 's/.*CN = //' | sed 's/,.*//')
                                print_success "Downloaded root CA: $ROOT_CN"
                            fi
                        fi
                        rm -f "$ROOT_TEMP" 2>/dev/null
                    fi
                else
                    print_warning "Downloaded file is not a valid certificate"
                fi
            else
                print_warning "Could not download CA from $AIA_URL"
                print_warning "You may need to manually provide the CA certificate"
            fi
            rm -f "$CA_TEMP_FILE" 2>/dev/null
        else
            print_warning "No CA download URL found in certificate"
            print_warning "Will try other methods to find CA..."
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Source 2: Kubeconfig certificate-authority-data (OpenShift internal CAs)
# ─────────────────────────────────────────────────────────────────────────────
# This contains the CAs that the cluster administrator configured
# Usually OpenShift internal CAs for self-signed setups
KUBECONFIG_CA=""
CA_DATA=$($CLI_TOOL config view --raw --minify -o jsonpath='{{.clusters[0].cluster.certificate-authority-data}}' 2>/dev/null || echo "")
if [ -n "$CA_DATA" ]; then
    KUBECONFIG_CA=$(echo "$CA_DATA" | base64 -d 2>/dev/null)
    if [ -n "$KUBECONFIG_CA" ]; then
        if [ -z "$CA_CERTS_COLLECTED" ]; then
            CA_CERTS_COLLECTED="$KUBECONFIG_CA"
            print_success "CA Certificate retrieved from kubeconfig"
        else
            # Append if not already included (avoid duplicates)
            if ! echo "$CA_CERTS_COLLECTED" | grep -q "$(echo "$KUBECONFIG_CA" | head -5)"; then
                CA_CERTS_COLLECTED="$CA_CERTS_COLLECTED
$KUBECONFIG_CA"
                print_success "Added kubeconfig CA to bundle"
            fi
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Source 3: ServiceAccount token secret (cluster internal CA)
# ─────────────────────────────────────────────────────────────────────────────
SA_CA=""
SA_CA_DATA=$($CLI_TOOL get secret $SA_NAME-token -n $NAMESPACE -o jsonpath='{{.data.ca\\.crt}}' 2>/dev/null || echo "")
if [ -n "$SA_CA_DATA" ]; then
    SA_CA=$(echo "$SA_CA_DATA" | base64 -d 2>/dev/null)
    if [ -n "$SA_CA" ]; then
        if [ -z "$CA_CERTS_COLLECTED" ]; then
            CA_CERTS_COLLECTED="$SA_CA"
            print_success "CA Certificate retrieved from token secret"
        else
            # Check if this adds new certs
            if ! echo "$CA_CERTS_COLLECTED" | grep -q "$(echo "$SA_CA" | head -5)"; then
                CA_CERTS_COLLECTED="$CA_CERTS_COLLECTED
$SA_CA"
                print_success "Added ServiceAccount CA to bundle"
            fi
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Final CA Bundle
# ─────────────────────────────────────────────────────────────────────────────
if [ -n "$CA_CERTS_COLLECTED" ]; then
    CA_CERT_DECODED="$CA_CERTS_COLLECTED"
    # Count total CA certs in bundle
    TOTAL_CAS=$(echo "$CA_CERT_DECODED" | grep -c "BEGIN CERTIFICATE" || echo "0")
    print_success "CA bundle ready with $TOTAL_CAS certificate(s)"
else
    print_warning "Could not retrieve CA Certificate automatically."
    print_warning "Options:"
    print_warning "  1. Enable 'Skip TLS Verify' in Flowfish UI"
    print_warning "  2. Manually provide CA certificate (see commands below)"
fi

# Inspector Gadget Namespace (used by Flowfish for kubectl gadget commands)
# NOTE: gadget_endpoint is no longer needed - Flowfish uses kubectl gadget via K8s API
print_success "Inspector Gadget namespace: $NAMESPACE"

# ═══════════════════════════════════════════════════════════════════════════
# PART 4: Output Connection Details for Flowfish UI
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                           ║"
echo "║   ✅ SETUP COMPLETE - Copy these values to Flowfish UI                    ║"
echo "║                                                                           ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 📌 FLOWFISH UI - ADD CLUSTER FORM                                          │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ Connection Type:     Token                                                  │"
echo "│                                                                             │"
echo "│ ─────────────────────────────────────────────────────────────────────────── │"
echo "│                                                                             │"
echo "│ API Server URL:                                                             │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "$API_SERVER"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ Service Account Token:                                                      │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "$SA_TOKEN"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ Inspector Gadget Namespace:                                                 │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "$NAMESPACE"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ CA Certificate:                                                               │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
if [ -n "$CA_CERT_DECODED" ]; then
    echo "$CA_CERT_DECODED"
else
    echo "(Not retrieved automatically - use manual command below or enable 'Skip TLS Verify')"
fi
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 🔒 SECURITY SUMMARY                                                         │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ ✅ ServiceAccount: $SA_NAME (READ-ONLY)"
echo "│ ✅ Permissions: GET, LIST, WATCH only (no write access)"
echo "│ ✅ Token Validity: 1 year"
echo "│ ✅ Namespace: $NAMESPACE"
if [ "$USE_PERSISTENT_STORAGE" = true ]; then
    echo "│ ✅ Storage: Persistent (StorageClass: $STORAGE_CLASS)"
    echo "│    - OCI volume: 10Gi per node"
    echo "│    - WASM cache: 5Gi per node"
else
    echo "│ ⚠️  Storage: emptyDir (ephemeral - data lost on pod restart)"
fi
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 📝 MANUAL COMMANDS (if values above are empty)                              │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ Get Token:                                                                  │"
echo "│   $CLI_TOOL create token $SA_NAME -n $NAMESPACE --duration=8760h            │"
echo "│                                                                             │"
echo "│ Get CA Certificate (choose based on your environment):                      │"
echo "│                                                                             │"
echo "│ Option 1 - From API Server connection (Corporate PKI):                      │"
echo "│   echo | openssl s_client -connect $API_HOST:$API_PORT -showcerts 2>/dev/null | sed -n '/BEGIN/,/END/p'"
echo "│                                                                             │"
echo "│ Option 2 - From kubeconfig (Self-signed/Internal):                          │"
echo "│   $CLI_TOOL config view --raw -o jsonpath='{{.clusters[0].cluster.certificate-authority-data}}' | base64 -d"
echo "│                                                                             │"
echo "│ Option 3 - From ConfigMap (Kubernetes internal):                            │"
echo "│   $CLI_TOOL get configmap kube-root-ca.crt -n $NAMESPACE -o jsonpath='{{.data.ca\\.crt}}'"
echo "│                                                                             │"
echo "│ Option 4 - From ServiceAccount secret:                                      │"
echo "│   $CLI_TOOL get secret $SA_NAME-token -n $NAMESPACE -o jsonpath='{{.data.ca\\.crt}}' | base64 -d"
echo "│                                                                             │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 🔍 VERIFICATION COMMANDS                                                    │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ Check Gadget pods:    $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
echo "│ Check ServiceAccount: $CLI_TOOL get sa $SA_NAME -n $NAMESPACE"
echo "│ View Gadget logs:     $CLI_TOOL logs -l app=inspektor-gadget -n $NAMESPACE --tail=20"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
print_success "Setup complete! Copy the values above to Flowfish UI and click 'Test Connection'"
echo ""
'''
        
        logger.info("Generated complete setup script", provider=provider)
        
        return script
        
    except Exception as e:
        logger.error("Failed to generate setup script", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate script: {str(e)}"
        )


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: int):
    """Get cluster by ID"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_namespace, gadget_endpoint,
               gadget_health_status, gadget_version, status,
               total_nodes, total_pods, total_namespaces,
               k8s_version, created_at, updated_at
        FROM clusters
        WHERE id = :cluster_id
        """
        
        cluster = await database.fetch_one(query, {"cluster_id": cluster_id})
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        return dict(cluster)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get cluster failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cluster: {str(e)}"
        )


@router.patch("/clusters/{cluster_id}")
async def update_cluster(cluster_id: int, cluster_data: ClusterUpdate):
    """
    Update cluster configuration.
    
    All fields are optional - only provided fields will be updated.
    Sensitive fields (token, kubeconfig, ca_cert) are only updated if explicitly provided.
    Empty strings for sensitive fields are ignored to prevent accidental clearing.
    """
    try:
        # Check if cluster exists
        existing = await database.fetch_one(
            "SELECT id, name, connection_type FROM clusters WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        # Build update query dynamically
        updates = []
        params = {"cluster_id": cluster_id}
        
        # Basic fields
        if cluster_data.name is not None:
            # Check if new name conflicts with another cluster
            if cluster_data.name != existing["name"]:
                name_check = await database.fetch_one(
                    "SELECT id FROM clusters WHERE name = :name AND id != :cluster_id AND status != 'deleted'",
                    {"name": cluster_data.name, "cluster_id": cluster_id}
                )
                if name_check:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cluster with name '{cluster_data.name}' already exists"
                    )
            updates.append("name = :name")
            params["name"] = cluster_data.name
            
        if cluster_data.description is not None:
            updates.append("description = :description")
            params["description"] = cluster_data.description
            
        if cluster_data.environment is not None:
            updates.append("environment = :environment")
            params["environment"] = cluster_data.environment
            
        if cluster_data.provider is not None:
            updates.append("provider = :provider")
            params["provider"] = cluster_data.provider
            
        if cluster_data.region is not None:
            updates.append("region = :region")
            params["region"] = cluster_data.region
            
        if cluster_data.api_server_url is not None:
            updates.append("api_server_url = :api_server_url")
            params["api_server_url"] = cluster_data.api_server_url
            
        if cluster_data.gadget_namespace is not None:
            updates.append("gadget_namespace = :gadget_namespace")
            params["gadget_namespace"] = cluster_data.gadget_namespace
            
        if cluster_data.status is not None:
            updates.append("status = :status")
            params["status"] = cluster_data.status
            
        if cluster_data.skip_tls_verify is not None:
            updates.append("skip_tls_verify = :skip_tls_verify")
            params["skip_tls_verify"] = cluster_data.skip_tls_verify
        
        # Sensitive fields - only update if non-empty value provided
        # This prevents accidental clearing of credentials
        if cluster_data.token is not None and cluster_data.token.strip():
            updates.append("token = :token")
            params["token"] = cluster_data.token
            
        if cluster_data.kubeconfig is not None and cluster_data.kubeconfig.strip():
            updates.append("kubeconfig = :kubeconfig")
            params["kubeconfig"] = cluster_data.kubeconfig
            
        if cluster_data.ca_cert is not None and cluster_data.ca_cert.strip():
            updates.append("ca_cert = :ca_cert")
            params["ca_cert"] = cluster_data.ca_cert
        
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        # Always update updated_at
        updates.append("updated_at = NOW()")
        
        query = f"""
        UPDATE clusters 
        SET {', '.join(updates)}
        WHERE id = :cluster_id
        """
        
        await database.execute(query, params)
        
        # Return updated cluster (without sensitive fields)
        updated = await database.fetch_one(
            """SELECT id, name, description, environment, provider, region,
                      connection_type, api_server_url, gadget_namespace, gadget_endpoint,
                      gadget_health_status, gadget_version, status, 
                      total_nodes, total_pods, total_namespaces, k8s_version,
                      skip_tls_verify, created_at, updated_at
               FROM clusters WHERE id = :cluster_id""",
            {"cluster_id": cluster_id}
        )
        
        logger.info("Cluster updated", cluster_id=cluster_id, updated_fields=list(params.keys()))
        
        return {
            "message": "Cluster updated successfully",
            "cluster": dict(updated) if updated else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update cluster failed", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cluster: {str(e)}"
        )


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: int):
    """Delete cluster (soft delete)"""
    try:
        # Check if cluster exists
        existing = await database.fetch_one(
            "SELECT id, name FROM clusters WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        # Soft delete - set status to 'deleted'
        await database.execute(
            "UPDATE clusters SET status = 'deleted', updated_at = NOW() WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        logger.info("Cluster deleted", cluster_id=cluster_id, cluster_name=existing["name"])
        
        return {
            "message": f"Cluster '{existing['name']}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete cluster failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete cluster: {str(e)}"
        )


@router.post("/clusters/{cluster_id}/sync")
async def sync_cluster(cluster_id: int):
    """Sync cluster information (workloads, nodes, etc.)"""
    try:
        cluster = await database.fetch_one(
            """SELECT id, name, connection_type, api_server_url, kubeconfig_encrypted,
                      token_encrypted, ca_cert_encrypted, skip_tls_verify, gadget_namespace
               FROM clusters WHERE id = :cluster_id AND status = 'active'""",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active cluster {cluster_id} not found"
            )
        
        logger.info("Starting cluster sync", cluster_id=cluster_id, cluster_name=cluster['name'])
        
        # Use unified ClusterConnectionManager for all connection types
        cluster_info = await cluster_connection_manager.get_cluster_info(cluster_id)
        
        logger.info("Starting gadget health check via ClusterConnectionManager", cluster_id=cluster_id)
        try:
            gadget_health = await cluster_connection_manager.check_gadget_health(cluster_id)
            logger.info("Gadget health check result", 
                       health_status=gadget_health.get("health_status"),
                       version=gadget_health.get("version"),
                       error=gadget_health.get("error"),
                       pods_ready=gadget_health.get("pods_ready"),
                       pods_total=gadget_health.get("pods_total"))
        except Exception as health_err:
            logger.error("Gadget health check exception", error=str(health_err))
            gadget_health = {"health_status": "unknown", "error": str(health_err)}
        
        # Update cluster with fetched info
        # Even if cluster_info has error, we still update gadget health
        cluster_info_error = cluster_info.get("error")
        
        if not cluster_info_error:
            # Full sync - both cluster info and gadget health available
            await database.execute(
                """UPDATE clusters SET 
                   total_nodes = :total_nodes,
                   total_pods = :total_pods,
                   total_namespaces = :total_namespaces,
                   k8s_version = :k8s_version,
                   gadget_health_status = :gadget_health_status,
                   gadget_version = :gadget_version,
                   updated_at = NOW()
                   WHERE id = :cluster_id""",
                {
                    "cluster_id": cluster_id,
                    "total_nodes": cluster_info.get("total_nodes", 0),
                    "total_pods": cluster_info.get("total_pods", 0),
                    "total_namespaces": cluster_info.get("total_namespaces", 0),
                    "k8s_version": cluster_info.get("k8s_version"),
                    "gadget_health_status": gadget_health.get("health_status", "unknown"),
                    "gadget_version": gadget_health.get("version")
                }
            )
            
            logger.info("Cluster sync completed", 
                       cluster_id=cluster_id,
                       nodes=cluster_info.get("total_nodes", 0),
                       pods=cluster_info.get("total_pods", 0),
                       namespaces=cluster_info.get("total_namespaces", 0))
            
            # Proactively refresh cache after successful sync
            try:
                await cluster_cache_service.refresh_cluster_cache(cluster_id)
                logger.info("Cache refreshed after sync", cluster_id=cluster_id)
            except Exception as cache_err:
                logger.warning("Cache refresh failed after sync", 
                             cluster_id=cluster_id, 
                             error=str(cache_err))
            
            return {
                "message": f"Cluster '{cluster['name']}' synced successfully",
                "status": "completed",
                "resources": {
                    "nodes": cluster_info.get("total_nodes", 0),
                    "pods": cluster_info.get("total_pods", 0),
                    "namespaces": cluster_info.get("total_namespaces", 0)
                },
                "gadget_health": gadget_health.get("health_status", "unknown"),
                "gadget_details": {
                    "version": gadget_health.get("version"),
                    "error": gadget_health.get("error"),
                    "pods_ready": gadget_health.get("pods_ready", 0),
                    "pods_total": gadget_health.get("pods_total", 0),
                    "details": gadget_health.get("details", {})
                }
            }
        else:
            # Partial sync - cluster info failed but gadget health may be available
            logger.warning("Cluster info fetch failed, updating gadget health only",
                          cluster_id=cluster_id,
                          error=cluster_info_error)
            
            # Still update gadget health even if cluster info failed
            await database.execute(
                """UPDATE clusters SET 
                   gadget_health_status = :gadget_health_status,
                   gadget_version = :gadget_version,
                   updated_at = NOW()
                   WHERE id = :cluster_id""",
                {
                    "cluster_id": cluster_id,
                    "gadget_health_status": gadget_health.get("health_status", "unknown"),
                    "gadget_version": gadget_health.get("version")
                }
            )
            
            # Return partial success instead of 500 error
            return {
                "message": f"Cluster '{cluster['name']}' partially synced - cluster info unavailable",
                "status": "partial",
                "warning": f"Cluster info fetch failed: {cluster_info_error}",
                "resources": None,
                "gadget_health": gadget_health.get("health_status", "unknown"),
                "gadget_details": {
                    "version": gadget_health.get("version"),
                    "error": gadget_health.get("error"),
                    "pods_ready": gadget_health.get("pods_ready", 0),
                    "pods_total": gadget_health.get("pods_total", 0),
                    "details": gadget_health.get("details", {})
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cluster sync failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync cluster: {str(e)}"
        )


class ConnectionTestRequest(BaseModel):
    """Request model for connection test"""
    connection_type: str  # 'in-cluster', 'kubeconfig', 'token'
    api_server_url: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None
    skip_tls_verify: Optional[bool] = False
    gadget_namespace: str  # Namespace where gadget is deployed (REQUIRED from UI)


@router.post("/clusters/test-connection")
async def test_cluster_connection(test_data: ConnectionTestRequest):
    """
    Test cluster connection before creating.
    
    This endpoint allows users to verify their cluster credentials
    and Inspector Gadget endpoint before creating a cluster.
    
    Uses ClusterConnectionManager.test_connection() for unified logic.
    Returns detailed connection status and any errors.
    """
    try:
        # Validate required fields based on connection type
        normalized_type = test_data.connection_type.replace('_', '-').lower() if test_data.connection_type else ""
        
        if normalized_type == "token":
            if not test_data.api_server_url:
                raise ValueError("API Server URL is required for token authentication")
            if not test_data.token:
                raise ValueError("Token is required for token authentication")
        
        # Use ClusterConnectionManager for unified connection testing
        test_result = await cluster_connection_manager.test_connection(
            connection_type=test_data.connection_type,
            api_server_url=test_data.api_server_url,
            token=test_data.token,
            ca_cert=test_data.ca_cert,
            kubeconfig=test_data.token if normalized_type == "kubeconfig" else None,
            skip_tls_verify=test_data.skip_tls_verify or False,
            gadget_namespace=test_data.gadget_namespace
        )
        
        # Add recommendations based on errors
        result = {
            "cluster_connection": test_result["cluster_connection"],
            "gadget_connection": test_result["gadget_connection"],
            "overall_status": test_result["overall_status"],
            "recommendations": []
        }
        
        # Add cluster connection recommendations
        if result["cluster_connection"]["status"] == "failed":
            error = result["cluster_connection"].get("error", "").lower()
            if "certificate" in error or "ssl" in error:
                result["recommendations"].append(
                    "Certificate verification failed. Try enabling 'Skip TLS Verify' or provide a valid CA certificate."
                )
            elif "unauthorized" in error or "401" in error:
                result["recommendations"].append(
                    "Authentication failed. Verify your token has the correct permissions."
                )
            elif "connection" in error or "timeout" in error:
                result["recommendations"].append(
                    "Cannot connect to the API server. Verify the URL and network connectivity."
                )
            elif "token" in error or "required" in error:
                result["recommendations"].append(
                    "Please provide the required authentication credentials."
                )
        
        # Add gadget connection recommendations
        if result["gadget_connection"]["status"] == "failed":
            error = result["gadget_connection"].get("error", "")
            result["recommendations"].append(
                f"Inspector Gadget pods not healthy in namespace '{test_data.gadget_namespace}'. Check DaemonSet status."
            )
        elif result["gadget_connection"]["status"] == "warning":
            result["recommendations"].append(
                "Inspector Gadget may be degraded. Check the DaemonSet status on the cluster."
            )
        elif result["gadget_connection"]["status"] == "skipped":
            result["recommendations"].append(
                "Provide an Inspector Gadget endpoint for full functionality."
            )
        
        logger.info("Connection test completed", 
                   connection_type=test_data.connection_type,
                   overall_status=result["overall_status"])
        
        return result
        
    except Exception as e:
        logger.error("Connection test failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


