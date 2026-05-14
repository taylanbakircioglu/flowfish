/**
 * Shared constants for the L7 Service Map.
 * Network type definitions match L4 Map.tsx NETWORK_TYPE_INFO for consistency.
 */

export const SYSTEM_NAMESPACES = new Set(
  [
    'kube-system',
    'kube-public',
    'kube-node-lease',
    'cattle-system',
    'istio-system',
    'linkerd',
    'openshift',
    'openshift-operator',
    'openshift-monitoring',
    'openshift-operators',
    'gmp-system',
    'gke-system',
  ].map((s) => s.toLowerCase()),
);

// Synthetic namespaces emitted by the backend when an endpoint is best
// described as cluster infrastructure rather than an application workload.
// These are real, legitimate edges (e.g. kubelet readiness/liveness probes,
// OpenShift SDN gateways) but should be visually de-emphasized so operators
// can focus on application-to-application dependencies.
export const INFRASTRUCTURE_NAMESPACES = new Set(
  [
    'cluster-infra',          // Worker / infra node identities (kubelet probes)
    'sdn-infrastructure',     // OpenShift SDN gateway IPs (egress fabric)
  ].map((s) => s.toLowerCase()),
);

// Synthetic namespaces emitted when Beyla / the L7 collector could not
// resolve the endpoint to a real Kubernetes object. These nodes should be
// treated as informational only — they signal an observability gap rather
// than a meaningful dependency. `loopback` is normally dropped upstream
// (collector + timeseries-writer) and is included here as a defense for
// historic data or stale upstream components.
export const UNRESOLVED_NAMESPACES = new Set(
  [
    'unknown',
    'loopback',
  ].map((s) => s.toLowerCase()),
);

export function isSystemNamespace(ns: string): boolean {
  const n = (ns || '').toLowerCase();
  if (SYSTEM_NAMESPACES.has(n)) return true;
  return n.startsWith('kube-') || n.startsWith('openshift-');
}

export function isInfrastructureNamespace(ns: string): boolean {
  return INFRASTRUCTURE_NAMESPACES.has((ns || '').toLowerCase());
}

export function isUnresolvedNamespace(ns: string): boolean {
  return UNRESOLVED_NAMESPACES.has((ns || '').toLowerCase());
}

// Namespaces that should be visually de-emphasized in the Service Map.
// Combines control-plane system namespaces with cluster infrastructure
// (kubelet probes, SDN gateways) and unresolved synthetic namespaces.
export function isSecondaryNamespace(ns: string): boolean {
  return (
    isSystemNamespace(ns) ||
    isInfrastructureNamespace(ns) ||
    isUnresolvedNamespace(ns)
  );
}

export type NamespaceCategory = 'application' | 'system' | 'infrastructure' | 'unresolved';

export function classifyNamespace(ns: string): NamespaceCategory {
  if (isSystemNamespace(ns)) return 'system';
  if (isInfrastructureNamespace(ns)) return 'infrastructure';
  if (isUnresolvedNamespace(ns)) return 'unresolved';
  return 'application';
}

export function statusClass(code: number): '2xx' | '3xx' | '4xx' | '5xx' | null {
  if (code >= 200 && code < 300) return '2xx';
  if (code >= 300 && code < 400) return '3xx';
  if (code >= 400 && code < 500) return '4xx';
  if (code >= 500 && code < 600) return '5xx';
  return null;
}

export function normalizeProtocol(p?: string | null): string {
  return (p || '').toLowerCase();
}

export function healthFromErrorRate(rate: number): 'healthy' | 'warning' | 'critical' {
  if (rate > 0.2) return 'critical';
  if (rate > 0.05) return 'warning';
  return 'healthy';
}

export function healthColor(h: 'healthy' | 'warning' | 'critical'): string {
  if (h === 'critical') return '#ef4444';
  if (h === 'warning') return '#ca8a04';
  return '#22c55e';
}

export function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export const NODE_W = 228;
export const NODE_H = 102;
