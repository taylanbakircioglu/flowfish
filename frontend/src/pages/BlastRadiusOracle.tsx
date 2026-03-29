/**
 * Blast Radius - Pre-deployment Impact Assessment
 * 
 * CI/CD Pipeline Integration Page
 * Provides API documentation, assessment history, and live testing
 * 
 * Inspired by:
 * - Google/Baidu Blast Radius methodology
 * - Gremlin Reliability Score
 * - Netflix ChAP
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Typography,
  Space,
  Table,
  Tag,
  Button,
  Row,
  Col,
  Statistic,
  Alert,
  Tabs,
  Select,
  Form,
  message,
  Badge,
  Progress,
  Divider,
  Empty,
  Spin,
  Modal,
  Timeline,
  List,
  Descriptions,
  theme,
} from 'antd';
import {
  RocketOutlined,
  ApiOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { colors } from '../styles/colors';
import CodeBlock from '../components/integration/CodeBlock';
import {
  PIPELINE_PLATFORMS,
  buildBlastRadiusCurlSnippet,
  buildBlastRadiusPipelineSnippet,
} from '../utils/snippetBuilders';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { useToken } = theme;

// Types
interface BlastRadiusAssessment {
  assessment_id: string;
  timestamp: string;
  cluster_id: number;
  target: string;
  namespace: string;
  change_type: string;
  risk_score: number;
  risk_level: string;
  affected_count: number;
  triggered_by?: string;
  pipeline?: string;
}

interface AssessmentStats {
  period_days: number;
  total_assessments: number;
  avg_risk_score: number;
  risk_distribution: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  avg_affected_services: number;
}

interface AssessmentResult {
  assessment_id: string;
  timestamp: string;
  risk_score: number;
  risk_level: string;
  confidence: number;
  blast_radius: {
    total_affected: number;
    direct_dependencies: number;
    indirect_dependencies: number;
    critical_services: string[];
    namespaces_affected: string[];
  };
  recommendation: string;
  suggested_actions: Array<{
    priority: string;
    action: string;
    reason: string;
    automatable: boolean;
  }>;
  advisory_only: boolean;
  assessment_duration_ms: number;
}

const BlastRadiusOracle: React.FC = () => {
  const { token } = useToken();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'overview');
  const [assessments, setAssessments] = useState<BlastRadiusAssessment[]>([]);
  const [stats, setStats] = useState<AssessmentStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('azure_devops');
  
  // Test form state
  const [testForm] = Form.useForm();
  const [testResult, setTestResult] = useState<AssessmentResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedAssessment, setSelectedAssessment] = useState<any>(null);
  const [selectedTestClusterId, setSelectedTestClusterId] = useState<number | null>(null);
  const [workloads, setWorkloads] = useState<any[]>([]);
  const [loadingWorkloads, setLoadingWorkloads] = useState(false);
  
  // Cluster and analysis data
  const { data: clustersData } = useGetClustersQuery();
  const clusters: any[] = (clustersData as any)?.clusters || [];
  const { data: analysesData } = useGetAnalysesQuery({});
  const analyses: any[] = Array.isArray(analysesData) ? analysesData : [];
  
  // Filter analyses by selected cluster
  const filteredAnalyses = selectedTestClusterId 
    ? analyses.filter((a: any) => a.cluster_id === selectedTestClusterId)
    : [];
  
  // Fetch workloads when cluster changes
  const fetchWorkloads = useCallback(async (clusterId: number) => {
    setLoadingWorkloads(true);
    try {
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(`/api/v1/workloads?cluster_id=${clusterId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setWorkloads(data.workloads || data || []);
      }
    } catch (error) {
      console.error('Failed to fetch workloads:', error);
    } finally {
      setLoadingWorkloads(false);
    }
  }, []);
  
  // Handle cluster change in test form
  const handleTestClusterChange = (clusterId: number) => {
    setSelectedTestClusterId(clusterId);
    testForm.setFieldsValue({ analysis_id: undefined, target: undefined, namespace: undefined });
    setWorkloads([]);
    if (clusterId) {
      fetchWorkloads(clusterId);
    }
  };

  // Fetch assessment history
  const fetchAssessments = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch('/api/v1/blast-radius/assessments?limit=50', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setAssessments(data);
      }
    } catch (error) {
      console.error('Failed to fetch assessments:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch('/api/v1/blast-radius/stats?days=7', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }, []);

  useEffect(() => {
    fetchAssessments();
    fetchStats();
  }, [fetchAssessments, fetchStats]);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    setSearchParams({ tab: key }, { replace: true });
  };

  // Run test assessment
  const runTestAssessment = async (values: any) => {
    setTesting(true);
    setTestResult(null);
    try {
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch('/api/v1/blast-radius/assess', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          cluster_id: values.cluster_id,
          analysis_id: values.analysis_id,
          change: {
            type: values.change_type,
            target: values.target,
            namespace: values.namespace || 'default',
            triggered_by: 'manual-test',
            pipeline: 'flowfish-ui'
          }
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        setTestResult(result);
        message.success(`Assessment completed: Risk Score ${result.risk_score}/100`);
        fetchAssessments();
        fetchStats();
      } else {
        const error = await response.json();
        message.error(error.detail || 'Assessment failed');
      }
    } catch (error) {
      message.error('Failed to run assessment');
    } finally {
      setTesting(false);
    }
  };

  // View assessment detail
  const viewAssessmentDetail = async (assessmentId: string) => {
    try {
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(`/api/v1/blast-radius/assessment/${assessmentId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setSelectedAssessment(data);
        setDetailModalVisible(true);
      }
    } catch (error) {
      message.error('Failed to load assessment details');
    }
  };

  // Risk level colors
  const getRiskColor = (level: string) => {
    switch (level) {
      case 'critical': return colors.status.error;
      case 'high': return colors.charts.orange;
      case 'medium': return colors.status.warning;
      case 'low': return colors.status.success;
      default: return token.colorTextSecondary;
    }
  };

  // Assessment history columns
  const historyColumns = [
    {
      title: 'Assessment',
      dataIndex: 'assessment_id',
      key: 'assessment_id',
      render: (id: string, record: BlastRadiusAssessment) => (
        <Space direction="vertical" size={0}>
          <Button type="link" size="small" onClick={() => viewAssessmentDetail(id)} style={{ padding: 0 }}>
            {id}
          </Button>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {new Date(record.timestamp).toLocaleString()}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Target',
      key: 'target',
      render: (_: any, record: BlastRadiusAssessment) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.target}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Change',
      dataIndex: 'change_type',
      key: 'change_type',
      render: (type: string) => <Tag>{type.replaceAll('_', ' ')}</Tag>,
    },
    {
      title: 'Risk Score',
      dataIndex: 'risk_score',
      key: 'risk_score',
      render: (score: number, record: BlastRadiusAssessment) => (
        <Space>
          <Progress
            type="circle"
            percent={score}
            size={40}
            strokeColor={getRiskColor(record.risk_level)}
            format={(p) => <span style={{ fontSize: 11 }}>{p}</span>}
          />
        </Space>
      ),
    },
    {
      title: 'Risk Level',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (level: string) => (
        <Tag color={
          level === 'critical' ? 'red' :
          level === 'high' ? 'orange' :
          level === 'medium' ? 'gold' : 'green'
        }>
          {level.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Affected',
      dataIndex: 'affected_count',
      key: 'affected_count',
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 5 ? colors.status.error : colors.status.info }} />
      ),
    },
    {
      title: 'Pipeline',
      dataIndex: 'pipeline',
      key: 'pipeline',
      render: (pipeline: string) => pipeline ? <Tag icon={<BranchesOutlined />}>{pipeline}</Tag> : '-',
    },
  ];

  // ─── Overview tab content ───
  const overviewContent = (
    <Row gutter={24}>
      <Col span={12}>
        <Alert
          message="Advisory Only - You Control the Decision"
          description={
            <div>
              <Paragraph style={{ marginBottom: 8 }}>
                Flowfish Blast Radius Oracle provides risk assessment and recommendations, 
                but <strong>never blocks deployments</strong>. Your pipeline owns the decision.
              </Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                <li>Risk score 0-100 with level classification</li>
                <li>Affected services list (direct &amp; indirect)</li>
                <li>Actionable recommendations</li>
                <li>Full history and statistics</li>
              </ul>
            </div>
          }
          type="info"
          showIcon
          icon={<SafetyCertificateOutlined />}
          style={{ marginBottom: 16 }}
        />
        
        <Card title="How It Works" size="small" bordered>
          <Timeline
            items={[
              {
                color: 'blue',
                children: (
                  <div>
                    <Text strong>1. Pipeline calls Flowfish API</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>POST /api/v1/blast-radius/assess</Text>
                  </div>
                ),
              },
              {
                color: 'cyan',
                children: (
                  <div>
                    <Text strong>2. Flowfish analyzes dependencies</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>Uses existing analysis data and dependency graph</Text>
                  </div>
                ),
              },
              {
                color: 'green',
                children: (
                  <div>
                    <Text strong>3. Returns risk score &amp; recommendations</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>JSON response with score, affected services, suggestions</Text>
                  </div>
                ),
              },
              {
                color: 'gold',
                children: (
                  <div>
                    <Text strong>4. Pipeline decides what to do</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>Continue, require approval, delay - your rules</Text>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      </Col>
      
      <Col span={12}>
        <Card 
          title={<span><ApiOutlined /> API Endpoint</span>} 
          size="small" 
          bordered
          style={{ marginBottom: 16 }}
        >
          <div style={{ 
            background: token.colorBgLayout, 
            padding: 12, 
            borderRadius: 6,
            fontFamily: 'monospace',
            fontSize: 13,
          }}>
            <Text strong style={{ color: colors.status.success }}>POST</Text>
            <Text> /api/v1/blast-radius/assess</Text>
          </div>
          
          <Divider style={{ margin: '12px 0' }} />
          
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Request Body:</Text>
          <pre style={{ 
            background: token.colorBgLayout, 
            padding: 12, 
            borderRadius: 6,
            fontSize: 11,
            overflow: 'auto',
            maxHeight: 200,
          }}>
{`{
  "cluster_id": 1,
  "change": {
    "type": "image_update",
    "target": "payment-service",
    "namespace": "production",
    "triggered_by": "jenkins",
    "pipeline": "main-deploy"
  }
}`}
          </pre>
        </Card>
        
        <Card 
          title={<span><FileTextOutlined /> Response Fields</span>} 
          size="small" 
          bordered
        >
          <List
            size="small"
            dataSource={[
              { field: 'risk_score', desc: '0-100, higher = more risky' },
              { field: 'risk_level', desc: 'low / medium / high / critical' },
              { field: 'blast_radius.total_affected', desc: 'Total services in impact zone' },
              { field: 'recommendation', desc: 'proceed / review_required / delay_suggested' },
              { field: 'suggested_actions[]', desc: 'Contextual action items' },
              { field: 'advisory_only', desc: 'Always true - Flowfish never blocks' },
            ]}
            renderItem={(item) => (
              <List.Item style={{ padding: '6px 0' }}>
                <Text code style={{ fontSize: 11 }}>{item.field}</Text>
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>{item.desc}</Text>
              </List.Item>
            )}
          />
        </Card>

        <Card size="small" bordered style={{ marginTop: 16 }}>
          <Space>
            <ApiOutlined />
            <div>
              <Text strong>Need dependency data for CI/CD pipelines?</Text>
              <br />
              <Link to="/integration/hub">
                <Text type="secondary">
                  Integration Hub &mdash; generate integration snippets for dependency analysis
                </Text>
              </Link>
            </div>
          </Space>
        </Card>
      </Col>
    </Row>
  );

  // ─── Integration tab content ───
  const integrationContent = (
    <div>
      <Alert
        message={
          <Space>
            <ApiOutlined />
            <span>
              For a complete guided setup wizard with all platforms and authentication docs, visit the{' '}
              <Link to="/integration/hub"><strong>Integration Hub</strong></Link>.
            </span>
          </Space>
        }
        type="info"
        showIcon={false}
        style={{ marginBottom: 16 }}
        action={
          <Link to="/integration/hub">
            <Button size="small" type="primary">Open Integration Hub</Button>
          </Link>
        }
      />

      <Tabs
        size="small"
        items={[
          {
            key: 'br-pipeline',
            label: <span><RocketOutlined /> Pipeline</span>,
            children: (
              <div>
                <Space align="center" style={{ marginBottom: 12 }}>
                  <Text strong>Platform:</Text>
                  <Select value={selectedPlatform} onChange={setSelectedPlatform} style={{ width: 200 }}>
                    {PIPELINE_PLATFORMS.map(p => (
                      <Option key={p.value} value={p.value}>{p.label}</Option>
                    ))}
                  </Select>
                </Space>
                <CodeBlock code={buildBlastRadiusPipelineSnippet(selectedPlatform)} label="Blast Radius Pipeline" />
              </div>
            ),
          },
          {
            key: 'br-curl',
            label: <span><CodeOutlined /> curl</span>,
            children: <CodeBlock code={buildBlastRadiusCurlSnippet()} label="Blast Radius curl" />,
          },
        ]}
      />

      <Card size="small" style={{ marginTop: 16 }}>
        <Text strong style={{ display: 'block', marginBottom: 12 }}>Required Variables</Text>
        <Descriptions size="small" column={{ xs: 1, sm: 3 }} bordered>
          <Descriptions.Item label={<Text code>FLOWFISH_URL</Text>}>
            <Text type="secondary" style={{ fontSize: 12 }}>Flowfish API base URL</Text>
          </Descriptions.Item>
          <Descriptions.Item label={<Text code>FLOWFISH_API_KEY</Text>}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              API Key from <Link to="/settings">Settings &gt; API Keys</Link>
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label={<Text code>CLUSTER_ID</Text>}>
            <Text type="secondary" style={{ fontSize: 12 }}>Target cluster ID in Flowfish</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );

  // ─── Test tab content ───
  const testContent = (
    <Row gutter={24}>
      <Col span={10}>
        <Card title="Run Test Assessment" bordered size="small">
          <Form
            form={testForm}
            layout="vertical"
            onFinish={runTestAssessment}
          >
            <Form.Item
              name="cluster_id"
              label="Cluster"
              rules={[{ required: true, message: 'Select cluster' }]}
            >
              <Select 
                placeholder="Select cluster"
                onChange={handleTestClusterChange}
              >
                {clusters.map((c: any) => (
                  <Option key={c.id} value={c.id}>{c.name}</Option>
                ))}
              </Select>
            </Form.Item>
            
            <Form.Item
              name="analysis_id"
              label="Analysis (optional)"
              tooltip="Uses latest completed analysis if not selected"
            >
              <Select 
                placeholder={!selectedTestClusterId ? "Select cluster first" : "Latest analysis"} 
                allowClear
                disabled={!selectedTestClusterId}
              >
                {filteredAnalyses.map((a: any) => (
                  <Option key={a.id} value={a.id}>
                    {a.name} ({a.status})
                  </Option>
                ))}
              </Select>
            </Form.Item>
            
            <Form.Item
              name="target"
              label="Target Service"
              rules={[{ required: true, message: 'Select or enter target' }]}
            >
              <Select
                placeholder={!selectedTestClusterId ? "Select cluster first" : "Select target service"}
                disabled={!selectedTestClusterId}
                loading={loadingWorkloads}
                showSearch
                allowClear
                optionFilterProp="children"
                onChange={(value) => {
                  const selectedWorkload = workloads.find((w: any) => w.name === value);
                  if (selectedWorkload?.namespace) {
                    testForm.setFieldsValue({ namespace: selectedWorkload.namespace });
                  }
                }}
              >
                {workloads
                  .filter((w: any, index: number, self: any[]) => 
                    index === self.findIndex((t: any) => t.name === w.name && t.namespace === w.namespace)
                  )
                  .map((w: any) => (
                    <Option key={`${w.namespace}-${w.name}`} value={w.name}>
                      {w.name} ({w.namespace})
                    </Option>
                  ))}
              </Select>
            </Form.Item>
            
            <Form.Item
              name="namespace"
              label="Namespace"
              tooltip="Auto-filled when you select a target service"
            >
              <Select
                placeholder={!selectedTestClusterId ? "Select cluster first" : "Select namespace"}
                disabled={!selectedTestClusterId}
                allowClear
                showSearch
              >
                {Array.from(new Set(workloads.map((w: any) => w.namespace))).filter(Boolean).map((ns: any) => (
                  <Option key={ns} value={ns}>{ns}</Option>
                ))}
              </Select>
            </Form.Item>
            
            <Form.Item
              name="change_type"
              label="Change Type"
              initialValue="image_update"
            >
              <Select>
                <Option value="image_update">Image Update</Option>
                <Option value="config_change">Config Change</Option>
                <Option value="scale_change">Scale Change</Option>
                <Option value="delete">Delete</Option>
                <Option value="network_policy">Network Policy</Option>
              </Select>
            </Form.Item>
            
            <Button 
              type="primary" 
              htmlType="submit" 
              loading={testing}
              icon={<PlayCircleOutlined />}
              block
            >
              Run Assessment
            </Button>
          </Form>
        </Card>
      </Col>
      
      <Col span={14}>
        <Card 
          title="Assessment Result" 
          bordered 
          size="small"
          style={{ minHeight: 400 }}
        >
          {!testResult && !testing && (
            <Empty description="Run a test to see results" />
          )}
          
          {testing && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <div style={{ marginTop: 16 }}>
                <Text>Analyzing dependencies...</Text>
              </div>
            </div>
          )}
          
          {testResult && (
            <div>
              <div style={{ textAlign: 'center', marginBottom: 24 }}>
                <Progress
                  type="dashboard"
                  percent={testResult.risk_score}
                  strokeColor={getRiskColor(testResult.risk_level)}
                  format={(p) => (
                    <div>
                      <div style={{ fontSize: 28, fontWeight: 700 }}>{p}</div>
                      <Tag color={
                        testResult.risk_level === 'critical' ? 'red' :
                        testResult.risk_level === 'high' ? 'orange' :
                        testResult.risk_level === 'medium' ? 'gold' : 'green'
                      }>
                        {testResult.risk_level.toUpperCase()}
                      </Tag>
                    </div>
                  )}
                  width={150}
                />
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">
                    Confidence: {Math.round(testResult.confidence * 100)}% | 
                    Duration: {testResult.assessment_duration_ms}ms
                  </Text>
                </div>
              </div>
              
              <Divider />
              
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={8}>
                  <Statistic 
                    title="Total Affected" 
                    value={testResult.blast_radius.total_affected} 
                    valueStyle={{ color: colors.primary.main }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic 
                    title="Direct" 
                    value={testResult.blast_radius.direct_dependencies}
                    valueStyle={{ color: colors.status.error }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic 
                    title="Indirect" 
                    value={testResult.blast_radius.indirect_dependencies}
                    valueStyle={{ color: colors.status.warning }}
                  />
                </Col>
              </Row>
              
              {testResult.blast_radius.critical_services.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong>Critical Services:</Text>
                  <div style={{ marginTop: 8 }}>
                    {testResult.blast_radius.critical_services.map((s, i) => (
                      <Tag key={i} color="red">{s}</Tag>
                    ))}
                  </div>
                </div>
              )}
              
              <Alert
                message={`Recommendation: ${testResult.recommendation.replaceAll('_', ' ').toUpperCase()}`}
                type={
                  testResult.recommendation === 'proceed' ? 'success' :
                  testResult.recommendation === 'review_required' ? 'warning' : 'error'
                }
                showIcon
                style={{ marginBottom: 16 }}
              />
              
              <Text strong>Suggested Actions:</Text>
              <List
                size="small"
                dataSource={testResult.suggested_actions}
                renderItem={(action) => (
                  <List.Item>
                    <Space>
                      {action.priority === 'critical' && <ExclamationCircleOutlined style={{ color: colors.status.error }} />}
                      {action.priority === 'high' && <WarningOutlined style={{ color: colors.status.warning }} />}
                      {action.priority === 'medium' && <InfoCircleOutlined style={{ color: colors.status.info }} />}
                      {action.priority === 'low' && <CheckCircleOutlined style={{ color: colors.status.success }} />}
                      <div>
                        <Text>{action.action}</Text>
                        {action.automatable && <Tag style={{ marginLeft: 8 }} color="blue">Automatable</Tag>}
                      </div>
                    </Space>
                  </List.Item>
                )}
              />

              <Divider />

              <Alert
                message={
                  <span>
                    Need deeper analysis with flow diagrams, chaos templates, and network policy generation?{' '}
                    <Link to={`/impact/simulation${selectedTestClusterId ? `?clusterId=${selectedTestClusterId}` : ''}`}>
                      <strong>Open Impact Simulation</strong>
                    </Link>
                  </span>
                }
                type="info"
                showIcon
                icon={<ThunderboltOutlined />}
              />
            </div>
          )}
        </Card>
      </Col>
    </Row>
  );

  // ─── History tab content ───
  const historyContent = (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button 
          icon={<ReloadOutlined />} 
          onClick={fetchAssessments}
          loading={loading}
        >
          Refresh
        </Button>
      </div>
      
      <Table
        dataSource={assessments}
        columns={historyColumns}
        rowKey="assessment_id"
        loading={loading}
        pagination={{ pageSize: 15, showSizeChanger: true, pageSizeOptions: ['10', '15', '30', '50'] }}
        locale={{ emptyText: 'No assessments yet. Run a test or integrate with your pipeline.' }}
      />
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center" style={{ marginBottom: 8 }}>
          <RocketOutlined style={{ fontSize: 28, color: colors.primary.main }} />
          <Title level={2} style={{ margin: 0 }}>Blast Radius</Title>
          <Tag color="blue">Beta</Tag>
        </Space>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Pre-deployment impact assessment API for CI/CD pipeline integration. 
          Flowfish provides risk scores and recommendations - your pipeline decides what to do.
        </Paragraph>
      </div>

      {/* Stats Cards */}
      {stats ? (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic
                title="Assessments (7 days)"
                value={stats.total_assessments}
                prefix={<HistoryOutlined style={{ color: colors.primary.main }} />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic
                title="Avg Risk Score"
                value={stats.avg_risk_score}
                suffix="/100"
                valueStyle={{ color: stats.avg_risk_score > 50 ? colors.status.warning : colors.status.success }}
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic
                title="High/Critical Risks"
                value={(stats.risk_distribution?.high || 0) + (stats.risk_distribution?.critical || 0)}
                valueStyle={{ color: colors.status.error }}
                prefix={<ExclamationCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic
                title="Avg Affected Services"
                value={stats.avg_affected_services}
                prefix={<CloudServerOutlined style={{ color: colors.charts.blue }} />}
              />
            </Card>
          </Col>
        </Row>
      ) : (
        <Card style={{ marginBottom: 24, textAlign: 'center', padding: 16 }}>
          <ClockCircleOutlined style={{ fontSize: 24, color: token.colorTextSecondary, marginBottom: 8 }} />
          <br />
          <Text type="secondary">
            Run your first assessment or integrate with a CI/CD pipeline to see statistics here.
          </Text>
        </Card>
      )}

      {/* Main Tabs */}
      <Card bordered={false}>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'overview',
              label: <span><InfoCircleOutlined /> Overview</span>,
              children: overviewContent,
            },
            {
              key: 'integration',
              label: <span><CodeOutlined /> Integration</span>,
              children: integrationContent,
            },
            {
              key: 'test',
              label: <span><PlayCircleOutlined /> Test</span>,
              children: testContent,
            },
            {
              key: 'history',
              label: (
                <span>
                  <HistoryOutlined /> History
                  {assessments.length > 0 && (
                    <Badge
                      count={assessments.length}
                      style={{ marginLeft: 8, backgroundColor: token.colorPrimary }}
                    />
                  )}
                </span>
              ),
              children: historyContent,
            },
          ]}
        />
      </Card>

      {/* Assessment Detail Modal */}
      <Modal
        title={`Assessment: ${selectedAssessment?.assessment_id}`}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={null}
        width={700}
      >
        {selectedAssessment && (
          <div>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Statistic 
                  title="Risk Score" 
                  value={selectedAssessment.risk_score} 
                  suffix="/100"
                  valueStyle={{ color: getRiskColor(selectedAssessment.risk_level) }}
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="Affected Services" 
                  value={selectedAssessment.blast_radius?.total_affected || 0} 
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="Confidence" 
                  value={Math.round((selectedAssessment.confidence || 0) * 100)} 
                  suffix="%"
                />
              </Col>
            </Row>
            
            <pre style={{ 
              background: token.colorBgLayout, 
              padding: 16, 
              borderRadius: 8,
              fontSize: 11,
              overflow: 'auto',
              maxHeight: 400,
            }}>
              {JSON.stringify(selectedAssessment, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default BlastRadiusOracle;
