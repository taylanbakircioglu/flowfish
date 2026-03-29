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
  buildBlastRadiusCurlSnippet,
  buildBlastRadiusPipelineSnippet,
} from '../utils/snippetBuilders';

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

const IntegrationHub: React.FC = () => {
  const { token } = theme.useToken();
  const [currentStep, setCurrentStep] = useState(0);
  const [integrationType, setIntegrationType] = useState<IntegrationType>(null);
  const [form] = Form.useForm();

  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState<number[]>([]);
  const [platform, setPlatform] = useState('azure_devops');
  const [idMethod, setIdMethod] = useState('annotation');
  const [depth, setDepth] = useState(1);

  // Blast Radius Gate flow state
  const [brTargetService, setBrTargetService] = useState('');
  const [brTargetNamespace, setBrTargetNamespace] = useState('');

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

  const canProceedConfigure = selectedAnalysisIds.length > 0;

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
    setCurrentStep(3);
  }, [selectedAnalysisIds, buildParamsFromForm]);

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
      if (n === 2 && summaryData?.success) setCurrentStep(n);
      else if (n === 3 && (summaryData?.success || summaryParams)) setCurrentStep(n);
    }
    if (integrationType === 'blast_radius') {
      if (n === 2) setCurrentStep(n);
    }
  };

  // ─── Shared auth card ───
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
        <li>Go to <Link to="/settings"><Text strong>Settings</Text></Link> and open the <Text strong>API Keys</Text> tab</li>
        <li>Click <Text strong>Generate New API Key</Text> and give it a descriptive name (e.g. &quot;azure-devops-pipeline&quot;)</li>
        <li>Copy the generated key (starts with <Text code>fk_</Text>) and store it securely in your CI/CD platform&apos;s secrets/variables</li>
      </ol>
      <Alert
        type="warning"
        showIcon
        message="API keys provide full API access. Store them as encrypted secrets in your pipeline platform, never in source code."
        style={{ marginTop: 8 }}
      />
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
            items={activeSteps}
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
              disabled={!canProceedConfigure}
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

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={handleBackToTypeSelection}>
              Back
            </Button>
            <Space>
              {!summaryData?.success && (
                <Button onClick={onSkipToSetup} disabled={!canProceedConfigure}>
                  Skip to Integration Code <ArrowRightOutlined />
                </Button>
              )}
              <Button
                type="primary"
                icon={<ArrowRightOutlined />}
                disabled={!summaryData?.success}
                onClick={() => setCurrentStep(2)}
              >
                Preview Results
              </Button>
            </Space>
          </div>
        </Card>
      )}

      {/* ─── Dep Step 2: Preview & Validate ─── */}
      {integrationType === 'dependency' && currentStep === 2 && !summaryData?.success && (
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
      {integrationType === 'dependency' && currentStep === 2 && summaryData?.success && (
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
      {integrationType === 'dependency' && currentStep === 3 && !summaryData?.success && !summaryParams && (
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
      {integrationType === 'dependency' && currentStep === 3 && (summaryData?.success || summaryParams) && (
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
                    <CodeBlock code={buildPipelineSnippet(summaryParams, platform)} label="Pipeline YAML" />
                  </div>
                ),
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
                      description={<>Use this endpoint to assess the impact of deploying changes to a service. You can also <Button type="link" style={{ padding: 0 }} onClick={handleBackToTypeSelection}>set up Blast Radius as a dedicated integration type</Button> from Step 1.</>}
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
                          label: `Pipeline (${PIPELINE_PLATFORMS.find(p => p.value === platform)?.label || 'Pipeline'})`,
                          children: <CodeBlock code={buildBlastRadiusPipelineSnippet(platform, contextNamespace, contextOwnerName)} label="Blast Radius Pipeline" />,
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
            <Paragraph>
              The <Text code>/dependencies/summary</Text> response groups all dependencies by <Text strong>service category</Text> (database, cache, api, message_broker, etc.).
              Each dependency includes its Kubernetes <Text strong>annotations</Text> and <Text strong>labels</Text>.
            </Paragraph>
            <Paragraph>
              Your pipeline should:
            </Paragraph>
            <ol>
              <li>Extract <Text code>annotations[&quot;git-repo&quot;]</Text> from each downstream service to identify affected repositories</li>
              <li>Check <Text code>is_critical</Text> flag to prioritize critical dependency changes</li>
              <li>Use <Text code>service_category</Text> grouping to understand the type of each dependency (database, cache, API, etc.)</li>
              <li>Examine <Text code>callers</Text> to understand which services call the changed service</li>
            </ol>
          </Card>

          <div style={{ marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(summaryData?.success ? 2 : 1)}>
              {summaryData?.success ? 'Back to Preview' : 'Back to Configure'}
            </Button>
          </div>
        </div>
      )}

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
                    <CodeBlock code={buildBlastRadiusPipelineSnippet(platform, brTargetNamespace || undefined, brTargetService || undefined)} label="Blast Radius Pipeline" />
                  </div>
                ),
              },
              {
                key: 'br-curl',
                label: <span><CodeOutlined /> curl</span>,
                children: <CodeBlock code={buildBlastRadiusCurlSnippet(brTargetNamespace || undefined, brTargetService || undefined)} label="Blast Radius curl" />,
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
