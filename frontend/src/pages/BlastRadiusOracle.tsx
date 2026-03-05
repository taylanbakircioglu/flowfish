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
  Input,
  Form,
  message,
  Badge,
  Progress,
  Tooltip,
  Divider,
  Empty,
  Spin,
  Modal,
  Timeline,
  List,
  theme,
} from 'antd';
import {
  RocketOutlined,
  ApiOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  CopyOutlined,
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
  SettingOutlined,
} from '@ant-design/icons';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { colors } from '../styles/colors';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
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

// Code snippets for different CI/CD platforms
const codeSnippets = {
  azureDevOps: `# Azure DevOps Pipeline - Flowfish Blast Radius Check
- task: Bash@3
  displayName: '🐟 Flowfish Blast Radius Check'
  inputs:
    targetType: 'inline'
    script: |
      #!/bin/bash
      set -e
      
      echo "=========================================="
      echo "🐟 Flowfish Blast Radius Assessment"
      echo "=========================================="
      
      # Flowfish API çağrısı
      RESPONSE=$(curl -s -w "\\n%{http_code}" -X POST \\
        "$(FLOWFISH_URL)/api/v1/blast-radius/assess" \\
        -H "Authorization: Bearer $(FLOWFISH_TOKEN)" \\
        -H "Content-Type: application/json" \\
        -d '{
          "cluster_id": $(CLUSTER_ID),
          "change": {
            "type": "$(Build.Reason)",
            "target": "$(SERVICE_NAME)",
            "namespace": "$(NAMESPACE)",
            "triggered_by": "$(Build.RequestedFor)",
            "pipeline": "$(Build.DefinitionName)",
            "commit": "$(Build.SourceVersion)"
          }
        }')
      
      # Response ve HTTP code ayır
      HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
      BODY=$(echo "$RESPONSE" | sed '$d')
      
      # API erişilemezse devam et
      if [ "$HTTP_CODE" != "200" ]; then
        echo "⚠️ Flowfish API unreachable. Continuing..."
        exit 0
      fi
      
      # Sonuçları göster
      RISK_SCORE=$(echo "$BODY" | jq -r '.risk_score')
      RISK_LEVEL=$(echo "$BODY" | jq -r '.risk_level')
      AFFECTED=$(echo "$BODY" | jq -r '.blast_radius.total_affected')
      
      echo "📊 Risk Score: $RISK_SCORE/100"
      echo "📊 Risk Level: $RISK_LEVEL"
      echo "📊 Affected Services: $AFFECTED"
      
      # Pipeline variable olarak kaydet
      echo "##vso[task.setvariable variable=RISK_SCORE]$RISK_SCORE"
      echo "##vso[task.setvariable variable=RISK_LEVEL]$RISK_LEVEL"
  continueOnError: true  # Flowfish hatası pipeline'ı durdurmaz
  env:
    FLOWFISH_URL: $(FLOWFISH_URL)
    FLOWFISH_TOKEN: $(FLOWFISH_TOKEN)`,

  jenkins: `// Jenkins Pipeline - Flowfish Blast Radius Check
stage('Blast Radius Check') {
    steps {
        script {
            def response = httpRequest(
                url: "\${FLOWFISH_URL}/api/v1/blast-radius/assess",
                httpMode: 'POST',
                contentType: 'APPLICATION_JSON',
                customHeaders: [[name: 'Authorization', value: "Bearer \${FLOWFISH_TOKEN}"]],
                requestBody: """
                {
                    "cluster_id": \${CLUSTER_ID},
                    "change": {
                        "type": "image_update",
                        "target": "\${SERVICE_NAME}",
                        "namespace": "\${NAMESPACE}",
                        "triggered_by": "\${BUILD_USER}",
                        "pipeline": "\${JOB_NAME}"
                    }
                }
                """,
                validResponseCodes: '200:500'
            )
            
            if (response.status == 200) {
                def result = readJSON(text: response.content)
                echo "🐟 Risk Score: \${result.risk_score}/100"
                echo "🐟 Risk Level: \${result.risk_level}"
                echo "🐟 Affected: \${result.blast_radius.total_affected} services"
                
                // Takımın kendi kuralı
                if (result.risk_score > 80 && env.STRICT_MODE == 'true') {
                    input message: "High risk! Approve deployment?"
                }
            } else {
                echo "⚠️ Flowfish unavailable, continuing..."
            }
        }
    }
}`,

  githubActions: `# GitHub Actions - Flowfish Blast Radius Check
- name: 🐟 Flowfish Blast Radius Check
  id: blast-radius
  continue-on-error: true
  run: |
    RESPONSE=$(curl -s -X POST \\
      "\${{ secrets.FLOWFISH_URL }}/api/v1/blast-radius/assess" \\
      -H "Authorization: Bearer \${{ secrets.FLOWFISH_TOKEN }}" \\
      -H "Content-Type: application/json" \\
      -d '{
        "cluster_id": \${{ vars.CLUSTER_ID }},
        "change": {
          "type": "image_update",
          "target": "\${{ github.event.repository.name }}",
          "namespace": "\${{ vars.NAMESPACE }}",
          "triggered_by": "\${{ github.actor }}",
          "pipeline": "\${{ github.workflow }}",
          "commit": "\${{ github.sha }}"
        }
      }')
    
    RISK_SCORE=$(echo "$RESPONSE" | jq -r '.risk_score // 0')
    RISK_LEVEL=$(echo "$RESPONSE" | jq -r '.risk_level // "unknown"')
    
    echo "risk_score=$RISK_SCORE" >> $GITHUB_OUTPUT
    echo "risk_level=$RISK_LEVEL" >> $GITHUB_OUTPUT
    echo "🐟 Risk: $RISK_SCORE/100 ($RISK_LEVEL)"

- name: Comment PR with Risk Assessment
  if: github.event_name == 'pull_request'
  uses: actions/github-script@v6
  with:
    script: |
      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: '🐟 **Flowfish Blast Radius**: \${{ steps.blast-radius.outputs.risk_score }}/100 (\${{ steps.blast-radius.outputs.risk_level }})'
      })`,

  curl: `# Simple cURL Example
curl -X POST "https://flowfish.your-domain.com/api/v1/blast-radius/assess" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "cluster_id": 1,
    "change": {
      "type": "image_update",
      "target": "payment-service",
      "namespace": "production",
      "triggered_by": "deploy-bot",
      "pipeline": "main-deploy"
    }
  }'

# Response:
# {
#   "assessment_id": "br-20260117-abc123",
#   "risk_score": 72,
#   "risk_level": "high",
#   "blast_radius": {
#     "total_affected": 14,
#     "direct_dependencies": 3,
#     "critical_services": ["checkout", "order-service"]
#   },
#   "recommendation": "review_required",
#   "advisory_only": true
# }`
};

const BlastRadiusOracle: React.FC = () => {
  const { token } = useToken();
  const [activeTab, setActiveTab] = useState('overview');
  const [assessments, setAssessments] = useState<BlastRadiusAssessment[]>([]);
  const [stats, setStats] = useState<AssessmentStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('azureDevOps');
  
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
        fetchAssessments(); // Refresh history
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

  // Copy code to clipboard
  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    message.success('Code copied to clipboard!');
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
      render: (type: string) => <Tag>{type.replace('_', ' ')}</Tag>,
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
      {stats && (
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
                value={stats.risk_distribution.high + stats.risk_distribution.critical}
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
      )}

      {/* Main Tabs */}
      <Card bordered={false}>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          {/* Overview Tab */}
          <TabPane
            tab={<span><InfoCircleOutlined /> Overview</span>}
            key="overview"
          >
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
                        <li>Affected services list (direct & indirect)</li>
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
                            <Text strong>3. Returns risk score & recommendations</Text>
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
              </Col>
            </Row>
          </TabPane>

          {/* Integration Tab */}
          <TabPane
            tab={<span><CodeOutlined /> Integration</span>}
            key="integration"
          >
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ marginRight: 12 }}>Platform:</Text>
              <Select
                value={selectedPlatform}
                onChange={setSelectedPlatform}
                style={{ width: 200 }}
              >
                <Option value="azureDevOps">
                  <Space><SettingOutlined /> Azure DevOps</Space>
                </Option>
                <Option value="jenkins">
                  <Space><SettingOutlined /> Jenkins</Space>
                </Option>
                <Option value="githubActions">
                  <Space><SettingOutlined /> GitHub Actions</Space>
                </Option>
                <Option value="curl">
                  <Space><CodeOutlined /> cURL (Generic)</Space>
                </Option>
              </Select>
            </div>
            
            <Card 
              bordered
              title={
                <Space>
                  <CodeOutlined />
                  <span>
                    {selectedPlatform === 'azureDevOps' && 'Azure DevOps Pipeline'}
                    {selectedPlatform === 'jenkins' && 'Jenkins Pipeline'}
                    {selectedPlatform === 'githubActions' && 'GitHub Actions'}
                    {selectedPlatform === 'curl' && 'cURL Example'}
                  </span>
                </Space>
              }
              extra={
                <Button 
                  icon={<CopyOutlined />} 
                  onClick={() => copyCode(codeSnippets[selectedPlatform as keyof typeof codeSnippets])}
                >
                  Copy
                </Button>
              }
            >
              <pre style={{ 
                background: '#1e1e1e', 
                color: '#d4d4d4',
                padding: 16, 
                borderRadius: 8,
                fontSize: 12,
                overflow: 'auto',
                maxHeight: 500,
                margin: 0,
              }}>
                {codeSnippets[selectedPlatform as keyof typeof codeSnippets]}
              </pre>
            </Card>
            
            <Alert
              message="Required Variables"
              description={
                <Row gutter={16}>
                  <Col span={8}>
                    <Text code>FLOWFISH_URL</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>Flowfish API base URL</Text>
                  </Col>
                  <Col span={8}>
                    <Text code>FLOWFISH_TOKEN</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>JWT authentication token</Text>
                  </Col>
                  <Col span={8}>
                    <Text code>CLUSTER_ID</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>Target cluster ID in Flowfish</Text>
                  </Col>
                </Row>
              }
              type="warning"
              showIcon
              style={{ marginTop: 16 }}
            />
          </TabPane>

          {/* Test Tab */}
          <TabPane
            tab={<span><PlayCircleOutlined /> Test</span>}
            key="test"
          >
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
                          // Auto-fill namespace when target is selected
                          const selectedWorkload = workloads.find((w: any) => w.name === value);
                          if (selectedWorkload?.namespace) {
                            testForm.setFieldsValue({ namespace: selectedWorkload.namespace });
                          }
                        }}
                      >
                        {/* Deduplicate workloads by name+namespace */}
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
                      {/* Risk Score Display */}
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
                      
                      {/* Blast Radius */}
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
                      
                      {/* Critical Services */}
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
                      
                      {/* Recommendation */}
                      <Alert
                        message={`Recommendation: ${testResult.recommendation.replace('_', ' ').toUpperCase()}`}
                        type={
                          testResult.recommendation === 'proceed' ? 'success' :
                          testResult.recommendation === 'review_required' ? 'warning' : 'error'
                        }
                        showIcon
                        style={{ marginBottom: 16 }}
                      />
                      
                      {/* Suggested Actions */}
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
                    </div>
                  )}
                </Card>
              </Col>
            </Row>
          </TabPane>

          {/* History Tab */}
          <TabPane
            tab={
              <span>
                <HistoryOutlined /> History
                {assessments.length > 0 && (
                  <Badge count={assessments.length} style={{ marginLeft: 8 }} />
                )}
              </span>
            }
            key="history"
          >
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
              pagination={{ pageSize: 15 }}
              locale={{ emptyText: 'No assessments yet. Run a test or integrate with your pipeline.' }}
            />
          </TabPane>
        </Tabs>
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
