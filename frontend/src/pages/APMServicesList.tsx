/**
 * APMServicesList — Phase 2.6
 *
 * Workload-level RED metrics table (similar to Datadog APM's Services List).
 * Reads the backend `/api/v1/apm/services` endpoint and renders the
 * p50/p95/p99 + rate + error rate values produced by the
 * AggregatingMergeTree RED MVs in a single table. Clicking a workload
 * navigates to the Service Detail page at `/apm/services/{key}`.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Select,
  Input,
  Table,
  Space,
  Typography,
  Tag,
  Empty,
  Alert,
  Button,
} from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import {
  useGetApmServicesQuery,
  ApmService,
} from '../store/api/apmApi';
import { isL7Compatible } from '../utils/analysisFilters';
import ClusterBadge from '../components/Common/ClusterBadge';
import useClusterColors from '../hooks/useClusterColors';

const { Text, Title } = Typography;

const formatLatency = (ms: number): string => {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}μs`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const formatRate = (count: number): string => {
  // Backend already aggregates over the analysis lifetime; we display the
  // raw count rather than a per-second rate to avoid implying a sliding
  // window we don't actually have.
  if (count < 1000) return `${count}`;
  if (count < 1000000) return `${(count / 1000).toFixed(1)}K`;
  return `${(count / 1000000).toFixed(2)}M`;
};

// Color helper for percentile cells — green/yellow/red based on common
// SLO thresholds. Falls back to default Tag for missing data.
const latencyTagColor = (ms: number): string => {
  if (!ms) return 'default';
  if (ms < 100) return 'success';
  if (ms < 500) return 'processing';
  if (ms < 2000) return 'warning';
  return 'error';
};

// Whitelist matches the backend `regex="^(rate|errors|p50|p95|p99)$"`.
// `avg` was removed because the AggregatingMergeTree state on the
// backend does not project an avg column — sorting by it produced
// "Unknown identifier" -> HTTP 500. The frontend dropdown never exposed
// `avg` either, so the only way to hit it was a hand-edited URL, which
// now falls back to the default. Hoisted out of the component so the
// Set is allocated once.
type SortBy = 'rate' | 'errors' | 'p50' | 'p95' | 'p99';
const VALID_SORTS: ReadonlySet<SortBy> = new Set<SortBy>([
  'rate', 'errors', 'p50', 'p95', 'p99',
]);

const APMServicesList: React.FC = () => {
  const navigate = useNavigate();
  const { data: analyses, isLoading: analysesLoading } = useGetAnalysesQuery({});
  const l7Analyses = useMemo(
    () => (analyses || []).filter((a) => isL7Compatible(a)),
    [analyses],
  );

  const [searchParams, setSearchParams] = useSearchParams();
  const [analysisId, setAnalysisId] = useState<string>(
    () => searchParams.get('analysis_id') || '',
  );
  const [namespace, setNamespace] = useState<string>(
    () => searchParams.get('namespace') || '',
  );
  // Cluster filter (Plan v3 Akış A m.6 / B4.2): multi-cluster analizde
  // kullanıcı tek cluster'ı izole edebilir. Empty string = "all clusters".
  const [clusterFilter, setClusterFilter] = useState<string>(
    () => searchParams.get('cluster_id') || '',
  );
  const [sortBy, setSortBy] = useState<SortBy>(() => {
    const raw = searchParams.get('sort_by');
    return raw && VALID_SORTS.has(raw as SortBy) ? (raw as SortBy) : 'rate';
  });
  const [page, setPage] = useState<number>(1);
  const pageSize = 50;

  // Cluster lookup helper (Plan v3 Akış A — getClusterInfo returns null for
  // deleted clusters; we fall back to `Cluster {id}`). `useClusterColors`
  // cache is shared across the app so this hook is cheap.
  const { getClusterInfo } = useClusterColors();

  // Cluster options for the filter dropdown — derived from the selected
  // analysis. Multi-cluster analyses expose `cluster_ids: [...]`; single-
  // cluster analyses just have `cluster_id`. We always keep the dropdown
  // potentially renderable but only show it when there are 2+ clusters
  // (otherwise it would be a one-option select with no value).
  const clusterOptions = useMemo(() => {
    if (!analysisId) return [] as Array<{ value: string; label: string }>;
    const a = (analyses || []).find((x: any) => String(x.id) === String(analysisId));
    if (!a) return [];
    const ids: Array<string | number> = (a as any).cluster_ids?.length
      ? (a as any).cluster_ids
      : (a as any).cluster_id != null
      ? [(a as any).cluster_id]
      : [];
    return ids.map((id) => {
      const info = getClusterInfo(id as any);
      const label = info?.name
        ? `${info.name}${info.shortLabel && info.shortLabel !== info.name ? ` · ${info.shortLabel}` : ''}`
        : `Cluster ${id}`;
      return { value: String(id), label };
    });
  }, [analyses, analysisId, getClusterInfo]);

  // Defensive: clear `clusterFilter` if it isn't a member of the selected
  // analysis's cluster list (handles stale deep-links like
  // `?analysis_id=42&cluster_id=99` where analysis 42 only covers cluster 20).
  useEffect(() => {
    if (!clusterFilter) return;
    if (clusterOptions.length === 0) return;
    const ok = clusterOptions.some((o) => o.value === clusterFilter);
    if (!ok) setClusterFilter('');
  }, [clusterFilter, clusterOptions]);

  // Reflect state changes into the URL so the page is shareable.
  useEffect(() => {
    const next = new URLSearchParams();
    if (analysisId) next.set('analysis_id', analysisId);
    if (namespace) next.set('namespace', namespace);
    if (clusterFilter) next.set('cluster_id', clusterFilter);
    if (sortBy && sortBy !== 'rate') next.set('sort_by', sortBy);
    setSearchParams(next, { replace: true });
  }, [analysisId, namespace, clusterFilter, sortBy, setSearchParams]);

  const skip = !analysisId;
  const { data, isFetching, error } = useGetApmServicesQuery(
    {
      analysis_id: analysisId,
      cluster_id: clusterFilter || undefined,
      namespace: namespace || undefined,
      sort_by: sortBy,
      limit: pageSize,
      offset: (page - 1) * pageSize,
    },
    { skip },
  );

  const columns = [
    {
      title: 'Cluster',
      dataIndex: 'cluster_id',
      key: 'cluster_id',
      width: 140,
      render: (v: string) => {
        if (!v) return <Text type="secondary">-</Text>;
        const info = getClusterInfo(v);
        return (
          <ClusterBadge
            clusterId={Number(v) || 0}
            clusterName={info?.name || `Cluster ${v}`}
            environment={info?.environment}
            size="small"
          />
        );
      },
    },
    {
      title: 'Namespace',
      dataIndex: 'dst_namespace',
      key: 'dst_namespace',
      width: 180,
      render: (v: string) => v || <Text type="secondary">unknown</Text>,
    },
    {
      title: 'Service',
      key: 'service',
      render: (_: any, r: ApmService) => (
        <Button
          type="link"
          onClick={() => {
            const params = new URLSearchParams();
            params.set('analysis_id', analysisId);
            // Always pass the per-row cluster_id (from server payload),
            // not the page-level filter — service detail must be tied
            // to the cluster that produced the row, even when the page
            // filter is "all clusters".
            if (r.cluster_id) params.set('cluster_id', r.cluster_id);
            navigate(`/apm/services/${encodeURIComponent(r.workload_key)}?${params.toString()}`);
          }}
          style={{ padding: 0, fontWeight: 500 }}
        >
          {r.dst_workload || '?'}
        </Button>
      ),
    },
    {
      title: 'Rate',
      dataIndex: 'request_count',
      key: 'rate',
      width: 100,
      align: 'right' as const,
      render: (v: number) => formatRate(v || 0),
    },
    {
      title: 'Errors',
      key: 'errors',
      width: 140,
      align: 'right' as const,
      render: (_: any, r: ApmService) => {
        const ratePercent = (r.error_rate * 100).toFixed(2);
        if (r.error_count === 0) {
          return <Tag>0</Tag>;
        }
        return (
          <Space>
            <Tag color={r.error_rate > 0.05 ? 'error' : 'warning'}>
              {formatRate(r.error_count)}
            </Tag>
            <Text type={r.error_rate > 0.05 ? 'danger' : 'warning'}>
              {ratePercent}%
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'p50',
      dataIndex: 'latency_p50_ms',
      key: 'p50',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (
        <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>
      ),
    },
    {
      title: 'p95',
      dataIndex: 'latency_p95_ms',
      key: 'p95',
      width: 110,
      align: 'right' as const,
      render: (v: number) => (
        <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>
      ),
    },
    {
      title: 'p99',
      dataIndex: 'latency_p99_ms',
      key: 'p99',
      width: 110,
      align: 'right' as const,
      render: (v: number) => (
        <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3} style={{ marginBottom: 4 }}>
        APM Services
      </Title>
      <Text type="secondary">
        Workload-level RED metrics (Rate / Errors / Duration). HTTP + gRPC are combined;
        p50/p95/p99 are computed via ClickHouse quantileTDigest.
      </Text>

      <Card style={{ marginTop: 16 }}>
        <Space wrap>
          <Select
            placeholder="Select an L7 analysis"
            value={analysisId || undefined}
            onChange={(v) => {
              setAnalysisId(v);
              setClusterFilter('');
              setPage(1);
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
          {clusterOptions.length > 1 && (
            <Select
              placeholder="All clusters"
              value={clusterFilter || undefined}
              onChange={(v) => {
                setClusterFilter(v || '');
                setPage(1);
              }}
              allowClear
              style={{ width: 220 }}
              options={[
                { value: '', label: 'All clusters' },
                ...clusterOptions,
              ]}
            />
          )}
          <Input
            placeholder="Namespace filter (optional)"
            value={namespace}
            onChange={(e) => {
              setNamespace(e.target.value);
              setPage(1);
            }}
            allowClear
            style={{ width: 220 }}
          />
          <Select
            value={sortBy}
            onChange={(v) => {
              setSortBy(v);
              setPage(1);
            }}
            style={{ width: 180 }}
            options={[
              { value: 'rate', label: 'Sort: Rate (DESC)' },
              { value: 'errors', label: 'Sort: Errors' },
              { value: 'p50', label: 'Sort: p50 latency' },
              { value: 'p95', label: 'Sort: p95 latency' },
              { value: 'p99', label: 'Sort: p99 latency' },
            ]}
          />
        </Space>
      </Card>

      {!analysisId ? (
        <Card style={{ marginTop: 16 }}>
          <Empty description="Select an L7 analysis to continue" />
        </Card>
      ) : error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 16 }}
          message="Failed to load APM service list"
          description={
            (error as any)?.data?.detail ||
            (error as any)?.error ||
            'Unexpected error. The APM RED MV migration may not have been applied (clickhouse_005_add_apm_red_mvs.sql).'
          }
        />
      ) : (
        <Card style={{ marginTop: 16 }}>
          <Table<ApmService>
            rowKey={(r) => `${r.cluster_id}/${r.workload_key}`}
            columns={columns}
            dataSource={data?.services || []}
            loading={isFetching}
            pagination={{
              current: page,
              pageSize,
              total: data?.total || 0,
              showTotal: (total) => `${total} services`,
              onChange: (p) => setPage(p),
              showSizeChanger: false,
            }}
            locale={{
              emptyText: (
                <div style={{ padding: 32 }}>
                  <Empty
                    description={
                      <div>
                        <div>No APM data is available for this analysis yet.</div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          The first RED metric becomes visible after ~5 minutes
                          (MV granularity = 5min). If data is not flowing: (1) verify
                          `clickhouse_005_add_apm_red_mvs.sql` has been applied,
                          (2) check that rows exist in `l7_http_flows` / `l7_grpc_flows`.
                        </Text>
                      </div>
                    }
                  />
                </div>
              ),
            }}
          />
        </Card>
      )}
    </div>
  );
};

export default APMServicesList;
