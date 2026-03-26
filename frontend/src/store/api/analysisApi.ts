import { createApi } from '@reduxjs/toolkit/query/react';
import { Analysis } from '../../types';
import { baseQueryWithReauth } from './baseQuery';

interface ScopeConfig {
  cluster_id: number;
  cluster_ids?: number[];  // For multi-cluster analysis
  scope_type: 'cluster' | 'namespace' | 'deployment' | 'pod' | 'label';
  namespaces?: string[];
  deployments?: string[];
  pods?: string[];
  labels?: Record<string, string>;
  per_cluster_scope?: Record<string, any>;  // Per-cluster scope configuration
  exclude_namespaces?: string[];
  exclude_pod_patterns?: string[];
  exclude_strategy?: 'aggressive' | 'conservative';
}

interface GadgetConfig {
  enabled_gadgets: string[];
  network_traffic?: Record<string, unknown>;
  dns_queries?: Record<string, unknown>;
  // NOTE: tcp_connections removed - IG trace_tcp doesn't produce TCP state events
  process_events?: Record<string, unknown>;
  syscall_tracking?: Record<string, unknown>;
  file_access?: Record<string, unknown>;
}

interface TimeConfig {
  mode: 'continuous' | 'timed' | 'time_range' | 'periodic' | 'baseline' | 'recurring';
  start_time?: string;
  end_time?: string;
  duration_seconds?: number;
  duration_minutes?: number;
  periodic_interval?: number;
  baseline_name?: string;
  data_retention_policy?: 'unlimited' | 'stop_on_limit' | 'rolling_window';
  max_data_size_mb?: number;
  schedule_expression?: string;
  schedule_duration_seconds?: number;
}

export interface ScheduleAnalysisRequest {
  cron_expression: string;
  duration_seconds: number;
  max_runs?: number;
}

export interface ScheduleAnalysisResponse {
  analysis_id: number;
  is_scheduled: boolean;
  schedule_expression: string;
  schedule_duration_seconds: number;
  next_run_at?: string;
  message: string;
}

interface OutputConfig {
  enable_dashboard: boolean;
  enable_llm_analysis: boolean;
  llm_provider?: string;
  llm_model?: string;
  enable_alarms: boolean;
  alarm_thresholds?: Record<string, unknown>;
  enable_webhooks: boolean;
  webhook_urls?: string[];
  export_format?: string[];
}

export interface DeleteAnalysisResponse {
  analysis_id: number;
  deleted: boolean;
  postgresql?: {
    deleted_analyses?: number;
    deleted_runs?: number;
    error?: string;
  };
  neo4j: {
    deleted_edges?: number;
    deleted_nodes?: number;
    orphaned_nodes?: number;
    batches?: number;
    duration_ms?: number;
    cluster_id?: number;
    initial_counts?: {
      edges?: Record<string, number>;
      nodes?: number;
      by_cluster?: { edges?: number; nodes?: number };
      diagnostic?: {
        total_nodes?: number;
        total_edges?: number;
        distinct_analysis_ids?: string[];
      };
    };
    warning?: string;
    error?: string;
  };
  clickhouse: {
    total_deleted?: number;
    completed?: boolean;
    duration_ms?: number;
    tables?: Record<string, number>;
    warning?: string;
    diagnostic?: {
      total_all?: Record<string, number>;
      empty_analysis_id?: Record<string, number>;
    };
    error?: string;
  };
  redis?: {
    deleted_keys?: number;
    error?: string;
  };
  rabbitmq?: {
    note?: string;
    status?: string;
    error?: string;
  };
  duration_ms: number;
  message: string;
}

// Change detection strategy types
export type ChangeDetectionStrategy = 'baseline' | 'rolling_window' | 'run_comparison';

// Change types that can be tracked
export type ChangeType = 
  | 'all'
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

export interface AnalysisCreateRequest {
  name: string;
  description?: string;
  scope: ScopeConfig;
  gadgets: GadgetConfig;
  time_config: TimeConfig;
  output: OutputConfig;
  change_detection_enabled?: boolean;  // Enable/disable change tracking (default: true)
  change_detection_strategy?: ChangeDetectionStrategy;  // Detection strategy (default: 'baseline')
  change_detection_types?: ChangeType[];  // Change types to track (default: ['all'])
}

// Stop analysis response - includes orchestrator status for safety verification
export interface StopAnalysisResponse {
  message: string;
  analysis_id: number;
  events_collected?: number;
  communications_discovered?: number;
  orchestrator_status: 'success' | 'warning';
  orchestrator_error?: string;
}

export interface AnalysisRun {
  id: number;
  analysis_id: number;
  status: string;
  start_time?: string;
  end_time?: string;
  events_collected: number;
  communications_discovered: number;
  error_message?: string;
}

export const analysisApi = createApi({
  reducerPath: 'analysisApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Analysis', 'AnalysisRun'],
  endpoints: (builder) => ({
    // Get all analyses
    getAnalyses: builder.query<Analysis[], { cluster_id?: number; status?: string }>({
      query: ({ cluster_id, status }) => ({
        url: '/analyses',
        params: { cluster_id, status }
      }),
      providesTags: ['Analysis'],
    }),
    
    // Get single analysis
    getAnalysis: builder.query<Analysis, number>({
      query: (id) => `/analyses/${id}`,
      providesTags: (result, error, id) => [{ type: 'Analysis', id }],
    }),
    
    // Create analysis
    createAnalysis: builder.mutation<Analysis, AnalysisCreateRequest>({
      query: (analysis) => ({
        url: '/analyses',
        method: 'POST',
        body: analysis,
      }),
      invalidatesTags: ['Analysis'],
    }),
    
    // Start analysis
    startAnalysis: builder.mutation<AnalysisRun, number>({
      query: (id) => ({
        url: `/analyses/${id}/start`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, id) => [
        { type: 'Analysis', id },
        'AnalysisRun'
      ],
    }),
    
    // Stop analysis - returns orchestrator status for safety verification
    stopAnalysis: builder.mutation<StopAnalysisResponse, number>({
      query: (id) => ({
        url: `/analyses/${id}/stop`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, id) => [
        { type: 'Analysis', id },
        'AnalysisRun'
      ],
    }),
    
    // Delete analysis - returns detailed deletion summary
    deleteAnalysis: builder.mutation<DeleteAnalysisResponse, number>({
      query: (id) => ({
        url: `/analyses/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Analysis'],
    }),
    
    // Get analysis runs
    getAnalysisRuns: builder.query<AnalysisRun[], number>({
      query: (analysisId) => `/analyses/${analysisId}/runs`,
      providesTags: (result, error, analysisId) => [
        { type: 'AnalysisRun', id: `analysis-${analysisId}` }
      ],
    }),
    
    // Schedule analysis for recurring execution
    scheduleAnalysis: builder.mutation<ScheduleAnalysisResponse, { id: number; body: ScheduleAnalysisRequest }>({
      query: ({ id, body }) => ({
        url: `/analyses/${id}/schedule`,
        method: 'POST',
        body,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: 'Analysis', id }],
    }),
    
    // Remove schedule from analysis
    unscheduleAnalysis: builder.mutation<{ message: string; analysis_id: number }, number>({
      query: (id) => ({
        url: `/analyses/${id}/schedule`,
        method: 'DELETE',
      }),
      invalidatesTags: (result, error, id) => [{ type: 'Analysis', id }],
    }),
  }),
});

export const {
  useGetAnalysesQuery,
  useGetAnalysisQuery,
  useCreateAnalysisMutation,
  useStartAnalysisMutation,
  useStopAnalysisMutation,
  useDeleteAnalysisMutation,
  useGetAnalysisRunsQuery,
  useScheduleAnalysisMutation,
  useUnscheduleAnalysisMutation,
} = analysisApi;

