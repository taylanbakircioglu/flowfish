import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// W3C distributed trace span (OTLP / Beyla). Mirrors the row shape returned
// by `timeseries-query` `/l7/traces/{trace_id}`. Optional fields are present
// in HTTP rows but not gRPC, and vice versa; consumers should treat missing
// values as empty rather than throwing.
export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string;
  span_name: string;
  span_kind: number; // 1=INTERNAL 2=SERVER 3=CLIENT 4=PRODUCER 5=CONSUMER
  timestamp: string;
  analysis_id: string;
  cluster_id: string;
  cluster_name: string;
  src_namespace: string;
  src_workload: string;
  src_pod: string;
  src_ip: string;
  src_port: number;
  dst_namespace: string;
  dst_workload: string;
  dst_pod: string;
  dst_ip: string;
  dst_port: number;
  protocol: 'HTTP' | 'GRPC';
  method: string;
  path: string;
  grpc_service?: string;
  status_code: number;
  latency_ms: number;
  // Phase 4: when present, indicates this span was correlated into a
  // virtual trace by the writer's PID-temporal correlator (the producer
  // service did not propagate W3C traceparent). Defaults to '' on
  // legacy rows; consumers must treat empty as "not virtual".
  virtual_trace_id?: string;
}

export interface TraceSummary {
  trace_id: string;
  span_count: number;
  clusters: string[];
  services: string[];
  error_count: number;
  duration_ms: number;
}

export interface TraceResponse {
  trace_id: string;
  spans: TraceSpan[];
  summary: TraceSummary;
}

export interface RecentTrace {
  trace_id: string;
  start_time: string;
  end_time: string;
  span_count: number;
  error_count: number;
  max_latency_ms: number;
  duration_ms: number;
  clusters: string[];
}

export interface TracesListResponse {
  traces: RecentTrace[];
  total: number;
  limit: number;
  offset: number;
}

// Phase 3B — anchor metadata + two correlation groups returned by
// `GET /l7/events/traces/{trace_id}/related`. Used by the Trace Waterfall
// "Related Traces" tab. The same RecentTrace shape powers both groups so
// the UI can re-use the same row template.
export interface RelatedTraceAnchor {
  trace_id: string;
  timestamp: string;
  src_namespace: string;
  src_workload: string;
  src_pod: string;
  dst_namespace: string;
  dst_workload: string;
  dst_pod: string;
  cluster_id: string;
}

export interface RelatedTracesResponse {
  anchor: RelatedTraceAnchor | null;
  same_edge: RecentTrace[];
  same_pod: RecentTrace[];
  rel_type: 'same_edge' | 'same_pod' | 'both';
  time_window_minutes?: number;
}

export interface RelatedTracesParams {
  trace_id: string;
  analysis_id?: string | number | null;
  rel_type?: 'same_edge' | 'same_pod' | 'both';
  limit?: number;
  time_window_minutes?: number;
}

// Phase 1A — typed parameter shape for `useGetL7RecentTracesQuery`. Every
// filter is optional and additive; passing only `analysis_id` reproduces the
// legacy behaviour exactly. Kept in sync with backend
// `backend/routers/l7_events.py::list_l7_traces`.
//
// Plan v3 Akış B m.3 + m.4 additions:
//   - `max_latency_ms`: trace-level upper bound used by the latency
//     histogram bucket click (paired with `min_latency_ms` to scope a
//     trace to a specific log-scale bucket).
//   - `q`: free-form search across operation, workloads, namespaces and
//     trace_id (debounced 300ms on the frontend, `min_length=1` enforced
//     on the backend).
export interface RecentTracesParams {
  analysis_id: string;
  cluster_id?: string;
  workload?: string;
  src_workload?: string;
  dst_workload?: string;
  operation?: string;
  min_latency_ms?: number;
  max_latency_ms?: number;
  error_only?: boolean | 'true' | 'false';
  start_time?: string;
  end_time?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export const l7EventsApi = createApi({
  reducerPath: 'l7EventsApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['L7Events', 'L7Traces'],
  endpoints: (builder) => ({
    getL7HttpEvents: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/events/http', params }),
      providesTags: ['L7Events'],
    }),
    getL7GrpcEvents: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/events/grpc', params }),
      providesTags: ['L7Events'],
    }),
    getL7DnsEvents: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/events/dns', params }),
      providesTags: ['L7Events'],
    }),
    getL7EventStats: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/events/stats', params }),
      providesTags: ['L7Events'],
    }),
    getL7EventHistogram: builder.query<any, Record<string, any>>({
      query: (params) => ({ url: '/l7/events/histogram', params }),
      providesTags: ['L7Events'],
    }),
    // L7 Distributed Tracing (Faz 3.4)
    // analysis_id is optional so the Trace Explorer deep-link
    // (/trace-explorer?trace_id=...) can resolve a trace cluster-wide when
    // the operator only has the W3C trace ID. The backend treats an
    // omitted analysis_id as "search across all analyses".
    getL7Trace: builder.query<
      TraceResponse,
      { trace_id: string; analysis_id?: string | number | null }
    >({
      query: ({ trace_id, analysis_id }) => ({
        url: `/l7/events/traces/${encodeURIComponent(trace_id)}`,
        params:
          analysis_id !== undefined && analysis_id !== null && analysis_id !== ''
            ? { analysis_id }
            : {},
      }),
      providesTags: (_res, _err, arg) => [{ type: 'L7Traces' as const, id: arg.trace_id }],
    }),
    // Strip undefined/empty values so we don't send `?workload=` (which
    // ClickHouse would treat as an empty-string equality filter and return
    // no rows). Backward-compat with prior `Record<string, any>` callers.
    getL7RecentTraces: builder.query<TracesListResponse, RecentTracesParams>({
      query: (params) => {
        const cleaned: Record<string, any> = {};
        Object.entries(params).forEach(([k, v]) => {
          if (v === undefined || v === null || v === '') return;
          if (typeof v === 'boolean') {
            if (v) cleaned[k] = 'true';
            return;
          }
          cleaned[k] = v;
        });
        return { url: '/l7/events/traces', params: cleaned };
      },
      providesTags: ['L7Traces'],
    }),
    // Phase 3B — Related Traces. Anchor trace_id is in the path; analysis_id
    // and tunables are query params. Distinct cache entries per (trace_id,
    // rel_type) so switching tabs in the waterfall refetches as needed.
    getL7RelatedTraces: builder.query<RelatedTracesResponse, RelatedTracesParams>({
      query: ({ trace_id, analysis_id, rel_type, limit, time_window_minutes }) => {
        const params: Record<string, any> = {};
        if (analysis_id !== undefined && analysis_id !== null && analysis_id !== '') {
          params.analysis_id = analysis_id;
        }
        if (rel_type) params.rel_type = rel_type;
        if (limit !== undefined) params.limit = limit;
        if (time_window_minutes !== undefined) params.time_window_minutes = time_window_minutes;
        return {
          url: `/l7/events/traces/${encodeURIComponent(trace_id)}/related`,
          params,
        };
      },
      providesTags: (_res, _err, arg) => [
        { type: 'L7Traces' as const, id: `related-${arg.trace_id}` },
      ],
    }),
  }),
});

export const {
  useGetL7HttpEventsQuery,
  useGetL7GrpcEventsQuery,
  useGetL7DnsEventsQuery,
  useGetL7EventStatsQuery,
  useGetL7EventHistogramQuery,
  useGetL7TraceQuery,
  useGetL7RecentTracesQuery,
  useGetL7RelatedTracesQuery,
} = l7EventsApi;
