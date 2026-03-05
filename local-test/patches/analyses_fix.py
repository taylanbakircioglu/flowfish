"""
Analysis management API endpoints
Sprint 5-6: Analysis Wizard & Communication Discovery
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import structlog
import json

from database.postgresql import database
from utils.jwt_utils import get_current_user
from grpc_clients.analysis_orchestrator_client import analysis_orchestrator_client

logger = structlog.get_logger()
router = APIRouter()

# Request/Response Models
class ScopeConfig(BaseModel):
    """Analysis scope configuration"""
    cluster_id: int
    scope_type: str = Field(..., description="cluster, namespace, deployment, pod, label")
    namespaces: Optional[List[str]] = None
    deployments: Optional[List[str]] = None
    pods: Optional[List[str]] = None
    labels: Optional[dict] = None

class GadgetConfig(BaseModel):
    """eBPF Gadget module configuration"""
    enabled_gadgets: List[str] = Field(
        ..., 
        description="List of gadget modules",
        example=["network_traffic", "dns_queries", "tcp_connections"]
    )
    network_traffic: Optional[dict] = Field(None, description="Network traffic gadget config")
    dns_queries: Optional[dict] = Field(None, description="DNS queries gadget config")
    tcp_connections: Optional[dict] = Field(None, description="TCP connections gadget config")
    process_events: Optional[dict] = Field(None, description="Process events gadget config")
    syscall_tracking: Optional[dict] = Field(None, description="Syscall tracking gadget config")
    file_access: Optional[dict] = Field(None, description="File access gadget config")

class TimeConfig(BaseModel):
    """Analysis time and profiling configuration"""
    mode: str = Field(..., description="continuous, time_range, periodic, baseline")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    periodic_interval: Optional[int] = Field(None, description="Interval in seconds for periodic mode")
    baseline_name: Optional[str] = Field(None, description="Baseline profile name")

class OutputConfig(BaseModel):
    """Analysis output and integration configuration"""
    enable_dashboard: bool = True
    enable_llm_analysis: bool = False
    llm_provider: Optional[str] = Field(None, description="openai, anthropic, azure")
    llm_model: Optional[str] = None
    enable_alarms: bool = False
    alarm_thresholds: Optional[dict] = None
    enable_webhooks: bool = False
    webhook_urls: Optional[List[str]] = None
    export_format: Optional[List[str]] = Field(None, description="csv, json, graph_json")

class AnalysisCreateRequest(BaseModel):
    """Complete analysis creation request"""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    scope: ScopeConfig
    gadgets: GadgetConfig
    time_config: TimeConfig
    output: OutputConfig

class AnalysisResponse(BaseModel):
    """Analysis response model"""
    id: int
    name: str
    description: Optional[str]
    cluster_id: int
    status: str
    scope_type: str
    scope_config: dict
    gadget_config: dict
    time_config: dict
    output_config: dict
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: int

class AnalysisRunResponse(BaseModel):
    """Analysis run response"""
    id: int
    analysis_id: int
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    events_collected: int
    communications_discovered: int
    error_message: Optional[str]


# API Endpoints

@router.post("", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    analysis: AnalysisCreateRequest
):
    """
    Create a new analysis configuration via wizard
    
    **Sprint 5-6 Feature**
    
    This endpoint creates a complete analysis configuration after the user
    completes the 4-step wizard:
    1. Scope Selection
    2. Gadget Modules
    3. Time & Profile
    4. Output & Integration
    """
    
    # Validate cluster exists
    cluster_query = "SELECT id FROM clusters WHERE id = :cluster_id AND status = 'active'"
    cluster = await database.fetch_one(cluster_query, {"cluster_id": analysis.scope.cluster_id})
    
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster with id {analysis.scope.cluster_id} not found or inactive"
        )
    
    # Insert analysis
    insert_query = """
        INSERT INTO analyses (
            name, description, cluster_id, status, scope_type, scope_config,
            gadget_config, time_config, output_config, created_by
        ) VALUES (
            :name, :description, :cluster_id, 'draft', :scope_type, :scope_config,
            :gadget_config, :time_config, :output_config, :created_by
        ) RETURNING *
    """
    
    values = {
        "name": analysis.name,
        "description": analysis.description,
        "cluster_id": analysis.scope.cluster_id,
        "scope_type": analysis.scope.scope_type,
        "scope_config": json.dumps(analysis.scope.dict()),
        "gadget_config": json.dumps(analysis.gadgets.dict()),
        "time_config": json.dumps(analysis.time_config.dict(), default=str),
        "output_config": json.dumps(analysis.output.dict()),
        "created_by": 1  # Default user for MVP
    }
    
    result = await database.fetch_one(insert_query, values)
    
    return AnalysisResponse(**result)


@router.get("", response_model=List[AnalysisResponse])
async def get_analyses(
    cluster_id: Optional[int] = None,
    status: Optional[str] = None
):
    """
    Get all analyses with optional filters
    
    **Filters:**
    - cluster_id: Filter by cluster
    - status: Filter by status (draft, running, stopped, completed, failed)
    """
    
    query = """
        SELECT * FROM analyses
        WHERE 1=1
    """
    params = {}
    
    if cluster_id:
        query += " AND cluster_id = :cluster_id"
        params["cluster_id"] = cluster_id
    
    if status:
        query += " AND status = :status"
        params["status"] = status
    
    query += " ORDER BY created_at DESC"
    
    results = await database.fetch_all(query, params)
    return [AnalysisResponse(**row) for row in results]


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get single analysis by ID"""
    
    query = "SELECT * FROM analyses WHERE id = :id"
    result = await database.fetch_one(query, {"id": analysis_id})
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    return AnalysisResponse(**result)


@router.post("/{analysis_id}/start", response_model=AnalysisRunResponse)
async def start_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Start an analysis execution
    
    **Sprint 5-6 Feature**
    
    This will:
    1. Create a new analysis_run record
    2. Start eBPF data collection via Inspektor Gadget
    3. Begin communication discovery
    4. Update analysis status to 'running'
    """
    
    # Get analysis
    analysis_query = "SELECT * FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    # Check if already running
    if analysis["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis is already running"
        )
    
    # Create analysis run
    run_query = """
        INSERT INTO analysis_runs (
            analysis_id, status, start_time, events_collected, communications_discovered
        ) VALUES (
            :analysis_id, 'running', NOW(), 0, 0
        ) RETURNING *
    """
    
    run_result = await database.fetch_one(run_query, {"analysis_id": analysis_id})
    
    # Update analysis status to running
    update_query = "UPDATE analyses SET status = 'running', updated_at = NOW() WHERE id = :id"
    await database.execute(update_query, {"id": analysis_id})
    
    # Start analysis via Analysis Orchestrator (microservice)
    try:
        logger.info("Calling Analysis Orchestrator to start analysis",
                   analysis_id=analysis_id)
        
        orchestrator_response = await analysis_orchestrator_client.start_analysis(analysis_id)
        
        logger.info("Analysis Orchestrator started analysis successfully",
                   analysis_id=analysis_id,
                   tasks=len(orchestrator_response.get("task_assignments", [])))
        
        return AnalysisRunResponse(**run_result)
        
    except Exception as e:
        # Rollback if orchestrator call failed
        logger.error("Analysis Orchestrator failed to start analysis",
                    analysis_id=analysis_id,
                    error=str(e))
        
        await database.execute(
            "UPDATE analyses SET status = 'failed', updated_at = NOW() WHERE id = :id",
            {"id": analysis_id}
        )
        await database.execute(
            "UPDATE analysis_runs SET status = 'failed', error_message = :error WHERE id = :id",
            {"id": run_result["id"], "error": f"Failed to start via orchestrator: {str(e)}"}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start analysis via orchestrator: {str(e)}"
        )


@router.post("/{analysis_id}/stop")
async def stop_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Stop a running analysis
    
    **Sprint 5-6 Feature**
    """
    
    # Get analysis
    analysis_query = "SELECT * FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    if analysis["status"] != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis is not running"
        )
    
    # Stop current run
    stop_run_query = """
        UPDATE analysis_runs 
        SET status = 'stopped', end_time = NOW()
        WHERE analysis_id = :analysis_id AND status = 'running'
    """
    await database.execute(stop_run_query, {"analysis_id": analysis_id})
    
    # Stop analysis via Analysis Orchestrator (microservice)
    try:
        logger.info("Calling Analysis Orchestrator to stop analysis",
                   analysis_id=analysis_id)
        
        stopped = await analysis_orchestrator_client.stop_analysis(analysis_id)
        
        if stopped:
            # Update analysis status
            update_query = "UPDATE analyses SET status = 'stopped', updated_at = NOW() WHERE id = :id"
            await database.execute(update_query, {"id": analysis_id})
            
            logger.info("Analysis stopped successfully via orchestrator",
                       analysis_id=analysis_id)
            
            return {
                "message": "Analysis stopped successfully", 
                "analysis_id": analysis_id
            }
        else:
            logger.warning("Analysis Orchestrator could not stop analysis",
                          analysis_id=analysis_id)
            
            return {
                "message": "Analysis stop request sent, but orchestrator reported failure",
                "analysis_id": analysis_id
            }
            
    except Exception as e:
        logger.error("Failed to stop analysis via orchestrator",
                    analysis_id=analysis_id,
                    error=str(e))
        
        # Try to update status anyway
        update_query = "UPDATE analyses SET status = 'stopped', updated_at = NOW() WHERE id = :id"
        await database.execute(update_query, {"id": analysis_id})
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop analysis via orchestrator: {str(e)}"
        )


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete an analysis (only if not running)"""
    
    # Get analysis
    analysis_query = "SELECT status FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    if analysis["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a running analysis. Stop it first."
        )
    
    # Delete analysis (cascade will delete runs)
    delete_query = "DELETE FROM analyses WHERE id = :id"
    await database.execute(delete_query, {"id": analysis_id})
    
    return None


@router.get("/{analysis_id}/runs", response_model=List[AnalysisRunResponse])
async def get_analysis_runs(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get all runs for an analysis"""
    
    query = """
        SELECT * FROM analysis_runs
        WHERE analysis_id = :analysis_id
        ORDER BY start_time DESC
    """
    
    results = await database.fetch_all(query, {"analysis_id": analysis_id})
    return [AnalysisRunResponse(**row) for row in results]
