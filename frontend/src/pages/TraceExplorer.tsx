/**
 * TraceExplorer — list and inspect distributed traces collected by Beyla.
 *
 * Phase 1A redesign:
 * - Advanced filter bar (src/dst workload, operation, min latency, error-only, time range).
 * - Latency histogram (recharts BarChart) computed from the visible page's
 *   `max_latency_ms` distribution; gives operators an at-a-glance view of
 *   tail latency without an extra round-trip.
 * - Four-tab layout: Traces (current table), Operations / Services /
 *   Dependencies (cross-link out to the dedicated APM pages added in Phase 2;
 *   the same data is rendered there with full RED chart + dependency map).
 *
 * Backwards compatibility:
 * - URL deep-link `/discovery/trace-explorer?trace_id=...` still resolves
 *   the trace cluster-wide (TraceDetailDrawer keeps its old behaviour).
 * - The legacy `?workload=` and `?analysis_id=` query parameters keep
 *   working — they are read on mount and merged with the new filters.
 * - Calling backend `list_l7_traces` with only `analysis_id` reproduces the
 *   pre-Phase-1A query, so older bookmarks are not broken.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Card,
  Select,
  Input,
  Button,
  Table,
  Space,
  Typography,
  Tag,
  Empty,
  Alert,
  Drawer,
  Spin,
  Descriptions,
  Tabs,
  Switch,
  InputNumber,
  DatePicker,
  Collapse,
  Tooltip,
  message as antdMessage,
} from 'antd';
import { SearchOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import dayjs, { Dayjs } from 'dayjs';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import {
  useGetL7TraceQuery,
  useGetL7RecentTracesQuery,
  RecentTrace,
  RecentTracesParams,
} from '../store/api/l7EventsApi';
import {
  useGetApmServicesQuery,
  useGetApmGlobalOperationsQuery,
  useGetApmGlobalDependenciesQuery,
  ApmService,
  ApmGlobalOperation,
  ApmGlobalEdge,
} from '../store/api/apmApi';
import { isL7Compatible } from '../utils/analysisFilters';
import TraceWaterfall from '../components/trace/TraceWaterfall';
import ClusterBadge from '../components/Common/ClusterBadge';
import useClusterColors from '../hooks/useClusterColors';
import { useDebounce } from '../hooks/useDebounce';

const { Text, Title } = Typography;
const { RangePicker } = DatePicker;

// Log-scale buckets (ms). Chosen to span the typical Beyla L7 latency range
// (sub-ms for hot path, multi-second for slow chains) while keeping the
// histogram readable on a single 60-bar canvas.
const LATENCY_BUCKETS: { label: string; min: number; max: number }[] = [
  { label: '<1ms', min: 0, max: 1 },
  { label: '1-5ms', min: 1, max: 5 },
  { label: '5-10ms', min: 5, max: 10 },
  { label: '10-50ms', min: 10, max: 50 },
  { label: '50-100ms', min: 50, max: 100 },
  { label: '100-500ms', min: 100, max: 500 },
  { label: '500ms-1s', min: 500, max: 1000 },
  { label: '1-5s', min: 1000, max: 5000 },
  { label: '5-30s', min: 5000, max: 30000 },
  { label: '>30s', min: 30000, max: Number.POSITIVE_INFINITY },
];

const bucketColor = (bucketIdx: number, hasErrors: boolean): string => {
  // Cool → warm gradient by bucket position so tail latency is visually obvious.
  // Errors override with red.
  if (hasErrors) return '#ff4d4f';
  const palette = ['#52c41a', '#73d13d', '#a0d911', '#fadb14', '#faad14', '#fa8c16', '#ff7a45', '#ff4d4f', '#cf1322', '#820014'];
  return palette[Math.min(bucketIdx, palette.length - 1)];
};

interface HistogramBucket {
  label: string;
  count: number;
  errors: number;
}

const computeHistogram = (traces: RecentTrace[]): HistogramBucket[] => {
  return LATENCY_BUCKETS.map((b) => {
    const inBucket = traces.filter((t) => {
      const lat = t.max_latency_ms || 0;
      return lat >= b.min && lat < b.max;
    });
    return {
      label: b.label,
      count: inBucket.length,
      errors: inBucket.filter((t) => (t.error_count || 0) > 0).length,
    };
  });
};

const TraceExplorer: React.FC = () => {
  const { data: analyses, isLoading: analysesLoading } = useGetAnalysesQuery({});
  const l7Analyses = useMemo(
    () => (analyses || []).filter((a) => isL7Compatible(a)),
    [analyses],
  );

  // Cluster lookup helpers (Plan v3 Akış A — m.1, m.6).
  // `useClusterColors` is shared across the app so this hook is cheap and the
  // returned helpers gracefully fall back to `Cluster {id}` for clusters that
  // were deleted between the time a trace was ingested and the time the
  // operator views it (B1.7).
  const { getClusterInfo, getClusterName, getShortLabel } = useClusterColors();

  // URL-synced state so an operator can deep-link or bookmark a specific trace
  // (e.g. share `?analysis_id=42&trace_id=abc123` with their team after an
  // incident). All Phase 1A filters also persist to the URL so a complex
  // search query is shareable verbatim.
  const [searchParams, setSearchParams] = useSearchParams();
  const [analysisId, setAnalysisId] = useState<string>(
    () => searchParams.get('analysis_id') || '',
  );
  // Multi-cluster narrowing — distinct from analysis_id because the DB
  // writes the bare numeric analysis_id even when an analysis spans
  // multiple clusters; cluster_id is the query-time filter that picks
  // a single cluster's slice. Empty string = "all clusters in this
  // analysis". Persisted to the URL so cluster-scoped views are
  // shareable just like the rest of the filter set.
  const [clusterFilter, setClusterFilter] = useState<string>(
    () => searchParams.get('cluster_id') || '',
  );
  const [workloadFilter, setWorkloadFilter] = useState<string>(
    () => searchParams.get('workload') || '',
  );
  // Phase 1A — new advanced filters. Each defaults to empty/false so the
  // URL stays clean for operators using the basic flow.
  const [srcWorkload, setSrcWorkload] = useState<string>(
    () => searchParams.get('src_workload') || '',
  );
  const [dstWorkload, setDstWorkload] = useState<string>(
    () => searchParams.get('dst_workload') || '',
  );
  const [operation, setOperation] = useState<string>(
    () => searchParams.get('operation') || '',
  );
  const [minLatencyMs, setMinLatencyMs] = useState<number | null>(() => {
    const v = searchParams.get('min_latency_ms');
    return v ? Number(v) : null;
  });
  // Plan v3 Akış B m.3 (B1.1, B1.2): trace-level upper bound for the
  // histogram bucket click. Persisted to the URL alongside min_latency_ms
  // so the deep-link reproduces the bucket selection exactly.
  const [maxLatencyMs, setMaxLatencyMs] = useState<number | null>(() => {
    const v = searchParams.get('max_latency_ms');
    return v ? Number(v) : null;
  });
  // Histogram bucket click state. `selectedBucket = null` means "no
  // bucket selected"; once a bucket is picked we back up the operator's
  // current manual min/max so the "Clear bucket" CTA can restore them.
  // The histogram itself reads `selectedBucket` to highlight the active
  // bar.
  const [selectedBucket, setSelectedBucket] = useState<string | null>(
    () => searchParams.get('bucket') || null,
  );
  const [prevManualMin, setPrevManualMin] = useState<number | null>(null);
  const [prevManualMax, setPrevManualMax] = useState<number | null>(null);
  const [errorOnly, setErrorOnly] = useState<boolean>(
    () => searchParams.get('error_only') === 'true',
  );
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(() => {
    const s = searchParams.get('start_time');
    const e = searchParams.get('end_time');
    if (s || e) return [s ? dayjs(s) : null, e ? dayjs(e) : null];
    return null;
  });
  // Plan v3 Akış B m.4 — global free-form search. Debounced 300ms (B4.3)
  // before being sent to the backend so an operator typing a path doesn't
  // hammer the API. The raw value drives the input UI, the debounced
  // value drives the query.
  const [globalQuery, setGlobalQuery] = useState<string>(
    () => searchParams.get('q') || '',
  );
  const debouncedGlobalQuery = useDebounce(globalQuery, 300);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(() => {
    const t = searchParams.get('trace_id');
    return t && /^[0-9a-fA-F]{1,32}$/.test(t) ? t.toLowerCase() : null;
  });
  const [activeTab, setActiveTab] = useState<string>(
    () => searchParams.get('tab') || 'traces',
  );
  const [page, setPage] = useState<number>(1);
  const pageSize = 25;

  // Reflect state changes into the URL so the URL is shareable. `replace: true`
  // avoids polluting the history stack on every keystroke (workload filter).
  useEffect(() => {
    const next = new URLSearchParams();
    if (analysisId) next.set('analysis_id', analysisId);
    if (clusterFilter) next.set('cluster_id', clusterFilter);
    if (workloadFilter) next.set('workload', workloadFilter);
    if (srcWorkload) next.set('src_workload', srcWorkload);
    if (dstWorkload) next.set('dst_workload', dstWorkload);
    if (operation) next.set('operation', operation);
    if (minLatencyMs != null) next.set('min_latency_ms', String(minLatencyMs));
    if (maxLatencyMs != null) next.set('max_latency_ms', String(maxLatencyMs));
    if (selectedBucket) next.set('bucket', selectedBucket);
    if (errorOnly) next.set('error_only', 'true');
    if (timeRange?.[0]) next.set('start_time', timeRange[0].toISOString());
    if (timeRange?.[1]) next.set('end_time', timeRange[1].toISOString());
    if (debouncedGlobalQuery) next.set('q', debouncedGlobalQuery);
    if (selectedTraceId) next.set('trace_id', selectedTraceId);
    if (activeTab && activeTab !== 'traces') next.set('tab', activeTab);
    setSearchParams(next, { replace: true });
  }, [
    analysisId,
    clusterFilter,
    workloadFilter,
    srcWorkload,
    dstWorkload,
    operation,
    minLatencyMs,
    maxLatencyMs,
    selectedBucket,
    errorOnly,
    timeRange,
    debouncedGlobalQuery,
    selectedTraceId,
    activeTab,
    setSearchParams,
  ]);

  const queryParams: RecentTracesParams | null = analysisId
    ? {
        analysis_id: analysisId,
        cluster_id: clusterFilter || undefined,
        workload: workloadFilter || undefined,
        src_workload: srcWorkload || undefined,
        dst_workload: dstWorkload || undefined,
        operation: operation || undefined,
        min_latency_ms: minLatencyMs ?? undefined,
        max_latency_ms: maxLatencyMs ?? undefined,
        error_only: errorOnly || undefined,
        start_time: timeRange?.[0]?.toISOString(),
        end_time: timeRange?.[1]?.toISOString(),
        q: debouncedGlobalQuery || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }
    : null;

  const skip = !queryParams;
  const { data, isFetching, error, refetch } = useGetL7RecentTracesQuery(
    queryParams || ({ analysis_id: '' } as RecentTracesParams),
    { skip },
  );

  // Plan v3 Akış B m.2 — Trace Explorer "Operations" / "Services" /
  // "Dependencies" tabs. Each tab pulls its own RED MV aggregate so
  // the operator sees the same dataset filtered by the same scope as
  // the Traces tab. We only fire the request once the operator has
  // actually opened the tab (lazy via `skip = activeTab !== 'foo'`)
  // to avoid spending ClickHouse cycles on tabs nobody is looking at.
  //
  // Latency / time / workload filters are intentionally NOT applied
  // to these aggregates because the RED MVs are pre-rolled at 5-min
  // granularity and don't carry trace-level fields like
  // `min_latency_ms`. Forcing them here would silently drop rows the
  // operator can't see in the Traces tab. We surface the filter
  // coverage in the tab header chip so the operator knows.
  const apmGlobalParams = analysisId
    ? {
        analysis_id: analysisId,
        cluster_id: clusterFilter || undefined,
        q: debouncedGlobalQuery || undefined,
        limit: 50,
      }
    : null;

  const skipServices = skip || activeTab !== 'services';
  const {
    data: servicesData,
    isFetching: servicesFetching,
    error: servicesError,
    refetch: refetchServices,
  } = useGetApmServicesQuery(
    apmGlobalParams
      ? {
          analysis_id: apmGlobalParams.analysis_id,
          cluster_id: apmGlobalParams.cluster_id,
          q: apmGlobalParams.q,
          sort_by: 'rate',
          limit: 50,
        }
      : ({ analysis_id: '' } as any),
    { skip: skipServices },
  );

  const skipOperations = skip || activeTab !== 'operations';
  const {
    data: operationsData,
    isFetching: operationsFetching,
    error: operationsError,
    refetch: refetchOperations,
  } = useGetApmGlobalOperationsQuery(
    apmGlobalParams || ({ analysis_id: '' } as any),
    { skip: skipOperations },
  );

  const skipDependencies = skip || activeTab !== 'dependencies';
  const {
    data: dependenciesData,
    isFetching: dependenciesFetching,
    error: dependenciesError,
    refetch: refetchDependencies,
  } = useGetApmGlobalDependenciesQuery(
    apmGlobalParams || ({ analysis_id: '' } as any),
    { skip: skipDependencies },
  );

  // Plan v3 (audit fix): the previous Refresh button only refetched the
  // traces query, leaving operators staring at stale data when they were
  // sitting on the Operations / Services / Dependencies tab. We dispatch
  // refetch to whichever tab is active so a single click matches the
  // operator's intuition. RTK Query refetch is a no-op when the query is
  // skipped so we don't need to gate per-tab.
  const refreshActiveTab = useCallback(() => {
    switch (activeTab) {
      case 'services':
        refetchServices();
        break;
      case 'operations':
        refetchOperations();
        break;
      case 'dependencies':
        refetchDependencies();
        break;
      case 'traces':
      default:
        refetch();
    }
  }, [activeTab, refetch, refetchServices, refetchOperations, refetchDependencies]);

  const histogramData = useMemo(
    () => computeHistogram(data?.traces || []),
    [data?.traces],
  );

  // Plan v3 Akış B m.4 — Smart search dispatcher.
  // The single search box doubles as a trace_id navigator AND a free-form
  // filter (`q`). Pressing Enter / clicking Search routes by content:
  //   1. W3C traceparent header pasted in full → extract trace_id segment
  //      and open the trace drawer.
  //   2. 1–32 hex chars (matches the W3C trace_id format) → treat as
  //      direct trace_id lookup; opens the drawer if found.
  //   3. Anything else → already debounced into `globalQuery`/`q`; no-op
  //      here (the table refresh kicks in via the debounce path), so we
  //      just surface a small toast confirming the filter is active.
  // Empty input is short-circuited with an info toast so the operator
  // can't accidentally fire an unscoped search.
  const handleSmartSearch = () => {
    const raw = globalQuery.trim();
    if (!raw) {
      antdMessage.info('Type a trace_id, traceparent header, or text to search.');
      return;
    }
    let v = raw;
    const traceparent = v.match(/^([0-9a-fA-F]{2})-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-([0-9a-fA-F]{2})$/);
    if (traceparent) {
      v = traceparent[2];
    }
    if (/^[0-9a-fA-F]{1,32}$/.test(v) && (v.length === 16 || v.length === 32 || traceparent)) {
      // Looks like a real trace_id (16- or 32-hex), or was extracted from
      // a full traceparent header. Open the drawer directly.
      setSelectedTraceId(v.toLowerCase());
      return;
    }
    // Free-form search: the debounced value is already in flight via
    // `debouncedGlobalQuery` -> `q`. We surface a small toast so the
    // operator gets feedback that hitting Enter wasn't a no-op.
    antdMessage.info(`Filtering by "${raw}". Results update automatically.`);
  };

  const resetFilters = () => {
    setClusterFilter('');
    setWorkloadFilter('');
    setSrcWorkload('');
    setDstWorkload('');
    setOperation('');
    setMinLatencyMs(null);
    setMaxLatencyMs(null);
    setSelectedBucket(null);
    setPrevManualMin(null);
    setPrevManualMax(null);
    setErrorOnly(false);
    setTimeRange(null);
    setGlobalQuery('');
    setPage(1);
  };

  // Plan v3 Akış B m.3 (B1.1 fix): histogram bucket click handler. We
  // back up whatever the operator had typed manually (so a "Clear bucket"
  // CTA can restore it) and then drive the backend with the bucket's
  // [min, max) bounds. Manual min/max inputs are disabled while a bucket
  // is selected to prevent the two filter sources from fighting.
  const handleBucketClick = (label: string, min: number, max: number) => {
    if (selectedBucket === label) {
      // Clicking the same bucket again clears the selection and restores
      // the operator's previous manual values.
      setSelectedBucket(null);
      setMinLatencyMs(prevManualMin);
      setMaxLatencyMs(prevManualMax);
      setPrevManualMin(null);
      setPrevManualMax(null);
      setPage(1);
      return;
    }
    if (selectedBucket === null) {
      // First-time bucket selection — snapshot manual values for restore.
      setPrevManualMin(minLatencyMs);
      setPrevManualMax(maxLatencyMs);
    }
    setSelectedBucket(label);
    setMinLatencyMs(min);
    // The largest bucket is `>30s` (max = +Infinity in the bucket table).
    // Sending Infinity to the backend would serialise as "Infinity" and
    // fail validation; we send `undefined` so the upper bound is open
    // (still bounded by min_latency_ms).
    setMaxLatencyMs(Number.isFinite(max) ? max : null);
    setPage(1);
  };

  const clearBucket = () => {
    setSelectedBucket(null);
    setMinLatencyMs(prevManualMin);
    setMaxLatencyMs(prevManualMax);
    setPrevManualMin(null);
    setPrevManualMax(null);
    setPage(1);
  };

  const activeFilterCount =
    (clusterFilter ? 1 : 0) +
    (workloadFilter ? 1 : 0) +
    (srcWorkload ? 1 : 0) +
    (dstWorkload ? 1 : 0) +
    (operation ? 1 : 0) +
    (minLatencyMs != null ? 1 : 0) +
    (maxLatencyMs != null ? 1 : 0) +
    (selectedBucket ? 1 : 0) +
    (errorOnly ? 1 : 0) +
    (timeRange ? 1 : 0) +
    (debouncedGlobalQuery ? 1 : 0);

  // Cluster options derived from the selected analysis. Multi-cluster
  // analyses expose `cluster_ids: [15, 16]` plus a `cluster_id` for the
  // owning cluster; single-cluster analyses only have `cluster_id`. We
  // always show the dropdown so the operator can see which cluster(s)
  // are in scope, but it's only meaningfully interactive when there
  // are 2+ clusters.
  const clusterOptions = useMemo(() => {
    if (!analysisId) return [];
    const a = (analyses || []).find((x) => String(x.id) === String(analysisId));
    if (!a) return [];
    const ids: Array<string | number> = (a as any).cluster_ids?.length
      ? (a as any).cluster_ids
      : (a as any).cluster_id != null
      ? [(a as any).cluster_id]
      : [];
    return ids.map((id) => {
      // Resolve human-friendly cluster name; if the cluster has been
      // deleted (or not yet loaded) `getClusterName` returns
      // `Cluster {id}` — same fallback we use everywhere so the UI never
      // shows an empty label.
      const name = getClusterName(id);
      const short = getShortLabel(id);
      const label =
        short && short !== name && !short.startsWith('C')
          ? `${name} (${short})`
          : name;
      return {
        value: String(id),
        label,
      };
    });
  }, [analyses, analysisId, getClusterName, getShortLabel]);

  // Defensive: clear `clusterFilter` when it isn't a member of the
  // currently-selected analysis's cluster list. This case fires when
  // an operator deep-links with a stale URL (e.g.
  // `?analysis_id=42&cluster_id=15` where analysis 42 only covers
  // cluster 20). Without this guard the request would be sent with a
  // non-matching cluster_id, the API would return zero traces, and
  // the dropdown wouldn't even render (single-cluster path) so the
  // operator would have no UI handle to clear the bogus filter.
  // Skipped while analyses are still loading (clusterOptions empty
  // before the API responds) so we don't drop a valid value.
  useEffect(() => {
    if (!clusterFilter) return;
    if (clusterOptions.length === 0) return;
    const ok = clusterOptions.some((o) => o.value === clusterFilter);
    if (!ok) {
      setClusterFilter('');
    }
  }, [clusterFilter, clusterOptions]);

  const columns = [
    {
      title: 'Trace ID',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 280,
      render: (v: string) => (
        <Button type="link" onClick={() => setSelectedTraceId(v)} style={{ padding: 0 }}>
          <code>{v.length > 32 ? `${v.slice(0, 32)}…` : v}</code>
        </Button>
      ),
    },
    {
      title: 'Start',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: 'Duration',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (v: number) => `${(v || 0).toFixed(2)} ms`,
    },
    {
      title: 'Spans',
      dataIndex: 'span_count',
      key: 'span_count',
      width: 80,
      align: 'right' as const,
    },
    {
      title: 'Errors',
      dataIndex: 'error_count',
      key: 'error_count',
      width: 80,
      align: 'right' as const,
      render: (v: number) => (v > 0 ? <Tag color="error">{v}</Tag> : <Tag>0</Tag>),
    },
    {
      title: 'Max Latency',
      dataIndex: 'max_latency_ms',
      key: 'max_latency_ms',
      width: 130,
      render: (v: number) => `${(v || 0).toFixed(2)} ms`,
    },
    {
      title: 'Clusters',
      dataIndex: 'clusters',
      key: 'clusters',
      // Defensive: backend writes the cluster_id list directly from the
      // ClickHouse trace summary; very old rows can have empty strings or
      // nulls (especially during the multi-cluster migration), so we filter
      // them out before rendering — otherwise `<ClusterBadge>` would render
      // a blank chip with no tooltip and confuse operators (B1.8).
      render: (v: string[]) => (
        <Space size={4} wrap>
          {(v || [])
            .filter((c) => c !== null && c !== undefined && c !== '')
            .map((c) => {
              const info = getClusterInfo(c);
              return (
                <ClusterBadge
                  key={c}
                  clusterId={Number(c) || 0}
                  clusterName={info?.name || `Cluster ${c}`}
                  environment={info?.environment}
                  size="small"
                />
              );
            })}
        </Space>
      ),
    },
  ];

  // Plan v3 Akış B m.2 — Operations / Services / Dependencies tabs.
  //
  // The previous implementation rendered an Empty cross-link to the
  // dedicated APM Services page, which was confusing: operators saw
  // empty tabs while the Traces tab showed hundreds of rows. We now
  // render a compact RED summary inline (top-50) using the same MVs
  // that power the APM page, scoped to the same analysis_id /
  // cluster_id / q as the Traces tab.
  //
  // We still surface a "Open in full APM" affordance per tab so the
  // operator can pivot to the dedicated workflow (RED time-series
  // chart, dependency map, etc.) without losing context.

  // Filter coverage chip — communicates which Trace Explorer filters
  // are *not* applied to the RED MV-backed tabs (5-min rollups don't
  // carry trace-level latency or time-window). Without this an
  // operator who set min_latency_ms=500 might wrongly assume the
  // Operations tab is also filtered to the slow tail.
  const apmFilterCoverage = useMemo(() => {
    const ignored: string[] = [];
    if (workloadFilter || srcWorkload || dstWorkload) ignored.push('workload');
    if (operation) ignored.push('operation');
    if (minLatencyMs != null || maxLatencyMs != null || selectedBucket)
      ignored.push('latency');
    if (errorOnly) ignored.push('errors-only');
    if (timeRange?.[0] || timeRange?.[1]) ignored.push('time-range');
    return ignored;
  }, [
    workloadFilter,
    srcWorkload,
    dstWorkload,
    operation,
    minLatencyMs,
    maxLatencyMs,
    selectedBucket,
    errorOnly,
    timeRange,
  ]);

  const apmCoverageBanner = apmFilterCoverage.length > 0 ? (
    <Alert
      type="info"
      showIcon
      style={{ marginBottom: 12 }}
      message="Aggregate view"
      description={
        <Text type="secondary" style={{ fontSize: 12 }}>
          This tab uses 5-minute RED metric rollups, so the following
          Trace-level filters are NOT applied here:{' '}
          <strong>{apmFilterCoverage.join(', ')}</strong>. Cluster, search
          (<code>q</code>) and analysis scope are preserved. Pivot to the
          full APM Services page for per-operation drill-downs.
        </Text>
      }
    />
  ) : null;

  // Compact RED stat formatters — "1.2k" style for rate, percent for
  // error_rate, "ms" suffix for percentiles. Keeps the table scannable.
  const fmtCount = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
  };
  const fmtMs = (n: number) => `${Math.round(n)} ms`;
  const fmtErrorRate = (rate: number) => `${(rate * 100).toFixed(1)}%`;

  // Pivot to APM Services (single-service detail) without losing the
  // analysis_id; cluster_id is also forwarded so the Service Detail
  // page opens in the same scope.
  const apmServiceDetailUrl = (workloadKey: string) => {
    const p = new URLSearchParams();
    if (analysisId) p.set('analysis_id', analysisId);
    if (clusterFilter) p.set('cluster_id', clusterFilter);
    return `/apm/services/${encodeURIComponent(workloadKey)}?${p.toString()}`;
  };
  const apmServicesUrl = () => {
    const p = new URLSearchParams();
    if (analysisId) p.set('analysis_id', analysisId);
    if (clusterFilter) p.set('cluster_id', clusterFilter);
    if (debouncedGlobalQuery) p.set('q', debouncedGlobalQuery);
    return `/apm/services?${p.toString()}`;
  };

  // Renderers per tab — kept inline (rather than separate components)
  // because each is small and the parent supplies all the closures
  // (cluster colors, smart-search dispatcher) anyway.
  const renderEmptyState = (
    primary: string,
    secondary?: string,
  ) => (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <div>
          <div>{primary}</div>
          {secondary && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {secondary}
            </Text>
          )}
        </div>
      }
    />
  );

  const renderServicesTab = () => {
    if (servicesError) {
      return (
        <Alert
          type="error"
          showIcon
          message="Failed to load services"
          description={
            (servicesError as any)?.data?.detail ||
            (servicesError as any)?.error ||
            'Unexpected error'
          }
        />
      );
    }
    const rows = servicesData?.services || [];
    return (
      <>
        {apmCoverageBanner}
        <Table<ApmService>
          rowKey={(r) => `${r.cluster_id}|${r.workload_key}`}
          dataSource={rows}
          loading={servicesFetching}
          pagination={false}
          size="small"
          columns={[
            {
              title: 'Service',
              dataIndex: 'workload_key',
              render: (key: string, record) => (
                <Space size={4}>
                  <Link to={apmServiceDetailUrl(key)}>{record.dst_workload}</Link>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {record.dst_namespace}
                  </Text>
                </Space>
              ),
            },
            {
              title: 'Cluster',
              dataIndex: 'cluster_id',
              width: 140,
              render: (cid: string) => {
                if (!cid) return <Text type="secondary">—</Text>;
                const info = getClusterInfo(Number(cid));
                return (
                  <ClusterBadge
                    clusterId={Number(cid) || 0}
                    clusterName={info?.name || `Cluster ${cid}`}
                    environment={info?.environment}
                    size="small"
                  />
                );
              },
            },
            {
              title: 'Rate',
              dataIndex: 'request_count',
              width: 90,
              align: 'right' as const,
              sorter: (a, b) => a.request_count - b.request_count,
              defaultSortOrder: 'descend' as const,
              render: (n: number) => fmtCount(n),
            },
            {
              title: 'Errors',
              dataIndex: 'error_rate',
              width: 90,
              align: 'right' as const,
              sorter: (a, b) => a.error_rate - b.error_rate,
              render: (rate: number, record) => (
                <Text type={record.error_count > 0 ? 'danger' : undefined}>
                  {fmtErrorRate(rate)}
                </Text>
              ),
            },
            {
              title: 'p50',
              dataIndex: 'latency_p50_ms',
              width: 80,
              align: 'right' as const,
              render: (n: number) => fmtMs(n),
            },
            {
              title: 'p95',
              dataIndex: 'latency_p95_ms',
              width: 80,
              align: 'right' as const,
              sorter: (a, b) => a.latency_p95_ms - b.latency_p95_ms,
              render: (n: number) => fmtMs(n),
            },
            {
              title: 'p99',
              dataIndex: 'latency_p99_ms',
              width: 80,
              align: 'right' as const,
              render: (n: number) => fmtMs(n),
            },
          ]}
          locale={{
            emptyText: renderEmptyState(
              'No services match the current scope.',
              'Try widening the analysis or clearing the cluster/search filters.',
            ),
          }}
        />
        <div style={{ textAlign: 'right', marginTop: 12 }}>
          <Link to={apmServicesUrl()}>Open in APM Services →</Link>
        </div>
      </>
    );
  };

  const renderOperationsTab = () => {
    if (operationsError) {
      return (
        <Alert
          type="error"
          showIcon
          message="Failed to load operations"
          description={
            (operationsError as any)?.data?.detail ||
            (operationsError as any)?.error ||
            'Unexpected error'
          }
        />
      );
    }
    const rows = operationsData?.operations || [];
    return (
      <>
        {apmCoverageBanner}
        <Table<ApmGlobalOperation>
          rowKey={(r) =>
            `${r.protocol}|${r.cluster_id}|${r.workload_key}|${r.method}|${r.operation}`
          }
          dataSource={rows}
          loading={operationsFetching}
          pagination={false}
          size="small"
          columns={[
            {
              title: 'Operation',
              dataIndex: 'operation',
              render: (op: string, record) => (
                <Space size={4}>
                  <Tag color={record.protocol === 'GRPC' ? 'purple' : 'geekblue'}>
                    {record.protocol}
                  </Tag>
                  {record.method && record.protocol === 'HTTP' && (
                    <Tag>{record.method}</Tag>
                  )}
                  <Text code>{op}</Text>
                </Space>
              ),
            },
            {
              title: 'Service',
              dataIndex: 'workload_key',
              width: 220,
              render: (key: string, record) => (
                <Link to={apmServiceDetailUrl(key)}>
                  {record.workload}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                    {record.namespace}
                  </Text>
                </Link>
              ),
            },
            {
              title: 'Rate',
              dataIndex: 'request_count',
              width: 90,
              align: 'right' as const,
              sorter: (a, b) => a.request_count - b.request_count,
              defaultSortOrder: 'descend' as const,
              render: (n: number) => fmtCount(n),
            },
            {
              title: 'Errors',
              dataIndex: 'error_rate',
              width: 90,
              align: 'right' as const,
              render: (rate: number, record) => (
                <Text type={record.error_count > 0 ? 'danger' : undefined}>
                  {fmtErrorRate(rate)}
                </Text>
              ),
            },
            {
              title: 'p95',
              dataIndex: 'latency_p95_ms',
              width: 80,
              align: 'right' as const,
              render: (n: number) => fmtMs(n),
            },
          ]}
          locale={{
            emptyText: renderEmptyState(
              'No operations match the current scope.',
              'Operations come from the RED operations MV; if the trace list is non-empty but this is empty, the MV may still be building.',
            ),
          }}
        />
      </>
    );
  };

  const renderDependenciesTab = () => {
    if (dependenciesError) {
      return (
        <Alert
          type="error"
          showIcon
          message="Failed to load dependencies"
          description={
            (dependenciesError as any)?.data?.detail ||
            (dependenciesError as any)?.error ||
            'Unexpected error'
          }
        />
      );
    }
    const rows = dependenciesData?.edges || [];
    return (
      <>
        {apmCoverageBanner}
        <Table<ApmGlobalEdge>
          rowKey={(r) =>
            `${r.cluster_id}|${r.src_workload_key}|${r.dst_workload_key}`
          }
          dataSource={rows}
          loading={dependenciesFetching}
          pagination={false}
          size="small"
          columns={[
            {
              title: 'Source',
              dataIndex: 'src_workload_key',
              render: (_: string, r) => (
                <Link to={apmServiceDetailUrl(r.src_workload_key)}>
                  {r.src_workload}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                    {r.src_namespace}
                  </Text>
                </Link>
              ),
            },
            {
              title: '',
              key: 'arrow',
              width: 32,
              align: 'center' as const,
              render: () => <Text type="secondary">→</Text>,
            },
            {
              title: 'Destination',
              dataIndex: 'dst_workload_key',
              render: (_: string, r) => (
                <Link to={apmServiceDetailUrl(r.dst_workload_key)}>
                  {r.dst_workload}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                    {r.dst_namespace}
                  </Text>
                </Link>
              ),
            },
            {
              title: 'Cluster',
              dataIndex: 'cluster_id',
              width: 140,
              render: (cid: string) => {
                if (!cid) return <Text type="secondary">—</Text>;
                const info = getClusterInfo(Number(cid));
                return (
                  <ClusterBadge
                    clusterId={Number(cid) || 0}
                    clusterName={info?.name || `Cluster ${cid}`}
                    environment={info?.environment}
                    size="small"
                  />
                );
              },
            },
            {
              title: 'Rate',
              dataIndex: 'request_count',
              width: 90,
              align: 'right' as const,
              sorter: (a, b) => a.request_count - b.request_count,
              defaultSortOrder: 'descend' as const,
              render: (n: number) => fmtCount(n),
            },
            {
              title: 'Errors',
              dataIndex: 'error_rate',
              width: 90,
              align: 'right' as const,
              render: (rate: number, r) => (
                <Text type={r.error_count > 0 ? 'danger' : undefined}>
                  {fmtErrorRate(rate)}
                </Text>
              ),
            },
            {
              title: 'p95',
              dataIndex: 'latency_p95_ms',
              width: 80,
              align: 'right' as const,
              render: (n: number) => fmtMs(n),
            },
          ]}
          locale={{
            emptyText: renderEmptyState(
              'No service-to-service edges in scope.',
              'Edges require both sides of the call to be observed by Beyla; check that both source and destination workloads are in the analysis namespaces.',
            ),
          }}
        />
      </>
    );
  };

  return (
    <div style={{ padding: 24 }}>
      <Title level={3} style={{ marginBottom: 4 }}>
        Trace Explorer
      </Title>
      <Text type="secondary">
        W3C Distributed Tracing — inspect HTTP / gRPC traces collected by Beyla.
      </Text>

      <Card style={{ marginTop: 16 }}>
        <Space wrap>
          <Select
            placeholder="Select an L7 analysis"
            value={analysisId || undefined}
            onChange={(v) => {
              setAnalysisId(v);
              setPage(1);
              // Close any open trace drawer; the trace_id likely belongs to
              // the previous analysis and would 404 on refetch.
              setSelectedTraceId(null);
              // Plan v3 Akış B m.4 — also clear the smart-search box so a
              // free-form query from the previous analysis (e.g. a path that
              // no longer exists) doesn't carry over and silently produce
              // an empty result.
              setGlobalQuery('');
              // Drop the cluster filter — the new analysis very likely
              // covers a different set of clusters and a stale value
              // would show "0 traces" with no obvious cause.
              setClusterFilter('');
            }}
            style={{ width: 320 }}
            loading={analysesLoading}
            options={l7Analyses.map((a) => ({
              value: String(a.id),
              label: `#${a.id} — ${a.name || 'unnamed'} (${a.status})`,
            }))}
            showSearch
            optionFilterProp="label"
          />
          {/*
            Plan v3 Akış B m.4 — single smart search input.

            Datadog/Honeycomb/New Relic all use a single prominent search
            input that auto-detects identifiers vs free text. We mirror
            that pattern: paste a trace_id or traceparent header → opens
            the trace drawer; type anything else → filters the table /
            tab data via the `q` query param (debounced 300ms).

            The tooltip is the operator's discoverability hook for the
            two modes; the prefix icon stays static so the input doesn't
            "flicker" between modes as the operator types.
          */}
          <Tooltip
            title={
              <div style={{ maxWidth: 280 }}>
                <div><strong>Smart search</strong></div>
                <div style={{ marginTop: 4 }}>
                  Paste a trace_id (1–32 hex) or full W3C traceparent header to
                  open a trace directly.
                </div>
                <div style={{ marginTop: 4 }}>
                  Type anything else to filter all tabs (Traces, Operations,
                  Services, Dependencies) by workload, namespace, HTTP path,
                  gRPC method, etc.
                </div>
              </div>
            }
          >
            <Input
              placeholder="Search trace_id, workload, path, service…"
              value={globalQuery}
              onChange={(e) => {
                setGlobalQuery(e.target.value);
                setPage(1);
              }}
              onPressEnter={handleSmartSearch}
              allowClear
              prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
              style={{ width: 360 }}
            />
          </Tooltip>
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSmartSearch}>
            Search
          </Button>
          <Tooltip title={`Refresh the ${activeTab} tab data`}>
            <Button
              icon={<ReloadOutlined />}
              onClick={refreshActiveTab}
              disabled={skip}
              loading={
                (activeTab === 'traces' && isFetching) ||
                (activeTab === 'services' && servicesFetching) ||
                (activeTab === 'operations' && operationsFetching) ||
                (activeTab === 'dependencies' && dependenciesFetching)
              }
            >
              Refresh
            </Button>
          </Tooltip>
        </Space>
      </Card>

      {analysisId && (
        <Card style={{ marginTop: 16 }} bodyStyle={{ padding: 0 }}>
          <Collapse
            ghost
            defaultActiveKey={activeFilterCount > 0 ? ['filters'] : []}
            items={[
              {
                key: 'filters',
                label: (
                  <Space>
                    <FilterOutlined />
                    <Text strong>Advanced Filters</Text>
                    {activeFilterCount > 0 && (
                      <Tag color="blue">{activeFilterCount} active</Tag>
                    )}
                  </Space>
                ),
                children: (
                  <div style={{ padding: '0 16px 16px 16px' }}>
                    <Space wrap size={[12, 12]} style={{ width: '100%' }}>
                      {clusterOptions.length > 1 && (
                        <Select
                          placeholder="All clusters"
                          value={clusterFilter || undefined}
                          onChange={(v) => {
                            setClusterFilter(v || '');
                            setPage(1);
                          }}
                          allowClear
                          style={{ width: 160 }}
                          options={clusterOptions}
                        />
                      )}
                      <Input
                        placeholder="Workload (src OR dst)"
                        value={workloadFilter}
                        onChange={(e) => {
                          setWorkloadFilter(e.target.value);
                          setPage(1);
                        }}
                        allowClear
                        style={{ width: 200 }}
                      />
                      <Input
                        placeholder="Source workload (src only)"
                        value={srcWorkload}
                        onChange={(e) => {
                          setSrcWorkload(e.target.value);
                          setPage(1);
                        }}
                        allowClear
                        style={{ width: 220 }}
                      />
                      <Input
                        placeholder="Destination workload (dst only)"
                        value={dstWorkload}
                        onChange={(e) => {
                          setDstWorkload(e.target.value);
                          setPage(1);
                        }}
                        allowClear
                        style={{ width: 240 }}
                      />
                      <Input
                        placeholder="Operation (HTTP path / gRPC method)"
                        value={operation}
                        onChange={(e) => {
                          setOperation(e.target.value);
                          setPage(1);
                        }}
                        allowClear
                        style={{ width: 260 }}
                      />
                      <InputNumber
                        placeholder="Min latency (ms)"
                        value={minLatencyMs ?? undefined}
                        onChange={(v) => {
                          setMinLatencyMs(v != null ? Number(v) : null);
                          setPage(1);
                        }}
                        min={0}
                        step={10}
                        style={{ width: 160 }}
                        // B1.1: while a histogram bucket is active the
                        // bucket's [min, max) range owns the latency
                        // filter — disabling manual input prevents two
                        // sources of truth fighting and clears the data
                        // loss bug where typing here would silently
                        // overwrite the bucket bound.
                        disabled={selectedBucket !== null}
                      />
                      <InputNumber
                        placeholder="Max latency (ms)"
                        value={maxLatencyMs ?? undefined}
                        onChange={(v) => {
                          setMaxLatencyMs(v != null ? Number(v) : null);
                          setPage(1);
                        }}
                        min={0}
                        step={10}
                        style={{ width: 160 }}
                        disabled={selectedBucket !== null}
                      />
                      <Space>
                        <Text>Errors only</Text>
                        <Switch
                          checked={errorOnly}
                          onChange={(v) => {
                            setErrorOnly(v);
                            setPage(1);
                          }}
                        />
                      </Space>
                      <RangePicker
                        showTime
                        value={timeRange as any}
                        onChange={(v) => {
                          setTimeRange(v as [Dayjs | null, Dayjs | null] | null);
                          setPage(1);
                        }}
                        style={{ width: 380 }}
                      />
                      {activeFilterCount > 0 && (
                        <Button onClick={resetFilters}>Clear Filters</Button>
                      )}
                    </Space>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {!analysisId ? (
        <Card style={{ marginTop: 16 }}>
          <Empty description="Select an L7 analysis to continue" />
        </Card>
      ) : (
        <>
          {/* Latency histogram — client-side bucketing of the visible page's
              `max_latency_ms`. Phase 2's RED MVs already store
              quantileTDigestState which a future backend endpoint can use to
              compute a higher-fidelity, server-paginated histogram across all
              traces (not just the visible page). For now the client-side
              version is sufficient for at-a-glance triage. */}
          {(data?.traces?.length ?? 0) > 0 && (
            <Card
              size="small"
              style={{ marginTop: 16 }}
              title={
                <Space>
                  <Text strong>Latency Distribution</Text>
                  <Text type="secondary" style={{ fontWeight: 'normal', fontSize: 12 }}>
                    (current page, n={data?.traces?.length || 0})
                  </Text>
                  {selectedBucket && (
                    <Tag color="processing">
                      Bucket filter: {selectedBucket}
                    </Tag>
                  )}
                </Space>
              }
              extra={
                selectedBucket ? (
                  <Button size="small" onClick={clearBucket}>
                    Clear bucket
                  </Button>
                ) : (
                  <Tooltip title="Click a bar to filter traces in that latency bucket. Click the same bar again or use the manual Min/Max latency inputs to clear.">
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      Click a bar to filter
                    </Text>
                  </Tooltip>
                )
              }
            >
              <ResponsiveContainer width="100%" height={160}>
                <BarChart
                  data={histogramData}
                  margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
                >
                  <XAxis dataKey="label" fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} width={32} />
                  <RechartsTooltip
                    formatter={(value: any, name: string) => {
                      if (name === 'errors') return [value, 'Errored traces'];
                      return [value, 'Trace count'];
                    }}
                    labelFormatter={(label) => `Latency: ${label}`}
                  />
                  <Bar
                    dataKey="count"
                    name="count"
                    cursor="pointer"
                    onClick={(payload: any) => {
                      // Recharts forwards the bar payload as the first
                      // argument; the bucket index is positional in
                      // LATENCY_BUCKETS so we look it up by label.
                      const label = payload?.label;
                      if (!label) return;
                      const bucket = LATENCY_BUCKETS.find((b) => b.label === label);
                      if (!bucket) return;
                      handleBucketClick(bucket.label, bucket.min, bucket.max);
                    }}
                  >
                    {histogramData.map((b, i) => {
                      const isSelected = selectedBucket === b.label;
                      const fill = bucketColor(i, b.errors > 0);
                      return (
                        <Cell
                          key={i}
                          fill={fill}
                          // Plan v3 B5.7 (a11y): selected bucket gets a
                          // strong outline so keyboard / screen-reader
                          // users navigating the recharts node see the
                          // active filter; non-selected fade to 60%
                          // opacity to make the contrast obvious.
                          stroke={isSelected ? '#0050b3' : 'none'}
                          strokeWidth={isSelected ? 2 : 0}
                          fillOpacity={
                            selectedBucket && !isSelected ? 0.45 : 1
                          }
                        />
                      );
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          {error ? (
            <Alert
              type="error"
              showIcon
              style={{ marginTop: 16 }}
              message="Failed to load traces"
              description={(error as any)?.data?.detail || (error as any)?.error || 'Unexpected error'}
            />
          ) : (
            <Card style={{ marginTop: 16 }}>
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  {
                    key: 'traces',
                    label: `Traces ${data?.total ? `(${data.total})` : ''}`,
                    children: (
                      <Table<RecentTrace>
                        rowKey="trace_id"
                        columns={columns}
                        dataSource={data?.traces || []}
                        loading={isFetching}
                        pagination={{
                          current: page,
                          pageSize,
                          total: data?.total || 0,
                          showTotal: (total) => `${total} traces`,
                          onChange: (p) => setPage(p),
                          showSizeChanger: false,
                        }}
                        locale={{
                          emptyText: (
                            <div style={{ padding: 32 }}>
                              <Empty
                                description={
                                  <div>
                                    <div>
                                      {activeFilterCount > 0
                                        ? 'No traces match these filters.'
                                        : 'No trace data has been collected for this analysis yet.'}
                                    </div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      Trace collection requires: (1) Beyla 3.x with
                                      track_request_headers enabled, (2) W3C traceparent
                                      propagation across the monitored service chain,
                                      (3) the L7_TRACING_ENABLED environment variable set.
                                    </Text>
                                  </div>
                                }
                              />
                            </div>
                          ),
                        }}
                      />
                    ),
                  },
                  {
                    key: 'operations',
                    label: `Operations${
                      operationsData?.operations?.length
                        ? ` (${operationsData.operations.length})`
                        : ''
                    }`,
                    children: renderOperationsTab(),
                  },
                  {
                    key: 'services',
                    label: `Services${
                      servicesData?.total ? ` (${servicesData.total})` : ''
                    }`,
                    children: renderServicesTab(),
                  },
                  {
                    key: 'dependencies',
                    label: `Dependencies${
                      dependenciesData?.edges?.length
                        ? ` (${dependenciesData.edges.length})`
                        : ''
                    }`,
                    children: renderDependenciesTab(),
                  },
                ]}
              />
            </Card>
          )}
        </>
      )}

      <TraceDetailDrawer
        traceId={selectedTraceId}
        analysisId={analysisId}
        onClose={() => setSelectedTraceId(null)}
      />
    </div>
  );
};

interface TraceDetailDrawerProps {
  traceId: string | null;
  analysisId: string;
  onClose: () => void;
}

const TraceDetailDrawer: React.FC<TraceDetailDrawerProps> = ({ traceId, analysisId, onClose }) => {
  // Drawer-local cluster lookup (Plan v3 Akış A — m.1). Same hook as the
  // outer page; the underlying `useGetClustersQuery` cache is shared so
  // there's no extra network call.
  const { getClusterInfo } = useClusterColors();
  // analysisId is optional: when an operator deep-links with `?trace_id=...`
  // we still query the backend (it falls back to a cluster-wide trace lookup
  // because W3C trace IDs are unique across analyses). The previous
  // implementation skipped the query in that case and showed a misleading
  // "select an analysis" alert, but the deep-link is the canonical way to
  // share a trace from incident notes.
  const skip = !traceId;
  const { data, isFetching, error } = useGetL7TraceQuery(
    { trace_id: traceId || '', analysis_id: analysisId || undefined },
    { skip },
  );
  return (
    <Drawer
      title={
        <Space direction="vertical" size={0}>
          <Text strong>Trace Detail</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <code>{traceId}</code>
            {!analysisId && (
              <Text type="secondary" style={{ marginLeft: 8 }}>
                (searched cluster-wide)
              </Text>
            )}
          </Text>
        </Space>
      }
      width={960}
      open={Boolean(traceId)}
      onClose={onClose}
      destroyOnClose
    >
      {isFetching ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="Failed to load trace"
          description={(error as any)?.data?.detail || (error as any)?.error || 'Unexpected error'}
        />
      ) : data && data.spans?.length ? (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          {data.summary && (
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="Spans">{data.summary.span_count}</Descriptions.Item>
              <Descriptions.Item label="Total duration">
                {(data.summary.duration_ms || 0).toFixed(2)} ms
              </Descriptions.Item>
              <Descriptions.Item label="Errors">{data.summary.error_count}</Descriptions.Item>
              <Descriptions.Item label="Clusters">
                {(() => {
                  const ids = (data.summary.clusters || []).filter(
                    (c) => c !== null && c !== undefined && c !== '',
                  );
                  if (ids.length === 0) return '-';
                  return (
                    <Space size={4} wrap>
                      {ids.map((c) => {
                        const info = getClusterInfo(c);
                        return (
                          <ClusterBadge
                            key={c}
                            clusterId={Number(c) || 0}
                            clusterName={info?.name || `Cluster ${c}`}
                            environment={info?.environment}
                            size="small"
                          />
                        );
                      })}
                    </Space>
                  );
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="Services" span={2}>
                {(data.summary.services || []).join(', ') || '-'}
              </Descriptions.Item>
            </Descriptions>
          )}
          <TraceWaterfall spans={data.spans} />
        </Space>
      ) : (
        <Empty description="No spans found for this trace" />
      )}
    </Drawer>
  );
};

export default TraceExplorer;
