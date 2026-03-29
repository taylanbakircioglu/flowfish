"""
Timeseries Query Client for Analysis Orchestrator

HTTP client for querying ClickHouse data via timeseries-query microservice.
Used for:
- Anomaly detection (traffic patterns, unusual behavior)
- Change detection (compare with baseline)
- Event statistics for analysis results
"""

import logging
from typing import Dict, List, Optional, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TimeseriesQueryClient:
    """
    HTTP client for timeseries-query microservice
    
    Provides access to ClickHouse event data for analysis:
    - Event statistics
    - Event queries with filtering
    - Time-range aggregations
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize client
        
        Args:
            base_url: Timeseries query service URL
                     Falls back to settings.timeseries_query_url
        """
        self.base_url = (base_url or settings.timeseries_query_url).rstrip("/")
        self.timeout = 30.0
        logger.info(f"TimeseriesQueryClient initialized: {self.base_url}")
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to timeseries-query service"""
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
                elif method == "DELETE":
                    response = await client.delete(url, params=params)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"Timeseries query failed",
                        endpoint=endpoint,
                        status=response.status_code,
                        response=response.text[:500]
                    )
                    return None
                    
        except httpx.ConnectError as e:
            logger.warning(f"Cannot connect to timeseries-query: {e}")
            return None
        except Exception as e:
            logger.error(f"Timeseries query error: {e}")
            return None
    
    async def get_event_stats(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get event statistics for a cluster/analysis
        
        Returns:
            - total_events
            - event_counts by type
            - time_range
            - top_namespaces
            - top_pods
        """
        result = await self._request(
            "GET",
            "/events/stats",
            params={"cluster_id": cluster_id, "analysis_id": analysis_id}
        )
        
        return result or {
            "total_events": 0,
            "event_counts": {},
            "time_range": {"start": None, "end": None},
            "top_namespaces": [],
            "top_pods": []
        }
    
    async def get_network_flows(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get network flow events"""
        result = await self._request(
            "GET",
            "/events/network",
            params={
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "limit": limit,
                "offset": offset
            }
        )
        return result or {"events": [], "total": 0}
    
    async def get_dns_queries(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get DNS query events"""
        result = await self._request(
            "GET",
            "/events/dns",
            params={
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "limit": limit
            }
        )
        return result or {"queries": [], "total": 0}
    
    async def get_security_events(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get security/capability events"""
        result = await self._request(
            "GET",
            "/events/security",
            params={
                "cluster_id": cluster_id,
                "analysis_id": analysis_id,
                "namespace": namespace,
                "limit": limit
            }
        )
        return result or {"events": [], "total": 0}
    
    async def get_all_events(
        self,
        cluster_id: int,
        analysis_id: Optional[int] = None,
        namespace: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get all events with filtering"""
        params = {
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "namespace": namespace,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit
        }
        
        if event_types:
            params["event_types"] = ",".join(event_types)
        
        result = await self._request("GET", "/events", params=params)
        return result or {"events": [], "total": 0, "has_more": False}
    
    async def health_check(self) -> bool:
        """Check if timeseries-query service is healthy"""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "healthy" if result else False
        except Exception:
            return False


# Global singleton
_timeseries_client: Optional[TimeseriesQueryClient] = None


def get_timeseries_client() -> TimeseriesQueryClient:
    """Get or create global TimeseriesQueryClient instance"""
    global _timeseries_client
    if _timeseries_client is None:
        _timeseries_client = TimeseriesQueryClient()
    return _timeseries_client

