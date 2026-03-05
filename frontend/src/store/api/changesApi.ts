import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// Change types
// Legacy types: workload_added, workload_removed, namespace_changed (for backward compatibility)
// K8s API types: replica_changed, config_changed, image_changed, label_changed
// eBPF types: connection_added, connection_removed, port_changed, traffic_anomaly, dns_anomaly, process_anomaly, error_anomaly
export type ChangeType = 
  // Legacy types (backward compatibility)
  | 'workload_added'
  | 'workload_removed'
  | 'namespace_changed'
  // Infrastructure changes (K8s API) - Workloads
  | 'replica_changed'
  | 'config_changed'
  | 'image_changed'
  | 'label_changed'
  | 'resource_changed'
  | 'env_changed'
  | 'spec_changed'
  // Infrastructure changes (K8s API) - Services
  | 'service_port_changed'
  | 'service_selector_changed'
  | 'service_type_changed'
  | 'service_added'
  | 'service_removed'
  // Infrastructure changes (K8s API) - Network / Ingress / Route
  | 'network_policy_added'
  | 'network_policy_removed'
  | 'network_policy_changed'
  | 'ingress_added'
  | 'ingress_removed'
  | 'ingress_changed'
  | 'route_added'
  | 'route_removed'
  | 'route_changed'
  // Behavioral changes (eBPF) - Connections
  | 'connection_added'
  | 'connection_removed'
  | 'port_changed'
  // Behavioral changes (eBPF) - Anomalies
  | 'traffic_anomaly'
  | 'dns_anomaly'
  | 'process_anomaly'
  | 'error_anomaly';

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low';

// Change interface
export interface Change {
  id: number;
  cluster_id?: number;
  analysis_id?: number;
  timestamp: string;
  change_type: ChangeType;
  target: string;
  namespace: string;
  details: string;
  risk: RiskLevel;
  affected_services: number;
  changed_by: string;
  status?: string;
  metadata?: Record<string, unknown>;
}

// Change statistics
export interface ChangeStats {
  total_changes: number;
  by_type: Record<string, number>;
  by_risk: Record<string, number>;
  by_namespace: Record<string, number>;
}

// Snapshot comparison
export interface SnapshotComparison {
  before: Record<string, number>;
  after: Record<string, number>;
  summary: {
    added: number;
    removed: number;
    modified: number;
  };
}

// Response interfaces
export interface ChangesResponse {
  changes: Change[];
  total: number;
  stats: ChangeStats;
  comparison: SnapshotComparison;
}

export interface ChangeStatsSummary {
  cluster_id: number;
  analysis_id?: number;
  period: {
    start: string;
    end: string;
    days: number;
  };
  stats: ChangeStats;
  daily_breakdown: Record<string, number>;
  trends: {
    avg_changes_per_day: number;
    high_risk_ratio: number;
  };
}

export interface SnapshotDiff {
  cluster_id: number;
  analysis_before: {
    id: number;
    workloads: number;
    connections: number;
    namespaces: string[];
  };
  analysis_after: {
    id: number;
    workloads: number;
    connections: number;
    namespaces: string[];
  };
  diff: {
    workloads_added: string[];
    workloads_removed: string[];
    connections_added: Array<{
      source: string;
      target: string;
      port: number;
    }>;
    connections_removed: Array<{
      source: string;
      target: string;
      port: number;
    }>;
    namespaces_added: string[];
    namespaces_removed: string[];
  };
  summary: {
    total_changes: number;
    workload_changes: number;
    connection_changes: number;
    namespace_changes: number;
  };
}

// Query parameters
export interface ChangesQueryParams {
  cluster_id: number;
  analysis_id?: number;
  run_id?: number;
  run_ids?: string;
  start_time?: string;
  end_time?: string;
  change_types?: string;
  risk_levels?: string;
  limit?: number;
  offset?: number;
}

// Analysis Run interfaces (Phase 9)
export interface AnalysisRun {
  run_id: number;
  run_number: number;
  status: 'running' | 'completed' | 'stopped' | 'failed' | 'cancelled';
  start_time: string;
  end_time?: string;
  duration_seconds?: number;
  events_collected?: number;
  workloads_discovered?: number;
  communications_discovered?: number;
  anomalies_detected?: number;
  changes_detected?: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

export interface AnalysisRunsResponse {
  analysis_id: number;
  total_runs: number;
  run_based_filtering_enabled: boolean;
  runs: AnalysisRun[];
}

export interface RunStats {
  run_id: number;
  run_number: number;
  total_changes: number;
  by_risk: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  by_type: Record<string, number>;
  first_change_at?: string;
  last_change_at?: string;
}

export interface RunStatsResponse {
  analysis_id: number;
  source: 'clickhouse' | 'postgresql';
  stats: RunStats[];
}

// Run Comparison interfaces
export interface RunComparisonChange {
  change_type: string;
  target_name: string;
  target_namespace: string;
  risk_level: string;
  details: string;
  before_state: Record<string, unknown>;
  after_state: Record<string, unknown>;
  detected_at: string;
}

export interface RunComparisonMeta {
  run_id: number;
  run_number: number;
  status: string;
  start_time: string;
  end_time?: string;
  total_changes: number;
  events_collected: number;
  communications_discovered: number;
}

export interface RunComparisonResult {
  analysis_id: number;
  run_a: RunComparisonMeta;
  run_b: RunComparisonMeta;
  comparison: {
    total_in_run_a: number;
    total_in_run_b: number;
    only_in_run_a: number;
    only_in_run_b: number;
    common: number;
    by_type: {
      only_in_a: Record<string, number>;
      only_in_b: Record<string, number>;
      common: Record<string, number>;
    };
    by_risk: {
      only_in_a: Record<string, number>;
      only_in_b: Record<string, number>;
      common: Record<string, number>;
    };
    summary: {
      new_in_b: string;
      removed_from_a: string;
      persistent: string;
    };
  };
  changes_only_in_a: RunComparisonChange[];
  changes_only_in_b: RunComparisonChange[];
  common_changes: RunComparisonChange[];
}

export interface ChangeDetectionConfig {
  storage: string;  // 'clickhouse'
  run_based_filtering: boolean;
  architecture: string;  // 'ClickHouse-only'
  feature_flags: {
    RUN_BASED_FILTERING_ENABLED: boolean;
  };
  documentation: Record<string, string>;
}

export const changesApi = createApi({
  reducerPath: 'changesApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Changes'],
  endpoints: (builder) => ({
    // Get changes list
    getChanges: builder.query<ChangesResponse, ChangesQueryParams>({
      query: (params) => ({
        url: '/changes',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Changes', id: `${params.cluster_id}-${params.analysis_id || 'all'}` }
      ],
    }),

    // Get change details
    getChangeDetails: builder.query<Change & { 
      related_changes: Change[]; 
      rollback_available: boolean;
      before_state?: Record<string, unknown>;
      after_state?: Record<string, unknown>;
      audit_trail?: Array<{ action: string; timestamp: string; actor: string }>;
    }, number>({
      query: (changeId) => `/changes/${changeId}`,
      providesTags: (result, error, id) => [
        { type: 'Changes', id }
      ],
    }),

    // Get change stats summary
    getChangeStatsSummary: builder.query<ChangeStatsSummary, { cluster_id: number; analysis_id?: number; days?: number }>({
      query: ({ cluster_id, analysis_id, days = 7 }) => ({
        url: '/changes/stats/summary',
        params: { cluster_id, analysis_id, days },
      }),
      providesTags: ['Changes'],
    }),

    // Compare snapshots
    compareSnapshots: builder.query<SnapshotDiff, { cluster_id: number; analysis_id_before: number; analysis_id_after: number }>({
      query: (params) => ({
        url: '/changes/compare',
        params,
      }),
      providesTags: ['Changes'],
    }),

    // Sprint 5: Impact Analysis
    analyzeChangeImpact: builder.query<ImpactAnalysisResponse, { 
      cluster_id: number; 
      change_id?: number; 
      workload?: string; 
      namespace?: string; 
      change_type?: string;
    }>({
      query: (params) => ({
        url: '/changes/impact/analyze',
        params,
      }),
      providesTags: ['Changes'],
    }),

    // Get impact for a specific change
    getChangeImpact: builder.query<ImpactAnalysisResponse, number>({
      query: (changeId) => `/changes/${changeId}/impact`,
      providesTags: (result, error, id) => [{ type: 'Changes', id: `impact-${id}` }],
    }),

    // Get correlated changes
    getCorrelatedChanges: builder.query<CorrelatedChangesResponse, { 
      change_id: number; 
      cluster_id: number; 
      time_window?: number;
    }>({
      query: ({ change_id, cluster_id, time_window = 30 }) => ({
        url: `/changes/${change_id}/correlated`,
        params: { cluster_id, time_window },
      }),
      providesTags: (result, error, { change_id }) => [
        { type: 'Changes', id: `correlated-${change_id}` }
      ],
    }),

    // Phase 9: Run-based filtering endpoints
    // Get analysis runs
    getAnalysisRuns: builder.query<AnalysisRunsResponse, number>({
      query: (analysisId) => `/changes/runs/${analysisId}`,
      providesTags: (result, error, analysisId) => [
        { type: 'Changes', id: `runs-${analysisId}` }
      ],
    }),

    // Get run statistics
    getRunStats: builder.query<RunStatsResponse, { analysis_id: number; run_id?: number }>({
      query: ({ analysis_id, run_id }) => ({
        url: `/changes/runs/${analysis_id}/stats`,
        params: run_id ? { run_id } : undefined,
      }),
      providesTags: (result, error, { analysis_id }) => [
        { type: 'Changes', id: `run-stats-${analysis_id}` }
      ],
    }),

    // Compare two runs of the same analysis
    compareRuns: builder.query<RunComparisonResult, { analysis_id: number; run_a: number; run_b: number }>({
      query: ({ analysis_id, run_a, run_b }) => ({
        url: `/changes/runs/${analysis_id}/compare`,
        params: { run_a, run_b },
      }),
      providesTags: (result, error, { analysis_id, run_a, run_b }) => [
        { type: 'Changes', id: `run-compare-${analysis_id}-${run_a}-${run_b}` }
      ],
    }),

    // Get change detection configuration
    getChangeDetectionConfig: builder.query<ChangeDetectionConfig, void>({
      query: () => '/changes/config',
    }),

    // Get error anomaly summary for Network Explorer and Dashboard
    getErrorAnomalySummary: builder.query<ErrorAnomalySummary, ErrorAnomalySummaryParams>({
      query: ({ cluster_id, analysis_id, time_range = '24h' }) => ({
        url: '/changes/errors/summary',
        params: { cluster_id, analysis_id, time_range },
      }),
      providesTags: (result, error, params) => [
        { type: 'Changes', id: `error-summary-${params.cluster_id}-${params.analysis_id || 'all'}` }
      ],
    }),
  }),
});

// Error Anomaly Summary Types
export interface ErrorAnomalySummaryParams {
  cluster_id: number;
  analysis_id?: number;
  time_range?: '1h' | '6h' | '24h' | '7d';
}

export interface ErrorAnomalyConnection {
  source: string;
  target: string;
  error_type: string;
  current_error_count: number;
  previous_error_count: number;
  risk_level: string;
  detected_at: string;
}

export interface ErrorAnomalySummary {
  total_anomalies: number;
  by_error_type: Record<string, number>;
  affected_connections: ErrorAnomalyConnection[];
  trends: {
    last_hour: number;
    last_24h: number;
    trend: 'increasing' | 'decreasing' | 'stable';
  };
  cluster_id?: number;
  analysis_id?: number;
}

// Sprint 5: Impact Analysis Types
export interface AffectedService {
  name: string;
  namespace: string;
  kind: string;
  dependency_type: 'direct' | 'indirect' | 'cascade';
  direction: string;
  port?: number;
  protocol?: string;
  request_count?: number;
  impact_level: 'high' | 'medium' | 'low';
  impact_category: string;
  is_external: boolean;
}

export interface ImpactGraphNode {
  id: string;
  name: string;
  namespace: string;
  type: 'target' | 'direct' | 'indirect' | 'cascade';
  level: number;
  direction?: string;
  is_external?: boolean;
}

export interface ImpactGraphEdge {
  source: string;
  target: string;
  port?: number;
  protocol?: string;
  request_count?: number;
}

export interface ImpactAnalysisResponse {
  target?: {
    workload: string;
    namespace: string;
    change_type?: string;
  };
  blast_radius: {
    total: number;
    direct: number;
    indirect: number;
    cascade: number;
  };
  affected_services: AffectedService[];
  impact_graph: {
    nodes: ImpactGraphNode[];
    edges: ImpactGraphEdge[];
    stats?: {
      total_nodes: number;
      total_edges: number;
      levels: number;
    };
  };
  risk_score: number;
  risk_level?: string;
  impact_categories?: Record<string, number>;
  has_external_connections?: boolean;
  confidence?: number;
  recommendations?: string[];
  error?: string;
}

export interface CorrelatedChange {
  id: number;
  timestamp: string;
  change_type: ChangeType;
  target: string;
  namespace: string;
  details: string;
  risk: RiskLevel;
  affected_services: number;
  changed_by: string;
  correlation_type: 'same_source' | 'same_namespace' | 'time_proximity';
}

export interface CorrelatedChangesResponse {
  reference_change_id: number;
  time_window_minutes: number;
  correlated_changes: CorrelatedChange[];
  total_correlated: number;
  correlation_types: {
    same_source: number;
    same_namespace: number;
    time_proximity: number;
  };
  error?: string;
}

export const {
  useGetChangesQuery,
  useGetChangeDetailsQuery,
  useGetChangeStatsSummaryQuery,
  useCompareSnapshotsQuery,
  // Note: useAnalyzeChangeImpactQuery and useGetChangeImpactQuery are available
  // but we use ChangeImpactSummary component instead (links to Impact Simulation page)
  useAnalyzeChangeImpactQuery,
  useGetChangeImpactQuery,
  useGetCorrelatedChangesQuery,
  // Phase 9: Run-based filtering hooks
  useGetAnalysisRunsQuery,
  useGetRunStatsQuery,
  useCompareRunsQuery,
  useGetChangeDetectionConfigQuery,
  // Error anomaly summary for Network Explorer, Dashboard, Map
  useGetErrorAnomalySummaryQuery,
} = changesApi;

