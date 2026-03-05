"""
Clusters router - Simplified for MVP
PATCHED for local testing - fixed NoneType error and schema issues
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import structlog

from database.postgresql import database
from services.cluster_info_service import cluster_info_service

logger = structlog.get_logger()

router = APIRouter()

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
    gadget_endpoint: Optional[str] = None
    skip_tls_verify: Optional[bool] = False

class ClusterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


@router.get("/clusters")
async def get_clusters():
    """Get all clusters"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_endpoint,
               gadget_health_status, gadget_version, status,
               total_nodes, total_pods, total_namespaces,
               k8s_version, created_at, updated_at
        FROM clusters
        WHERE status = 'active'
        ORDER BY name
        """
        
        clusters = await database.fetch_all(query, {})
        
        return {
            "clusters": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "description": c["description"],
                    "environment": c["environment"],
                    "provider": c["provider"],
                    "region": c["region"],
                    "connection_type": c["connection_type"],
                    "api_server_url": c["api_server_url"],
                    "gadget_endpoint": c["gadget_endpoint"],
                    "gadget_health_status": c["gadget_health_status"],
                    "gadget_version": c["gadget_version"],
                    "status": c["status"],
                    "total_nodes": c["total_nodes"],
                    "total_pods": c["total_pods"],
                    "total_namespaces": c["total_namespaces"],
                    "k8s_version": c["k8s_version"],
                    "created_at": c["created_at"],
                    "updated_at": c["updated_at"]
                }
                for c in clusters
            ],
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
        # Insert cluster
        insert_query = """
        INSERT INTO clusters (
            name, description, environment, provider, region,
            connection_type, api_server_url, kubeconfig_encrypted,
            token_encrypted, ca_cert_encrypted, gadget_endpoint,
            skip_tls_verify, status, gadget_health_status, created_at
        )
        VALUES (
            :name, :description, :environment, :provider, :region,
            :connection_type, :api_server_url, :kubeconfig,
            :token, :ca_cert, :gadget_endpoint,
            :skip_tls_verify, 'active', 'unknown', NOW()
        )
        RETURNING id
        """
        
        params = {
            "name": cluster_data.name,
            "description": cluster_data.description or "",
            "environment": cluster_data.environment or "production",
            "provider": cluster_data.provider or "kubernetes",
            "region": cluster_data.region or "default",
            "connection_type": cluster_data.connection_type,
            "api_server_url": cluster_data.api_server_url,
            "kubeconfig": cluster_data.kubeconfig,
            "token": cluster_data.token,
            "ca_cert": cluster_data.ca_cert,
            "gadget_endpoint": cluster_data.gadget_endpoint,
            "skip_tls_verify": cluster_data.skip_tls_verify or False
        }
        
        result = await database.fetch_one(insert_query, params)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create cluster: INSERT returned no result"
            )
        
        cluster_id = result['id']
        
        logger.info("Cluster created", cluster_id=cluster_id, name=cluster_data.name)
        
        # Asynchronously fetch cluster info (best effort)
        try:
            # Get cluster resources
            cluster_info = await cluster_info_service.get_cluster_info(
                connection_type=cluster_data.connection_type,
                api_server_url=cluster_data.api_server_url,
                kubeconfig=cluster_data.kubeconfig,
                token=cluster_data.token,
                ca_cert=cluster_data.ca_cert,
                skip_tls_verify=cluster_data.skip_tls_verify or False
            )
            
            # Check gadget health
            gadget_health = await cluster_info_service.check_gadget_health(
                cluster_data.gadget_endpoint
            )
            
            # Update cluster with fetched info
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
                    "cluster_id": cluster_id,
                    "total_nodes": cluster_info.get("total_nodes", 0),
                    "total_pods": cluster_info.get("total_pods", 0),
                    "total_namespaces": cluster_info.get("total_namespaces", 0),
                    "k8s_version": cluster_info.get("k8s_version"),
                    "gadget_health_status": gadget_health.get("health_status", "unknown"),
                    "gadget_version": gadget_health.get("version")
                })
                
                logger.info("Cluster info updated", cluster_id=cluster_id)
        except Exception as e:
            logger.warning("Failed to fetch cluster info", cluster_id=cluster_id, error=str(e))
        
        # Fetch the complete cluster record
        cluster = await database.fetch_one(
            """SELECT id, name, description, environment, provider, region,
                      connection_type, api_server_url, gadget_endpoint,
                      gadget_health_status, gadget_version, status,
                      total_nodes, total_pods, total_namespaces,
                      k8s_version, created_at, updated_at
               FROM clusters WHERE id = :cluster_id""",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            logger.error("Cluster not found after creation", cluster_id=cluster_id)
            # Return minimal response instead of error
            return {
                "message": "Cluster created successfully",
                "cluster": {
                    "id": cluster_id,
                    "name": cluster_data.name,
                    "status": "active"
                }
            }
        
        return {
            "message": "Cluster created successfully",
            "cluster": {
                "id": cluster["id"],
                "name": cluster["name"],
                "description": cluster["description"],
                "environment": cluster["environment"],
                "provider": cluster["provider"],
                "region": cluster["region"],
                "connection_type": cluster["connection_type"],
                "api_server_url": cluster["api_server_url"],
                "gadget_endpoint": cluster["gadget_endpoint"],
                "gadget_health_status": cluster["gadget_health_status"],
                "gadget_version": cluster["gadget_version"],
                "status": cluster["status"],
                "total_nodes": cluster["total_nodes"],
                "total_pods": cluster["total_pods"],
                "total_namespaces": cluster["total_namespaces"],
                "k8s_version": cluster["k8s_version"],
                "created_at": cluster["created_at"],
                "updated_at": cluster["updated_at"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create cluster failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create cluster: {str(e)}"
        )


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: int):
    """Get cluster by ID"""
    try:
        query = """
        SELECT id, name, description, environment, provider, region,
               connection_type, api_server_url, gadget_endpoint,
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
        
        return {
            "id": cluster["id"],
            "name": cluster["name"],
            "description": cluster["description"],
            "environment": cluster["environment"],
            "provider": cluster["provider"],
            "region": cluster["region"],
            "connection_type": cluster["connection_type"],
            "api_server_url": cluster["api_server_url"],
            "gadget_endpoint": cluster["gadget_endpoint"],
            "gadget_health_status": cluster["gadget_health_status"],
            "gadget_version": cluster["gadget_version"],
            "status": cluster["status"],
            "total_nodes": cluster["total_nodes"],
            "total_pods": cluster["total_pods"],
            "total_namespaces": cluster["total_namespaces"],
            "k8s_version": cluster["k8s_version"],
            "created_at": cluster["created_at"],
            "updated_at": cluster["updated_at"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get cluster failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cluster: {str(e)}"
        )


@router.delete("/clusters/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cluster(cluster_id: int):
    """Delete a cluster"""
    try:
        # Check if exists
        cluster = await database.fetch_one(
            "SELECT id FROM clusters WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        # Delete (cascade will handle related records)
        await database.execute(
            "DELETE FROM clusters WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        logger.info("Cluster deleted", cluster_id=cluster_id)
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete cluster failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete cluster: {str(e)}"
        )


@router.post("/clusters/{cluster_id}/refresh")
async def refresh_cluster(cluster_id: int):
    """Refresh cluster information"""
    try:
        # Get cluster
        cluster = await database.fetch_one(
            """SELECT id, connection_type, api_server_url, kubeconfig_encrypted,
                      token_encrypted, ca_cert_encrypted, gadget_endpoint, skip_tls_verify
               FROM clusters WHERE id = :cluster_id""",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        # Fetch updated info
        cluster_info = await cluster_info_service.get_cluster_info(
            connection_type=cluster["connection_type"],
            api_server_url=cluster["api_server_url"],
            kubeconfig=cluster["kubeconfig_encrypted"],
            token=cluster["token_encrypted"],
            ca_cert=cluster["ca_cert_encrypted"],
            skip_tls_verify=cluster["skip_tls_verify"] or False
        )
        
        gadget_health = await cluster_info_service.check_gadget_health(
            cluster["gadget_endpoint"]
        )
        
        # Update
        if not cluster_info.get("error"):
            await database.execute(
                """UPDATE clusters
                   SET total_nodes = :total_nodes,
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
        
        return {
            "message": "Cluster refreshed",
            "cluster_info": cluster_info,
            "gadget_health": gadget_health
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Refresh cluster failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh cluster: {str(e)}"
        )

