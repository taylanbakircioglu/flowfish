"""
Analysis management API endpoints
Sprint 5-6: Analysis Wizard & Communication Discovery
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import structlog
import json
import asyncio

from database.postgresql import database
from utils.jwt_utils import get_current_user, require_permissions
from grpc_clients.analysis_orchestrator_client import analysis_orchestrator_client
from services.activity_service import activity_service, ActivityService

logger = structlog.get_logger()
router = APIRouter()


def check_analysis_permission(current_user: dict, required_action: str) -> bool:
    """
    Check if user has permission for analysis actions.
    
    Permission mapping:
    - analysis.create: Create new analyses
    - analysis.start: Start/execute analyses  
    - analysis.stop: Stop running analyses
    - analysis.delete: Delete analyses
    - analysis.view: View analyses (read-only)
    
    Super Admin, Admin, Platform Admin bypass all checks.
    Viewer role should only have analysis.view permission.
    """
    user_roles = current_user.get("roles", [])
    
    # Super Admin, Admin, Platform Admin bypass all permission checks
    admin_roles = ["super admin", "admin", "platform admin"]
    if any(r.lower() in admin_roles for r in user_roles):
        return True
    
    # For non-admin users, check against role-based permissions
    # Viewer role should NOT have start/stop/create/delete permissions
    viewer_roles = ["viewer", "read-only", "readonly"]
    is_viewer = any(r.lower() in viewer_roles for r in user_roles)
    
    # Define what viewers CAN do (only view)
    viewer_allowed_actions = ["view"]
    
    if is_viewer and required_action not in viewer_allowed_actions:
        return False
    
    # For other roles (Operator, Analyst, etc.), allow the action
    # In production, this should check the permissions table
    return True


def require_analysis_permission(required_action: str):
    """Decorator to require specific analysis permission"""
    def check(current_user: dict):
        if not check_analysis_permission(current_user, required_action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required permission: analysis.{required_action}"
            )
        return current_user
    return check


def get_client_ip(request: Request) -> str:
    """Extract client IP from request headers"""
    # Priority: X-Client-IP (from frontend) > X-Forwarded-For > X-Real-IP > client.host
    if request.headers.get("X-Client-IP"):
        return request.headers.get("X-Client-IP")
    elif request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP")
    elif request.client:
        return request.client.host
    return "0.0.0.0"

# Request/Response Models
class ScopeConfig(BaseModel):
    """
    Analysis scope configuration
    
    Supports both single-cluster and multi-cluster analysis:
    - cluster_id: Primary cluster (required)
    - cluster_ids: List of all cluster IDs for multi-cluster (optional)
    """
    cluster_id: int = Field(..., description="Primary cluster ID")
    cluster_ids: Optional[List[int]] = Field(None, description="List of cluster IDs for multi-cluster analysis")
    scope_type: str = Field(..., description="cluster, namespace, deployment, pod, label")
    namespaces: Optional[List[str]] = None
    deployments: Optional[List[str]] = None
    pods: Optional[List[str]] = None
    labels: Optional[dict] = None
    
    # Per-cluster scope configuration for multi-cluster
    # Format: { "cluster_id": { "namespaces": [...], "deployments": [...] } }
    per_cluster_scope: Optional[dict] = Field(None, description="Per-cluster scope configuration")
    
    @staticmethod
    def _strip_cluster_suffix(values: Optional[List[str]]) -> Optional[List[str]]:
        """Strip @clusterId suffix from values (e.g., 'namespace@4' -> 'namespace')"""
        if not values:
            return values
        cleaned = []
        for val in values:
            if '@' in val:
                # Use lastIndexOf in case value itself contains @
                clean_val = val[:val.rfind('@')]
                cleaned.append(clean_val)
            else:
                cleaned.append(val)
        # Remove duplicates while preserving order
        return list(dict.fromkeys(cleaned))
    
    def __init__(self, **data):
        # Clean values before validation
        if 'namespaces' in data and data['namespaces']:
            data['namespaces'] = self._strip_cluster_suffix(data['namespaces'])
        if 'deployments' in data and data['deployments']:
            data['deployments'] = self._strip_cluster_suffix(data['deployments'])
        if 'pods' in data and data['pods']:
            data['pods'] = self._strip_cluster_suffix(data['pods'])
        # Also clean per_cluster_scope values
        if 'per_cluster_scope' in data and data['per_cluster_scope']:
            for cluster_id, scope in data['per_cluster_scope'].items():
                if isinstance(scope, dict):
                    if 'namespaces' in scope:
                        scope['namespaces'] = self._strip_cluster_suffix(scope['namespaces'])
                    if 'deployments' in scope:
                        scope['deployments'] = self._strip_cluster_suffix(scope['deployments'])
                    if 'pods' in scope:
                        scope['pods'] = self._strip_cluster_suffix(scope['pods'])
        super().__init__(**data)

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
    """Analysis time and profiling configuration with data sizing support"""
    mode: str = Field(..., description="continuous, timed, time_range, periodic, baseline, recurring")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(None, ge=60, le=604800, description="Fixed duration in seconds (min 60s, max 7 days)")
    periodic_interval: Optional[int] = Field(None, ge=60, le=86400, description="Interval in seconds for periodic mode (min 60s, max 24h)")
    baseline_name: Optional[str] = Field(None, description="Baseline profile name")
    
    # Recurring schedule fields (stored here for reference; authoritative values are in analyses columns)
    schedule_expression: Optional[str] = Field(None, max_length=100, description="Cron expression for recurring mode")
    schedule_duration_seconds: Optional[int] = Field(None, ge=60, le=86400, description="Per-run duration for recurring mode")
    
    # Data sizing configuration
    data_retention_policy: Optional[str] = Field(
        'unlimited', 
        description="unlimited, stop_on_limit, rolling_window"
    )
    max_data_size_mb: Optional[int] = Field(
        None,
        ge=10,  # Minimum 10 MB
        le=10240,  # Maximum 10 GB
        description="Maximum data size in MB (10 MB - 10 GB, required for stop_on_limit and rolling_window)"
    )
    
    @classmethod
    def validate_retention_config(cls, values):
        """Validate that max_data_size_mb is provided when retention policy requires it"""
        policy = values.get('data_retention_policy', 'unlimited')
        max_size = values.get('max_data_size_mb')
        
        # Validate policy value
        valid_policies = ['unlimited', 'stop_on_limit', 'rolling_window']
        if policy and policy not in valid_policies:
            # Don't raise error, just default to unlimited for backward compatibility
            values['data_retention_policy'] = 'unlimited'
            return values
        
        # If policy requires size limit, ensure max_data_size_mb is provided
        if policy in ['stop_on_limit', 'rolling_window'] and not max_size:
            # Default to 500 MB if not provided
            values['max_data_size_mb'] = 500
        
        return values
    
    def __init__(self, **data):
        # Apply validation before pydantic validation
        data = self.validate_retention_config(data)
        super().__init__(**data)

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
    change_detection_enabled: bool = Field(
        default=True,
        description="Enable change detection for this analysis. When enabled, infrastructure changes are tracked."
    )
    change_detection_strategy: str = Field(
        default="baseline",
        description="Detection strategy: 'baseline' (compare against initial state), 'rolling_window' (compare recent periods), 'run_comparison' (compare between runs)"
    )
    change_detection_types: List[str] = Field(
        default=["all"],
        description="Change types to track: ['all'] or specific types like ['replica_changed', 'connection_added', 'port_changed']"
    )

class AnalysisResponse(BaseModel):
    """Analysis response model with multi-cluster support"""
    id: int
    name: str = "unnamed"
    description: Optional[str] = None
    cluster_id: int  # Primary cluster
    cluster_name: Optional[str] = None  # Primary cluster name
    cluster_ids: Optional[List[int]] = None  # All clusters for multi-cluster
    is_multi_cluster: bool = False
    status: str = "unknown"
    scope_type: str = "cluster"
    scope_config: dict = {}
    gadget_config: dict = {}
    time_config: dict = {}
    output_config: dict = {}
    change_detection_enabled: bool = True
    change_detection_strategy: str = "baseline"
    change_detection_types: List[str] = ["all"]
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    created_by: int
    is_scheduled: bool = False
    schedule_expression: Optional[str] = None
    schedule_duration_seconds: Optional[int] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    schedule_run_count: int = 0
    max_scheduled_runs: Optional[int] = None

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
    analysis: AnalysisCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new analysis configuration via wizard
    
    **Sprint 5-6 Feature - Multi-Cluster Support**
    
    This endpoint creates a complete analysis configuration after the user
    completes the 4-step wizard:
    1. Scope Selection (supports single or multiple clusters)
    2. Gadget Modules
    3. Time & Profile
    4. Output & Integration
    
    **Multi-Cluster Support:**
    - Set cluster_ids in scope to analyze multiple clusters simultaneously
    - Each cluster can have its own scope configuration via per_cluster_scope
    
    **Permissions Required:** analysis.create (Viewer role cannot create)
    """
    # Check permission - Viewer role cannot create analyses
    if not check_analysis_permission(current_user, "create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. You do not have permission to create analyses. Required role: Admin, Operator, or Analyst."
        )
    
    # Determine if this is a multi-cluster analysis
    cluster_ids = analysis.scope.cluster_ids or [analysis.scope.cluster_id]
    is_multi_cluster = len(cluster_ids) > 1
    
    # Validate all clusters exist
    for cid in cluster_ids:
        cluster_query = "SELECT id, name FROM clusters WHERE id = :cluster_id AND status = 'active'"
        cluster = await database.fetch_one(cluster_query, {"cluster_id": cid})
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster with id {cid} not found or inactive"
            )
    
    logger.info("Creating analysis",
               name=analysis.name,
               is_multi_cluster=is_multi_cluster,
               cluster_ids=cluster_ids)
    
    # Insert analysis with multi-cluster support
    # NOTE: namespaces column is populated separately to maintain backward compatibility
    # if migration hasn't run yet
    insert_query = """
        INSERT INTO analyses (
            name, description, cluster_id, cluster_ids, is_multi_cluster,
            status, scope_type, scope_config,
            gadget_config, time_config, output_config, 
            change_detection_enabled, change_detection_strategy, change_detection_types,
            created_by
        ) VALUES (
            :name, :description, :cluster_id, :cluster_ids, :is_multi_cluster,
            'draft', :scope_type, :scope_config,
            :gadget_config, :time_config, :output_config,
            :change_detection_enabled, :change_detection_strategy, :change_detection_types,
            :created_by
        ) RETURNING *
    """

    values = {
        "name": analysis.name,
        "description": analysis.description,
        "cluster_id": analysis.scope.cluster_id,  # Primary cluster
        "cluster_ids": json.dumps(cluster_ids),  # All clusters as JSON array
        "is_multi_cluster": is_multi_cluster,
        "scope_type": analysis.scope.scope_type,
        "scope_config": json.dumps(analysis.scope.dict()),
        "gadget_config": json.dumps(analysis.gadgets.dict()),
        "time_config": json.dumps(analysis.time_config.dict(), default=str),
        "output_config": json.dumps(analysis.output.dict()),
        "change_detection_enabled": analysis.change_detection_enabled,
        "change_detection_strategy": analysis.change_detection_strategy,
        "change_detection_types": json.dumps(analysis.change_detection_types),
        "created_by": current_user.get('user_id', 1)
    }
    
    result = await database.fetch_one(insert_query, values)
    analysis_id = result['id']
    
    # Extract namespaces from scope config for change detection filtering
    # This is done as a separate UPDATE to maintain backward compatibility
    # if the namespaces column doesn't exist yet (migration not run)
    namespaces_list = None
    if analysis.scope.namespaces:
        namespaces_list = analysis.scope.namespaces
    elif analysis.scope.per_cluster_scope:
        # Collect namespaces from all clusters in multi-cluster setup
        all_namespaces = set()
        for cluster_scope in analysis.scope.per_cluster_scope.values():
            if isinstance(cluster_scope, dict) and cluster_scope.get("namespaces"):
                all_namespaces.update(cluster_scope["namespaces"])
        if all_namespaces:
            namespaces_list = list(all_namespaces)
    
    # Try to populate namespaces column (fails gracefully if column doesn't exist)
    if namespaces_list:
        try:
            update_ns_query = """
                UPDATE analyses SET namespaces = :namespaces WHERE id = :id
            """
            await database.execute(update_ns_query, {
                "id": analysis_id,
                "namespaces": json.dumps(namespaces_list)
            })
            logger.debug("Namespaces column updated", analysis_id=analysis_id, namespaces=namespaces_list)
        except Exception as e:
            # Column might not exist if migration hasn't run - this is OK
            # Change detection will fall back to scope_config
            logger.debug("Could not update namespaces column (migration may not have run)", 
                        analysis_id=analysis_id, error=str(e))
    
    # Get cluster name for response
    cluster_query = "SELECT name FROM clusters WHERE id = :cluster_id"
    cluster = await database.fetch_one(cluster_query, {"cluster_id": analysis.scope.cluster_id})
    cluster_name = cluster["name"] if cluster else None
    
    # Parse cluster_ids and change_detection_types back from JSON for response
    response_data = dict(result)
    response_data['cluster_name'] = cluster_name
    if response_data.get('cluster_ids'):
        response_data['cluster_ids'] = json.loads(response_data['cluster_ids']) if isinstance(response_data['cluster_ids'], str) else response_data['cluster_ids']
    if response_data.get('change_detection_types'):
        response_data['change_detection_types'] = json.loads(response_data['change_detection_types']) if isinstance(response_data['change_detection_types'], str) else response_data['change_detection_types']
    
    # Log activity
    await activity_service.log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username', 'system'),
        action=ActivityService.ACTION_CREATE,
        resource_type=ActivityService.RESOURCE_ANALYSIS,
        resource_id=str(result['id']),
        resource_name=analysis.name,
        ip_address=get_client_ip(request),
        details={
            "cluster_id": analysis.scope.cluster_id,
            "cluster_name": cluster_name,
            "is_multi_cluster": is_multi_cluster,
            "scope_type": analysis.scope.scope_type
        }
    )
    
    return AnalysisResponse(**response_data)


@router.get("", response_model=List[AnalysisResponse])
async def get_analyses(
    cluster_id: Optional[int] = None,
    status: Optional[str] = None,
    include_multi_cluster: bool = True
):
    """
    Get all analyses with optional filters
    
    **Filters:**
    - cluster_id: Filter by cluster (also matches multi-cluster analyses that include this cluster)
    - status: Filter by status (draft, running, stopped, completed, failed)
    - include_multi_cluster: Include analyses where cluster_id appears in cluster_ids array
    """
    
    # Join with clusters to get cluster_name
    query = """
        SELECT a.*, c.name as cluster_name 
        FROM analyses a
        LEFT JOIN clusters c ON a.cluster_id = c.id
        WHERE 1=1
    """
    params = {}
    
    if cluster_id:
        if include_multi_cluster:
            # Match both primary cluster and multi-cluster analyses containing this cluster
            query += """ AND (
                a.cluster_id = :cluster_id 
                OR (a.is_multi_cluster = true AND a.cluster_ids::jsonb @> :cluster_id_json)
            )"""
            params["cluster_id"] = cluster_id
            params["cluster_id_json"] = json.dumps([cluster_id])
        else:
            query += " AND a.cluster_id = :cluster_id"
            params["cluster_id"] = cluster_id
    
    if status:
        query += " AND a.status = :status"
        params["status"] = status
    
    query += " ORDER BY a.created_at DESC"
    
    results = await database.fetch_all(query, params)
    
    # Parse cluster_ids and change_detection_types from JSON for each result
    response_list = []
    for row in results:
        row_dict = dict(row)
        if row_dict.get('cluster_ids'):
            row_dict['cluster_ids'] = json.loads(row_dict['cluster_ids']) if isinstance(row_dict['cluster_ids'], str) else row_dict['cluster_ids']
        if row_dict.get('change_detection_types'):
            row_dict['change_detection_types'] = json.loads(row_dict['change_detection_types']) if isinstance(row_dict['change_detection_types'], str) else row_dict['change_detection_types']
        response_list.append(AnalysisResponse(**row_dict))

    return response_list


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get single analysis by ID with multi-cluster support"""
    
    # Join with clusters to get cluster_name
    query = """
        SELECT a.*, c.name as cluster_name 
        FROM analyses a
        LEFT JOIN clusters c ON a.cluster_id = c.id
        WHERE a.id = :id
    """
    result = await database.fetch_one(query, {"id": analysis_id})
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    # Parse cluster_ids and change_detection_types from JSON for response
    row_dict = dict(result)
    if row_dict.get('cluster_ids'):
        row_dict['cluster_ids'] = json.loads(row_dict['cluster_ids']) if isinstance(row_dict['cluster_ids'], str) else row_dict['cluster_ids']
    if row_dict.get('change_detection_types'):
        row_dict['change_detection_types'] = json.loads(row_dict['change_detection_types']) if isinstance(row_dict['change_detection_types'], str) else row_dict['change_detection_types']

    return AnalysisResponse(**row_dict)


@router.post("/{analysis_id}/start", response_model=AnalysisRunResponse)
async def start_analysis(
    analysis_id: int,
    request: Request,
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
    
    **Permissions Required:** analysis.start (Viewer role cannot start)
    """
    # Check permission - Viewer role cannot start analyses
    if not check_analysis_permission(current_user, "start"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. You do not have permission to start analyses. Required role: Admin, Operator, or Analyst."
        )
    
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
    
    # Get next run_number for this analysis
    run_number_query = """
        SELECT COALESCE(MAX(run_number), 0) + 1 as next_run_number
        FROM analysis_runs WHERE analysis_id = :analysis_id
    """
    run_number_result = await database.fetch_one(run_number_query, {"analysis_id": analysis_id})
    next_run_number = run_number_result["next_run_number"] if run_number_result else 1
    
    # Create analysis run
    run_query = """
        INSERT INTO analysis_runs (
            analysis_id, run_number, status, start_time, events_collected,
            workloads_discovered, communications_discovered, anomalies_detected, changes_detected
        ) VALUES (
            :analysis_id, :run_number, 'running', NOW(), 0, 0, 0, 0, 0
        ) RETURNING *
    """
    
    run_result = await database.fetch_one(run_query, {"analysis_id": analysis_id, "run_number": next_run_number})
    
    # Update analysis status to running and reset started_at for auto-stop timing
    # started_at must be updated on EVERY Start (not just first) for correct auto-stop behavior on restarts
    update_query = "UPDATE analyses SET status = 'running', started_at = NOW(), updated_at = NOW() WHERE id = :id"
    await database.execute(update_query, {"id": analysis_id})
    
    # Start analysis via Analysis Orchestrator (microservice)
    try:
        logger.info("Calling Analysis Orchestrator to start analysis",
                   analysis_id=analysis_id)
        
        orchestrator_response = await analysis_orchestrator_client.start_analysis(analysis_id)
        
        logger.info("Analysis Orchestrator started analysis successfully",
                   analysis_id=analysis_id,
                   tasks=len(orchestrator_response.get("task_assignments", [])))
        
        # Log activity
        await activity_service.log_activity(
            user_id=current_user.get('user_id'),
            username=current_user.get('username', 'system'),
            action=ActivityService.ACTION_START,
            resource_type=ActivityService.RESOURCE_ANALYSIS,
            resource_id=str(analysis_id),
            resource_name=analysis.get("name", f"Analysis {analysis_id}"),
            ip_address=get_client_ip(request),
            details={
                "run_id": run_result['id'],
                "run_number": next_run_number
            }
        )
        
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
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Stop a running analysis
    
    **Sprint 5-6 Feature**
    
    Also fetches final statistics from ClickHouse and updates analysis_runs.
    
    **Permissions Required:** analysis.stop (Viewer role cannot stop)
    """
    # Check permission - Viewer role cannot stop analyses
    if not check_analysis_permission(current_user, "stop"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. You do not have permission to stop analyses. Required role: Admin, Operator, or Analyst."
        )
    
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
    
    cluster_id = analysis["cluster_id"]
    
    # SAFETY FIRST: Stop the orchestrator BEFORE updating any status
    # This ensures we don't show "stopped" while analysis is still running
    
    # Step 1: Call orchestrator to ACTUALLY stop the analysis
    # This is the critical operation - must succeed before status update
    orchestrator_success = False
    orchestrator_error = None
    try:
        logger.info("Calling Analysis Orchestrator to stop analysis", analysis_id=analysis_id)
        orchestrator_success = await analysis_orchestrator_client.stop_analysis(analysis_id)
        
        if not orchestrator_success:
            logger.warning("Orchestrator returned False for stop_analysis, will verify status", analysis_id=analysis_id)
            
            # Verify by checking actual status from orchestrator
            await asyncio.sleep(0.5)  # Brief wait for state to propagate
            
            status_check = await analysis_orchestrator_client.get_analysis_status(analysis_id)
            if status_check is None or status_check.get("status") in ["stopped", "completed", "error"]:
                # Analysis is actually stopped (not found = not running = stopped)
                logger.info("Status verification confirms analysis is stopped", analysis_id=analysis_id)
                orchestrator_success = True
            else:
                logger.warning("Status verification shows analysis still running", 
                              analysis_id=analysis_id, status=status_check.get("status"))
    except Exception as e:
        orchestrator_error = str(e)
        logger.error("Failed to stop analysis via orchestrator", analysis_id=analysis_id, error=orchestrator_error)
        
        # Even on exception, verify the actual status
        try:
            status_check = await analysis_orchestrator_client.get_analysis_status(analysis_id)
            if status_check is None or status_check.get("status") in ["stopped", "completed", "error"]:
                logger.info("Despite exception, status verification confirms analysis is stopped", analysis_id=analysis_id)
                orchestrator_success = True
                orchestrator_error = None
        except Exception:
            pass  # Keep original error
    
    # Step 2: Only update status to 'stopped' AFTER orchestrator confirms stop
    # Even if orchestrator had issues, we proceed (but log warning) because:
    # - The stop command was sent
    # - Better to update status than leave in inconsistent state
    # - User can check orchestrator logs if issues persist
    
    stop_run_query = """
        UPDATE analysis_runs 
        SET status = 'stopped', end_time = NOW()
        WHERE analysis_id = :analysis_id AND status = 'running'
    """
    await database.execute(stop_run_query, {"analysis_id": analysis_id})
    
    update_query = "UPDATE analyses SET status = 'stopped', updated_at = NOW() WHERE id = :id"
    await database.execute(update_query, {"id": analysis_id})
    
    logger.info("Analysis status updated to stopped in database", 
                analysis_id=analysis_id, 
                orchestrator_success=orchestrator_success)
    
    # Step 4: Get previous runs' total events (to calculate this run's events only)
    previous_events_total = 0
    previous_comms_total = 0
    try:
        prev_runs_query = """
            SELECT COALESCE(SUM(events_collected), 0) as prev_events,
                   COALESCE(SUM(communications_discovered), 0) as prev_comms
            FROM analysis_runs 
            WHERE analysis_id = :analysis_id 
              AND status IN ('stopped', 'completed', 'failed')
              AND id != (SELECT id FROM analysis_runs WHERE analysis_id = :analysis_id ORDER BY start_time DESC LIMIT 1)
        """
        prev_result = await database.fetch_one(prev_runs_query, {"analysis_id": analysis_id})
        if prev_result:
            previous_events_total = int(prev_result["prev_events"] or 0)
            previous_comms_total = int(prev_result["prev_comms"] or 0)
        logger.debug(f"Previous runs totals: events={previous_events_total}, comms={previous_comms_total}")
    except Exception as e:
        logger.warning(f"Failed to get previous runs totals: {e}")
    
    # Step 5: Fetch statistics from ClickHouse (can be slow, but analysis is already stopped)
    events_collected = 0
    communications_discovered = 0
    total_events_clickhouse = 0
    total_comms_clickhouse = 0
    
    try:
        from repositories.event_repository import get_event_repository
        event_repo = get_event_repository(use_microservice=True)
        
        # Get event counts - use simple count query for speed
        event_counts = await event_repo.get_event_counts_by_type(
            cluster_id=cluster_id,
            analysis_id=analysis_id
        )
        total_events_clickhouse = int(sum(event_counts.values())) if event_counts else 0
        
        # Calculate this run's events only (total - previous runs)
        events_collected = max(0, total_events_clickhouse - previous_events_total)
        
        # Get unique communications count from network_flows
        try:
            from config import get_clickhouse_config
            from repositories.event_repository import ClickHouseEventRepository
            
            ch_config = get_clickhouse_config()
            direct_repo = ClickHouseEventRepository(
                host=ch_config.get('host', 'clickhouse'),
                port=ch_config.get('port', 8123),
                database=ch_config.get('database', 'flowfish'),
                user=ch_config.get('user', 'default'),
                password=ch_config.get('password', ''),
            )
            
            # Count unique source->destination communication pairs
            # Support multi-cluster format: analysis_id can be '{id}' or '{id}-{cluster_id}'
            comm_query = f"""
                SELECT count() as cnt FROM (
                    SELECT DISTINCT 
                        source_namespace, source_pod, 
                        dest_namespace, dest_pod, dest_port, protocol
                    FROM network_flows 
                    WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'
                )
            """
            comm_result = await direct_repo._execute_query(comm_query)
            if comm_result and len(comm_result) > 0:
                total_comms_clickhouse = int(comm_result[0].get('cnt', 0))
                # Calculate this run's communications only (total - previous runs)
                communications_discovered = max(0, total_comms_clickhouse - previous_comms_total)
        except Exception as comm_err:
            logger.warning(f"Failed to get communications count: {comm_err}")
        
        logger.info("Fetched analysis statistics from ClickHouse",
                   analysis_id=analysis_id,
                   total_events_clickhouse=total_events_clickhouse,
                   total_comms_clickhouse=total_comms_clickhouse,
                   previous_events_total=previous_events_total,
                   previous_comms_total=previous_comms_total,
                   events_collected=events_collected,
                   communications_discovered=communications_discovered)
                   
    except Exception as e:
        logger.warning(f"Failed to fetch statistics from ClickHouse: {e}")
    
    # Step 6: Update run with final statistics
    update_stats_query = """
        UPDATE analysis_runs 
        SET events_collected = :events_collected,
            communications_discovered = :communications_discovered
        WHERE analysis_id = :analysis_id AND status = 'stopped'
        AND end_time = (SELECT MAX(end_time) FROM analysis_runs WHERE analysis_id = :analysis_id)
    """
    await database.execute(update_stats_query, {
        "analysis_id": analysis_id,
        "events_collected": events_collected,
        "communications_discovered": communications_discovered
    })
    
    # Log activity
    await activity_service.log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username', 'system'),
        action=ActivityService.ACTION_STOP,
        resource_type=ActivityService.RESOURCE_ANALYSIS,
        resource_id=str(analysis_id),
        resource_name=analysis.get("name", f"Analysis {analysis_id}"),
        ip_address=get_client_ip(request),
        details={
            "events_collected": events_collected,
            "communications_discovered": communications_discovered,
            "orchestrator_success": orchestrator_success
        }
    )
    
    if orchestrator_success:
        logger.info("Analysis stopped successfully via orchestrator",
                   analysis_id=analysis_id,
                   events_collected=events_collected,
                   communications_discovered=communications_discovered)
        
        return {
            "message": "Analysis stopped successfully", 
            "analysis_id": analysis_id,
            "events_collected": events_collected,
            "communications_discovered": communications_discovered,
            "orchestrator_status": "success"
        }
    else:
        logger.warning("Analysis stopped but orchestrator reported issues", 
                      analysis_id=analysis_id,
                      orchestrator_error=orchestrator_error)
        
        return {
            "message": "Analysis stopped (orchestrator reported issues - please verify no data is being collected)",
            "analysis_id": analysis_id,
            "events_collected": events_collected,
            "communications_discovered": communications_discovered,
            "orchestrator_status": "warning",
            "orchestrator_error": orchestrator_error
        }


class DeleteAnalysisResponse(BaseModel):
    """Response model for analysis deletion"""
    analysis_id: int
    deleted: bool
    postgresql: dict = {}
    neo4j: dict = {}
    clickhouse: dict = {}
    redis: dict = {}
    rabbitmq: dict = {}
    duration_ms: int = 0
    message: str = ""


@router.delete("/{analysis_id}", response_model=DeleteAnalysisResponse)
async def delete_analysis(
    analysis_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an analysis and ALL associated data
    
    This will delete:
    - PostgreSQL: analyses, analysis_runs records
    - Neo4j: All nodes and edges with this analysis_id (batch delete)
    - ClickHouse: All events from all tables with this analysis_id (with polling)
    - Redis: All cached data with this analysis_id
    
    Returns detailed summary of what was deleted.
    
    **Permissions Required:** analysis.delete (Viewer role cannot delete)
    """
    # Check permission - Viewer role cannot delete analyses
    if not check_analysis_permission(current_user, "delete"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. You do not have permission to delete analyses. Required role: Admin or Operator."
        )
    
    import time
    start_time = time.time()
    
    # Get analysis with cluster_id for comprehensive deletion
    analysis_query = "SELECT status, name, cluster_id, is_scheduled FROM analyses WHERE id = :id"
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
    
    # Remove schedule from orchestrator before deleting (best-effort)
    if analysis.get("is_scheduled"):
        try:
            await analysis_orchestrator_client.unschedule_analysis(analysis_id)
        except Exception as e:
            logger.warning("Failed to unschedule before delete (scheduler will self-heal)",
                          analysis_id=analysis_id, error=str(e))
    
    analysis_name = analysis["name"]
    cluster_id = analysis["cluster_id"]
    neo4j_result = {}
    clickhouse_result = {}
    redis_result = {}
    
    # STEP 0: Mark analysis as deleted in Redis cache
    # This prevents timeseries-writer and graph-writer from creating orphan data
    # while we're deleting
    try:
        from database.redis import redis_client
        
        deleted_key = f"flowfish:deleted_analysis:{analysis_id}"
        await redis_client.setex(deleted_key, 86400, "1")  # 24 hour TTL
        logger.info("Marked analysis as deleted in Redis cache",
                   analysis_id=analysis_id,
                   key=deleted_key)
        
        # Wait briefly for in-flight messages to be filtered out by writers
        await asyncio.sleep(0.5)  # 500ms should be enough for batch flush
        
    except Exception as e:
        logger.warning("Failed to mark analysis as deleted in Redis (continuing)",
                      analysis_id=analysis_id,
                      error=str(e))
    
    # Delete from Neo4j (graph data) - batch processing with cluster_id fallback
    try:
        from database.neo4j import neo4j_service
        neo4j_result = neo4j_service.delete_analysis_data(
            analysis_id, 
            cluster_id=cluster_id,
            batch_size=5000
        )
        # Remove duplicate keys from neo4j_result before logging
        log_result = {k: v for k, v in neo4j_result.items() if k not in ('analysis_id', 'cluster_id')}
        logger.info("Deleted Neo4j data", 
                   analysis_id=analysis_id,
                   cluster_id=cluster_id,
                   analysis_name=analysis_name,
                   **log_result)
    except Exception as e:
        logger.warning("Failed to delete Neo4j data (continuing)", 
                      analysis_id=analysis_id, 
                      error=str(e))
        neo4j_result = {"error": str(e)}
    
    # Delete from ClickHouse (time-series events) - with polling
    # Try microservice first, then fallback to direct ClickHouse access
    try:
        from repositories.event_repository import get_event_repository, ClickHouseEventRepository
        from config import get_clickhouse_config
        
        # First try via microservice
        event_repo = get_event_repository(use_microservice=True)
        clickhouse_result = await event_repo.delete_analysis_data(
            analysis_id, 
            wait_for_completion=True,
            timeout_seconds=30
        )
        
        # Check if microservice deletion failed (returned error in result)
        if clickhouse_result.get("error") or clickhouse_result.get("total_deleted", 0) == 0:
            logger.warning("Microservice deletion failed or returned 0, trying direct ClickHouse access",
                          analysis_id=analysis_id,
                          microservice_result=clickhouse_result)
            
            # Fallback to direct ClickHouse access
            ch_config = get_clickhouse_config()
            direct_repo = ClickHouseEventRepository(
                host=ch_config.get('host', 'clickhouse'),
                port=ch_config.get('port', 8123),
                database=ch_config.get('database', 'flowfish'),
                user=ch_config.get('user', 'default'),
                password=ch_config.get('password', ''),
            )
            clickhouse_result = await direct_repo.delete_analysis_data(
                analysis_id,
                wait_for_completion=True,
                timeout_seconds=60
            )
        
        logger.info("ClickHouse deletion completed", 
                   analysis_id=analysis_id,
                   analysis_name=analysis_name,
                   **clickhouse_result)
    except Exception as e:
        logger.warning("Failed to delete ClickHouse data (continuing)", 
                      analysis_id=analysis_id, 
                      error=str(e))
        clickhouse_result = {"error": str(e)}
    
    # Delete from Redis (cached data)
    try:
        from database.redis import redis_client
        
        redis_deleted = 0
        
        # Delete analysis-specific cache keys
        # Pattern 1: analysis:status:{analysis_id}
        status_key = f"analysis:status:{analysis_id}"
        deleted = await redis_client.delete(status_key)
        redis_deleted += deleted if deleted else 0
        
        # Pattern 2: Any key containing the analysis_id
        # Use scan to find keys matching pattern
        analysis_patterns = [
            f"*analysis*{analysis_id}*",
            f"*:analysis:{analysis_id}*",
            f"analysis:{analysis_id}:*",
        ]
        
        for pattern in analysis_patterns:
            try:
                matching_keys = await redis_client.keys(pattern)
                if matching_keys:
                    for key in matching_keys:
                        await redis_client.delete(key)
                        redis_deleted += 1
            except Exception as pattern_error:
                logger.debug(f"Pattern {pattern} search failed: {pattern_error}")
        
        redis_result = {"deleted_keys": redis_deleted}
        logger.info("Redis cache cleared", 
                   analysis_id=analysis_id,
                   deleted_keys=redis_deleted)
    except Exception as e:
        logger.warning("Failed to clear Redis cache (continuing)", 
                      analysis_id=analysis_id, 
                      error=str(e))
        redis_result = {"error": str(e)}
    
    # RabbitMQ note - messages are transient and consumed by workers
    # We cannot selectively delete messages by analysis_id
    # Any pending messages for this analysis will be processed but data 
    # will reference a non-existent analysis (which is fine)
    rabbitmq_result = {
        "note": "RabbitMQ messages are transient and consumed by workers within seconds. "
                "Any pending messages for this analysis will be automatically discarded.",
        "status": "not_applicable"
    }
    
    # Count analysis_runs before deletion (for PostgreSQL info)
    runs_count_query = "SELECT COUNT(*) as cnt FROM analysis_runs WHERE analysis_id = :id"
    runs_count = await database.fetch_one(runs_count_query, {"id": analysis_id})
    runs_deleted = runs_count["cnt"] if runs_count else 0
    
    # NOTE: change_workflow table removed from PostgreSQL
    # Change events are now stored only in ClickHouse (deleted above)
    
    # Clean up dependent tables before deleting the analysis record.
    # blast_radius_assessments has a FK without ON DELETE CASCADE (fixed in migration,
    # but explicit cleanup ensures safety even before migration runs).
    # analysis_event_types has no FK at all, so orphan rows would accumulate.
    blast_radius_deleted = 0
    event_types_deleted = 0
    
    try:
        br_count_query = "SELECT COUNT(*) as cnt FROM blast_radius_assessments WHERE analysis_id = :id"
        br_count = await database.fetch_one(br_count_query, {"id": analysis_id})
        blast_radius_deleted = br_count["cnt"] if br_count else 0
        if blast_radius_deleted > 0:
            await database.execute(
                "DELETE FROM blast_radius_assessments WHERE analysis_id = :id",
                {"id": analysis_id}
            )
            logger.info("Deleted blast_radius_assessments",
                       analysis_id=analysis_id, count=blast_radius_deleted)
    except Exception as e:
        logger.warning("Failed to clean blast_radius_assessments",
                      analysis_id=analysis_id, error=str(e))
    
    try:
        aet_count_query = "SELECT COUNT(*) as cnt FROM analysis_event_types WHERE analysis_id = :id"
        aet_count = await database.fetch_one(aet_count_query, {"id": analysis_id})
        event_types_deleted = aet_count["cnt"] if aet_count else 0
        if event_types_deleted > 0:
            await database.execute(
                "DELETE FROM analysis_event_types WHERE analysis_id = :id",
                {"id": analysis_id}
            )
    except Exception as e:
        logger.warning("Failed to clean analysis_event_types",
                      analysis_id=analysis_id, error=str(e))
    
    # Delete from PostgreSQL (analysis record - cascade deletes analysis_runs)
    try:
        delete_query = "DELETE FROM analyses WHERE id = :id"
        await database.execute(delete_query, {"id": analysis_id})
    except Exception as e:
        error_msg = str(e)
        if "ForeignKeyViolationError" in error_msg or "IntegrityError" in error_msg:
            logger.error("FK violation deleting analysis - dependent rows remain",
                        analysis_id=analysis_id, error=error_msg)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete analysis {analysis_id}: dependent records still exist in the database. "
                    "This may happen if a migration has not been applied. "
                    "Please contact your administrator."
                )
            )
        raise
    
    postgresql_result = {
        "deleted_analyses": 1,
        "deleted_runs": runs_deleted,
        "deleted_blast_radius_assessments": blast_radius_deleted,
        "deleted_event_types": event_types_deleted
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    total_deleted = (
        neo4j_result.get("deleted_edges", 0) + 
        neo4j_result.get("deleted_nodes", 0) + 
        clickhouse_result.get("total_deleted", 0) +
        redis_result.get("deleted_keys", 0) +
        postgresql_result.get("deleted_analyses", 0) +
        postgresql_result.get("deleted_runs", 0)
    )
    
    # Check if Neo4j had 0 deletes but ClickHouse had data (analysis_id overwrite issue)
    neo4j_deleted = neo4j_result.get("deleted_edges", 0) + neo4j_result.get("deleted_nodes", 0)
    clickhouse_deleted = clickhouse_result.get("total_deleted", 0)
    
    if neo4j_deleted == 0 and clickhouse_deleted > 0:
        neo4j_result["warning"] = (
            "Neo4j graph data may have been claimed by a later analysis. "
            "This happens when multiple analyses run on the same cluster/pods. "
            "Orphaned nodes will be cleaned up automatically."
        )
        logger.warning("Neo4j showed 0 deletes but ClickHouse had data - analysis_id may have been overwritten",
                      analysis_id=analysis_id,
                      clickhouse_deleted=clickhouse_deleted)
    
    # STEP 6: Auto-cleanup orphaned data (data for analyses that no longer exist in PostgreSQL)
    orphan_result = {"cleaned": 0}
    try:
        # Get all valid analysis IDs from PostgreSQL
        valid_ids_query = "SELECT id FROM analyses"
        valid_analyses = await database.fetch_all(valid_ids_query)
        valid_analysis_ids = {str(row["id"]) for row in valid_analyses}
        
        # Find and delete orphaned analysis_ids in ClickHouse
        orphaned_ids = set()
        tables = [
            'network_flows', 'dns_queries', 'tcp_lifecycle', 'process_events',
            'file_operations', 'capability_checks', 'oom_kills', 'bind_events',
            'sni_events', 'mount_events', 'workload_metadata', 'communication_edges'
        ]
        
        ch_config = get_clickhouse_config()
        direct_repo = ClickHouseEventRepository(
            host=ch_config.get('host', 'clickhouse'),
            port=ch_config.get('port', 8123),
            database=ch_config.get('database', 'flowfish'),
            user=ch_config.get('user', 'default'),
            password=ch_config.get('password', ''),
        )
        
        for table in tables[:3]:  # Check first 3 tables for speed
            try:
                distinct_query = f"SELECT DISTINCT analysis_id FROM {table} WHERE analysis_id != '' LIMIT 100"
                result = await direct_repo._execute_query(distinct_query)
                if result:
                    for row in result:
                        aid = str(row.get("analysis_id", ""))
                        if aid and aid not in valid_analysis_ids:
                            orphaned_ids.add(aid)
            except:
                pass
        
        # Delete orphaned data
        for orphan_id in orphaned_ids:
            try:
                result = await direct_repo.delete_analysis_data(
                    int(orphan_id) if orphan_id.isdigit() else 0,
                    wait_for_completion=False,  # Don't wait, do async
                    timeout_seconds=10
                )
                orphan_result["cleaned"] += result.get("total_deleted", 0)
            except:
                pass
        
        if orphaned_ids:
            logger.info("Auto-cleaned orphaned data",
                       orphaned_ids=list(orphaned_ids),
                       cleaned=orphan_result["cleaned"])
            
    except Exception as e:
        logger.debug(f"Orphan cleanup skipped: {e}")
    
    total_deleted += orphan_result.get("cleaned", 0)
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info("Analysis deleted completely", 
               analysis_id=analysis_id,
               analysis_name=analysis_name,
               total_deleted=total_deleted,
               orphans_cleaned=orphan_result.get("cleaned", 0),
               duration_ms=duration_ms)
    
    # Log activity
    await activity_service.log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username', 'system'),
        action=ActivityService.ACTION_DELETE,
        resource_type=ActivityService.RESOURCE_ANALYSIS,
        resource_id=str(analysis_id),
        resource_name=analysis_name,
        ip_address=get_client_ip(request),
        details={
            "cluster_id": cluster_id,
            "total_deleted": total_deleted,
            "duration_ms": duration_ms
        }
    )
    
    message_text = f"Analysis '{analysis_name}' deleted. Removed {total_deleted:,} records in {duration_ms}ms."
    if orphan_result.get("cleaned", 0) > 0:
        message_text += f" (including {orphan_result['cleaned']:,} orphaned records)"
    
    return DeleteAnalysisResponse(
        analysis_id=analysis_id,
        deleted=True,
        postgresql=postgresql_result,
        neo4j=neo4j_result,
        clickhouse=clickhouse_result,
        redis=redis_result,
        rabbitmq=rabbitmq_result,
        duration_ms=duration_ms,
        message=message_text
    )


@router.get("/{analysis_id}/runs", response_model=List[AnalysisRunResponse])
async def get_analysis_runs(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all runs for an analysis
    
    If analysis is running or events_collected is 0, fetches current counts from ClickHouse.
    This ensures live updates while analysis is running.
    """
    
    # Get analysis to get cluster_id and status
    analysis_query = "SELECT cluster_id, status FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    cluster_id = analysis["cluster_id"] if analysis else None
    analysis_status = analysis["status"] if analysis else None
    
    query = """
        SELECT * FROM analysis_runs
        WHERE analysis_id = :analysis_id
        ORDER BY start_time DESC
    """
    
    results = await database.fetch_all(query, {"analysis_id": analysis_id})
    runs = [dict(row) for row in results]
    
    # Fetch from ClickHouse if:
    # 1. Analysis is currently running (for live updates)
    # 2. Any run has 0 events (initial load or missing data)
    is_running = analysis_status == 'running'
    has_zero_events = any(run.get('events_collected', 0) == 0 for run in runs)
    needs_update = is_running or has_zero_events
    
    if needs_update and cluster_id:
        try:
            from repositories.event_repository import get_event_repository, ClickHouseEventRepository
            from config import get_clickhouse_config
            
            event_repo = get_event_repository(use_microservice=True)
            
            # Get event counts from ClickHouse
            event_counts = await event_repo.get_event_counts_by_type(
                cluster_id=cluster_id,
                analysis_id=analysis_id
            )
            total_events = int(sum(event_counts.values())) if event_counts else 0
            
            # Get unique communications count from network_flows
            communications_count = 0
            try:
                ch_config = get_clickhouse_config()
                direct_repo = ClickHouseEventRepository(
                    host=ch_config.get('host', 'clickhouse'),
                    port=ch_config.get('port', 8123),
                    database=ch_config.get('database', 'flowfish'),
                    user=ch_config.get('user', 'default'),
                    password=ch_config.get('password', ''),
                )
                
                # Count unique source->destination communication pairs
                # Support multi-cluster format: analysis_id can be '{id}' or '{id}-{cluster_id}'
                comm_query = f"""
                    SELECT count() as cnt FROM (
                        SELECT DISTINCT 
                            source_namespace, source_pod, 
                            dest_namespace, dest_pod, dest_port, protocol
                        FROM network_flows 
                        WHERE analysis_id = '{analysis_id}' OR analysis_id LIKE '{analysis_id}-%'
                    )
                """
                comm_result = await direct_repo._execute_query(comm_query)
                if comm_result and len(comm_result) > 0:
                    communications_count = int(comm_result[0].get('cnt', 0))
            except Exception as e:
                logger.debug(f"Failed to get communications count: {e}")
            
            # Update runs with ClickHouse data
            # Strategy: ClickHouse stores events by analysis_id (not per-run), so we can't
            # know exactly which events belong to which run. Best approach:
            # 1. Runs with DB values > 0: Keep their recorded values
            # 2. Running run: Show (total - sum of recorded runs)
            # 3. Completed/stopped runs with 0: Backfill with (total - sum of recorded runs)
            #    but only for the LATEST such run to avoid double-counting
            
            # Sort runs by run_number to process in order
            sorted_runs = sorted(runs, key=lambda r: r.get('run_number', 0))
            
            # Calculate sum of runs that already have recorded values
            recorded_events = sum(
                (r.get('events_collected') or 0) for r in sorted_runs 
                if (r.get('events_collected') or 0) > 0
            )
            recorded_comms = sum(
                (r.get('communications_discovered') or 0) for r in sorted_runs 
                if (r.get('communications_discovered') or 0) > 0
            )
            
            # Calculate unrecorded events (what's in ClickHouse but not in any run)
            unrecorded_events = max(0, total_events - recorded_events)
            unrecorded_comms = max(0, communications_count - recorded_comms)
            
            # Find which run should get the unrecorded events:
            # Priority: 1) Currently running run, 2) Latest run with 0 events
            target_run_id = None
            
            # First check for running run
            for run in reversed(sorted_runs):
                if run.get('status') == 'running':
                    target_run_id = run.get('id')
                    break
            
            # If no running run, find the latest completed/stopped run with 0 events
            if not target_run_id:
                for run in reversed(sorted_runs):
                    if (run.get('events_collected') or 0) == 0:
                        target_run_id = run.get('id')
                        break
            
            # Update the target run with unrecorded events
            for run in sorted_runs:
                run_id = run.get('id')
                run_status = run.get('status', '')
                current_events = run.get('events_collected') or 0
                
                if run_id == target_run_id:
                    run['events_collected'] = unrecorded_events
                    run['communications_discovered'] = unrecorded_comms
                    
                    # Persist to DB if this is a completed/stopped/failed run (backfill)
                    if run_status in ('stopped', 'completed', 'failed') and current_events == 0:
                        try:
                            update_query = """
                                UPDATE analysis_runs 
                                SET events_collected = :events, communications_discovered = :comms
                                WHERE id = :run_id
                            """
                            await database.execute(update_query, {
                                "run_id": run_id,
                                "events": unrecorded_events,
                                "comms": unrecorded_comms
                            })
                            logger.info(f"Backfilled run {run_id} with events={unrecorded_events}, comms={unrecorded_comms}")
                        except Exception as db_err:
                            logger.warning(f"Failed to backfill run {run_id}: {db_err}")
                        
            logger.info("Fetched live ClickHouse data for analysis runs",
                       analysis_id=analysis_id,
                       is_running=is_running,
                       total_events=total_events,
                       communications_count=communications_count,
                       recorded_events=recorded_events,
                       unrecorded_events=unrecorded_events,
                       target_run_id=target_run_id)
                       
        except Exception as e:
            logger.warning(f"Failed to fetch ClickHouse data for runs: {e}")
    
    return [AnalysisRunResponse(**run) for run in runs]


class OrphanCleanupResponse(BaseModel):
    """Response model for orphan cleanup operation"""
    orphaned_analysis_ids: List[str] = []
    clickhouse_deleted: dict = {}
    neo4j_deleted: dict = {}
    total_deleted: int = 0
    duration_ms: int = 0
    message: str = ""


@router.delete("/cleanup/orphaned", response_model=OrphanCleanupResponse)
async def cleanup_orphaned_data(
    current_user: dict = Depends(get_current_user)
):
    """
    Clean up orphaned data - data in ClickHouse/Neo4j for analyses that no longer exist in PostgreSQL.
    
    This is useful when:
    - An analysis was partially deleted
    - Data was written with an analysis_id that doesn't match any existing analysis
    - Manual database cleanup left inconsistent state
    
    WARNING: This will permanently delete all orphaned data!
    """
    import time
    start_time = time.time()
    
    # Step 1: Get all valid analysis IDs from PostgreSQL
    valid_ids_query = "SELECT id FROM analyses"
    valid_analyses = await database.fetch_all(valid_ids_query)
    valid_analysis_ids = {str(row["id"]) for row in valid_analyses}
    
    logger.info("Valid analysis IDs in PostgreSQL", count=len(valid_analysis_ids), ids=list(valid_analysis_ids))
    
    # Step 2: Find orphaned analysis IDs in ClickHouse
    orphaned_ids = set()
    clickhouse_result = {"tables": {}, "total_deleted": 0}
    
    try:
        from repositories.event_repository import get_event_repository, ClickHouseEventRepository
        from config import get_clickhouse_config
        
        ch_config = get_clickhouse_config()
        direct_repo = ClickHouseEventRepository(
            host=ch_config.get('host', 'clickhouse'),
            port=ch_config.get('port', 8123),
            database=ch_config.get('database', 'flowfish'),
            user=ch_config.get('user', 'default'),
            password=ch_config.get('password', ''),
        )
        
        # Query for distinct analysis_ids in ClickHouse
        tables = [
            'network_flows', 'dns_queries', 'tcp_lifecycle', 'process_events',
            'file_operations', 'capability_checks', 'oom_kills', 'bind_events',
            'sni_events', 'mount_events', 'workload_metadata', 'communication_edges'
        ]
        
        for table in tables:
            try:
                distinct_query = f"SELECT DISTINCT analysis_id FROM {table} WHERE analysis_id != ''"
                result = await direct_repo._execute_query(distinct_query)
                if result:
                    for row in result:
                        aid = str(row.get("analysis_id", ""))
                        if aid and aid not in valid_analysis_ids:
                            orphaned_ids.add(aid)
            except Exception as e:
                logger.debug(f"Query failed for {table}: {e}")
        
        logger.info("Found orphaned analysis IDs in ClickHouse", 
                   count=len(orphaned_ids), 
                   ids=list(orphaned_ids))
        
        # Step 3: Delete orphaned data from ClickHouse
        for orphan_id in orphaned_ids:
            try:
                result = await direct_repo.delete_analysis_data(
                    int(orphan_id) if orphan_id.isdigit() else 0,
                    wait_for_completion=True,
                    timeout_seconds=30
                )
                for table, count in result.get("tables", {}).items():
                    clickhouse_result["tables"][table] = clickhouse_result["tables"].get(table, 0) + count
                clickhouse_result["total_deleted"] += result.get("total_deleted", 0)
            except Exception as e:
                logger.warning(f"Failed to delete orphan {orphan_id} from ClickHouse: {e}")
        
    except Exception as e:
        logger.error("ClickHouse orphan cleanup failed", error=str(e))
        clickhouse_result["error"] = str(e)
    
    # Step 4: Clean up orphaned Neo4j data
    neo4j_result = {"deleted_edges": 0, "deleted_nodes": 0}
    
    try:
        from database.neo4j import neo4j_service
        
        for orphan_id in orphaned_ids:
            try:
                result = neo4j_service.delete_analysis_data(
                    int(orphan_id) if orphan_id.isdigit() else 0,
                    batch_size=5000
                )
                neo4j_result["deleted_edges"] += result.get("deleted_edges", 0)
                neo4j_result["deleted_nodes"] += result.get("deleted_nodes", 0)
            except Exception as e:
                logger.warning(f"Failed to delete orphan {orphan_id} from Neo4j: {e}")
        
        # Also cleanup nodes with no edges (truly orphaned)
        cleanup_query = """
        MATCH (n) WHERE NOT EXISTS { MATCH (n)-[]-() }
        WITH n LIMIT 10000
        DELETE n
        RETURN count(n) as deleted
        """
        try:
            cleanup_result = neo4j_service._execute_query(cleanup_query, {})
            if cleanup_result:
                neo4j_result["orphaned_nodes"] = cleanup_result[0].get("deleted", 0)
                neo4j_result["deleted_nodes"] += neo4j_result["orphaned_nodes"]
        except:
            pass
            
    except Exception as e:
        logger.error("Neo4j orphan cleanup failed", error=str(e))
        neo4j_result["error"] = str(e)
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    total_deleted = (
        clickhouse_result.get("total_deleted", 0) +
        neo4j_result.get("deleted_edges", 0) +
        neo4j_result.get("deleted_nodes", 0)
    )
    
    logger.info("Orphan cleanup completed",
               orphaned_ids=list(orphaned_ids),
               clickhouse_deleted=clickhouse_result.get("total_deleted", 0),
               neo4j_deleted=neo4j_result,
               duration_ms=duration_ms)
    
    return OrphanCleanupResponse(
        orphaned_analysis_ids=list(orphaned_ids),
        clickhouse_deleted=clickhouse_result,
        neo4j_deleted=neo4j_result,
        total_deleted=total_deleted,
        duration_ms=duration_ms,
        message=f"Cleaned up {len(orphaned_ids)} orphaned analyses. Deleted {total_deleted:,} records in {duration_ms}ms."
    )


# ============================================
# Scheduled Analysis Endpoints
# ============================================

class ScheduleAnalysisRequest(BaseModel):
    """Request to schedule recurring analysis execution"""
    cron_expression: str = Field(..., max_length=100, description="Cron expression (e.g. '0 2 * * *' for daily at 02:00)")
    duration_seconds: int = Field(..., ge=60, le=86400, description="Per-run duration in seconds (1 min - 24 hours)")
    max_runs: Optional[int] = Field(None, ge=0, description="Maximum scheduled runs (0 or null = unlimited)")

class ScheduleAnalysisResponse(BaseModel):
    """Response for schedule operation"""
    analysis_id: int
    is_scheduled: bool
    schedule_expression: str
    schedule_duration_seconds: int
    next_run_at: Optional[str] = None
    message: str


@router.post("/{analysis_id}/schedule", response_model=ScheduleAnalysisResponse)
async def schedule_analysis(
    analysis_id: int,
    schedule_req: ScheduleAnalysisRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Schedule an analysis for recurring execution.
    
    Sets up a cron-based schedule that will automatically start the analysis
    at the specified intervals. Each run uses the same configuration as the
    original analysis and auto-stops after duration_seconds.
    
    **Permissions Required:** analysis.start
    """
    if not check_analysis_permission(current_user, "start"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. Required role: Admin, Operator, or Analyst."
        )
    
    analysis_query = "SELECT * FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    max_runs = schedule_req.max_runs or 0
    
    try:
        orc_result = await analysis_orchestrator_client.schedule_analysis(
            analysis_id=analysis_id,
            cron_expression=schedule_req.cron_expression,
            duration_seconds=schedule_req.duration_seconds,
            max_runs=max_runs
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register schedule with orchestrator: {str(e)}"
        )
    
    if not orc_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=orc_result.get("message", "Orchestrator rejected the schedule")
        )
    
    update_query = """
        UPDATE analyses SET 
            is_scheduled = true,
            schedule_expression = :cron,
            schedule_duration_seconds = :duration,
            max_scheduled_runs = :max_runs,
            next_run_at = :next_run_at,
            updated_at = NOW()
        WHERE id = :id
    """
    await database.execute(update_query, {
        "id": analysis_id,
        "cron": schedule_req.cron_expression,
        "duration": schedule_req.duration_seconds,
        "max_runs": max_runs if max_runs > 0 else None,
        "next_run_at": orc_result.get("next_run_at")
    })
    
    await activity_service.log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username', 'system'),
        action="schedule",
        resource_type=ActivityService.RESOURCE_ANALYSIS,
        resource_id=str(analysis_id),
        resource_name=analysis.get("name", f"Analysis {analysis_id}"),
        ip_address=get_client_ip(request),
        details={
            "cron_expression": schedule_req.cron_expression,
            "duration_seconds": schedule_req.duration_seconds,
            "max_runs": max_runs
        }
    )
    
    return ScheduleAnalysisResponse(
        analysis_id=analysis_id,
        is_scheduled=True,
        schedule_expression=schedule_req.cron_expression,
        schedule_duration_seconds=schedule_req.duration_seconds,
        next_run_at=orc_result.get("next_run_at"),
        message="Analysis scheduled successfully"
    )


@router.delete("/{analysis_id}/schedule")
async def unschedule_analysis(
    analysis_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Remove the schedule from an analysis.
    
    Stops recurring execution. Does not affect a currently running analysis.
    
    **Permissions Required:** analysis.stop
    """
    if not check_analysis_permission(current_user, "stop"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. Required role: Admin, Operator, or Analyst."
        )
    
    analysis_query = "SELECT * FROM analyses WHERE id = :id"
    analysis = await database.fetch_one(analysis_query, {"id": analysis_id})
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with id {analysis_id} not found"
        )
    
    try:
        await analysis_orchestrator_client.unschedule_analysis(analysis_id)
    except Exception as e:
        logger.warning("Failed to unschedule via orchestrator (clearing DB anyway)",
                      analysis_id=analysis_id, error=str(e))
    
    update_query = """
        UPDATE analyses SET 
            is_scheduled = false,
            schedule_expression = NULL,
            schedule_duration_seconds = NULL,
            next_run_at = NULL,
            max_scheduled_runs = NULL,
            schedule_run_count = 0,
            updated_at = NOW()
        WHERE id = :id
    """
    await database.execute(update_query, {"id": analysis_id})
    
    await activity_service.log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username', 'system'),
        action="unschedule",
        resource_type=ActivityService.RESOURCE_ANALYSIS,
        resource_id=str(analysis_id),
        resource_name=analysis.get("name", f"Analysis {analysis_id}"),
        ip_address=get_client_ip(request),
        details={}
    )
    
    return {"message": "Schedule removed", "analysis_id": analysis_id}
