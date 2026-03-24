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
  Slider,
  Divider,
  Empty,
  Tooltip,
  Progress,
  message,
  Spin,
  Row,
  Col,
  Descriptions,
  Statistic,
} from 'antd';
import {
  RobotOutlined,
  SearchOutlined,
  ApartmentOutlined,
  ThunderboltOutlined,
  CodeOutlined,
  CopyOutlined,
  DownloadOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import {
  useGetPodDependencyStreamQuery,
  useGetDependencyImpactQuery,
  useGetDependencyDiffQuery,
  PodDependencyStreamParams,
  PodDependencyInfo,
  DependencyHealthScore,
  SuggestedAction,
} from '../store/api/communicationApi';

const { Text, Title, Paragraph } = Typography;

const API_BASE = typeof window !== 'undefined' ? `${window.location.origin}/api/v1` : '/api/v1';

const CHANGE_TYPES = [
  { value: 'image_update', label: 'Image Update' },
  { value: 'config_change', label: 'Config Change' },
  { value: 'scale_change', label: 'Scale Change' },
  { value: 'delete', label: 'Delete' },
];

const CODE_BLOCK_STYLE: React.CSSProperties = {
  background: '#0d1117',
  color: '#e6edf3',
  padding: 16,
  borderRadius: 8,
  overflow: 'auto',
  fontSize: 12,
  margin: 0,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
};

function healthScoreToVisual(score: number | undefined) {
  if (score == null || Number.isNaN(score)) return { label: 'Unknown', color: 'default' };
  if (score >= 80) return { label: 'Healthy', color: 'success' };
  if (score >= 60) return { label: 'Degraded', color: 'warning' };
  if (score >= 30) return { label: 'Unhealthy', color: 'orange' };
  return { label: 'Critical', color: 'error' };
}

function HealthBadge({ health }: { health?: DependencyHealthScore }) {
  const score = health?.score;
  const { label } = healthScoreToVisual(score);
  const display = score != null ? `${Math.round(score)}` : '\u2014';
  const badgeColor =
    score == null || Number.isNaN(score)
      ? '#d9d9d9'
      : score >= 80
        ? '#52c41a'
        : score >= 60
          ? '#faad14'
          : score >= 30
            ? '#fa8c16'
            : '#cf1322';
  return (
    <Tooltip title={health ? `${label} \u00b7 err ${health.error_rate_percent?.toFixed?.(2) ?? 0}%` : undefined}>
      <Badge color={badgeColor} text={display} />
    </Tooltip>
  );
}

function riskProgressColor(percent: number): string {
  if (percent >= 70) return '#cf1322';
  if (percent >= 40) return '#faad14';
  return '#52c41a';
}

function RecommendationBadge({ rec }: { rec: 'proceed' | 'caution' | 'block' }) {
  const map = {
    proceed: { color: 'success' as const, icon: <CheckCircleOutlined />, text: 'Proceed' },
    caution: { color: 'warning' as const, icon: <WarningOutlined />, text: 'Caution' },
    block: { color: 'error' as const, icon: <CloseCircleOutlined />, text: 'Block' },
  };
  const m = map[rec] ?? map.proceed;
  return <Tag icon={m.icon} color={m.color}>{m.text}</Tag>;
}

function UpstreamBanner({ upstream, downstream, callers }: {
  upstream?: PodDependencyInfo;
  downstream: PodDependencyInfo[];
  callers: PodDependencyInfo[];
}) {
  if (!upstream) return null;
  return (
    <Card size="small" style={{ borderLeft: '3px solid #1677ff' }}>
      <Row gutter={16} align="middle">
        <Col flex="auto">
          <Space split={<Divider type="vertical" />}>
            <Text strong>{upstream.owner_name || upstream.pod_name}</Text>
            <Text type="secondary">{upstream.namespace}</Text>
            {upstream.owner_kind && <Tag>{upstream.owner_kind}</Tag>}
          </Space>
        </Col>
        <Col>
          <Space size="large">
            <Statistic title={<><ArrowDownOutlined /> Downstream</>} value={downstream.length} valueStyle={{ fontSize: 18 }} />
            <Statistic title={<><ArrowUpOutlined /> Callers</>} value={callers.length} valueStyle={{ fontSize: 18 }} />
          </Space>
        </Col>
      </Row>
    </Card>
  );
}

function CodeBlockWithCopy({ code, label }: { code: string; label: string }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      message.success(`${label} copied`);
    } catch {
      message.error('Clipboard unavailable');
    }
  };
  return (
    <div style={{ position: 'relative' }}>
      <Button
        size="small"
        icon={<CopyOutlined />}
        onClick={copy}
        style={{ position: 'absolute', top: 8, right: 8, zIndex: 1, opacity: 0.85 }}
      >
        Copy
      </Button>
      <pre style={CODE_BLOCK_STYLE}>{code}</pre>
    </div>
  );
}

function buildExportMermaid(root: PodDependencyInfo, downstream: PodDependencyInfo[]): string {
  const lines = ['flowchart LR', `  root["${root.pod_name}\\n${root.namespace}"]`];
  downstream.slice(0, 24).forEach((d, i) => {
    lines.push(`  d${i}["${d.pod_name}\\n${d.namespace}"]`);
    lines.push(`  root --> d${i}`);
  });
  return lines.join('\n');
}

function buildExportDot(root: PodDependencyInfo, downstream: PodDependencyInfo[]): string {
  const lines = ['digraph G {', `  root [label="${root.pod_name}\\n${root.namespace}"];`];
  downstream.slice(0, 24).forEach((d, i) => {
    lines.push(`  d${i} [label="${d.pod_name}\\n${d.namespace}"];`);
    lines.push(`  root -> d${i};`);
  });
  lines.push('}');
  return lines.join('\n');
}

const URL_PARAM_FIELDS = [
  'analysis_id', 'cluster_id', 'namespace', 'pod_name', 'owner_name',
  'label_key', 'label_value', 'annotation_key', 'annotation_value', 'ip',
] as const;

const AIIntegrationHub: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [currentStep, setCurrentStep] = useState(0);
  const [depth, setDepth] = useState(2);
  const [changeType, setChangeType] = useState('image_update');
  const [streamParams, setStreamParams] = useState<PodDependencyStreamParams | null>(null);
  const [diffAnalysisBefore, setDiffAnalysisBefore] = useState('');
  const [diffAnalysisAfter, setDiffAnalysisAfter] = useState('');

  useEffect(() => {
    const prefill: Record<string, string> = {};
    let hasAny = false;
    for (const key of URL_PARAM_FIELDS) {
      const val = searchParams.get(key);
      if (val) {
        prefill[key] = val;
        hasAny = true;
      }
    }
    if (hasAny) {
      form.setFieldsValue(prefill);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    data: streamData,
    isFetching: streamLoading,
    isError: streamIsError,
    error: streamError,
  } = useGetPodDependencyStreamQuery(streamParams as PodDependencyStreamParams, {
    skip: !streamParams,
  });

  const firstResult = streamData?.results?.[0];
  const upstream = firstResult?.upstream;
  const downstreamRows = firstResult?.downstream ?? [];
  const callerRows = firstResult?.callers ?? [];

  const impactParams = useMemo(() => {
    if (!streamParams) return undefined;
    return {
      analysis_id: streamParams.analysis_id,
      cluster_id: streamParams.cluster_id,
      pod_name: streamParams.pod_name ?? upstream?.pod_name,
      namespace: streamParams.namespace ?? upstream?.namespace,
      owner_name: streamParams.owner_name,
      label_key: streamParams.label_key,
      label_value: streamParams.label_value,
      annotation_key: streamParams.annotation_key,
      annotation_value: streamParams.annotation_value,
      ip: streamParams.ip,
      depth,
      change_type: changeType,
    };
  }, [streamParams, upstream, depth, changeType]);

  const {
    data: impactData,
    isFetching: impactLoading,
    isError: impactIsError,
    error: impactError,
  } = useGetDependencyImpactQuery(impactParams!, {
    skip: !impactParams || currentStep !== 2,
  });

  const diffParams = useMemo(() => {
    if (!diffAnalysisBefore.trim() || !diffAnalysisAfter.trim()) return undefined;
    return {
      analysis_id_before: diffAnalysisBefore.trim(),
      analysis_id_after: diffAnalysisAfter.trim(),
      pod_name: streamParams?.pod_name ?? upstream?.pod_name,
      namespace: streamParams?.namespace ?? upstream?.namespace,
      owner_name: streamParams?.owner_name,
      cluster_id: streamParams?.cluster_id,
    };
  }, [diffAnalysisBefore, diffAnalysisAfter, streamParams, upstream]);

  const {
    data: diffData,
    isFetching: diffLoading,
    isError: diffIsError,
    error: diffError,
  } = useGetDependencyDiffQuery(diffParams!, {
    skip: currentStep !== 2 || !diffParams,
  });

  const onSearch = useCallback(async () => {
    try {
      const values = await form.validateFields();
      const next: PodDependencyStreamParams = {
        analysis_id: values.analysis_id != null && values.analysis_id !== '' ? Number(values.analysis_id) : undefined,
        cluster_id: values.cluster_id != null && values.cluster_id !== '' ? Number(values.cluster_id) : undefined,
        namespace: values.namespace?.trim() || undefined,
        pod_name: values.pod_name?.trim() || undefined,
        owner_name: values.owner_name?.trim() || undefined,
        label_key: values.label_key?.trim() || undefined,
        label_value: values.label_value?.trim() || undefined,
        annotation_key: values.annotation_key?.trim() || undefined,
        annotation_value: values.annotation_value?.trim() || undefined,
        ip: values.ip?.trim() || undefined,
        depth,
      };
      setStreamParams(next);
    } catch {
      /* validation */
    }
  }, [form, depth]);

  const onDepthChange = (v: number) => {
    setDepth(v);
    setStreamParams((prev) => (prev ? { ...prev, depth: v } : null));
  };

  const goNext = () => setCurrentStep((s) => Math.min(3, s + 1));
  const goPrev = () => setCurrentStep((s) => Math.max(0, s - 1));

  const queryStringFromParams = (p: PodDependencyStreamParams) => {
    const sp = new URLSearchParams();
    if (p.analysis_id != null) sp.set('analysis_id', String(p.analysis_id));
    if (p.cluster_id != null) sp.set('cluster_id', String(p.cluster_id));
    if (p.namespace) sp.set('namespace', p.namespace);
    if (p.pod_name) sp.set('pod_name', p.pod_name);
    if (p.owner_name) sp.set('owner_name', p.owner_name);
    if (p.label_key) sp.set('label_key', p.label_key);
    if (p.label_value) sp.set('label_value', p.label_value);
    if (p.annotation_key) sp.set('annotation_key', p.annotation_key);
    if (p.annotation_value) sp.set('annotation_value', p.annotation_value);
    if (p.ip) sp.set('ip', p.ip);
    if (p.depth != null) sp.set('depth', String(p.depth));
    return sp.toString();
  };

  const snippets = useMemo(() => {
    const qs = streamParams ? queryStringFromParams(streamParams) : '';
    const streamUrl = `${API_BASE}/communications/dependencies/stream`;
    const impactUrl = `${API_BASE}/communications/dependencies/impact`;

    const curl = `curl -sS -H "Authorization: Bearer $FLOWFISH_API_TOKEN" \\
  "${streamUrl}?${qs}"`;

    const curlImpact = `curl -sS -H "Authorization: Bearer $FLOWFISH_API_TOKEN" \\
  "${impactUrl}?${qs}&change_type=image_update"`;

    const filteredEntries = streamParams
      ? Object.entries({
          analysis_id: streamParams.analysis_id,
          cluster_id: streamParams.cluster_id,
          namespace: streamParams.namespace,
          pod_name: streamParams.pod_name,
          owner_name: streamParams.owner_name,
          label_key: streamParams.label_key,
          label_value: streamParams.label_value,
          annotation_key: streamParams.annotation_key,
          annotation_value: streamParams.annotation_value,
          ip: streamParams.ip,
          depth: streamParams.depth,
        }).filter(([, v]) => v != null && v !== '')
      : [];

    const pyParamsBlock = filteredEntries.length
      ? filteredEntries.map(([k, v]) => `    "${k}": ${JSON.stringify(v)},`).join('\n')
      : '    # add query params';

    const python = `import os, requests

BASE = os.environ.get("FLOWFISH_API_BASE", "${API_BASE}")
TOKEN = os.environ["FLOWFISH_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# 1. Get dependency stream
params = {
${pyParamsBlock}
}
deps = requests.get(f"{BASE}/communications/dependencies/stream", params=params, headers=HEADERS).json()
print(f"Found {deps.get('count', 0)} upstream matches")

# 2. Get impact assessment (optional)
params["change_type"] = "image_update"
impact = requests.get(f"{BASE}/communications/dependencies/impact", params=params, headers=HEADERS).json()
print(f"Risk: {impact.get('impact_assessment', {}).get('risk_score', '?')}/100")`;

    const jsParamsObj = streamParams
      ? JSON.stringify(
          Object.fromEntries(filteredEntries),
          null,
          2,
        )
      : '{}';

    const javascript = `const BASE = process.env.FLOWFISH_API_BASE || "${API_BASE}";
const TOKEN = process.env.FLOWFISH_API_TOKEN;
const headers = { Authorization: \`Bearer \${TOKEN}\` };

// 1. Dependency stream
const qs = new URLSearchParams(${jsParamsObj});
const deps = await fetch(\`\${BASE}/communications/dependencies/stream?\${qs}\`, { headers });
const data = await deps.json();
console.log(\`Upstream: \${data.results?.[0]?.upstream?.pod_name}\`);
console.log(\`Downstream: \${data.results?.[0]?.downstream?.length} services\`);

// 2. Impact assessment (optional)
qs.set("change_type", "image_update");
const impact = await fetch(\`\${BASE}/communications/dependencies/impact?\${qs}\`, { headers });
console.log(await impact.json());`;

    const azure = `# Azure Pipelines \u2014 Flowfish dependency & impact gate
trigger:
  - main

pool:
  vmImage: ubuntu-latest

steps:
  - bash: |
      set -e
      DEPS=$(curl -sS -f -H "Authorization: Bearer $(FLOWFISH_API_TOKEN)" \\
        "${streamUrl}?${qs}")
      echo "$DEPS" | jq '.results[0] | {upstream: .upstream.pod_name, downstream: (.downstream | length), callers: (.callers | length)}'

      IMPACT=$(curl -sS -f -H "Authorization: Bearer $(FLOWFISH_API_TOKEN)" \\
        "${impactUrl}?${qs}&change_type=image_update")
      RISK=$(echo "$IMPACT" | jq '.impact_assessment.risk_score')
      echo "Risk score: $RISK"
      if [ "$RISK" -ge 70 ]; then echo "##vso[task.logissue type=error]High risk deployment!"; exit 1; fi
    displayName: Flowfish Impact Gate
    env:
      FLOWFISH_API_TOKEN: $(FLOWFISH_API_TOKEN)`;

    const gha = `name: flowfish-impact-gate
on: [push, workflow_dispatch]

jobs:
  impact-check:
    runs-on: ubuntu-latest
    steps:
      - name: Check dependencies & impact
        env:
          FLOWFISH_API_TOKEN: \${{ secrets.FLOWFISH_API_TOKEN }}
        run: |
          set -e
          DEPS=$(curl -sS -f -H "Authorization: Bearer $FLOWFISH_API_TOKEN" \\
            "${streamUrl}?${qs}")
          echo "$DEPS" | jq '.results[0] | {upstream: .upstream.pod_name, downstream: (.downstream | length)}'

          IMPACT=$(curl -sS -f -H "Authorization: Bearer $FLOWFISH_API_TOKEN" \\
            "${impactUrl}?${qs}&change_type=image_update")
          RISK=$(echo "$IMPACT" | jq '.impact_assessment.risk_score')
          echo "::notice::Risk score: $RISK/100"
          if [ "$RISK" -ge 70 ]; then echo "::error::High risk! Blocking."; exit 1; fi`;

    return { curl, curlImpact, python, javascript, azure, gha };
  }, [streamParams]);

  const downstreamColumns = useMemo(
    () => [
      { title: 'Name', dataIndex: 'pod_name', key: 'pod_name', ellipsis: true },
      { title: 'Namespace', dataIndex: 'namespace', key: 'namespace', width: 140 },
      {
        title: 'Type',
        key: 'service_type',
        width: 150,
        render: (_: unknown, r: PodDependencyInfo) => {
          const t = r.communication?.service_type;
          const cat = r.communication?.service_category;
          const critical = r.communication?.is_critical;
          if (!t || t === 'unknown') return <Text type="secondary">{'\u2014'}</Text>;
          return (
            <Space size={4} wrap>
              <Tag color={critical ? 'red' : undefined}>{t}</Tag>
              {cat && cat !== 'service' && cat !== t && <Text type="secondary" style={{ fontSize: 11 }}>{cat}</Text>}
            </Space>
          );
        },
      },
      {
        title: 'Port',
        key: 'port',
        width: 72,
        render: (_: unknown, r: PodDependencyInfo) => r.communication?.port ?? '\u2014',
      },
      {
        title: 'Protocol',
        key: 'proto',
        width: 100,
        render: (_: unknown, r: PodDependencyInfo) =>
          r.communication?.app_protocol || r.communication?.protocol || '\u2014',
      },
      {
        title: 'Health',
        key: 'health',
        width: 90,
        render: (_: unknown, r: PodDependencyInfo) => <HealthBadge health={r.health} />,
      },
      {
        title: 'Hop',
        key: 'hop',
        width: 56,
        render: (_: unknown, r: PodDependencyInfo) => r.hop_count ?? '\u2014',
      },
      {
        title: 'Requests',
        key: 'req',
        width: 100,
        render: (_: unknown, r: PodDependencyInfo) => {
          const c = r.communication?.request_count;
          return c != null ? c.toLocaleString() : '\u2014';
        },
      },
      {
        title: 'Error Rate',
        key: 'err',
        width: 100,
        render: (_: unknown, r: PodDependencyInfo) => {
          const er = r.health?.error_rate_percent ?? r.communication?.error_rate_percent;
          if (er == null) return '\u2014';
          const val = Number(er);
          return <Text type={val > 5 ? 'danger' : val > 1 ? 'warning' : undefined}>{val.toFixed(2)}%</Text>;
        },
      },
    ],
    []
  );

  const canGoNextFromStep0 = Boolean(streamParams && streamData?.success && (streamData?.count ?? 0) > 0);
  const assessment = impactData?.impact_assessment;
  const riskPct = Math.min(100, Math.max(0, assessment?.risk_score ?? 0));

  const streamErrMsg =
    streamIsError && streamError && 'data' in streamError
      ? String((streamError as { data?: { detail?: string } }).data?.detail ?? 'Request failed')
      : streamIsError
        ? 'Failed to load dependency stream'
        : null;

  const StepNav = ({ disableNext }: { disableNext?: boolean }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24, paddingTop: 16, borderTop: '1px solid #f0f0f0' }}>
      <Button
        icon={<ArrowLeftOutlined />}
        disabled={currentStep === 0}
        onClick={goPrev}
      >
        Previous
      </Button>
      <Button
        type="primary"
        icon={<ArrowRightOutlined />}
        disabled={currentStep === 3 || disableNext}
        onClick={goNext}
      >
        {currentStep === 2 ? 'Go to Integration Setup' : 'Next'}
      </Button>
    </div>
  );

  return (
    <div style={{ maxWidth: 1120, margin: '0 auto', padding: 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <Title level={2} style={{ marginBottom: 4 }}>
              <RobotOutlined /> AI Integration Hub
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              Discover service dependencies and generate integration snippets for AI agents and CI/CD pipelines.
            </Paragraph>
          </div>
          <Link to="/discovery/map">
            <Button type="link">Back to Map</Button>
          </Link>
        </div>

        <Card>
          <Steps
            current={currentStep}
            onChange={(n) => {
              if (n <= currentStep || (n === 1 && canGoNextFromStep0)) setCurrentStep(n);
            }}
            items={[
              { title: 'Service Selection', icon: <SearchOutlined /> },
              { title: 'Dependencies', icon: <ApartmentOutlined /> },
              { title: 'Impact Analysis', icon: <ThunderboltOutlined /> },
              { title: 'Integration', icon: <CodeOutlined /> },
            ]}
          />
        </Card>

        {currentStep > 0 && upstream && (
          <UpstreamBanner upstream={upstream} downstream={downstreamRows} callers={callerRows} />
        )}

        {/* Step 0: Service Selection */}
        {currentStep === 0 && (
          <Card title="Find your service">
            <Paragraph type="secondary" style={{ marginBottom: 16 }}>
              Search by any combination of filters. At least one search parameter is required.
            </Paragraph>
            <Form
              form={form}
              layout="vertical"
              onFinish={onSearch}
              initialValues={{ analysis_id: undefined, cluster_id: undefined }}
            >
              <Row gutter={16}>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="namespace" label="Namespace">
                    <Input placeholder="e.g. production" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="owner_name" label="Owner / Deployment name">
                    <Input placeholder="e.g. payment-service" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="pod_name" label="Pod name">
                    <Input placeholder="e.g. payment-service-7b9d4" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="annotation_key" label="Annotation key">
                    <Input placeholder="e.g. app.company.com/team" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="annotation_value" label="Annotation value">
                    <Input placeholder="e.g. platform-team" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="ip" label="Pod IP">
                    <Input placeholder="e.g. 10.244.1.15" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="label_key" label="Label key">
                    <Input placeholder="e.g. app.kubernetes.io/name" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="label_value" label="Label value">
                    <Input placeholder="e.g. nginx" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="analysis_id" label="Analysis ID">
                    <Input type="number" placeholder="e.g. 42" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="cluster_id" label="Cluster ID">
                    <Input type="number" placeholder="e.g. 1" />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" icon={<SearchOutlined />} onClick={onSearch} loading={streamLoading} size="large">
                Search Service
              </Button>
            </Form>

            {streamErrMsg && (
              <Alert type="error" showIcon style={{ marginTop: 16 }} message={streamErrMsg} />
            )}

            {streamLoading && (
              <div style={{ marginTop: 24, textAlign: 'center' }}><Spin tip="Searching..." /></div>
            )}

            {streamData && !streamLoading && (
              <>
                {!streamData.success || !upstream ? (
                  <Alert type="warning" showIcon style={{ marginTop: 16 }} message={streamData.error || 'No matching workload found. Try different search criteria.'} />
                ) : (
                  <Alert
                    type="success"
                    showIcon
                    icon={<CheckCircleOutlined />}
                    style={{ marginTop: 16 }}
                    message={
                      <span>
                        Found <Text strong>{upstream.owner_name || upstream.pod_name}</Text> in{' '}
                        <Text strong>{upstream.namespace}</Text>
                        {' \u2014 '}
                        {downstreamRows.length} downstream, {callerRows.length} callers
                      </span>
                    }
                    description={
                      <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} style={{ marginTop: 8 }}>
                        {upstream.owner_kind && <Descriptions.Item label="Kind">{upstream.owner_kind}</Descriptions.Item>}
                        {upstream.image && <Descriptions.Item label="Image"><Text code style={{ fontSize: 11 }}>{upstream.image}</Text></Descriptions.Item>}
                        {upstream.ip && <Descriptions.Item label="IP">{upstream.ip}</Descriptions.Item>}
                        {upstream.node && <Descriptions.Item label="Node">{upstream.node}</Descriptions.Item>}
                        {upstream.service_account && <Descriptions.Item label="Service Account">{upstream.service_account}</Descriptions.Item>}
                      </Descriptions>
                    }
                  />
                )}
              </>
            )}

            <StepNav disableNext={!canGoNextFromStep0} />
          </Card>
        )}

        {/* Step 1: Dependency Discovery */}
        {currentStep === 1 && (
          <Card title="Dependency Discovery">
            <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
              <Col flex="auto">
                <Text strong>Traversal depth: {depth}</Text>
                <Slider min={1} max={5} value={depth} onChange={onDepthChange} marks={{ 1: '1', 2: '2', 3: '3', 4: '4', 5: '5' }} style={{ maxWidth: 300 }} />
              </Col>
            </Row>

            {streamLoading && <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>}

            <Tabs
              defaultActiveKey="downstream"
              items={[
                {
                  key: 'downstream',
                  label: <span><ArrowDownOutlined /> Downstream ({downstreamRows.length})</span>,
                  children: (
                    <Table
                      rowKey={(r, i) => `${r.namespace}-${r.pod_name}-${i}`}
                      loading={streamLoading}
                      columns={downstreamColumns}
                      dataSource={downstreamRows}
                      pagination={downstreamRows.length > 10 ? { pageSize: 10 } : false}
                      locale={{ emptyText: <Empty description="No downstream dependencies found" /> }}
                      scroll={{ x: 960 }}
                      size="small"
                    />
                  ),
                },
                {
                  key: 'callers',
                  label: <span><ArrowUpOutlined /> Callers ({callerRows.length})</span>,
                  children: (
                    <Table
                      rowKey={(r, i) => `caller-${r.namespace}-${r.pod_name}-${i}`}
                      loading={streamLoading}
                      columns={downstreamColumns}
                      dataSource={callerRows}
                      pagination={callerRows.length > 10 ? { pageSize: 10 } : false}
                      locale={{ emptyText: <Empty description="No callers found" /> }}
                      scroll={{ x: 960 }}
                      size="small"
                    />
                  ),
                },
              ]}
            />

            <StepNav />
          </Card>
        )}

        {/* Step 2: Impact Analysis */}
        {currentStep === 2 && (
          <Card title="Impact Analysis">
            <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
              <Col>
                <Text strong>Change type:</Text>
              </Col>
              <Col>
                <Select
                  style={{ minWidth: 200 }}
                  value={changeType}
                  onChange={setChangeType}
                  options={CHANGE_TYPES}
                />
              </Col>
            </Row>

            {impactLoading && <div style={{ textAlign: 'center', padding: 24 }}><Spin tip="Calculating impact..." /></div>}
            {impactIsError && (
              <Alert
                type="error"
                showIcon
                message={
                  impactError && 'data' in impactError
                    ? String((impactError as { data?: { detail?: string } }).data?.detail ?? 'Impact request failed')
                    : 'Impact analysis failed'
                }
              />
            )}

            {!impactLoading && assessment && (
              <Card size="small" style={{ marginBottom: 24 }}>
                <Row gutter={[24, 24]}>
                  <Col xs={24} md={6} style={{ textAlign: 'center' }}>
                    <Progress
                      type="dashboard"
                      percent={riskPct}
                      strokeColor={riskProgressColor(riskPct)}
                      format={(p) => <span style={{ fontSize: 22, fontWeight: 700 }}>{p}</span>}
                      size={120}
                    />
                    <div style={{ marginTop: 4 }}>
                      <Tag color="blue">{assessment.risk_level}</Tag>
                      <RecommendationBadge rec={assessment.recommendation} />
                    </div>
                  </Col>
                  <Col xs={24} md={18}>
                    <Row gutter={[16, 16]}>
                      <Col xs={12} sm={6}>
                        <Statistic title="Blast Radius" value={assessment.blast_radius} suffix="deps" />
                      </Col>
                      <Col xs={12} sm={6}>
                        <Statistic title="Downstream" value={downstreamRows.length} />
                      </Col>
                      <Col xs={12} sm={6}>
                        <Statistic title="Callers" value={callerRows.length} />
                      </Col>
                      <Col xs={12} sm={6}>
                        <Statistic title="Critical" value={assessment.critical_dependencies?.length ?? 0} valueStyle={assessment.critical_dependencies?.length ? { color: '#cf1322' } : undefined} />
                      </Col>
                    </Row>
                    {(assessment.critical_dependencies?.length ?? 0) > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <Text strong>Critical dependencies: </Text>
                        {assessment.critical_dependencies!.map((d) => <Tag color="red" key={d}>{d}</Tag>)}
                      </div>
                    )}
                    {(assessment.suggested_actions?.length ?? 0) > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <Text strong>Suggested actions:</Text>
                        <ul style={{ marginBottom: 0, paddingLeft: 20, marginTop: 4 }}>
                          {assessment.suggested_actions.map((a: SuggestedAction, i: number) => (
                            <li key={i}>
                              <Tag color={a.priority === 'critical' ? 'red' : a.priority === 'high' ? 'orange' : a.priority === 'medium' ? 'gold' : 'blue'} style={{ marginRight: 6 }}>
                                {a.priority}
                              </Tag>
                              <Text>{a.action}</Text>
                              {a.reason && <Text type="secondary" style={{ marginLeft: 4 }}>({a.reason})</Text>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </Col>
                </Row>
              </Card>
            )}

            <Divider orientation="left"><SwapOutlined /> Dependency Diff</Divider>
            <Paragraph type="secondary">
              Compare two analysis runs to detect added, removed, or changed dependencies over time.
            </Paragraph>
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col xs={24} sm={12}>
                <Input
                  addonBefore="Before"
                  placeholder="Analysis ID"
                  value={diffAnalysisBefore}
                  onChange={(e) => setDiffAnalysisBefore(e.target.value)}
                />
              </Col>
              <Col xs={24} sm={12}>
                <Input
                  addonBefore="After"
                  placeholder="Analysis ID"
                  value={diffAnalysisAfter}
                  onChange={(e) => setDiffAnalysisAfter(e.target.value)}
                />
              </Col>
            </Row>
            {diffLoading && <div style={{ textAlign: 'center', padding: 16 }}><Spin /></div>}
            {diffIsError && diffParams && (
              <Alert
                type="warning"
                showIcon
                message={
                  diffError && 'data' in diffError
                    ? String((diffError as { data?: { detail?: string } }).data?.detail ?? 'Diff request failed')
                    : 'Could not load dependency diff'
                }
              />
            )}
            {diffData?.success && (
              <Card size="small" style={{ marginTop: 8 }}>
                <Row gutter={16}>
                  <Col xs={6}><Statistic title={<><PlusCircleOutlined /> Added</>} value={diffData.added_dependencies?.length ?? 0} valueStyle={{ color: '#52c41a' }} /></Col>
                  <Col xs={6}><Statistic title={<><MinusCircleOutlined /> Removed</>} value={diffData.removed_dependencies?.length ?? 0} valueStyle={{ color: '#cf1322' }} /></Col>
                  <Col xs={6}><Statistic title={<><SwapOutlined /> Changed</>} value={diffData.changed_dependencies?.length ?? 0} valueStyle={{ color: '#faad14' }} /></Col>
                  <Col xs={6}><Statistic title="Unchanged" value={diffData.unchanged_count ?? 0} /></Col>
                </Row>
              </Card>
            )}
            {!diffParams && !diffLoading && (
              <Text type="secondary">Enter both analysis IDs above to generate a diff report.</Text>
            )}

            <StepNav />
          </Card>
        )}

        {/* Step 3: Integration Setup */}
        {currentStep === 3 && (
          <Card title="Integration Setup">
            <Alert
              type="info"
              showIcon
              icon={<ApiOutlined />}
              style={{ marginBottom: 20 }}
              message="API Authentication"
              description={
                <span>
                  Generate an API key from <Link to="/settings">Settings</Link> and use it as{' '}
                  <Text code>FLOWFISH_API_TOKEN</Text> in your integrations.
                </span>
              }
            />

            <Tabs
              items={[
                {
                  key: 'curl',
                  label: 'cURL',
                  children: (
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                      <div>
                        <Text strong>Dependency Stream</Text>
                        <CodeBlockWithCopy code={snippets.curl} label="cURL (stream)" />
                      </div>
                      <div>
                        <Text strong>Impact Assessment</Text>
                        <CodeBlockWithCopy code={snippets.curlImpact} label="cURL (impact)" />
                      </div>
                    </Space>
                  ),
                },
                {
                  key: 'py',
                  label: 'Python',
                  children: <CodeBlockWithCopy code={snippets.python} label="Python" />,
                },
                {
                  key: 'js',
                  label: 'JavaScript',
                  children: <CodeBlockWithCopy code={snippets.javascript} label="JavaScript" />,
                },
                {
                  key: 'ado',
                  label: 'Azure DevOps',
                  children: <CodeBlockWithCopy code={snippets.azure} label="Azure DevOps YAML" />,
                },
                {
                  key: 'gha',
                  label: 'GitHub Actions',
                  children: <CodeBlockWithCopy code={snippets.gha} label="GitHub Actions" />,
                },
              ]}
            />

            <Divider orientation="left"><DownloadOutlined /> Export Dependency Graph</Divider>
            <Space wrap>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                disabled={!streamData}
                onClick={() => {
                  const blob = new Blob([JSON.stringify(streamData ?? {}, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'flowfish-dependency-stream.json';
                  a.click();
                  URL.revokeObjectURL(url);
                  message.success('Download started');
                }}
              >
                Download JSON
              </Button>
              <Button
                icon={<CopyOutlined />}
                disabled={!upstream}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(upstream ? buildExportMermaid(upstream, downstreamRows) : '');
                    message.success('Mermaid copied');
                  } catch { message.error('Clipboard unavailable'); }
                }}
              >
                Copy Mermaid
              </Button>
              <Button
                icon={<CopyOutlined />}
                disabled={!upstream}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(upstream ? buildExportDot(upstream, downstreamRows) : '');
                    message.success('DOT copied');
                  } catch { message.error('Clipboard unavailable'); }
                }}
              >
                Copy DOT
              </Button>
            </Space>

            <StepNav />
          </Card>
        )}
      </Space>
    </div>
  );
};

export default AIIntegrationHub;
