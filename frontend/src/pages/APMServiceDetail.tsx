/**
 * APMServiceDetail — Phase 2.7
 *
 * Detailed RED metrics view for a single service
 * (workload_key = "namespace/workload"):
 *   - RED chart (5min buckets: rate + error rate + p95 latency)
 *   - Operations tab — RED breakdown by HTTP method+path / gRPC service+method
 *   - Dependencies tab — upstream/downstream service list
 *   - Traces tab — deep-link into Trace Explorer with `?workload=`
 *
 * Backend:
 *   /api/v1/apm/services/{workload_key}/stats
 *   /api/v1/apm/services/{workload_key}/operations
 *   /api/v1/apm/services/{workload_key}/dependencies
 *
 * Backwards compatibility: the Trace Explorer link uses the existing
 * `workload` query param (not a new one), so the legacy Trace Explorer
 * behaviour stays intact.
 */
import React, { useMemo } from 'react';
import {
  Card,
  Tabs,
  Space,
  Typography,
  Tag,
  Empty,
  Alert,
  Button,
  Descriptions,
  Table,
  Spin,
  Tooltip,
} from 'antd';
import {
  ArrowLeftOutlined,
  ApiOutlined,
  ImportOutlined,
  ExportOutlined,
  ArrowRightOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import dayjs from 'dayjs';
import {
  useGetApmServiceStatsQuery,
  useGetApmOperationsQuery,
  useGetApmServiceDependenciesQuery,
  ApmOperation,
  ApmDependency,
} from '../store/api/apmApi';
import ClusterBadge from '../components/Common/ClusterBadge';
import useClusterColors from '../hooks/useClusterColors';

const { Text, Title } = Typography;

const formatLatency = (ms: number): string => {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}μs`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const formatRate = (count: number): string => {
  if (count < 1000) return `${count}`;
  if (count < 1000000) return `${(count / 1000).toFixed(1)}K`;
  return `${(count / 1000000).toFixed(2)}M`;
};

const latencyTagColor = (ms: number): string => {
  if (!ms) return 'default';
  if (ms < 100) return 'success';
  if (ms < 500) return 'processing';
  if (ms < 2000) return 'warning';
  return 'error';
};

interface DependencyCardProps {
  dep: ApmDependency;
  direction: 'upstream' | 'downstream';
  onOpen: (key: string) => void;
  // Audit fix: parent passes `true` when the neighbour list spans
  // multiple clusters so each card can disambiguate which cluster
  // the edge originated from. Single-cluster analyses suppress the
  // badge to keep the card compact.
  showCluster?: boolean;
}

/**
 * DependencyCard — Plan v3 Akış C m.5.
 *
 * Single neighbour card used by both upstream and downstream columns.
 * Replaces the old inline div-of-tags layout with a discoverable,
 * keyboard-accessible card pattern (Datadog Service Catalog / Honeycomb
 * Service Inventory style):
 *   - Hover state communicates clickability (border + subtle lift).
 *   - Focus ring for keyboard users (`tabIndex=0` + Enter/Space → onOpen).
 *   - Health dot derived from p95 + error_rate so an operator can scan
 *     the column visually for hot edges.
 *   - Right chevron + caption explains the navigation target ("Open
 *     service detail") so the affordance isn't ambiguous.
 *
 * The card itself is intentionally compact (single card, one line per
 * data point) so eight neighbours fit on the screen without scrolling.
 */
const healthColorFromMetrics = (errorRate: number, p95Ms: number): string => {
  if (errorRate > 0.05 || p95Ms >= 2000) return '#ff4d4f';
  if (errorRate > 0.01 || p95Ms >= 500) return '#faad14';
  return '#52c41a';
};

const DependencyCard: React.FC<DependencyCardProps> = ({
  dep,
  direction,
  onOpen,
  showCluster,
}) => {
  const { getClusterInfo } = useClusterColors();
  const clusterInfo =
    showCluster && dep.cluster_id ? getClusterInfo(Number(dep.cluster_id)) : null;
  const [hover, setHover] = React.useState(false);
  // Audit fix: explicit focus state. Inline styles can't reach
  // `:focus-visible`, so without an `onFocus`/`onBlur` listener
  // keyboard users would lose the visual cue when the Tab key
  // moves between cards (we removed the browser default to keep
  // the hover/focus cue uniform).
  const [focused, setFocused] = React.useState(false);
  const healthColor = healthColorFromMetrics(dep.error_rate, dep.latency_p95_ms);
  const directionLabel = direction === 'upstream' ? 'Caller' : 'Callee';
  const isActive = hover || focused;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen(dep.workload_key);
    }
  };

  const healthTitle =
    dep.error_rate > 0.05
      ? `High error rate: ${(dep.error_rate * 100).toFixed(1)}%`
      : dep.latency_p95_ms >= 500
        ? `Elevated p95 latency: ${formatLatency(dep.latency_p95_ms)}`
        : 'Healthy';

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(dep.workload_key)}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      aria-label={`Open ${directionLabel.toLowerCase()} ${dep.workload_key} (rate ${formatRate(dep.request_count)}, p95 ${formatLatency(dep.latency_p95_ms)}, health ${healthTitle.toLowerCase()})`}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        border: `1px solid ${isActive ? '#1677ff' : 'var(--ant-color-border-secondary, #f0f0f0)'}`,
        borderRadius: 8,
        cursor: 'pointer',
        background: isActive ? 'rgba(22, 119, 255, 0.04)' : 'var(--ant-color-bg-container, #fff)',
        boxShadow: focused
          ? '0 0 0 2px rgba(22, 119, 255, 0.25)'
          : hover
            ? '0 2px 8px rgba(0, 0, 0, 0.06)'
            : 'none',
        transition: 'all 120ms ease-out',
        outline: 'none',
      }}
    >
      <Tooltip title={healthTitle}>
        <span
          aria-hidden
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: healthColor,
            flexShrink: 0,
          }}
        />
      </Tooltip>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontWeight: 600,
            fontSize: 13,
            color: 'var(--ant-color-text, #262626)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {dep.workload || '(unknown)'}
        </div>
        <div
          style={{
            fontSize: 11,
            color: 'var(--ant-color-text-secondary, #8c8c8c)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {dep.namespace || '—'}
        </div>
        {showCluster && dep.cluster_id ? (
          <div style={{ marginTop: 4 }}>
            <ClusterBadge
              clusterId={Number(dep.cluster_id) || 0}
              clusterName={clusterInfo?.name || `Cluster ${dep.cluster_id}`}
              environment={clusterInfo?.environment}
              size="small"
            />
          </div>
        ) : null}
        <Space size={4} style={{ marginTop: 4 }}>
          <Tooltip title={`${dep.request_count.toLocaleString()} requests`}>
            <Tag style={{ fontSize: 10, margin: 0 }}>
              {formatRate(dep.request_count)} req
            </Tag>
          </Tooltip>
          {dep.error_count > 0 && (
            <Tooltip title={`${dep.error_count.toLocaleString()} errors`}>
              <Tag color="error" style={{ fontSize: 10, margin: 0 }}>
                {(dep.error_rate * 100).toFixed(1)}% err
              </Tag>
            </Tooltip>
          )}
          <Tooltip title="95th percentile latency">
            <Tag color={latencyTagColor(dep.latency_p95_ms)} style={{ fontSize: 10, margin: 0 }}>
              p95 {formatLatency(dep.latency_p95_ms)}
            </Tag>
          </Tooltip>
        </Space>
      </div>
      <RightOutlined
        style={{
          color: isActive ? '#1677ff' : '#bfbfbf',
          fontSize: 12,
          flexShrink: 0,
          transition: 'color 120ms ease-out',
        }}
      />
    </div>
  );
};

interface MiniServiceMapProps {
  workloadKey: string;
  upstream: ApmDependency[];
  downstream: ApmDependency[];
  onNeighbourClick: (key: string) => void;
}

/**
 * MiniServiceMap — Plan v3 Akış C m.5 redesign.
 *
 * Three-pane layout that mirrors the request flow direction:
 *
 *   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
 *   │   Upstream   │ →  │  This service│ →  │  Downstream  │
 *   │   (callers)  │    │              │    │   (callees)  │
 *   └──────────────┘    └──────────────┘    └──────────────┘
 *
 * Each card is keyboard-accessible (DependencyCard above) and the
 * directional language is unambiguous — "callers" for who sends
 * requests TO this service, "callees" for who this service sends
 * requests TO. The header pill underneath each column reinforces this
 * with an explicit caption (e.g. "Send requests to this service").
 *
 * Empty states explain why the column might be empty (e.g. external
 * traffic ingress, leaf service) so the operator doesn't mistake an
 * empty column for "no data".
 */
const MiniServiceMap: React.FC<MiniServiceMapProps> = ({
  workloadKey,
  upstream,
  downstream,
  onNeighbourClick,
}) => {
  const [, workloadOnly] = workloadKey.split('/');

  // Audit fix (multi-cluster): when neighbours come from more than one
  // cluster (multi-cluster analyses, shared mesh) we surface the cluster
  // badge on each card. For single-cluster analyses we hide the badge to
  // keep the card compact — the parent service detail header already
  // shows the owning cluster.
  const allClusterIds = React.useMemo(() => {
    const ids = new Set<string>();
    for (const dep of [...upstream, ...downstream]) {
      if (dep.cluster_id) ids.add(dep.cluster_id);
    }
    return ids;
  }, [upstream, downstream]);
  const showCluster = allClusterIds.size > 1;

  const renderColumn = (
    title: string,
    caption: string,
    icon: React.ReactNode,
    items: ApmDependency[],
    direction: 'upstream' | 'downstream',
    emptyHint: string,
  ) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ marginBottom: 12 }}>
        <Space size={6}>
          {icon}
          <Text strong style={{ fontSize: 14 }}>
            {title}
          </Text>
          <Tag style={{ marginLeft: 4 }}>{items.length}</Tag>
        </Space>
        <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>{caption}</div>
      </div>
      {items.length === 0 ? (
        <div
          style={{
            padding: 16,
            border: '1px dashed var(--ant-color-border, #d9d9d9)',
            borderRadius: 8,
            textAlign: 'center',
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            {emptyHint}
          </Text>
        </div>
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {items.slice(0, 8).map((dep) => (
            <DependencyCard
              key={`${direction}-${dep.cluster_id || ''}-${dep.workload_key}`}
              dep={dep}
              direction={direction}
              onOpen={onNeighbourClick}
              showCluster={showCluster}
            />
          ))}
          {items.length > 8 && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              +{items.length - 8} more — open the full Service Map for the complete graph
            </Text>
          )}
        </Space>
      )}
    </div>
  );

  return (
    <div>
      {/* Legend strip — tiny health dot key so the operator doesn't have
          to hover every dot to learn what red/yellow/green mean. */}
      <div style={{ marginBottom: 16, fontSize: 11, color: '#8c8c8c' }}>
        <Space size={12}>
          <span>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#52c41a', marginRight: 4 }} />
            Healthy
          </span>
          <span>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#faad14', marginRight: 4 }} />
            Elevated p95 / error rate
          </span>
          <span>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#ff4d4f', marginRight: 4 }} />
            Hot — needs attention
          </span>
        </Space>
      </div>

      <div style={{ display: 'flex', alignItems: 'stretch', gap: 16 }}>
        {renderColumn(
          'Upstream',
          'Send requests TO this service',
          <ImportOutlined style={{ color: '#1677ff' }} />,
          upstream,
          'upstream',
          'No upstream callers observed. This service may be an ingress entry point or only called externally.',
        )}

        {/* Center pane — directional arrows on either side make the flow
            unambiguous (left-to-right reads as "calls flow this way"). */}
        <div
          style={{
            flex: '0 0 240px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'flex-start',
            paddingTop: 56,
          }}
        >
          <Space size={4} style={{ color: '#bfbfbf', fontSize: 11, marginBottom: 8 }}>
            <ArrowRightOutlined />
            <Text type="secondary">request flow</Text>
            <ArrowRightOutlined />
          </Space>
          <div
            style={{
              padding: '14px 18px',
              border: '2px solid #1677ff',
              borderRadius: 12,
              background: 'linear-gradient(135deg, rgba(22, 119, 255, 0.08) 0%, rgba(22, 119, 255, 0.02) 100%)',
              boxShadow: '0 4px 16px rgba(22, 119, 255, 0.15)',
              textAlign: 'center',
              width: '100%',
            }}
          >
            <ApiOutlined style={{ color: '#1677ff', fontSize: 18, marginBottom: 4 }} />
            <div style={{ fontWeight: 600, fontSize: 14, wordBreak: 'break-word' }}>
              {workloadOnly || workloadKey}
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              this service
            </Text>
          </div>
        </div>

        {renderColumn(
          'Downstream',
          'This service sends requests TO',
          <ExportOutlined style={{ color: '#722ed1' }} />,
          downstream,
          'downstream',
          'No downstream callees observed. This service may be a leaf node (no outbound L7 calls) or its outbound traffic is not captured.',
        )}
      </div>
    </div>
  );
};

const APMServiceDetail: React.FC = () => {
  const { workloadKey } = useParams<{ workloadKey: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const analysisId = searchParams.get('analysis_id') || '';
  const clusterId = searchParams.get('cluster_id') || undefined;
  const { getClusterInfo } = useClusterColors();

  const decodedKey = useMemo(() => {
    if (!workloadKey) return '';
    // `decodeURIComponent` throws URIError on malformed escape
    // sequences (e.g. `%E0` without a valid UTF-8 continuation).
    // A user pasting a hand-crafted URL would otherwise crash the
    // page; falling back to the raw segment lets the downstream
    // API call respond with a clean 404 / "not found" instead.
    try {
      return decodeURIComponent(workloadKey);
    } catch {
      return workloadKey;
    }
  }, [workloadKey]);

  const { data: stats, isFetching: statsFetching, error: statsError } =
    useGetApmServiceStatsQuery(
      { workload_key: decodedKey, analysis_id: analysisId, cluster_id: clusterId },
      { skip: !decodedKey || !analysisId },
    );

  const { data: ops, isFetching: opsFetching, error: opsError } = useGetApmOperationsQuery(
    { workload_key: decodedKey, analysis_id: analysisId, cluster_id: clusterId, limit: 100 },
    { skip: !decodedKey || !analysisId },
  );

  const {
    data: deps,
    isFetching: depsFetching,
    error: depsError,
  } = useGetApmServiceDependenciesQuery(
    { workload_key: decodedKey, analysis_id: analysisId, cluster_id: clusterId },
    { skip: !decodedKey || !analysisId },
  );

  // Pre-format chart data (recharts wants its X axis as a primitive).
  const chartData = useMemo(
    () =>
      (stats?.buckets || []).map((b) => ({
        time: dayjs(b.timestamp).format('HH:mm'),
        rate: b.request_count,
        errors: b.error_count,
        p50: b.latency_p50_ms,
        p95: b.latency_p95_ms,
        p99: b.latency_p99_ms,
      })),
    [stats?.buckets],
  );

  // Aggregate top-level summary across all 5min buckets — convenient
  // header pill so operators don't need to mentally sum the chart.
  const summary = useMemo(() => {
    if (!stats?.buckets?.length) return null;
    const totalRate = stats.buckets.reduce((a, b) => a + (b.request_count || 0), 0);
    const totalErrors = stats.buckets.reduce((a, b) => a + (b.error_count || 0), 0);
    const maxP95 = Math.max(...stats.buckets.map((b) => b.latency_p95_ms || 0));
    return {
      totalRate,
      totalErrors,
      errorRate: totalRate > 0 ? totalErrors / totalRate : 0,
      maxP95,
    };
  }, [stats?.buckets]);

  const opColumns = [
    {
      title: 'Protocol',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 90,
      render: (v: string) => <Tag color={v === 'HTTP' ? 'blue' : 'purple'}>{v}</Tag>,
    },
    {
      title: 'Method',
      dataIndex: 'method',
      key: 'method',
      width: 110,
    },
    {
      title: 'Operation',
      dataIndex: 'operation',
      key: 'operation',
      ellipsis: true,
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
      width: 130,
      align: 'right' as const,
      render: (_: any, r: ApmOperation) => {
        if (r.error_count === 0) return <Tag>0</Tag>;
        return (
          <Tag color={r.error_rate > 0.05 ? 'error' : 'warning'}>
            {formatRate(r.error_count)} ({(r.error_rate * 100).toFixed(1)}%)
          </Tag>
        );
      },
    },
    {
      title: 'p50',
      dataIndex: 'latency_p50_ms',
      key: 'p50',
      width: 100,
      align: 'right' as const,
      render: (v: number) => <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>,
    },
    {
      title: 'p95',
      dataIndex: 'latency_p95_ms',
      key: 'p95',
      width: 110,
      align: 'right' as const,
      render: (v: number) => <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>,
    },
    {
      title: 'p99',
      dataIndex: 'latency_p99_ms',
      key: 'p99',
      width: 110,
      align: 'right' as const,
      render: (v: number) => <Tag color={latencyTagColor(v)}>{formatLatency(v || 0)}</Tag>,
    },
  ];

  if (!decodedKey || !analysisId) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="warning"
          showIcon
          message="Missing parameters"
          description="This page requires both workload_key and analysis_id. Click a service from the APM Services List."
          action={
            <Button onClick={() => navigate('/apm/services')}>Back to APM Services</Button>
          }
        />
      </div>
    );
  }

  const navigateToNeighbour = (key: string) => {
    const params = new URLSearchParams();
    params.set('analysis_id', analysisId);
    if (clusterId) params.set('cluster_id', clusterId);
    navigate(`/apm/services/${encodeURIComponent(key)}?${params.toString()}`);
  };

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(`/apm/services?analysis_id=${analysisId}`)}
        >
          APM Services
        </Button>
        <Title level={3} style={{ margin: 0 }}>
          {decodedKey}
        </Title>
        <Tag color="blue">analysis #{analysisId}</Tag>
        {clusterId && (() => {
          const info = getClusterInfo(clusterId);
          return (
            <ClusterBadge
              clusterId={Number(clusterId) || 0}
              clusterName={info?.name || `Cluster ${clusterId}`}
              environment={info?.environment}
              size="default"
            />
          );
        })()}
      </Space>

      {summary && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="Total Rate">
              <Text strong>{formatRate(summary.totalRate)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Total Errors">
              <Tag color={summary.errorRate > 0.05 ? 'error' : summary.errorRate > 0 ? 'warning' : 'default'}>
                {formatRate(summary.totalErrors)} ({(summary.errorRate * 100).toFixed(2)}%)
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Peak p95">
              <Tag color={latencyTagColor(summary.maxP95)}>{formatLatency(summary.maxP95)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="MV Granularity">5 minutes</Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {statsError ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="Failed to load RED metrics"
          description={
            (statsError as any)?.data?.detail ||
            'No APM RED MV data. Has the clickhouse_005_add_apm_red_mvs.sql migration been applied?'
          }
        />
      ) : statsFetching ? (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin />
          </div>
        </Card>
      ) : chartData.length > 0 ? (
        <Card title="RED Metrics (5-minute buckets)" size="small" style={{ marginBottom: 16 }}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" fontSize={11} />
              <YAxis yAxisId="left" fontSize={11} />
              <YAxis yAxisId="right" orientation="right" fontSize={11} />
              <RechartsTooltip />
              <Legend />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="rate"
                stroke="#1677ff"
                name="Rate"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="errors"
                stroke="#ff4d4f"
                name="Errors"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="p95"
                stroke="#faad14"
                name="p95 latency (ms)"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="p99"
                stroke="#f5222d"
                name="p99 latency (ms)"
                strokeWidth={1}
                strokeDasharray="3 3"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      ) : (
        <Card style={{ marginBottom: 16 }}>
          <Empty description="No 5-minute MV data yet for this service (the first bucket appears ~5 minutes after collection starts)" />
        </Card>
      )}

      <Card>
        <Tabs
          items={[
            {
              key: 'operations',
              label: `Operations ${ops?.operations?.length ? `(${ops.operations.length})` : ''}`,
              children: opsError ? (
                <Alert
                  type="error"
                  showIcon
                  message="Failed to load operations"
                  description={
                    (opsError as any)?.data?.detail ||
                    'Could not read operation RED MV data. The clickhouse_005 migration may not be applied.'
                  }
                />
              ) : (
                <Table<ApmOperation>
                  rowKey={(r) => `${r.protocol}|${r.method}|${r.operation}`}
                  size="small"
                  columns={opColumns}
                  dataSource={ops?.operations || []}
                  loading={opsFetching}
                  pagination={{ pageSize: 25, showSizeChanger: false }}
                  locale={{
                    emptyText: <Empty description="No operation RED data" />,
                  }}
                />
              ),
            },
            {
              key: 'dependencies',
              label: `Dependencies ${
                deps?.upstream?.length || deps?.downstream?.length
                  ? `(${(deps?.upstream?.length || 0) + (deps?.downstream?.length || 0)})`
                  : ''
              }`,
              children: depsError ? (
                <Alert
                  type="error"
                  showIcon
                  message="Failed to load dependency map"
                  description={
                    (depsError as any)?.data?.detail ||
                    'Could not read service dependency list. The clickhouse_005 migration may not be applied.'
                  }
                />
              ) : depsFetching ? (
                <div style={{ textAlign: 'center', padding: 60 }}>
                  <Spin />
                </div>
              ) : (
                <MiniServiceMap
                  workloadKey={decodedKey}
                  upstream={deps?.upstream || []}
                  downstream={deps?.downstream || []}
                  onNeighbourClick={navigateToNeighbour}
                />
              ),
            },
            {
              key: 'traces',
              label: 'Traces',
              children: (
                <Empty
                  description={
                    <Space direction="vertical" align="center">
                      <Text>Open the trace list for this service in the Trace Explorer.</Text>
                      <Button
                        type="primary"
                        onClick={() => {
                          const params = new URLSearchParams();
                          params.set('analysis_id', analysisId);
                          // Use legacy `workload` param so the existing
                          // src OR dst filter applies — gives the operator
                          // every trace this service appears in.
                          const wl = decodedKey.split('/')[1] || decodedKey;
                          params.set('workload', wl);
                          navigate(`/discovery/trace-explorer?${params.toString()}`);
                        }}
                      >
                        Open in Trace Explorer
                      </Button>
                    </Space>
                  }
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default APMServiceDetail;
