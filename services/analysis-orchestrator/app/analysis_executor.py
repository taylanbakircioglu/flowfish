"""Analysis Execution Logic"""

import logging
from datetime import datetime
from typing import Dict, Any, List
import asyncio

from app.database import db_manager, AnalysisStatus, AnalysisType
from app.gadget_client import get_gadget_client
from app.timeseries_query_client import get_timeseries_client
from app.graph_query_client import get_graph_client

logger = logging.getLogger(__name__)


class AnalysisExecutor:
    """Executes different types of analyses"""
    
    def __init__(self):
        logger.info("AnalysisExecutor initialized")
    
    async def execute_analysis(self, analysis_id: int) -> Dict[str, Any]:
        """
        Execute an analysis (supports both single and multi-cluster)
        
        Args:
            analysis_id: Analysis ID
        
        Returns:
            Execution result
        """
        logger.info(f"🚀 Starting analysis execution: {analysis_id}")
        
        # Get analysis
        analysis = await db_manager.get_analysis(analysis_id)
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")
        
        # Check for multi-cluster analysis
        is_multi_cluster = getattr(analysis, 'is_multi_cluster', False)
        cluster_ids = getattr(analysis, 'cluster_ids', None) or [analysis.cluster_id]
        
        if is_multi_cluster:
            logger.info(f"🌐 Multi-cluster analysis detected: {len(cluster_ids)} clusters")
        
        # Create analysis run record
        # NOTE: Column names must match database schema (start_time, end_time, NOT started_at/completed_at)
        run = await db_manager.create_analysis_run({
            "analysis_id": analysis_id,
            "run_number": 1,  # TODO: Increment based on existing runs
            "status": "pending",
            "start_time": datetime.utcnow()
        })
        
        try:
            # Update analysis status
            await db_manager.update_analysis(analysis_id, {"status": AnalysisStatus.RUNNING})
            await db_manager.update_analysis_run(run.id, {"status": "running"})
            
            # 🚀 Start Inspector Gadget trace for each cluster
            # Default gadget client for in-cluster scenarios
            default_gadget_client = get_gadget_client()
            parameters = analysis.parameters or {}
            gadget_results = []
            
            for cluster_id in cluster_ids:
                cluster_gadget_client = None
                try:
                    # Get cluster info to find gadget endpoint
                    cluster = await db_manager.get_cluster(cluster_id)
                    
                    # Use cluster-specific gadget endpoint if available
                    gadget_endpoint = getattr(cluster, 'gadget_endpoint', None) if cluster else None
                    
                    if gadget_endpoint:
                        # Create cluster-specific gadget client
                        from app.gadget_client import GadgetClient
                        cluster_gadget_client = GadgetClient(gadget_endpoint=gadget_endpoint)
                        gadget_client_to_use = cluster_gadget_client
                        logger.info(f"Using remote gadget endpoint for cluster {cluster_id}: {gadget_endpoint}")
                    else:
                        # Use default in-cluster gadget client
                        gadget_client_to_use = default_gadget_client
                    
                    # Use unique trace ID per cluster for multi-cluster analyses
                    trace_id_suffix = f"{analysis_id}-{cluster_id}"
                    
                    gadget_result = await gadget_client_to_use.start_trace(
                        analysis_id=trace_id_suffix,
                        cluster_id=str(cluster_id),
                        namespace=parameters.get("namespace"),
                        labels=parameters.get("labels"),
                        pods=parameters.get("pods"),
                        gadgets=parameters.get("gadgets", ["network", "dns", "tcp"])
                    )
                    gadget_results.append({
                        "cluster_id": cluster_id,
                        "trace_id": gadget_result.get('trace_id'),
                        "status": "started",
                        "gadget_endpoint": gadget_endpoint or "in-cluster"
                    })
                    logger.info(f"✅ Gadget trace started for cluster {cluster_id}: {gadget_result.get('trace_id')}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to start Gadget trace for cluster {cluster_id}: {e}")
                    gadget_results.append({
                        "cluster_id": cluster_id,
                        "error": str(e),
                        "status": "failed"
                    })
                    # Continue with other clusters even if one fails
                finally:
                    # Close cluster-specific client if created
                    if cluster_gadget_client:
                        await cluster_gadget_client.close()
            
            # Execute based on analysis type (with multi-cluster support)
            result = await self._execute_by_type(analysis, cluster_ids=cluster_ids)
            result["gadget_results"] = gadget_results
            result["is_multi_cluster"] = is_multi_cluster
            result["cluster_count"] = len(cluster_ids)
            
            # Calculate duration
            completed_at = datetime.utcnow()
            duration = (completed_at - run.start_time).total_seconds() if run.start_time else 0
            
            # Update run record (use correct column names per DB schema)
            await db_manager.update_analysis_run(run.id, {
                "status": "completed",
                "end_time": completed_at,
                "duration_seconds": int(duration),
                "run_metadata": result  # Store result in metadata column (mapped to 'metadata' in DB)
            })
            
            # Update analysis status
            await db_manager.update_analysis(analysis_id, {"status": AnalysisStatus.COMPLETED})
            
            logger.info(f"✅ Analysis {analysis_id} completed in {duration:.2f}s (clusters: {len(cluster_ids)})")
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Analysis {analysis_id} failed: {e}")
            
            # Update run record with error (use correct column names per DB schema)
            completed_at = datetime.utcnow()
            duration = (completed_at - run.start_time).total_seconds() if run.start_time else 0
            
            await db_manager.update_analysis_run(run.id, {
                "status": "failed",
                "end_time": completed_at,
                "duration_seconds": int(duration),
                "error_message": str(e)
            })
            
            # Update analysis status
            await db_manager.update_analysis(analysis_id, {"status": AnalysisStatus.FAILED})
            
            raise
    
    async def _execute_by_type(self, analysis, cluster_ids: List[int] = None) -> Dict[str, Any]:
        """
        Execute analysis based on type (supports multi-cluster)
        
        Args:
            analysis: Analysis object
            cluster_ids: List of cluster IDs for multi-cluster analysis
        
        Returns:
            Analysis result (aggregated for multi-cluster)
        """
        # All analyses currently use dependency mapping
        # Future types can be added based on gadget_config or a dedicated field
        scope_type = getattr(analysis, 'scope_type', 'cluster')
        scope_config = getattr(analysis, 'scope_config', {}) or {}
        
        # Use provided cluster_ids or fallback to single cluster
        if not cluster_ids:
            cluster_ids = [analysis.cluster_id]
        
        is_multi_cluster = len(cluster_ids) > 1
        
        logger.info(f"Executing dependency mapping analysis with scope_type={scope_type}, clusters={len(cluster_ids)}")
        
        # Build parameters from scope_config
        parameters = {
            'scope_type': scope_type,
            'namespaces': scope_config.get('namespaces', []),
            'deployments': scope_config.get('deployments', []),
            'pods': scope_config.get('pods', []),
            'labels': scope_config.get('labels', {})
        }
        
        if is_multi_cluster:
            # Execute dependency mapping for each cluster and aggregate results
            return await self._execute_multi_cluster_dependency_mapping(cluster_ids, parameters)
        else:
            # Execute dependency mapping for single cluster
            return await self._execute_dependency_mapping(analysis.cluster_id, parameters)
    
    async def _execute_multi_cluster_dependency_mapping(
        self,
        cluster_ids: List[int],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute dependency mapping analysis across multiple clusters
        
        Aggregates results from all clusters and provides per-cluster breakdown.
        """
        logger.info(f"Executing multi-cluster dependency mapping for {len(cluster_ids)} clusters")
        
        # Execute for each cluster in parallel
        tasks = [
            self._execute_dependency_mapping(cluster_id, parameters)
            for cluster_id in cluster_ids
        ]
        
        cluster_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        aggregated = {
            "total_workloads": 0,
            "total_connections": 0,
            "isolated_workloads": 0,
            "max_depth": 0,
            "critical_paths": 0,
            "critical_nodes": [],
            "per_cluster": {}
        }
        
        for idx, result in enumerate(cluster_results):
            cluster_id = cluster_ids[idx]
            
            if isinstance(result, Exception):
                logger.warning(f"Cluster {cluster_id} analysis failed: {result}")
                aggregated["per_cluster"][str(cluster_id)] = {
                    "error": str(result),
                    "status": "failed"
                }
                continue
            
            # Aggregate totals
            aggregated["total_workloads"] += result.get("total_workloads", 0)
            aggregated["total_connections"] += result.get("total_connections", 0)
            aggregated["isolated_workloads"] += result.get("isolated_workloads", 0)
            aggregated["max_depth"] = max(aggregated["max_depth"], result.get("max_depth", 0))
            aggregated["critical_paths"] += result.get("critical_paths", 0)
            
            # Collect critical nodes with cluster context
            for node in result.get("critical_nodes", []):
                node["cluster_id"] = cluster_id
                aggregated["critical_nodes"].append(node)
            
            # Store per-cluster results
            aggregated["per_cluster"][str(cluster_id)] = {
                "total_workloads": result.get("total_workloads", 0),
                "total_connections": result.get("total_connections", 0),
                "isolated_workloads": result.get("isolated_workloads", 0),
                "max_depth": result.get("max_depth", 0),
                "status": "completed"
            }
        
        # Sort and limit critical nodes
        aggregated["critical_nodes"] = sorted(
            aggregated["critical_nodes"],
            key=lambda x: x.get("connection_count", 0),
            reverse=True
        )[:20]  # Top 20 across all clusters
        
        logger.info(f"✅ Multi-cluster dependency mapping completed: "
                   f"{aggregated['total_workloads']} workloads, "
                   f"{aggregated['total_connections']} connections across {len(cluster_ids)} clusters")
        
        return aggregated
    
    async def _execute_dependency_mapping(
        self,
        cluster_id: int,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute dependency mapping analysis
        
        Uses graph-query service to:
        1. Query Neo4j for current dependency graph
        2. Analyze connections and dependencies
        3. Calculate metrics (depth, breadth, complexity)
        """
        logger.info(f"Executing dependency mapping for cluster {cluster_id}")
        
        graph_client = get_graph_client()
        namespace = parameters.get("namespaces", [None])[0]  # Use first namespace or None
        
        try:
            # Get dependency graph from graph-query service
            graph = await graph_client.get_dependency_graph(
                cluster_id=cluster_id,
                namespace=namespace
            )
            
            total_workloads = graph.get("total_nodes", 0)
            total_connections = graph.get("total_edges", 0)
            
            # Get isolated workloads
            isolated = await graph_client.get_isolated_workloads(
                cluster_id=cluster_id,
                namespace=namespace
            )
            
            # Get critical paths
            critical = await graph_client.get_critical_paths(
                cluster_id=cluster_id,
                min_depth=3
            )
            
            # Calculate max depth (approximation based on critical nodes)
            max_depth = max([c.get("connection_count", 0) for c in critical], default=0)
            
            logger.info(f"✅ Dependency mapping completed: {total_workloads} workloads, {total_connections} connections")
            
            return {
                "total_workloads": total_workloads,
                "total_connections": total_connections,
                "isolated_workloads": len(isolated),
                "max_depth": max_depth,
                "critical_paths": len(critical),
                "critical_nodes": critical[:10]  # Top 10 critical nodes
            }
            
        except Exception as e:
            logger.error(f"Dependency mapping failed: {e}")
            # Return empty result on error
            return {
                "total_workloads": 0,
                "total_connections": 0,
                "isolated_workloads": 0,
                "max_depth": 0,
                "critical_paths": 0,
                "error": str(e)
            }
    
    async def _execute_change_detection(
        self,
        cluster_id: int,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute change detection analysis
        
        Uses graph-query + timeseries-query services to:
        1. Compare current state with baseline
        2. Detect new/removed workloads and connections
        3. Generate change report
        """
        logger.info(f"Executing change detection for cluster {cluster_id}")
        
        graph_client = get_graph_client()
        ts_client = get_timeseries_client()
        
        try:
            # Get current graph state
            current_graph = await graph_client.get_dependency_graph(cluster_id=cluster_id)
            current_nodes = {n.get("id") for n in current_graph.get("nodes", [])}
            current_edges = {
                (e.get("source_id"), e.get("target_id"))
                for e in current_graph.get("edges", [])
            }
            
            # Get event statistics for analysis context
            stats = await ts_client.get_event_stats(cluster_id=cluster_id)
            
            # TODO: Compare with stored baseline
            # For now, return current state as "changes" since no baseline exists
            baseline_nodes: set = set()  # Would come from stored baseline
            baseline_edges: set = set()  # Would come from stored baseline
            
            new_workloads = len(current_nodes - baseline_nodes)
            removed_workloads = len(baseline_nodes - current_nodes)
            new_connections = len(current_edges - baseline_edges)
            removed_connections = len(baseline_edges - current_edges)
            
            # Connections in both but potentially modified (different metrics)
            modified_connections = 0  # Would require deeper comparison
            
            logger.info(f"✅ Change detection completed: +{new_workloads}/-{removed_workloads} workloads")
            
            return {
                "new_workloads": new_workloads,
                "removed_workloads": removed_workloads,
                "new_connections": new_connections,
                "removed_connections": removed_connections,
                "modified_connections": modified_connections,
                "current_workload_count": len(current_nodes),
                "current_connection_count": len(current_edges),
                "total_events": stats.get("total_events", 0)
            }
            
        except Exception as e:
            logger.error(f"Change detection failed: {e}")
            return {
                "new_workloads": 0,
                "removed_workloads": 0,
                "new_connections": 0,
                "removed_connections": 0,
                "modified_connections": 0,
                "error": str(e)
            }
    
    async def _execute_anomaly_detection(
        self,
        cluster_id: int,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute anomaly detection analysis
        
        Uses timeseries-query service to:
        1. Query time-series data from ClickHouse
        2. Apply statistical analysis
        3. Identify anomalous patterns
        """
        logger.info(f"Executing anomaly detection for cluster {cluster_id}")
        
        ts_client = get_timeseries_client()
        
        try:
            # Get event statistics
            stats = await ts_client.get_event_stats(cluster_id=cluster_id)
            event_counts = stats.get("event_counts", {})
            
            # Get security events (potential anomalies)
            security_data = await ts_client.get_security_events(
                cluster_id=cluster_id,
                limit=500
            )
            security_events = security_data.get("events", [])
            
            # Analyze for anomalies
            anomalies = []
            anomaly_types = set()
            
            # Check for denied security events
            denied_events = [e for e in security_events if e.get("verdict") == "denied"]
            if denied_events:
                anomalies.extend([
                    {
                        "type": "security_denied",
                        "severity": "high",
                        "details": e
                    }
                    for e in denied_events[:10]  # Limit to 10
                ])
                anomaly_types.add("security_denied")
            
            # Check for unusual event distributions
            total_events = stats.get("total_events", 0)
            if total_events > 0:
                # OOM events are always anomalies
                oom_count = event_counts.get("oom_event", 0)
                if oom_count > 0:
                    anomalies.append({
                        "type": "oom_kills",
                        "severity": "high",
                        "count": oom_count
                    })
                    anomaly_types.add("oom_kills")
                
                # High security event ratio could be anomalous
                security_count = event_counts.get("security_event", 0)
                if security_count > total_events * 0.1:  # >10% security events
                    anomalies.append({
                        "type": "high_security_events",
                        "severity": "medium",
                        "count": security_count,
                        "percentage": round(security_count / total_events * 100, 2)
                    })
                    anomaly_types.add("high_security_events")
            
            # Categorize by severity
            high_severity = len([a for a in anomalies if a.get("severity") == "high"])
            medium_severity = len([a for a in anomalies if a.get("severity") == "medium"])
            low_severity = len([a for a in anomalies if a.get("severity") == "low"])
            
            logger.info(f"✅ Anomaly detection completed: {len(anomalies)} anomalies found")
            
            return {
                "total_anomalies": len(anomalies),
                "high_severity": high_severity,
                "medium_severity": medium_severity,
                "low_severity": low_severity,
                "anomaly_types": list(anomaly_types),
                "anomalies": anomalies[:20],  # Return top 20
                "total_events_analyzed": total_events
            }
            
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return {
                "total_anomalies": 0,
                "high_severity": 0,
                "medium_severity": 0,
                "low_severity": 0,
                "anomaly_types": [],
                "error": str(e)
            }
    
    async def _execute_baseline_creation(
        self,
        cluster_id: int,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute baseline creation
        
        Uses graph-query + timeseries-query services to:
        1. Capture current state as baseline
        2. Store in database (TODO: implement storage)
        3. Calculate baseline metrics
        """
        logger.info(f"Executing baseline creation for cluster {cluster_id}")
        
        graph_client = get_graph_client()
        ts_client = get_timeseries_client()
        
        try:
            # Get current graph state
            graph = await graph_client.get_dependency_graph(cluster_id=cluster_id)
            
            # Get event statistics
            stats = await ts_client.get_event_stats(cluster_id=cluster_id)
            
            workload_count = graph.get("total_nodes", 0)
            connection_count = graph.get("total_edges", 0)
            
            # TODO: Store baseline in database
            # For now, generate a baseline ID and return metrics
            baseline_id = int(datetime.utcnow().timestamp())
            
            logger.info(f"✅ Baseline created: {workload_count} workloads, {connection_count} connections")
            
            return {
                "baseline_id": baseline_id,
                "workload_count": workload_count,
                "connection_count": connection_count,
                "total_events": stats.get("total_events", 0),
                "event_distribution": stats.get("event_counts", {}),
                "baseline_date": datetime.utcnow().isoformat(),
                "namespaces": [n.get("namespace") for n in stats.get("top_namespaces", [])]
            }
            
        except Exception as e:
            logger.error(f"Baseline creation failed: {e}")
            return {
                "baseline_id": 0,
                "workload_count": 0,
                "connection_count": 0,
                "baseline_date": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    async def _execute_risk_assessment(
        self,
        cluster_id: int,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute risk assessment
        
        Uses graph-query + timeseries-query services to:
        1. Analyze security posture
        2. Check for risky configurations
        3. Calculate risk scores
        """
        logger.info(f"Executing risk assessment for cluster {cluster_id}")
        
        graph_client = get_graph_client()
        ts_client = get_timeseries_client()
        
        try:
            # Get graph for topology analysis
            graph = await graph_client.get_dependency_graph(cluster_id=cluster_id)
            
            # Get security events
            security_data = await ts_client.get_security_events(
                cluster_id=cluster_id,
                limit=1000
            )
            security_events = security_data.get("events", [])
            
            # Get event statistics
            stats = await ts_client.get_event_stats(cluster_id=cluster_id)
            event_counts = stats.get("event_counts", {})
            
            # Risk factors analysis
            risk_factors = []
            risk_scores = []
            
            # 1. Cross-namespace communications
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            
            node_namespaces = {n.get("id"): n.get("namespace") for n in nodes}
            cross_ns_edges = [
                e for e in edges
                if node_namespaces.get(e.get("source_id")) != node_namespaces.get(e.get("target_id"))
            ]
            if len(cross_ns_edges) > len(edges) * 0.2:  # >20% cross-namespace
                risk_factors.append("high_cross_namespace_traffic")
                risk_scores.append(0.3)
            
            # 2. Denied security events
            denied_events = [e for e in security_events if e.get("verdict") == "denied"]
            if denied_events:
                risk_factors.append("security_denials")
                risk_scores.append(min(len(denied_events) * 0.1, 0.4))
            
            # 3. OOM events indicate resource issues
            oom_count = event_counts.get("oom_event", 0)
            if oom_count > 0:
                risk_factors.append("oom_events")
                risk_scores.append(min(oom_count * 0.05, 0.3))
            
            # 4. Privilege escalation attempts
            priv_escalation = [
                e for e in security_events
                if "CAP_" in str(e.get("capability", ""))
                and e.get("verdict") == "denied"
            ]
            if priv_escalation:
                risk_factors.append("privilege_escalation_attempts")
                risk_scores.append(0.4)
            
            # Calculate overall risk score (0-100)
            overall_risk = min(sum(risk_scores) * 100, 100) if risk_scores else 10
            
            # Categorize workloads by risk
            total_workloads = len(nodes)
            high_risk = int(total_workloads * 0.1) if "privilege_escalation_attempts" in risk_factors else 0
            medium_risk = int(total_workloads * 0.3) if len(risk_factors) > 1 else 0
            low_risk = total_workloads - high_risk - medium_risk
            
            logger.info(f"✅ Risk assessment completed: score {overall_risk:.0f}/100")
            
            return {
                "overall_risk_score": int(overall_risk),
                "high_risk_workloads": high_risk,
                "medium_risk_workloads": medium_risk,
                "low_risk_workloads": low_risk,
                "risk_factors": risk_factors,
                "total_workloads": total_workloads,
                "security_events_analyzed": len(security_events),
                "denied_events": len(denied_events)
            }
            
        except Exception as e:
            logger.error(f"Risk assessment failed: {e}")
            return {
                "overall_risk_score": 0,
                "high_risk_workloads": 0,
                "medium_risk_workloads": 0,
                "low_risk_workloads": 0,
                "risk_factors": [],
                "error": str(e)
            }

