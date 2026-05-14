import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  Steps,
  Form,
  Select,
  Input,
  Button,
  Card,
  Table,
  Tag,
  Badge,
  Tabs,
  Space,
  Typography,
  Alert,
  Divider,
  Tooltip,
  message,
  Spin,
  Row,
  Col,
  Descriptions,
  Statistic,
  Radio,
  Collapse,
  theme,
} from 'antd';
import {
  ApiOutlined,
  BranchesOutlined,
  CodeOutlined,
  CheckCircleOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  RocketOutlined,
  EyeOutlined,
  ExperimentOutlined,
  KeyOutlined,
  ThunderboltOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import {
  useLazyGetDependencySummaryQuery,
  DependencySummaryParams,
  MatchedService,
} from '../store/api/communicationApi';
import CodeBlock from '../components/integration/CodeBlock';
import DependencyCategoryGroup from '../components/integration/DependencyCategoryGroup';
import {
  PIPELINE_PLATFORMS,
  ID_METHODS,
  buildCurlSnippet,
  buildPythonSnippet,
  buildJsSnippet,
  buildPipelineSnippet,
  buildL7CurlSnippet,
  buildL7PythonSnippet,
  buildL7JsSnippet,
  buildL7JavaSnippet,
  buildL7PipelineSnippet,
  buildL7TreeCurlSnippet,
  buildL7TreePythonSnippet,
  buildL7TreePipelineSnippet,
  buildBlastRadiusCurlSnippet,
  buildBlastRadiusPipelineSnippet,
} from '../utils/snippetBuilders';
import { useL4Analyses } from '../utils/analysisFilters';
import {
  useLazyGetL7DependencySummaryQuery,
  useLazyGetL7DependencyTreeSummaryQuery,
  L7DependencySummaryParams,
  L7TreeSummaryParams,
} from '../store/api/l7CommunicationApi';
import type { Analysis } from '../types';

const { Text, Title, Paragraph } = Typography;
const { Option } = Select;

type IntegrationType = 'dependency' | 'blast_radius' | null;

const EXAMPLE_BR_RESPONSE = `{
  "assessment_id": "br-20260327-abc123",
  "risk_score": 42,
  "risk_level": "medium",
  "blast_radius": {
    "total_affected": 8,
    "direct_dependencies": 3,
    "indirect_dependencies": 5,
    "critical_services": ["checkout-service"]
  },
  "recommendation": "proceed",
  "suggested_actions": [
    { "action": "Notify checkout-service team", "priority": "medium" }
  ],
  "advisory_only": true
}`;

// Audit v3 (B-30 / preview tabs): the L7 and L4 preview bodies are
// rendered in three places now — pure-L7 step, pure-L4 step, and the
// BOTH-mode dual-tab step. We pull each body into a standalone
// React.FC at module scope so:
//   * the BOTH wrapper can reuse the exact same JSX as the pure
//     branches (no drift between the three paths),
//   * the components are defined once instead of recreated on every
//     IntegrationHub render (no perf regression from inline factories).
// Both components accept the data and theme tokens as props so they
// stay decoupled from the parent hook state.

interface L7PreviewBodyProps {
  l7Summary: any;
  l7Tree: any;
  tokenPrimary: string;
}

const L7PreviewBody: React.FC<L7PreviewBodyProps> = ({ l7Summary, l7Tree, tokenPrimary }) => (
  <>
    <Card size="small" style={{ borderLeft: `3px solid ${tokenPrimary}`, marginBottom: 16 }}>
      <Row gutter={24} align="middle">
        <Col>
          <Statistic
            title="L7 Workloads"
            value={l7Summary.workloads?.length ?? l7Summary.summary?.total_matched ?? 0}
            valueStyle={{ fontSize: 28, fontWeight: 700, color: tokenPrimary }}
          />
        </Col>
        {l7Tree?.summary && (
          <>
            <Col>
              <Statistic
                title={<><ArrowDownOutlined /> Downstream</>}
                value={l7Tree.summary.total_downstream ?? 0}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
            </Col>
            <Col>
              <Statistic
                title={<><ArrowUpOutlined /> Callers</>}
                value={l7Tree.summary.total_callers ?? 0}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
            </Col>
          </>
        )}
      </Row>
    </Card>

    <Tabs
      defaultActiveKey="workloads"
      style={{ marginTop: 8 }}
      items={[
        {
          key: 'workloads',
          label: <span><ApiOutlined /> Workloads ({l7Summary.workloads?.length ?? 0})</span>,
          children: (
            <Table
              size="small"
              dataSource={l7Summary.workloads ?? []}
              rowKey={(r: any, i?: number) => `${r.namespace}-${r.name}-${i}`}
              pagination={{ pageSize: 15, showSizeChanger: true, size: 'small' }}
              scroll={{ x: 800 }}
              columns={[
                { title: 'Name', dataIndex: 'name', key: 'name', sorter: (a: any, b: any) => a.name.localeCompare(b.name), ellipsis: true,
                  // Audit v3 (E-3): when the L7 summary is filtered, the
                  // backend marks the matched workloads with is_matched=true
                  // and includes immediate neighbours with is_matched=false.
                  // Surface the flag so operators can tell which workloads
                  // came from their identification fields versus which were
                  // pulled in by adjacency.
                  render: (v: string, r: any) => (
                    <span>
                      {v}
                      {r.is_matched === false && <Tag color="default" style={{ marginLeft: 8, fontSize: 10 }}>neighbor</Tag>}
                      {r.is_matched === true && <Tag color="green" style={{ marginLeft: 8, fontSize: 10 }}>matched</Tag>}
                    </span>
                  ),
                },
                { title: 'Namespace', dataIndex: 'namespace', key: 'namespace', sorter: (a: any, b: any) => a.namespace.localeCompare(b.namespace), width: 150 },
                { title: 'Cluster', dataIndex: 'cluster', key: 'cluster', width: 110, ellipsis: true },
                { title: 'Inbound', dataIndex: 'inbound_count', key: 'inbound', width: 80, sorter: (a: any, b: any) => (a.inbound_count ?? 0) - (b.inbound_count ?? 0) },
                { title: 'Outbound', dataIndex: 'outbound_count', key: 'outbound', width: 90, sorter: (a: any, b: any) => (a.outbound_count ?? 0) - (b.outbound_count ?? 0) },
                { title: 'Requests', dataIndex: 'request_count', key: 'reqs', width: 90, sorter: (a: any, b: any) => (a.request_count ?? 0) - (b.request_count ?? 0) },
                { title: 'Errors', dataIndex: 'error_count', key: 'errs', width: 70, sorter: (a: any, b: any) => (a.error_count ?? 0) - (b.error_count ?? 0),
                  render: (v: any) => v > 0 ? <Tag color="red">{v}</Tag> : v ?? 0 },
                { title: 'Error %', dataIndex: 'error_rate_percent', key: 'errp', width: 80, sorter: (a: any, b: any) => (a.error_rate_percent ?? 0) - (b.error_rate_percent ?? 0),
                  render: (v: any) => v != null ? `${Number(v).toFixed(1)}%` : '—' },
                { title: 'Owner', dataIndex: 'owner_kind', key: 'owner', width: 100, render: (v: any) => v || '—' },
                { title: 'Labels', dataIndex: 'labels', key: 'labels', width: 200, ellipsis: true,
                  render: (v: any) => {
                    if (!v || typeof v !== 'object') return '—';
                    const entries = Object.entries(v).slice(0, 5);
                    return entries.length ? (
                      <Space wrap size={2}>{entries.map(([k, val]) => <Tag key={k} style={{ fontSize: 11, margin: 0 }}>{k}={String(val)}</Tag>)}</Space>
                    ) : '—';
                  },
                },
              ]}
            />
          ),
        },
        ...(l7Tree?.matched_services ? [{
          key: 'edges',
          label: <span><BranchesOutlined /> Edges ({(() => {
            let c = 0;
            l7Tree.matched_services.forEach((s: any) => {
              const ds = s.downstream?.by_protocol ?? {};
              const cs2 = s.callers?.by_protocol ?? {};
              Object.values(ds).forEach((arr: any) => { c += arr?.length ?? 0; });
              Object.values(cs2).forEach((arr: any) => { c += arr?.length ?? 0; });
            });
            return c;
          })()})</span>,
          children: (() => {
            const rows: any[] = [];
            (l7Tree.matched_services ?? []).forEach((svc: any) => {
              const downstream = svc.downstream?.by_protocol ?? {};
              Object.entries(downstream).forEach(([proto, deps]: [string, any]) => {
                (deps ?? []).forEach((d: any, di: number) => {
                  rows.push({
                    key: `${svc.name}-ds-${proto}-${di}`,
                    source: `${svc.namespace}/${svc.name}`,
                    target: `${d.namespace}/${d.name}`,
                    direction: 'downstream',
                    protocol: proto,
                    http_method: d.http_method,
                    http_path: d.http_path,
                    request_count: d.request_count,
                    error_count: d.error_count,
                    avg_latency_ms: d.avg_latency_ms,
                  });
                });
              });
              const callers = svc.callers?.by_protocol ?? {};
              Object.entries(callers).forEach(([proto, deps]: [string, any]) => {
                (deps ?? []).forEach((d: any, di: number) => {
                  rows.push({
                    key: `${svc.name}-cl-${proto}-${di}`,
                    source: `${d.namespace}/${d.name}`,
                    target: `${svc.namespace}/${svc.name}`,
                    direction: 'caller',
                    protocol: proto,
                    http_method: d.http_method,
                    http_path: d.http_path,
                    request_count: d.request_count,
                    error_count: d.error_count,
                    avg_latency_ms: d.avg_latency_ms,
                  });
                });
              });
            });
            return (
              <Table
                size="small"
                dataSource={rows}
                rowKey="key"
                pagination={{ pageSize: 15, showSizeChanger: true, size: 'small' }}
                scroll={{ x: 900 }}
                columns={[
                  { title: 'Source', dataIndex: 'source', key: 'source', ellipsis: true, width: 170 },
                  { title: 'Target', dataIndex: 'target', key: 'target', ellipsis: true, width: 170 },
                  { title: 'Dir', dataIndex: 'direction', key: 'dir', width: 90, render: (v: string) => <Tag color={v === 'downstream' ? 'blue' : 'green'}>{v}</Tag> },
                  { title: 'Proto', dataIndex: 'protocol', key: 'proto', width: 70 },
                  { title: 'Method', dataIndex: 'http_method', key: 'method', width: 70 },
                  { title: 'Path', dataIndex: 'http_path', key: 'path', ellipsis: true, width: 150 },
                  { title: 'Requests', dataIndex: 'request_count', key: 'reqs', width: 90, sorter: (a: any, b: any) => (a.request_count ?? 0) - (b.request_count ?? 0) },
                  { title: 'Errors', dataIndex: 'error_count', key: 'errs', width: 70,
                    render: (v: any) => v > 0 ? <Tag color="red">{v}</Tag> : v ?? 0 },
                  { title: 'Avg ms', dataIndex: 'avg_latency_ms', key: 'lat', width: 80,
                    render: (v: any) => v != null ? Number(v).toFixed(1) : '—' },
                ]}
              />
            );
          })(),
        }] : []),
        {
          key: 'l7summary',
          label: <span><CodeOutlined /> Summary JSON</span>,
          children: (
            <div>
              <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
                Dependency summary response: ~{Math.round(JSON.stringify(l7Summary).length / 1024)} KB
              </Text>
              <CodeBlock code={JSON.stringify(l7Summary, null, 2)} label="JSON" />
            </div>
          ),
        },
        ...(l7Tree ? [{
          key: 'l7tree',
          label: <span><CodeOutlined /> Tree JSON</span>,
          children: (
            <div>
              <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
                Tree summary response: ~{Math.round(JSON.stringify(l7Tree).length / 1024)} KB
              </Text>
              <CodeBlock code={JSON.stringify(l7Tree, null, 2)} label="JSON" />
            </div>
          ),
        }] : []),
      ]}
    />
  </>
);

interface L4PreviewBodyProps {
  l4: any;
  tokenPrimary: string;
  tokenError: string;
  tokenSuccess: string;
  tokenBorderSecondary: string;
  showL7Details: boolean;
  responseSize: number;
}

const L4PreviewBody: React.FC<L4PreviewBodyProps> = ({
  l4,
  tokenPrimary,
  tokenError,
  tokenSuccess,
  tokenBorderSecondary,
  showL7Details,
  responseSize,
}) => (
  <>
    {l4.multi_service && l4.matched_services ? (() => {
      const namespaces: string[] = Array.from(new Set<string>(l4.matched_services.map((s: any) => String(s.namespace || '')))).sort();
      const critCount = l4.summary?.downstream_critical_count ?? 0;
      return (
        <Card size="small" style={{ borderLeft: `3px solid ${tokenPrimary}`, marginBottom: 16 }}>
          <Row gutter={24} align="middle">
            <Col>
              <Statistic
                title="Matched Services"
                value={l4.matched_services.length}
                valueStyle={{ fontSize: 28, fontWeight: 700, color: tokenPrimary }}
              />
            </Col>
            <Col>
              <Statistic
                title="Namespaces"
                value={namespaces.length}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
            </Col>
            <Col>
              <Statistic
                title={<><ArrowDownOutlined /> Downstream</>}
                value={l4.summary?.total_downstream_unique ?? 0}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
            </Col>
            <Col>
              <Statistic
                title={<><ArrowUpOutlined /> Callers</>}
                value={l4.summary?.total_callers_unique ?? 0}
                valueStyle={{ fontSize: 28, fontWeight: 700 }}
              />
            </Col>
            {critCount > 0 && (
              <Col>
                <Statistic
                  title="Critical"
                  value={critCount}
                  valueStyle={{ fontSize: 28, fontWeight: 700, color: tokenError }}
                />
              </Col>
            )}
          </Row>
          {namespaces.length > 0 && (
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 4,
              marginTop: 12, paddingTop: 12,
              borderTop: `1px solid ${tokenBorderSecondary}`,
            }}>
              {namespaces.map(ns => (
                <Tag key={ns} style={{ margin: 0, fontSize: 12 }}>{ns}</Tag>
              ))}
            </div>
          )}
        </Card>
      );
    })() : (
      <Card size="small" style={{ borderLeft: `3px solid ${tokenPrimary}`, marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Space split={<Divider type="vertical" />}>
              <Text strong style={{ fontSize: 16 }}>{l4.service?.name}</Text>
              <Text type="secondary">{l4.service?.namespace}</Text>
              {l4.service?.kind && <Tag>{l4.service.kind}</Tag>}
            </Space>
          </Col>
          <Col>
            <Space size="large">
              <Statistic title={<><ArrowDownOutlined /> Downstream</>} value={l4.summary?.total_downstream_unique ?? 0} valueStyle={{ fontSize: 18 }} />
              <Statistic title={<><ArrowUpOutlined /> Callers</>} value={l4.summary?.total_callers_unique ?? 0} valueStyle={{ fontSize: 18 }} />
            </Space>
          </Col>
        </Row>
      </Card>
    )}

    {l4.multi_service && l4.matched_services && l4.matched_services.length > 0 && (
      <Card size="small" title={`Matched Upstream Services (${l4.matched_services.length})`} style={{ marginBottom: 16 }}>
        <Table<MatchedService>
          dataSource={l4.matched_services}
          rowKey={(r) => `${r.namespace}/${r.name}`}
          size="small"
          pagination={l4.matched_services.length > 10 ? { pageSize: 10 } : false}
          columns={[
            { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <Text strong>{v}</Text> },
            { title: 'Namespace', dataIndex: 'namespace', key: 'ns' },
            { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
            { title: 'Downstream', dataIndex: ['downstream', 'total'], key: 'ds', render: (v: number) => <Badge count={v ?? 0} showZero style={{ backgroundColor: v ? tokenPrimary : tokenBorderSecondary }} /> },
            { title: 'Callers', dataIndex: ['callers', 'total'], key: 'cl', render: (v: number) => <Badge count={v ?? 0} showZero style={{ backgroundColor: v ? tokenSuccess : tokenBorderSecondary }} /> },
            {
              title: 'Metadata',
              key: 'meta',
              render: (_: unknown, r: MatchedService) => {
                const annCount = Object.keys(r.annotations || {}).length;
                const lblCount = Object.keys(r.labels || {}).length;
                return (
                  <Tooltip title={`${lblCount} labels, ${annCount} annotations`}>
                    <Tag>{lblCount}L / {annCount}A</Tag>
                  </Tooltip>
                );
              },
            },
          ]}
        />
      </Card>
    )}

    {!l4.multi_service && Object.keys(l4.matched_services?.[0]?.annotations || {}).length > 0 && (
      <Card size="small" title="Upstream Service Metadata" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
          {Object.entries(l4.matched_services![0].annotations).map(([k, v]) => (
            <Descriptions.Item key={k} label={<Text strong style={{ fontSize: 11 }}>{k}</Text>}>
              <Text style={{ fontSize: 11, wordBreak: 'break-all' }}>{v as string}</Text>
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Card>
    )}

    {l4.multi_service && l4.matched_services ? (
      <Tabs
        items={[
          {
            key: 'dependencies',
            label: <span><BranchesOutlined /> Per-Service Dependencies ({l4.matched_services.length})</span>,
            children: (
              <Collapse
                defaultActiveKey={l4.matched_services.slice(0, 5).map((_: any, i: number) => String(i))}
                items={l4.matched_services.map((svc: any, idx: number) => ({
                  key: String(idx),
                  label: (
                    <Space size="small" wrap>
                      <Text strong>{svc.name}</Text>
                      <Text type="secondary">{svc.namespace}</Text>
                      {svc.kind && <Tag>{svc.kind}</Tag>}
                      <Badge count={svc.downstream.total} showZero style={{ backgroundColor: svc.downstream.total ? tokenPrimary : tokenBorderSecondary }} />
                      <Badge count={svc.callers.total} showZero style={{ backgroundColor: svc.callers.total ? tokenSuccess : tokenBorderSecondary }} />
                    </Space>
                  ),
                  children: (
                    <Tabs
                      size="small"
                      items={[
                        {
                          key: 'ds',
                          label: <span><ArrowDownOutlined /> Downstream ({svc.downstream.total})</span>,
                          children: <DependencyCategoryGroup group={svc.downstream} title="Downstream" showL7Details={showL7Details} />,
                        },
                        {
                          key: 'cl',
                          label: <span><ArrowUpOutlined /> Callers ({svc.callers.total})</span>,
                          children: <DependencyCategoryGroup group={svc.callers} title="Callers" showL7Details={showL7Details} />,
                        },
                      ]}
                    />
                  ),
                }))}
              />
            ),
          },
          {
            key: 'raw',
            label: <span><CodeOutlined /> Raw JSON</span>,
            children: (
              <div>
                <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>Response size: ~{responseSize} KB</Text>
                <CodeBlock code={JSON.stringify(l4, null, 2)} label="JSON" />
              </div>
            ),
          },
        ]}
      />
    ) : l4.matched_services?.[0] ? (
      <Tabs
        items={[
          {
            key: 'downstream',
            label: <span><ArrowDownOutlined /> Downstream ({l4.matched_services[0].downstream.total})</span>,
            children: <DependencyCategoryGroup group={l4.matched_services[0].downstream} title="Downstream" showL7Details={showL7Details} />,
          },
          {
            key: 'callers',
            label: <span><ArrowUpOutlined /> Callers ({l4.matched_services[0].callers.total})</span>,
            children: <DependencyCategoryGroup group={l4.matched_services[0].callers} title="Callers" showL7Details={showL7Details} />,
          },
          {
            key: 'raw',
            label: <span><CodeOutlined /> Raw JSON</span>,
            children: (
              <div>
                <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>Response size: ~{responseSize} KB</Text>
                <CodeBlock code={JSON.stringify(l4, null, 2)} label="JSON" />
              </div>
            ),
          },
        ]}
      />
    ) : null}
  </>
);

const IntegrationHub: React.FC = () => {
  const { token } = theme.useToken();
  const [currentStep, setCurrentStep] = useState(0);
  const [integrationType, setIntegrationType] = useState<IntegrationType>(null);
  const [form] = Form.useForm();

  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState<number[]>([]);
  const [platform, setPlatform] = useState('azure_devops');
  const [idMethod, setIdMethod] = useState('annotation');
  const [depth, setDepth] = useState(1);

  // Audit v3 (UI3): when the operator picks a BOTH analysis we kick
  // off both the L4 and L7 endpoints in parallel, but the Integration
  // Code step needs to render a snippet for ONE side at a time —
  // emitting twelve tab variants doubles the visual noise without
  // helping the operator. We render a single L4/L7 toggle and reuse
  // the existing snippet tabs for whichever side is active.
  const [snippetLevelToggle, setSnippetLevelToggle] = useState<'l4' | 'l7'>('l4');

  // Blast Radius Gate flow state
  const [brTargetService, setBrTargetService] = useState('');
  const [brTargetNamespace, setBrTargetNamespace] = useState('');
  // Audit fix: standalone Blast Radius flow had no cluster picker —
  // every generated snippet baked in `cluster_id: 1`, which silently
  // misrouted assessment requests on every non-default cluster and
  // broke completely on multi-cluster installs. We now expose the
  // operator's cluster list and forward the selection to the snippet
  // builder. `null` keeps the legacy CI variable form ($CLUSTER_ID,
  // ${{ vars.CLUSTER_ID }}) for pipelines that template across
  // multiple clusters.
  const [brClusterId, setBrClusterId] = useState<number | null>(null);
  // Plan v3 Akış D m.7 — `analysisLevel` is now DERIVED from the
  // selected analyses rather than a separate radio. The operator
  // already picked an analysis (which carries its own level metadata),
  // so forcing them to also pick a level was redundant and frequently
  // caused empty dropdowns ("I picked Both but I see no L7 options").
  //
  // Derivation rules:
  //   - 0 selected: default to 'l4' so the form shape is stable.
  //   - 1 selected: use that analysis' analysis_level.
  //   - >1 selected: if any analysis is L7-capable ('l7' / 'both'),
  //     use 'l7'; else 'l4'. We surface a warning banner if the
  //     selection mixes pure-L4 and L7-capable analyses so the operator
  //     understands which features will be available.
  //
  // The state is kept (rather than purely derived in render) so that
  // callbacks like resetSummary and lazy-trigger choices can read a
  // stable value without recomputing the derivation.
  const [analysisLevel, setAnalysisLevel] = useState<'l4' | 'l7' | 'both'>('l4');

  const [triggerL4Summary, { data: rawL4SummaryData, isFetching: l4SummaryLoading, error: rawL4SummaryError }] =
    useLazyGetDependencySummaryQuery();
  const [triggerL7Summary, { data: rawL7SummaryData, isFetching: l7SummaryLoading, error: rawL7SummaryError }] =
    useLazyGetL7DependencySummaryQuery();
  const [triggerL7Tree, { data: rawL7TreeData, isFetching: l7TreeLoading, error: rawL7TreeError }] =
    useLazyGetL7DependencyTreeSummaryQuery();
  const [summaryParams, setSummaryParams] = useState<DependencySummaryParams | null>(null);
  const [summaryCleared, setSummaryCleared] = useState(false);
  const resetSummary = useCallback(() => {
    setSummaryCleared(true);
    setSummaryParams(null);
  }, []);

  // Audit v3 (B-26, B-27): the previous flow flipped between the L4
  // and the L7 lazy query results based on `analysisLevel`. That made
  // BOTH-analysis flows unreachable because the L4 branch silently
  // shadowed every L7 result. We now compute a composite that
  // surfaces BOTH sides, and a level-aware `effectiveSuccess` /
  // `effectiveLoading` so render code can stay agnostic of which
  // endpoint(s) backed the current step.
  const compositeSummary = useMemo(() => {
    const cleared = summaryCleared;
    return {
      l4: cleared ? undefined : rawL4SummaryData,
      l7Summary: cleared ? undefined : rawL7SummaryData,
      l7Tree: cleared ? undefined : rawL7TreeData,
      l4Loading: l4SummaryLoading,
      l7Loading: l7SummaryLoading || l7TreeLoading,
      l4Error: cleared ? undefined : rawL4SummaryError,
      l7Error: cleared ? undefined : (rawL7SummaryError ?? rawL7TreeError),
      l4Success: !cleared && Boolean(rawL4SummaryData?.success),
      l7Success: !cleared && Boolean(rawL7SummaryData?.success),
    };
  }, [
    summaryCleared,
    rawL4SummaryData, rawL7SummaryData, rawL7TreeData,
    l4SummaryLoading, l7SummaryLoading, l7TreeLoading,
    rawL4SummaryError, rawL7SummaryError, rawL7TreeError,
  ]);

  // Legacy helpers — many JSX branches expect `summaryData` /
  // `summaryError` / `summaryLoading`. Map them to the level-active
  // entry so we don't have to rewrite every conditional.
  const summaryData = analysisLevel === 'l7'
    ? compositeSummary.l7Summary
    : compositeSummary.l4;
  const summaryError = analysisLevel === 'l7'
    ? compositeSummary.l7Error
    : compositeSummary.l4Error;
  const summaryLoading = analysisLevel === 'l7'
    ? compositeSummary.l7Loading
    : compositeSummary.l4Loading;

  const effectiveSuccess = useMemo(() => {
    if (analysisLevel === 'l4') return compositeSummary.l4Success;
    if (analysisLevel === 'l7') return compositeSummary.l7Success;
    return compositeSummary.l4Success || compositeSummary.l7Success;
  }, [analysisLevel, compositeSummary]);

  const effectiveLoading = analysisLevel === 'l4'
    ? compositeSummary.l4Loading
    : analysisLevel === 'l7'
      ? compositeSummary.l7Loading
      : (compositeSummary.l4Loading || compositeSummary.l7Loading);

  const [searchParams] = useSearchParams();
  useEffect(() => {
    const urlOwner = searchParams.get('owner_name');
    const urlNs = searchParams.get('namespace');
    const urlAnnotationKey = searchParams.get('annotation_key');
    const urlAnnotationValue = searchParams.get('annotation_value');
    if (urlOwner || urlNs || urlAnnotationKey) {
      setIntegrationType('dependency');
      setCurrentStep(1);
      if (urlAnnotationKey) setIdMethod('annotation');
      else if (urlOwner || urlNs) setIdMethod('namespace_deployment');
      setTimeout(() => {
        const fields: Record<string, string> = {};
        if (urlOwner) fields.owner_name = urlOwner;
        if (urlNs) fields.namespace = urlNs;
        if (urlAnnotationKey) fields.annotation_key = urlAnnotationKey;
        if (urlAnnotationValue) fields.annotation_value = urlAnnotationValue;
        form.setFieldsValue(fields);
      }, 0);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: clustersData } = useGetClustersQuery();
  const clusters: any[] = (clustersData as any)?.clusters || [];
  const clusterNameMap = useMemo(() => {
    const m: Record<number, string> = {};
    clusters.forEach((c: any) => { m[c.id] = c.name; });
    return m;
  }, [clusters]);

  const { data: analysesData } = useGetAnalysesQuery({});
  const statusFiltered = useMemo(
    () =>
      (Array.isArray(analysesData) ? analysesData : []).filter(
        (a: any) => a.status === 'completed' || a.status === 'running' || a.status === 'stopped',
      ),
    [analysesData],
  );
  const l4Analyses = useL4Analyses(statusFiltered as Analysis[]);
  // Plan v3 Akış D m.7 — `analyses` now exposes EVERY status-eligible
  // analysis. Grouping/labeling in the Select OptGroup handles the
  // visual segmentation by cluster + level. Filtering by level was
  // moved out of the data layer because the level is now derived from
  // the operator's picks.
  const analyses: any[] = statusFiltered;

  // Helper: classify an analysis. `analysis_level` is kept in lower
  // case to match the database; missing values fall back to legacy
  // 'l4' (the original default before L7 support landed).
  const getAnalysisLevel = useCallback((a: any): 'l4' | 'l7' | 'both' => {
    const lv = (a?.analysis_level || 'l4').toLowerCase();
    if (lv === 'l7' || lv === 'both') return lv;
    return 'l4';
  }, []);

  // Derive analysis level from the current selection. Effect is keyed
  // on the selected IDs + the analyses list (the ID alone isn't
  // enough; the analysis row may load asynchronously).
  //
  // Resolution table (L = level set of selected analyses):
  //   L = {}             → keep previous level (avoid flicker on clear)
  //   L = {l4}           → 'l4'
  //   L = {l7}           → 'l7'
  //   L = {both}         → 'both'
  //   L = {l4, both}     → 'l4'   (L4 endpoint covers both — both has L4 data)
  //   L = {l7, both}     → 'l7'   (L7 endpoint covers both — both has L7 data)
  //   L = {l4, l7}       → 'l4'   (no shared endpoint — L4 default + warning)
  //   L = {l4, l7, both} → 'l4'   (same: L4 default + warning)
  //
  // The mixedLevelWarning memo below surfaces a warning whenever the
  // selection set contains > 1 distinct level; the warning explicitly
  // names the levels so the operator knows which analyses contribute
  // which signals.
  useEffect(() => {
    if (!selectedAnalysisIds.length) {
      return;
    }
    const picked = analyses.filter((a: any) => selectedAnalysisIds.includes(a.id));
    if (!picked.length) return;
    const levels = picked.map(getAnalysisLevel);
    const allL4 = levels.every((l) => l === 'l4');
    const allL7 = levels.every((l) => l === 'l7');
    const allBoth = levels.every((l) => l === 'both');
    const hasPureL7 = levels.includes('l7');
    const hasPureL4 = levels.includes('l4');
    let next: 'l4' | 'l7' | 'both';
    if (allL4) next = 'l4';
    else if (allL7) next = 'l7';
    else if (allBoth) next = 'both';
    else if (!hasPureL7) next = 'l4';
    else if (!hasPureL4) next = 'l7';
    else next = 'l4';
    setAnalysisLevel((prev) => (prev === next ? prev : next));
  }, [selectedAnalysisIds, analyses, getAnalysisLevel]);

  // Audit v3 (B-29): the mixed-level warning was firing for any BOTH
  // analysis as soon as the operator picked a second analysis with
  // a different label — even when both selections were honoured by
  // the dual-query flow. We now only warn when the selection set
  // contains genuinely incompatible levels (i.e. mixing pure-L4 with
  // pure-L7 with no BOTH analysis to bridge them). Pure BOTH and
  // BOTH-mixed-with-anything selections get a softer "info" banner
  // via the existing Configure-step alert.
  const mixedLevelWarning = useMemo(() => {
    if (selectedAnalysisIds.length < 2) return null;
    const picked = analyses.filter((a: any) => selectedAnalysisIds.includes(a.id));
    const levels = new Set(picked.map(getAnalysisLevel));
    if (levels.size <= 1) return null;
    // L4 + L7 with no BOTH is the only combination where the
    // operator cannot get a unified result set — one analysis
    // contributes only network signals, the other only application
    // signals, and there's no shared signal to merge them.
    if (levels.has('l4') && levels.has('l7') && !levels.has('both')) {
      return Array.from(levels).join(', ');
    }
    return null;
  }, [selectedAnalysisIds, analyses, getAnalysisLevel]);

  useEffect(() => {
    setSelectedAnalysisIds((prev) => prev.filter((id) => analyses.some((a: any) => a.id === id)));
  }, [analyses]);

  // Round 2 audit (R-NEW-cluster-deleted): when an admin deletes a
  // cluster while the operator is mid-flow on the standalone Blast
  // Radius form, the picker still holds the now-stale id. Antd's
  // Select renders empty (no matching option) but the state is
  // preserved, so the generated snippet would forward the dead
  // cluster_id and the operator would get a 404 from the backend.
  // We drop the state on the next render once the clusters list
  // confirms the id is gone.
  useEffect(() => {
    if (brClusterId == null) return;
    if (clusters.length === 0) return; // list still loading
    const stillExists = clusters.some((c: any) => c.id === brClusterId);
    if (!stillExists) {
      setBrClusterId(null);
    }
  }, [clusters, brClusterId]);

  // Audit v3 (B-26 + E-1): build a composite error message so a BOTH
  // flow can surface BOTH failures distinctly. Pure L4 / pure L7
  // flows preserve their original phrasing (single error, level-
  // aware hint). BOTH flows annotate each side with its level label
  // and, when every endpoint fails, prepend "Both endpoints failed".
  const summaryErrMsg = useMemo(() => {
    const extractRaw = (err: any, data: any): string | null => {
      const eraw = err ? ((err as any)?.data?.detail || 'Query failed') : null;
      const draw = data && !data.success ? (data.error || 'No results') : null;
      return eraw || draw || null;
    };
    const annotateNoResults = (raw: string, level: 'l4' | 'l7'): string => {
      const lc = raw.toLowerCase();
      if (!(lc.includes('no pod') || lc.includes('no results') || lc.includes('no matching'))) {
        return raw;
      }
      if (level === 'l7') {
        return `${raw}. Tip: Verify Beyla is running and healthy in Integration Hub settings. Ensure the selected analysis collected L7 traffic. Check that target pods have HTTP/gRPC/DNS traffic.`;
      }
      return `${raw}. Tip: Check the Map view to verify available annotations/labels for your pods. Infrastructure annotations (openshift.io/*, kubernetes.io/*) are filtered — use custom annotations like git-repo, team, or version.`;
    };

    if (analysisLevel === 'l4' || analysisLevel === 'l7') {
      const raw = extractRaw(
        analysisLevel === 'l7' ? compositeSummary.l7Error : compositeSummary.l4Error,
        analysisLevel === 'l7' ? compositeSummary.l7Summary : compositeSummary.l4,
      );
      return raw ? annotateNoResults(raw, analysisLevel) : null;
    }

    // BOTH — composite error surface.
    const l4raw = extractRaw(compositeSummary.l4Error, compositeSummary.l4);
    const l7raw = extractRaw(compositeSummary.l7Error, compositeSummary.l7Summary);
    if (!l4raw && !l7raw) return null;
    const lines: string[] = [];
    if (l4raw && l7raw) lines.push('Both endpoints failed.');
    if (l4raw) lines.push(`L4 (network): ${annotateNoResults(l4raw, 'l4')}`);
    if (l7raw) lines.push(`L7 (application): ${annotateNoResults(l7raw, 'l7')}`);
    return lines.join(' ');
  }, [
    analysisLevel,
    compositeSummary.l4, compositeSummary.l7Summary,
    compositeSummary.l4Error, compositeSummary.l7Error,
  ]);

  const canProceedConfigure = selectedAnalysisIds.length > 0;

  // Plan v3 Akış D m.8 — Service identification is now OPTIONAL.
  // When the operator submits with no annotation/label/owner/pod_name/
  // ip we fall back to discovery mode (`match_all=true`) which the
  // backend allows IFF a cluster_id or namespace is also present (the
  // tenant guard in `find_pod_dependencies`).
  //
  // The discovery cluster scope comes from the selected analyses.
  // When EVERY cluster touched by the selection collapses to a single
  // unique cluster id we forward it automatically so a single-cluster
  // flow doesn't surface an error to the operator. For any selection
  // that spans more than one cluster we MUST leave cluster_id empty;
  // the backend's tenant guard treats `cluster_id` as a strict filter
  // and silently drops every dependency from other clusters (verified
  // live: analysis 47 with cluster_ids=[15,16] returns 19 services
  // when cluster_id=15 is sent vs 9 services when cluster_id=16 is
  // sent; sending only cluster 15 hides the 9 services of cluster 16
  // that the operator legitimately scoped into the analysis).
  //
  // The previous implementation only inspected `cluster_id` (the
  // analysis' primary cluster), which silently misclassified every
  // multi-cluster analysis as single-cluster and triggered the data
  // loss above. We now expand each analysis to its full cluster_ids
  // set first.
  const singleClusterId = useMemo(() => {
    if (!selectedAnalysisIds.length) return null;
    const picked = analyses.filter((a: any) => selectedAnalysisIds.includes(a.id));
    const all = new Set<number>();
    picked.forEach((a: any) => {
      const cids: number[] = Array.isArray(a.cluster_ids) && a.cluster_ids.length
        ? a.cluster_ids
        : (a.cluster_id != null ? [a.cluster_id] : []);
      cids.forEach((c) => {
        if (c != null) all.add(Number(c));
      });
    });
    return all.size === 1 ? Number(Array.from(all)[0]) : null;
  }, [selectedAnalysisIds, analyses]);

  // Plan v3 Akış D m.8 — reactive form-field watchers for the
  // discovery hint banner. `form.getFieldsValue()` inside JSX is a
  // snapshot at render time and doesn't trigger re-renders when the
  // operator types into a Form.Item — the parent component would
  // show stale banner state. `Form.useWatch` subscribes to specific
  // form fields and re-renders the parent on every change, so the
  // banner stays in sync without per-keystroke onChange plumbing.
  const watchedAnnotationKey = Form.useWatch('annotation_key', form);
  const watchedLabelKey = Form.useWatch('label_key', form);
  const watchedNamespace = Form.useWatch('namespace', form);
  const watchedOwnerName = Form.useWatch('owner_name', form);
  const watchedPodName = Form.useWatch('pod_name', form);
  const watchedIp = Form.useWatch('ip', form);

  // Round 2 audit (R-NEW-B — stale form state when switching id
  // methods). Antd's Form keeps every field's value alive even when
  // the surrounding markup is conditionally hidden. So a sequence
  // like:
  //   1. Pick "Annotation" → type annotation_key="git-repo"
  //   2. Switch to "Label" → type label_key="app", label_value="frontend"
  //   3. Press Test Query
  // would silently submit BOTH `annotation_key=git-repo` AND
  // `label_key=app` to the backend. The backend ANDs every filter,
  // so the typical result is "no pods found" with no signal as to
  // why. Verified live: the same combo against the real API returns
  // success=false matched=0.
  //
  // We clear fields that don't belong to the active method so the
  // hidden state never leaks. The "Advanced" mode shows every field
  // simultaneously, so we leave its values alone.
  useEffect(() => {
    if (idMethod === 'advanced') return;
    const ALL = ['annotation_key', 'annotation_value', 'label_key', 'label_value', 'namespace', 'owner_name', 'pod_name', 'ip'];
    const KEEP: Record<string, string[]> = {
      annotation: ['annotation_key', 'annotation_value'],
      label: ['label_key', 'label_value'],
      namespace_deployment: ['namespace', 'owner_name'],
      pod_name: ['pod_name'],
    };
    const keep = new Set(KEEP[idMethod] || []);
    const reset: Record<string, undefined> = {};
    ALL.forEach((f) => {
      if (!keep.has(f)) reset[f] = undefined;
    });
    if (Object.keys(reset).length) {
      form.setFieldsValue(reset);
    }
  }, [idMethod, form]);
  const hasAnyIdentificationField = Boolean(
    watchedAnnotationKey ||
      watchedLabelKey ||
      watchedNamespace ||
      watchedOwnerName ||
      watchedPodName ||
      watchedIp,
  );

  const buildParamsFromForm = useCallback((): DependencySummaryParams | null => {
    const values = form.getFieldsValue();
    if (!selectedAnalysisIds.length) return null;
    const hasSearch =
      values.annotation_key ||
      values.label_key ||
      values.namespace ||
      values.owner_name ||
      values.pod_name ||
      values.ip;
    const params: DependencySummaryParams = {
      analysis_ids: selectedAnalysisIds,
      depth,
    };
    if (values.annotation_key) params.annotation_key = values.annotation_key;
    if (values.annotation_value) params.annotation_value = values.annotation_value;
    if (values.label_key) params.label_key = values.label_key;
    if (values.label_value) params.label_value = values.label_value;
    if (values.namespace) params.namespace = values.namespace;
    if (values.owner_name) params.owner_name = values.owner_name;
    if (values.pod_name) params.pod_name = values.pod_name;
    if (values.ip) params.ip = values.ip;
    if (!hasSearch) {
      // Discovery mode. Auto-forward the cluster scope when
      // unambiguous so the operator doesn't have to type it in.
      params.match_all = true;
      if (singleClusterId != null) {
        params.cluster_id = singleClusterId;
      } else if (!values.namespace) {
        // Multi-cluster selection without a namespace — backend will
        // refuse with the tenant-guard error. Surface that locally to
        // avoid a round-trip and an opaque toast.
        return null;
      }
    }
    return params;
  }, [form, selectedAnalysisIds, depth, singleClusterId]);

  // Audit v3 (B-19): derive an L7 dependency summary payload from
  // the shared L4 params. The L7 backend understands annotation/
  // label/owner_name/pod_name natively now, so a single source of
  // truth (the form) feeds both endpoints. owner_name is forwarded
  // as-is and the FastAPI proxy aliases it to workload_name.
  const buildL7ParamsFromForm = useCallback((
    l4Params: DependencySummaryParams,
    aid: number | string,
  ): L7DependencySummaryParams => ({
    analysis_id: aid,
    ...(l4Params.cluster_id != null ? { cluster_id: l4Params.cluster_id } : {}),
    ...(l4Params.namespace ? { namespace: l4Params.namespace } : {}),
    ...(l4Params.annotation_key ? { annotation_key: l4Params.annotation_key } : {}),
    ...(l4Params.annotation_value ? { annotation_value: l4Params.annotation_value } : {}),
    ...(l4Params.label_key ? { label_key: l4Params.label_key } : {}),
    ...(l4Params.label_value ? { label_value: l4Params.label_value } : {}),
    ...(l4Params.owner_name ? { owner_name: l4Params.owner_name } : {}),
    ...(l4Params.pod_name ? { pod_name: l4Params.pod_name } : {}),
    filter_noise_annotations: true,
  }), []);

  // Tree-summary uses workload_name, not owner_name; we pin
  // workload_name_exact=false to mirror the L4 owner_name CONTAINS
  // behaviour the IntegrationHub UI promises.
  const buildL7TreeParamsFromForm = useCallback((
    l4Params: DependencySummaryParams,
    aid: number | string,
  ): L7TreeSummaryParams => ({
    analysis_id: aid,
    ...(l4Params.cluster_id != null ? { cluster_id: l4Params.cluster_id } : {}),
    ...(l4Params.namespace ? { namespace: l4Params.namespace } : {}),
    ...(l4Params.annotation_key ? { annotation_key: l4Params.annotation_key } : {}),
    ...(l4Params.annotation_value ? { annotation_value: l4Params.annotation_value } : {}),
    ...(l4Params.label_key ? { label_key: l4Params.label_key } : {}),
    ...(l4Params.label_value ? { label_value: l4Params.label_value } : {}),
    ...(l4Params.owner_name ? {
      workload_name: l4Params.owner_name,
      workload_name_exact: false,
    } : {}),
    ...(l4Params.depth != null ? { depth: l4Params.depth } : {}),
  }), []);

  const onTestQuery = useCallback(async () => {
    if (!selectedAnalysisIds.length) {
      message.warning('Select at least one analysis');
      return;
    }
    try {
      await form.validateFields();
    } catch (err) {
      return;
    }
    const baseParams = buildParamsFromForm();
    if (!baseParams) {
      message.warning(
        'Multi-cluster selection without a namespace. Either narrow the analyses to a single cluster, or fill in the Namespace field for discovery mode.',
      );
      return;
    }
    setSummaryParams(baseParams);
    setSummaryCleared(false);

    const aid = selectedAnalysisIds[0];
    const l7Params = buildL7ParamsFromForm(baseParams, aid);
    const l7TreeParams = buildL7TreeParamsFromForm(baseParams, aid);

    // L4 covers EVERY selected analysis; L7 endpoints accept one at
    // a time so we forward the first ID and toast the operator about
    // the truncation when relevant.
    if (analysisLevel === 'l4' || analysisLevel === 'both') {
      triggerL4Summary(baseParams, false);
    }
    if (analysisLevel === 'l7' || analysisLevel === 'both') {
      if (selectedAnalysisIds.length > 1) {
        const ignored = selectedAnalysisIds.length - 1;
        const detail = analysisLevel === 'both'
          ? `L7 endpoints only query the first analysis (#${aid}); ${ignored} other ${ignored === 1 ? 'analysis is' : 'analyses are'} ignored. L4 still covers all ${selectedAnalysisIds.length}.`
          : `L7 dependency analysis only queries one analysis at a time. Using analysis #${aid}; ${ignored} other ${ignored === 1 ? 'analysis was' : 'analyses were'} skipped.`;
        message.warning(detail);
      }
      triggerL7Summary(l7Params, false);
      triggerL7Tree(l7TreeParams, false);
    }
  }, [
    form, selectedAnalysisIds, buildParamsFromForm,
    buildL7ParamsFromForm, buildL7TreeParamsFromForm,
    analysisLevel, triggerL4Summary, triggerL7Summary, triggerL7Tree,
  ]);

  const onSkipToSetup = useCallback(async () => {
    if (!selectedAnalysisIds.length) {
      message.warning('Select at least one analysis');
      return;
    }
    try {
      await form.validateFields();
    } catch (err) {
      return;
    }
    const baseParams = buildParamsFromForm();
    if (!baseParams) {
      message.warning(
        'Multi-cluster selection without a namespace. Either narrow the analyses to a single cluster, or fill in the Namespace field for discovery mode.',
      );
      return;
    }
    setSummaryParams(baseParams);
    setCurrentStep(3);
  }, [form, selectedAnalysisIds, buildParamsFromForm]);

  const responseSize = useMemo(() => {
    if (!summaryData) return 0;
    return Math.round(JSON.stringify(summaryData).length / 1024 * 10) / 10;
  }, [summaryData]);

  const contextNamespace = summaryParams?.namespace;
  const contextOwnerName = summaryParams?.owner_name;

  const handleSelectType = (type: IntegrationType) => {
    setIntegrationType(type);
    setCurrentStep(1);
  };

  const handleBackToTypeSelection = () => {
    setIntegrationType(null);
    setCurrentStep(0);
    setBrTargetService('');
    setBrTargetNamespace('');
    setBrClusterId(null);
    resetSummary();
  };

  const depSteps = [
    { title: 'Integration Type', icon: <ApiOutlined /> },
    { title: 'Configure', icon: <ExperimentOutlined /> },
    { title: 'Preview', icon: <EyeOutlined /> },
    { title: 'Integration Code', icon: <CodeOutlined /> },
  ];

  const brSteps = [
    { title: 'Integration Type', icon: <ApiOutlined /> },
    { title: 'Configure', icon: <ExperimentOutlined /> },
    { title: 'Integration Code', icon: <CodeOutlined /> },
  ];

  const activeSteps = integrationType === 'blast_radius' ? brSteps : depSteps;

  const handleStepClick = (n: number) => {
    if (n === 0) {
      handleBackToTypeSelection();
      return;
    }
    if (n < currentStep) {
      setCurrentStep(n);
      return;
    }
    if (integrationType === 'dependency') {
      if (n === 2 && effectiveSuccess) setCurrentStep(n);
      else if (n === 3 && (effectiveSuccess || summaryParams)) setCurrentStep(n);
    }
    if (integrationType === 'blast_radius') {
      if (n === 2) setCurrentStep(n);
    }
  };

  // ─── Shared auth card ───
  // Round 2 audit (R-NEW-1) — the previous card pointed users at
  // Settings > API Keys but didn't tell them WHICH scope checkbox to
  // tick. Settings defaults to `blast-radius` only; an operator
  // creating a key for Dependency Analysis would generate a key with
  // the wrong logical scope (the backend's enforcement is currently
  // permissive, but audit/compliance reviews flag mismatched scopes).
  // We surface the recommended scope for the active integration type
  // so the operator picks the right checkbox the first time.
  const requiredScope = integrationType === 'blast_radius' ? 'blast-radius' : 'read';
  const requiredScopeLabel = integrationType === 'blast_radius'
    ? <Tag color="orange">blast-radius</Tag>
    : <Tag color="blue">read</Tag>;
  const authCard = (
    <Card
      title={<span><KeyOutlined /> Authentication</span>}
      size="small"
      style={{ marginTop: 16 }}
    >
      <Paragraph>
        All API calls require authentication via <Text strong>API Key</Text>. Include the header <Text code>X-API-Key: fk_your_key</Text> in every request.
      </Paragraph>
      <ol>
        <li>Go to <Link to="/settings?tab=api-tokens"><Text strong>Settings &gt; API Keys</Text></Link></li>
        <li>Click <Text strong>Generate New API Key</Text> and give it a descriptive name (e.g. &quot;azure-devops-pipeline&quot;)</li>
        <li>
          Tick the {requiredScopeLabel} scope for this integration type
          {integrationType === 'dependency' && (
            <Text type="secondary"> (the dependency / L7 endpoints fall under read access)</Text>
          )}
        </li>
        <li>Copy the generated key (starts with <Text code>fk_</Text>) and store it securely in your CI/CD platform&apos;s secrets/variables</li>
      </ol>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
        <Link to={`/settings?tab=api-tokens&suggestScope=${requiredScope}`}>
          <Button type="primary" icon={<KeyOutlined />}>
            Generate API Key (scope: {requiredScope})
          </Button>
        </Link>
        <Alert
          type="warning"
          showIcon
          message="API keys provide full API access. Store them as encrypted secrets in your pipeline platform, never in source code."
          style={{ flex: 1, margin: 0 }}
        />
      </div>
    </Card>
  );

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            <ApiOutlined /> Integration Hub
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Set up CI/CD pipeline integrations with Flowfish dependency and impact data.
          </Paragraph>
        </div>
        <Link to="/discovery/map">
          <Button type="link">Back to Map</Button>
        </Link>
      </div>

      {integrationType && (
        <Card style={{ marginBottom: 16 }}>
          <Steps
            current={currentStep}
            onChange={handleStepClick}
            items={activeSteps.map((s, idx) => ({
              ...s,
              disabled: idx > currentStep && !(idx === 2 && effectiveSuccess) && !(idx === 3 && summaryParams),
              description: idx > currentStep ? (
                idx === 1 ? 'Select an analysis first' :
                idx === 2 ? 'Run Test Query first' :
                idx === 3 ? 'Complete previous steps' : undefined
              ) : undefined,
            }))}
          />
        </Card>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Step 0: Integration Type Selection                        */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {currentStep === 0 && (
        <Row gutter={24} style={{ marginTop: 8 }}>
          <Col xs={24} md={12}>
            <Card
              hoverable
              onClick={() => handleSelectType('dependency')}
              style={{
                height: '100%',
                borderColor: token.colorPrimary,
                cursor: 'pointer',
                transition: 'box-shadow 0.2s',
              }}
              styles={{ body: { padding: 24 } }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: `${token.colorPrimary}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <BranchesOutlined style={{ fontSize: 24, color: token.colorPrimary }} />
                </div>
                <div>
                  <Text strong style={{ fontSize: 16 }}>Dependency Analysis</Text>
                  <Tag color="blue" style={{ marginLeft: 8 }}>Most Common</Tag>
                </div>
              </div>
              <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                Expose cross-service dependency data to CI/CD pipelines. Identify affected repositories, critical services, and downstream impact chains.
              </Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20, color: token.colorTextSecondary, fontSize: 13 }}>
                <li>Multi-analysis scope with 5 identification methods</li>
                <li>Live preview with downstream/caller categorization</li>
                <li>Pipeline YAML, curl, Python, and JavaScript snippets</li>
                <li>Git-repo annotation extraction for cross-project impact</li>
              </ul>
              <div style={{ marginTop: 16 }}>
                <Button type="primary" icon={<ArrowRightOutlined />}>Get Started</Button>
              </div>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card
              hoverable
              onClick={() => handleSelectType('blast_radius')}
              style={{
                height: '100%',
                cursor: 'pointer',
                transition: 'box-shadow 0.2s',
              }}
              styles={{ body: { padding: 24 } }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: `${token.colorWarning}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <ThunderboltOutlined style={{ fontSize: 24, color: token.colorWarning }} />
                </div>
                <Text strong style={{ fontSize: 16 }}>Blast Radius Gate</Text>
              </div>
              <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                Add pre-deployment risk scoring to your CI/CD pipeline. Get automated risk assessments, affected service counts, and actionable recommendations.
              </Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20, color: token.colorTextSecondary, fontSize: 13 }}>
                <li>Risk score (0-100) with level classification</li>
                <li>Blast radius: direct, indirect, and critical services</li>
                <li>Advisory-only — Flowfish never blocks deployments</li>
                <li>Pipeline snippets for all major CI/CD platforms</li>
              </ul>
              <div style={{ marginTop: 16 }}>
                <Button icon={<ArrowRightOutlined />}>Get Started</Button>
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* DEPENDENCY ANALYSIS FLOW (Steps 1-3)                      */}
      {/* ═══════════════════════════════════════════════════════════ */}

      {/* ─── Dep Step 1: Configure ─── */}
      {integrationType === 'dependency' && currentStep === 1 && (
        <Card title="Analysis Scope & Service Identification">
          <Paragraph type="secondary" style={{ marginBottom: 12 }}>
            Pick one or more completed/running analyses. The capture level
            (<Tag>L4</Tag>/<Tag>L7</Tag>/<Tag>Both</Tag>) is auto-detected
            from your selection — L4 powers Inspector Gadget-based
            dependency graphs, L7 powers application-level dependency
            tracing.
          </Paragraph>
          {/*
            Plan v3 Akış D m.7 — single-source-of-truth dropdown.

            We render every status-eligible analysis grouped by cluster,
            and put a Level tag on each option so the operator can scan
            visually for the level they need. Optionally we also sub-
            group inside each cluster by level.

            `mode='multiple'` is unconditional now — the previous flow
            switched between single and multi-select based on the radio
            choice; that mismatch caused state-flush bugs when the
            operator changed level after picking analyses.
          */}
          <Form.Item label="Analyses (required)" required>
            <Select
              mode="multiple"
              placeholder="Select one or more analyses"
              value={selectedAnalysisIds}
              onChange={(val) => {
                const ids = Array.isArray(val) ? val : (val != null ? [val] : []);
                setSelectedAnalysisIds(ids);
                resetSummary();
              }}
              style={{ width: '100%' }}
              optionFilterProp="label"
              showSearch
              maxTagCount="responsive"
            >
              {(() => {
                // Group by cluster first (operators usually scope by
                // environment / cluster), then by capture level inside
                // each cluster. Level grouping inside a cluster keeps
                // the dropdown scannable when a cluster has many
                // analyses across L4/L7/Both.
                const grouped: Record<string, Record<string, any[]>> = {};
                analyses.forEach((a: any) => {
                  const cName = clusterNameMap[a.cluster_id] || `Cluster ${a.cluster_id}`;
                  const lvl = getAnalysisLevel(a).toUpperCase();
                  ((grouped[cName] ||= {})[lvl] ||= []).push(a);
                });
                const clusterOrder = Object.keys(grouped).sort();
                const levelOrder = ['BOTH', 'L7', 'L4'];
                return clusterOrder.flatMap((clusterName) =>
                  levelOrder
                    .filter((lvl) => grouped[clusterName][lvl]?.length)
                    .map((lvl) => (
                      <Select.OptGroup
                        key={`${clusterName}::${lvl}`}
                        label={`${clusterName} — ${lvl}`}
                      >
                        {grouped[clusterName][lvl].map((a: any) => (
                          <Option
                            key={a.id}
                            value={a.id}
                            label={`${clusterName} ${a.name} ${lvl}`}
                          >
                            <Space size={6}>
                              <span>{a.name}</span>
                              <Tag
                                color={lvl === 'L7' ? 'purple' : lvl === 'BOTH' ? 'cyan' : 'blue'}
                                style={{ marginRight: 0 }}
                              >
                                {lvl}
                              </Tag>
                              <Tag color={a.status === 'completed' ? 'green' : 'orange'}>
                                {a.status}
                              </Tag>
                            </Space>
                          </Option>
                        ))}
                      </Select.OptGroup>
                    )),
                );
              })()}
            </Select>
          </Form.Item>

          {selectedAnalysisIds.length > 0 && (
            <Alert
              type={mixedLevelWarning ? 'warning' : 'info'}
              showIcon
              icon={mixedLevelWarning ? undefined : <CheckCircleOutlined />}
              message={
                mixedLevelWarning ? (
                  <span>
                    {selectedAnalysisIds.length} analyses selected with mixed
                    levels (<strong>{mixedLevelWarning}</strong>). L4-only
                    analyses won't contribute L7 dependency edges; L7-only
                    analyses won't contribute L4 ones. Effective level:{' '}
                    <Tag color={analysisLevel === 'l4' ? 'blue' : analysisLevel === 'l7' ? 'purple' : 'cyan'}>
                      {analysisLevel.toUpperCase()}
                    </Tag>
                  </span>
                ) : (
                  <span>
                    {selectedAnalysisIds.length} analysis selected — capture
                    level:{' '}
                    <Tag color={analysisLevel === 'l4' ? 'blue' : analysisLevel === 'l7' ? 'purple' : 'cyan'}>
                      {analysisLevel.toUpperCase()}
                    </Tag>
                  </span>
                )
              }
              style={{ marginBottom: 16 }}
            />
          )}

          <Divider />

          {/* Audit v3 (B-23 + UI3): the multi-cluster scope info banner
              used to live inside the (now-removed) L7 Workload Search
              card. Surface it here for any L7-capable selection so the
              operator still sees the cross-cluster heads-up. */}
          {analysisLevel !== 'l4' && selectedAnalysisIds.length > 0 && singleClusterId == null && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={
                <span>
                  <strong>Multi-cluster scope</strong> — the selected analysis spans more than one cluster, so the L7 endpoint will return workloads from <strong>all</strong> of them. Add a Namespace below to narrow if two clusters share namespace names you need to disambiguate.
                </span>
              }
            />
          )}

          {/*
            Audit v3 (B-19, UI3): the Service Identification card now
            renders for every analysisLevel. The previous flow only
            showed it for L4/BOTH and hid L7 behind a separate
            "L7 Workload Search" card that lacked annotation/label
            inputs entirely. Both endpoints accept the same
            identification surface now, so a single form drives them.

            Plan v3 Akış D m.8 — Service Identification stays OPTIONAL.

            Datadog/Honeycomb's flow: pick a service → then refine. We
            mirror that here:
              • If you fill nothing → discovery mode (every workload
                in the cluster/namespace scope)
              • If you fill any field → focused mode (matching pods)
          */}
          <Form.Item
            label={
              <Space>
                <span>Service Identification Method (optional)</span>
                <Tooltip
                  title={
                    <span>
                      Leave every field empty to use <strong>discovery mode</strong>
                      — every workload in the selected cluster/namespace
                      will be returned (depth capped at 2 to keep the
                      result bounded).
                    </span>
                  }
                >
                  <InfoCircleOutlined style={{ color: '#bfbfbf' }} />
                </Tooltip>
              </Space>
            }
          >
            <Radio.Group
              value={idMethod}
              onChange={(e) => {
                const next = e.target.value;
                if (next === 'advanced') {
                  setIdMethod(next);
                  resetSummary();
                  return;
                }
                const keep: Record<string, string> = {};
                const current = form.getFieldsValue();
                const fieldsForMethod: Record<string, string[]> = {
                  annotation: ['annotation_key', 'annotation_value'],
                  label: ['label_key', 'label_value'],
                  namespace_deployment: ['namespace', 'owner_name'],
                  pod_name: ['pod_name'],
                };
                const nextFields = fieldsForMethod[next] || [];
                nextFields.forEach((f) => { if (current[f]) keep[f] = current[f]; });
                form.resetFields();
                if (Object.keys(keep).length) {
                  setTimeout(() => form.setFieldsValue(keep), 0);
                }
                setIdMethod(next);
                resetSummary();
              }}
            >
              {ID_METHODS.map(m => <Radio.Button key={m.value} value={m.value}>{m.label}</Radio.Button>)}
            </Radio.Group>
          </Form.Item>

          <Form form={form} layout="vertical">
            <Row gutter={16}>
              {(idMethod === 'annotation' || idMethod === 'advanced') && (
                <>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="annotation_key"
                      label="Annotation Key"
                      tooltip="Use custom annotations set during deployment. Supports * wildcard for prefix matching (e.g. mycompany.com/* matches all keys starting with mycompany.com/)."
                      // Audit fix (UX gap): when the operator types
                      // an annotation_value but leaves the key blank,
                      // the backend silently ignores the value (it
                      // only ever filters on key first, then value).
                      // Telling them up-front avoids a copy/paste
                      // snippet that returns mysteriously broad
                      // results.
                      dependencies={['annotation_value']}
                      rules={[({ getFieldValue }) => ({
                        validator(_rule, value) {
                          if (!value && getFieldValue('annotation_value')) {
                            return Promise.reject(new Error('Annotation Value requires an Annotation Key — the backend ignores values without a key.'));
                          }
                          return Promise.resolve();
                        },
                      })]}
                    >
                      <Input placeholder="e.g. git-repo, mycompany.com/project-link, mycompany.com/*" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="annotation_value"
                      label="Annotation Value"
                      tooltip="Enter exact value or use * wildcard. Use * alone to match any value, or as prefix/suffix (e.g. https://tfs.company.com/*)."
                    >
                      <Input placeholder="e.g. exact-value, https://tfs.company.com/*, *" />
                    </Form.Item>
                  </Col>
                </>
              )}
              {(idMethod === 'label' || idMethod === 'advanced') && (
                <>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="label_key"
                      label="Label Key"
                      dependencies={['label_value']}
                      rules={[({ getFieldValue }) => ({
                        validator(_rule, value) {
                          if (!value && getFieldValue('label_value')) {
                            return Promise.reject(new Error('Label Value requires a Label Key — the backend ignores values without a key.'));
                          }
                          return Promise.resolve();
                        },
                      })]}
                    >
                      <Input placeholder="e.g. app" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item name="label_value" label="Label Value">
                      <Input placeholder="e.g. payment-service" />
                    </Form.Item>
                  </Col>
                </>
              )}
              {(idMethod === 'namespace_deployment' || idMethod === 'advanced') && (
                <Col xs={24} sm={12}>
                  {/* Deployment / L7 Workload owner — sibling to the
                      always-visible Namespace below. Hidden when the
                      operator picks a different ID method. */}
                  <Form.Item name="owner_name" label="Deployment / Workload Name">
                    <Input placeholder="e.g. payment-service" />
                  </Form.Item>
                </Col>
              )}
              {(idMethod === 'pod_name' || idMethod === 'advanced') && (
                <Col xs={24} sm={12}>
                  <Form.Item name="pod_name" label="Pod Name">
                    <Input placeholder="e.g. payment-service-7b9d4" />
                  </Form.Item>
                </Col>
              )}
              {idMethod === 'advanced' && (
                <Col xs={24} sm={12}>
                  <Form.Item name="ip" label="Pod IP">
                    <Input placeholder="e.g. 10.244.1.15" />
                  </Form.Item>
                </Col>
              )}
              {/* Audit v3 (UI3): namespace lives outside the radio so
                  it applies to every identification mode (annotation,
                  label, namespace_deployment, pod_name, advanced) and
                  to the L7 flow. Operators can scope by namespace as
                  an orthogonal filter without flipping radios. */}
              <Col xs={24} sm={12}>
                <Form.Item name="namespace" label="Namespace (applies to every method)">
                  <Input placeholder="e.g. production" />
                </Form.Item>
              </Col>
            </Row>
          </Form>

          {/*
            Plan v3 Akış D m.8 — discovery hint banner.

            Reactive via `Form.useWatch` (see hasAnyIdentificationField
            above) so the banner appears/disappears in real time as the
            operator types. Only shown when:
              • a non-L7 flow (L7 has its own workload search card)
              • at least one analysis is selected
              • no identification field is filled in
            Tells the operator ahead of time that submission will use
            discovery mode and which tenant guard applies. Avoids the
            "I clicked Test Query and got an error" surprise for
            multi-cluster selections without a namespace.
          */}
          {selectedAnalysisIds.length > 0 && !hasAnyIdentificationField && (
            <Alert
              type={singleClusterId != null ? 'info' : 'warning'}
              showIcon
              style={{ marginBottom: 16 }}
              message={
                <span>
                  <strong>Discovery mode</strong> — every workload in scope will be returned.
                  {singleClusterId != null
                    ? ` Cluster scope auto-detected from selection (cluster #${singleClusterId}).`
                    : ' Multi-cluster selection — fill in the Namespace field above to enable discovery, or narrow the analyses to a single cluster.'}
                  {' '}depth ≥ 3 is silently capped at 2 to keep results bounded.
                </span>
              }
            />
          )}

          <Form.Item label="Traversal Depth" style={{ maxWidth: 200 }}>
            <Select value={depth} onChange={setDepth}>
              {[1, 2, 3, 4, 5].map(d => <Option key={d} value={d}>Depth {d}{d === 1 ? ' (direct only)' : ''}</Option>)}
            </Select>
          </Form.Item>

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <Button
              type="primary"
              icon={<ExperimentOutlined />}
              onClick={onTestQuery}
              loading={effectiveLoading}
              disabled={!canProceedConfigure}
            >
              Test Query
            </Button>
          </div>

          {summaryErrMsg && !effectiveLoading && (
            <Alert type="error" showIcon style={{ marginTop: 16 }} message={summaryErrMsg} />
          )}

          {effectiveLoading && (
            <div style={{ marginTop: 24, textAlign: 'center' }}>
              <Spin tip={
                analysisLevel === 'both'
                  ? 'Querying L4 (network) and L7 (application) endpoints...'
                  : analysisLevel === 'l7'
                    ? 'Querying L7...'
                    : 'Querying L4...'
              } />
            </div>
          )}

          {/* Audit v3 (B-26): per-level success messaging. L4 uses the
              single-service shape (or the multi-service summary); L7
              surfaces workload + edge totals; BOTH stacks both lines. */}
          {!effectiveLoading && compositeSummary.l4Success && (analysisLevel === 'l4' || analysisLevel === 'both') && compositeSummary.l4 && (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              style={{ marginTop: 16 }}
              message={
                compositeSummary.l4.multi_service && compositeSummary.l4.matched_services ? (
                  <span>
                    L4 (network): <Text strong>{compositeSummary.l4.matched_services.length}</Text> matched service(s) · {compositeSummary.l4.summary?.total_downstream_unique ?? 0} downstream, {compositeSummary.l4.summary?.total_callers_unique ?? 0} callers
                  </span>
                ) : compositeSummary.l4.service ? (
                  <span>
                    L4 (network): <Text strong>{compositeSummary.l4.service.name}</Text> in <Text strong>{compositeSummary.l4.service.namespace}</Text>
                    {' \u2014 '}
                    {compositeSummary.l4.summary?.total_downstream_unique ?? 0} downstream, {compositeSummary.l4.summary?.total_callers_unique ?? 0} callers
                    {compositeSummary.l4.summary?.downstream_critical_count ? <Tag color="red" style={{ marginLeft: 8 }}>{compositeSummary.l4.summary.downstream_critical_count} critical</Tag> : null}
                  </span>
                ) : <span>L4 (network) query succeeded</span>
              }
            />
          )}

          {!effectiveLoading && compositeSummary.l7Success && (analysisLevel === 'l7' || analysisLevel === 'both') && compositeSummary.l7Summary && (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              style={{ marginTop: 16 }}
              message={
                <span>
                  L7 (application): <Text strong>{compositeSummary.l7Summary.workloads?.length ?? compositeSummary.l7Summary.summary?.total_matched ?? 0}</Text> workload(s) with L7 communication edges
                  {compositeSummary.l7Tree && !compositeSummary.l7Loading && (
                    <span> · Tree: <Text strong>{compositeSummary.l7Tree.summary?.total_downstream ?? 0}</Text> downstream, <Text strong>{compositeSummary.l7Tree.summary?.total_callers ?? 0}</Text> callers</span>
                  )}
                </span>
              }
            />
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={handleBackToTypeSelection}>
              Back
            </Button>
            <Space>
              {!effectiveSuccess && (
                <Button onClick={onSkipToSetup} disabled={!canProceedConfigure}>
                  Skip to Integration Code <ArrowRightOutlined />
                </Button>
              )}
              <Button
                type="primary"
                icon={<ArrowRightOutlined />}
                disabled={!effectiveSuccess}
                onClick={() => setCurrentStep(2)}
              >
                Preview Results
              </Button>
            </Space>
          </div>
        </Card>
      )}

      {/* ─── Dep Step 2: Preview & Validate ─── */}
      {/* Audit v3 (B-26): gate by composite effectiveSuccess so a BOTH
          flow with only one side returning data still reaches the
          preview (the failing side surfaces its error inside its tab). */}
      {integrationType === 'dependency' && currentStep === 2 && !effectiveSuccess && (
        <Card>
          <Alert
            type="warning"
            showIcon
            message="Preview data is no longer available. Please run Test Query again."
            style={{ marginBottom: 16 }}
          />
          <Button type="primary" onClick={() => setCurrentStep(1)}>Back to Configure</Button>
        </Card>
      )}
      {/* L7-only preview — uses composite L7 refs so BOTH mode can
          re-use the same JSX (via the Tabs wrapper below). */}
      {integrationType === 'dependency' && currentStep === 2 && analysisLevel === 'l7' && compositeSummary.l7Success && compositeSummary.l7Summary && (
        <div>
          <L7PreviewBody
            l7Summary={compositeSummary.l7Summary}
            l7Tree={compositeSummary.l7Tree}
            tokenPrimary={token.colorPrimary}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(1)}>
              Back
            </Button>
            <Space>
              <Link to={`/discovery/service-map?analysis_id=${selectedAnalysisIds?.[0] ?? ''}`}>
                <Button icon={<EyeOutlined />}>Open in Service Map</Button>
              </Link>
              <Link to={`/discovery/trace-explorer?analysis_id=${selectedAnalysisIds?.[0] ?? ''}`}>
                <Button>View Recent Traces</Button>
              </Link>
              <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => setCurrentStep(3)}>
                Integration Code
              </Button>
            </Space>
          </div>
        </div>
      )}
      {/* BOTH preview — Network (L4) and Application (L7) tabs.
          Each tab surfaces its own success or error state. */}
      {integrationType === 'dependency' && currentStep === 2 && analysisLevel === 'both' && effectiveSuccess && (
        <div>
          <Tabs
            defaultActiveKey={compositeSummary.l4Success ? 'l4' : 'l7'}
            items={[
              {
                key: 'l4',
                label: <span><BranchesOutlined /> Network Dependencies (L4)</span>,
                children: compositeSummary.l4Success && compositeSummary.l4 ? (
                  <L4PreviewBody
                    l4={compositeSummary.l4}
                    tokenPrimary={token.colorPrimary}
                    tokenError={token.colorError}
                    tokenSuccess={token.colorSuccess}
                    tokenBorderSecondary={token.colorBorderSecondary}
                    showL7Details
                    responseSize={responseSize}
                  />
                ) : (
                  <Alert
                    type="warning"
                    showIcon
                    message="L4 (network) data unavailable"
                    description={summaryErrMsg || 'The L4 dependency endpoint did not return any results for this query.'}
                  />
                ),
              },
              {
                key: 'l7',
                label: <span><ApiOutlined /> Application Dependencies (L7)</span>,
                children: compositeSummary.l7Success && compositeSummary.l7Summary ? (
                  <L7PreviewBody
                    l7Summary={compositeSummary.l7Summary}
                    l7Tree={compositeSummary.l7Tree}
                    tokenPrimary={token.colorPrimary}
                  />
                ) : (
                  <Alert
                    type="warning"
                    showIcon
                    message="L7 (application) data unavailable"
                    description={summaryErrMsg || 'The L7 dependency endpoint did not return any results for this query.'}
                  />
                ),
              },
            ]}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(1)}>
              Back
            </Button>
            <Space>
              <Link to={`/discovery/service-map?analysis_id=${selectedAnalysisIds?.[0] ?? ''}`}>
                <Button icon={<EyeOutlined />}>Open in Service Map</Button>
              </Link>
              <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => setCurrentStep(3)}>
                Integration Code
              </Button>
            </Space>
          </div>
        </div>
      )}
      {integrationType === 'dependency' && currentStep === 2 && analysisLevel === 'l4' && compositeSummary.l4Success && compositeSummary.l4 && (
        <div>
          <L4PreviewBody
            l4={compositeSummary.l4}
            tokenPrimary={token.colorPrimary}
            tokenError={token.colorError}
            tokenSuccess={token.colorSuccess}
            tokenBorderSecondary={token.colorBorderSecondary}
            showL7Details={false}
            responseSize={responseSize}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(1)}>
              Back
            </Button>
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => setCurrentStep(3)}>
              Integration Code
            </Button>
          </div>
        </div>
      )}

      {/* ─── Dep Step 3: Integration Code ─── */}
      {integrationType === 'dependency' && currentStep === 3 && !effectiveSuccess && !summaryParams && (
        <Card>
          <Alert
            type="warning"
            showIcon
            message="Configuration required. Please set up your query in the Configure step."
            style={{ marginBottom: 16 }}
          />
          <Button type="primary" onClick={() => setCurrentStep(1)}>Back to Configure</Button>
        </Card>
      )}
      {integrationType === 'dependency' && currentStep === 3 && (effectiveSuccess || summaryParams) && (() => {
        // Audit v3 (UI3 + B-30): in BOTH mode the operator gets a
        // top-level L4/L7 radio toggle and the snippet tabs render
        // for the chosen side only. In pure modes the effective
        // level is fixed and the toggle is hidden.
        const effectiveSnippetLevel: 'l4' | 'l7' = analysisLevel === 'both'
          ? snippetLevelToggle
          : analysisLevel;
        const isL7 = effectiveSnippetLevel === 'l7';
        return (
        <div>
          {!effectiveSuccess && (
            <Alert
              type="warning"
              showIcon
              message="Test Query was skipped — snippets are generated from your configured parameters. Run Test Query in the Configure step to preview and validate results."
              style={{ marginBottom: 16 }}
            />
          )}
          {/* Audit v3 (UX1): the L7 single-analysis limit applies to
              both pure L7 and BOTH-mode snippets, so the banner
              triggers whenever the operator landed on the L7 side
              of the toggle with more than one analysis selected. */}
          {isL7 && selectedAnalysisIds.length > 1 && (
            <Alert
              type="warning"
              showIcon
              message="L7 snippets target a single analysis"
              description={`The L7 dependency endpoints accept only one analysis at a time. Generated snippets will use analysis #${selectedAnalysisIds[0]} (${selectedAnalysisIds.length - 1} other ${selectedAnalysisIds.length - 1 === 1 ? 'analysis is' : 'analyses are'} ignored). The L4 snippets in this Hub still cover every selected analysis.`}
              style={{ marginBottom: 16 }}
            />
          )}
          {!isL7 && summaryParams && summaryParams.match_all && summaryParams.cluster_id == null && (
            <Alert
              type="warning"
              showIcon
              message="Discovery mode without an explicit cluster"
              description="Your selection covers multiple clusters. The generated snippets include match_all=true and a namespace filter, but no cluster_id. Add a Namespace in the Configure step or narrow the analyses to one cluster if you want a stricter tenant guard."
              style={{ marginBottom: 16 }}
            />
          )}
          <Alert
            type="info"
            showIcon
            message="All snippets below use your selected parameters. Copy and adapt to your environment."
            style={{ marginBottom: 16 }}
          />

          {analysisLevel === 'both' && (
            <div style={{ marginBottom: 16 }}>
              <Radio.Group
                value={snippetLevelToggle}
                onChange={(e) => setSnippetLevelToggle(e.target.value)}
                buttonStyle="solid"
              >
                <Radio.Button value="l4">Network (L4) Snippets</Radio.Button>
                <Radio.Button value="l7">Application (L7) Snippets</Radio.Button>
              </Radio.Group>
            </div>
          )}

          <Tabs
            items={[
              {
                key: 'pipeline',
                label: <span><RocketOutlined /> Pipeline</span>,
                children: (
                  <div>
                    <Space align="center" style={{ marginBottom: 12 }}>
                      <Text strong>Platform:</Text>
                      <Select value={platform} onChange={setPlatform} style={{ width: 200 }}>
                        {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
                      </Select>
                    </Space>
                    <CodeBlock code={isL7 ? buildL7PipelineSnippet(summaryParams, platform) : buildPipelineSnippet(summaryParams, platform)} label="Pipeline YAML" />
                  </div>
                ),
              },
              {
                key: 'curl',
                label: <span><CodeOutlined /> curl</span>,
                children: <CodeBlock code={isL7 ? buildL7CurlSnippet(summaryParams) : buildCurlSnippet(summaryParams)} label="curl" />,
              },
              {
                key: 'python',
                label: <span><CodeOutlined /> Python</span>,
                children: <CodeBlock code={isL7 ? buildL7PythonSnippet(summaryParams) : buildPythonSnippet(summaryParams)} label="Python" />,
              },
              {
                key: 'js',
                label: <span><CodeOutlined /> JavaScript</span>,
                children: <CodeBlock code={isL7 ? buildL7JsSnippet(summaryParams) : buildJsSnippet(summaryParams)} label="JavaScript" />,
              },
              ...(isL7 ? [{
                key: 'java',
                label: <span><CodeOutlined /> Java</span>,
                children: <CodeBlock code={buildL7JavaSnippet(summaryParams)} label="Java" />,
              }] : []),
              ...(isL7 ? [{
                key: 'tree-curl',
                label: <span><BranchesOutlined /> Tree curl</span>,
                children: <CodeBlock code={buildL7TreeCurlSnippet(summaryParams)} label="Tree-summary curl" />,
              }, {
                key: 'tree-python',
                label: <span><BranchesOutlined /> Tree Python</span>,
                children: <CodeBlock code={buildL7TreePythonSnippet(summaryParams)} label="Tree-summary Python" />,
              }, {
                key: 'tree-pipeline',
                label: <span><BranchesOutlined /> Tree Pipeline</span>,
                children: (
                  <div>
                    <Space align="center" style={{ marginBottom: 12 }}>
                      <Text strong>Platform:</Text>
                      <Select value={platform} onChange={setPlatform} style={{ width: 200 }}>
                        {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
                      </Select>
                    </Space>
                    <CodeBlock code={buildL7TreePipelineSnippet(summaryParams, platform)} label="Tree-summary Pipeline" />
                  </div>
                ),
              }] : []),
              {
                key: 'blast-radius',
                label: <span><ThunderboltOutlined /> Blast Radius</span>,
                children: (
                  <div>
                    <Alert
                      type="info"
                      showIcon
                      icon={<InfoCircleOutlined />}
                      message="Pre-deployment risk assessment"
                      description={<>Use this endpoint to assess the impact of deploying changes to a service. You can also <Button type="link" style={{ padding: 0 }} onClick={handleBackToTypeSelection}>set up Blast Radius as a dedicated integration type</Button> from Step 1.</>}
                      style={{ marginBottom: 16 }}
                    />
                    <Tabs
                      size="small"
                      items={[
                        {
                          key: 'br-curl',
                          label: 'curl',
                          children: <CodeBlock code={buildBlastRadiusCurlSnippet(contextNamespace, contextOwnerName, summaryParams?.cluster_id ?? undefined)} label="Blast Radius curl" />,
                        },
                        {
                          key: 'br-pipeline',
                          label: `Pipeline (${PIPELINE_PLATFORMS.find(p => p.value === platform)?.label || 'Pipeline'})`,
                          children: <CodeBlock code={buildBlastRadiusPipelineSnippet(platform, contextNamespace, contextOwnerName, summaryParams?.cluster_id ?? undefined)} label="Blast Radius Pipeline" />,
                        },
                      ]}
                    />
                    <div style={{ marginTop: 12 }}>
                      <Link to="/impact/blast-radius?tab=test">
                        <Button type="link" style={{ padding: 0 }}>
                          <ThunderboltOutlined /> Test blast radius assessments interactively
                        </Button>
                      </Link>
                    </div>
                  </div>
                ),
              },
            ]}
          />

          {authCard}

          <Card title="Understanding the Response" size="small" style={{ marginTop: 16 }}>
            {isL7 ? (
              <>
                <Paragraph>
                  The <Text code>/l7/dependencies/summary</Text> response provides <Text strong>per-workload L7 communication summaries</Text>.
                  Each workload includes inbound/outbound connection counts, request totals, error counts, and error rates derived from eBPF-captured HTTP/gRPC traffic.
                </Paragraph>
                <Paragraph>
                  Your pipeline should:
                </Paragraph>
                <ol>
                  <li>Iterate <Text code>workloads</Text> to process each L7 workload and its communication metrics</li>
                  <li>Check <Text code>error_rate_percent</Text> to identify workloads with elevated error rates</li>
                  <li>Use <Text code>inbound_count</Text> and <Text code>outbound_count</Text> to understand the dependency fan-in/fan-out</li>
                  <li>Use <Text code>/l7/dependencies/tree-summary</Text> with <Text code>workload_name</Text> and <Text code>depth</Text> for directed dependency traversal</li>
                  <li>Filter by <Text code>is_matched=true</Text> if your snippet used annotation/label/owner filters and you only want originally matched workloads (neighbours are returned with <Text code>is_matched=false</Text>)</li>
                  <li>Use <Text code>summary</Text> for aggregate counts across all matched workloads</li>
                </ol>
              </>
            ) : (
              <>
                <Paragraph>
                  The <Text code>/dependencies/summary</Text> response provides <Text strong>per-service dependency breakdowns</Text>.
                  Each matched upstream service includes its own <Text code>downstream</Text> and <Text code>callers</Text> grouped by service category (database, cache, api, message_broker, etc.).
                  A top-level <Text code>summary</Text> provides globally deduplicated aggregate counts.
                </Paragraph>
                <Paragraph>
                  Your pipeline should:
                </Paragraph>
                <ol>
                  <li>Iterate <Text code>matched_services</Text> to process each upstream service and its dependencies</li>
                  <li>For each service, extract <Text code>annotations[&quot;git-repo&quot;]</Text> from downstream dependencies to identify affected repositories</li>
                  <li>Check <Text code>is_critical</Text> flag to prioritize critical dependency changes</li>
                  <li>Use <Text code>hop_count</Text> (when depth &gt; 1) to distinguish direct from indirect dependencies</li>
                  <li>Use <Text code>summary</Text> for aggregate counts across all matched services</li>
                </ol>
              </>
            )}
          </Card>

          <Collapse
            size="small"
            style={{ marginTop: 16 }}
            items={[{
              key: 'response-fields',
              label: 'Response Fields Reference',
              children: isL7 ? (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label={<Text code>success</Text>}>Boolean — query result status</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[]</Text>}>Array of L7 workload objects</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].name</Text>}>Workload name (Deployment/StatefulSet)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].namespace</Text>}>Kubernetes namespace</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].cluster</Text>}>Cluster name</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].inbound_count</Text>}>Number of inbound communication edges</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].outbound_count</Text>}>Number of outbound communication edges</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].request_count</Text>}>Total L7 requests observed</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].error_count</Text>}>Total L7 errors (4xx/5xx, gRPC errors)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].error_rate_percent</Text>}>Percentage of requests that errored</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].is_matched</Text>}>True for workloads that matched the filter (annotation/label/owner_name/pod_name); false for neighbours returned for context. Field is omitted when no filter is active.</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].owner_kind</Text>}>Controller kind: Deployment, StatefulSet, DaemonSet, or empty</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].labels</Text>}>Pod labels (filtered, noisy keys removed)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>workloads[].annotations</Text>}>Pod annotations (filtered, noisy keys removed)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>summary.total_matched</Text>}>Total matched workloads</Descriptions.Item>
                </Descriptions>
              ) : (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label={<Text code>success</Text>}>Boolean — query result status</Descriptions.Item>
                  <Descriptions.Item label={<Text code>matched_services[]</Text>}>Array of matched upstream services</Descriptions.Item>
                  <Descriptions.Item label={<Text code>downstream</Text>}>Services called by this service</Descriptions.Item>
                  <Descriptions.Item label={<Text code>callers</Text>}>Services that call this service</Descriptions.Item>
                  <Descriptions.Item label={<Text code>is_critical</Text>}>Whether this dependency is marked critical</Descriptions.Item>
                  <Descriptions.Item label={<Text code>annotations</Text>}>Pod annotations (git-repo, team, etc.)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>hop_count</Text>}>Dependency distance (when depth {">"} 1)</Descriptions.Item>
                  <Descriptions.Item label={<Text code>summary</Text>}>Aggregate counts across all matches</Descriptions.Item>
                </Descriptions>
              ),
            }]}
          />

          <div style={{ marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(effectiveSuccess ? 2 : 1)}>
              {effectiveSuccess ? 'Back to Preview' : 'Back to Configure'}
            </Button>
          </div>
        </div>
        );
      })()}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* BLAST RADIUS GATE FLOW (Steps 1-2)                        */}
      {/* ═══════════════════════════════════════════════════════════ */}

      {/* ─── BR Step 1: Configure ─── */}
      {integrationType === 'blast_radius' && currentStep === 1 && (
        <Card title="Blast Radius Gate Configuration">
          <Paragraph type="secondary">
            Configure your pre-deployment risk assessment integration. The Blast Radius API evaluates the impact of changes
            and returns a risk score with recommendations — your pipeline decides what to do.
          </Paragraph>

          <Divider />

          <Form layout="vertical">
            <Form.Item label="Pipeline Platform" required>
              <Select value={platform} onChange={setPlatform} style={{ maxWidth: 300 }}>
                {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
              </Select>
            </Form.Item>

            <Form.Item
              label="Cluster"
              required
              tooltip="Blast Radius is scoped to one cluster at a time. Pick the cluster you want to assess, or leave empty to render a CI variable placeholder (CLUSTER_ID) so the same snippet can be reused across environments."
            >
              <Select
                allowClear
                placeholder="Select a cluster (or leave empty for a templated CI variable)"
                style={{ maxWidth: 420 }}
                value={brClusterId ?? undefined}
                onChange={(v) => setBrClusterId(v ?? null)}
                options={clusters.map((c: any) => ({ value: c.id, label: c.name }))}
              />
            </Form.Item>

            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item
                  label="Target Service Name"
                  tooltip="Optional — if left empty, snippets will use a placeholder. You can parameterize this in your pipeline."
                >
                  <Input
                    placeholder="e.g. payment-service"
                    value={brTargetService}
                    onChange={e => setBrTargetService(e.target.value)}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  label="Target Namespace"
                  tooltip="Optional — defaults to 'default' in generated snippets."
                >
                  <Input
                    placeholder="e.g. production"
                    value={brTargetNamespace}
                    onChange={e => setBrTargetNamespace(e.target.value)}
                  />
                </Form.Item>
              </Col>
            </Row>
          </Form>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={handleBackToTypeSelection}>
              Back
            </Button>
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => setCurrentStep(2)}>
              Generate Integration Code
            </Button>
          </div>
        </Card>
      )}

      {/* ─── BR Step 2: Integration Code ─── */}
      {integrationType === 'blast_radius' && currentStep === 2 && (
        <div>
          <Alert
            type="info"
            showIcon
            message="All snippets below use your configured parameters. Copy and adapt to your environment."
            style={{ marginBottom: 16 }}
          />

          <Tabs
            items={[
              {
                key: 'br-pipeline',
                label: <span><RocketOutlined /> Pipeline</span>,
                children: (
                  <div>
                    <Space align="center" style={{ marginBottom: 12 }}>
                      <Text strong>Platform:</Text>
                      <Select value={platform} onChange={setPlatform} style={{ width: 200 }}>
                        {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
                      </Select>
                    </Space>
                    <CodeBlock code={buildBlastRadiusPipelineSnippet(platform, brTargetNamespace || undefined, brTargetService || undefined, brClusterId ?? undefined)} label="Blast Radius Pipeline" />
                  </div>
                ),
              },
              {
                key: 'br-curl',
                label: <span><CodeOutlined /> curl</span>,
                children: <CodeBlock code={buildBlastRadiusCurlSnippet(brTargetNamespace || undefined, brTargetService || undefined, brClusterId ?? undefined)} label="Blast Radius curl" />,
              },
            ]}
          />

          <Card title="Example Response" size="small" style={{ marginTop: 16 }}>
            <Paragraph type="secondary" style={{ marginBottom: 8 }}>
              The <Text code>POST /api/v1/blast-radius/assess</Text> endpoint returns a risk assessment:
            </Paragraph>
            <CodeBlock code={EXAMPLE_BR_RESPONSE} label="Example Response" />
          </Card>

          <Card title="Response Fields" size="small" style={{ marginTop: 16 }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label={<Text code>risk_score</Text>}>0-100, higher = more risky</Descriptions.Item>
              <Descriptions.Item label={<Text code>risk_level</Text>}>low / medium / high / critical</Descriptions.Item>
              <Descriptions.Item label={<Text code>blast_radius.total_affected</Text>}>Total services in impact zone</Descriptions.Item>
              <Descriptions.Item label={<Text code>blast_radius.critical_services</Text>}>Names of critical downstream services</Descriptions.Item>
              <Descriptions.Item label={<Text code>recommendation</Text>}>proceed / review_required / delay_suggested</Descriptions.Item>
              <Descriptions.Item label={<Text code>advisory_only</Text>}>Always true — Flowfish never blocks deployments</Descriptions.Item>
            </Descriptions>
          </Card>

          {authCard}

          <div style={{ marginTop: 16 }}>
            <Link to="/impact/blast-radius?tab=test">
              <Button type="link" icon={<ThunderboltOutlined />} style={{ padding: 0 }}>
                Test blast radius assessments interactively
              </Button>
            </Link>
          </div>

          <div style={{ marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(1)}>
              Back to Configure
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default IntegrationHub;
