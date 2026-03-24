import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// =============================================================================
// Types - Network Policy
// =============================================================================

export interface LabelSelector {
  match_labels?: Record<string, string>;
  match_expressions?: Array<{
    key: string;
    operator: string;
    values?: string[];
  }>;
}

export interface IPBlock {
  cidr: string;
  except?: string[];
}

export interface NetworkPolicyPeer {
  namespace_selector?: LabelSelector;
  pod_selector?: LabelSelector;
  ip_block?: IPBlock;
}

export interface NetworkPolicyPort {
  protocol: string;
  port?: number;
  end_port?: number;
}

export interface NetworkPolicyRule {
  rule_type: 'ingress' | 'egress';
  action: 'allow' | 'deny';
  peers?: NetworkPolicyPeer[];
  ports?: NetworkPolicyPort[];
}

export interface NetworkPolicySpec {
  policy_name: string;
  target_namespace: string;
  target_pod_selector: LabelSelector;
  policy_types: Array<'ingress' | 'egress' | 'both'>;
  ingress_rules?: NetworkPolicyRule[];
  egress_rules?: NetworkPolicyRule[];
}

// =============================================================================
// Types - Requests
// =============================================================================

export interface NetworkPolicyGenerateRequest {
  cluster_id: number;
  analysis_id?: number;
  target_namespace: string;
  target_workload: string;
  target_kind?: string;
  policy_types?: Array<'ingress' | 'egress' | 'both'>;
  include_dns?: boolean;
  strict_mode?: boolean;
}

export interface NetworkPolicyPreviewRequest {
  cluster_id: number;
  analysis_id?: number;
  target_namespace: string;
  target_workload: string;
  target_kind?: string;
  policy_spec: NetworkPolicySpec;
}

export type ChangeType = 
  | 'delete' 
  | 'scale_down' 
  | 'network_isolate' 
  | 'resource_change' 
  | 'port_change' 
  | 'config_change' 
  | 'image_update' 
  | 'network_policy_apply' 
  | 'network_policy_remove';

export interface ImpactSimulationRequest {
  cluster_id: number;
  analysis_id?: number;
  target_id: string;
  target_name: string;
  target_namespace: string;
  target_kind: string;
  change_type: ChangeType;
  network_policy_spec?: NetworkPolicySpec;
}

// =============================================================================
// Types - Responses
// =============================================================================

export interface AffectedConnection {
  source_name: string;
  source_namespace: string;
  source_kind: string;
  target_name: string;
  target_namespace: string;
  target_kind: string;
  protocol: string;
  port: number;
  request_count: number;
  would_be_blocked: boolean;
  rule_match?: string;
}

export interface NetworkPolicyGenerateResponse {
  policy_name: string;
  target_workload: string;
  target_namespace: string;
  observed_ingress_sources: number;
  observed_egress_destinations: number;
  generated_yaml: string;
  policy_spec: NetworkPolicySpec;
  coverage_summary: {
    ingress: {
      total_sources: number;
      namespaces_covered: number;
      ports_covered: number;
    };
    egress: {
      total_destinations: number;
      namespaces_covered: number;
      external_endpoints: number;
    };
  };
  recommendations: string[];
}

export interface NetworkPolicyPreviewResponse {
  policy_name: string;
  target_workload: string;
  target_namespace: string;
  total_connections: number;
  blocked_connections: number;
  allowed_connections: number;
  affected_connections: AffectedConnection[];
  generated_yaml: string;
  warnings: string[];
  recommendations: string[];
}

export type ImpactLevel = 'high' | 'medium' | 'low' | 'none';
export type DependencyType = 'direct' | 'indirect';

// Impact categories - what kind of effect the change has
// IMPORTANT: Category and Level must be consistent:
// - service_outage, connectivity_loss → Always HIGH
// - cascade_risk → MEDIUM (potential impact, not actual outage)
// - performance_degradation → MEDIUM or LOW
export type ImpactCategory = 
  | 'service_outage'           // Complete service unavailability → HIGH
  | 'connectivity_loss'        // Network connectivity issues → HIGH
  | 'cascade_risk'             // Potential cascade from upstream failure → MEDIUM
  | 'performance_degradation'  // Slowdowns, resource constraints → MEDIUM/LOW
  | 'configuration_drift'      // Config inconsistencies
  | 'security_exposure'        // Security posture changes
  | 'compatibility_risk'       // Version/API compatibility issues
  | 'transient_disruption';    // Temporary restart/rollout

export interface AffectedService {
  id: string;
  name: string;
  namespace: string;
  kind: string;
  impact: ImpactLevel;
  impact_category?: ImpactCategory;
  impact_description?: string;
  dependency: DependencyType;
  recommendation: string;
  connection_details?: {
    protocol?: string;
    port?: number;
    request_count?: number;
    last_seen?: string;
    hop_distance?: number;
  };
  risk_score: number;
  risk_factors?: string[];
  recovery_info?: {
    recovery_time?: string;
    reversible?: boolean;
  };
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
}

export interface ImpactSummary {
  total_affected: number;
  high_impact: number;
  medium_impact: number;
  low_impact: number;
  blast_radius: number;
  confidence_score: number;
  // Change type specific fields
  primary_impact_category?: ImpactCategory;
  impact_description?: string;
  expected_behavior?: string;
  recovery_time?: string;
  is_reversible?: boolean;
}

export interface NoDependencyInfo {
  scenario: 'NO_GRAPH_MATCH' | 'ISOLATED_WORKLOAD' | 'EXTERNAL_ONLY';
  title: string;
  description: string;
  suggestions: string[];
  alert_type: 'success' | 'info' | 'warning' | 'error';
}

export interface SimulationDetails {
  target_name: string;
  target_namespace: string;
  target_kind: string;
  change_type: string;
  change_description: string;
  graph_matches: number;
  simulation_timestamp: string;
}

export interface TimelineProjection {
  immediate: {
    description: string;
    affected_count: number;
    expected_duration: string;
    impact_category?: string;
  };
  short_term: {
    description: string;
    affected_count: number;
    expected_duration: string;
    secondary_impacts?: string[];
  };
  long_term: {
    description: string;
    affected_count: number;
    expected_duration: string;
    recovery_time?: string;
  };
}

export interface RollbackScenario {
  feasibility: 'high' | 'medium' | 'low';
  estimated_time: string;
  steps: string[];
  risks: string[];
  reversible?: boolean;
}

export interface ImpactSimulationResponse {
  success: boolean;
  simulation_id: string;
  details: SimulationDetails;
  summary: ImpactSummary;
  affected_services: AffectedService[];
  no_dependency_info?: NoDependencyInfo;
  network_policy_suggestion?: NetworkPolicyGenerateResponse;
  timeline_projection?: TimelineProjection;
  rollback_scenario?: RollbackScenario;
}

export interface ChangeTypeInfo {
  key: ChangeType;
  label: string;
  description: string;
  icon: string;
  category: string;
  advanced?: boolean;
}

export interface ChangeTypesResponse {
  change_types: ChangeTypeInfo[];
}

// =============================================================================
// Types - Scheduled Simulations
// =============================================================================

export interface ScheduledSimulation {
  id: string;
  name: string;
  description?: string;
  cluster_id: string;
  analysis_id?: string;
  target_name: string;
  target_namespace: string;
  target_kind: string;
  change_type: string;
  schedule_type: 'once' | 'daily' | 'weekly';
  scheduled_time: string;
  notify_before_minutes: number;
  auto_rollback: boolean;
  rollback_on_failure: boolean;
  status: 'scheduled' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  created_by?: string;
  last_run_at?: string;
  last_run_result?: string;
}

export interface ScheduledSimulationCreateRequest {
  name: string;
  description?: string;
  cluster_id: string;
  analysis_id?: string;
  target_name: string;
  target_namespace: string;
  target_kind: string;
  change_type: string;
  schedule_type: 'once' | 'daily' | 'weekly';
  scheduled_time: string;
  notify_before_minutes?: number;
  auto_rollback?: boolean;
  rollback_on_failure?: boolean;
}

export interface ScheduledSimulationListResponse {
  simulations: ScheduledSimulation[];
  total: number;
}

// =============================================================================
// Types - Simulation History
// =============================================================================

export interface SimulationHistoryEntry {
  id: string;
  simulation_id: string;
  cluster_id: string;
  analysis_id?: string;
  target_name: string;
  target_namespace: string;
  target_kind: string;
  change_type: string;
  total_affected: number;
  high_impact: number;
  medium_impact: number;
  low_impact: number;
  blast_radius: number;
  confidence_score: number;
  status: 'completed' | 'failed';
  created_at: string;
  created_by?: string;
  duration_ms?: number;
  result_summary?: {
    affected_services?: Array<{
      name: string;
      namespace: string;
      kind: string;
      impact: string;
      dependency: string;
      risk_score: number;
    }>;
    timeline_projection?: TimelineProjection;
    rollback_scenario?: RollbackScenario;
  };
}

export interface SimulationHistoryListResponse {
  history: SimulationHistoryEntry[];
  total: number;
}

// =============================================================================
// API Definition
// =============================================================================

export const simulationApi = createApi({
  reducerPath: 'simulationApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Simulation', 'NetworkPolicy', 'ScheduledSimulation', 'SimulationHistory'],
  endpoints: (builder) => ({
    // Generate network policy from observed traffic
    generateNetworkPolicy: builder.mutation<NetworkPolicyGenerateResponse, NetworkPolicyGenerateRequest>({
      query: (request) => ({
        url: '/simulation/network-policy/generate',
        method: 'POST',
        body: request,
      }),
      invalidatesTags: ['NetworkPolicy'],
    }),

    // Preview network policy impact
    previewNetworkPolicy: builder.mutation<NetworkPolicyPreviewResponse, NetworkPolicyPreviewRequest>({
      query: (request) => ({
        url: '/simulation/network-policy/preview',
        method: 'POST',
        body: request,
      }),
    }),

    // Run impact simulation
    runImpactSimulation: builder.mutation<ImpactSimulationResponse, ImpactSimulationRequest>({
      query: (request) => ({
        url: '/simulation/impact',
        method: 'POST',
        body: request,
      }),
      invalidatesTags: ['Simulation', 'SimulationHistory'],
    }),

    // Get available change types
    getChangeTypes: builder.query<ChangeTypesResponse, void>({
      query: () => '/simulation/change-types',
    }),

    // Export simulation to JSON
    exportSimulationJson: builder.mutation<Blob, ImpactSimulationRequest & { cluster_name?: string }>({
      query: ({ cluster_name, ...request }) => ({
        url: '/simulation/impact/export/json',
        method: 'POST',
        body: request,
        params: cluster_name ? { cluster_name } : undefined,
        responseHandler: async (response) => {
          const blob = await response.blob();
          return blob;
        },
      }),
    }),

    // Export simulation to CSV
    exportSimulationCsv: builder.mutation<Blob, ImpactSimulationRequest & { cluster_name?: string }>({
      query: ({ cluster_name, ...request }) => ({
        url: '/simulation/impact/export/csv',
        method: 'POST',
        body: request,
        params: cluster_name ? { cluster_name } : undefined,
        responseHandler: async (response) => {
          const blob = await response.blob();
          return blob;
        },
      }),
    }),

    // ==========================================================================
    // Scheduled Simulations
    // ==========================================================================

    // List scheduled simulations
    getScheduledSimulations: builder.query<ScheduledSimulationListResponse, { cluster_id?: string; status?: string }>({
      query: (params) => ({
        url: '/simulation/scheduled',
        params,
      }),
      providesTags: ['ScheduledSimulation'],
    }),

    // Create scheduled simulation
    createScheduledSimulation: builder.mutation<ScheduledSimulation, ScheduledSimulationCreateRequest>({
      query: (request) => ({
        url: '/simulation/scheduled',
        method: 'POST',
        body: request,
      }),
      invalidatesTags: ['ScheduledSimulation'],
    }),

    // Cancel/delete scheduled simulation
    cancelScheduledSimulation: builder.mutation<{ message: string; id: string }, string>({
      query: (simulationId) => ({
        url: `/simulation/scheduled/${simulationId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['ScheduledSimulation'],
    }),

    // Run scheduled simulation now
    runScheduledSimulationNow: builder.mutation<{ message: string; id: string; result: ImpactSimulationResponse }, string>({
      query: (simulationId) => ({
        url: `/simulation/scheduled/${simulationId}/run`,
        method: 'POST',
      }),
      invalidatesTags: ['ScheduledSimulation', 'SimulationHistory'],
    }),

    // ==========================================================================
    // Simulation History
    // ==========================================================================

    // List simulation history
    getSimulationHistory: builder.query<SimulationHistoryListResponse, { cluster_id?: string; analysis_id?: string; limit?: number; offset?: number }>({
      query: (params) => ({
        url: '/simulation/history',
        params,
      }),
      providesTags: ['SimulationHistory'],
    }),

    // Get specific history entry
    getSimulationHistoryEntry: builder.query<SimulationHistoryEntry, string>({
      query: (historyId) => `/simulation/history/${historyId}`,
      providesTags: ['SimulationHistory'],
    }),

    // Delete history entry
    deleteSimulationHistoryEntry: builder.mutation<{ message: string; id: string }, string>({
      query: (historyId) => ({
        url: `/simulation/history/${historyId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['SimulationHistory'],
    }),
  }),
});

export const {
  useGenerateNetworkPolicyMutation,
  usePreviewNetworkPolicyMutation,
  useRunImpactSimulationMutation,
  useGetChangeTypesQuery,
  useExportSimulationJsonMutation,
  useExportSimulationCsvMutation,
  // Scheduled Simulations
  useGetScheduledSimulationsQuery,
  useCreateScheduledSimulationMutation,
  useCancelScheduledSimulationMutation,
  useRunScheduledSimulationNowMutation,
  // Simulation History
  useGetSimulationHistoryQuery,
  useGetSimulationHistoryEntryQuery,
  useDeleteSimulationHistoryEntryMutation,
} = simulationApi;

