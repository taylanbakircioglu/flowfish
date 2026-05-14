/**
 * TraceWaterfall — Jaeger/Zipkin-style waterfall view for a single distributed trace.
 *
 * Phase 1B redesign:
 * - Tabbed layout: Spans (waterfall + click-to-inspect detail panel) /
 *   Errors (error-only span list) / Logs (Phase 2 placeholder) /
 *   Related Traces (Phase 3 placeholder).
 * - Service-colored bars: each unique destination workload gets a stable
 *   HSL-derived hue so a chain like A→B→C is instantly distinguishable on
 *   the waterfall.
 * - Click-to-inspect: clicking any span opens an in-panel detail view with
 *   all attributes plus a JSON tree of the raw span object — useful for
 *   debugging Beyla attribute injection without round-tripping ClickHouse.
 *
 * Backwards compatibility:
 * - Component props (`spans`, `hasActiveFilters`) are unchanged. Both
 *   callers (`TraceExplorer.tsx` and `ServiceMap.tsx::TraceDrawer`) keep
 *   working with no edits — they get the redesign automatically.
 * - The waterfall geometry (start offset / width / depth indentation) is
 *   identical to the v1 layout so any UI screenshots in playbooks match.
 */
import React, { useMemo, useState } from 'react';
import {
  Alert,
  Empty,
  Space,
  Tag,
  Tooltip,
  Typography,
  Tabs,
  Table,
  Descriptions,
  Button,
  Spin,
  Collapse,
} from 'antd';
import { CloseOutlined, LinkOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import type {
  TraceSpan,
  RecentTrace,
  RelatedTraceAnchor,
} from '../../store/api/l7EventsApi';
import { useGetL7RelatedTracesQuery } from '../../store/api/l7EventsApi';

const { Text } = Typography;

interface TraceWaterfallProps {
  spans: TraceSpan[];
  hasActiveFilters?: boolean;
}

interface SpanRow extends TraceSpan {
  startMs: number;
  durationMs: number;
  depth: number;
  hasParent: boolean;
}

const SPAN_KIND_LABEL: Record<number, string> = {
  1: 'INTERNAL',
  2: 'SERVER',
  3: 'CLIENT',
  4: 'PRODUCER',
  5: 'CONSUMER',
};

const ERROR_COLOR = '#ff4d4f';

// Stable per-service hue using DJB2-style string hash.
// Same workload key always yields the same color across renders, so a chain
// like A→B→C looks identical between waterfall, drawer, and Service Map.
const hashHue = (key: string): number => {
  let h = 5381;
  for (let i = 0; i < key.length; i += 1) {
    h = ((h << 5) + h) ^ key.charCodeAt(i);
  }
  // Avoid red hue band (0-15, 345-360) to leave red exclusively for errors.
  const hue = ((h >>> 0) % 300) + 30;
  return hue;
};

const serviceColor = (span: TraceSpan): string => {
  const key = `${span.dst_namespace || ''}/${span.dst_workload || span.dst_ip || '?'}`;
  return `hsl(${hashHue(key)}, 55%, 50%)`;
};

const formatDuration = (ms: number): string => {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}μs`;
  if (ms < 1000) return `${ms.toFixed(2)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const isErrorSpan = (s: TraceSpan): boolean =>
  (s.protocol === 'HTTP' && s.status_code >= 400) ||
  (s.protocol === 'GRPC' && s.status_code !== 0);

// Recursive JSON tree renderer — keeps the dependency surface flat (no
// react-json-view) and matches the rest of the project's antd typography.
const JsonTree: React.FC<{ value: unknown; depth?: number }> = ({ value, depth = 0 }) => {
  const indent = depth * 12;
  if (value === null) return <span style={{ color: '#bfbfbf' }}>null</span>;
  if (typeof value === 'undefined') return <span style={{ color: '#bfbfbf' }}>undefined</span>;
  if (typeof value === 'string') return <span style={{ color: '#52c41a' }}>"{value}"</span>;
  if (typeof value === 'number') return <span style={{ color: '#1677ff' }}>{value}</span>;
  if (typeof value === 'boolean') return <span style={{ color: '#722ed1' }}>{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span style={{ color: '#bfbfbf' }}>[]</span>;
    return (
      <div style={{ paddingLeft: indent }}>
        [
        {value.map((item, i) => (
          <div key={i} style={{ paddingLeft: 12 }}>
            <JsonTree value={item} depth={depth + 1} />
            {i < value.length - 1 ? ',' : ''}
          </div>
        ))}
        ]
      </div>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span style={{ color: '#bfbfbf' }}>{'{}'}</span>;
    return (
      <div style={{ paddingLeft: indent }}>
        {'{'}
        {entries.map(([k, v], i) => (
          <div key={k} style={{ paddingLeft: 12 }}>
            <span style={{ color: '#fa541c' }}>"{k}"</span>
            <span style={{ color: '#8c8c8c' }}>: </span>
            <JsonTree value={v} depth={depth + 1} />
            {i < entries.length - 1 ? ',' : ''}
          </div>
        ))}
        {'}'}
      </div>
    );
  }
  return <span>{String(value)}</span>;
};

interface SpanDetailPanelProps {
  span: TraceSpan;
  onClose: () => void;
}

const SpanDetailPanel: React.FC<SpanDetailPanelProps> = ({ span, onClose }) => {
  return (
    <div
      style={{
        width: 380,
        flexShrink: 0,
        borderLeft: '1px solid var(--ant-color-border-secondary, #d9d9d9)',
        padding: 12,
        overflowY: 'auto',
        maxHeight: 600,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text strong>Span Detail</Text>
        <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClose} />
      </div>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Protocol">
          <Tag color={span.protocol === 'HTTP' ? 'blue' : 'purple'}>{span.protocol}</Tag>
          <Tag>{SPAN_KIND_LABEL[span.span_kind] || span.span_kind}</Tag>
          {isErrorSpan(span) && <Tag color="error">{span.status_code}</Tag>}
          {!span.trace_id && span.virtual_trace_id && (
            <Tooltip title="The producing service did not propagate the W3C traceparent header. This span was attached to a virtual trace produced by the timeseries-writer's PID-temporal correlator (cluster + src_pod + container_id + pid + 50ms window -> sha1 hash).">
              <Tag color="gold">🔗 Virtual Trace</Tag>
            </Tooltip>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="span_id">
          <code style={{ fontSize: 11 }}>{span.span_id}</code>
        </Descriptions.Item>
        <Descriptions.Item label="parent_span_id">
          <code style={{ fontSize: 11 }}>{span.parent_span_id || '(root)'}</code>
        </Descriptions.Item>
        <Descriptions.Item label="trace_id">
          <code style={{ fontSize: 11 }}>{span.trace_id || '(empty — virtual)'}</code>
        </Descriptions.Item>
        {span.virtual_trace_id && (
          <Descriptions.Item label="virtual_trace_id">
            <code style={{ fontSize: 11 }}>{span.virtual_trace_id}</code>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="Timestamp">{span.timestamp}</Descriptions.Item>
        <Descriptions.Item label="Latency">{formatDuration(span.latency_ms || 0)}</Descriptions.Item>
        <Descriptions.Item label="Source">
          {span.src_namespace}/{span.src_workload || '?'}
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            pod: {span.src_pod || '-'} | {span.src_ip}:{span.src_port}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label="Destination">
          {span.dst_namespace}/{span.dst_workload || '?'}
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>
            pod: {span.dst_pod || '-'} | {span.dst_ip}:{span.dst_port}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label="Cluster">{span.cluster_name || span.cluster_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="Method">{span.method || '-'}</Descriptions.Item>
        <Descriptions.Item label="Path / Service">{span.path || span.grpc_service || '-'}</Descriptions.Item>
        <Descriptions.Item label="Status Code">{span.status_code}</Descriptions.Item>
      </Descriptions>
      <div style={{ marginTop: 12 }}>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>
          Raw JSON
        </Text>
        <div
          style={{
            fontFamily: 'monospace',
            fontSize: 11,
            background: 'var(--ant-color-bg-elevated, #fafafa)',
            padding: 8,
            borderRadius: 4,
            border: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
          }}
        >
          <JsonTree value={span} />
        </div>
      </div>
    </div>
  );
};

// Roadmap placeholder — surfaces a clear "not in this version" message rather
// than an empty pane that operators might mistake for "no data". `tag` is
// shown verbatim next to the label (typical values: "Roadmap",
// "Kapsam disi"). Decoupled from phase numbers so the UI doesn't lie about
// when a feature ships.
const FuturePlaceholder: React.FC<{ tag: string; label: string; description: string }> = ({
  tag,
  label,
  description,
}) => (
  <Empty
    style={{ padding: 48 }}
    description={
      <div>
        <Text strong style={{ display: 'block', marginBottom: 8 }}>
          {label} <Tag style={{ marginLeft: 8 }}>{tag}</Tag>
        </Text>
        <Text type="secondary">{description}</Text>
      </div>
    }
  />
);

// Phase 3C — Related Traces tab. Lives inside the waterfall's Tabs as a
// lazily-mounted child: the hook fires only once the operator clicks the
// tab, keeping the Trace Explorer's initial render cost unchanged. We
// derive trace_id and analysis_id from the first span (all spans of a
// trace share the same trace_id by definition; analysis_id is consistent
// within a trace because Beyla writes the running analysis stamp on
// every event).
interface RelatedTracesTabProps {
  traceId: string;
  analysisId?: string | null;
}

const formatRelatedDuration = (ms: number): string => {
  if (!ms || !isFinite(ms)) return '-';
  if (ms < 1) return `${(ms * 1000).toFixed(0)}μs`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

// Build a deep-link to the Trace Explorer using the *exact* route +
// query-param shape that page consumes (`/discovery/trace-explorer`,
// `analysis_id=...`, `trace_id=...`). Mirrors the pattern already used
// by `APMServiceDetail.tsx` so behaviour stays consistent across pages.
const buildTraceExplorerLink = (tid: string, analysisId?: string | null): string => {
  const params = new URLSearchParams();
  if (analysisId) params.set('analysis_id', String(analysisId));
  params.set('trace_id', tid);
  return `/discovery/trace-explorer?${params.toString()}`;
};

const relatedTraceColumns = (analysisId?: string | null) => [
  {
    title: 'Trace ID',
    dataIndex: 'trace_id',
    key: 'trace_id',
    width: 200,
    render: (tid: string) => (
      <Link to={buildTraceExplorerLink(tid, analysisId)}>
        <code style={{ fontSize: 11 }}>{tid.slice(0, 16)}…</code>
        <LinkOutlined style={{ marginLeft: 4, fontSize: 11 }} />
      </Link>
    ),
  },
  {
    title: 'Start',
    dataIndex: 'start_time',
    key: 'start_time',
    width: 200,
    render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
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
    width: 90,
    align: 'right' as const,
    render: (v: number) =>
      v > 0 ? <Tag color="error">{v}</Tag> : <Text type="secondary">0</Text>,
  },
  {
    title: 'Max latency',
    dataIndex: 'max_latency_ms',
    key: 'max_latency_ms',
    width: 110,
    align: 'right' as const,
    render: (v: number) => formatRelatedDuration(v || 0),
  },
  {
    title: 'Clusters',
    dataIndex: 'clusters',
    key: 'clusters',
    render: (cs: string[]) =>
      cs && cs.length > 0 ? (
        <Space size={[4, 4]} wrap>
          {cs.map((c) => (
            <Tag key={c}>{c}</Tag>
          ))}
        </Space>
      ) : (
        <Text type="secondary">-</Text>
      ),
  },
];

const AnchorBlock: React.FC<{ anchor: RelatedTraceAnchor }> = ({ anchor }) => (
  <div
    style={{
      padding: 12,
      marginBottom: 16,
      background: 'var(--ant-color-bg-elevated, #fafafa)',
      border: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
      borderRadius: 6,
    }}
  >
    <Text strong style={{ display: 'block', marginBottom: 8 }}>
      Anchor trace
    </Text>
    <Space size="middle" wrap>
      <span>
        <Text type="secondary">Source: </Text>
        <Text>
          {anchor.src_namespace}/{anchor.src_workload || '?'}
        </Text>
      </span>
      <span>
        <Text type="secondary">→ Destination: </Text>
        <Text>
          {anchor.dst_namespace}/{anchor.dst_workload || '?'}
        </Text>
      </span>
      <span>
        <Text type="secondary">dst_pod: </Text>
        <Text>{anchor.dst_pod || '-'}</Text>
      </span>
      <span>
        <Text type="secondary">cluster: </Text>
        <Text>{anchor.cluster_id || '-'}</Text>
      </span>
    </Space>
  </div>
);

const RelatedTracesTab: React.FC<RelatedTracesTabProps> = ({ traceId, analysisId }) => {
  const { data, isFetching, isError, error } = useGetL7RelatedTracesQuery(
    {
      trace_id: traceId,
      analysis_id: analysisId ?? undefined,
      rel_type: 'both',
      limit: 50,
      time_window_minutes: 60,
    },
    { skip: !traceId },
  );

  if (isFetching) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin tip="Loading related traces..." />
      </div>
    );
  }
  if (isError) {
    const detail = (error as any)?.data?.detail || (error as any)?.error || 'unknown error';
    return (
      <Alert
        type="error"
        showIcon
        message="Failed to load related traces"
        description={String(detail)}
      />
    );
  }
  if (!data) {
    return <Empty description="No related-trace data" />;
  }
  const { anchor, same_edge: sameEdge, same_pod: samePod, time_window_minutes: window } = data;
  if (!anchor) {
    return (
      <Empty
        description={
          <div>
            <Text strong>Anchor trace not found</Text>
            <br />
            <Text type="secondary">
              Could not fetch trace metadata — the analysis may have been deleted or
              fallen outside the retention window.
            </Text>
          </div>
        }
      />
    );
  }
  const totalCount = sameEdge.length + samePod.length;
  if (totalCount === 0) {
    return (
      <>
        <AnchorBlock anchor={anchor} />
        <Empty
          description={
            <div>
              <Text strong>No related traces for this trace</Text>
              <br />
              <Text type="secondary">
                No other traces matched the same edge or dst_pod within the last
                {' '}{window || 60} minutes. Lower load, short retention, or
                passive Beyla sampling are common explanations.
              </Text>
            </div>
          }
        />
      </>
    );
  }
  return (
    <>
      <AnchorBlock anchor={anchor} />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`Related traces in the last ${window || 60} minutes`}
        description={
          <span>
            <strong>Same-edge:</strong> traces with the same (src_workload, dst_workload) pair.
            {' '}
            <strong>Same-pod:</strong> traces hitting the same dst_pod. PID-temporal
            virtual traces are included (marked with a sha1 hash; Phase 4 correlation
            for services that do not propagate W3C trace_id).
          </span>
        }
      />
      <Collapse
        defaultActiveKey={[
          ...(sameEdge.length > 0 ? ['edge'] : []),
          ...(samePod.length > 0 ? ['pod'] : []),
        ]}
        items={[
          {
            key: 'edge',
            label: (
              <span>
                Same Edge (src_workload + dst_workload){' '}
                <Tag>{sameEdge.length}</Tag>
              </span>
            ),
            children:
              sameEdge.length > 0 ? (
                <Table<RecentTrace>
                  rowKey="trace_id"
                  size="small"
                  columns={relatedTraceColumns(analysisId)}
                  dataSource={sameEdge}
                  pagination={false}
                />
              ) : (
                <Empty description="No other traces share this edge" />
              ),
          },
          {
            key: 'pod',
            label: (
              <span>
                Same Pod (dst_pod = {anchor.dst_pod || '-'}) <Tag>{samePod.length}</Tag>
              </span>
            ),
            children:
              samePod.length > 0 ? (
                <Table<RecentTrace>
                  rowKey="trace_id"
                  size="small"
                  columns={relatedTraceColumns(analysisId)}
                  dataSource={samePod}
                  pagination={false}
                />
              ) : (
                <Empty description="No other traces share this dst_pod" />
              ),
          },
        ]}
      />
    </>
  );
};

const TraceWaterfall: React.FC<TraceWaterfallProps> = ({ spans, hasActiveFilters }) => {
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);

  const { rows, totalMs, orphanCount } = useMemo(() => {
    if (!spans || spans.length === 0) {
      return { rows: [] as SpanRow[], totalMs: 0, orphanCount: 0 };
    }

    // Compute relative time using timestamp + latency_ms. We don't have an
    // explicit `end_time` field per span, so end = start + latency.
    const parseTs = (s: string): number => {
      try {
        return new Date(s).getTime();
      } catch {
        return 0;
      }
    };

    const startTimes = spans.map((s) => parseTs(s.timestamp));
    const minStart = Math.min(...startTimes);
    const maxEnd = Math.max(
      ...spans.map((s, i) => startTimes[i] + (s.latency_ms || 0))
    );
    const totalMs = Math.max(1, maxEnd - minStart);

    // Build span_id -> span lookup for parent traversal.
    const byId = new Map<string, TraceSpan>();
    for (const s of spans) byId.set(s.span_id, s);

    const depthOf = (span: TraceSpan, seen = new Set<string>()): number => {
      if (!span.parent_span_id || seen.has(span.span_id)) return 0;
      const parent = byId.get(span.parent_span_id);
      if (!parent) return 0;
      seen.add(span.span_id);
      return 1 + depthOf(parent, seen);
    };

    let orphans = 0;
    const rows: SpanRow[] = spans.map((s, i) => {
      const startMs = startTimes[i] - minStart;
      const durationMs = s.latency_ms || 0;
      const hasParent = !!s.parent_span_id && byId.has(s.parent_span_id);
      if (s.parent_span_id && !hasParent) orphans += 1;
      return {
        ...s,
        startMs,
        durationMs,
        depth: depthOf(s),
        hasParent,
      };
    });

    rows.sort((a, b) => a.startMs - b.startMs);
    return { rows, totalMs, orphanCount: orphans };
  }, [spans]);

  const errorRows = useMemo(() => rows.filter(isErrorSpan), [rows]);

  // Phase 4 — derive virtual-trace summary so the header can flag traces
  // that came together via PID-temporal correlation rather than W3C
  // trace_id propagation. We don't toggle behaviour on this; it's a UX
  // hint so operators don't trust virtual traces as much as real ones.
  const virtualSummary = useMemo(() => {
    const total = rows.length;
    if (total === 0) return { total: 0, virtual: 0, isAll: false, isMixed: false };
    const virtual = rows.filter((r) => !!r.virtual_trace_id && !r.trace_id).length;
    return {
      total,
      virtual,
      isAll: virtual > 0 && virtual === total,
      isMixed: virtual > 0 && virtual < total,
    };
  }, [rows]);

  const selectedSpan = useMemo(
    () => (selectedSpanId ? rows.find((r) => r.span_id === selectedSpanId) ?? null : null),
    [selectedSpanId, rows],
  );

  if (!spans || spans.length === 0) {
    return <Empty description="No spans found for this trace" />;
  }

  // Service legend — unique dst_workload list with their assigned colors.
  // Helps operators map the chain at a glance before diving into spans.
  const serviceLegend = useMemo(() => {
    const seen = new Map<string, string>();
    rows.forEach((r) => {
      const key = `${r.dst_namespace || ''}/${r.dst_workload || r.dst_ip || '?'}`;
      if (!seen.has(key)) seen.set(key, serviceColor(r));
    });
    return Array.from(seen.entries());
  }, [rows]);

  const renderWaterfall = () => (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ marginBottom: 8 }}>
          <Space size="middle" wrap>
            <Text type="secondary">Total duration:</Text>
            <Text strong>{formatDuration(totalMs)}</Text>
            <Text type="secondary">Spans:</Text>
            <Text strong>{spans.length}</Text>
            {errorRows.length > 0 && (
              <Tag color="error">Errors: {errorRows.length}</Tag>
            )}
            {virtualSummary.isAll && (
              <Tooltip title="Every span in this trace was attached by the PID-temporal correlator (Phase 4) because the producing services did not propagate the W3C traceparent header. Virtual traces are usually accurate but the parent-child tree is approximate; treat them as less authoritative than real W3C traces.">
                <Tag color="gold">🔗 Virtual Trace</Tag>
              </Tooltip>
            )}
            {virtualSummary.isMixed && (
              <Tooltip title={`${virtualSummary.virtual}/${virtualSummary.total} spans were attached via the PID-temporal correlator (virtual_trace_id); the rest carry a real W3C trace_id. Mixed-source trace.`}>
                <Tag color="orange">🔗 Mixed (W3C + Virtual)</Tag>
              </Tooltip>
            )}
          </Space>
        </div>

        {serviceLegend.length > 1 && (
          <div style={{ marginBottom: 8 }}>
            <Space wrap size={[4, 4]}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                Services:
              </Text>
              {serviceLegend.map(([key, color]) => (
                <span
                  key={key}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 11,
                    padding: '0 6px',
                    border: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
                    borderRadius: 10,
                    background: 'var(--ant-color-bg-container, #fff)',
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      background: color,
                      display: 'inline-block',
                    }}
                  />
                  {key}
                </span>
              ))}
            </Space>
          </div>
        )}

        <div
          style={{
            border: '1px solid var(--ant-color-border-secondary, #d9d9d9)',
            borderRadius: 6,
            padding: 8,
            background: 'var(--ant-color-bg-container, #fff)',
          }}
        >
          {rows.map((row) => {
            const leftPct = totalMs > 0 ? (row.startMs / totalMs) * 100 : 0;
            const widthPct = totalMs > 0 ? Math.max(0.5, (row.durationMs / totalMs) * 100) : 0.5;
            const error = isErrorSpan(row);
            const color = error ? ERROR_COLOR : serviceColor(row);
            const isSelected = row.span_id === selectedSpanId;
            return (
              <div
                key={`${row.span_id}-${row.timestamp}`}
                onClick={() => setSelectedSpanId(isSelected ? null : row.span_id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '4px 4px',
                  cursor: 'pointer',
                  background: isSelected
                    ? 'var(--ant-color-fill-tertiary, #f0f7ff)'
                    : 'transparent',
                  borderRadius: 4,
                  transition: 'background 0.1s',
                }}
              >
                <div
                  style={{
                    width: 280,
                    paddingLeft: 8 + row.depth * 16,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Tooltip
                    title={
                      <div style={{ maxWidth: 320 }}>
                        <div><b>span_id:</b> {row.span_id}</div>
                        <div><b>parent_id:</b> {row.parent_span_id || '(root)'}</div>
                        <div><b>cluster:</b> {row.cluster_name || row.cluster_id || '-'}</div>
                        <div><b>src:</b> {row.src_namespace}/{row.src_workload}</div>
                        <div><b>dst:</b> {row.dst_namespace}/{row.dst_workload}</div>
                        <div><b>kind:</b> {SPAN_KIND_LABEL[row.span_kind] || row.span_kind}</div>
                        {row.span_name && <div><b>name:</b> {row.span_name}</div>}
                        <div style={{ marginTop: 4, fontStyle: 'italic' }}>Click for details</div>
                      </div>
                    }
                  >
                    <Tag color={row.protocol === 'HTTP' ? 'blue' : 'purple'} style={{ marginRight: 6 }}>
                      {row.protocol}
                    </Tag>
                    <Text strong>
                      {row.dst_workload || row.dst_namespace || '?'}
                    </Text>
                    <Text type="secondary" style={{ marginLeft: 6 }}>
                      {row.method || ''}{' '}
                      {row.path
                        ? row.path.length > 40
                          ? `${row.path.slice(0, 40)}…`
                          : row.path
                        : ''}
                    </Text>
                  </Tooltip>
                </div>
                <div style={{ flex: 1, position: 'relative', height: 20 }}>
                  <div
                    style={{
                      position: 'absolute',
                      left: `${leftPct}%`,
                      width: `${widthPct}%`,
                      height: 16,
                      top: 2,
                      background: color,
                      borderRadius: 3,
                      opacity: isSelected ? 1 : 0.85,
                      boxShadow: isSelected ? `0 0 0 2px ${color}55` : 'none',
                    }}
                  />
                </div>
                <div style={{ width: 90, textAlign: 'right', paddingRight: 8 }}>
                  <Text>{formatDuration(row.durationMs)}</Text>
                </div>
                <div style={{ width: 60, textAlign: 'right' }}>
                  {error ? (
                    <Tag color="error">{row.status_code}</Tag>
                  ) : (
                    <Tag>{row.status_code}</Tag>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {selectedSpan && (
        <SpanDetailPanel
          span={selectedSpan}
          onClose={() => setSelectedSpanId(null)}
        />
      )}
    </div>
  );

  const errorColumns = [
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 200,
    },
    {
      title: 'Service',
      key: 'service',
      render: (_: any, r: SpanRow) =>
        `${r.dst_namespace}/${r.dst_workload || r.dst_ip || '?'}`,
    },
    {
      title: 'Operation',
      key: 'op',
      render: (_: any, r: SpanRow) => `${r.method || ''} ${r.path || r.grpc_service || ''}`,
    },
    {
      title: 'Status',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 100,
      render: (v: number) => <Tag color="error">{v}</Tag>,
    },
    {
      title: 'Latency',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 110,
      render: (v: number) => formatDuration(v || 0),
    },
    {
      title: 'span_id',
      dataIndex: 'span_id',
      key: 'span_id',
      width: 200,
      render: (v: string) => (
        <Button size="small" type="link" onClick={() => setSelectedSpanId(v)} style={{ padding: 0 }}>
          <code style={{ fontSize: 11 }}>{v.slice(0, 16)}…</code>
        </Button>
      ),
    },
  ];

  return (
    <div style={{ width: '100%' }}>
      {spans.length === 1 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Trace contains only a single span"
          description="No child spans were found for this trace. Common causes: (1) the service chain is incomplete, (2) downstream services are not instrumented by Beyla, (3) sampling or filter settings dropped the children, (4) internal (non HTTP/gRPC/DNS) spans are not surfaced in this version."
        />
      )}
      {orphanCount > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="Trace may be incomplete"
          description={`${orphanCount} span(s) reference a parent that is not present in this trace. Sampling / filter settings (exclude_paths, namespace_allow), losses during Beyla restarts, or internal spans being hidden can all cause this.`}
        />
      )}
      {hasActiveFilters && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Active filters may affect trace integrity"
          description="The analysis configuration has an HTTP path/method/status or namespace filter active. Some spans of this trace may have been dropped by the filter; missing spans (if any) are reported in the warnings above."
        />
      )}

      <Tabs
        size="small"
        // Lazy-mount inactive tabs so the Related Traces tab doesn't fire
        // its (potentially expensive) ClickHouse query every time a span
        // detail drawer opens. The Spans tab is the default; the rest
        // wait for an explicit click. Also unmounts when switching back —
        // tradeoff: re-fetch on revisit, save CPU/RAM the rest of the time.
        destroyInactiveTabPane
        items={[
          {
            key: 'spans',
            label: `Spans (${spans.length})`,
            children: renderWaterfall(),
          },
          {
            key: 'errors',
            label: errorRows.length > 0
              ? <span>Errors <Tag color="error" style={{ marginLeft: 4 }}>{errorRows.length}</Tag></span>
              : 'Errors',
            children:
              errorRows.length > 0 ? (
                <Table<SpanRow>
                  rowKey={(r) => `${r.span_id}-${r.timestamp}`}
                  size="small"
                  columns={errorColumns}
                  dataSource={errorRows}
                  pagination={false}
                />
              ) : (
                <Empty description="No error spans in this trace" />
              ),
          },
          {
            key: 'logs',
            label: 'Logs',
            children: (
              <FuturePlaceholder
                tag="Roadmap"
                label="Span logs"
                description="OpenTelemetry log correlation (OTel logs SDK + Loki integration) is a separate feature on the roadmap. This tab is a placeholder — for now, copy the span timestamp and use it in the Activity Monitor / Events Timeline screen."
              />
            ),
          },
          {
            key: 'related',
            label: 'Related Traces',
            // Virtual traces (Phase 4) have empty `trace_id` but a non-empty
            // `virtual_trace_id`. The backend `get_related_traces` now accepts
            // either as the anchor, so we surface whichever is present.
            // Without this fallback the tab would dead-end on virtual traces.
            children: (() => {
              const head = rows[0];
              const anchorId = head?.trace_id || head?.virtual_trace_id || '';
              if (!anchorId) {
                return <Empty description="No trace ID available" />;
              }
              return (
                <RelatedTracesTab
                  traceId={anchorId}
                  analysisId={head?.analysis_id || null}
                />
              );
            })(),
          },
        ]}
      />
    </div>
  );
};

export default TraceWaterfall;
