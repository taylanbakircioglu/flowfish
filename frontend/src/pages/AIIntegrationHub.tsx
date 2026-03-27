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
  theme,
} from 'antd';
import {
  RobotOutlined,
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
  buildBlastRadiusCurlSnippet,
  buildBlastRadiusPipelineSnippet,
} from '../utils/snippetBuilders';

const { Text, Title, Paragraph } = Typography;
const { Option } = Select;

const AIIntegrationHub: React.FC = () => {
  const { token } = theme.useToken();
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();

  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState<number[]>([]);
  const [platform, setPlatform] = useState('azure_devops');
  const [idMethod, setIdMethod] = useState('annotation');
  const [depth, setDepth] = useState(1);

  const [triggerSummary, { data: rawSummaryData, isFetching: summaryLoading, error: rawSummaryError }] =
    useLazyGetDependencySummaryQuery();
  const [summaryParams, setSummaryParams] = useState<DependencySummaryParams | null>(null);
  const [summaryCleared, setSummaryCleared] = useState(false);
  const summaryData = summaryCleared ? undefined : rawSummaryData;
  const summaryError = summaryCleared ? undefined : rawSummaryError;
  const resetSummary = useCallback(() => {
    setSummaryCleared(true);
    setSummaryParams(null);
  }, []);

  const [searchParams] = useSearchParams();
  useEffect(() => {
    const urlOwner = searchParams.get('owner_name');
    const urlNs = searchParams.get('namespace');
    const urlAnnotationKey = searchParams.get('annotation_key');
    const urlAnnotationValue = searchParams.get('annotation_value');
    if (urlOwner || urlNs || urlAnnotationKey) {
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
  const analyses: any[] = useMemo(() =>
    (Array.isArray(analysesData) ? analysesData : [])
      .filter((a: any) => a.status === 'completed' || a.status === 'running'),
    [analysesData],
  );

  const summaryErrMsg = useMemo(() => {
    const raw = summaryError
      ? (summaryError as any)?.data?.detail || 'Query failed'
      : summaryData && !summaryData.success
        ? summaryData.error || 'No results'
        : null;
    if (!raw) return null;
    if (raw.toLowerCase().includes('no pod') || raw.toLowerCase().includes('no results') || raw.toLowerCase().includes('no matching')) {
      return `${raw}. Tip: Check the Map view to verify available annotations/labels for your pods. Infrastructure annotations (openshift.io/*, kubernetes.io/*) are filtered — use custom annotations like git-repo, team, or version.`;
    }
    return raw;
  }, [summaryError, summaryData]);

  const canProceedStep0 = selectedAnalysisIds.length > 0;

  const buildParamsFromForm = useCallback((): DependencySummaryParams | null => {
    const values = form.getFieldsValue();
    if (!selectedAnalysisIds.length) return null;
    const hasSearch = values.annotation_key || values.label_key || values.namespace || values.owner_name || values.pod_name || values.ip;
    if (!hasSearch) return null;
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
    return params;
  }, [form, selectedAnalysisIds, depth]);

  const onTestQuery = useCallback(() => {
    if (!selectedAnalysisIds.length) {
      message.warning('Select at least one analysis');
      return;
    }
    const params = buildParamsFromForm();
    if (!params) {
      message.warning('At least one search parameter is required (e.g. namespace, deployment, annotation)');
      return;
    }
    setSummaryParams(params);
    setSummaryCleared(false);
    triggerSummary(params, false);
  }, [selectedAnalysisIds, buildParamsFromForm, triggerSummary]);

  const onSkipToSetup = useCallback(() => {
    if (!selectedAnalysisIds.length) {
      message.warning('Select at least one analysis');
      return;
    }
    const params = buildParamsFromForm();
    if (!params) {
      message.warning('At least one search parameter is required (e.g. namespace, deployment, annotation)');
      return;
    }
    setSummaryParams(params);
    setCurrentStep(2);
  }, [selectedAnalysisIds, buildParamsFromForm]);

  const responseSize = useMemo(() => {
    if (!summaryData) return 0;
    return Math.round(JSON.stringify(summaryData).length / 1024 * 10) / 10;
  }, [summaryData]);

  const contextNamespace = summaryParams?.namespace;
  const contextOwnerName = summaryParams?.owner_name;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            <RobotOutlined /> AI Integration Hub
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Set up CI/CD pipeline and AI agent integrations with Flowfish dependency and impact data.
          </Paragraph>
        </div>
        <Link to="/discovery/map">
          <Button type="link">Back to Map</Button>
        </Link>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Steps
          current={currentStep}
          onChange={(n) => {
            if (n < currentStep) setCurrentStep(n);
            else if (n === 1 && summaryData?.success) setCurrentStep(n);
            else if (n === 2 && (summaryData?.success || summaryParams)) setCurrentStep(n);
          }}
          items={[
            { title: 'Configure', icon: <ExperimentOutlined /> },
            { title: 'Preview', icon: <EyeOutlined /> },
            { title: 'Integration Code', icon: <CodeOutlined /> },
          ]}
        />
      </Card>

      {/* ─── Step 0: Configure ─── */}
      {currentStep === 0 && (
        <Card title="Analysis Scope & Service Identification">
          <Form.Item label="Analysis (required, multi-select)" required>
            <Select
              mode="multiple"
              placeholder="Select one or more analyses"
              value={selectedAnalysisIds}
              onChange={(ids) => { setSelectedAnalysisIds(ids); resetSummary(); }}
              style={{ width: '100%' }}
              optionFilterProp="label"
              showSearch
            >
              {(() => {
                const grouped: Record<string, any[]> = {};
                analyses.forEach((a: any) => {
                  const cName = clusterNameMap[a.cluster_id] || `Cluster ${a.cluster_id}`;
                  (grouped[cName] ||= []).push(a);
                });
                return Object.entries(grouped).map(([clusterName, items]) => (
                  <Select.OptGroup key={clusterName} label={clusterName}>
                    {items.map((a: any) => (
                      <Option key={a.id} value={a.id} label={`${clusterName} ${a.name}`}>
                        {a.name} <Tag color={a.status === 'completed' ? 'green' : 'blue'}>{a.status}</Tag>
                      </Option>
                    ))}
                  </Select.OptGroup>
                ));
              })()}
            </Select>
          </Form.Item>

          {selectedAnalysisIds.length > 0 && (
            <Alert
              type="info"
              showIcon
              icon={<CheckCircleOutlined />}
              message={`${selectedAnalysisIds.length} analysis selected`}
              style={{ marginBottom: 16 }}
            />
          )}

          <Divider />

          <Form.Item label="Service Identification Method">
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
                      tooltip="Use custom annotations set during deployment (e.g. git-repo, team, version). Infrastructure annotations like openshift.io/* and kubernetes.io/* are not indexed."
                    >
                      <Input placeholder="e.g. git-repo, build-id, team" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item name="annotation_value" label="Annotation Value">
                      <Input placeholder="e.g. https://tfs.company.com/.../my-service" />
                    </Form.Item>
                  </Col>
                </>
              )}
              {(idMethod === 'label' || idMethod === 'advanced') && (
                <>
                  <Col xs={24} sm={12}>
                    <Form.Item name="label_key" label="Label Key">
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
                <>
                  <Col xs={24} sm={12}>
                    <Form.Item name="namespace" label="Namespace">
                      <Input placeholder="e.g. production" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item name="owner_name" label="Deployment Name">
                      <Input placeholder="e.g. payment-service" />
                    </Form.Item>
                  </Col>
                </>
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
            </Row>
          </Form>

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
              loading={summaryLoading}
              disabled={!canProceedStep0}
            >
              Test Query
            </Button>
          </div>

          {summaryErrMsg && !summaryLoading && (
            <Alert type="error" showIcon style={{ marginTop: 16 }} message={summaryErrMsg} />
          )}

          {summaryLoading && (
            <div style={{ marginTop: 24, textAlign: 'center' }}><Spin tip="Querying Flowfish..." /></div>
          )}

          {summaryData?.success && !summaryLoading && (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              style={{ marginTop: 16 }}
              message={
                <span>
                  Found <Text strong>{summaryData.service.name}</Text> in <Text strong>{summaryData.service.namespace}</Text>
                  {' \u2014 '}
                  {summaryData.downstream.total} downstream, {summaryData.callers.total} callers
                  {summaryData.downstream.critical_count ? <Tag color="red" style={{ marginLeft: 8 }}>{summaryData.downstream.critical_count} critical</Tag> : null}
                </span>
              }
            />
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginTop: 24, gap: 8 }}>
            {!summaryData?.success && (
              <Button onClick={onSkipToSetup} disabled={!canProceedStep0}>
                Skip to Integration Code <ArrowRightOutlined />
              </Button>
            )}
            <Button
              type="primary"
              icon={<ArrowRightOutlined />}
              disabled={!summaryData?.success}
              onClick={() => setCurrentStep(1)}
            >
              Preview Results
            </Button>
          </div>
        </Card>
      )}

      {/* ─── Step 1: Preview & Validate ─── */}
      {currentStep === 1 && !summaryData?.success && (
        <Card>
          <Alert
            type="warning"
            showIcon
            message="Preview data is no longer available. Please run Test Query again."
            style={{ marginBottom: 16 }}
          />
          <Button type="primary" onClick={() => setCurrentStep(0)}>Back to Configure</Button>
        </Card>
      )}
      {currentStep === 1 && summaryData?.success && (
        <div>
          <Card size="small" style={{ borderLeft: `3px solid ${token.colorPrimary}`, marginBottom: 16 }}>
            <Row gutter={16} align="middle">
              <Col flex="auto">
                <Space split={<Divider type="vertical" />}>
                  <Text strong style={{ fontSize: 16 }}>{summaryData.service.name}</Text>
                  <Text type="secondary">{summaryData.service.namespace}</Text>
                  {summaryData.service.kind && <Tag>{summaryData.service.kind}</Tag>}
                </Space>
              </Col>
              <Col>
                <Space size="large">
                  <Statistic title={<><ArrowDownOutlined /> Downstream</>} value={summaryData.downstream.total} valueStyle={{ fontSize: 18 }} />
                  <Statistic title={<><ArrowUpOutlined /> Callers</>} value={summaryData.callers.total} valueStyle={{ fontSize: 18 }} />
                </Space>
              </Col>
            </Row>
          </Card>

          {summaryData.multi_service && summaryData.matched_services && summaryData.matched_services.length > 0 && (
            <Card size="small" title={`Matched Upstream Services (${summaryData.matched_services.length})`} style={{ marginBottom: 16 }}>
              <Table<MatchedService>
                dataSource={summaryData.matched_services}
                rowKey={(r) => `${r.namespace}/${r.name}`}
                size="small"
                pagination={summaryData.matched_services.length > 10 ? { pageSize: 10 } : false}
                columns={[
                  { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <Text strong>{v}</Text> },
                  { title: 'Namespace', dataIndex: 'namespace', key: 'ns' },
                  { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
                  { title: 'Downstream', dataIndex: 'downstream_count', key: 'ds', render: (v: number) => <Badge count={v} showZero style={{ backgroundColor: v ? token.colorPrimary : token.colorBorderSecondary }} /> },
                  { title: 'Callers', dataIndex: 'callers_count', key: 'cl', render: (v: number) => <Badge count={v} showZero style={{ backgroundColor: v ? token.colorSuccess : token.colorBorderSecondary }} /> },
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

          {!summaryData.multi_service && Object.keys(summaryData.service.annotations || {}).length > 0 && (
            <Card size="small" title="Upstream Service Metadata" style={{ marginBottom: 16 }}>
              <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
                {Object.entries(summaryData.service.annotations).map(([k, v]) => (
                  <Descriptions.Item key={k} label={<Text strong style={{ fontSize: 11, color: token.colorWarning }}>{k}</Text>}>
                    <Text style={{ fontSize: 11, wordBreak: 'break-all' }}>{v}</Text>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </Card>
          )}

          <Tabs
            items={[
              {
                key: 'downstream',
                label: <span><ArrowDownOutlined /> Downstream ({summaryData.downstream.total})</span>,
                children: <DependencyCategoryGroup group={summaryData.downstream} title="Downstream" />,
              },
              {
                key: 'callers',
                label: <span><ArrowUpOutlined /> Callers ({summaryData.callers.total})</span>,
                children: <DependencyCategoryGroup group={summaryData.callers} title="Callers" />,
              },
              {
                key: 'raw',
                label: <span><CodeOutlined /> Raw JSON</span>,
                children: (
                  <div>
                    <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>Response size: ~{responseSize} KB</Text>
                    <CodeBlock code={JSON.stringify(summaryData, null, 2)} label="JSON" />
                  </div>
                ),
              },
            ]}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => setCurrentStep(0)}
            >
              Back
            </Button>
            <Button
              type="primary"
              icon={<ArrowRightOutlined />}
              onClick={() => setCurrentStep(2)}
            >
              Integration Code
            </Button>
          </div>
        </div>
      )}

      {/* ─── Step 2: Integration Code ─── */}
      {currentStep === 2 && !summaryData?.success && !summaryParams && (
        <Card>
          <Alert
            type="warning"
            showIcon
            message="Configuration required. Please set up your query in the Configure step."
            style={{ marginBottom: 16 }}
          />
          <Button type="primary" onClick={() => setCurrentStep(0)}>Back to Configure</Button>
        </Card>
      )}
      {currentStep === 2 && (summaryData?.success || summaryParams) && (
        <div>
          {!summaryData?.success && (
            <Alert
              type="warning"
              showIcon
              message="Test Query was skipped — snippets are generated from your configured parameters. Run Test Query in the Configure step to preview and validate results."
              style={{ marginBottom: 16 }}
            />
          )}
          <Alert
            type="info"
            showIcon
            message="All snippets below use your selected parameters. Copy and adapt to your environment."
            style={{ marginBottom: 16 }}
          />

          <Card
            size="small"
            style={{ marginBottom: 16 }}
          >
            <Space align="center">
              <Text strong>Pipeline Platform:</Text>
              <Select value={platform} onChange={setPlatform} style={{ width: 200 }}>
                {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
              </Select>
              <Text type="secondary">(affects pipeline snippet format)</Text>
            </Space>
          </Card>

          <Tabs
            items={[
              {
                key: 'pipeline',
                label: <span><RocketOutlined /> {PIPELINE_PLATFORMS.find(p => p.value === platform)?.label || 'Pipeline'}</span>,
                children: <CodeBlock code={buildPipelineSnippet(summaryParams, platform)} label="Pipeline YAML" />,
              },
              {
                key: 'curl',
                label: <span><CodeOutlined /> curl</span>,
                children: <CodeBlock code={buildCurlSnippet(summaryParams)} label="curl" />,
              },
              {
                key: 'python',
                label: <span><CodeOutlined /> Python</span>,
                children: <CodeBlock code={buildPythonSnippet(summaryParams)} label="Python" />,
              },
              {
                key: 'js',
                label: <span><CodeOutlined /> JavaScript</span>,
                children: <CodeBlock code={buildJsSnippet(summaryParams)} label="JavaScript" />,
              },
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
                      description="Use this endpoint to assess the impact of deploying changes to a service. Returns a risk score (0-100), affected services count, and actionable recommendations."
                      style={{ marginBottom: 16 }}
                    />
                    <Tabs
                      size="small"
                      items={[
                        {
                          key: 'br-curl',
                          label: 'curl',
                          children: <CodeBlock code={buildBlastRadiusCurlSnippet(contextNamespace, contextOwnerName)} label="Blast Radius curl" />,
                        },
                        {
                          key: 'br-pipeline',
                          label: PIPELINE_PLATFORMS.find(p => p.value === platform)?.label || 'Pipeline',
                          children: <CodeBlock code={buildBlastRadiusPipelineSnippet(platform, contextNamespace, contextOwnerName)} label="Blast Radius Pipeline" />,
                        },
                      ]}
                    />
                    <div style={{ marginTop: 12 }}>
                      <Link to="/impact/blast-radius">
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

          <Card
            title={<span><KeyOutlined /> Authentication</span>}
            size="small"
            style={{ marginTop: 16 }}
          >
            <Paragraph>
              All API calls require authentication via <Text strong>API Key</Text>. Include the header <Text code>X-API-Key: fk_your_key</Text> in every request.
            </Paragraph>
            <ol>
              <li>Go to <Link to="/settings"><Text strong>Settings</Text></Link> and open the <Text strong>API Keys</Text> tab</li>
              <li>Click <Text strong>Generate New API Key</Text> and give it a descriptive name (e.g. "azure-devops-pipeline")</li>
              <li>Copy the generated key (starts with <Text code>fk_</Text>) and store it securely in your CI/CD platform's secrets/variables</li>
            </ol>
            <Alert
              type="warning"
              showIcon
              message="API keys provide full API access. Store them as encrypted secrets in your pipeline platform, never in source code."
              style={{ marginTop: 8 }}
            />
          </Card>

          <Card title="Understanding the Response" size="small" style={{ marginTop: 16 }}>
            <Paragraph>
              The <Text code>/dependencies/summary</Text> response groups all dependencies by <Text strong>service category</Text> (database, cache, api, message_broker, etc.).
              Each dependency includes its Kubernetes <Text strong>annotations</Text> and <Text strong>labels</Text>.
            </Paragraph>
            <Paragraph>
              Your AI agent or pipeline should:
            </Paragraph>
            <ol>
              <li>Extract <Text code>annotations["git-repo"]</Text> from each downstream service to identify affected repositories</li>
              <li>Check <Text code>is_critical</Text> flag to prioritize critical dependency changes</li>
              <li>Use <Text code>service_category</Text> grouping to understand the type of each dependency (database, cache, API, etc.)</li>
              <li>Examine <Text code>callers</Text> to understand which services call the changed service</li>
            </ol>
          </Card>

          <div style={{ marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(summaryData?.success ? 1 : 0)}>
              {summaryData?.success ? 'Back to Preview' : 'Back to Configure'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIIntegrationHub;
