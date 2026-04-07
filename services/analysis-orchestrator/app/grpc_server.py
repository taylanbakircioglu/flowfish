"""gRPC Server for Analysis Orchestrator Service"""

import grpc
from concurrent import futures
import logging
import sys
import os
import asyncio
import threading
import httpx

# Add proto to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proto import analysis_orchestrator_pb2
from proto import analysis_orchestrator_pb2_grpc
from proto import common_pb2
from app.config import settings
from app.database import db_manager, AnalysisType, AnalysisStatus
from app.scheduler import scheduler
import app.scheduler as scheduler_module
from app.analysis_executor import AnalysisExecutor
from app.ingestion_client import ingestion_client
from app.auto_stop_monitor import auto_stop_monitor

logger = logging.getLogger(__name__)


class AnalysisOrchestratorService(analysis_orchestrator_pb2_grpc.AnalysisOrchestratorServicer):
    """gRPC Service implementation"""
    
    def __init__(self):
        self.executor = AnalysisExecutor()
        self.active_sessions = {}  # analysis_id -> session_id mapping
        logger.info("AnalysisOrchestratorService initialized")
    
    def CreateAnalysis(self, request, context):
        """Create a new analysis"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Note: Backend creates analyses directly in DB, this is for compatibility
            analysis_data = {
                "cluster_id": request.cluster_id,
                "name": request.name,
                "description": request.description,
                "scope_type": "cluster",  # Default scope type
                "scope_config": dict(request.parameters) if request.parameters else {},
                "gadget_config": {"enabled_gadgets": ["trace_network", "top_tcp", "trace_tcpretrans"]},
                "time_config": {},
                "output_config": {},
                "created_by": request.created_by
            }
            
            analysis = loop.run_until_complete(db_manager.create_analysis(analysis_data))
            
            # TODO: Re-enable scheduling when time_config schema is extended
            # if request.schedule_expression:
            #     loop.run_until_complete(
            #         scheduler.schedule_analysis(analysis.id, request.schedule_expression)
            #     )
            
            return self._analysis_to_proto(analysis)
        
        except Exception as e:
            logger.error(f"Failed to create analysis: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return analysis_orchestrator_pb2.Analysis()
    
    def GetAnalysis(self, request, context):
        """Get analysis by ID"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            analysis = loop.run_until_complete(db_manager.get_analysis(request.id))
            
            if not analysis:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Analysis not found")
                return analysis_orchestrator_pb2.Analysis()
            
            return self._analysis_to_proto(analysis)
        
        except Exception as e:
            logger.error(f"Failed to get analysis: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return analysis_orchestrator_pb2.Analysis()
    
    def ListAnalyses(self, request, context):
        """List analyses"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Note: request.status is a string, not an enum
            analyses = loop.run_until_complete(
                db_manager.list_analyses(
                    cluster_id=request.cluster_id if request.cluster_id else None,
                    scope_type=None,  # analysis_type removed from schema
                    status=request.status if request.status else None
                )
            )
            
            return analysis_orchestrator_pb2.AnalysisList(
                analyses=[self._analysis_to_proto(a) for a in analyses],
                total=len(analyses)
            )
        
        except Exception as e:
            logger.error(f"Failed to list analyses: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return analysis_orchestrator_pb2.ListAnalysesResponse()
    
    def DeleteAnalysis(self, request, context):
        """Delete analysis"""
        try:
            # Use sync method to avoid event loop issues
            success = db_manager.delete_analysis_sync(request.id)
            
            if not success:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Analysis not found")
            
            return common_pb2.StatusResponse(
                success=success,
                message="Analysis deleted" if success else "Analysis not found",
                code=0 if success else 404
            )
        
        except Exception as e:
            logger.error(f"Failed to delete analysis: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return common_pb2.StatusResponse(success=False, message=str(e), code=500)
    
    def ExecuteAnalysis(self, request, context):
        """Execute analysis immediately"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Execute
            result = loop.run_until_complete(self.executor.execute_analysis(request.id))
            
            return analysis_orchestrator_pb2.ExecuteAnalysisResponse(
                success=True,
                message="Analysis executed successfully",
                result_summary=str(result)
            )
        
        except Exception as e:
            logger.error(f"Failed to execute analysis: {e}")
            return analysis_orchestrator_pb2.ExecuteAnalysisResponse(
                success=False,
                message=f"Execution failed: {str(e)}",
                result_summary=""
            )
    
    def StartAnalysis(self, request, context):
        """Start an analysis (begins eBPF collection) - supports multi-cluster"""
        try:
            import json
            import uuid
            
            # Use sync methods to avoid event loop issues
            analysis = db_manager.get_analysis_sync(request.analysis_id)
            
            if not analysis:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Analysis {request.analysis_id} not found")
                return analysis_orchestrator_pb2.StartAnalysisResponse()
            
            # Multi-cluster support: get all cluster IDs
            is_multi_cluster = getattr(analysis, 'is_multi_cluster', False)
            cluster_ids_json = getattr(analysis, 'cluster_ids', None)
            
            # Parse cluster_ids (stored as JSON in database)
            if cluster_ids_json:
                if isinstance(cluster_ids_json, str):
                    cluster_ids = json.loads(cluster_ids_json)
                else:
                    cluster_ids = cluster_ids_json
            else:
                cluster_ids = [analysis.cluster_id]
            
            if is_multi_cluster:
                logger.info(f"🌐 Multi-cluster analysis {request.analysis_id}: starting collection on {len(cluster_ids)} clusters")
            
            # Parse common configurations from database
            scope_data = analysis.scope_config or {}
            scope_type_str = scope_data.get('scope_type', analysis.scope_type or 'cluster')
            
            scope_type_map = {
                'cluster': analysis_orchestrator_pb2.ScopeType.CLUSTER,
                'namespace': analysis_orchestrator_pb2.ScopeType.NAMESPACE,
                'deployment': analysis_orchestrator_pb2.ScopeType.DEPLOYMENT,
                'pod': analysis_orchestrator_pb2.ScopeType.POD,
                'label': analysis_orchestrator_pb2.ScopeType.LABEL
            }
            
            # Get per-cluster scope configuration (for multi-cluster with different scopes per cluster)
            per_cluster_scope = scope_data.get('per_cluster_scope', {}) or {}
            
            # Global scope values (used as fallback when per_cluster_scope is not defined)
            global_namespaces = scope_data.get('namespaces', []) or []
            global_deployments = scope_data.get('deployments', []) or []
            global_pods = scope_data.get('pods', []) or []
            global_labels = scope_data.get('labels', {}) or {}
            
            # Exclusion filters
            exclude_namespaces = scope_data.get('exclude_namespaces', []) or []
            exclude_pod_patterns = scope_data.get('exclude_pod_patterns', []) or []
            exclude_strategy = scope_data.get('exclude_strategy', 'aggressive') or 'aggressive'
            
            gadget_data = analysis.gadget_config or {}
            # Default gadgets: network flow, TCP throughput (for bytes), TCP retransmit (for errors)
            default_gadgets = ['trace_network', 'top_tcp', 'trace_tcpretrans']
            
            # Map event type IDs (from frontend) to gadget names (for Inspector Gadget)
            EVENT_TYPE_TO_GADGET = {
                'network_flow': 'trace_network',
                'dns_query': 'trace_dns',
                'tcp_throughput': 'top_tcp',        # Required for bytes sent/received
                'tcp_retransmit': 'trace_tcpretrans',  # Required for network errors
                'process_exec': 'trace_exec',
                'file_operations': 'trace_open',
                'capability_checks': 'trace_capabilities',
                'oom_kills': 'trace_oomkill',
                'bind_events': 'trace_bind',
                'sni_events': 'trace_sni',
                'mount_events': 'trace_mount',
            }
            
            raw_gadgets = gadget_data.get('enabled_gadgets', default_gadgets) or default_gadgets
            
            # Convert event type IDs to gadget names
            gadget_modules = []
            for g in raw_gadgets:
                # If it's already a gadget name (starts with trace_ or top_), keep it
                if g.startswith('trace_') or g.startswith('top_'):
                    gadget_modules.append(g)
                # Otherwise, map from event type ID to gadget name
                elif g in EVENT_TYPE_TO_GADGET:
                    gadget_modules.append(EVENT_TYPE_TO_GADGET[g])
                else:
                    # Unknown - try to use as-is
                    gadget_modules.append(g)
            
            # CRITICAL FIX: Auto-add dependent gadgets for complete network metrics
            # When network_flow (trace_network/trace_tcp) is enabled, we MUST also enable:
            # - top_tcp: Required for bytes_sent/bytes_received metrics
            # - trace_tcpretrans: Required for network error detection
            # Without these, network flows will have 0 bytes and 0 errors
            network_gadgets = {'trace_network', 'trace_tcp', 'network_flow', 'network', 'network_traffic'}
            has_network = any(g in network_gadgets or g.lower() in network_gadgets for g in gadget_modules)
            
            if has_network:
                # Add top_tcp for byte transfer metrics if not already present
                if 'top_tcp' not in gadget_modules and 'tcp_throughput' not in raw_gadgets:
                    gadget_modules.append('top_tcp')
                    logger.info("Auto-added top_tcp gadget for byte transfer metrics")
                
                # Add trace_tcpretrans for network error detection if not already present
                if 'trace_tcpretrans' not in gadget_modules and 'tcp_retransmit' not in raw_gadgets:
                    gadget_modules.append('trace_tcpretrans')
                    logger.info("Auto-added trace_tcpretrans gadget for network error detection")
            
            # Remove duplicates while preserving order
            gadget_modules = list(dict.fromkeys(gadget_modules))
            
            time_data = analysis.time_config or {}
            duration_seconds = time_data.get('duration_seconds', 0) or 0
            
            # For recurring analyses only: fall back to schedule_duration_seconds
            # so manual starts also have a bounded per-run duration.
            # Scoped to 'recurring' mode to avoid altering continuous/timed/time_range behavior.
            analysis_mode = time_data.get('mode', '')
            if duration_seconds == 0 and analysis_mode == 'recurring' and getattr(analysis, 'schedule_duration_seconds', None):
                duration_seconds = analysis.schedule_duration_seconds
                # Persist to time_config so the auto-stop monitor can enforce this duration
                time_data['duration_seconds'] = duration_seconds
                db_manager.update_analysis_sync(request.analysis_id, {"time_config": time_data})
                logger.info(f"Analysis {request.analysis_id}: recurring mode, injected schedule_duration_seconds={duration_seconds}s into time_config")
            
            logger.info(f"Analysis {request.analysis_id} config: scope_type={scope_type_str}, "
                       f"global_namespaces={global_namespaces}, global_pods={global_pods}, "
                       f"per_cluster_scope_defined={bool(per_cluster_scope)}, "
                       f"exclude_namespaces={exclude_namespaces}, exclude_pod_patterns={exclude_pod_patterns}, exclude_strategy={exclude_strategy}, "
                       f"gadgets={gadget_modules}, clusters={len(cluster_ids)}")
            
            # Fetch global ingestion rate limit via synchronous HTTP call
            # NOTE: StartAnalysis is a sync gRPC method, so we must use httpx.Client (not AsyncClient)
            ingestion_rate_limit = 0
            try:
                backend_url = f"http://{settings.backend_service_host}:{settings.backend_service_port}"
                with httpx.Client(timeout=5.0) as http_client:
                    resp = http_client.get(f"{backend_url}/api/v1/settings/analysis-limits/defaults")
                    if resp.status_code == 200:
                        ingestion_rate_limit = resp.json().get('ingestion_rate_limit_per_second', 0)
            except Exception as e:
                logger.warning(f"Failed to fetch ingestion rate limit, using safe fallback (5000 events/sec): {e}")
                ingestion_rate_limit = 5000
            
            # Start collection for each cluster
            task_assignments = []
            session_ids = []
            failed_clusters = []
            
            for cluster_id in cluster_ids:
                try:
                    cluster = db_manager.get_cluster_sync(cluster_id)
                    
                    if not cluster:
                        logger.error(f"Cluster {cluster_id} not found for analysis {request.analysis_id}")
                        failed_clusters.append({"cluster_id": cluster_id, "error": "Cluster not found"})
                        continue
                    
                    cluster_name = cluster.get('name', f"cluster-{cluster_id}")
                    connection_type = cluster.get('connection_type', 'in-cluster')
                    
                    # ============================================
                    # PER-CLUSTER SCOPE: Build cluster-specific scope
                    # Priority: per_cluster_scope[cluster_id] > global scope
                    # ============================================
                    cluster_id_str = str(cluster_id)
                    cluster_specific_scope = per_cluster_scope.get(cluster_id_str, {})
                    
                    # Use cluster-specific values if defined, otherwise fall back to global
                    cluster_namespaces = cluster_specific_scope.get('namespaces') if cluster_specific_scope.get('namespaces') else global_namespaces
                    cluster_deployments = cluster_specific_scope.get('deployments') if cluster_specific_scope.get('deployments') else global_deployments
                    cluster_pods = cluster_specific_scope.get('pods') if cluster_specific_scope.get('pods') else global_pods
                    # Labels are always global (per-cluster labels not implemented in wizard)
                    cluster_labels = global_labels
                    
                    # Create cluster-specific scope config
                    cluster_scope_config = analysis_orchestrator_pb2.ScopeConfig(
                        scope_type=scope_type_map.get(scope_type_str, analysis_orchestrator_pb2.ScopeType.CLUSTER),
                        namespaces=cluster_namespaces,
                        deployments=cluster_deployments,
                        pods=cluster_pods,
                        labels=cluster_labels,
                        exclude_namespaces=exclude_namespaces,
                        exclude_pod_patterns=exclude_pod_patterns,
                        exclude_strategy=exclude_strategy
                    )
                    
                    logger.info(f"Cluster {cluster_id} ({cluster_name}): scope namespaces={cluster_namespaces}, "
                               f"deployments={cluster_deployments}, pods={cluster_pods}")
                    
                    # Get gadget_namespace FIRST (required from UI)
                    gadget_namespace = cluster.get('gadget_namespace')
                    if not gadget_namespace:
                        logger.error(f"Cluster {cluster_id} has no gadget_namespace configured")
                        failed_clusters.append({"cluster_id": cluster_id, "error": "gadget_namespace not configured"})
                        continue
                    
                    # Now we can construct gadget_endpoint if not present
                    gadget_endpoint = cluster.get('gadget_endpoint') or f'inspektor-gadget.{gadget_namespace}.svc.cluster.local:16060'
                    
                    # Determine if this is a remote cluster
                    is_remote = connection_type.lower() not in ('in-cluster', 'in_cluster')
                    
                    # Use kubectl-gadget CLI for both in-cluster and remote clusters
                    gadget_protocol = "kubectl"
                    
                    # Get remote cluster credentials (encrypted in DB)
                    remote_token = cluster.get('token_encrypted', '')
                    remote_ca_cert = cluster.get('ca_cert_encrypted', '')
                    api_server_url = cluster.get('api_server_url', '')
                    skip_tls_verify = cluster.get('skip_tls_verify', False)
                    
                    logger.info(f"Cluster {cluster_id} ({cluster_name}): type={connection_type}, "
                               f"is_remote={is_remote}, gadget={gadget_endpoint}")
                    
                    # Generate unique task ID per cluster for multi-cluster
                    # Use format: task-{analysis_id}-{cluster_id}-{uuid} for multi-cluster
                    if is_multi_cluster:
                        task_id = f"task-{request.analysis_id}-{cluster_id}-{uuid.uuid4().hex[:8]}"
                    else:
                        task_id = f"task-{request.analysis_id}-{uuid.uuid4().hex[:8]}"
                    
                    # Call Ingestion Service to start collection
                    # NOTE: analysis_id stays as int; trace_manager formats it as {analysis_id}-{cluster_id}
                    # for multi-cluster when publishing events
                    # Get cluster's gadget version for dynamic OCI tag
                    cluster_gadget_version = cluster.get('gadget_version') or ''
                    
                    session_info = ingestion_client.start_collection(
                        task_id=task_id,
                        analysis_id=request.analysis_id,  # Keep as base analysis_id (int)
                        cluster_id=cluster_id,
                        cluster_name=cluster_name,
                        gadget_endpoint=gadget_endpoint,
                        gadget_protocol=gadget_protocol,
                        gadget_auth_method="token" if is_remote else "incluster",
                        gadget_modules=gadget_modules,
                        scope=cluster_scope_config,  # Use cluster-specific scope (per_cluster_scope support)
                        duration_seconds=duration_seconds,
                        # Remote cluster credentials
                        token=remote_token,
                        ca_cert=remote_ca_cert,
                        api_server_url=api_server_url,
                        verify_ssl=not skip_tls_verify,
                        gadget_namespace=gadget_namespace,
                        is_remote_cluster=is_remote,
                        gadget_version=cluster_gadget_version,
                        max_events_per_second=ingestion_rate_limit
                    )
                    
                    session_ids.append(session_info['session_id'])
                    
                    # Build task assignment for this cluster
                    task_assignment = analysis_orchestrator_pb2.TaskAssignment(
                        task_id=task_id,
                        worker_id=str(session_info['worker_id']),
                        cluster_id=cluster_id,
                        cluster_ids=[cluster_id],
                        gadget_modules=gadget_modules,
                        status="assigned",
                        analysis_id=request.analysis_id
                    )
                    task_assignments.append(task_assignment)
                    
                    logger.info(f"✅ Started collection on cluster {cluster_id}: session={session_info['session_id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to start collection on cluster {cluster_id}: {e}")
                    failed_clusters.append({"cluster_id": cluster_id, "error": str(e)})
            
            # Store session mappings (store all session IDs as comma-separated for multi-cluster)
            if session_ids:
                self.active_sessions[request.analysis_id] = ",".join(session_ids)
                
                # Update auto-stop monitor with current sessions
                auto_stop_monitor.set_active_sessions(self.active_sessions)
                
                # Update analysis status (sync)
                db_manager.update_analysis_status_sync(request.analysis_id, AnalysisStatus.RUNNING)
                
                # Check for gadget startup errors ASYNCHRONOUSLY (non-blocking)
                # This runs in a background thread so gRPC response is not delayed
                def _check_gadget_errors_background(analysis_id: int, session_id_list: list, existing_output: dict):
                    """Background task to check gadget errors after startup delay"""
                    import time as time_module  # Local import for thread safety
                    try:
                        # Wait for gadgets to attempt startup
                        time_module.sleep(3)
                        
                        all_gadget_errors = []
                        for sid in session_id_list:
                            try:
                                status = ingestion_client.get_collection_status(sid)
                                if status and status.get('gadget_errors'):
                                    all_gadget_errors.extend(status['gadget_errors'])
                            except Exception as e:
                                logger.warning(f"Failed to get status for session {sid}: {e}")
                        
                        # Save gadget errors to analysis output_config if any found
                        if all_gadget_errors:
                            logger.warning(f"Analysis {analysis_id} has gadget errors: {len(all_gadget_errors)}")
                            try:
                                updated_output = {
                                    **(existing_output or {}),
                                    "gadget_errors": all_gadget_errors,
                                    "has_gadget_warnings": True
                                }
                                db_manager.update_analysis_sync(analysis_id, {"output_config": updated_output})
                                logger.info(f"Saved gadget errors to analysis {analysis_id} metadata (async)")
                            except Exception as e:
                                logger.error(f"Failed to save gadget errors to analysis: {e}")
                    except Exception as e:
                        logger.error(f"Background gadget error check failed: {e}")
                
                # Start background thread (non-blocking)
                existing_output = analysis.output_config or {}
                thread = threading.Thread(
                    target=_check_gadget_errors_background,
                    args=(request.analysis_id, list(session_ids), existing_output),
                    daemon=True  # Thread will exit when main process exits
                )
                thread.start()
                
                # Build success message
                if failed_clusters:
                    message = f"Analysis started on {len(session_ids)}/{len(cluster_ids)} clusters"
                else:
                    message = f"Analysis started successfully on {len(cluster_ids)} cluster(s)"
                
                return analysis_orchestrator_pb2.StartAnalysisResponse(
                    success=True,
                    message=message,
                    task_assignments=task_assignments
                )
            else:
                # All clusters failed
                return analysis_orchestrator_pb2.StartAnalysisResponse(
                    success=False,
                    message=f"Failed to start analysis on all {len(cluster_ids)} clusters",
                    task_assignments=[]
                )
        
        except Exception as e:
            logger.error(f"Failed to start analysis {request.analysis_id}: {e}", exc_info=True)
            return analysis_orchestrator_pb2.StartAnalysisResponse(
                success=False,
                message=f"Failed to start analysis: {str(e)}",
                task_assignments=[]
            )
    
    def StopAnalysis(self, request, context):
        """Stop an analysis (stops eBPF collection) - supports multi-cluster"""
        try:
            # Check if we have active sessions for this analysis
            session_ids_str = self.active_sessions.get(request.analysis_id)
            
            if not session_ids_str:
                logger.warning(f"No active session found for analysis {request.analysis_id}")
                # Still try to update status (sync)
                db_manager.update_analysis_status_sync(request.analysis_id, AnalysisStatus.STOPPED)
                return common_pb2.StatusResponse(
                    success=True,
                    message="Analysis was not running",
                    code=0
                )
            
            # Multi-cluster support: session_ids are comma-separated
            session_ids = session_ids_str.split(",")
            is_multi_cluster = len(session_ids) > 1
            
            if is_multi_cluster:
                logger.info(f"🌐 Stopping multi-cluster analysis {request.analysis_id}: {len(session_ids)} sessions")
            else:
                logger.info(f"Stopping analysis {request.analysis_id}: session_id={session_ids[0]}")
            
            # Stop all sessions IN PARALLEL for multi-cluster
            # This reduces total stop time from N*30s to ~30s
            stopped_count = 0
            failed_sessions = []
            
            if is_multi_cluster:
                # Use ThreadPoolExecutor for parallel stops
                def stop_session(sid):
                    try:
                        return sid, ingestion_client.stop_collection(sid), None
                    except Exception as e:
                        return sid, False, str(e)
                
                with futures.ThreadPoolExecutor(max_workers=len(session_ids)) as executor:
                    stop_futures = {executor.submit(stop_session, sid): sid for sid in session_ids}
                    
                    for future in futures.as_completed(stop_futures):
                        session_id, success, error = future.result()
                        if success:
                            stopped_count += 1
                            logger.info(f"Stopped session: {session_id}")
                        else:
                            failed_sessions.append(session_id)
                            if error:
                                logger.error(f"Error stopping session {session_id}: {error}")
                            else:
                                logger.warning(f"Failed to stop session: {session_id}")
            else:
                # Single session - stop directly
                session_id = session_ids[0]
                try:
                    if ingestion_client.stop_collection(session_id):
                        stopped_count += 1
                        logger.info(f"Stopped session: {session_id}")
                    else:
                        failed_sessions.append(session_id)
                        logger.warning(f"Failed to stop session: {session_id}")
                except Exception as e:
                    failed_sessions.append(session_id)
                    logger.error(f"Error stopping session {session_id}: {e}")
            
            # Remove from active sessions
            if request.analysis_id in self.active_sessions:
                del self.active_sessions[request.analysis_id]
                # Update auto-stop monitor
                auto_stop_monitor.set_active_sessions(self.active_sessions)
            
            # Update analysis status (sync)
            db_manager.update_analysis_status_sync(request.analysis_id, AnalysisStatus.STOPPED)
            
            # Return appropriate response
            if stopped_count == len(session_ids):
                message = f"Analysis stopped successfully ({stopped_count} session(s))"
                return common_pb2.StatusResponse(success=True, message=message, code=0)
            elif stopped_count > 0:
                message = f"Analysis partially stopped: {stopped_count}/{len(session_ids)} sessions"
                return common_pb2.StatusResponse(success=True, message=message, code=0)
            else:
                return common_pb2.StatusResponse(
                    success=False,
                    message="Failed to stop collection via Ingestion Service",
                    code=500
                )
        
        except Exception as e:
            logger.error(f"Failed to stop analysis {request.analysis_id}: {e}", exc_info=True)
            return common_pb2.StatusResponse(
                success=False,
                message=f"Failed to stop analysis: {str(e)}",
                code=500
            )
    
    def GetAnalysisHistory(self, request, context):
        """Get analysis execution history - NOT IMPLEMENTED"""
        # TODO: This RPC and AnalysisRun message not defined in proto, needs proto update
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("GetAnalysisHistory RPC not implemented in proto definition")
        raise NotImplementedError("GetAnalysisHistory RPC not defined in proto")
    
    def GetAnalysisStatus(self, request, context):
        """Get current status of an analysis"""
        try:
            analysis_id = request.analysis_id
            
            # Get analysis from database using sync method
            analysis = db_manager.get_analysis_sync(analysis_id)
            
            if not analysis:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Analysis {analysis_id} not found")
                return analysis_orchestrator_pb2.AnalysisStatus()
            
            # Check if analysis has an active session
            session_id = self.active_sessions.get(analysis_id)
            
            return analysis_orchestrator_pb2.AnalysisStatus(
                analysis_id=analysis_id,
                status=analysis.status if isinstance(analysis.status, str) else analysis.status.value,
                events_collected=0,  # TODO: Get from ClickHouse
                bytes_written=0,     # TODO: Get from ClickHouse
            )
        
        except Exception as e:
            logger.error(f"Failed to get analysis status: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return analysis_orchestrator_pb2.AnalysisStatus()
    
    def ScheduleAnalysis(self, request, context):
        """Schedule an analysis for recurring cron-based execution"""
        try:
            analysis_id = request.analysis_id
            cron_expression = request.cron_expression
            duration_seconds = request.duration_seconds
            max_runs = request.max_runs
            
            analysis = db_manager.get_analysis_sync(analysis_id)
            if not analysis:
                return analysis_orchestrator_pb2.ScheduleAnalysisResponse(
                    success=False,
                    message=f"Analysis {analysis_id} not found"
                )
            
            next_run_at = scheduler.schedule_analysis_sync(
                analysis_id, cron_expression, duration_seconds, max_runs
            )
            
            return analysis_orchestrator_pb2.ScheduleAnalysisResponse(
                success=True,
                message=f"Analysis {analysis_id} scheduled with cron: {cron_expression}",
                next_run_at=next_run_at or ""
            )
            
        except Exception as e:
            logger.error(f"Failed to schedule analysis {request.analysis_id}: {e}", exc_info=True)
            return analysis_orchestrator_pb2.ScheduleAnalysisResponse(
                success=False,
                message=f"Failed to schedule: {str(e)}"
            )
    
    def UnscheduleAnalysis(self, request, context):
        """Remove schedule from an analysis"""
        try:
            scheduler.unschedule_analysis_sync(request.analysis_id)
            
            return common_pb2.StatusResponse(
                success=True,
                message=f"Analysis {request.analysis_id} unscheduled",
                code=0
            )
        except Exception as e:
            logger.error(f"Failed to unschedule analysis {request.analysis_id}: {e}")
            return common_pb2.StatusResponse(
                success=False,
                message=str(e),
                code=500
            )
    
    def _analysis_to_proto(self, analysis) -> analysis_orchestrator_pb2.Analysis:
        """Convert database analysis to proto"""
        return analysis_orchestrator_pb2.Analysis(
            id=analysis.id,
            name=analysis.name,
            description=analysis.description or "",
            cluster_ids=[analysis.cluster_id] if hasattr(analysis, 'cluster_id') and analysis.cluster_id else []
        )


def serve():
    """Start gRPC server"""
    # Initialize database tables
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db_manager.create_tables())
    
    # Start scheduler
    scheduler.start()
    
    # Start auto-stop monitor in background thread with its own event loop
    def run_auto_stop_monitor():
        monitor_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(monitor_loop)
        monitor_loop.run_until_complete(auto_stop_monitor.start())
        monitor_loop.run_forever()
    
    monitor_thread = threading.Thread(target=run_auto_stop_monitor, daemon=True)
    monitor_thread.start()
    logger.info("🔍 Auto-stop monitor started in background thread")
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers))
    
    # Create service instance and register
    service = AnalysisOrchestratorService()
    analysis_orchestrator_pb2_grpc.add_AnalysisOrchestratorServicer_to_server(
        service,
        server
    )
    
    # Set gRPC service reference so scheduler can call StartAnalysis
    scheduler_module._grpc_service_instance = service
    
    # Restore scheduled jobs from database (persistence across pod restarts)
    scheduler.restore_jobs_from_db()
    
    server.add_insecure_port(f'[::]:{settings.grpc_port}')
    server.start()
    
    logger.info(f"Analysis Orchestrator Service started on port {settings.grpc_port}")
    
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    server = serve()
    server.wait_for_termination()

