"""
Graph Query Client for Analysis Orchestrator

HTTP client for querying Neo4j graph data via graph-query microservice.
Used for:
- Dependency mapping analysis
- Communication topology
- Workload discovery
"""

import logging
from typing import Dict, List, Optional, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GraphQueryClient:
    """
    HTTP client for graph-query microservice
    
    Provides access to Neo4j graph data for analysis:
    - Workload discovery
    - Communication relationships
    - Dependency mapping
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize client
        
        Args:
            base_url: Graph query service URL
                     Falls back to settings.graph_query_url
        """
        self.base_url = (base_url or settings.graph_query_url).rstrip("/")
        self.timeout = 30.0
        logger.info(f"GraphQueryClient initialized: {self.base_url}")
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to graph-query service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.base_url}{endpoint}"
                
                # Filter out None values from params
                if params:
                    params = {k: v for k, v in params.items() if v is not None}
                
                if method == "GET":
                    response = await client.get(url, params=params)
                elif method == "POST":
                    response = await client.post(url, json=json_body, params=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"Graph query failed",
                        endpoint=endpoint,
                        status=response.status_code,
                        response=response.text[:500]
                    )
                    return None
                    
        except httpx.ConnectError as e:
            logger.warning(f"Cannot connect to graph-query: {e}")
            return None
        except Exception as e:
            logger.error(f"Graph query error: {e}")
            return None
    
    async def get_workloads(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get workloads from graph database
        
        Returns list of workload nodes with metadata
        """
        params = {
            "limit": limit
        }
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if namespace:
            params["namespace"] = namespace
        
        result = await self._request("GET", "/workloads", params=params)
        
        if result and result.get("success"):
            return result.get("data", [])
        
        return []
    
    async def get_communications(
        self,
        cluster_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get communications (edges) from graph database
        
        Returns list of communication relationships
        """
        params = {
            "limit": limit
        }
        if cluster_id:
            params["cluster_id"] = str(cluster_id)
        if analysis_id:
            params["analysis_id"] = str(analysis_id)
        if namespace:
            params["namespace"] = namespace
        
        result = await self._request("GET", "/communications", params=params)
        
        if result and result.get("success"):
            return result.get("data", [])
        
        return []
    
    async def get_dependency_graph(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        depth: int = 3
    ) -> Dict[str, Any]:
        """
        Get full dependency graph (nodes + edges)
        
        Returns:
            {
                "nodes": [...],
                "edges": [...],
                "total_nodes": int,
                "total_edges": int
            }
        """
        # Get workloads first
        workloads = await self.get_workloads(cluster_id, analysis_id, namespace)
        
        # Get communications
        communications = await self.get_communications(cluster_id, analysis_id, namespace)
        
        # Transform to graph format
        nodes = []
        node_ids = set()
        
        for w in workloads:
            node_id = w.get("id") or f"{w.get('namespace')}:{w.get('name')}"
            if node_id not in node_ids:
                nodes.append({
                    "id": node_id,
                    "name": w.get("name", "unknown"),
                    "kind": w.get("kind", "Pod"),
                    "namespace": w.get("namespace", "default"),
                    "cluster_id": str(cluster_id),
                    "status": w.get("status", "active"),
                    "labels": w.get("labels", {})
                })
                node_ids.add(node_id)
        
        edges = []
        for c in communications:
            edges.append({
                "source_id": c.get("source_id", ""),
                "target_id": c.get("destination_id", c.get("target_id", "")),
                "edge_type": "COMMUNICATES_WITH",
                "protocol": c.get("protocol", "TCP"),
                "port": c.get("destination_port", c.get("port", 0)),
                "request_count": c.get("request_count", 0)
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        }
    
    async def get_isolated_workloads(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get workloads with no communications
        
        Useful for identifying unused/orphaned workloads
        """
        graph = await self.get_dependency_graph(cluster_id, analysis_id, namespace)
        
        # Find nodes with no edges
        connected_nodes = set()
        for edge in graph.get("edges", []):
            connected_nodes.add(edge.get("source_id"))
            connected_nodes.add(edge.get("target_id"))
        
        isolated = [
            node for node in graph.get("nodes", [])
            if node.get("id") not in connected_nodes
        ]
        
        return isolated
    
    async def get_critical_paths(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        min_depth: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get critical dependency paths (high connectivity chains)
        
        Returns paths where failure would cascade
        """
        # This would require more complex graph traversal
        # For now, return nodes with high connection count
        graph = await self.get_dependency_graph(cluster_id, analysis_id)
        
        # Count connections per node
        connection_count = {}
        for edge in graph.get("edges", []):
            src = edge.get("source_id")
            dst = edge.get("target_id")
            connection_count[src] = connection_count.get(src, 0) + 1
            connection_count[dst] = connection_count.get(dst, 0) + 1
        
        # Return nodes with 3+ connections as "critical"
        critical_nodes = [
            {"node_id": node_id, "connection_count": count}
            for node_id, count in connection_count.items()
            if count >= min_depth
        ]
        
        return sorted(critical_nodes, key=lambda x: x["connection_count"], reverse=True)
    
    async def health_check(self) -> bool:
        """Check if graph-query service is healthy"""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "healthy" if result else False
        except Exception:
            return False


# Global singleton
_graph_client: Optional[GraphQueryClient] = None


def get_graph_client() -> GraphQueryClient:
    """Get or create global GraphQueryClient instance"""
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphQueryClient()
    return _graph_client

