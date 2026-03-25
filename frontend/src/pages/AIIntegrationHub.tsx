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
  Empty,
  Tooltip,
  message,
  Spin,
  Row,
  Col,
  Descriptions,
  Statistic,
  Radio,
} from 'antd';
import {
  RobotOutlined,
  ApartmentOutlined,
  CodeOutlined,
  CopyOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  RocketOutlined,
  EyeOutlined,
  AlertOutlined,
  MessageOutlined,
  AuditOutlined,
  ExperimentOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import {
  useLazyGetDependencySummaryQuery,
  DependencySummaryParams,
  DependencySummaryService,
  DependencySummaryGroup,
  MatchedService,
} from '../store/api/communicationApi';

const { Text, Title, Paragraph } = Typography;
const { Option } = Select;

const API_BASE = typeof window !== 'undefined' ? `${window.location.origin}/api/v1` : '/api/v1';

type IntegrationType = 'cicd' | 'agent' | 'explorer' | null;

const PIPELINE_PLATFORMS = [
  { value: 'azure_devops', label: 'Azure DevOps' },
  { value: 'github_actions', label: 'GitHub Actions' },
  { value: 'gitlab_ci', label: 'GitLab CI' },
  { value: 'jenkins', label: 'Jenkins' },
  { value: 'tekton', label: 'Tekton' },
  { value: 'argocd', label: 'ArgoCD' },
  { value: 'other', label: 'Other' },
];

const AGENT_TYPES = [
  { value: 'code_review', label: 'Code Review' },
  { value: 'security_scan', label: 'Security Scan' },
  { value: 'architecture', label: 'Architecture Compliance' },
  { value: 'migration', label: 'Migration Impact' },
  { value: 'custom', label: 'Custom' },
];

const ID_METHODS = [
  { value: 'annotation', label: 'Annotation (e.g. git-repo URL)' },
  { value: 'label', label: 'Label (e.g. app name)' },
  { value: 'namespace_deployment', label: 'Namespace + Deployment' },
  { value: 'pod_name', label: 'Pod Name' },
  { value: 'advanced', label: 'Advanced (any combination)' },
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

function CategoryGroup({ group, title }: { group: DependencySummaryGroup; title: string }) {
  if (!group || group.total === 0) {
    return <Empty description={`No ${title.toLowerCase()}`} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 12 }}>
        <Col><Statistic title="Total" value={group.total} valueStyle={{ fontSize: 20 }} /></Col>
        {(group.critical_count ?? 0) > 0 && (
          <Col><Statistic title="Critical" value={group.critical_count} valueStyle={{ fontSize: 20, color: '#cf1322' }} /></Col>
        )}
        <Col><Statistic title="Categories" value={Object.keys(group.by_category || {}).length} valueStyle={{ fontSize: 20 }} /></Col>
      </Row>
      {Object.entries(group.by_category || {}).map(([cat, services]) => (
        <Card
          key={cat}
          size="small"
          title={<><Tag color={cat === 'database' ? 'blue' : cat === 'cache' ? 'green' : cat === 'message_broker' ? 'purple' : 'default'}>{cat}</Tag> <Text type="secondary">({services.length})</Text></>}
          style={{ marginBottom: 8 }}
        >
          <Table
            dataSource={services}
            rowKey={(r) => `${r.namespace}/${r.name}`}
            size="small"
            pagination={false}
            columns={[
              { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string, r: DependencySummaryService) => <><Text strong>{v}</Text>{r.is_critical && <Tag color="red" style={{ marginLeft: 4 }}>critical</Tag>}</> },
              { title: 'Namespace', dataIndex: 'namespace', key: 'ns' },
              { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: 'Port', dataIndex: 'port', key: 'port', render: (v: number) => v ?? '-' },
              {
                title: 'Annotations',
                key: 'ann',
                render: (_: unknown, r: DependencySummaryService) => {
                  const entries = Object.entries(r.annotations || {});
                  if (!entries.length) return <Text type="secondary">-</Text>;
                  const gitRepo = r.annotations['git-repo'] || r.annotations['gitRepo'] || r.annotations['source-repo'];
                  if (gitRepo) return <Tooltip title={gitRepo}><Tag color="geekblue">git-repo</Tag></Tooltip>;
                  return <Tooltip title={entries.map(([k, v]) => `${k}=${v}`).join(', ')}><Tag>{entries.length} annotations</Tag></Tooltip>;
                },
              },
            ]}
          />
        </Card>
      ))}
    </div>
  );
}

const AIIntegrationHub: React.FC = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [integrationType, setIntegrationType] = useState<IntegrationType>(null);
  const [form] = Form.useForm();

  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState<number[]>([]);
  const [platform, setPlatform] = useState('azure_devops');
  const [agentType, setAgentType] = useState('code_review');
  const [idMethod, setIdMethod] = useState('annotation');
  const [depth, setDepth] = useState(1);

  // Lazy query: triggered manually, always fresh. Use isFetching (not isLoading)
  // so the spinner shows even during forced refetch of cached params.
  const [triggerSummary, { data: rawSummaryData, isFetching: summaryLoading, error: rawSummaryError }] =
    useLazyGetDependencySummaryQuery();
  const [summaryParams, setSummaryParams] = useState<DependencySummaryParams | null>(null);
  const [summaryCleared, setSummaryCleared] = useState(false);
  const summaryData = summaryCleared ? undefined : rawSummaryData;
  const summaryError = summaryCleared ? undefined : rawSummaryError;
  const resetSummary = useCallback(() => setSummaryCleared(true), []);

  // Pre-fill from URL params (e.g. when navigating from Map page)
  const [searchParams] = useSearchParams();
  useEffect(() => {
    const urlOwner = searchParams.get('owner_name');
    const urlNs = searchParams.get('namespace');
    const urlAnnotationKey = searchParams.get('annotation_key');
    const urlAnnotationValue = searchParams.get('annotation_value');
    if (urlOwner || urlNs || urlAnnotationKey) {
      setIntegrationType('explorer');
      setCurrentStep(1);
      if (urlAnnotationKey) setIdMethod('annotation');
      else if (urlOwner && urlNs) setIdMethod('namespace_deployment');
      else if (urlOwner) setIdMethod('pod_name');
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

  // Load ALL analyses (no cluster filter) and cluster names for display
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

  const canProceedStep1 = selectedAnalysisIds.length > 0;

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

  const buildQueryString = useCallback(() => {
    if (!summaryParams) return '';
    const qs = new URLSearchParams();
    summaryParams.analysis_ids.forEach(id => qs.append('analysis_ids', String(id)));
    if (summaryParams.annotation_key) qs.set('annotation_key', summaryParams.annotation_key);
    if (summaryParams.annotation_value) qs.set('annotation_value', summaryParams.annotation_value);
    if (summaryParams.label_key) qs.set('label_key', summaryParams.label_key);
    if (summaryParams.label_value) qs.set('label_value', summaryParams.label_value);
    if (summaryParams.namespace) qs.set('namespace', summaryParams.namespace);
    if (summaryParams.owner_name) qs.set('owner_name', summaryParams.owner_name);
    if (summaryParams.pod_name) qs.set('pod_name', summaryParams.pod_name);
    if (summaryParams.ip) qs.set('ip', summaryParams.ip);
    if (summaryParams.depth && summaryParams.depth > 1) qs.set('depth', String(summaryParams.depth));
    return qs.toString();
  }, [summaryParams]);

  const buildCurlSnippet = useCallback(() => {
    const qsStr = buildQueryString();
    if (!qsStr) return '';
    return `# Get your API key from Settings > API Keys\ncurl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\\n  "${API_BASE}/communications/dependencies/summary?${qsStr}"`;
  }, [buildQueryString]);

  const buildPipelineSnippet = useCallback(() => {
    const qsStr = buildQueryString();
    if (!qsStr) return '';

    const baseUrl = typeof window !== 'undefined' ? window.location.origin : 'https://your-flowfish-instance';

    if (platform === 'azure_devops') {
      return `# Azure DevOps Pipeline - Flowfish Integration
# Get your API key from Flowfish Settings > API Keys
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

steps:
  - script: |
      DEPS=$(curl -sf -H "X-API-Key: $(FLOWFISH_API_KEY)" \\
        "$(FLOWFISH_URL)/api/v1/communications/dependencies/summary?$(FLOWFISH_QUERY)")
      echo "$DEPS" > flowfish-deps.json
      
      CRITICAL=$(echo "$DEPS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d.get('downstream',{}).get('critical_count',0)
print(c)
")
      echo "##vso[task.setvariable variable=CRITICAL_DEPS]$CRITICAL"
    displayName: 'Flowfish: Get Cross-Project Dependencies'
    env:
      FLOWFISH_API_KEY: $(FLOWFISH_API_KEY)
      FLOWFISH_URL: $(FLOWFISH_URL)
  
  - script: |
      python ai-agent/analyze.py \\
        --pr-diff $(System.PullRequest.PullRequestId) \\
        --deps flowfish-deps.json
    displayName: 'AI Impact Analysis (Cross-Project)'
    condition: succeededOrFailed()`;
    }

    if (platform === 'github_actions') {
      return `# GitHub Actions - Flowfish Integration
# Store your API key in repository secrets as FLOWFISH_API_KEY
# Set FLOWFISH_URL in repository variables (Settings > Secrets and variables > Actions)
env:
  FLOWFISH_QUERY: '${qsStr}'

jobs:
  flowfish:
    steps:
      - name: Get Flowfish Dependencies
        id: flowfish
        run: |
          curl -sf -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
            "\${{ vars.FLOWFISH_URL }}/api/v1/communications/dependencies/summary?\${FLOWFISH_QUERY}" \\
            > flowfish-deps.json
          
          CRITICAL=$(python3 -c "
import json
d=json.load(open('flowfish-deps.json'))
print(d.get('downstream',{}).get('critical_count',0))
")
          echo "critical_deps=$CRITICAL" >> $GITHUB_OUTPUT

      - name: AI Impact Analysis
        run: |
          python ai-agent/analyze.py \\
            --pr-diff \${{ github.event.pull_request.number }} \\
            --deps flowfish-deps.json`;
    }

    if (platform === 'gitlab_ci') {
      return `# GitLab CI - Flowfish Integration
# Store FLOWFISH_API_KEY and FLOWFISH_URL as CI/CD variables
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

flowfish_dependencies:
  stage: test
  script:
    - |
      curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
        "$FLOWFISH_URL/api/v1/communications/dependencies/summary?$FLOWFISH_QUERY" \\
        > flowfish-deps.json
    - python ai-agent/analyze.py --deps flowfish-deps.json
  artifacts:
    paths:
      - flowfish-deps.json`;
    }

    if (platform === 'jenkins') {
      return `// Jenkins Pipeline - Flowfish Integration
// Store FLOWFISH_API_KEY and FLOWFISH_URL in Jenkins credentials
def FLOWFISH_URL = '${baseUrl}'
def FLOWFISH_QUERY = '${qsStr}'

stage('Flowfish Dependencies') {
    steps {
        script {
            def deps = sh(returnStdout: true, script: """
                curl -sf -H "X-API-Key: \${FLOWFISH_API_KEY}" \\
                  "\${FLOWFISH_URL}/api/v1/communications/dependencies/summary?\${FLOWFISH_QUERY}"
            """).trim()
            writeFile file: 'flowfish-deps.json', text: deps
        }
    }
}`;
    }

    return `# Generic CI/CD - Flowfish Integration
# Get your API key from Flowfish Settings > API Keys
FLOWFISH_URL='${baseUrl}'
FLOWFISH_QUERY='${qsStr}'

curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "$FLOWFISH_URL/api/v1/communications/dependencies/summary?$FLOWFISH_QUERY" \\
  > flowfish-deps.json`;
  }, [buildQueryString, platform]);

  const buildPythonSnippet = useCallback(() => {
    if (!summaryParams) return '';
    const paramLines: string[] = [];
    summaryParams.analysis_ids.forEach(id => paramLines.push(`    ("analysis_ids", "${id}"),`));
    if (summaryParams.annotation_key) paramLines.push(`    ("annotation_key", "${summaryParams.annotation_key}"),`);
    if (summaryParams.annotation_value) paramLines.push(`    ("annotation_value", "${summaryParams.annotation_value}"),`);
    if (summaryParams.label_key) paramLines.push(`    ("label_key", "${summaryParams.label_key}"),`);
    if (summaryParams.label_value) paramLines.push(`    ("label_value", "${summaryParams.label_value}"),`);
    if (summaryParams.namespace) paramLines.push(`    ("namespace", "${summaryParams.namespace}"),`);
    if (summaryParams.owner_name) paramLines.push(`    ("owner_name", "${summaryParams.owner_name}"),`);
    if (summaryParams.pod_name) paramLines.push(`    ("pod_name", "${summaryParams.pod_name}"),`);
    if (summaryParams.depth && summaryParams.depth > 1) paramLines.push(`    ("depth", "${summaryParams.depth}"),`);

    return `import requests

FLOWFISH_URL = "${API_BASE}"
API_KEY = "fk_your_api_key_here"  # Get from Settings > API Keys

resp = requests.get(
    f"{FLOWFISH_URL}/communications/dependencies/summary",
    params=[
${paramLines.join('\n')}
    ],
    headers={"X-API-Key": API_KEY},
)
deps = resp.json()

# Extract affected git repos from downstream annotations
affected_repos = []
for category, services in deps.get("downstream", {}).get("by_category", {}).items():
    for svc in services:
        repo = svc.get("annotations", {}).get("git-repo")
        if repo:
            affected_repos.append({
                "repo": repo,
                "service": svc["name"],
                "namespace": svc["namespace"],
                "category": category,
                "critical": svc.get("is_critical", False),
            })

print(f"Found {len(affected_repos)} affected repositories")
for r in affected_repos:
    flag = " [CRITICAL]" if r["critical"] else ""
    print(f"  {r['service']} ({r['category']}){flag} -> {r['repo']}")`;
  }, [summaryParams]);

  const buildJsSnippet = useCallback(() => {
    const qsStr = buildQueryString();
    if (!qsStr) return '';
    return `// Get your API key from Flowfish Settings > API Keys
const resp = await fetch(
  \`\${FLOWFISH_URL}/api/v1/communications/dependencies/summary?${qsStr}\`,
  { headers: { "X-API-Key": FLOWFISH_API_KEY } }
);
const deps = await resp.json();

// Extract affected repos
const affectedRepos = Object.entries(deps.downstream?.by_category ?? {})
  .flatMap(([category, services]) =>
    services
      .filter(svc => svc.annotations?.["git-repo"])
      .map(svc => ({
        repo: svc.annotations["git-repo"],
        service: svc.name,
        category,
        critical: svc.is_critical,
      }))
  );

console.log(\`Found \${affectedRepos.length} affected repos\`);`;
  }, [buildQueryString]);

  const responseSize = useMemo(() => {
    if (!summaryData) return 0;
    return Math.round(JSON.stringify(summaryData).length / 1024 * 10) / 10;
  }, [summaryData]);

  // Step navigation helper
  function StepNav({ disableNext, nextLabel }: { disableNext?: boolean; nextLabel?: string }) {
    return (
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          disabled={currentStep === 0}
          onClick={() => setCurrentStep(s => s - 1)}
        >
          Back
        </Button>
        <Button
          type="primary"
          icon={<ArrowRightOutlined />}
          disabled={disableNext || currentStep === 3}
          onClick={() => setCurrentStep(s => s + 1)}
        >
          {nextLabel || 'Next'}
        </Button>
      </div>
    );
  }

  // ───────────────────────── RENDER ─────────────────────────

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            <RobotOutlined /> AI Integration Hub
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Set up CI/CD pipeline and AI agent integrations with Flowfish dependency data.
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
            else if (n === 1 && integrationType) setCurrentStep(n);
            else if (n === 2 && summaryData?.success) setCurrentStep(n);
            else if (n === 3 && (summaryData?.success || summaryParams)) setCurrentStep(n);
          }}
          items={[
            { title: 'Integration Type', icon: <ApiOutlined /> },
            { title: 'Configure', icon: <ExperimentOutlined /> },
            { title: 'Preview', icon: <EyeOutlined /> },
            { title: 'Integration Setup', icon: <CodeOutlined /> },
          ]}
        />
      </Card>

      {/* ─── Step 0: Integration Type ─── */}
      {currentStep === 0 && (
        <div>
          <Row gutter={[16, 16]}>
            {[
              { key: 'cicd' as const, icon: <RocketOutlined style={{ fontSize: 28 }} />, title: 'CI/CD Pipeline', desc: 'PR validation, deployment gates, build job dependency and impact analysis', tags: ['Azure DevOps', 'GitHub Actions', 'GitLab CI', 'Jenkins'] },
              { key: 'agent' as const, icon: <RobotOutlined style={{ fontSize: 28 }} />, title: 'AI Agent', desc: 'Code review agents, security scan agents, architecture compliance', tags: ['Code Review', 'Security', 'Compliance'] },
              { key: 'explorer' as const, icon: <ApartmentOutlined style={{ fontSize: 28 }} />, title: 'Analysis Explorer', desc: 'Browse analysis dependencies, export data, generate reports', tags: ['Browse', 'Export', 'Audit'] },
            ].map(item => (
              <Col xs={24} md={8} key={item.key}>
                <Card
                  hoverable
                  onClick={() => { setIntegrationType(item.key); form.resetFields(); resetSummary(); setCurrentStep(1); }}
                  style={{
                    borderColor: integrationType === item.key ? '#1677ff' : undefined,
                    borderWidth: integrationType === item.key ? 2 : 1,
                    height: '100%',
                  }}
                >
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    {item.icon}
                    <Text strong style={{ fontSize: 16 }}>{item.title}</Text>
                    <Text type="secondary" style={{ fontSize: 13 }}>{item.desc}</Text>
                    <div>{item.tags.map(t => <Tag key={t} style={{ marginBottom: 4 }}>{t}</Tag>)}</div>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>

          <Divider>Coming Soon</Divider>

          <Row gutter={[16, 16]}>
            {[
              { icon: <AlertOutlined />, title: 'Monitoring & Alerting', desc: 'Prometheus/Grafana dashboards, PagerDuty/OpsGenie' },
              { icon: <AuditOutlined />, title: 'Change Management', desc: 'ServiceNow/Jira change request enrichment' },
              { icon: <MessageOutlined />, title: 'ChatOps', desc: 'Slack/Teams bot dependency queries' },
            ].map(item => (
              <Col xs={24} md={8} key={item.title}>
                <Card style={{ opacity: 0.55, cursor: 'not-allowed' }}>
                  <Space direction="vertical" size={4}>
                    {item.icon}
                    <Text strong>{item.title}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.desc}</Text>
                    <Badge count="Coming Soon" style={{ backgroundColor: '#d9d9d9', color: '#666' }} />
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      )}

      {/* ─── Step 1: Configure ─── */}
      {currentStep === 1 && (
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

          {/* Integration-type-specific config */}
          {integrationType === 'cicd' && (
            <Form.Item label="Pipeline Platform">
              <Select value={platform} onChange={setPlatform} style={{ width: 300 }}>
                {PIPELINE_PLATFORMS.map(p => <Option key={p.value} value={p.value}>{p.label}</Option>)}
              </Select>
            </Form.Item>
          )}

          {integrationType === 'agent' && (
            <Form.Item label="Agent Type">
              <Select value={agentType} onChange={setAgentType} style={{ width: 300 }}>
                {AGENT_TYPES.map(a => <Option key={a.value} value={a.value}>{a.label}</Option>)}
              </Select>
            </Form.Item>
          )}

          {(integrationType === 'cicd' || integrationType === 'agent') && (
            <>
              <Form.Item label="Service Identification Method">
                <Radio.Group value={idMethod} onChange={(e) => { setIdMethod(e.target.value); form.resetFields(); resetSummary(); }}>
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
            </>
          )}

          {integrationType === 'explorer' && (
            <Form form={form} layout="vertical">
              <Row gutter={16}>
                <Col xs={24} sm={12}>
                  <Form.Item name="namespace" label="Namespace (optional)">
                    <Input placeholder="e.g. production" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item name="owner_name" label="Workload Name (optional)">
                    <Input placeholder="e.g. payment-service" />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
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
              loading={summaryLoading}
              disabled={!canProceedStep1}
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
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(0)}>Back</Button>
            <Space>
              {!summaryData?.success && (
                <Button onClick={onSkipToSetup} disabled={!canProceedStep1}>
                  Skip to Setup <ArrowRightOutlined />
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

      {/* ─── Step 2: Preview & Validate ─── */}
      {currentStep === 2 && summaryData?.success && (
        <div>
          {/* Service banner */}
          <Card size="small" style={{ borderLeft: '3px solid #1677ff', marginBottom: 16 }}>
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

          {/* Multi-service: show matched upstream services table */}
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
                  { title: 'Downstream', dataIndex: 'downstream_count', key: 'ds', render: (v: number) => <Badge count={v} showZero style={{ backgroundColor: v ? '#1677ff' : '#d9d9d9' }} /> },
                  { title: 'Callers', dataIndex: 'callers_count', key: 'cl', render: (v: number) => <Badge count={v} showZero style={{ backgroundColor: v ? '#52c41a' : '#d9d9d9' }} /> },
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

          {/* Single-service: show annotations only when not multi */}
          {!summaryData.multi_service && Object.keys(summaryData.service.annotations || {}).length > 0 && (
            <Card size="small" title="Upstream Service Metadata" style={{ marginBottom: 16 }}>
              <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
                {Object.entries(summaryData.service.annotations).map(([k, v]) => (
                  <Descriptions.Item key={k} label={<Text strong style={{ fontSize: 11, color: '#d48806' }}>{k}</Text>}>
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
                children: <CategoryGroup group={summaryData.downstream} title="Downstream" />,
              },
              {
                key: 'callers',
                label: <span><ArrowUpOutlined /> Callers ({summaryData.callers.total})</span>,
                children: <CategoryGroup group={summaryData.callers} title="Callers" />,
              },
              {
                key: 'raw',
                label: <span><CodeOutlined /> Raw JSON</span>,
                children: (
                  <div>
                    <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>Response size: ~{responseSize} KB</Text>
                    <CodeBlockWithCopy code={JSON.stringify(summaryData, null, 2)} label="JSON" />
                  </div>
                ),
              },
            ]}
          />

          <StepNav />
        </div>
      )}

      {/* ─── Step 3: Integration Setup ─── */}
      {currentStep === 3 && (summaryData?.success || summaryParams) && (
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
              ...(integrationType === 'cicd' ? [{
                key: 'pipeline',
                label: <span><RocketOutlined /> {PIPELINE_PLATFORMS.find(p => p.value === platform)?.label || 'Pipeline'}</span>,
                children: <CodeBlockWithCopy code={buildPipelineSnippet()} label="Pipeline YAML" />,
              }] : []),
              {
                key: 'curl',
                label: <span><CodeOutlined /> curl</span>,
                children: <CodeBlockWithCopy code={buildCurlSnippet()} label="curl" />,
              },
              {
                key: 'python',
                label: <span><CodeOutlined /> Python</span>,
                children: <CodeBlockWithCopy code={buildPythonSnippet()} label="Python" />,
              },
              {
                key: 'js',
                label: <span><CodeOutlined /> JavaScript</span>,
                children: <CodeBlockWithCopy code={buildJsSnippet()} label="JavaScript" />,
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

          {(integrationType === 'cicd' || integrationType === 'agent') && (
            <Card title="How Your AI Agent Uses This Data" size="small" style={{ marginTop: 16 }}>
              <Paragraph>
                The <Text code>/dependencies/summary</Text> response groups all dependencies by <Text strong>service category</Text> (database, cache, api, message_broker, etc.).
                Each dependency includes its Kubernetes <Text strong>annotations</Text> and <Text strong>labels</Text>.
              </Paragraph>
              <Paragraph>
                Your AI agent should:
              </Paragraph>
              <ol>
                <li>Extract <Text code>annotations["git-repo"]</Text> from each downstream service to identify affected repositories</li>
                <li>Check <Text code>is_critical</Text> flag to prioritize critical dependency changes</li>
                <li>Use <Text code>service_category</Text> grouping to understand the type of each dependency (database, cache, API, etc.)</li>
                <li>Examine <Text code>callers</Text> to understand which services call the changed service</li>
              </ol>
            </Card>
          )}

          <div style={{ marginTop: 24 }}>
            <Button icon={<ArrowLeftOutlined />} onClick={() => setCurrentStep(summaryData?.success ? 2 : 1)}>
              {summaryData?.success ? 'Back to Preview' : 'Back to Configure'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIIntegrationHub;
