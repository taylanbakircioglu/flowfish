/**
 * ChangeImpactSummary - Historical Impact Summary for Change Detection
 * 
 * NOTE: This is NOT the same as Impact Simulation!
 * - Impact Simulation: Proactive "what if" analysis BEFORE changes
 * - This Component: Historical summary of what ACTUALLY happened
 * 
 * For detailed impact analysis and simulation, use the Impact Simulation page.
 */

import React from 'react';
import {
  Card,
  Row,
  Col,
  Typography,
  Tag,
  Space,
  Statistic,
  Progress,
  Alert,
  Button,
  Tooltip,
  Divider,
} from 'antd';
import {
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  ThunderboltOutlined,
  RightOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Text, Paragraph } = Typography;

// Types
interface ChangeImpactSummaryProps {
  changeType?: string;
  target?: string;
  namespace?: string;
  affectedServices: number;
  riskLevel: 'critical' | 'high' | 'medium' | 'low';
  clusterId?: number;
  analysisId?: number;
}

// Risk level configuration
const riskLevelConfig: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  critical: { color: '#cf1322', label: 'Critical', icon: <ExclamationCircleOutlined /> },
  high: { color: '#c75450', label: 'High', icon: <WarningOutlined /> },
  medium: { color: '#b89b5d', label: 'Medium', icon: <WarningOutlined /> },
  low: { color: '#4d9f7c', label: 'Low', icon: <CheckCircleOutlined /> },
};

// Change type labels (display names)
const changeTypeLabels: Record<string, string> = {
  connection_removed: 'Connection Anomaly',
};

// Change type descriptions
const changeTypeDescriptions: Record<string, string> = {
  workload_added: 'A new workload was added. Dependencies may have been created.',
  workload_removed: 'A workload was removed. Dependent services may have been affected.',
  connection_added: 'A new connection was detected.',
  connection_removed: 'A connection is no longer observed — may be transient.',
  port_changed: 'Port configuration changed. Clients should have been updated.',
  config_changed: 'Configuration was modified.',
  namespace_changed: 'Namespace was changed.',
  replica_changed: 'Replica count was modified.',
};

const ChangeImpactSummary: React.FC<ChangeImpactSummaryProps> = ({
  changeType,
  target,
  namespace,
  affectedServices,
  riskLevel,
  clusterId,
  analysisId,
}) => {
  const navigate = useNavigate();
  const riskConfig = riskLevelConfig[riskLevel] || riskLevelConfig.medium;

  // Calculate impact severity for progress bar
  const impactSeverity = 
    riskLevel === 'critical' ? 100 :
    riskLevel === 'high' ? 75 :
    riskLevel === 'medium' ? 50 : 25;

  const handleGoToSimulation = () => {
    // Navigate to Impact Simulation with pre-filled target and filters
    const params = new URLSearchParams();
    if (analysisId) params.set('analysisId', String(analysisId));
    if (clusterId) params.set('clusterId', String(clusterId));
    if (target) params.set('target', target);
    if (namespace) params.set('namespace', namespace);
    
    const queryString = params.toString();
    navigate(`/impact-simulation${queryString ? `?${queryString}` : ''}`);
  };

  return (
    <div>
      {/* Info Alert */}
      <Alert
        type="info"
        icon={<InfoCircleOutlined />}
        message="Historical Impact Summary"
        description={
          <span>
            This is the impact summary at the time the change occurred. 
            To simulate the impact of future changes, use the{' '}
            <Button type="link" size="small" onClick={handleGoToSimulation} style={{ padding: 0 }}>
              Impact Simulation
            </Button>{' '}
            page.
          </span>
        }
        style={{ marginBottom: 16 }}
      />

      {/* Impact Summary Cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card bordered={false}>
            <Statistic
              title="Affected Services"
              value={affectedServices}
              prefix={<CloudServerOutlined style={{ color: '#0891b2' }} />}
              valueStyle={{ 
                color: affectedServices > 5 ? '#c75450' : 
                       affectedServices > 2 ? '#b89b5d' : '#4d9f7c' 
              }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card bordered={false}>
            <Statistic
              title="Risk Level"
              value={riskConfig.label}
              prefix={riskConfig.icon}
              valueStyle={{ color: riskConfig.color }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card bordered={false}>
            <Statistic
              title="Blast Radius"
              value={
                affectedServices > 10 ? 'Wide' :
                affectedServices > 5 ? 'Medium' :
                affectedServices > 0 ? 'Limited' : 'None'
              }
              prefix={<ThunderboltOutlined />}
              valueStyle={{ 
                color: affectedServices > 10 ? '#c75450' : 
                       affectedServices > 5 ? '#b89b5d' : '#4d9f7c' 
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* Risk Progress */}
      <Card bordered={false} style={{ marginBottom: 16 }}>
        <Text strong>Impact Severity</Text>
        <Progress
          percent={impactSeverity}
          strokeColor={riskConfig.color}
          format={() => riskConfig.label}
          style={{ marginTop: 8 }}
        />
        
        {changeType && (
          <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            <Tag color="blue">{changeTypeLabels[changeType] || changeType.replace('_', ' ')}</Tag>
            {changeTypeDescriptions[changeType] || 'Change detected.'}
          </Paragraph>
        )}
      </Card>

      {/* Warning for high impact */}
      {(riskLevel === 'critical' || riskLevel === 'high') && (
        <Alert
          type={riskLevel === 'critical' ? 'error' : 'warning'}
          message={`${riskConfig.label} Risk Change`}
          description={
            <div>
              <Paragraph style={{ marginBottom: 8 }}>
                This change affected {affectedServices} service(s).
                {riskLevel === 'critical' && ' Immediate review may be required.'}
              </Paragraph>
              <Space>
                <Tooltip title="Simulate the impact of a similar change in the future">
                  <Button 
                    type="primary" 
                    size="small" 
                    icon={<ThunderboltOutlined />}
                    onClick={handleGoToSimulation}
                  >
                    Go to Impact Simulation
                  </Button>
                </Tooltip>
              </Space>
            </div>
          }
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Action suggestion */}
      <Divider />
      <Card 
        bordered={false} 
        style={{ background: '#fafafa', cursor: 'pointer' }}
        onClick={handleGoToSimulation}
        hoverable
      >
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <ThunderboltOutlined style={{ fontSize: 20, color: '#0891b2' }} />
            <div>
              <Text strong>Simulate Future Changes</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                Use Impact Simulation for "what if" analysis
              </Text>
            </div>
          </Space>
          <RightOutlined style={{ color: '#999' }} />
        </Space>
      </Card>
    </div>
  );
};

export default ChangeImpactSummary;
