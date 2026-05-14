/**
 * apmApi — RTK Query for APM (RED metrics) endpoints introduced in Phase 2.
 *
 * Backend mapping:
 *   GET /api/v1/apm/services                                 -> useGetApmServicesQuery
 *   GET /api/v1/apm/services/{workload_key}/operations       -> useGetApmOperationsQuery
 *   GET /api/v1/apm/services/{workload_key}/stats            -> useGetApmServiceStatsQuery
 *   GET /api/v1/apm/services/{workload_key}/dependencies     -> useGetApmServiceDependenciesQuery
 *
 * `workload_key` is `"<namespace>/<workload>"`. We percent-encode it
 * before substituting into the path so embedded slashes don't change the
 * route shape (matches the encoding the backend's `_encode_workload_key`
 * helper does on the way out).
 */
import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

export interface ApmService {
  cluster_id: string;
  dst_workload: string;
  dst_namespace: string;
  workload_key: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
}

export interface ApmServicesResponse {
  services: ApmService[];
  total: number;
  limit: number;
  offset: number;
  sort_by: string;
}

export interface ApmOperation {
  protocol: 'HTTP' | 'GRPC';
  method: string;
  operation: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
}

export interface ApmOperationsResponse {
  operations: ApmOperation[];
  workload_key: string;
  limit: number;
  offset: number;
}

export interface ApmStatsBucket {
  timestamp: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
}

export interface ApmStatsResponse {
  buckets: ApmStatsBucket[];
  workload_key: string;
  interval_seconds: number;
}

export interface ApmDependency {
  // Audit fix: backend now groups by cluster_id so the same workload
  // name in two clusters renders as two rows. Optional for backward
  // compatibility with API clients that haven't redeployed yet.
  cluster_id?: string;
  workload: string;
  namespace: string;
  workload_key: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p95_ms: number;
}

export interface ApmDependenciesResponse {
  workload_key: string;
  upstream: ApmDependency[];
  downstream: ApmDependency[];
  direction: 'upstream' | 'downstream' | 'both';
}

// Plan v3 Akış B m.2 — Trace Explorer "Operations" tab. Each row
// has the same shape as the per-workload `ApmOperation` plus a
// cluster_id / workload context so the operator can correlate a
// hot operation back to the owning service in one glance.
export interface ApmGlobalOperation extends ApmOperation {
  cluster_id: string;
  workload: string;
  namespace: string;
  workload_key: string;
}

export interface ApmGlobalOperationsResponse {
  operations: ApmGlobalOperation[];
  limit: number;
}

// Plan v3 Akış B m.2 — Trace Explorer "Dependencies" tab. Each row
// is a directed edge `(src → dst)` with RED metrics for the edge.
export interface ApmGlobalEdge {
  cluster_id: string;
  src_workload: string;
  src_namespace: string;
  src_workload_key: string;
  dst_workload: string;
  dst_namespace: string;
  dst_workload_key: string;
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_p95_ms: number;
}

export interface ApmGlobalDependenciesResponse {
  edges: ApmGlobalEdge[];
  limit: number;
}

export interface ApmGlobalParams {
  analysis_id: string;
  cluster_id?: string;
  limit?: number;
  q?: string;
}

export interface ApmServicesParams {
  analysis_id: string;
  cluster_id?: string;
  namespace?: string;
  sort_by?: 'rate' | 'errors' | 'p50' | 'p95' | 'p99' | 'avg';
  limit?: number;
  offset?: number;
  // Plan v3 Akış B m.4 — global free-form search shared with Trace Explorer.
  // Empty string is stripped by `cleanParams` so an idle search box never
  // round-trips a no-op `?q=` to the backend.
  q?: string;
}

export interface ApmWorkloadParams {
  workload_key: string;
  analysis_id: string;
  cluster_id?: string;
}

export interface ApmOperationsParams extends ApmWorkloadParams {
  limit?: number;
  offset?: number;
  q?: string;
}

export interface ApmDependenciesParams extends ApmWorkloadParams {
  direction?: 'upstream' | 'downstream' | 'both';
  q?: string;
}

const cleanParams = (input: Record<string, unknown>): Record<string, unknown> => {
  const out: Record<string, unknown> = {};
  Object.entries(input).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    out[k] = v;
  });
  return out;
};

// Encode the embedded `/` in `namespace/workload` so the path-param routing
// still matches on the way to FastAPI. The backend re-encodes it again
// before proxying to timeseries-query.
const encodeKey = (key: string) => encodeURIComponent(key);

export const apmApi = createApi({
  reducerPath: 'apmApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: [
    'ApmServices',
    'ApmOperations',
    'ApmStats',
    'ApmDependencies',
    'ApmGlobalOps',
    'ApmGlobalEdges',
  ],
  endpoints: (builder) => ({
    getApmServices: builder.query<ApmServicesResponse, ApmServicesParams>({
      query: (params) => ({ url: '/apm/services', params: cleanParams(params as any) }),
      providesTags: ['ApmServices'],
    }),
    getApmOperations: builder.query<ApmOperationsResponse, ApmOperationsParams>({
      query: ({ workload_key, ...rest }) => ({
        url: `/apm/services/${encodeKey(workload_key)}/operations`,
        params: cleanParams(rest as any),
      }),
      providesTags: (_r, _e, arg) => [{ type: 'ApmOperations' as const, id: arg.workload_key }],
    }),
    getApmServiceStats: builder.query<ApmStatsResponse, ApmWorkloadParams>({
      query: ({ workload_key, ...rest }) => ({
        url: `/apm/services/${encodeKey(workload_key)}/stats`,
        params: cleanParams(rest as any),
      }),
      providesTags: (_r, _e, arg) => [{ type: 'ApmStats' as const, id: arg.workload_key }],
    }),
    getApmServiceDependencies: builder.query<ApmDependenciesResponse, ApmDependenciesParams>({
      query: ({ workload_key, ...rest }) => ({
        url: `/apm/services/${encodeKey(workload_key)}/dependencies`,
        params: cleanParams(rest as any),
      }),
      providesTags: (_r, _e, arg) => [{ type: 'ApmDependencies' as const, id: arg.workload_key }],
    }),
    // Plan v3 Akış B m.2 — flat global aggregates for Trace Explorer.
    // Distinct tag types so a write to per-workload data doesn't blow
    // away the global cache and vice versa.
    getApmGlobalOperations: builder.query<ApmGlobalOperationsResponse, ApmGlobalParams>({
      query: (params) => ({ url: '/apm/operations', params: cleanParams(params as any) }),
      providesTags: ['ApmGlobalOps'],
    }),
    getApmGlobalDependencies: builder.query<ApmGlobalDependenciesResponse, ApmGlobalParams>({
      query: (params) => ({ url: '/apm/dependencies', params: cleanParams(params as any) }),
      providesTags: ['ApmGlobalEdges'],
    }),
  }),
});

export const {
  useGetApmServicesQuery,
  useGetApmOperationsQuery,
  useGetApmServiceStatsQuery,
  useGetApmServiceDependenciesQuery,
  useGetApmGlobalOperationsQuery,
  useGetApmGlobalDependenciesQuery,
} = apmApi;
