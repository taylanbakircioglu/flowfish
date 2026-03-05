"""
Network Policy Service - Policy generation and simulation logic
Generates Kubernetes NetworkPolicy manifests based on observed traffic patterns
"""

import structlog
import yaml
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from schemas.simulation import (
    NetworkPolicySpec,
    NetworkPolicyRule,
    NetworkPolicyPeer,
    NetworkPolicyPort,
    LabelSelector,
    IPBlock,
    PolicyType,
    PolicyAction,
    ImpactLevel,
    ImpactCategory,
    DependencyType,
    ChangeType,
    ChangeTypeCharacteristics,
    AffectedConnection,
    AffectedService,
    NetworkPolicyPreviewRequest,
    NetworkPolicyPreviewResponse,
    NetworkPolicyGenerateRequest,
    NetworkPolicyGenerateResponse,
    ImpactSummary,
    NoDependencyInfo,
    SimulationDetails,
    ImpactSimulationResponse,
)

logger = structlog.get_logger(__name__)


class NetworkPolicyService:
    """Service for network policy simulation and generation"""

    def __init__(self, neo4j_service=None):
        """Initialize with optional Neo4j service for graph queries"""
        self.neo4j_service = neo4j_service

    def _get_neo4j_service(self):
        """Lazy load Neo4j service"""
        if self.neo4j_service is None:
            from database.neo4j import neo4j_service
            self.neo4j_service = neo4j_service
        return self.neo4j_service

    # =========================================================================
    # Network Policy Generation
    # =========================================================================

    async def generate_network_policy(
        self,
        request: NetworkPolicyGenerateRequest
    ) -> NetworkPolicyGenerateResponse:
        """
        Generate a NetworkPolicy based on observed traffic patterns.
        Creates a least-privilege policy that allows only observed connections.
        """
        logger.info(
            "Generating network policy",
            cluster_id=request.cluster_id,
            target=f"{request.target_namespace}/{request.target_workload}"
        )

        neo4j = self._get_neo4j_service()

        # Get observed traffic for the target workload
        ingress_sources = []
        egress_destinations = []

        try:
            # Query incoming connections (ingress)
            ingress_data = neo4j.get_workload_incoming_connections(
                cluster_id=request.cluster_id,
                analysis_id=request.analysis_id,
                namespace=request.target_namespace,
                workload_name=request.target_workload
            )
            ingress_sources = ingress_data if ingress_data else []

            # Query outgoing connections (egress)
            egress_data = neo4j.get_workload_outgoing_connections(
                cluster_id=request.cluster_id,
                analysis_id=request.analysis_id,
                namespace=request.target_namespace,
                workload_name=request.target_workload
            )
            egress_destinations = egress_data if egress_data else []

        except Exception as e:
            logger.warning("Failed to query traffic patterns", error=str(e))
            # Continue with empty lists - will generate restrictive policy

        # Build policy specification
        policy_name = f"{request.target_workload}-network-policy"
        
        policy_spec = self._build_policy_spec(
            policy_name=policy_name,
            target_namespace=request.target_namespace,
            target_workload=request.target_workload,
            ingress_sources=ingress_sources,
            egress_destinations=egress_destinations,
            policy_types=request.policy_types,
            include_dns=request.include_dns,
            strict_mode=request.strict_mode
        )

        # Generate YAML
        generated_yaml = self._generate_yaml(policy_spec)

        # Build coverage summary
        coverage_summary = {
            "ingress": {
                "total_sources": len(ingress_sources),
                "namespaces_covered": len(set(s.get("namespace", "") for s in ingress_sources)),
                "ports_covered": len(set(s.get("port", 0) for s in ingress_sources))
            },
            "egress": {
                "total_destinations": len(egress_destinations),
                "namespaces_covered": len(set(d.get("namespace", "") for d in egress_destinations)),
                "external_endpoints": sum(1 for d in egress_destinations if d.get("is_external", False))
            }
        }

        # Generate recommendations
        recommendations = self._generate_recommendations(
            ingress_sources, egress_destinations, request
        )

        return NetworkPolicyGenerateResponse(
            policy_name=policy_name,
            target_workload=request.target_workload,
            target_namespace=request.target_namespace,
            observed_ingress_sources=len(ingress_sources),
            observed_egress_destinations=len(egress_destinations),
            generated_yaml=generated_yaml,
            policy_spec=policy_spec,
            coverage_summary=coverage_summary,
            recommendations=recommendations
        )

    def _build_policy_spec(
        self,
        policy_name: str,
        target_namespace: str,
        target_workload: str,
        ingress_sources: List[Dict],
        egress_destinations: List[Dict],
        policy_types: List[PolicyType],
        include_dns: bool,
        strict_mode: bool
    ) -> NetworkPolicySpec:
        """Build NetworkPolicySpec from observed traffic"""

        # Target pod selector
        target_selector = LabelSelector(
            match_labels={"app": target_workload}
        )

        # Determine policy types
        active_types = []
        if PolicyType.BOTH in policy_types:
            active_types = [PolicyType.INGRESS, PolicyType.EGRESS]
        else:
            active_types = policy_types

        # Build ingress rules
        ingress_rules = None
        if PolicyType.INGRESS in active_types or PolicyType.BOTH in policy_types:
            ingress_rules = self._build_ingress_rules(ingress_sources, strict_mode)

        # Build egress rules
        egress_rules = None
        if PolicyType.EGRESS in active_types or PolicyType.BOTH in policy_types:
            egress_rules = self._build_egress_rules(
                egress_destinations, include_dns, strict_mode
            )

        return NetworkPolicySpec(
            policy_name=policy_name,
            target_namespace=target_namespace,
            target_pod_selector=target_selector,
            policy_types=active_types,
            ingress_rules=ingress_rules,
            egress_rules=egress_rules
        )

    def _build_ingress_rules(
        self,
        sources: List[Dict],
        strict_mode: bool
    ) -> List[NetworkPolicyRule]:
        """Build ingress rules from observed sources"""
        rules = []

        # Group sources by namespace
        by_namespace: Dict[str, List[Dict]] = {}
        for source in sources:
            ns = source.get("namespace", "default")
            if ns not in by_namespace:
                by_namespace[ns] = []
            by_namespace[ns].append(source)

        for namespace, ns_sources in by_namespace.items():
            # Collect unique ports
            ports = list(set(
                (s.get("protocol", "TCP"), s.get("port", 0))
                for s in ns_sources if s.get("port")
            ))

            # Build peer
            peer = NetworkPolicyPeer(
                namespace_selector=LabelSelector(
                    match_labels={"kubernetes.io/metadata.name": namespace}
                )
            )

            # Build port specs
            port_specs = [
                NetworkPolicyPort(protocol=proto, port=port)
                for proto, port in ports if port > 0
            ]

            rules.append(NetworkPolicyRule(
                rule_type=PolicyType.INGRESS,
                action=PolicyAction.ALLOW,
                peers=[peer],
                ports=port_specs if port_specs else None
            ))

        return rules if rules else None

    def _build_egress_rules(
        self,
        destinations: List[Dict],
        include_dns: bool,
        strict_mode: bool
    ) -> List[NetworkPolicyRule]:
        """Build egress rules from observed destinations"""
        rules = []

        # Add DNS rule if requested
        if include_dns:
            rules.append(NetworkPolicyRule(
                rule_type=PolicyType.EGRESS,
                action=PolicyAction.ALLOW,
                peers=[NetworkPolicyPeer(
                    namespace_selector=LabelSelector(
                        match_labels={"kubernetes.io/metadata.name": "kube-system"}
                    ),
                    pod_selector=LabelSelector(
                        match_labels={"k8s-app": "kube-dns"}
                    )
                )],
                ports=[NetworkPolicyPort(protocol="UDP", port=53)]
            ))

        # Group destinations by namespace (for internal) or by IP (for external)
        internal_by_ns: Dict[str, List[Dict]] = {}
        external_ips: List[Dict] = []

        for dest in destinations:
            if dest.get("is_external", False):
                external_ips.append(dest)
            else:
                ns = dest.get("namespace", "default")
                if ns not in internal_by_ns:
                    internal_by_ns[ns] = []
                internal_by_ns[ns].append(dest)

        # Internal destinations
        for namespace, ns_dests in internal_by_ns.items():
            ports = list(set(
                (d.get("protocol", "TCP"), d.get("port", 0))
                for d in ns_dests if d.get("port")
            ))

            peer = NetworkPolicyPeer(
                namespace_selector=LabelSelector(
                    match_labels={"kubernetes.io/metadata.name": namespace}
                )
            )

            port_specs = [
                NetworkPolicyPort(protocol=proto, port=port)
                for proto, port in ports if port > 0
            ]

            rules.append(NetworkPolicyRule(
                rule_type=PolicyType.EGRESS,
                action=PolicyAction.ALLOW,
                peers=[peer],
                ports=port_specs if port_specs else None
            ))

        # External destinations (IP blocks)
        for ext in external_ips:
            ip = ext.get("ip", "")
            port = ext.get("port", 0)
            protocol = ext.get("protocol", "TCP")

            if ip:
                # Create /32 CIDR for specific IP
                cidr = f"{ip}/32" if "/" not in ip else ip
                
                rules.append(NetworkPolicyRule(
                    rule_type=PolicyType.EGRESS,
                    action=PolicyAction.ALLOW,
                    peers=[NetworkPolicyPeer(
                        ip_block=IPBlock(cidr=cidr)
                    )],
                    ports=[NetworkPolicyPort(protocol=protocol, port=port)] if port else None
                ))

        return rules if rules else None

    def _generate_yaml(self, policy_spec: NetworkPolicySpec) -> str:
        """Generate Kubernetes NetworkPolicy YAML from spec"""
        
        policy = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": policy_spec.policy_name,
                "namespace": policy_spec.target_namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "flowfish",
                    "flowfish.io/generated": "true"
                }
            },
            "spec": {
                "podSelector": self._selector_to_dict(policy_spec.target_pod_selector),
                "policyTypes": [pt.value.capitalize() for pt in policy_spec.policy_types]
            }
        }

        # Add ingress rules
        if policy_spec.ingress_rules:
            policy["spec"]["ingress"] = []
            for rule in policy_spec.ingress_rules:
                ingress_rule = {}
                if rule.peers:
                    ingress_rule["from"] = [self._peer_to_dict(p) for p in rule.peers]
                if rule.ports:
                    ingress_rule["ports"] = [self._port_to_dict(p) for p in rule.ports]
                if ingress_rule:
                    policy["spec"]["ingress"].append(ingress_rule)

        # Add egress rules
        if policy_spec.egress_rules:
            policy["spec"]["egress"] = []
            for rule in policy_spec.egress_rules:
                egress_rule = {}
                if rule.peers:
                    egress_rule["to"] = [self._peer_to_dict(p) for p in rule.peers]
                if rule.ports:
                    egress_rule["ports"] = [self._port_to_dict(p) for p in rule.ports]
                if egress_rule:
                    policy["spec"]["egress"].append(egress_rule)

        return yaml.dump(policy, default_flow_style=False, sort_keys=False)

    def _selector_to_dict(self, selector: Optional[LabelSelector]) -> Dict:
        """Convert LabelSelector to dict"""
        if not selector:
            return {}
        result = {}
        if selector.match_labels:
            result["matchLabels"] = selector.match_labels
        if selector.match_expressions:
            result["matchExpressions"] = selector.match_expressions
        return result

    def _peer_to_dict(self, peer: NetworkPolicyPeer) -> Dict:
        """Convert NetworkPolicyPeer to dict"""
        result = {}
        if peer.namespace_selector:
            result["namespaceSelector"] = self._selector_to_dict(peer.namespace_selector)
        if peer.pod_selector:
            result["podSelector"] = self._selector_to_dict(peer.pod_selector)
        if peer.ip_block:
            ip_block_dict = {"cidr": peer.ip_block.cidr}
            if peer.ip_block.except_cidrs:
                ip_block_dict["except"] = peer.ip_block.except_cidrs
            result["ipBlock"] = ip_block_dict
        return result

    def _port_to_dict(self, port: NetworkPolicyPort) -> Dict:
        """Convert NetworkPolicyPort to dict"""
        result = {"protocol": port.protocol}
        if port.port:
            result["port"] = port.port
        if port.end_port:
            result["endPort"] = port.end_port
        return result

    def _generate_recommendations(
        self,
        ingress_sources: List[Dict],
        egress_destinations: List[Dict],
        request: NetworkPolicyGenerateRequest
    ) -> List[str]:
        """Generate recommendations based on traffic analysis"""
        recommendations = []

        # Check for cross-namespace traffic
        cross_ns_ingress = [s for s in ingress_sources if s.get("namespace") != request.target_namespace]
        if cross_ns_ingress:
            recommendations.append(
                f"Cross-namespace ingress detected from {len(cross_ns_ingress)} source(s). "
                "Ensure these connections are intentional."
            )

        # Check for external egress
        external_egress = [d for d in egress_destinations if d.get("is_external")]
        if external_egress:
            recommendations.append(
                f"External egress to {len(external_egress)} endpoint(s) detected. "
                "Consider using FQDN policies if available."
            )

        # Check for wide port ranges
        all_ports = set()
        for s in ingress_sources:
            if s.get("port"):
                all_ports.add(s["port"])
        for d in egress_destinations:
            if d.get("port"):
                all_ports.add(d["port"])

        if len(all_ports) > 10:
            recommendations.append(
                "Many different ports observed. Consider consolidating services "
                "or using port ranges where appropriate."
            )

        # Strict mode recommendation
        if not request.strict_mode:
            recommendations.append(
                "Policy generated in permissive mode. Consider enabling strict_mode "
                "for deny-all default behavior in production."
            )

        return recommendations

    # =========================================================================
    # Network Policy Preview (Impact Analysis)
    # =========================================================================

    async def preview_network_policy_impact(
        self,
        request: NetworkPolicyPreviewRequest
    ) -> NetworkPolicyPreviewResponse:
        """
        Preview the impact of applying a network policy.
        Shows which existing connections would be blocked.
        """
        logger.info(
            "Previewing network policy impact",
            cluster_id=request.cluster_id,
            target=f"{request.target_namespace}/{request.target_workload}"
        )

        neo4j = self._get_neo4j_service()

        # Get all current connections for the target
        all_connections = []
        try:
            # Get incoming connections
            incoming = neo4j.get_workload_incoming_connections(
                cluster_id=request.cluster_id,
                analysis_id=request.analysis_id,
                namespace=request.target_namespace,
                workload_name=request.target_workload
            ) or []

            # Get outgoing connections
            outgoing = neo4j.get_workload_outgoing_connections(
                cluster_id=request.cluster_id,
                analysis_id=request.analysis_id,
                namespace=request.target_namespace,
                workload_name=request.target_workload
            ) or []

            all_connections = incoming + outgoing

        except Exception as e:
            logger.warning("Failed to query connections", error=str(e))

        # Analyze each connection against the policy
        affected_connections = []
        blocked_count = 0
        allowed_count = 0

        for conn in all_connections:
            is_blocked, rule_match = self._check_connection_against_policy(
                conn, request.policy_spec
            )

            affected_conn = AffectedConnection(
                source_name=conn.get("source_name", "unknown"),
                source_namespace=conn.get("source_namespace", "unknown"),
                source_kind=conn.get("source_kind", "Pod"),
                target_name=conn.get("target_name", request.target_workload),
                target_namespace=conn.get("target_namespace", request.target_namespace),
                target_kind=conn.get("target_kind", "Pod"),
                protocol=conn.get("protocol", "TCP"),
                port=conn.get("port", 0),
                request_count=conn.get("request_count", 0),
                would_be_blocked=is_blocked,
                rule_match=rule_match
            )
            affected_connections.append(affected_conn)

            if is_blocked:
                blocked_count += 1
            else:
                allowed_count += 1

        # Generate warnings
        warnings = []
        if blocked_count > 0:
            warnings.append(
                f"This policy would block {blocked_count} existing connection(s). "
                "Review the affected connections before applying."
            )

        # Generate YAML
        generated_yaml = self._generate_yaml(request.policy_spec)

        # Generate recommendations
        recommendations = []
        if blocked_count == 0 and allowed_count == 0:
            recommendations.append(
                "No existing connections found. The policy may be applied safely, "
                "but ensure the target workload has been observed."
            )
        elif blocked_count > allowed_count:
            recommendations.append(
                "More connections would be blocked than allowed. "
                "Consider reviewing the policy rules."
            )

        return NetworkPolicyPreviewResponse(
            policy_name=request.policy_spec.policy_name,
            target_workload=request.target_workload,
            target_namespace=request.target_namespace,
            total_connections=len(all_connections),
            blocked_connections=blocked_count,
            allowed_connections=allowed_count,
            affected_connections=affected_connections,
            generated_yaml=generated_yaml,
            warnings=warnings,
            recommendations=recommendations
        )

    def _check_connection_against_policy(
        self,
        connection: Dict,
        policy_spec: NetworkPolicySpec
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a connection would be blocked by the policy.
        Returns (is_blocked, matching_rule_description)
        """
        # Determine if this is ingress or egress
        conn_namespace = connection.get("namespace", "")
        conn_port = connection.get("port", 0)
        is_incoming = connection.get("direction", "outgoing") == "incoming"

        # Check against appropriate rules
        if is_incoming and policy_spec.ingress_rules:
            for rule in policy_spec.ingress_rules:
                if self._connection_matches_rule(connection, rule, is_ingress=True):
                    return (False, f"Allowed by ingress rule for {conn_namespace}")
            return (True, "No matching ingress rule - blocked by default")

        elif not is_incoming and policy_spec.egress_rules:
            for rule in policy_spec.egress_rules:
                if self._connection_matches_rule(connection, rule, is_ingress=False):
                    return (False, f"Allowed by egress rule for {conn_namespace}:{conn_port}")
            return (True, "No matching egress rule - blocked by default")

        # If no rules defined for this direction, allow by default
        return (False, "No policy rules for this direction")

    def _connection_matches_rule(
        self,
        connection: Dict,
        rule: NetworkPolicyRule,
        is_ingress: bool
    ) -> bool:
        """Check if a connection matches a specific rule"""
        conn_namespace = connection.get("namespace", "")
        conn_port = connection.get("port", 0)
        conn_protocol = connection.get("protocol", "TCP")

        # Check port match
        if rule.ports:
            port_match = any(
                (p.port is None or p.port == conn_port) and
                (p.protocol == conn_protocol)
                for p in rule.ports
            )
            if not port_match:
                return False

        # Check peer match
        if rule.peers:
            peer_match = any(
                self._namespace_matches_peer(conn_namespace, peer)
                for peer in rule.peers
            )
            if not peer_match:
                return False

        return True

    def _namespace_matches_peer(self, namespace: str, peer: NetworkPolicyPeer) -> bool:
        """Check if namespace matches peer selector"""
        if peer.namespace_selector and peer.namespace_selector.match_labels:
            # Check if namespace label matches
            ns_label = peer.namespace_selector.match_labels.get("kubernetes.io/metadata.name")
            if ns_label and ns_label == namespace:
                return True
            # Also check generic name label
            name_label = peer.namespace_selector.match_labels.get("name")
            if name_label and name_label == namespace:
                return True
        
        # IP block matching would require IP lookup
        if peer.ip_block:
            # For now, assume external IPs don't match internal namespaces
            return False

        return False

    # =========================================================================
    # Impact Simulation Helpers - Change Type Aware
    # =========================================================================

    def calculate_impact_for_change_type(
        self,
        change_type: ChangeType,
        dependency_type: DependencyType,
        request_count: int,
        is_critical_path: bool = False
    ) -> Tuple[ImpactLevel, ImpactCategory, str, List[str]]:
        """
        Calculate impact based on BOTH change type AND dependency characteristics.
        
        IMPORTANT: Impact Level and Category must be consistent:
        - SERVICE_OUTAGE → Always HIGH (outage = critical by definition)
        - CONNECTIVITY_LOSS → Always HIGH
        - CASCADE_RISK → MEDIUM (potential impact, not immediate outage)
        - PERFORMANCE_DEGRADATION → MEDIUM or LOW
        
        Returns:
            Tuple of (impact_level, impact_category, impact_description, risk_factors)
        """
        chars = ChangeTypeCharacteristics.get(change_type)
        
        # Determine impact level and category based on dependency type
        if dependency_type == DependencyType.DIRECT:
            if not chars["affects_direct"]:
                return (ImpactLevel.NONE, chars["primary_impact"], 
                       "Direct connections not affected by this change type", [])
            base_impact = chars["direct_impact_level"]
            impact_category = chars["primary_impact"]
        else:  # INDIRECT
            if not chars["affects_indirect"]:
                return (ImpactLevel.NONE, chars["primary_impact"],
                       "Indirect connections not affected by this change type", [])
            base_impact = chars["indirect_impact_level"]
            # Use indirect-specific category if defined, otherwise use primary
            impact_category = chars.get("indirect_impact_category", chars["primary_impact"])
        
        # Adjust impact based on traffic volume and criticality
        final_impact = base_impact
        
        # CONSISTENCY CHECK: Ensure Impact Level matches Category
        # SERVICE_OUTAGE and CONNECTIVITY_LOSS must ALWAYS be HIGH
        if impact_category in [ImpactCategory.SERVICE_OUTAGE, ImpactCategory.CONNECTIVITY_LOSS]:
            final_impact = ImpactLevel.HIGH
        # CASCADE_RISK is MEDIUM by definition (potential, not actual outage)
        elif impact_category == ImpactCategory.CASCADE_RISK:
            # Can escalate to HIGH only if critical path AND high traffic
            if is_critical_path and request_count > 1000:
                final_impact = ImpactLevel.HIGH
            else:
                final_impact = ImpactLevel.MEDIUM
        # PERFORMANCE_DEGRADATION - adjust based on traffic
        elif impact_category == ImpactCategory.PERFORMANCE_DEGRADATION:
            if request_count > 1000 or is_critical_path:
                final_impact = ImpactLevel.MEDIUM
            elif request_count < 10:
                final_impact = ImpactLevel.LOW
            else:
                final_impact = ImpactLevel.MEDIUM
        # Other categories - use base with adjustments
        else:
            if base_impact == ImpactLevel.MEDIUM and (request_count > 1000 or is_critical_path):
                final_impact = ImpactLevel.HIGH
            elif base_impact == ImpactLevel.MEDIUM and request_count < 10:
                final_impact = ImpactLevel.LOW
        
        # Generate impact description based on change type
        impact_description = self._generate_impact_description(
            change_type, chars, dependency_type, request_count
        )
        
        return (final_impact, impact_category, impact_description, chars["risk_factors"])

    def _generate_impact_description(
        self,
        change_type: ChangeType,
        chars: dict,
        dependency_type: DependencyType,
        request_count: int
    ) -> str:
        """Generate human-readable impact description"""
        
        descriptions = {
            (ChangeType.DELETE, DependencyType.DIRECT): 
                f"Service will lose connection immediately. {request_count} requests will fail.",
            (ChangeType.DELETE, DependencyType.INDIRECT):
                f"May experience cascading failures from upstream service loss.",
            
            (ChangeType.SCALE_DOWN, DependencyType.DIRECT):
                f"Connection will fail until service is scaled back up. Queue may build up.",
            (ChangeType.SCALE_DOWN, DependencyType.INDIRECT):
                f"May experience degraded performance from upstream capacity loss.",
            
            (ChangeType.NETWORK_ISOLATE, DependencyType.DIRECT):
                f"Network traffic will be blocked. Service running but unreachable.",
            (ChangeType.NETWORK_ISOLATE, DependencyType.INDIRECT):
                f"Indirect path unaffected - only direct connections blocked.",
            
            (ChangeType.RESOURCE_CHANGE, DependencyType.DIRECT):
                f"May experience slower responses or timeouts. No complete outage expected.",
            (ChangeType.RESOURCE_CHANGE, DependencyType.INDIRECT):
                f"Minimal impact - resource changes don't cascade to indirect dependencies.",
            
            (ChangeType.PORT_CHANGE, DependencyType.DIRECT):
                f"Connection refused until client configuration updated to new port.",
            (ChangeType.PORT_CHANGE, DependencyType.INDIRECT):
                f"No impact - port changes only affect direct connections.",
            
            (ChangeType.CONFIG_CHANGE, DependencyType.DIRECT):
                f"Behavior may change. Watch for feature flag or environment-dependent logic.",
            (ChangeType.CONFIG_CHANGE, DependencyType.INDIRECT):
                f"Minimal impact unless config affects API contract.",
            
            (ChangeType.IMAGE_UPDATE, DependencyType.DIRECT):
                f"Brief disruption during rollout. Check API compatibility.",
            (ChangeType.IMAGE_UPDATE, DependencyType.INDIRECT):
                f"May be affected if API contract changes in new version.",
            
            (ChangeType.NETWORK_POLICY_APPLY, DependencyType.DIRECT):
                f"Traffic may be blocked if not in allowed list. Verify policy rules.",
            (ChangeType.NETWORK_POLICY_APPLY, DependencyType.INDIRECT):
                f"No impact - network policies only affect direct connections.",
            
            (ChangeType.NETWORK_POLICY_REMOVE, DependencyType.DIRECT):
                f"No connectivity impact. Security posture change only.",
            (ChangeType.NETWORK_POLICY_REMOVE, DependencyType.INDIRECT):
                f"No impact on connectivity or functionality.",
        }
        
        key = (change_type, dependency_type)
        return descriptions.get(key, chars["description"])

    def calculate_impact_level(
        self,
        dependency_type: DependencyType,
        request_count: int,
        is_critical_path: bool = False,
        change_type: ChangeType = None
    ) -> ImpactLevel:
        """
        Calculate impact level - now change-type aware.
        Kept for backward compatibility, delegates to new method.
        """
        if change_type:
            impact, _, _, _ = self.calculate_impact_for_change_type(
                change_type, dependency_type, request_count, is_critical_path
            )
            return impact
        
        # Legacy behavior for backward compatibility
        if dependency_type == DependencyType.DIRECT:
            if is_critical_path or request_count > 1000:
                return ImpactLevel.HIGH
            elif request_count > 100:
                return ImpactLevel.MEDIUM
            else:
                return ImpactLevel.LOW
        else:
            if request_count > 1000:
                return ImpactLevel.MEDIUM
            else:
                return ImpactLevel.LOW

    def get_recommendation(self, impact: ImpactLevel, change_type: str) -> str:
        """Get recommendation based on impact and change type"""
        
        # Change-type specific recommendations
        change_specific = {
            "delete": {
                ImpactLevel.HIGH: "⚠️ CRITICAL: Add fallback service or circuit breaker. Consider blue-green deployment.",
                ImpactLevel.MEDIUM: "Monitor for cascading failures. Have rollback plan ready.",
                ImpactLevel.LOW: "Low traffic service - safe to proceed with monitoring.",
            },
            "scale_down": {
                ImpactLevel.HIGH: "Implement graceful degradation. Drain connections before scaling.",
                ImpactLevel.MEDIUM: "Verify auto-scaling policies. Consider gradual scale-down.",
                ImpactLevel.LOW: "Safe to proceed - ensure quick scale-up capability.",
            },
            "network_isolate": {
                ImpactLevel.HIGH: "Test policy in audit mode first. Verify all required paths are allowed.",
                ImpactLevel.MEDIUM: "Review network policy rules for completeness.",
                ImpactLevel.LOW: "Safe to apply - minimal traffic affected.",
            },
            "resource_change": {
                ImpactLevel.HIGH: "⚡ PERFORMANCE: May cause latency spikes. Consider gradual resource adjustment.",
                ImpactLevel.MEDIUM: "Monitor response times and error rates after change.",
                ImpactLevel.LOW: "Safe to proceed - monitor for OOM events.",
            },
            "port_change": {
                ImpactLevel.HIGH: "🔌 Update all client configurations before changing port.",
                ImpactLevel.MEDIUM: "Coordinate port change with dependent teams.",
                ImpactLevel.LOW: "Update service discovery and client configs.",
            },
            "config_change": {
                ImpactLevel.HIGH: "🔧 Test in staging first. Watch for environment-specific behavior.",
                ImpactLevel.MEDIUM: "Validate config propagation. Check for cached values.",
                ImpactLevel.LOW: "Safe to proceed - monitor for unexpected behavior.",
            },
            "image_update": {
                ImpactLevel.HIGH: "📦 Check API compatibility. Use canary deployment if possible.",
                ImpactLevel.MEDIUM: "Review changelog for breaking changes. Monitor rollout.",
                ImpactLevel.LOW: "Safe to proceed - have rollback ready.",
            },
            "network_policy_apply": {
                ImpactLevel.HIGH: "🛡️ Policy may block traffic. Test in audit mode first.",
                ImpactLevel.MEDIUM: "Review policy rules match observed traffic patterns.",
                ImpactLevel.LOW: "Safe to apply - verify expected connections allowed.",
            },
            "network_policy_remove": {
                ImpactLevel.HIGH: "🔓 Security impact only - no connectivity disruption.",
                ImpactLevel.MEDIUM: "Review security implications of removing policy.",
                ImpactLevel.LOW: "Safe to proceed - update security documentation.",
            },
        }
        
        if change_type in change_specific:
            return change_specific[change_type].get(
                impact, 
                "Review impact carefully before proceeding."
            )
        
        # Generic fallback
        generic = {
            ImpactLevel.HIGH: "Coordinate with dependent teams before proceeding.",
            ImpactLevel.MEDIUM: "Review connection retry logic in clients.",
            ImpactLevel.LOW: "No immediate action required, monitor after change.",
        }
        return generic.get(impact, "Review impact carefully.")

    def determine_no_dependency_scenario(
        self,
        graph_matches: int,
        has_external_connections: bool,
        target_kind: str
    ) -> NoDependencyInfo:
        """Determine the appropriate no-dependency scenario"""
        
        if graph_matches == 0:
            return NoDependencyInfo(
                scenario="NO_GRAPH_MATCH",
                title="Target Not Found in Dependency Graph",
                description="This resource was not observed communicating during the analysis period.",
                suggestions=[
                    "Verify the analysis is still running or has captured data",
                    "Check if the target has any network activity",
                    "Consider extending the analysis duration",
                    "Ensure the target workload is in the analysis scope"
                ],
                alert_type="info"
            )
        elif has_external_connections:
            return NoDependencyInfo(
                scenario="EXTERNAL_ONLY",
                title="External Connections Only",
                description="This target only communicates with external endpoints outside the cluster.",
                suggestions=[
                    "External services may still be affected by this change",
                    "Consider DNS resolution dependencies",
                    "Review egress network policies",
                    "Check for external service health monitoring"
                ],
                alert_type="warning"
            )
        else:
            return NoDependencyInfo(
                scenario="ISOLATED_WORKLOAD",
                title="Isolated Workload Detected",
                description="This workload has no incoming or outgoing connections to other cluster resources.",
                suggestions=[
                    "This may be intentional (batch jobs, init containers, cron jobs)",
                    "Verify network policies are not blocking traffic",
                    "Check if the workload is functioning correctly",
                    "Review pod logs for connection errors"
                ],
                alert_type="success"
            )


# Singleton instance
_network_policy_service: Optional[NetworkPolicyService] = None


def get_network_policy_service() -> NetworkPolicyService:
    """Get or create NetworkPolicyService singleton"""
    global _network_policy_service
    if _network_policy_service is None:
        _network_policy_service = NetworkPolicyService()
    return _network_policy_service

