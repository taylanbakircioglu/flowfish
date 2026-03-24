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
  annotations: Record<string, string>;
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

// Communication contract (enriched communication details)
export interface CommunicationContract {
  protocol?: string;
  app_protocol?: string;
  port?: number;
  service_type?: string;
  service_category?: string;
  is_critical?: boolean;
  request_count?: number;
  bytes_transferred?: number;
  error_count?: number;
  error_rate_percent?: number;
  retransmit_count?: number;
  avg_latency_ms?: number;
  last_seen?: number;
}

// Dependency health score
export interface DependencyHealthScore {
  score: number;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'critical';
  error_rate_percent: number;
  retransmit_rate_percent: number;
  avg_latency_ms: number;
  risk_factors: string[];
}

// Upstream/Downstream dependency stream types
export interface PodDependencyInfo {
  pod_name: string;
  namespace: string;
  cluster_id?: string;
  ip?: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  owner_kind?: string;
  owner_name?: string;
  phase?: string;
  image?: string;
  container?: string;
  service_account?: string;
  host_ip?: string;
  node?: string;
  hop_count?: number;
  communication?: CommunicationContract;
  health?: DependencyHealthScore;
}

export interface PodDependencyResult {
  upstream: PodDependencyInfo;
  downstream: PodDependencyInfo[];
  callers: PodDependencyInfo[];
}

export interface PodDependencyStreamResponse {
  success: boolean;
  count: number;
  results: PodDependencyResult[];
  error?: string;
}

export interface PodDependencyStreamParams {
  analysis_id?: number;
  cluster_id?: number;
  pod_name?: string;
  namespace?: string;
  owner_name?: string;
  label_key?: string;
  label_value?: string;
  annotation_key?: string;
  annotation_value?: string;
  ip?: string;
  depth?: number;
  format?: 'json' | 'mermaid' | 'dot';
}

// Batch dependency request/response
export interface BatchDependencyServiceItem {
  pod_name?: string;
  namespace?: string;
  owner_name?: string;
  label_key?: string;
  label_value?: string;
  annotation_key?: string;
  annotation_value?: string;
  ip?: string;
}

export interface BatchDependencyRequest {
  analysis_id?: string;
  cluster_id?: string;
  services: BatchDependencyServiceItem[];
  depth?: number;
  include_communication_details?: boolean;
}

export interface BatchDependencyResponse {
  success: boolean;
  service_count: number;
  results: PodDependencyStreamResponse[];
  shared_dependencies: string[];
}

// Dependency diff response
export interface DependencyDiffEntry {
  name: string;
  namespace: string;
  port?: number;
  protocol?: string;
  service_type?: string;
}

export interface DependencyChangedEntry {
  name: string;
  namespace: string;
  change: string;
  before: Record<string, any>;
  after: Record<string, any>;
}

export interface DependencyDiffResponse {
  success: boolean;
  service: string;
  analysis_before: string;
  analysis_after: string;
  added_dependencies: DependencyDiffEntry[];
  removed_dependencies: DependencyDiffEntry[];
  changed_dependencies: DependencyChangedEntry[];
  unchanged_count: number;
  summary: string;
}

export interface DependencyDiffParams {
  analysis_id_before: string;
  analysis_id_after: string;
  pod_name?: string;
  namespace?: string;
  owner_name?: string;
  cluster_id?: number;
}

export interface SuggestedAction {
  priority: string;
  action: string;
  reason: string;
  automatable: boolean;
}

export interface ImpactAssessment {
  risk_score: number;
  risk_level: string;
  blast_radius: number;
  critical_dependencies: string[];
  recommendation: 'proceed' | 'caution' | 'block';
  suggested_actions: SuggestedAction[];
  change_type: string;
}

export interface DependencyImpactResponse {
  success: boolean;
  service: PodDependencyInfo;
  dependencies: {
    downstream: PodDependencyInfo[];
    callers: PodDependencyInfo[];
    downstream_count: number;
    callers_count: number;
  };
  impact_assessment: ImpactAssessment;
}

export interface DependencyImpactParams {
  analysis_id?: number;
  cluster_id?: number;
  pod_name?: string;
  namespace?: string;
  owner_name?: string;
  label_key?: string;
  label_value?: string;
  annotation_key?: string;
  annotation_value?: string;
  ip?: string;
  depth?: number;
  change_type?: string;
}

// AI-agent-friendly dependency summary (grouped by category)
export interface DependencySummaryParams {
  analysis_ids: number[];
  cluster_id?: number;
  pod_name?: string;
  namespace?: string;
  owner_name?: string;
  annotation_key?: string;
  annotation_value?: string;
  label_key?: string;
  label_value?: string;
  ip?: string;
  depth?: number;
}

export interface DependencySummaryService {
  name: string;
  namespace: string;
  kind?: string;
  annotations: Record<string, string>;
  labels: Record<string, string>;
  is_critical?: boolean;
  service_type?: string;
  port?: number;
}

export interface DependencySummaryGroup {
  total: number;
  critical_count?: number;
  by_category: Record<string, DependencySummaryService[]>;
}

export interface MatchedService {
  name: string;
  namespace: string;
  kind?: string;
  annotations: Record<string, string>;
  labels: Record<string, string>;
  downstream_count: number;
  callers_count: number;
}

export interface DependencySummaryResponse {
  success: boolean;
  analysis_ids: number[];
  multi_service?: boolean;
  service: DependencySummaryService;
  matched_services?: MatchedService[];
  downstream: DependencySummaryGroup;
  callers: DependencySummaryGroup;
  error?: string;
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
    
    // Find pod dependencies (upstream/downstream) by any metadata
    getPodDependencyStream: builder.query<PodDependencyStreamResponse, PodDependencyStreamParams>({
      query: (params) => ({
        url: '/communications/dependencies/stream',
        params,
      }),
      providesTags: ['Communication'],
    }),

    // Batch find dependencies for multiple services
    batchDependency: builder.mutation<BatchDependencyResponse, BatchDependencyRequest>({
      query: (body) => ({
        url: '/communications/dependencies/batch',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Communication'],
    }),

    // Diff dependencies between two analysis runs
    getDependencyDiff: builder.query<DependencyDiffResponse, DependencyDiffParams>({
      query: (params) => ({
        url: '/communications/dependencies/diff',
        params,
      }),
      providesTags: ['Communication'],
    }),

    // Combined dependency + impact assessment
    getDependencyImpact: builder.query<DependencyImpactResponse, DependencyImpactParams>({
      query: (params) => ({
        url: '/communications/dependencies/impact',
        params,
      }),
      providesTags: ['Communication'],
    }),

    // AI-agent-friendly dependency summary grouped by service category
    getDependencySummary: builder.query<DependencySummaryResponse, DependencySummaryParams>({
      query: ({ analysis_ids, ...rest }) => {
        const searchParams = new URLSearchParams();
        analysis_ids.forEach(id => searchParams.append('analysis_ids', String(id)));
        Object.entries(rest).forEach(([k, v]) => {
          if (v !== undefined && v !== null) searchParams.append(k, String(v));
        });
        return `/communications/dependencies/summary?${searchParams.toString()}`;
      },
      providesTags: ['Communication'],
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
  useGetPodDependencyStreamQuery,
  useBatchDependencyMutation,
  useGetDependencyDiffQuery,
  useGetDependencyImpactQuery,
  useGetDependencySummaryQuery,
  useLazyGetDependencySummaryQuery,
} = communicationApi;

