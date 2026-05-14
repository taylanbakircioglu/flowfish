"""
Clusters router - Simplified for MVP
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
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
from utils.encryption import encrypt_data, decrypt_data
from config import settings as app_settings
from utils.jwt_utils import get_current_user

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
    beyla_namespace: Optional[str] = None

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
    beyla_namespace: Optional[str] = None

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
    beyla_namespace: Optional[str] = None
    beyla_health_status: Optional[str] = None
    beyla_version: Optional[str] = None
    l7_collector_endpoint: Optional[str] = None
    beyla_last_check: Optional[datetime] = None
    status: Optional[str] = None
    total_nodes: Optional[int] = None
    total_pods: Optional[int] = None
    total_namespaces: Optional[int] = None
    k8s_version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@router.get("/clusters")
async def get_clusters(
    is_active: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get list of clusters"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_namespace, gadget_endpoint,
               gadget_health_status, gadget_version,
               beyla_namespace, beyla_health_status, beyla_version,
               l7_collector_endpoint, beyla_last_check,
               status,
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
            "count": len(clusters),
            "supported_gadget_version": app_settings.GADGET_SUPPORTED_VERSION,
            "supported_beyla_version": getattr(app_settings, 'BEYLA_SUPPORTED_VERSION', 'v3.9.5')
        }
        
    except Exception as e:
        logger.error("Get clusters failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve clusters: {str(e)}"
        )


@router.post("/clusters", status_code=status.HTTP_201_CREATED)
async def create_cluster(
    cluster_data: ClusterCreate,
    current_user: dict = Depends(get_current_user),
):
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
                    gadget_health_status = 'not_installed',
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
                beyla_namespace,
                skip_tls_verify, status, gadget_health_status, created_at
            )
            VALUES (
                :name, :description, :environment, :provider, :region,
                :connection_type, :api_server_url, :kubeconfig,
                :token, :ca_cert, :gadget_namespace,
                :beyla_namespace,
                :skip_tls_verify, 'active', 'not_installed', NOW()
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
                "beyla_namespace": cluster_data.beyla_namespace,
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

                beyla_health = {"health_status": "not_installed", "version": ""}
                try:
                    row = await database.fetch_one(
                        "SELECT beyla_namespace, gadget_namespace FROM clusters WHERE id = :id",
                        {"id": cid},
                    )
                    stored_beyla_ns = (row["beyla_namespace"] if row else "") or ""
                    beyla_ns = stored_beyla_ns or (row["gadget_namespace"] if row else "") or ""
                    if beyla_ns:
                        beyla_health = await cluster_connection_manager.check_beyla_health(cid, beyla_ns)
                        if not stored_beyla_ns and beyla_health.get("health_status") in ("healthy", "degraded"):
                            await database.execute(
                                "UPDATE clusters SET beyla_namespace = :ns WHERE id = :id",
                                {"ns": beyla_ns, "id": cid},
                            )
                            logger.info("Background: auto-discovered beyla_namespace", cluster_id=cid, namespace=beyla_ns)
                except Exception as be:
                    logger.debug("Background: Beyla health check failed: %s", be)

                if not cluster_info.get("error"):
                    update_query = """
                    UPDATE clusters
                    SET total_nodes = :total_nodes,
                        total_pods = :total_pods,
                        total_namespaces = :total_namespaces,
                        k8s_version = :k8s_version,
                        gadget_health_status = :gadget_health_status,
                        gadget_version = :gadget_version,
                        beyla_health_status = :beyla_health_status,
                        beyla_version = :beyla_version,
                        beyla_last_check = NOW(),
                        updated_at = NOW()
                    WHERE id = :cluster_id
                    """
                    
                    await database.execute(update_query, {
                        "cluster_id": cid,
                        "total_nodes": cluster_info.get("total_nodes", 0),
                        "total_pods": cluster_info.get("total_pods", 0),
                        "total_namespaces": cluster_info.get("total_namespaces", 0),
                        "k8s_version": cluster_info.get("k8s_version"),
                        "gadget_health_status": gadget_health.get("health_status", "not_installed"),
                        "gadget_version": gadget_health.get("version"),
                        "beyla_health_status": beyla_health.get("health_status", "not_installed"),
                        "beyla_version": beyla_health.get("version", ""),
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


def generate_uninstall_script(cli_tool: str) -> str:
    """Generate L4 (Gadget-only) uninstall script.

    IMPORTANT: This script NEVER removes the shared flowfish-remote-reader
    ServiceAccount, Secret, ClusterRole, or ClusterRoleBinding because they
    are used by L7 agents, cluster sync, and health checks.  Only
    Inspector-Gadget-specific resources are removed.
    """
    return f'''#!/bin/bash
#
# ============================================================================
#  L4 Agent Cleanup - Inspector Gadget ONLY
#
#  This script SAFELY removes ONLY Inspector Gadget resources:
#  - Inspector Gadget DaemonSet, Service, ConfigMap, ServiceAccount
#  - Gadget RBAC (ClusterRole/Binding if unused by other namespaces)
#  - Gadget SCC (OpenShift only, if unused)
#
#  PRESERVED (shared resources):
#  - flowfish-remote-reader ServiceAccount (used by L7 + cluster sync)
#  - flowfish-remote-reader ClusterRole/Binding
#  - Namespace
#  - Beyla (L7) and flowfish-l7-collector
# ============================================================================
#
# Usage:
#   chmod +x cleanup-l4-agent.sh
#   ./cleanup-l4-agent.sh <namespace>
#   ./cleanup-l4-agent.sh              # Interactive mode
#

CLI_TOOL="{cli_tool}"

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
BOLD='\\033[1m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}

echo ""
echo "============================================================"
echo "  L4 Agent Cleanup - Inspector Gadget"
echo "============================================================"
echo ""

# Pre-flight
if ! command -v $CLI_TOOL &> /dev/null; then
    print_error "$CLI_TOOL CLI is not installed or not in PATH"
    exit 1
fi
print_success "$CLI_TOOL CLI found"

if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &> /dev/null; then
        print_error "Not logged in. Run 'oc login' first."
        exit 1
    fi
    print_success "Logged in as: $($CLI_TOOL whoami)"
else
    if ! $CLI_TOOL cluster-info &> /dev/null 2>&1; then
        print_error "Cannot connect to cluster. Check your kubeconfig."
        exit 1
    fi
    print_success "Cluster connection OK"
fi

# Namespace
if [ -n "${{1:-}}" ]; then
    NAMESPACE="$1"
else
    read -p "Enter namespace: " NAMESPACE
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi

# Safety check
if ! $CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" &>/dev/null; then
    print_error "Inspector Gadget DaemonSet not found in namespace '$NAMESPACE'"
    exit 1
fi

# Detect L7 agents
L7_ACTIVE="no"
if $CLI_TOOL get daemonset beyla -n "$NAMESPACE" &>/dev/null 2>&1; then L7_ACTIVE=yes; fi
if $CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" &>/dev/null 2>&1; then L7_ACTIVE=yes; fi

echo ""
echo "The following L4 resources will be DELETED from namespace '$NAMESPACE':"
echo "------------------------------------------------------------"
echo "  - DaemonSet: inspektor-gadget"
echo "  - Service: inspektor-gadget"
echo "  - ConfigMap: inspektor-gadget-config"
echo "  - ServiceAccount: inspektor-gadget"
echo "  - ClusterRole/Binding: inspektor-gadget (if unused)"
echo "  - Role/RoleBinding: flowfish-gadget-access (namespace-scoped)"
echo "------------------------------------------------------------"
echo "  PRESERVED: flowfish-remote-reader ServiceAccount (shared)"
echo "  PRESERVED: flowfish-remote-reader ClusterRole/Binding (shared)"
echo "  PRESERVED: Namespace"
if [ "$L7_ACTIVE" = "yes" ]; then
    echo "  PRESERVED: Beyla / L7 Collector (detected running)"
fi
echo ""
read -p "Proceed? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_warning "Cancelled."
    exit 0
fi

echo ""
print_status "Removing Inspector Gadget resources..."
$CLI_TOOL delete daemonset inspektor-gadget -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete service inspektor-gadget -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete configmap inspektor-gadget-config -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete sa inspektor-gadget -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
print_success "Gadget resources removed"

print_status "Removing gadget namespace-scoped RBAC..."
$CLI_TOOL delete role flowfish-gadget-access -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete rolebinding flowfish-gadget-access -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
print_success "Gadget RBAC removed"

print_status "Cleaning up gadget cluster-scoped resources..."
$CLI_TOOL delete clusterrolebinding inspektor-gadget-$NAMESPACE --ignore-not-found=true 2>/dev/null

GADGET_BINDINGS=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="inspektor-gadget")].metadata.name}}' 2>/dev/null)
if [ -z "$GADGET_BINDINGS" ]; then
    $CLI_TOOL delete clusterrole inspektor-gadget --ignore-not-found=true 2>/dev/null
    print_success "Gadget ClusterRole removed (no longer in use)"
else
    print_warning "Gadget ClusterRole still in use by other namespaces, skipping"
fi

print_warning "flowfish-remote-reader SA/RBAC preserved (shared with L7 + cluster sync)"

# SCC cleanup (OpenShift only)
if [ "$CLI_TOOL" = "oc" ]; then
    $CLI_TOOL adm policy remove-scc-from-user inspektor-gadget-scc -z inspektor-gadget -n "$NAMESPACE" 2>/dev/null || true
    OTHER_USERS=$($CLI_TOOL get scc inspektor-gadget-scc -o jsonpath='{{.users[*]}}' 2>/dev/null || echo "")
    SCC_STILL_USED="no"
    for U in $OTHER_USERS; do
        if echo "$U" | grep -qF ":$NAMESPACE:"; then continue; fi
        SCC_STILL_USED="yes"
        break
    done
    if [ "$SCC_STILL_USED" = "no" ]; then
        print_status "Removing SCC inspektor-gadget-scc..."
        $CLI_TOOL delete scc inspektor-gadget-scc --ignore-not-found=true 2>/dev/null
        print_success "Gadget SCC removed"
    else
        print_warning "SCC inspektor-gadget-scc still in use by other namespaces, skipping"
    fi
fi

echo ""
echo "============================================================"
echo "  L4 AGENT CLEANUP COMPLETE"
echo ""
echo "  Namespace '$NAMESPACE' was preserved (NOT deleted)"
echo "  Beyla (L7) and other workloads were NOT affected"
echo "  flowfish-remote-reader SA was preserved (shared resource)"
echo ""
echo "  Note: Trace CRD was NOT removed. To remove manually:"
echo "  $CLI_TOOL delete crd traces.gadget.kinvolk.io"
echo ""
if [ "$L7_ACTIVE" = "no" ]; then
    echo "  To fully disconnect this cluster from Flowfish:"
    echo "  $CLI_TOOL delete sa flowfish-remote-reader -n $NAMESPACE"
    echo "  $CLI_TOOL delete clusterrolebinding flowfish-remote-reader-$NAMESPACE --ignore-not-found"
    echo "  $CLI_TOOL delete clusterrole flowfish-remote-reader --ignore-not-found"
    echo "  $CLI_TOOL delete namespace $NAMESPACE"
fi
echo "============================================================"
echo ""
'''


def _generate_l7_uninstall_script(cli_tool: str) -> str:
    """Generate L7 (Beyla + L7 Collector) uninstall script.

    IMPORTANT: This script NEVER removes the shared flowfish-remote-reader
    ServiceAccount, Secret, ClusterRole, or ClusterRoleBinding because they
    are used by L4 agents, cluster sync, and health checks.  Only
    Beyla/Collector-specific resources are removed.
    """
    return f'''#!/bin/bash
#
# ============================================================================
#  L7 Agent Cleanup - Grafana Beyla + flowfish-l7-collector
#
#  This script SAFELY removes ONLY:
#  - Beyla DaemonSet, ConfigMap, ServiceAccount, RBAC
#  - flowfish-l7-collector Deployment, Service, ServiceAccount, RBAC
#  - Beyla SCC (OpenShift only, if not used by other namespaces)
#
#  PRESERVED (shared resources):
#  - flowfish-remote-reader ServiceAccount (used by L4 + cluster sync)
#  - flowfish-remote-reader ClusterRole/Binding
#  - Namespace
#  - Inspector Gadget (L4) and other workloads
# ============================================================================
#
# Usage:
#   chmod +x cleanup-l7-agent.sh
#   ./cleanup-l7-agent.sh <namespace>
#   ./cleanup-l7-agent.sh              # Interactive mode
#

CLI_TOOL="{cli_tool}"
if ! command -v $CLI_TOOL &> /dev/null; then
    echo "[ERROR] $CLI_TOOL not found in PATH"
    exit 1
fi

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}

echo ""
echo "============================================================"
echo "  L7 Agent Cleanup - Grafana Beyla + L7 Collector"
echo "============================================================"
echo ""

# Pre-flight
print_status "Using CLI tool: $CLI_TOOL"

if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &> /dev/null; then
        print_error "Not logged in. Run 'oc login' first."
        exit 1
    fi
    print_success "Logged in as: $($CLI_TOOL whoami)"
else
    if ! $CLI_TOOL cluster-info &> /dev/null 2>&1; then
        print_error "Cannot connect to cluster. Check your kubeconfig."
        exit 1
    fi
    print_success "Cluster connection OK"
fi

# Namespace
if [ -n "${{1:-}}" ]; then
    NAMESPACE="$1"
else
    read -p "Enter namespace where Beyla is installed: " NAMESPACE
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi

# Safety check
if $CLI_TOOL get daemonset beyla -n "$NAMESPACE" &>/dev/null; then BEYLA_EXISTS=yes; else BEYLA_EXISTS=no; fi
if $CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" &>/dev/null || $CLI_TOOL get deployment l7-collector -n "$NAMESPACE" &>/dev/null; then COLLECTOR_EXISTS=yes; else COLLECTOR_EXISTS=no; fi

if [ "$BEYLA_EXISTS" = "no" ] && [ "$COLLECTOR_EXISTS" = "no" ]; then
    print_error "No L7 agent (Beyla/Collector) found in namespace '$NAMESPACE'"
    exit 1
fi

# Detect L4 agents
L4_ACTIVE="no"
if $CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" &>/dev/null 2>&1; then L4_ACTIVE=yes; fi

echo ""
echo "The following L7 resources will be DELETED from namespace '$NAMESPACE':"
echo "------------------------------------------------------------"
if [ "$BEYLA_EXISTS" = "yes" ]; then
    BEYLA_IMG=$($CLI_TOOL get daemonset beyla -n "$NAMESPACE" -o jsonpath='{{.spec.template.spec.containers[?(@.name=="beyla")].image}}' 2>/dev/null || echo "unknown")
    echo "  - DaemonSet: beyla ($BEYLA_IMG)"
    echo "  - ConfigMap: beyla-config"
    echo "  - ServiceAccount: beyla"
    echo "  - ClusterRole/Binding: beyla (if unused)"
fi
if [ "$COLLECTOR_EXISTS" = "yes" ]; then
    COLL_IMG=$($CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || \
              $CLI_TOOL get deployment l7-collector -n "$NAMESPACE" -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "unknown")
    echo "  - Deployment: l7-collector / flowfish-l7-collector ($COLL_IMG)"
    echo "  - Service: flowfish-l7-collector"
    echo "  - ServiceAccount: l7-collector / flowfish-l7-collector"
    echo "  - ClusterRole/Binding: flowfish-l7-collector-role (if unused)"
fi
echo "------------------------------------------------------------"
echo "  PRESERVED: flowfish-remote-reader ServiceAccount (shared)"
echo "  PRESERVED: flowfish-remote-reader ClusterRole/Binding (shared)"
echo "  PRESERVED: Namespace"
if [ "$L4_ACTIVE" = "yes" ]; then
    echo "  PRESERVED: Inspector Gadget / L4 Agent (detected running)"
fi
echo ""
read -p "Proceed? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_warning "Cancelled."
    exit 0
fi

echo ""
print_status "Removing Beyla DaemonSet and resources..."
$CLI_TOOL delete daemonset beyla -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete configmap beyla-config -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete serviceaccount beyla -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
print_success "Beyla resources removed"

print_status "Removing L7 Collector..."
$CLI_TOOL delete deployment flowfish-l7-collector -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete deployment l7-collector -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete service flowfish-l7-collector -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete serviceaccount flowfish-l7-collector -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete serviceaccount l7-collector -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete rolebinding flowfish-l7-proxy-binding -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete role flowfish-l7-proxy -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
print_success "L7 Collector removed"

print_status "Cleaning up cluster-scoped resources..."
$CLI_TOOL delete clusterrolebinding beyla --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete clusterrolebinding beyla-role-binding --ignore-not-found=true 2>/dev/null

BEYLA_BINDINGS=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="beyla")].metadata.name}}' 2>/dev/null)
BEYLA_BINDINGS_OLD=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="beyla-role")].metadata.name}}' 2>/dev/null)
if [ -z "$BEYLA_BINDINGS" ] && [ -z "$BEYLA_BINDINGS_OLD" ]; then
    $CLI_TOOL delete clusterrole beyla --ignore-not-found=true 2>/dev/null
    $CLI_TOOL delete clusterrole beyla-role --ignore-not-found=true 2>/dev/null
    print_success "Beyla ClusterRole removed (no longer in use)"
else
    print_warning "Beyla ClusterRole still in use by other namespaces, skipping"
fi

$CLI_TOOL delete clusterrolebinding flowfish-l7-collector-role-binding --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete clusterrolebinding l7-collector-role-binding --ignore-not-found=true 2>/dev/null
$CLI_TOOL delete clusterrolebinding flowfish-l7-collector --ignore-not-found=true 2>/dev/null

COLL_BINDINGS=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="flowfish-l7-collector-role")].metadata.name}}' 2>/dev/null)
COLL_BINDINGS2=$($CLI_TOOL get clusterrolebindings -o jsonpath='{{.items[?(@.roleRef.name=="flowfish-l7-collector")].metadata.name}}' 2>/dev/null)
if [ -z "$COLL_BINDINGS" ]; then
    $CLI_TOOL delete clusterrole flowfish-l7-collector-role --ignore-not-found=true 2>/dev/null
fi
if [ -z "$COLL_BINDINGS2" ]; then
    $CLI_TOOL delete clusterrole flowfish-l7-collector --ignore-not-found=true 2>/dev/null
fi
if [ -z "$COLL_BINDINGS" ] && [ -z "$COLL_BINDINGS2" ]; then
    print_success "Collector ClusterRole removed (no longer in use)"
else
    print_warning "Collector ClusterRole still in use by other namespaces, skipping"
fi

# SCC cleanup (OpenShift only)
if [ "$CLI_TOOL" = "oc" ]; then
    $CLI_TOOL adm policy remove-scc-from-user beyla-scc -z beyla -n "$NAMESPACE" 2>/dev/null || true
    OTHER_USERS=$($CLI_TOOL get scc beyla-scc -o jsonpath='{{.users[*]}}' 2>/dev/null || echo "")
    SCC_STILL_USED="no"
    for U in $OTHER_USERS; do
        if echo "$U" | grep -qF ":$NAMESPACE:"; then continue; fi
        SCC_STILL_USED="yes"
        break
    done
    if [ "$SCC_STILL_USED" = "no" ]; then
        print_status "Removing SCC beyla-scc..."
        $CLI_TOOL delete scc beyla-scc --ignore-not-found=true 2>/dev/null
        print_success "Beyla SCC removed"
    else
        print_warning "SCC beyla-scc still in use by other namespaces, skipping"
    fi
fi

print_warning "flowfish-remote-reader SA/RBAC preserved (shared with L4 + cluster sync)"

echo ""
echo "============================================================"
echo "  L7 AGENT CLEANUP COMPLETE"
echo ""
echo "  Namespace '$NAMESPACE' was preserved (NOT deleted)"
echo "  Inspector Gadget (L4) and other workloads were NOT affected"
echo "  flowfish-remote-reader SA was preserved (shared resource)"
echo ""
if [ "$L4_ACTIVE" = "no" ]; then
    echo "  To fully disconnect this cluster from Flowfish:"
    echo "  $CLI_TOOL delete sa flowfish-remote-reader -n $NAMESPACE"
    echo "  $CLI_TOOL delete clusterrolebinding flowfish-remote-reader-$NAMESPACE --ignore-not-found"
    echo "  $CLI_TOOL delete clusterrole flowfish-remote-reader --ignore-not-found"
    echo "  $CLI_TOOL delete namespace $NAMESPACE"
fi
echo "============================================================"
echo ""
'''


async def _get_beyla_excluded_namespaces() -> list:
    """Read excluded namespaces from Beyla settings in database."""
    try:
        row = await database.fetch_one(
            "SELECT value FROM system_settings WHERE key = 'beyla_settings'"
        )
        if row:
            import json as _json
            val = row["value"]
            if isinstance(val, str):
                val = _json.loads(val)
            return val.get("default_excluded_namespaces", [])
    except Exception:
        pass
    return []


def _generate_beyla_install_script(
    cli_tool: str,
    beyla_version: str = "3.9.5",
    image_registry: str = "",
    collector_tag: str = "",
    mem_limit: str = "6Gi",
    cpu_limit: str = "2",
    bpf_volume_type: str = "hostPath",
    excluded_namespaces: list = None,
) -> str:
    """Generate Beyla + flowfish-l7-collector install script."""
    beyla_version = beyla_version.lstrip("v")
    image_registry = image_registry.strip().rstrip("/")
    default_beyla = f"{image_registry}/beyla" if image_registry else "grafana/beyla"
    default_collector = f"{image_registry}/flowfish-l7-collector" if image_registry else "flowfish/flowfish-l7-collector"
    if not collector_tag:
        collector_tag = app_settings.IMAGE_TAG

    # Base excludes cover platform/operator namespaces that should never
    # produce application-level L7 traffic. We deliberately also exclude
    # Flowfish's own namespace ($NAMESPACE, resolved at install time by the
    # generated bash script) and the Inspektor Gadget namespace so Beyla
    # does not surface long-running gadget gRPC streams (kubectl-gadget →
    # IG worker) as multi-minute "single requests" in Service Map metrics.
    # Defense in depth: flowfish-l7-collector also drops events whose
    # endpoint resolved to the synthetic `loopback` namespace, and
    # timeseries-writer re-applies the same filter before insertion.
    base_excludes = [
        "openshift-*", "kube-*", "default", "ibm-*", "ibmblockstorage",
        "external-secrets", "calico-*", "tigera-*",
        "gadget",  # Inspektor Gadget DaemonSet namespace
        "$NAMESPACE",  # Flowfish self-monitoring (resolved by install script)
    ]
    extra_excludes = excluded_namespaces or []
    all_excludes = list(dict.fromkeys(base_excludes + extra_excludes))
    exclude_yaml_lines = "\n".join(f'        - k8s_namespace: "{ns}"' for ns in all_excludes)
    return f'''#!/bin/bash
set -euo pipefail

CLI_TOOL="{cli_tool}"
DEFAULT_BEYLA_IMAGE="{default_beyla}"
DEFAULT_BEYLA_VERSION="{beyla_version}"
DEFAULT_COLLECTOR_IMAGE="{default_collector}"
DEFAULT_COLLECTOR_VERSION="{collector_tag}"
MEM_LIMIT="{mem_limit}"
CPU_LIMIT="{cpu_limit}"
BPF_VOLUME_TYPE="{bpf_volume_type}"

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
BOLD='\\033[1m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}

echo ""
echo "============================================================"
echo "  Flowfish L7 Agent Install (Grafana Beyla)"
echo "============================================================"
echo ""

# --- Pre-flight checks ---
if ! command -v $CLI_TOOL &> /dev/null; then
    print_error "$CLI_TOOL not found in PATH"
    exit 1
fi

if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &> /dev/null; then
        print_error "Not logged in. Run 'oc login' first."
        exit 1
    fi
    print_success "Logged in as: $($CLI_TOOL whoami)"
else
    if ! $CLI_TOOL cluster-info &> /dev/null 2>&1; then
        print_error "Cannot connect to cluster. Check your kubeconfig."
        exit 1
    fi
    print_success "Cluster connection OK"
fi

# --- Runtime OpenShift detection ---
# An OpenShift cluster can be operated with either `oc` or `kubectl`.
# When the cluster admin runs this script with `kubectl` against an
# OpenShift cluster, we still need to create + bind a SecurityContext
# Constraint (SCC); otherwise Beyla pods will be rejected by the
# cluster's PodSecurity admission with errors like:
#   "provider restricted-v2: .spec.securityContext.hostPID: Invalid
#    value: true: Host PID is not allowed to be used"
# We therefore detect OpenShift by probing the security.openshift.io
# API group, which is unique to OpenShift. Vanilla Kubernetes will
# return no resources for that group.
if $CLI_TOOL api-resources --api-group=security.openshift.io 2>/dev/null \
    | grep -q SecurityContextConstraints; then
    IS_OPENSHIFT="true"
    print_success "OpenShift cluster detected (security.openshift.io API present)"
else
    IS_OPENSHIFT="false"
    print_status "Vanilla Kubernetes detected (no security.openshift.io API)"
fi

# --- Namespace ---
if [ -n "${{1:-}}" ]; then
    NAMESPACE="$1"
else
    read -p "Enter namespace for Beyla: " NAMESPACE
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

# --- Auto-detect registries from existing resources ---
EXISTING_BEYLA_IMG=""
EXISTING_COLLECTOR_IMG=""

if $CLI_TOOL get daemonset beyla -n "$NAMESPACE" &>/dev/null 2>&1; then
    EXISTING_BEYLA_IMG=$($CLI_TOOL get daemonset beyla -n "$NAMESPACE" \
        -o jsonpath='{{.spec.template.spec.containers[?(@.name=="beyla")].image}}' 2>/dev/null || echo "")
fi
if $CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" &>/dev/null 2>&1; then
    EXISTING_COLLECTOR_IMG=$($CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" \
        -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "")
elif $CLI_TOOL get deployment l7-collector -n "$NAMESPACE" &>/dev/null 2>&1; then
    EXISTING_COLLECTOR_IMG=$($CLI_TOOL get deployment l7-collector -n "$NAMESPACE" \
        -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "")
fi

# --- Resolve Beyla image ---
if [ -n "$EXISTING_BEYLA_IMG" ]; then
    BEYLA_REGISTRY=$(echo "$EXISTING_BEYLA_IMG" | sed 's|:[^:]*$||')
    BEYLA_CUR_VER=$(echo "$EXISTING_BEYLA_IMG" | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' || echo "$DEFAULT_BEYLA_VERSION")
    print_status "Existing Beyla image detected: $EXISTING_BEYLA_IMG"
    echo -e "  ${{CYAN}}Beyla Registry:${{NC}} $BEYLA_REGISTRY"
    echo -e "  Press Enter to keep current registry, or enter a new one."
    read -p "  Beyla registry [$BEYLA_REGISTRY]: " INPUT_BEYLA_REG
    BEYLA_REGISTRY="${{INPUT_BEYLA_REG:-$BEYLA_REGISTRY}}"
    echo -e "  ${{CYAN}}Beyla Version:${{NC}} $BEYLA_CUR_VER (default upgrade: $DEFAULT_BEYLA_VERSION)"
    read -p "  Beyla version [$DEFAULT_BEYLA_VERSION]: " INPUT_BEYLA_VER
    BEYLA_VERSION="${{INPUT_BEYLA_VER:-$DEFAULT_BEYLA_VERSION}}"
else
    echo ""
    echo -e "${{CYAN}}Beyla Image:${{NC}} Container image for Grafana Beyla"
    echo -e "  Default: $DEFAULT_BEYLA_IMAGE"
    echo -e "  Example: harbor.example.com/flowfish/beyla"
    echo -e "  (tip: if you enter a registry prefix like 'harbor.example.com/project', /beyla is appended automatically)"
    read -p "  Beyla image (press Enter for default): " INPUT_BEYLA_REG
    BEYLA_REGISTRY="${{INPUT_BEYLA_REG:-$DEFAULT_BEYLA_IMAGE}}"
    BEYLA_VERSION="$DEFAULT_BEYLA_VERSION"
fi
# Ensure Beyla image path ends with /beyla (user may enter just the registry prefix)
case "$BEYLA_REGISTRY" in
    */beyla) ;;
    *) BEYLA_REGISTRY="${{BEYLA_REGISTRY%/}}/beyla" ;;
esac
BEYLA_IMAGE="${{BEYLA_REGISTRY}}:${{BEYLA_VERSION}}"

# --- Resolve Collector image ---
if [ -n "$EXISTING_COLLECTOR_IMG" ]; then
    COLLECTOR_REGISTRY=$(echo "$EXISTING_COLLECTOR_IMG" | sed 's|:[^:]*$||')
    COLLECTOR_CUR_VER=$(echo "$EXISTING_COLLECTOR_IMG" | sed 's|.*:||')
    print_status "Existing Collector image detected: $EXISTING_COLLECTOR_IMG"
    echo -e "  ${{CYAN}}Collector Registry:${{NC}} $COLLECTOR_REGISTRY"
    echo -e "  Press Enter to keep current registry, or enter a new one."
    read -p "  Collector registry [$COLLECTOR_REGISTRY]: " INPUT_COLL_REG
    COLLECTOR_REGISTRY="${{INPUT_COLL_REG:-$COLLECTOR_REGISTRY}}"
    read -p "  Collector version [$COLLECTOR_CUR_VER]: " INPUT_COLL_VER
    COLLECTOR_VERSION="${{INPUT_COLL_VER:-$COLLECTOR_CUR_VER}}"
else
    echo ""
    echo -e "${{CYAN}}Collector Image Registry:${{NC}} Container registry for flowfish-l7-collector"
    echo -e "  Default: $DEFAULT_COLLECTOR_IMAGE"
    echo -e "  Example: harbor.example.com/flowfish/flowfish-l7-collector"
    read -p "  Collector registry (press Enter for default): " INPUT_COLL_REG
    COLLECTOR_REGISTRY="${{INPUT_COLL_REG:-$DEFAULT_COLLECTOR_IMAGE}}"
    echo -e "${{CYAN}}Collector Image Tag:${{NC}} Version tag for the collector image"
    echo -e "  Default: $DEFAULT_COLLECTOR_VERSION"
    read -p "  Collector tag (press Enter for default): " INPUT_COLL_VER
    COLLECTOR_VERSION="${{INPUT_COLL_VER:-$DEFAULT_COLLECTOR_VERSION}}"
fi
# Ensure Collector image path includes the image name
case "$COLLECTOR_REGISTRY" in
    *l7-collector*|*flowfish-l7-collector*) ;;
    *) COLLECTOR_REGISTRY="${{COLLECTOR_REGISTRY%/}}/flowfish-l7-collector" ;;
esac
COLLECTOR_IMAGE="${{COLLECTOR_REGISTRY}}:${{COLLECTOR_VERSION}}"

echo ""
print_status "Configuration:"
print_status "  Namespace:       $NAMESPACE"
print_status "  Beyla Image:     $BEYLA_IMAGE"
print_status "  Collector Image: $COLLECTOR_IMAGE"
print_status "  Memory Limit:    $MEM_LIMIT"
print_status "  CPU Limit:       $CPU_LIMIT"
print_status "  BPF Volume:      $BPF_VOLUME_TYPE"
echo ""

$CLI_TOOL create namespace "$NAMESPACE" --dry-run=client -o yaml | $CLI_TOOL apply -f -

echo "[1/7] Creating Beyla RBAC..."
cat <<YAML | $CLI_TOOL apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: beyla
  namespace: $NAMESPACE
  labels:
    app: beyla
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: beyla
  labels:
    app: beyla
rules:
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["list","watch","get"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["list","watch","get"]
- apiGroups: [""]
  resources: ["services"]
  verbs: ["list","watch","get"]
- apiGroups: ["apps"]
  resources: ["replicasets","deployments","statefulsets","daemonsets"]
  verbs: ["list","watch","get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: beyla
  labels:
    app: beyla
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: beyla
subjects:
- kind: ServiceAccount
  name: beyla
  namespace: $NAMESPACE
YAML

# SCC for Beyla (OpenShift only) - required for privileged + hostPID access
# We key off the *runtime* IS_OPENSHIFT detection above, not on whether
# the operator chose `oc` vs `kubectl`: an OpenShift cluster needs an
# SCC even when it is being driven by kubectl.
if [ "$IS_OPENSHIFT" = "true" ]; then
    echo "[2/7] Creating Security Context Constraint (SCC) for Beyla..."
    cat <<SCC_EOF | $CLI_TOOL apply -f -
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: beyla-scc
  labels:
    app: beyla
allowPrivilegedContainer: true
allowHostPID: true
allowHostNetwork: false
allowHostDirVolumePlugin: true
allowHostPorts: false
allowHostIPC: false
allowedCapabilities: []
defaultAddCapabilities: []
requiredDropCapabilities: []
runAsUser:
  type: RunAsAny
seLinuxContext:
  type: RunAsAny
fsGroup:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
volumes:
  - configMap
  - emptyDir
  - hostPath
  - projected
  - secret
  - downwardAPI
users:
  - system:serviceaccount:$NAMESPACE:beyla
SCC_EOF
    echo "[3/7] Binding SCC to Beyla ServiceAccount..."
    # The SCC manifest above already lists the SA in its `users:` field,
    # which is the cluster-wide source of truth for SCC binding and works
    # regardless of which CLI applied the manifest. The `oc adm policy`
    # call below is a redundant idempotent fallback that is only available
    # when the operator drives the script with `oc`; when running with
    # `kubectl` we silently skip it (the manifest binding is sufficient).
    if [ "$CLI_TOOL" = "oc" ]; then
        $CLI_TOOL adm policy add-scc-to-user beyla-scc -z beyla -n $NAMESPACE 2>/dev/null || true
    fi
    echo "  SCC created and bound to beyla ServiceAccount"
else
    echo "[2/7] Skipping SCC (not OpenShift)..."
    echo "[3/7] Skipping SCC binding (not OpenShift)..."
fi

echo "[4/7] Creating Beyla ConfigMap..."
cat <<YAML | $CLI_TOOL apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: beyla-config
  namespace: $NAMESPACE
data:
  beyla-config.yml: |
    log_level: info
    ebpf:
      # Passive mode: read W3C traceparent headers from observed requests without
      # injecting headers. Enables distributed tracing correlation across services
      # that propagate trace context themselves. No additional kernel privileges
      # beyond existing CAP_BPF/hostPID required.
      track_request_headers: true
    attributes:
      kubernetes:
        enable: true
    discovery:
      instrument:
        - k8s_namespace: "*"
          containers_only: true
      exclude_instrument:
{exclude_yaml_lines}
    otel_traces_export:
      endpoint: http://flowfish-l7-collector.$NAMESPACE:4318
      protocol: http/protobuf
    otel_metrics_export:
      endpoint: http://flowfish-l7-collector.$NAMESPACE:4318
      protocol: http/protobuf
      features: ["application", "application_service_graph"]
YAML

echo "[5/7] Creating flowfish-l7-collector RBAC..."
cat <<YAML | $CLI_TOOL apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: flowfish-l7-collector
  namespace: $NAMESPACE
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flowfish-l7-collector-role
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "services"]
  verbs: ["get","list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flowfish-l7-collector-role-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flowfish-l7-collector-role
subjects:
- kind: ServiceAccount
  name: flowfish-l7-collector
  namespace: $NAMESPACE
YAML

# Grant services/proxy permission for remote Flowfish access to collector
echo "  Configuring service proxy access for remote Flowfish platform..."
REMOTE_SA=""
for sa_candidate in flowfish-remote-reader flowfish-reader flowfish; do
    if $CLI_TOOL get serviceaccount "$sa_candidate" -n "$NAMESPACE" &>/dev/null 2>&1; then
        REMOTE_SA="$sa_candidate"
        break
    fi
done
if [ -z "$REMOTE_SA" ]; then
    echo -e "  ${{YELLOW}}No Flowfish remote-reader ServiceAccount found in $NAMESPACE.${{NC}}"
    echo -e "  If this is a remote cluster, enter the ServiceAccount name used by Flowfish to access this cluster."
    echo -e "  (Check your cluster configuration in the Flowfish UI for the SA name.)"
    read -p "  Remote reader ServiceAccount name (press Enter to skip): " INPUT_REMOTE_SA
    REMOTE_SA="${{INPUT_REMOTE_SA:-}}"
fi
if [ -n "$REMOTE_SA" ]; then
    cat <<PROXY_RBAC | $CLI_TOOL apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: flowfish-l7-proxy
  namespace: $NAMESPACE
  labels:
    app: flowfish-l7-collector
rules:
- apiGroups: [""]
  resources: ["services/proxy"]
  resourceNames: ["flowfish-l7-collector:8080"]
  verbs: ["get","create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: flowfish-l7-proxy-binding
  namespace: $NAMESPACE
  labels:
    app: flowfish-l7-collector
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: flowfish-l7-proxy
subjects:
- kind: ServiceAccount
  name: $REMOTE_SA
  namespace: $NAMESPACE
PROXY_RBAC
    print_success "Service proxy RBAC granted to $REMOTE_SA"
else
    print_warning "Skipped service proxy RBAC — remote L7 collection may not work without it"
fi

echo "[6/7] Deploying flowfish-l7-collector (must be ready before Beyla starts)..."
cat <<YAML | $CLI_TOOL apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flowfish-l7-collector
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: flowfish-l7-collector
  template:
    metadata:
      labels:
        app: flowfish-l7-collector
    spec:
      serviceAccountName: flowfish-l7-collector
      containers:
      - name: collector
        image: $COLLECTOR_IMAGE
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: API_PORT
          value: "8080"
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 15
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        resources:
          limits:
            memory: "1Gi"
            cpu: "1"
          requests:
            memory: "256Mi"
            cpu: "100m"
---
apiVersion: v1
kind: Service
metadata:
  name: flowfish-l7-collector
  namespace: $NAMESPACE
spec:
  selector:
    app: flowfish-l7-collector
  ports:
  - name: otlp
    port: 4318
    targetPort: 8080
  - name: api
    port: 8080
    targetPort: 8080
YAML

print_status "Waiting for flowfish-l7-collector to become ready..."
COLLECTOR_READY=false
for i in $(seq 1 60); do
    READY=$($CLI_TOOL get deployment flowfish-l7-collector -n "$NAMESPACE" -o jsonpath='{{.status.readyReplicas}}' 2>/dev/null || echo "0")
    if [ "${{READY:-0}}" -ge 1 ]; then
        COLLECTOR_READY=true
        break
    fi
    sleep 2
done
if [ "$COLLECTOR_READY" = "true" ]; then
    print_success "Collector is ready — Beyla can safely send OTLP data"
else
    print_warning "Collector not ready after 120s. Beyla will retry automatically once it starts."
fi

echo "[7/7] Deploying Beyla DaemonSet..."

# Build volume spec based on bpf_volume_type parameter
if [ "$BPF_VOLUME_TYPE" = "hostPath" ]; then
    BPF_VOLUME_SPEC="hostPath:
            path: /sys/fs/bpf
            type: DirectoryOrCreate"
    echo "  Using hostPath for bpffs volume (/sys/fs/bpf)"
else
    BPF_VOLUME_SPEC="emptyDir:
          sizeLimit: 512Mi"
    echo "  Using emptyDir for bpffs volume (ephemeral, limit: 512Mi)"
fi

BEYLA_RUN_VOLUME_SPEC="emptyDir:
          sizeLimit: 256Mi"

cat <<YAML | $CLI_TOOL apply -f -
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: beyla
  namespace: $NAMESPACE
spec:
  selector:
    matchLabels:
      app: beyla
  template:
    metadata:
      labels:
        app: beyla
    spec:
      serviceAccountName: beyla
      hostPID: true
      containers:
      - name: beyla
        image: $BEYLA_IMAGE
        securityContext:
          privileged: true
        resources:
          limits:
            memory: $MEM_LIMIT
            cpu: $CPU_LIMIT
          requests:
            memory: "1Gi"
            cpu: "200m"
        volumeMounts:
        - name: config
          mountPath: /config
          readOnly: true
        - name: var-run-beyla
          mountPath: /var/run/beyla
        - name: bpffs
          mountPath: /sys/fs/bpf
        env:
        - name: BEYLA_CONFIG_PATH
          value: /config/beyla-config.yml
        - name: OTEL_EBPF_KUBE_CLUSTER_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: OTEL_EXPORTER_OTLP_TRACES_TIMEOUT
          value: "30000"
        - name: OTEL_EXPORTER_OTLP_METRICS_TIMEOUT
          value: "30000"
      volumes:
      - name: config
        configMap:
          name: beyla-config
      - name: var-run-beyla
        $BEYLA_RUN_VOLUME_SPEC
      - name: bpffs
        $BPF_VOLUME_SPEC
YAML

echo ""
echo "[OK] Beyla L7 Agent and Collector deployed to namespace: $NAMESPACE"
echo ""
echo "Verify with:"
echo "  $CLI_TOOL get pods -n $NAMESPACE"
echo "  $CLI_TOOL logs -n $NAMESPACE -l app=beyla --tail=20"
'''


@router.get("/clusters/l7-uninstall-script", response_class=PlainTextResponse)
async def get_l7_uninstall_script(
    provider: str = Query("openshift", description="Kubernetes provider: openshift, kubernetes"),
    current_user: dict = Depends(get_current_user),
):
    """Generate L7 agent (Beyla + Collector) uninstall script."""
    cli_tool = "oc" if provider.lower() == "openshift" else "kubectl"
    return _generate_l7_uninstall_script(cli_tool)


@router.get("/clusters/gadget-fix-storage-script", response_class=PlainTextResponse)
async def get_gadget_fix_storage_script(
    provider: str = Query("openshift", description="Kubernetes provider: openshift, kubernetes"),
    current_user: dict = Depends(get_current_user),
):
    """Generate a script to migrate existing Gadget installations from PVC/ephemeral to emptyDir with sizeLimit."""
    cli_tool = "oc" if provider.lower() == "openshift" else "kubectl"
    return f'''#!/bin/bash
#
# ============================================================================
#  Gadget Storage Fix Script
#  Migrates Inspektor Gadget from PVC/ephemeral volumes to emptyDir + sizeLimit
#  This prevents node disk exhaustion caused by unbounded emptyDir or PVC issues
# ============================================================================
#
# Usage:
#   chmod +x fix-gadget-storage.sh
#   ./fix-gadget-storage.sh <namespace>
#   ./fix-gadget-storage.sh          # Interactive mode
#

# Auto-detect CLI tool
if command -v oc &> /dev/null; then
    CLI_TOOL="oc"
elif command -v kubectl &> /dev/null; then
    CLI_TOOL="kubectl"
else
    echo "[ERROR] Neither oc nor kubectl found in PATH"
    exit 1
fi

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
BOLD='\\033[1m'
NC='\\033[0m'

print_status() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_success() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
print_warning() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
print_error() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}

echo ""
echo "============================================================================"
echo "  Gadget Storage Fix - PVC to emptyDir Migration"
echo "============================================================================"
echo ""

# Get namespace
if [ -n "${{1:-}}" ]; then
    NAMESPACE="$1"
else
    read -p "Enter namespace where Gadget is installed: " NAMESPACE
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

# Pre-flight checks
print_status "Using CLI tool: $CLI_TOOL"

if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &> /dev/null; then
        print_error "Not logged in. Run 'oc login' first."
        exit 1
    fi
    print_success "Logged in as: $($CLI_TOOL whoami)"
else
    if ! $CLI_TOOL cluster-info &> /dev/null 2>&1; then
        print_error "Cannot connect to cluster. Check your kubeconfig."
        exit 1
    fi
    print_success "Cluster connection OK"
fi

if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi

# Check if gadget exists
if ! $CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" &>/dev/null; then
    print_error "Inspektor Gadget DaemonSet not found in namespace '$NAMESPACE'"
    exit 1
fi
print_success "Found Inspektor Gadget in namespace '$NAMESPACE'"

# Show current state
echo ""
print_status "Current DaemonSet volumes:"
$CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{{range .spec.template.spec.volumes[*]}}  {{.name}}: {{if .emptyDir}}emptyDir{{if .emptyDir.sizeLimit}} (sizeLimit: {{.emptyDir.sizeLimit}}){{else}} (NO sizeLimit){{end}}{{else if .ephemeral}}ephemeral/PVC{{else if .hostPath}}hostPath{{else if .configMap}}configMap{{else}}other{{end}}{{"\n"}}{{end}}' 2>/dev/null
echo ""

# Check for PVC/ephemeral volumes
HAS_PVC=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o json 2>/dev/null | grep -c '"ephemeral"' || echo "0")
HAS_UNLIMITED_EMPTYDIR=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o json 2>/dev/null | python3 -c "
import json, sys
try:
    ds = json.load(sys.stdin)
    vols = ds.get('spec', {{}}).get('template', {{}}).get('spec', {{}}).get('volumes', [])
    count = 0
    for v in vols:
        ed = v.get('emptyDir')
        if ed is not None and not ed.get('sizeLimit'):
            count += 1
    print(count)
except (json.JSONDecodeError, KeyError, TypeError):
    print(0)
" 2>/dev/null || echo "0")

if [ "$HAS_PVC" = "0" ] && [ "$HAS_UNLIMITED_EMPTYDIR" = "0" ]; then
    print_success "No PVC/ephemeral or unlimited emptyDir volumes found. Storage looks healthy."
    echo ""
    $CLI_TOOL get pods -n "$NAMESPACE" -l app=inspektor-gadget -o wide
    exit 0
fi

if [ "$HAS_PVC" -gt 0 ]; then
    print_warning "Found $HAS_PVC ephemeral/PVC volume(s) - will convert to emptyDir"
fi
if [ "$HAS_UNLIMITED_EMPTYDIR" -gt 0 ]; then
    print_warning "Found $HAS_UNLIMITED_EMPTYDIR emptyDir volume(s) without sizeLimit - will add limits"
fi

echo ""
read -p "Proceed with storage fix? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_warning "Cancelled."
    exit 0
fi

echo ""
print_status "Step 1/3: Patching DaemonSet volumes..."

# Get current image
GADGET_IMAGE=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{{.spec.template.spec.containers[?(@.name=="gadget")].image}}' 2>/dev/null)
print_status "Current Gadget image: $GADGET_IMAGE"
print_status "Extracting and modifying DaemonSet spec..."
$CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o json | python3 -c "
import json, sys

ds = json.load(sys.stdin)

# Clean metadata for apply
for key in ['resourceVersion', 'uid', 'creationTimestamp', 'generation']:
    ds['metadata'].pop(key, None)
ds['metadata'].get('annotations', {{}}).pop('kubectl.kubernetes.io/last-applied-configuration', None)
ds.pop('status', None)

volumes = ds['spec']['template']['spec']['volumes']
new_volumes = []
for v in volumes:
    name = v['name']
    if name == 'oci':
        new_volumes.append({{'name': 'oci', 'emptyDir': {{'sizeLimit': '5Gi'}}}})
    elif name == 'wasm-cache':
        new_volumes.append({{'name': 'wasm-cache', 'emptyDir': {{'sizeLimit': '2Gi'}}}})
    elif name == 'config-generated':
        new_volumes.append({{'name': 'config-generated', 'emptyDir': {{'sizeLimit': '128Mi'}}}})
    elif 'emptyDir' in v and not v['emptyDir'].get('sizeLimit'):
        v['emptyDir']['sizeLimit'] = '256Mi'
        new_volumes.append(v)
    else:
        new_volumes.append(v)

ds['spec']['template']['spec']['volumes'] = new_volumes

# Remove node affinity that excludes infra nodes (no longer needed without PVC)
affinity = ds['spec']['template']['spec'].get('affinity') or {{}}
node_aff = affinity.get('nodeAffinity') or {{}}
required = node_aff.get('requiredDuringSchedulingIgnoredDuringExecution') or {{}}
terms = required.get('nodeSelectorTerms') or []
for term in terms:
    exprs = term.get('matchExpressions') or []
    term['matchExpressions'] = [e for e in exprs if e.get('key') != 'node-role.kubernetes.io/infra']

json.dump(ds, sys.stdout)
" > /tmp/gadget-fixed.json

if [ ! -s /tmp/gadget-fixed.json ]; then
    print_error "Failed to generate fixed DaemonSet spec"
    exit 1
fi

$CLI_TOOL apply -f /tmp/gadget-fixed.json
rm -f /tmp/gadget-fixed.json
print_success "DaemonSet patched with emptyDir + sizeLimit"

echo ""
print_status "Step 2/3: Cleaning up orphaned PVCs..."
PVC_COUNT=0
for pvc in $($CLI_TOOL get pvc -n "$NAMESPACE" -l app=inspektor-gadget -o name 2>/dev/null); do
    print_status "Deleting $pvc..."
    $CLI_TOOL delete "$pvc" -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null
    PVC_COUNT=$((PVC_COUNT + 1))
done
if [ "$PVC_COUNT" -gt 0 ]; then
    print_success "Deleted $PVC_COUNT orphaned PVC(s)"
else
    print_status "No orphaned PVCs found"
fi

echo ""
print_status "Step 3/3: Restarting Gadget pods..."
$CLI_TOOL delete pods -l app=inspektor-gadget -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
sleep 5

print_status "Waiting for rollout..."
$CLI_TOOL rollout status daemonset/inspektor-gadget -n "$NAMESPACE" --timeout=5m || true

echo ""
print_status "Updated volumes:"
$CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{{range .spec.template.spec.volumes[*]}}  {{.name}}: {{if .emptyDir}}emptyDir{{if .emptyDir.sizeLimit}} (sizeLimit: {{.emptyDir.sizeLimit}}){{else}} (NO sizeLimit){{end}}{{else if .hostPath}}hostPath{{else if .configMap}}configMap{{else}}other{{end}}{{"\n"}}{{end}}' 2>/dev/null
echo ""

echo ""
print_status "Pod status:"
$CLI_TOOL get pods -n "$NAMESPACE" -l app=inspektor-gadget -o wide
echo ""

DESIRED=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{{.status.desiredNumberScheduled}}' 2>/dev/null || echo "?")
READY=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{{.status.numberReady}}' 2>/dev/null || echo "?")

echo ""
echo "============================================================================"
echo "  Storage Fix Complete"
echo "  Pods: $READY/$DESIRED ready"
echo "  Volumes: oci=5Gi, wasm-cache=2Gi, config-generated=128Mi (sizeLimit)"
echo "============================================================================"
echo ""
'''


@router.get("/clusters/beyla-install-script", response_class=PlainTextResponse)
async def get_beyla_install_script_general(
    provider: str = Query("kubernetes", description="Kubernetes provider"),
    beyla_version: str = Query("3.9.5", description="Beyla version"),
    image_registry: str = Query("", description="Image registry prefix (e.g., harbor.example.com/flowfish). Empty = official registries"),
    collector_tag: str = Query("", description="Collector image tag (e.g., 86451d5, v1.2.0). Empty = auto-detect from backend IMAGE_TAG"),
    mem_limit: str = Query("6Gi", description="Memory limit for Beyla"),
    cpu_limit: str = Query("2", description="CPU limit for Beyla"),
    bpf_volume_type: str = Query("hostPath", description="Volume type for bpffs: hostPath (persistent, recommended) or emptyDir (ephemeral)"),
    current_user: dict = Depends(get_current_user),
):
    """Generate general Beyla + flowfish-l7-collector install script."""
    cli_tool = "oc" if provider.lower() == "openshift" else "kubectl"
    excluded_ns = await _get_beyla_excluded_namespaces()
    return _generate_beyla_install_script(
        cli_tool=cli_tool,
        beyla_version=beyla_version,
        image_registry=image_registry,
        collector_tag=collector_tag,
        mem_limit=mem_limit,
        cpu_limit=cpu_limit,
        bpf_volume_type=bpf_volume_type,
        excluded_namespaces=excluded_ns,
    )


@router.get("/clusters/gadget-install-script", response_class=PlainTextResponse)
async def get_gadget_install_script(
    provider: str = Query("openshift", description="Kubernetes provider: openshift, kubernetes"),
    mode: str = Query("install", description="Script mode: install or uninstall"),
    image_registry: str = Query("", description="Image registry prefix (e.g., harbor.example.com/flowfish). Empty = official registry"),
    version: str = Query("v0.50.1", description="Gadget version tag"),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate setup or uninstall script for remote cluster integration.
    
    Install mode:
    1. Installs Inspector Gadget for eBPF event collection
    2. Creates a read-only ServiceAccount for Flowfish
    3. Generates authentication token (1 year validity)
    4. Outputs all connection details for Flowfish UI
    
    Uninstall mode:
    - Safely removes only Flowfish-related resources
    - Validates namespace before deletion
    
    image_registry examples:
    - (empty) -> ghcr.io/inspektor-gadget/inspektor-gadget (default)
    - harbor.example.com/flowfish -> harbor.example.com/flowfish/inspektor-gadget
    """
    image_registry = image_registry.strip().rstrip("/")
    registry = f"{image_registry}/inspektor-gadget" if image_registry else "ghcr.io/inspektor-gadget/inspektor-gadget"
    try:
        is_openshift = provider.lower() == "openshift"
        cli_tool = "oc" if is_openshift else "kubectl"
        
        # Return uninstall script if requested
        if mode == "uninstall":
            return generate_uninstall_script(cli_tool)
        
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
    # Dynamically overridden by install script based on cluster pod/node count
    events-buffer-length: 131072
    # Auto-detected by init container at pod startup
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
            memory: 6Gi
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
        emptyDir:
          sizeLimit: 5Gi
      - name: config
        configMap:
          name: inspektor-gadget-config
          defaultMode: 0400
      - name: config-generated
        emptyDir:
          sizeLimit: 128Mi
      - name: wasm-cache
        emptyDir:
          sizeLimit: 2Gi
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
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   chmod +x setup-flowfish-remote.sh
#   ./setup-flowfish-remote.sh <namespace> [registry] [version]
#   ./setup-flowfish-remote.sh                                    # Interactive mode
#
# Examples:
#   ./setup-flowfish-remote.sh flowfish
#   ./setup-flowfish-remote.sh flowfish harbor.example.com/flowfish/inspektor-gadget v0.50.1
#
# Arguments:
#   namespace     - Target namespace (required)
#   registry      - Gadget image registry (default: {registry})
#   version       - Gadget version tag (default: {version})
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

# Parse arguments
NAMESPACE="${{1:-}}"
GADGET_REGISTRY="${{2:-$DEFAULT_REGISTRY}}"
GADGET_VERSION="${{3:-$DEFAULT_VERSION}}"

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
echo "║  Security: Creates READ-ONLY access (no write permissions)               ║"
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

if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &> /dev/null; then
        print_error "Not logged in. Please run 'oc login' first."
        exit 1
    fi
    CURRENT_USER=$($CLI_TOOL whoami)
else
    if ! $CLI_TOOL cluster-info &> /dev/null 2>&1; then
        print_error "Not connected to cluster. Please configure kubeconfig first."
        exit 1
    fi
    CURRENT_USER=$($CLI_TOOL config current-context 2>/dev/null || echo "unknown")
fi
print_success "Logged in as: $CURRENT_USER"

# Check for cluster-admin
if ! $CLI_TOOL auth can-i create clusterrole &> /dev/null; then
    print_error "You need cluster-admin privileges to run this script"
    exit 1
fi
print_success "Cluster-admin privileges confirmed"

# Runtime OpenShift detection. The operator may run this script with
# `kubectl` against an OpenShift cluster (e.g. when the Flowfish UI
# only knows the cluster as "kubernetes"). In that case we still need
# to create + bind a SecurityContextConstraint (SCC) for Inspector
# Gadget; otherwise the DaemonSet's pods are rejected by OpenShift
# admission with errors like:
#   "provider restricted-v2: .spec.securityContext.hostNetwork:
#    Invalid value: true: Host network is not allowed to be used"
# We probe the security.openshift.io API group, which is unique to
# OpenShift; vanilla Kubernetes returns no resources for that group.
if $CLI_TOOL api-resources --api-group=security.openshift.io 2>/dev/null \
    | grep -q SecurityContextConstraints; then
    IS_OPENSHIFT="true"
    print_success "OpenShift cluster detected (security.openshift.io API present)"
else
    IS_OPENSHIFT="false"
    print_status "Vanilla Kubernetes detected (no security.openshift.io API)"
fi

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
    echo -e "  Example: v0.46.0, v0.50.1"
    echo -e "  Default: $DEFAULT_VERSION"
    read -p "Enter version (press Enter for default): " INPUT_VERSION
    GADGET_VERSION="${{INPUT_VERSION:-$DEFAULT_VERSION}}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
print_status "Configuration:"
print_status "  Namespace:     $NAMESPACE"
print_status "  Registry:      $GADGET_REGISTRY"
print_status "  Version:       $GADGET_VERSION"
print_status "  Storage:       emptyDir (with sizeLimit)"
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
# We key off the *runtime* IS_OPENSHIFT detection above, not on whether
# the operator chose `oc` vs `kubectl`: an OpenShift cluster needs an
# SCC even when it is being driven by kubectl.
if [ "$IS_OPENSHIFT" = "true" ]; then
    print_status "2/6 - Creating Security Context Constraint (SCC)..."
    # NOTE: the `users:` field below binds the SCC to the
    # inspektor-gadget ServiceAccount as part of the manifest itself.
    # This is the only binding mechanism that works regardless of CLI
    # (kubectl cannot run `oc adm policy add-scc-to-user`), so we
    # include it here instead of relying on a follow-up `oc adm` call.
    cat <<SCC_EOF | $CLI_TOOL apply -f -
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
  - hostPath
  - projected
  - secret
users:
  - system:serviceaccount:$NAMESPACE:inspektor-gadget
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
# The SCC manifest above already binds via its `users:` field, which is
# the cluster-wide source of truth and works whether the operator drove
# the script with `oc` or `kubectl`. The `oc adm policy` call below is a
# redundant idempotent fallback that is only available when running with
# `oc`; with `kubectl` we silently skip it (manifest binding suffices).
if [ "$IS_OPENSHIFT" = "true" ]; then
    print_status "4/6 - Binding SCC to ServiceAccount..."
    if [ "$CLI_TOOL" = "oc" ]; then
        $CLI_TOOL adm policy add-scc-to-user inspektor-gadget-scc -z inspektor-gadget -n $NAMESPACE 2>/dev/null || true
    fi
    print_success "SCC bound to ServiceAccount"
else
    print_status "4/6 - Skipping SCC binding (not OpenShift)..."
fi

# Step 5: Create ConfigMap (with dynamic buffer sizing based on cluster size)
print_status "5/6 - Creating ConfigMap..."
TOTAL_PODS=$($CLI_TOOL get pods -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
TOTAL_PODS=${{TOTAL_PODS:-0}}
TOTAL_NODES=$($CLI_TOOL get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
TOTAL_NODES=${{TOTAL_NODES:-1}}
[ "$TOTAL_NODES" -eq 0 ] 2>/dev/null && TOTAL_NODES=1
PODS_PER_NODE=$((TOTAL_PODS / TOTAL_NODES))

# Sizing: each gadget pod runs per-node, buffer is per-CPU ring.
# High pods/node → more eBPF events → need larger buffer.
#
# Production default policy: 2x headroom over the strictly-required tier.
# Field finding from a 190-pods/node OpenShift cluster: with the legacy
# 131K-2M tiering an 11-gadget burst flooded the IG ring buffers (logs
# show "lost 295k samples" + "bad file descriptor"), corrupted IG worker
# state, tripped the kubelet liveness probe, and SIGKILL'd the IG
# container (exit 137). The doubled tiers below absorb that burst plus
# normal sustained traffic on busy clusters.
#
# Trade-off vs. "even larger" (8M+): drop visibility latency goes up
# (operator notices flooding only after ~30s instead of ~5s), and
# Linux perf_event_open starts hitting kernel.perf_event_max_sample_rate
# limits. 4M is the sweet spot — well below kernel ceilings and still
# small enough that the IG drain loop never falls more than ~10s
# behind real time.
if [ "$PODS_PER_NODE" -gt 300 ] 2>/dev/null; then
    EVENTS_BUFFER=4194304   # 4M (cap — kernel perf_event ceiling)
elif [ "$PODS_PER_NODE" -gt 150 ] 2>/dev/null; then
    EVENTS_BUFFER=4194304   # was 2097152 — 2x boost for burst tolerance
elif [ "$PODS_PER_NODE" -gt 80 ] 2>/dev/null; then
    EVENTS_BUFFER=2097152   # was 1048576
elif [ "$PODS_PER_NODE" -gt 40 ] 2>/dev/null; then
    EVENTS_BUFFER=1048576   # was 524288
elif [ "$PODS_PER_NODE" -gt 15 ] 2>/dev/null; then
    EVENTS_BUFFER=524288    # was 262144
else
    EVENTS_BUFFER=262144    # was 131072 — small clusters still get 2x
fi

# Floor based on total pod count (guards against few-node large clusters).
# Doubled in lockstep with the per-node tiers above.
if [ "$TOTAL_PODS" -gt 2000 ] 2>/dev/null && [ "$EVENTS_BUFFER" -lt 4194304 ] 2>/dev/null; then
    EVENTS_BUFFER=4194304   # was 2097152
elif [ "$TOTAL_PODS" -gt 1000 ] 2>/dev/null && [ "$EVENTS_BUFFER" -lt 2097152 ] 2>/dev/null; then
    EVENTS_BUFFER=2097152   # was 1048576
elif [ "$TOTAL_PODS" -gt 500 ] 2>/dev/null && [ "$EVENTS_BUFFER" -lt 1048576 ] 2>/dev/null; then
    EVENTS_BUFFER=1048576   # was 524288
fi
print_status "Cluster: $TOTAL_PODS pods / $TOTAL_NODES nodes ($PODS_PER_NODE pods/node) -> buffer: $EVENTS_BUFFER"
cat <<'CONFIG_EOF' | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | sed "s/events-buffer-length:.*/events-buffer-length: $EVENTS_BUFFER/" | $CLI_TOOL apply -f -
{yaml_contents["config"]}
CONFIG_EOF
print_success "ConfigMap created (buffer=$EVENTS_BUFFER for $TOTAL_PODS pods on $TOTAL_NODES nodes)"

# Step 6: Deploy DaemonSet
print_status "6/6 - Deploying DaemonSet..."
GADGET_IMAGE="${{GADGET_REGISTRY}}:${{GADGET_VERSION}}"
print_status "Using Gadget image: $GADGET_IMAGE"

print_status "Configuring with emptyDir storage (with sizeLimit)"
cat <<'DAEMONSET_EOF' | sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/g" | sed "s|GADGET_IMAGE_PLACEHOLDER|$GADGET_IMAGE|g" | $CLI_TOOL apply -f -
{yaml_contents["daemonset"]}
DAEMONSET_EOF
print_success "DaemonSet deployed with emptyDir storage (sizeLimit enforced)"

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
    resources: ["pods", "nodes", "namespaces", "services", "events", "endpoints", "configmaps", "secrets"]
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
echo "║   SETUP COMPLETE - Copy these values to Flowfish UI                       ║"
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
echo "│ SECURITY SUMMARY                                                              │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ ServiceAccount: $SA_NAME (READ-ONLY)"
echo "│ Permissions: GET, LIST, WATCH only (no write access)"
echo "│ Token Validity: 1 year"
echo "│ Namespace: $NAMESPACE"
echo "│ Storage: emptyDir (OCI: 5Gi, WASM: 2Gi, config: 128Mi sizeLimit per node)"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ MANUAL COMMANDS (if values above are empty)                                  │"
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
echo "│ VERIFICATION COMMANDS                                                        │"
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
async def get_cluster(
    cluster_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get cluster by ID"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_namespace, gadget_endpoint,
               gadget_health_status, gadget_version, status,
               total_nodes, total_pods, total_namespaces,
               k8s_version, created_at, updated_at,
               beyla_namespace, beyla_health_status, beyla_version,
               l7_collector_endpoint, beyla_last_check
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
async def update_cluster(
    cluster_id: int,
    cluster_data: ClusterUpdate,
    current_user: dict = Depends(get_current_user),
):
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

        if cluster_data.beyla_namespace is not None:
            updates.append("beyla_namespace = :beyla_namespace")
            params["beyla_namespace"] = cluster_data.beyla_namespace

        if cluster_data.status is not None:
            updates.append("status = :status")
            params["status"] = cluster_data.status
            
        if cluster_data.skip_tls_verify is not None:
            updates.append("skip_tls_verify = :skip_tls_verify")
            params["skip_tls_verify"] = cluster_data.skip_tls_verify
        
        # Sensitive fields - only update if non-empty value provided
        # This prevents accidental clearing of credentials
        if cluster_data.token is not None and cluster_data.token.strip():
            updates.append("token_encrypted = :token")
            params["token"] = encrypt_data(cluster_data.token)
            
        if cluster_data.kubeconfig is not None and cluster_data.kubeconfig.strip():
            updates.append("kubeconfig_encrypted = :kubeconfig")
            params["kubeconfig"] = encrypt_data(cluster_data.kubeconfig)
            
        if cluster_data.ca_cert is not None and cluster_data.ca_cert.strip():
            updates.append("ca_cert_encrypted = :ca_cert")
            params["ca_cert"] = encrypt_data(cluster_data.ca_cert)
        
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
        
        # Refresh cached connection if credentials or connection params changed
        credential_fields = {"token", "kubeconfig", "ca_cert", "skip_tls_verify", "api_server_url"}
        if credential_fields & set(params.keys()):
            try:
                await cluster_connection_manager.refresh_connection(cluster_id)
                logger.info("Connection cache refreshed after credential update", cluster_id=cluster_id)
            except Exception as refresh_err:
                logger.warning("Connection refresh failed (will retry on next access)",
                             cluster_id=cluster_id, error=str(refresh_err))

        # Return updated cluster (without sensitive fields)
        updated = await database.fetch_one(
            """SELECT id, name, description, environment, provider, region,
                      connection_type, api_server_url, gadget_namespace, gadget_endpoint,
                      gadget_health_status, gadget_version,
                      beyla_namespace, beyla_health_status, beyla_version,
                      status, 
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
async def delete_cluster(
    cluster_id: int,
    current_user: dict = Depends(get_current_user),
):
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

        # Clean up cached connection so it's not left dangling
        try:
            await cluster_connection_manager.close_connection(cluster_id)
        except Exception as conn_err:
            logger.warning("Failed to close cached connection for deleted cluster",
                         cluster_id=cluster_id, error=str(conn_err))
        
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
async def sync_cluster(
    cluster_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Sync cluster information (workloads, nodes, etc.)"""
    try:
        cluster = await database.fetch_one(
            """SELECT id, name, connection_type, api_server_url, kubeconfig_encrypted,
                      token_encrypted, ca_cert_encrypted, skip_tls_verify,
                      gadget_namespace, beyla_namespace
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
        
        # Beyla (L7) health check — try beyla_namespace, fall back to gadget_namespace
        beyla_ns = cluster.get("beyla_namespace") or cluster.get("gadget_namespace") or ""
        beyla_health = {"health_status": "not_installed"}
        if beyla_ns:
            try:
                beyla_health = await cluster_connection_manager.check_beyla_health(cluster_id, beyla_ns)
                logger.info("Beyla health check result",
                           health_status=beyla_health.get("health_status"),
                           daemonset_ready=beyla_health.get("daemonset_ready"),
                           daemonset_total=beyla_health.get("daemonset_total"),
                           collector_ready=beyla_health.get("collector_ready"))
                # Auto-persist beyla_namespace if discovered via gadget_namespace fallback
                if not cluster.get("beyla_namespace") and beyla_health.get("health_status") in ("healthy", "degraded"):
                    await database.execute(
                        "UPDATE clusters SET beyla_namespace = :ns WHERE id = :id",
                        {"ns": beyla_ns, "id": cluster_id},
                    )
                    logger.info("Auto-discovered beyla_namespace", cluster_id=cluster_id, namespace=beyla_ns)
            except Exception as beyla_err:
                logger.error("Beyla health check exception", error=str(beyla_err))
                beyla_health = {"health_status": "unknown", "error": str(beyla_err)}
        
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
                   beyla_health_status = :beyla_health_status,
                   beyla_version = :beyla_version,
                   beyla_last_check = NOW(),
                   updated_at = NOW()
                   WHERE id = :cluster_id""",
                {
                    "cluster_id": cluster_id,
                    "total_nodes": cluster_info.get("total_nodes", 0),
                    "total_pods": cluster_info.get("total_pods", 0),
                    "total_namespaces": cluster_info.get("total_namespaces", 0),
                    "k8s_version": cluster_info.get("k8s_version"),
                    "gadget_health_status": gadget_health.get("health_status", "not_installed"),
                    "gadget_version": gadget_health.get("version"),
                    "beyla_health_status": beyla_health.get("health_status", "not_installed"),
                    "beyla_version": beyla_health.get("version", ""),
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
                "gadget_health": gadget_health.get("health_status", "not_installed"),
                "gadget_details": {
                    "version": gadget_health.get("version"),
                    "error": gadget_health.get("error"),
                    "pods_ready": gadget_health.get("pods_ready", 0),
                    "pods_total": gadget_health.get("pods_total", 0),
                    "details": gadget_health.get("details", {})
                },
                "beyla_health": beyla_health.get("health_status", "not_installed"),
                "beyla_version": beyla_health.get("version", ""),
                "beyla_details": {
                    "daemonset_ready": beyla_health.get("daemonset_ready", 0),
                    "daemonset_total": beyla_health.get("daemonset_total", 0),
                    "collector_ready": beyla_health.get("collector_ready", False),
                    "issues": beyla_health.get("issues", []),
                    "error": beyla_health.get("error"),
                },
            }
        else:
            # Partial sync - cluster info failed but gadget health may be available
            logger.warning("Cluster info fetch failed, updating gadget health only",
                          cluster_id=cluster_id,
                          error=cluster_info_error)
            
            # Still update gadget + beyla health even if cluster info failed
            await database.execute(
                """UPDATE clusters SET 
                   gadget_health_status = :gadget_health_status,
                   gadget_version = :gadget_version,
                   beyla_health_status = :beyla_health_status,
                   beyla_version = :beyla_version,
                   beyla_last_check = NOW(),
                   updated_at = NOW()
                   WHERE id = :cluster_id""",
                {
                    "cluster_id": cluster_id,
                    "gadget_health_status": gadget_health.get("health_status", "not_installed"),
                    "gadget_version": gadget_health.get("version"),
                    "beyla_health_status": beyla_health.get("health_status", "not_installed"),
                    "beyla_version": beyla_health.get("version", ""),
                }
            )
            
            # Return partial success instead of 500 error
            return {
                "message": f"Cluster '{cluster['name']}' partially synced - cluster info unavailable",
                "status": "partial",
                "warning": f"Cluster info fetch failed: {cluster_info_error}",
                "resources": None,
                "gadget_health": gadget_health.get("health_status", "not_installed"),
                "gadget_details": {
                    "version": gadget_health.get("version"),
                    "error": gadget_health.get("error"),
                    "pods_ready": gadget_health.get("pods_ready", 0),
                    "pods_total": gadget_health.get("pods_total", 0),
                    "details": gadget_health.get("details", {})
                },
                "beyla_health": beyla_health.get("health_status", "not_installed"),
                "beyla_version": beyla_health.get("version", ""),
                "beyla_details": {
                    "daemonset_ready": beyla_health.get("daemonset_ready", 0),
                    "daemonset_total": beyla_health.get("daemonset_total", 0),
                    "collector_ready": beyla_health.get("collector_ready", False),
                    "issues": beyla_health.get("issues", []),
                    "error": beyla_health.get("error"),
                },
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
    skip_tls_verify: Optional[bool] = None
    gadget_namespace: Optional[str] = None
    cluster_id: Optional[int] = None  # If provided, fall back to stored credentials


@router.post("/clusters/test-connection")
async def test_cluster_connection(
    test_data: ConnectionTestRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Test cluster connection before creating or after editing.
    
    This endpoint allows users to verify their cluster credentials
    and Inspector Gadget endpoint before creating a cluster.
    
    When cluster_id is provided (edit mode), missing credentials are
    loaded from the stored (encrypted) values in the database so the
    user only needs to supply fields they are changing.
    
    Uses ClusterConnectionManager.test_connection() for unified logic.
    Returns detailed connection status and any errors.
    """
    try:
        token = test_data.token
        ca_cert = test_data.ca_cert
        api_server_url = test_data.api_server_url
        skip_tls = test_data.skip_tls_verify
        gadget_ns = test_data.gadget_namespace
        conn_type = test_data.connection_type
        kubeconfig = None

        # For edit mode: fill missing fields from stored cluster data
        if test_data.cluster_id:
            stored = await database.fetch_one(
                """SELECT connection_type, api_server_url, token_encrypted,
                          ca_cert_encrypted, kubeconfig_encrypted,
                          skip_tls_verify, gadget_namespace
                   FROM clusters WHERE id = :cid AND status != 'deleted'""",
                {"cid": test_data.cluster_id},
            )
            if stored:
                conn_type = conn_type or stored["connection_type"]
                api_server_url = api_server_url or stored["api_server_url"]
                if not token and stored["token_encrypted"]:
                    token = decrypt_data(stored["token_encrypted"])
                if not ca_cert and stored["ca_cert_encrypted"]:
                    ca_cert = decrypt_data(stored["ca_cert_encrypted"])
                if not kubeconfig and stored["kubeconfig_encrypted"]:
                    kubeconfig = decrypt_data(stored["kubeconfig_encrypted"])
                if skip_tls is None:
                    skip_tls = stored["skip_tls_verify"] or False
                gadget_ns = gadget_ns or stored["gadget_namespace"] or ""

        skip_tls = skip_tls if skip_tls is not None else False
        gadget_ns = gadget_ns or ""

        # Validate required fields based on connection type
        normalized_type = conn_type.replace('_', '-').lower() if conn_type else ""
        
        if normalized_type == "token":
            if not api_server_url:
                raise ValueError("API Server URL is required for token authentication")
            if not token:
                raise ValueError("Token is required for token authentication")
        
        # For kubeconfig connections, use stored kubeconfig or the token field
        # (Add Cluster modal reuses the token field for kubeconfig content)
        effective_kubeconfig = None
        if normalized_type == "kubeconfig":
            effective_kubeconfig = kubeconfig or token

        # Use ClusterConnectionManager for unified connection testing
        test_result = await cluster_connection_manager.test_connection(
            connection_type=conn_type,
            api_server_url=api_server_url,
            token=token,
            ca_cert=ca_cert,
            kubeconfig=effective_kubeconfig,
            skip_tls_verify=skip_tls,
            gadget_namespace=gadget_ns
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


@router.get("/clusters/{cluster_id}/gadget-upgrade-script", response_class=PlainTextResponse)
async def get_gadget_upgrade_script(
    cluster_id: int,
    target_version: str = Query("v0.50.1", description="Target gadget version"),
    memory_limit: str = Query("6Gi", description="Memory limit for gadget containers"),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a cluster-specific upgrade script for Inspektor Gadget DaemonSet.
    Pre-fills parameters from the cluster's current configuration.
    """
    try:
        query = """
            SELECT id, name, gadget_namespace, gadget_version, connection_type
            FROM clusters WHERE id = :id AND status != 'deleted'
        """
        cluster = await database.fetch_one(query, {"id": cluster_id})
        
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        
        namespace = cluster['gadget_namespace'] or 'flowfish'
        current_version = cluster['gadget_version'] or 'unknown'
        cluster_name = cluster['name']
        
        script = f'''#!/bin/bash
# =========================================================================
# Inspektor Gadget Upgrade Script
# Generated for cluster: {cluster_name} (ID: {cluster_id})
# Current version: {current_version}
# Target version:  {target_version}
# =========================================================================
#
# Usage:
#   chmod +x upgrade-gadget.sh
#   ./upgrade-gadget.sh
#
# The script will interactively ask for configuration and validate
# each step before making changes. Safe to run - nothing changes
# without your explicit confirmation.
#
# =========================================================================

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
BOLD='\\033[1m'
NC='\\033[0m'

print_info() {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
print_ok() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
print_warn() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
print_err() {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; }}
print_header() {{ echo -e "\\n${{CYAN}}${{BOLD}}=== $1 ===${{NC}}\\n"; }}

confirm_step() {{
    local msg="${{1:-Continue?}}"
    read -p "$msg (y/N): " ans
    if [[ ! "$ans" =~ ^[Yy]$ ]]; then
        echo "Cancelled by user."
        exit 0
    fi
}}

echo ""
echo "======================================================================="
echo "  Inspektor Gadget Upgrade"
echo "  Cluster: {cluster_name}"
echo "======================================================================="
echo ""

# =========================================================================
# Step 1: Pre-flight Checks
# =========================================================================
print_header "Pre-flight Checks"

# Detect CLI tool
if command -v oc &>/dev/null; then
    CLI_TOOL="oc"
elif command -v kubectl &>/dev/null; then
    CLI_TOOL="kubectl"
else
    print_err "Neither oc nor kubectl found in PATH"
    exit 1
fi
print_ok "CLI tool: $CLI_TOOL"

# Check cluster connectivity and auth
if [ "$CLI_TOOL" = "oc" ]; then
    if ! $CLI_TOOL whoami &>/dev/null 2>&1; then
        print_err "Not logged in. Run 'oc login' first."
        exit 1
    fi
    CURRENT_USER=$($CLI_TOOL whoami 2>/dev/null)
else
    if ! $CLI_TOOL cluster-info &>/dev/null 2>&1; then
        print_err "Cannot reach cluster. Check your kubeconfig and context."
        exit 1
    fi
    CURRENT_USER=$($CLI_TOOL config current-context 2>/dev/null || echo "unknown")
fi
print_ok "Logged in as: $CURRENT_USER"

# Check permissions
if ! $CLI_TOOL auth can-i patch daemonset -n "{namespace}" &>/dev/null 2>&1; then
    print_warn "May not have permission to patch DaemonSets in {namespace}"
    print_warn "Upgrade might fail at the apply step"
fi

# =========================================================================
# Step 2: Interactive Configuration
# =========================================================================
print_header "Configuration"

# Namespace
DEFAULT_NAMESPACE="{namespace}"
echo -e "${{CYAN}}Namespace:${{NC}} Where Inspektor Gadget is deployed"
echo -e "  Default: $DEFAULT_NAMESPACE"
read -p "Enter namespace (press Enter for default): " INPUT_NS
NAMESPACE="${{INPUT_NS:-$DEFAULT_NAMESPACE}}"

# Validate namespace exists
if ! $CLI_TOOL get namespace "$NAMESPACE" &>/dev/null 2>&1; then
    print_err "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi
print_ok "Namespace '$NAMESPACE' exists"

# Validate DaemonSet exists
if ! $CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" &>/dev/null 2>&1; then
    print_err "DaemonSet 'inspektor-gadget' not found in namespace '$NAMESPACE'"
    print_info "Check: $CLI_TOOL get daemonset -n $NAMESPACE"
    exit 1
fi
print_ok "DaemonSet 'inspektor-gadget' found"
echo ""

# Read current state from cluster
CURRENT_IMAGE=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "unknown")
CURRENT_REGISTRY=$(echo "$CURRENT_IMAGE" | sed "s|:.*||")
CURRENT_VERSION=$(echo "$CURRENT_IMAGE" | grep -oE 'v[0-9]+\\.[0-9]+\\.[0-9]+' || echo "unknown")
CURRENT_MEM=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.spec.template.spec.containers[0].resources.limits.memory}}' 2>/dev/null || echo "unknown")
CURRENT_READY=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.status.numberReady}}' 2>/dev/null || echo "0")
CURRENT_DESIRED=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.status.desiredNumberScheduled}}' 2>/dev/null || echo "0")

print_info "Current state:"
print_info "  Image:        $CURRENT_IMAGE"
print_info "  Version:      $CURRENT_VERSION"
print_info "  Registry:     $CURRENT_REGISTRY"
print_info "  Memory Limit: $CURRENT_MEM"
print_info "  Pods Ready:   $CURRENT_READY / $CURRENT_DESIRED"
echo ""

# Check if pods are healthy before upgrade
if [ "$CURRENT_READY" != "$CURRENT_DESIRED" ] || [ "$CURRENT_READY" = "0" ]; then
    print_warn "Not all pods are ready ($CURRENT_READY / $CURRENT_DESIRED)"
    print_warn "Upgrading an unhealthy DaemonSet may cause issues"
    confirm_step "Continue anyway?"
fi

# Target version
DEFAULT_TARGET="{target_version}"
echo -e "${{CYAN}}Target Version:${{NC}} Version to upgrade to"
echo -e "  Current: $CURRENT_VERSION"
echo -e "  Default: $DEFAULT_TARGET"
read -p "Enter target version (press Enter for default): " INPUT_VER
TARGET_VERSION="${{INPUT_VER:-$DEFAULT_TARGET}}"

if [ "$TARGET_VERSION" = "$CURRENT_VERSION" ]; then
    print_warn "Target version ($TARGET_VERSION) is the same as current ($CURRENT_VERSION)"
    confirm_step "Continue anyway?"
fi

# Registry
echo ""
echo -e "${{CYAN}}Image Registry:${{NC}} Where to pull the gadget image from"
echo -e "  Current: $CURRENT_REGISTRY"
echo -e "  Press Enter to keep current registry (recommended)"
read -p "Enter registry (press Enter to keep current): " INPUT_REG
REGISTRY="${{INPUT_REG:-$CURRENT_REGISTRY}}"

# Memory limit
DEFAULT_MEM="{memory_limit}"
echo ""
echo -e "${{CYAN}}Memory Limit:${{NC}} Memory limit for gadget containers"
echo -e "  Current: $CURRENT_MEM"
echo -e "  Recommended: $DEFAULT_MEM"
read -p "Enter memory limit (press Enter for recommended): " INPUT_MEM
MEMORY_LIMIT="${{INPUT_MEM:-$DEFAULT_MEM}}"

# Events buffer - dynamically calculated from cluster pod count + node count
MIN_BUFFER=8192
CURRENT_BUFFER_VAL=""
if $CLI_TOOL get configmap inspektor-gadget-config -n "$NAMESPACE" &>/dev/null 2>&1; then
    CURRENT_BUFFER_VAL=$($CLI_TOOL get configmap inspektor-gadget-config -n "$NAMESPACE" \\
      -o jsonpath='{{.data.config\\.yaml}}' 2>/dev/null | grep "events-buffer-length" | grep -oE '[0-9]+' || echo "")
fi

TOTAL_PODS=$($CLI_TOOL get pods -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
TOTAL_PODS=${{TOTAL_PODS:-0}}
TOTAL_NODES=$($CLI_TOOL get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
TOTAL_NODES=${{TOTAL_NODES:-1}}
[ "$TOTAL_NODES" -eq 0 ] 2>/dev/null && TOTAL_NODES=1
PODS_PER_NODE=$((TOTAL_PODS / TOTAL_NODES))

# Tier table doubled vs the original to keep 2x burst headroom on top of
# the strictly-required ring size. See the install-script tier table for
# the full rationale and the 4M cap reasoning. Both paths must stay in
# lockstep — the upgrade UI reads CURRENT_BUFFER_VAL and only proposes a
# bump when current < recommended, so a divergent table here would cause
# spurious "below recommended" warnings or, worse, silent under-sizing.
if [ "$PODS_PER_NODE" -gt 300 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=4194304
elif [ "$PODS_PER_NODE" -gt 150 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=4194304   # was 2097152
elif [ "$PODS_PER_NODE" -gt 80 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=2097152   # was 1048576
elif [ "$PODS_PER_NODE" -gt 40 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=1048576   # was 524288
elif [ "$PODS_PER_NODE" -gt 15 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=524288    # was 262144
else
    RECOMMENDED_BUFFER=262144    # was 131072
fi

# Floor based on total pod count — doubled in lockstep.
if [ "$TOTAL_PODS" -gt 2000 ] 2>/dev/null && [ "$RECOMMENDED_BUFFER" -lt 4194304 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=4194304   # was 2097152
elif [ "$TOTAL_PODS" -gt 1000 ] 2>/dev/null && [ "$RECOMMENDED_BUFFER" -lt 2097152 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=2097152   # was 1048576
elif [ "$TOTAL_PODS" -gt 500 ] 2>/dev/null && [ "$RECOMMENDED_BUFFER" -lt 1048576 ] 2>/dev/null; then
    RECOMMENDED_BUFFER=1048576   # was 524288
fi

echo ""
echo -e "${{CYAN}}Events Buffer Length:${{NC}} eBPF ring buffer size (per-CPU, per-node)"
echo -e "  Cluster: $TOTAL_PODS pods / $TOTAL_NODES nodes ($PODS_PER_NODE pods/node)"
echo -e "  Recommended for this cluster: $RECOMMENDED_BUFFER"
if [ -n "$CURRENT_BUFFER_VAL" ]; then
    echo -e "  Current value: $CURRENT_BUFFER_VAL"
    if [ "$CURRENT_BUFFER_VAL" -ge "$RECOMMENDED_BUFFER" ] 2>/dev/null; then
        DEFAULT_BUFFER=$CURRENT_BUFFER_VAL
    else
        DEFAULT_BUFFER=$RECOMMENDED_BUFFER
        print_warn "Current buffer ($CURRENT_BUFFER_VAL) is below recommended ($RECOMMENDED_BUFFER) for $TOTAL_PODS pods"
    fi
else
    DEFAULT_BUFFER=$RECOMMENDED_BUFFER
fi
echo -e "  Default: $DEFAULT_BUFFER"
read -p "Enter buffer length (press Enter for recommended, 0 to skip): " INPUT_BUF
EVENTS_BUFFER_LENGTH="${{INPUT_BUF:-$DEFAULT_BUFFER}}"
if [ "$EVENTS_BUFFER_LENGTH" -lt "$MIN_BUFFER" ] 2>/dev/null && [ "$EVENTS_BUFFER_LENGTH" != "0" ]; then
    print_warn "Buffer $EVENTS_BUFFER_LENGTH is below minimum ($MIN_BUFFER), may cause event loss"
    confirm_step "Continue with this value?"
fi

# =========================================================================
# Step 3: Review & Confirm
# =========================================================================
print_header "Upgrade Plan"

echo "The following changes will be applied:"
echo ""
echo "  Namespace:      $NAMESPACE"
echo "  Image:          $REGISTRY:$TARGET_VERSION"
echo "  Version:        $CURRENT_VERSION -> $TARGET_VERSION"
echo "  Memory Limit:   $CURRENT_MEM -> $MEMORY_LIMIT"
if [ "$EVENTS_BUFFER_LENGTH" = "0" ]; then
    echo "  Events Buffer:  (skipped)"
elif [ -z "$CURRENT_BUFFER_VAL" ]; then
    echo "  Events Buffer:  (new) $EVENTS_BUFFER_LENGTH"
elif [ "$CURRENT_BUFFER_VAL" != "$EVENTS_BUFFER_LENGTH" ] 2>/dev/null; then
    echo "  Events Buffer:  $CURRENT_BUFFER_VAL -> $EVENTS_BUFFER_LENGTH"
else
    echo "  Events Buffer:  $EVENTS_BUFFER_LENGTH (no change)"
fi
echo ""
echo "  Rollback command (save this):"
echo "    $CLI_TOOL set image daemonset/inspektor-gadget -n $NAMESPACE gadget=$CURRENT_IMAGE"
echo ""

print_warn "All gadget pods will be restarted during the upgrade."
print_warn "Ensure no active analyses are running on this cluster."
echo ""
confirm_step "Apply upgrade?"

# =========================================================================
# Step 4: Apply Changes
# =========================================================================
print_header "Applying Upgrade"

# 4a: Update container image
print_info "[1/5] Updating DaemonSet image to $REGISTRY:$TARGET_VERSION ..."
if ! $CLI_TOOL set image daemonset/inspektor-gadget -n "$NAMESPACE" gadget="$REGISTRY:$TARGET_VERSION"; then
    print_err "Failed to update image!"
    print_info "Rollback: $CLI_TOOL set image daemonset/inspektor-gadget -n $NAMESPACE gadget=$CURRENT_IMAGE"
    exit 1
fi
print_ok "Image updated"

# 4b: Update GADGET_IMAGE env var (used by IG for OCI image pulls)
print_info "[2/5] Updating GADGET_IMAGE environment variable..."
if ! $CLI_TOOL set env daemonset/inspektor-gadget -n "$NAMESPACE" -c gadget \\
  GADGET_IMAGE="$REGISTRY:$TARGET_VERSION"; then
    print_warn "Failed to update GADGET_IMAGE env var (non-fatal, continuing)"
fi
print_ok "GADGET_IMAGE env updated"

# 4c: Update memory limit
print_info "[3/5] Setting memory limit to $MEMORY_LIMIT ..."
if ! $CLI_TOOL patch daemonset inspektor-gadget -n "$NAMESPACE" --type=json \\
  -p="[{{\\"op\\": \\"replace\\", \\"path\\": \\"/spec/template/spec/containers/0/resources/limits/memory\\", \\"value\\": \\"$MEMORY_LIMIT\\"}}]"; then
    print_warn "Failed to update memory limit (non-fatal, continuing)"
fi
print_ok "Memory limit set"

# 4d: Update events buffer
if [ "$EVENTS_BUFFER_LENGTH" != "0" ]; then
    print_info "[4/5] Updating events buffer..."
    if $CLI_TOOL get configmap inspektor-gadget-config -n "$NAMESPACE" &>/dev/null 2>&1; then
        CUR_CFG=$($CLI_TOOL get configmap inspektor-gadget-config -n "$NAMESPACE" \\
          -o jsonpath='{{.data.config\\.yaml}}' 2>/dev/null || echo "")
        if [ -n "$CUR_CFG" ]; then
            CUR_BUF=$(echo "$CUR_CFG" | grep "events-buffer-length" | grep -oE '[0-9]+' || echo "0")
            if [ "$CUR_BUF" != "$EVENTS_BUFFER_LENGTH" ] 2>/dev/null; then
                UPD_CFG=$(echo "$CUR_CFG" | sed "s/events-buffer-length:.*/events-buffer-length: $EVENTS_BUFFER_LENGTH/")
                $CLI_TOOL create configmap inspektor-gadget-config -n "$NAMESPACE" \\
                  --from-literal="config.yaml=$UPD_CFG" --dry-run=client -o yaml \\
                  | $CLI_TOOL apply -f -
                print_ok "Buffer updated: $CUR_BUF -> $EVENTS_BUFFER_LENGTH"
            else
                print_ok "Buffer unchanged (${{CUR_BUF:-unknown}})"
            fi
        else
            print_warn "ConfigMap has no config.yaml data, skipping"
        fi
    else
        print_warn "ConfigMap not found, skipping buffer update"
    fi
else
    print_info "[4/5] Events buffer update skipped (user choice)"
fi

# 4e: Wait for rollout
print_info "[5/5] Waiting for rollout (timeout: 5 minutes)..."
if ! $CLI_TOOL rollout status daemonset/inspektor-gadget -n "$NAMESPACE" --timeout=300s; then
    print_err "Rollout timed out or failed!"
    print_warn "Check pod status: $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
    print_warn "Check events: $CLI_TOOL get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20"
    print_info "Rollback: $CLI_TOOL set image daemonset/inspektor-gadget -n $NAMESPACE gadget=$CURRENT_IMAGE"
    exit 1
fi
print_ok "Rollout complete"

# =========================================================================
# Step 5: Verification
# =========================================================================
print_header "Verification"

NEW_IMAGE=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "unknown")
NEW_VERSION_ACTUAL=$(echo "$NEW_IMAGE" | grep -oE 'v[0-9]+\\.[0-9]+\\.[0-9]+' || echo "unknown")
NEW_MEM=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.spec.template.spec.containers[0].resources.limits.memory}}' 2>/dev/null || echo "unknown")
READY=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.status.numberReady}}' 2>/dev/null || echo "0")
DESIRED=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" \\
  -o jsonpath='{{.status.desiredNumberScheduled}}' 2>/dev/null || echo "0")

# Verify version
if [ "$NEW_VERSION_ACTUAL" = "$TARGET_VERSION" ]; then
    print_ok "Version: $NEW_VERSION_ACTUAL"
else
    print_warn "Version mismatch: expected $TARGET_VERSION, got $NEW_VERSION_ACTUAL"
fi

# Verify pods
if [ "$READY" = "$DESIRED" ] && [ "$READY" != "0" ]; then
    print_ok "Pods: $READY / $DESIRED ready"
else
    print_warn "Pods: $READY / $DESIRED ready"
    print_info "Some pods may still be starting. Check: $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
fi

print_ok "Memory Limit: $NEW_MEM"
print_ok "Image: $NEW_IMAGE"

echo ""
echo "======================================================================="
echo "  Upgrade Complete"
echo "======================================================================="
echo ""
echo "  Next steps:"
echo "  1. Sync the cluster in Flowfish UI to update version info"
echo "  2. Start a test analysis to verify gadget functionality"
echo ""
echo "  Rollback (if needed):"
echo "    $CLI_TOOL set image daemonset/inspektor-gadget -n $NAMESPACE gadget=$CURRENT_IMAGE"
echo "======================================================================="
'''
        
        return script
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate upgrade script", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upgrade script: {str(e)}"
        )


@router.get("/clusters/{cluster_id}/beyla-install-script", response_class=PlainTextResponse)
async def get_beyla_install_script(
    cluster_id: int,
    beyla_version: str = Query("3.9.5", description="Beyla version"),
    image_registry: str = Query("", description="Image registry prefix (e.g., harbor.example.com/flowfish). Empty = official registries"),
    collector_tag: str = Query("", description="Collector image tag (e.g., 86451d5, v1.2.0). Empty = auto-detect from backend IMAGE_TAG"),
    mem_limit: str = Query("6Gi", description="Memory limit"),
    cpu_limit: str = Query("2", description="CPU limit"),
    bpf_volume_type: str = Query("hostPath", description="Volume type for bpffs: hostPath (persistent, recommended) or emptyDir (ephemeral)"),
    current_user: dict = Depends(get_current_user),
):
    """Generate cluster-specific Beyla install script."""
    try:
        cluster = await database.fetch_one(
            "SELECT id, name, beyla_namespace, connection_type, provider FROM clusters WHERE id = :id AND status != 'deleted'",
            {"id": cluster_id},
        )
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        provider = (cluster.get("provider") or cluster.get("connection_type") or "").lower()
        cli_tool = "oc" if provider == "openshift" else "kubectl"
        excluded_ns = await _get_beyla_excluded_namespaces()
        return _generate_beyla_install_script(
            cli_tool=cli_tool,
            beyla_version=beyla_version,
            image_registry=image_registry,
            collector_tag=collector_tag,
            mem_limit=mem_limit,
            cpu_limit=cpu_limit,
            bpf_volume_type=bpf_volume_type,
            excluded_namespaces=excluded_ns,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate Beyla install script", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/{cluster_id}/beyla-upgrade-script", response_class=PlainTextResponse)
async def get_beyla_upgrade_script(
    cluster_id: int,
    target_version: str = Query("3.9.5", description="Target Beyla version"),
    current_user: dict = Depends(get_current_user),
):
    """Generate cluster-specific Beyla upgrade script."""
    try:
        cluster = await database.fetch_one(
            "SELECT id, name, beyla_namespace, beyla_version, connection_type, provider FROM clusters WHERE id = :id AND status != 'deleted'",
            {"id": cluster_id},
        )
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        ns = cluster.get("beyla_namespace") or "flowfish"
        current = cluster.get("beyla_version") or "unknown"
        cname = cluster.get("name") or f"cluster-{cluster_id}"
        provider = (cluster.get("provider") or cluster.get("connection_type") or "").lower()
        cli_tool = "oc" if provider == "openshift" else "kubectl"
        target_version = target_version.lstrip("v")

        script = f'''#!/bin/bash
set -euo pipefail
# Beyla Upgrade Script - Cluster: {cname} (ID: {cluster_id})
# Current: {current}  →  Target: {target_version}

NAMESPACE="{ns}"
CLI="{cli_tool}"

CURRENT_IMG=$($CLI get daemonset/beyla -n "$NAMESPACE" -o jsonpath='{{.spec.template.spec.containers[0].image}}' 2>/dev/null || echo "")
if [ -n "$CURRENT_IMG" ]; then
    BEYLA_REPO=$(echo "$CURRENT_IMG" | sed 's|:[^:]*$||')
else
    BEYLA_REPO="grafana/beyla"
fi

NEW_IMAGE="${{BEYLA_REPO}}:{target_version}"
echo "Upgrading Beyla DaemonSet image to $NEW_IMAGE ..."
$CLI set image daemonset/beyla -n "$NAMESPACE" beyla="$NEW_IMAGE"
$CLI rollout status daemonset/beyla -n "$NAMESPACE" --timeout=120s

echo ""
echo "[OK] Beyla upgraded to {target_version} in namespace $NAMESPACE"
echo "   Sync the cluster in Flowfish UI to update version info."
'''
        return script
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate Beyla upgrade script", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

