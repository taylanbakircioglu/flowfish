"""
Graph Query Service  
Main entry point - REST API
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from fastapi import Query

from app.config import settings
from app.graph_query_engine import graph_query_engine

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Flowfish Graph Query Service",
    description="Query API for dependency graph",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class QueryRequest(BaseModel):
    query: str


class BatchDependencyServiceItem(BaseModel):
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    owner_name: Optional[str] = None
    label_key: Optional[str] = None
    label_value: Optional[str] = None
    annotation_key: Optional[str] = None
    annotation_value: Optional[str] = None
    ip: Optional[str] = None


class BatchDependencyRequest(BaseModel):
    analysis_id: Optional[str] = None
    cluster_id: Optional[str] = None
    services: List[BatchDependencyServiceItem]
    depth: int = 1
    include_communication_details: bool = True


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": settings.service_name}


@app.post("/query")
async def execute_query(request: QueryRequest):
    """
    Execute custom Cypher query for Dev Console
    
    Security features:
    - Query validation at API Gateway level
    - Result size limits at engine level
    
    Returns:
        success: bool
        data: List of records
        count: Number of records
    """
    try:
        result = graph_query_engine.execute_query(request.query)
        return result
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dev-console/schema")
async def get_neo4j_schema():
    """
    Get Neo4j schema information for Dev Console
    
    Returns node labels and relationship types with their properties.
    """
    try:
        # Get node labels
        labels_result = graph_query_engine.execute_query(
            "CALL db.labels() YIELD label RETURN label ORDER BY label"
        )
        
        # Get relationship types
        rels_result = graph_query_engine.execute_query(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
        )
        
        # Get property keys
        props_result = graph_query_engine.execute_query(
            "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey ORDER BY propertyKey"
        )
        
        schema = {
            "database": "neo4j",
            "node_labels": [r.get("label") for r in labels_result.get("data", [])],
            "relationship_types": [r.get("relationshipType") for r in rels_result.get("data", [])],
            "property_keys": [r.get("propertyKey") for r in props_result.get("data", [])],
            "tables": [
                {
                    "name": "Workload (Node)",
                    "columns": [
                        {"name": "id", "type": "String", "description": "Unique identifier"},
                        {"name": "name", "type": "String", "description": "Workload name"},
                        {"name": "namespace", "type": "String", "description": "Kubernetes namespace"},
                        {"name": "kind", "type": "String", "description": "Resource kind"},
                        {"name": "cluster_id", "type": "String", "description": "Cluster ID"},
                        {"name": "analysis_id", "type": "String", "description": "Analysis ID"},
                        {"name": "ip", "type": "String", "description": "Pod IP address"},
                        {"name": "status", "type": "String", "description": "Pod status"},
                    ]
                },
                {
                    "name": "ExternalEndpoint (Node)",
                    "columns": [
                        {"name": "id", "type": "String", "description": "Unique identifier"},
                        {"name": "ip_address", "type": "String", "description": "External IP"},
                        {"name": "hostname", "type": "String", "description": "DNS hostname"},
                        {"name": "port", "type": "Integer", "description": "Port number"},
                    ]
                },
                {
                    "name": "COMMUNICATES_WITH (Relationship)",
                    "columns": [
                        {"name": "protocol", "type": "String", "description": "Network protocol"},
                        {"name": "destination_port", "type": "Integer", "description": "Destination port"},
                        {"name": "request_count", "type": "Integer", "description": "Number of requests"},
                        {"name": "bytes_transferred", "type": "Long", "description": "Bytes transferred"},
                        {"name": "first_seen", "type": "DateTime", "description": "First seen timestamp"},
                        {"name": "last_seen", "type": "DateTime", "description": "Last seen timestamp"},
                        {"name": "analysis_id", "type": "String", "description": "Analysis ID"},
                    ]
                },
                {
                    "name": "QUERIES_DNS (Relationship)",
                    "columns": [
                        {"name": "query_name", "type": "String", "description": "DNS query name"},
                        {"name": "request_count", "type": "Integer", "description": "Number of queries"},
                        {"name": "analysis_id", "type": "String", "description": "Analysis ID"},
                    ]
                }
            ]
        }
        
        return schema
        
    except Exception as e:
        logger.error(f"Failed to get schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: POST /dependencies, POST /subgraph, POST /path endpoints removed.
# GraphQueryEngine does not implement get_dependencies(), get_subgraph(), find_path().
# Use GET /dependencies/stream for dependency lookups instead.


@app.get("/communications")
async def get_communications(
    namespace: Optional[str] = None,
    protocol: Optional[str] = None,
    source_id: Optional[str] = None,
    destination_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100
):
    """Get communications between workloads"""
    logger.info(f"[COMMS_ENDPOINT] Request: analysis_id={analysis_id}, cluster_id={cluster_id}, namespace={namespace}, limit={limit}")
    try:
        result = graph_query_engine.get_communications(
            source_id=source_id,
            destination_id=destination_id,
            namespace=namespace,
            protocol=protocol,
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        data_count = len(result.get("data", [])) if result else 0
        logger.info(f"[COMMS_ENDPOINT] Result: success={result.get('success')}, data_count={data_count}")
        return result
    except Exception as e:
        logger.error(f"[COMMS_ENDPOINT] Failed to get communications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/communications/count")
async def get_communication_count(
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    namespace: Optional[str] = None
):
    """Get total count of communications (for smart edge limit calculation)"""
    try:
        count = graph_query_engine.get_communication_count(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            namespace=namespace
        )
        return {"total_count": count}
    except Exception as e:
        logger.error(f"Failed to get communication count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workloads")
async def get_workloads(
    namespace: Optional[str] = None,
    kind: Optional[str] = None,
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    limit: int = 1000
):
    """Get workloads with optional filters"""
    try:
        result = graph_query_engine.get_workloads(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            namespace=namespace,
            kind=kind,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get workloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dependencies/graph")
async def get_dependency_graph(
    cluster_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
    namespace: Optional[str] = None,
    depth: int = 2,
    search: Optional[str] = Query(None, min_length=3, description="Search term (min 3 chars) to filter nodes by name, namespace, or id")
):
    """Get dependency graph with nodes and edges for visualization (Live Map)
    
    When search is provided (min 3 chars), filters results to edges where at least
    one endpoint matches the search term. Also increases the result limit to ensure
    all matching results are returned.
    """
    try:
        result = graph_query_engine.get_dependency_graph(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            depth=depth,
            search=search
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get dependency graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/communications/stats")
async def get_communication_stats(
    cluster_id: Optional[str] = None,
    analysis_id: Optional[str] = None
):
    """Get communication statistics"""
    try:
        result = graph_query_engine.get_communication_stats(
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get communication stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cross-namespace")
async def get_cross_namespace_communications(
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    limit: int = 50
):
    """Get cross-namespace communications"""
    try:
        result = graph_query_engine.get_cross_namespace_communications(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get cross-namespace communications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/high-risk")
async def get_high_risk_communications(
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    limit: int = 50
):
    """Get high-risk communications"""
    try:
        result = graph_query_engine.get_high_risk_communications(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get high-risk communications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dependencies/stream")
async def find_pod_dependencies(
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    pod_name: Optional[str] = None,
    namespace: Optional[str] = None,
    owner_name: Optional[str] = None,
    label_key: Optional[str] = None,
    label_value: Optional[str] = None,
    annotation_key: Optional[str] = None,
    annotation_value: Optional[str] = None,
    ip: Optional[str] = None,
    depth: int = Query(1, ge=1, le=5, description="Traversal depth"),
    format: Optional[str] = Query("json", description="Response format: json, mermaid, dot")
):
    """
    Find a pod by any metadata and return upstream/downstream dependencies.
    
    The matched pod becomes the **upstream**. Pods it communicates with are **downstream**.
    Pods that communicate TO the matched pod are returned as **callers**.
    
    Search by any combination of: pod_name, namespace, owner_name, annotation_key/value, label_key/value, ip.
    At least one search parameter is required.
    
    Use format=mermaid or format=dot for text-based graph output suitable for LLMs.
    """
    try:
        result = graph_query_engine.find_pod_dependencies(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            pod_name=pod_name,
            namespace=namespace,
            owner_name=owner_name,
            label_key=label_key,
            label_value=label_value,
            annotation_key=annotation_key,
            annotation_value=annotation_value,
            ip=ip,
            depth=depth
        )
        if format and format in ("mermaid", "dot"):
            from fastapi.responses import PlainTextResponse
            text = graph_query_engine.format_dependency_graph(result, format)
            return PlainTextResponse(content=text, media_type="text/plain")
        return result
    except Exception as e:
        logger.error(f"Failed to find pod dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/external")
async def get_external_communications(
    namespace: Optional[str] = None,
    analysis_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    limit: int = 50
):
    """Get external communications (to endpoints outside the cluster)"""
    try:
        result = graph_query_engine.get_external_communications(
            namespace=namespace,
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get external communications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dependencies/batch")
async def batch_find_dependencies(request: BatchDependencyRequest):
    """Batch find dependencies for multiple services in one request."""
    try:
        services = [s.model_dump() for s in request.services]
        result = graph_query_engine.batch_find_dependencies(
            analysis_id=request.analysis_id,
            cluster_id=request.cluster_id,
            services=services,
            depth=request.depth,
            include_communication_details=request.include_communication_details,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to batch find dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dependencies/summary")
async def get_dependency_summary(
    analysis_ids: List[str] = Query(..., description="Analysis IDs (required, at least one)"),
    cluster_id: Optional[str] = None,
    pod_name: Optional[str] = None,
    namespace: Optional[str] = None,
    owner_name: Optional[str] = None,
    label_key: Optional[str] = None,
    label_value: Optional[str] = None,
    annotation_key: Optional[str] = None,
    annotation_value: Optional[str] = None,
    ip: Optional[str] = None,
    depth: int = Query(1, ge=1, le=5, description="Traversal depth"),
):
    """
    AI-agent-friendly dependency summary. Returns grouped, compact JSON.

    Requires at least one analysis_id and one search parameter.
    Dependencies are grouped by service_category with annotations/labels
    prominently exposed for cross-project impact analysis.
    """
    try:
        stream_result = graph_query_engine.find_pod_dependencies(
            analysis_ids=analysis_ids,
            cluster_id=cluster_id,
            pod_name=pod_name,
            namespace=namespace,
            owner_name=owner_name,
            label_key=label_key,
            label_value=label_value,
            annotation_key=annotation_key,
            annotation_value=annotation_value,
            ip=ip,
            depth=depth,
        )
        return graph_query_engine.format_dependency_summary(stream_result, analysis_ids)
    except Exception as e:
        logger.error(f"Failed to get dependency summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dependencies/diff")
async def diff_dependencies(
    analysis_id_before: str = Query(..., description="Analysis ID for before state"),
    analysis_id_after: str = Query(..., description="Analysis ID for after state"),
    pod_name: Optional[str] = None,
    namespace: Optional[str] = None,
    owner_name: Optional[str] = None,
    cluster_id: Optional[str] = None,
):
    """Diff dependencies between two analysis runs."""
    try:
        result = graph_query_engine.diff_pod_dependencies(
            analysis_id_before=analysis_id_before,
            analysis_id_after=analysis_id_after,
            pod_name=pod_name,
            namespace=namespace,
            owner_name=owner_name,
            cluster_id=cluster_id,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to diff dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn
    logger.info(f"🐟 Starting {settings.service_name}...")
    uvicorn.run(app, host=settings.host, port=settings.port)

