"""Analysis Management API Endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import grpc
import sys
import os

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from proto import analysis_orchestrator_pb2
from app.grpc_clients import grpc_clients

router = APIRouter(prefix="/analyses", tags=["analyses"])


# Pydantic Models
class AnalysisCreate(BaseModel):
    cluster_id: int
    name: str
    description: Optional[str] = None
    analysis_type: str  # "dependency_mapping", "change_detection", etc.
    parameters: Optional[Dict[str, Any]] = None
    schedule_expression: Optional[str] = None  # Cron expression
    created_by: int


class AnalysisResponse(BaseModel):
    id: int
    cluster_id: int
    name: str
    description: str
    analysis_type: str
    status: str
    schedule_expression: str
    is_scheduled: bool
    run_count: int


class AnalysisListResponse(BaseModel):
    analyses: List[AnalysisResponse]
    total_count: int


class AnalysisRunResponse(BaseModel):
    id: int
    analysis_id: int
    status: str
    duration_seconds: int
    result_summary: str
    error_message: str


class AnalysisHistoryResponse(BaseModel):
    runs: List[AnalysisRunResponse]


@router.post("/", response_model=AnalysisResponse)
async def create_analysis(analysis: AnalysisCreate):
    """Create a new analysis"""
    try:
        # Map analysis type
        analysis_type_map = {
            "dependency_mapping": analysis_orchestrator_pb2.AnalysisType.DEPENDENCY_MAPPING,
            "change_detection": analysis_orchestrator_pb2.AnalysisType.CHANGE_DETECTION,
            "anomaly_detection": analysis_orchestrator_pb2.AnalysisType.ANOMALY_DETECTION,
            "baseline_creation": analysis_orchestrator_pb2.AnalysisType.BASELINE_CREATION,
            "risk_assessment": analysis_orchestrator_pb2.AnalysisType.RISK_ASSESSMENT,
        }
        
        request = analysis_orchestrator_pb2.CreateAnalysisRequest(
            cluster_id=analysis.cluster_id,
            name=analysis.name,
            description=analysis.description or "",
            analysis_type=analysis_type_map.get(
                analysis.analysis_type,
                analysis_orchestrator_pb2.AnalysisType.UNKNOWN_ANALYSIS_TYPE
            ),
            parameters=analysis.parameters or {},
            schedule_expression=analysis.schedule_expression or "",
            created_by=analysis.created_by
        )
        
        response = grpc_clients.analysis_orchestrator.CreateAnalysis(request)
        
        return AnalysisResponse(
            id=response.id,
            cluster_id=response.cluster_id,
            name=response.name,
            description=response.description,
            analysis_type=_map_analysis_type(response.analysis_type),
            status=_map_status(response.status),
            schedule_expression=response.schedule_expression,
            is_scheduled=response.is_scheduled,
            run_count=response.run_count
        )
    
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


@router.get("/", response_model=AnalysisListResponse)
async def list_analyses(
    cluster_id: Optional[int] = None,
    analysis_type: Optional[str] = None,
    status: Optional[str] = None
):
    """List analyses with filters"""
    try:
        # Map filters
        analysis_type_proto = analysis_orchestrator_pb2.AnalysisType.UNKNOWN_ANALYSIS_TYPE
        if analysis_type:
            analysis_type_map = {
                "dependency_mapping": analysis_orchestrator_pb2.AnalysisType.DEPENDENCY_MAPPING,
                "change_detection": analysis_orchestrator_pb2.AnalysisType.CHANGE_DETECTION,
                "anomaly_detection": analysis_orchestrator_pb2.AnalysisType.ANOMALY_DETECTION,
                "baseline_creation": analysis_orchestrator_pb2.AnalysisType.BASELINE_CREATION,
                "risk_assessment": analysis_orchestrator_pb2.AnalysisType.RISK_ASSESSMENT,
            }
            analysis_type_proto = analysis_type_map.get(analysis_type, analysis_orchestrator_pb2.AnalysisType.UNKNOWN_ANALYSIS_TYPE)
        
        status_proto = analysis_orchestrator_pb2.AnalysisStatus.UNKNOWN_STATUS
        if status:
            status_map = {
                "pending": analysis_orchestrator_pb2.AnalysisStatus.PENDING,
                "running": analysis_orchestrator_pb2.AnalysisStatus.RUNNING,
                "completed": analysis_orchestrator_pb2.AnalysisStatus.COMPLETED,
                "failed": analysis_orchestrator_pb2.AnalysisStatus.FAILED,
                "cancelled": analysis_orchestrator_pb2.AnalysisStatus.CANCELLED,
            }
            status_proto = status_map.get(status, analysis_orchestrator_pb2.AnalysisStatus.UNKNOWN_STATUS)
        
        request = analysis_orchestrator_pb2.ListAnalysesRequest(
            cluster_id=cluster_id or 0,
            analysis_type=analysis_type_proto,
            status=status_proto
        )
        
        response = grpc_clients.analysis_orchestrator.ListAnalyses(request)
        
        analyses = [
            AnalysisResponse(
                id=a.id,
                cluster_id=a.cluster_id,
                name=a.name,
                description=a.description,
                analysis_type=_map_analysis_type(a.analysis_type),
                status=_map_status(a.status),
                schedule_expression=a.schedule_expression,
                is_scheduled=a.is_scheduled,
                run_count=a.run_count
            )
            for a in response.analyses
        ]
        
        return AnalysisListResponse(
            analyses=analyses,
            total_count=response.total_count
        )
    
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: int):
    """Get analysis by ID"""
    try:
        request = analysis_orchestrator_pb2.GetAnalysisRequest(id=analysis_id)
        response = grpc_clients.analysis_orchestrator.GetAnalysis(request)
        
        return AnalysisResponse(
            id=response.id,
            cluster_id=response.cluster_id,
            name=response.name,
            description=response.description,
            analysis_type=_map_analysis_type(response.analysis_type),
            status=_map_status(response.status),
            schedule_expression=response.schedule_expression,
            is_scheduled=response.is_scheduled,
            run_count=response.run_count
        )
    
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Analysis not found")
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: int):
    """Delete analysis"""
    try:
        request = analysis_orchestrator_pb2.DeleteAnalysisRequest(id=analysis_id)
        response = grpc_clients.analysis_orchestrator.DeleteAnalysis(request)
        
        if not response.success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return {"message": "Analysis deleted successfully"}
    
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


@router.post("/{analysis_id}/execute")
async def execute_analysis(analysis_id: int):
    """Execute analysis immediately"""
    try:
        request = analysis_orchestrator_pb2.ExecuteAnalysisRequest(id=analysis_id)
        response = grpc_clients.analysis_orchestrator.ExecuteAnalysis(request)
        
        return {
            "success": response.success,
            "message": response.message,
            "result_summary": response.result_summary
        }
    
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


@router.get("/{analysis_id}/history", response_model=AnalysisHistoryResponse)
async def get_analysis_history(analysis_id: int, limit: int = 10):
    """Get analysis execution history"""
    try:
        request = analysis_orchestrator_pb2.GetAnalysisHistoryRequest(
            analysis_id=analysis_id,
            limit=limit
        )
        response = grpc_clients.analysis_orchestrator.GetAnalysisHistory(request)
        
        runs = [
            AnalysisRunResponse(
                id=r.id,
                analysis_id=r.analysis_id,
                status=_map_status(r.status),
                duration_seconds=r.duration_seconds,
                result_summary=r.result_summary,
                error_message=r.error_message
            )
            for r in response.runs
        ]
        
        return AnalysisHistoryResponse(runs=runs)
    
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")


def _map_analysis_type(proto_type) -> str:
    """Map proto analysis type to string"""
    type_map = {
        analysis_orchestrator_pb2.AnalysisType.DEPENDENCY_MAPPING: "dependency_mapping",
        analysis_orchestrator_pb2.AnalysisType.CHANGE_DETECTION: "change_detection",
        analysis_orchestrator_pb2.AnalysisType.ANOMALY_DETECTION: "anomaly_detection",
        analysis_orchestrator_pb2.AnalysisType.BASELINE_CREATION: "baseline_creation",
        analysis_orchestrator_pb2.AnalysisType.RISK_ASSESSMENT: "risk_assessment",
    }
    return type_map.get(proto_type, "unknown")


def _map_status(proto_status) -> str:
    """Map proto status to string"""
    status_map = {
        analysis_orchestrator_pb2.AnalysisStatus.PENDING: "pending",
        analysis_orchestrator_pb2.AnalysisStatus.RUNNING: "running",
        analysis_orchestrator_pb2.AnalysisStatus.COMPLETED: "completed",
        analysis_orchestrator_pb2.AnalysisStatus.FAILED: "failed",
        analysis_orchestrator_pb2.AnalysisStatus.CANCELLED: "cancelled",
    }
    return status_map.get(proto_status, "unknown")

