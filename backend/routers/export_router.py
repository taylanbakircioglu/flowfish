"""
Export Router - Data export functionality
Sprint 5-6: Export events and analysis data to various formats

Supports:
- CSV export for tabular data
- JSON export for structured data  
- PDF reports (via HTML rendering)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime
import structlog
import csv
import json
import io

from utils.jwt_utils import get_current_user
from services.event_service import EventService, get_event_service
from repositories.event_repository import get_event_repository
from services.pdf_report_service import pdf_service
from database.postgresql import database

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_service() -> EventService:
    """Dependency provider for EventService"""
    return get_event_service()


# =============================================================================
# CSV Export Endpoints
# =============================================================================

@router.get(
    "/events/csv",
    summary="Export Events to CSV",
    description="Export events data to CSV format for analysis in Excel or other tools."
)
async def export_events_csv(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum rows"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export events to CSV"""
    try:
        # Parse event types
        types_list = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        # Get events
        response = await service.get_all_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            event_types=types_list,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )
        
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "timestamp", "event_type", "namespace", "pod", "container",
            "source", "target", "details"
        ])
        
        # Data rows
        for event in response.events:
            writer.writerow([
                event.timestamp.isoformat() if event.timestamp else "",
                event.event_type,
                event.namespace,
                event.pod,
                event.container or "",
                event.source or "",
                event.target or "",
                event.details
            ])
        
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_events_{cluster_id}_{timestamp}.csv"
        
        logger.info("CSV export completed", 
                   cluster_id=cluster_id,
                   rows=len(response.events))
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("CSV export failed", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get(
    "/network-flows/csv",
    summary="Export Network Flows to CSV",
    description="Export network flow data to CSV format."
)
async def export_network_flows_csv(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum rows"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export network flows to CSV"""
    try:
        response = await service.get_network_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=limit,
            offset=0
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "timestamp", "namespace", "pod", "source_ip", "source_port",
            "dest_ip", "dest_port", "protocol", "direction",
            "bytes_sent", "bytes_received", "latency_ms"
        ])
        
        for event in response.events:
            writer.writerow([
                event.timestamp.isoformat() if event.timestamp else "",
                event.namespace,
                event.pod,
                event.source_ip,
                event.source_port,
                event.dest_ip,
                event.dest_port,
                event.protocol,
                event.direction,
                event.bytes_sent,
                event.bytes_received,
                event.latency_ms
            ])
        
        output.seek(0)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_network_flows_{cluster_id}_{timestamp}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("Network flows CSV export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get(
    "/dns-queries/csv",
    summary="Export DNS Queries to CSV",
    description="Export DNS query data to CSV format."
)
async def export_dns_queries_csv(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum rows"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export DNS queries to CSV"""
    try:
        response = await service.get_dns_queries(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=limit,
            offset=0
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "timestamp", "namespace", "pod", "query_name", "query_type",
            "response_code", "response_ips", "latency_ms", "dns_server"
        ])
        
        for query in response.queries:
            writer.writerow([
                query.timestamp.isoformat() if query.timestamp else "",
                query.namespace,
                query.pod,
                query.query_name,
                query.query_type,
                query.response_code,
                ",".join(query.response_ips),
                query.latency_ms,
                query.dns_server_ip
            ])
        
        output.seek(0)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_dns_queries_{cluster_id}_{timestamp}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("DNS queries CSV export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get(
    "/security-events/csv",
    summary="Export Security Events to CSV",
    description="Export security/capability events to CSV format."
)
async def export_security_events_csv(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum rows"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export security events to CSV"""
    try:
        response = await service.get_security_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=limit,
            offset=0
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "timestamp", "namespace", "pod", "security_type", "capability",
            "syscall", "verdict", "pid", "comm"
        ])
        
        for event in response.events:
            writer.writerow([
                event.timestamp.isoformat() if event.timestamp else "",
                event.namespace,
                event.pod,
                event.security_type,
                event.capability or "",
                event.syscall or "",
                event.verdict,
                event.pid,
                event.comm
            ])
        
        output.seek(0)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_security_events_{cluster_id}_{timestamp}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("Security events CSV export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# =============================================================================
# JSON Export Endpoints
# =============================================================================

@router.get(
    "/events/json",
    summary="Export Events to JSON",
    description="Export events data to JSON format."
)
async def export_events_json(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum events"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export events to JSON"""
    try:
        types_list = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        response = await service.get_all_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            event_types=types_list,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )
        
        # Convert to JSON-serializable format
        events_data = []
        for event in response.events:
            events_data.append({
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "cluster_id": event.cluster_id,
                "analysis_id": event.analysis_id,
                "namespace": event.namespace,
                "pod": event.pod,
                "container": event.container,
                "source": event.source,
                "target": event.target,
                "details": event.details,
                "data": event.data
            })
        
        export_data = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "total_events": response.total,
            "exported_events": len(events_data),
            "events": events_data
        }
        
        output = json.dumps(export_data, indent=2)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_events_{cluster_id}_{timestamp}.json"
        
        logger.info("JSON export completed", 
                   cluster_id=cluster_id,
                   events=len(events_data))
        
        return StreamingResponse(
            iter([output]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("JSON export failed", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get(
    "/graph/json",
    summary="Export Dependency Graph to JSON",
    description="Export the dependency graph in JSON format for visualization tools."
)
async def export_graph_json(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    current_user: dict = Depends(get_current_user)
):
    """Export dependency graph to JSON (D3.js compatible)"""
    try:
        from database.neo4j import neo4j_service
        
        # Get graph data from Neo4j
        nodes = neo4j_service.get_workloads(cluster_id, analysis_id)
        edges = neo4j_service.get_communications(cluster_id, analysis_id)
        
        # Format for D3.js / visualization tools
        graph_data = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "nodes": [
                {
                    "id": node.get("id", ""),
                    "name": node.get("name", ""),
                    "namespace": node.get("namespace", ""),
                    "type": node.get("type", "workload"),
                    "labels": node.get("labels", {}),
                    "annotations": node.get("annotations", {}),
                    "metadata": node.get("metadata", {})
                }
                for node in nodes
            ],
            "links": [
                {
                    "source": edge.get("source_id", ""),
                    "target": edge.get("target_id", ""),
                    "protocol": edge.get("protocol", "TCP"),
                    "port": edge.get("port", 0),
                    "request_count": edge.get("request_count", 0),
                    "bytes_transferred": edge.get("bytes_transferred", 0)
                }
                for edge in edges
            ],
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges)
            }
        }
        
        output = json.dumps(graph_data, indent=2)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_graph_{cluster_id}_{timestamp}.json"
        
        return StreamingResponse(
            iter([output]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("Graph JSON export failed", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# =============================================================================
# Statistics Export
# =============================================================================

@router.get(
    "/stats/json",
    summary="Export Event Statistics to JSON",
    description="Export event statistics and summary data to JSON."
)
async def export_stats_json(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export event statistics to JSON"""
    try:
        stats = await service.get_event_stats(
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        
        stats_data = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "cluster_id": stats.cluster_id,
            "analysis_id": stats.analysis_id,
            "total_events": stats.total_events,
            "event_counts": stats.event_counts,
            "time_range": {
                "start": stats.time_range.start,
                "end": stats.time_range.end
            },
            "top_namespaces": [
                {"namespace": ns.namespace, "count": ns.count}
                for ns in stats.top_namespaces
            ],
            "top_pods": [
                {"pod": p.pod, "namespace": p.namespace, "count": p.count}
                for p in stats.top_pods
            ]
        }
        
        output = json.dumps(stats_data, indent=2)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_stats_{cluster_id}_{timestamp}.json"
        
        return StreamingResponse(
            iter([output]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("Stats JSON export failed", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# =============================================================================
# PDF Export Endpoints
# =============================================================================

async def get_cluster_and_analysis_names(cluster_id: int = None, analysis_id: int = None):
    """Helper to get cluster and analysis names"""
    cluster_name = "Unknown Cluster"
    analysis_name = "Unknown Analysis"
    
    if cluster_id:
        result = await database.fetch_one(
            "SELECT name FROM clusters WHERE id = :id",
            {"id": cluster_id}
        )
        if result:
            cluster_name = result['name']
    
    if analysis_id:
        result = await database.fetch_one(
            "SELECT name, cluster_id FROM analyses WHERE id = :id",
            {"id": analysis_id}
        )
        if result:
            analysis_name = result['name']
            if not cluster_id:
                cluster_result = await database.fetch_one(
                    "SELECT name FROM clusters WHERE id = :id",
                    {"id": result['cluster_id']}
                )
                if cluster_result:
                    cluster_name = cluster_result['name']
    
    return cluster_name, analysis_name


@router.get(
    "/dependency/pdf",
    summary="Export Dependency Report to PDF",
    description="Generate a beautifully formatted PDF report of service dependencies."
)
async def export_dependency_pdf(
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    current_user: dict = Depends(get_current_user)
):
    """Export dependency graph as PDF report"""
    try:
        from database.neo4j import neo4j_service
        
        cluster_name, analysis_name = await get_cluster_and_analysis_names(cluster_id, analysis_id)
        
        # Get graph data
        nodes = neo4j_service.get_workloads(cluster_id, analysis_id)
        edges = neo4j_service.get_communications(cluster_id, analysis_id)
        
        # Calculate stats
        stats = {
            "Total Services": len(nodes),
            "Total Connections": len(edges),
            "Namespaces": len(set(n.get('namespace', '') for n in nodes)),
            "Avg Connections": round(len(edges) / max(len(nodes), 1), 1)
        }
        
        # Generate PDF
        pdf_bytes = await pdf_service.generate_dependency_report(
            cluster_name=cluster_name,
            analysis_name=analysis_name,
            nodes=nodes,
            edges=edges,
            stats=stats
        )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_dependency_report_{timestamp}.pdf"
        
        logger.info("PDF dependency report generated", 
                   cluster_id=cluster_id, 
                   nodes=len(nodes), 
                   edges=len(edges))
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("PDF dependency export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF export failed: {str(e)}"
        )


@router.get(
    "/events/pdf",
    summary="Export Events Report to PDF",
    description="Generate a beautifully formatted PDF report of events."
)
async def export_events_pdf(
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum events"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export events as PDF report"""
    try:
        cluster_name, analysis_name = await get_cluster_and_analysis_names(cluster_id, analysis_id)
        
        # Parse event types
        types_list = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        # Get events
        response = await service.get_all_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            event_types=types_list,
            limit=limit,
            offset=0
        )
        
        # Convert events to dict format
        events = []
        for event in response.events:
            events.append({
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "event_type": event.event_type,
                "namespace": event.namespace,
                "pod": event.pod,
                "details": event.details
            })
        
        # Get event counts
        stats = await service.get_event_stats(cluster_id=cluster_id, analysis_id=analysis_id)
        event_counts = stats.event_counts if stats else {}
        
        # Generate PDF
        pdf_bytes = await pdf_service.generate_events_report(
            cluster_name=cluster_name,
            analysis_name=analysis_name,
            events=events,
            event_counts=event_counts
        )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_events_report_{timestamp}.pdf"
        
        logger.info("PDF events report generated", 
                   cluster_id=cluster_id, 
                   events=len(events))
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("PDF events export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF export failed: {str(e)}"
        )


@router.get(
    "/network-flows/pdf",
    summary="Export Network Flows Report to PDF",
    description="Generate a beautifully formatted PDF report of network flows."
)
async def export_network_flows_pdf(
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum flows"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export network flows as PDF report"""
    try:
        cluster_name, analysis_name = await get_cluster_and_analysis_names(cluster_id, analysis_id)
        
        # Get network flows
        response = await service.get_network_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=limit,
            offset=0
        )
        
        # Convert to dict format
        flows = []
        total_bytes = 0
        for flow in response.events:
            flows.append({
                "source_pod": flow.pod,
                "dest_pod": getattr(flow, 'dest_pod', '-'),
                "dest_ip": flow.dest_ip,
                "dest_port": flow.dest_port,
                "protocol": flow.protocol,
                "bytes": (flow.bytes_sent or 0) + (flow.bytes_received or 0)
            })
            total_bytes += (flow.bytes_sent or 0) + (flow.bytes_received or 0)
        
        # Stats
        stats = {
            "Total Flows": len(flows),
            "Total Bytes": f"{total_bytes / (1024*1024):.2f} MB",
            "Unique Destinations": len(set(f['dest_ip'] for f in flows)),
            "Protocols": len(set(f['protocol'] for f in flows))
        }
        
        # Generate PDF
        pdf_bytes = await pdf_service.generate_network_report(
            cluster_name=cluster_name,
            analysis_name=analysis_name,
            flows=flows,
            stats=stats
        )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_network_report_{timestamp}.pdf"
        
        logger.info("PDF network report generated", 
                   cluster_id=cluster_id, 
                   flows=len(flows))
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("PDF network export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF export failed: {str(e)}"
        )


@router.get(
    "/security/pdf",
    summary="Export Security Report to PDF",
    description="Generate a beautifully formatted PDF security report."
)
async def export_security_pdf(
    cluster_id: Optional[int] = Query(None, description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum events"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
):
    """Export security events as PDF report"""
    try:
        cluster_name, analysis_name = await get_cluster_and_analysis_names(cluster_id, analysis_id)
        
        # Get security events
        response = await service.get_security_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            limit=limit,
            offset=0
        )
        
        # Convert to dict format
        security_events = []
        for event in response.events:
            security_events.append({
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "severity": "high" if event.verdict == "deny" else "medium",
                "type": event.security_type,
                "namespace": event.namespace,
                "description": f"{event.capability or event.syscall or 'Unknown'} - {event.verdict}"
            })
        
        # Generate PDF
        pdf_bytes = await pdf_service.generate_security_report(
            cluster_name=cluster_name,
            analysis_name=analysis_name,
            security_events=security_events,
            anomalies=[]  # TODO: Add anomaly detection integration
        )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"flowfish_security_report_{timestamp}.pdf"
        
        logger.info("PDF security report generated", 
                   cluster_id=cluster_id, 
                   events=len(security_events))
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error("PDF security export failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF export failed: {str(e)}"
        )
