import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

export const l7CommunicationApi = createApi({
  reducerPath: 'l7CommunicationApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['L7Graph', 'L7Stats'],
  endpoints: (builder) => ({
    getL7Communications: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/communications', params }),
      providesTags: ['L7Graph'],
    }),
    getL7DependencyGraph: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/dependencies/graph', params }),
      providesTags: ['L7Graph'],
    }),
    getL7CommunicationStats: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/communications/stats', params }),
      providesTags: ['L7Stats'],
    }),
    getL7ErrorStats: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/communications/error-stats', params }),
      providesTags: ['L7Stats'],
    }),
    getL7DependencySummary: builder.query<L7DependencySummaryResponse, L7DependencySummaryParams>({
      query: (params) => ({ url: '/l7/dependencies/summary', params }),
      providesTags: ['L7Stats'],
    }),
    getL7DependencyTreeSummary: builder.query<L7TreeSummaryResponse, L7TreeSummaryParams>({
      query: (params) => ({ url: '/l7/dependencies/tree-summary', params }),
      providesTags: ['L7Stats'],
    }),
  }),
});

export interface L7DependencySummaryParams {
  analysis_id: string | number;
  cluster_id?: string | number;
  namespace?: string;
  include_metadata?: boolean;
  annotation_key?: string;
  annotation_value?: string;
  label_key?: string;
  label_value?: string;
  owner_name?: string;
  pod_name?: string;
  workload_name?: string;
  filter_noise_annotations?: boolean;
}

export interface L7Workload {
  id: string;
  name: string;
  namespace: string;
  cluster: string;
  inbound_count: number;
  outbound_count: number;
  request_count: number;
  error_count: number;
  error_rate_percent: number;
  is_matched?: boolean;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  owner_kind?: string;
}

export interface L7DependencySummaryResponse {
  success: boolean;
  analysis_id: string;
  cluster_id: string | null;
  workloads: L7Workload[];
  summary?: { total_matched: number; total_workloads: number };
  error?: string;
}

export interface L7TreeSummaryParams {
  analysis_id: string | number;
  cluster_id?: string | number;
  workload_name?: string;
  namespace?: string;
  depth?: number;
  label_key?: string;
  label_value?: string;
  annotation_key?: string;
  annotation_value?: string;
  include_metadata?: boolean;
  workload_name_exact?: boolean;
}

export interface L7TreeEdge {
  name: string;
  namespace: string;
  cluster: string;
  protocol: string;
  http_method: string;
  http_path: string;
  request_count: number;
  error_count: number;
  avg_latency_ms: number;
}

export interface L7TreeService {
  name: string;
  namespace: string;
  cluster: string;
  downstream: { total: number; by_protocol: Record<string, L7TreeEdge[]> };
  callers: { total: number; by_protocol: Record<string, L7TreeEdge[]> };
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  owner_kind?: string;
}

export interface L7TreeSummaryResponse {
  success: boolean;
  analysis_id: string;
  cluster_id: string | null;
  multi_service: boolean;
  summary: {
    total_matched: number;
    total_downstream: number;
    total_callers: number;
    total_workloads: number;
  };
  matched_services: L7TreeService[];
  error?: string;
}

export const {
  useGetL7CommunicationsQuery,
  useLazyGetL7CommunicationsQuery,
  useGetL7DependencyGraphQuery,
  useGetL7CommunicationStatsQuery,
  useGetL7ErrorStatsQuery,
  useLazyGetL7DependencySummaryQuery,
  useGetL7DependencySummaryQuery,
  useLazyGetL7DependencyTreeSummaryQuery,
  useGetL7DependencyTreeSummaryQuery,
} = l7CommunicationApi;
