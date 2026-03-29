import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// Types
export interface WorkloadInfo {
  id: string;
  name: string;
  kind: string;
  namespace: string;
  cluster_id?: string;
}

export interface CommunicationEdge {
  source: WorkloadInfo;
  destination: WorkloadInfo;
  protocol: string;
  port: number;
  request_count: number;
  bytes_transferred: number;
  avg_latency_ms: number;
  risk_level?: string;
  risk_score: number;
  first_seen?: string;
  last_seen?: string;
}

export interface CommunicationsResponse {
  communications: CommunicationEdge[];
  total: number;
  analysis_id?: number;
}

export interface DependencyNode {
  id: string;
  name: string;
  kind: string;
  namespace: string;
  cluster_id: string;
  cluster_name?: string;  // Cluster display name for multi-cluster visibility
  status: string;
  labels: Record<string, string>;
  ip?: string;
  node?: string;
  owner_kind?: string;  // Deployment, StatefulSet, DaemonSet, etc.
  owner_name?: string;  // Name of the owner resource
  // Extended metadata
  pod_uid?: string;
  host_ip?: string;
  container?: string;
  image?: string;
  service_account?: string;
  phase?: string;  // Running, Pending, etc.
  // Network classification for visualization grouping
  network_type?: string;  // Internal-Network, External-Network, Pod-Network, etc.
  resolution_source?: string;  // pod, service, node, dns, cidr, unknown
  is_external?: boolean;  // Convenience flag for external endpoints
}

export interface DependencyEdge {
  source_id: string;
  target_id: string;
  edge_type: string;
  protocol?: string;      // L4 protocol (TCP, UDP)
  app_protocol?: string;  // L7 application protocol (GRPC, HTTP, HTTPS, etc.)
  port?: number;
  request_count: number;
  error_count?: number;
  retransmit_count?: number;
  last_error_type?: string;  // CONNECTION_RESET, CONNECTION_REFUSED, RETRANSMIT, etc.
}

export interface DependencyGraphResponse {
  nodes: DependencyNode[];
  edges: DependencyEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface CommunicationStats {
  total_communications: number;
  total_request_count: number;
  total_bytes_transferred: number;
  // Legacy error fields (backward compatible)
  total_errors?: number;
  total_retransmits?: number;
  errors_by_type?: Record<string, number>;
  // New categorized error fields
  total_critical?: number;
  total_warnings?: number;
  critical_by_type?: Record<string, number>;
  warnings_by_type?: Record<string, number>;
  error_health_status?: 'healthy' | 'good' | 'warning' | 'degraded' | 'critical';
  // Other stats
  unique_namespaces: number;
  protocol_distribution: Record<string, number>;
  risk_distribution: Record<string, number>;
  cluster_id: number;
  analysis_id?: number;
}

// Categorized error statistics response
// Separates critical errors (real problems) from warnings (normal TCP behavior)
export interface ErrorStats {
  // Total counts
  total_errors: number;
  total_critical: number;
  total_warnings: number;
  // Breakdown by type
  critical_by_type: Record<string, number>;
  warnings_by_type: Record<string, number>;
  // Metrics
  total_flows: number;
  error_rate_percent: number;
  critical_rate_percent: number;
  // Health assessment
  health_status: 'healthy' | 'good' | 'warning' | 'degraded' | 'critical';
  health_message: string;
  // Context
  cluster_id?: number;
  analysis_id?: number;
  namespace?: string;
}

export interface ErrorStatsQueryParams {
  cluster_id?: number;
  analysis_id?: number;
  namespace?: string;
}

export interface CommunicationsQueryParams {
  cluster_id?: number;
  analysis_id?: number;
  namespace?: string;
  source_workload?: string;
  destination_workload?: string;
  protocol?: string;
  limit?: number;
}

export interface DependencyGraphQueryParams {
  cluster_id?: number;  // Optional for multi-cluster analysis (use analysis_id only)
  analysis_id?: number;
  namespace?: string;
  depth?: number;
  start_time?: string;
  end_time?: string;
  search?: string;  // Server-side search (min 3 chars) - filters nodes in Neo4j by name, namespace, or id
}

export const communicationApi = createApi({
  reducerPath: 'communicationApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Communication', 'DependencyGraph'],
  endpoints: (builder) => ({
    // Get communications list
    getCommunications: builder.query<CommunicationsResponse, CommunicationsQueryParams>({
      query: (params) => ({
        url: '/communications',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Communication', id: `cluster-${params.cluster_id}` }
      ],
    }),
    
    // Get dependency graph for visualization
    // Supports server-side search (min 3 chars) to filter nodes in Neo4j
    getDependencyGraph: builder.query<DependencyGraphResponse, DependencyGraphQueryParams>({
      query: ({ cluster_id, analysis_id, namespace, depth = 2, start_time, end_time, search }) => ({
        url: '/communications/graph',
        params: { cluster_id, analysis_id, namespace, depth, start_time, end_time, search },
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'DependencyGraph', id: `cluster-${cluster_id}` }
      ],
    }),
    
    // Get cross-namespace communications
    getCrossNamespaceCommunications: builder.query<CommunicationEdge[], { cluster_id?: number; analysis_id?: number; limit?: number }>({
      query: ({ cluster_id, limit = 50 }) => ({
        url: '/communications/cross-namespace',
        params: { cluster_id, limit },
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Communication', id: `cross-ns-${cluster_id}` }
      ],
    }),
    
    // Get high-risk communications
    getHighRiskCommunications: builder.query<CommunicationEdge[], { cluster_id?: number; analysis_id?: number; risk_threshold?: number; limit?: number }>({
      query: ({ cluster_id, risk_threshold = 0.5, limit = 50 }) => ({
        url: '/communications/high-risk',
        params: { cluster_id, risk_threshold, limit },
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Communication', id: `high-risk-${cluster_id}` }
      ],
    }),
    
    // Get communication statistics
    getCommunicationStats: builder.query<CommunicationStats, { cluster_id?: number; analysis_id?: number }>({
      query: ({ cluster_id, analysis_id }) => ({
        url: '/communications/stats',
        params: { cluster_id, analysis_id },
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Communication', id: `stats-${cluster_id}` }
      ],
    }),
    
    // Get categorized error statistics (NO LIMIT - accurate counts)
    // Separates critical errors (connection failures) from warnings (retransmissions)
    getErrorStats: builder.query<ErrorStats, ErrorStatsQueryParams>({
      query: ({ cluster_id, analysis_id, namespace }) => ({
        url: '/communications/error-stats',
        params: { cluster_id, analysis_id, namespace },
      }),
      providesTags: (result, error, { cluster_id, analysis_id }) => [
        { type: 'Communication', id: `error-stats-${cluster_id}-${analysis_id}` }
      ],
    }),
  }),
});

export const {
  useGetCommunicationsQuery,
  useGetDependencyGraphQuery,
  useGetCrossNamespaceCommunicationsQuery,
  useGetHighRiskCommunicationsQuery,
  useGetCommunicationStatsQuery,
  useGetErrorStatsQuery,
} = communicationApi;

