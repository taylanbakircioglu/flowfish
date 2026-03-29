/**
 * ChangeDetailDrawer - Detailed view for a single change
 * 
 * Shows:
 * - Full change details
 * - Before/After state comparison
 * - Impact preview (affected services)
 * - Audit trail
 * - Related changes
 */

import React, { useState } from 'react';
import {
  Drawer,
  Typography,
  Space,
  Tag,
  Descriptions,
  Timeline,
  Card,
  Row,
  Col,
  Statistic,
  Divider,
  Badge,
  Empty,
  Spin,
  Button,
  Tooltip,
  Alert,
  theme,
  Tabs,
} from 'antd';
import {
  ClockCircleOutlined,
  UserOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  SwapOutlined,
  ApiOutlined,
  CloudServerOutlined,
  RollbackOutlined,
  HistoryOutlined,
  LinkOutlined,
  ArrowRightOutlined,
  ApartmentOutlined,
  InfoCircleOutlined,
  DisconnectOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { 
  useGetChangeDetailsQuery, 
  useGetCorrelatedChangesQuery,
  Change, 
  ChangeType, 
  RiskLevel 
} from '../store/api/changesApi';
import ChangeImpactSummary from './ChangeImpactSummary';

dayjs.extend(relativeTime);

const { Title, Text, Paragraph } = Typography;

// Change type configuration
const changeTypeConfig: Record<ChangeType, { label: string; color: string; icon: React.ReactNode; description: string }> = {
  workload_added: { 
    label: 'Workload Added', 
    color: '#4d9f7c', 
    icon: <CloudServerOutlined />,
    description: 'A new workload (deployment, statefulset, daemonset) was added to the cluster'
  },
  workload_removed: { 
    label: 'Workload Removed', 
    color: '#c75450', 
    icon: <CloudServerOutlined />,
    description: 'An existing workload was removed or deleted from the cluster'
  },
  connection_added: { 
    label: 'New Connection', 
    color: '#4d9f7c', 
    icon: <ApiOutlined />,
    description: 'A new network connection was observed between workloads'
  },
  connection_removed: { 
    label: 'Connection Anomaly', 
    color: '#c75450', 
    icon: <DisconnectOutlined />,
    description: 'A network connection between workloads is no longer observed — may be transient'
  },
  port_changed: { 
    label: 'Port Changed', 
    color: '#7c8eb5', 
    icon: <SwapOutlined />,
    description: 'A workload changed its exposed port configuration'
  },
  config_changed: { 
    label: 'Config Changed', 
    color: '#22a6a6', 
    icon: <SwapOutlined />,
    description: 'Configuration (ConfigMap, Secret, env vars) was modified'
  },
  namespace_changed: { 
    label: 'Namespace Changed', 
    color: '#a67c9e', 
    icon: <SwapOutlined />,
    description: 'A workload was moved to a different namespace'
  },
  replica_changed: { 
    label: 'Replica Changed', 
    color: '#c9a55a', 
    icon: <SwapOutlined />,
    description: 'The number of replicas was scaled up or down'
  },
  // Infrastructure change types - Workloads
  image_changed: {
    label: 'Image Changed',
    color: '#9254de',
    icon: <SwapOutlined />,
    description: 'Container image version or tag was updated'
  },
  label_changed: {
    label: 'Label Changed',
    color: '#597ef7',
    icon: <SwapOutlined />,
    description: 'Kubernetes labels or annotations were modified'
  },
  resource_changed: {
    label: 'Resource Changed',
    color: '#d48806',
    icon: <SwapOutlined />,
    description: 'Container CPU/memory requests or limits were modified'
  },
  env_changed: {
    label: 'Env Changed',
    color: '#7cb305',
    icon: <SwapOutlined />,
    description: 'Container environment variables were modified'
  },
  spec_changed: {
    label: 'Spec Changed',
    color: '#531dab',
    icon: <SwapOutlined />,
    description: 'Container or pod spec was modified (general catch-all)'
  },
  // Infrastructure change types - Services
  service_port_changed: {
    label: 'Service Port Changed',
    color: '#08979c',
    icon: <SwapOutlined />,
    description: 'Service port, targetPort, or protocol was modified'
  },
  service_selector_changed: {
    label: 'Service Selector Changed',
    color: '#c41d7f',
    icon: <SwapOutlined />,
    description: 'Service pod selector was modified, may affect routing'
  },
  service_type_changed: {
    label: 'Service Type Changed',
    color: '#1d39c4',
    icon: <CloudServerOutlined />,
    description: 'Service type was changed (e.g., ClusterIP to LoadBalancer)'
  },
  service_added: {
    label: 'Service Added',
    color: '#389e0d',
    icon: <CloudServerOutlined />,
    description: 'A new Kubernetes service was created'
  },
  service_removed: {
    label: 'Service Removed',
    color: '#cf1322',
    icon: <CloudServerOutlined />,
    description: 'A Kubernetes service was deleted'
  },
  // Infrastructure change types - Network / Ingress / Route
  network_policy_added: {
    label: 'Network Policy Added',
    color: '#389e0d',
    icon: <ApiOutlined />,
    description: 'A new NetworkPolicy was created'
  },
  network_policy_removed: {
    label: 'Network Policy Removed',
    color: '#cf1322',
    icon: <ApiOutlined />,
    description: 'A NetworkPolicy was deleted'
  },
  network_policy_changed: {
    label: 'Network Policy Changed',
    color: '#d46b08',
    icon: <ApiOutlined />,
    description: 'NetworkPolicy rules were modified'
  },
  ingress_added: {
    label: 'Ingress Added',
    color: '#389e0d',
    icon: <ApiOutlined />,
    description: 'A new Ingress resource was created'
  },
  ingress_removed: {
    label: 'Ingress Removed',
    color: '#cf1322',
    icon: <ApiOutlined />,
    description: 'An Ingress resource was deleted'
  },
  ingress_changed: {
    label: 'Ingress Changed',
    color: '#d46b08',
    icon: <ApiOutlined />,
    description: 'Ingress rules or configuration were modified'
  },
  route_added: {
    label: 'Route Added',
    color: '#389e0d',
    icon: <ApiOutlined />,
    description: 'A new OpenShift Route was created'
  },
  route_removed: {
    label: 'Route Removed',
    color: '#cf1322',
    icon: <ApiOutlined />,
    description: 'An OpenShift Route was deleted'
  },
  route_changed: {
    label: 'Route Changed',
    color: '#d46b08',
    icon: <ApiOutlined />,
    description: 'OpenShift Route configuration was modified'
  },
  // Anomaly detection types
  traffic_anomaly: {
    label: 'Traffic Anomaly',
    color: '#d4756a',
    icon: <SwapOutlined />,
    description: 'Unusual traffic pattern detected (volume spike, latency increase)'
  },
  dns_anomaly: {
    label: 'DNS Anomaly',
    color: '#0891b2',
    icon: <SwapOutlined />,
    description: 'Unusual DNS activity (new domains, NXDOMAIN spikes)'
  },
  process_anomaly: {
    label: 'Process Anomaly',
    color: '#7c8eb5',
    icon: <SwapOutlined />,
    description: 'Unusual process execution detected'
  },
  error_anomaly: {
    label: 'Error Anomaly',
    color: '#cf1322',
    icon: <SwapOutlined />,
    description: 'Spike in connection errors or retransmits detected'
  },
};

// Risk level configuration
const riskLevelConfig: Record<RiskLevel, { color: string; label: string; icon: React.ReactNode; description: string }> = {
  critical: { 
    color: '#cf1322', 
    label: 'Critical', 
    icon: <ExclamationCircleOutlined />,
    description: 'Immediate attention required - may cause service disruption'
  },
  high: { 
    color: '#c75450', 
    label: 'High', 
    icon: <WarningOutlined />,
    description: 'Significant impact - review and validate as soon as possible'
  },
  medium: { 
    color: '#b89b5d', 
    label: 'Medium', 
    icon: <WarningOutlined />,
    description: 'Moderate impact - monitor for unexpected behavior'
  },
  low: { 
    color: '#4d9f7c', 
    label: 'Low', 
    icon: <CheckCircleOutlined />,
    description: 'Minimal impact - normal operational change'
  },
};

interface ChangeDetailDrawerProps {
  changeId: number | null;
  open: boolean;
  onClose: () => void;
  onViewRelated?: (changeId: number) => void;
}

const { useToken } = theme;

const ChangeDetailDrawer: React.FC<ChangeDetailDrawerProps> = ({
  changeId,
  open,
  onClose,
  onViewRelated,
}) => {
  const { token } = useToken();
  const [activeTab, setActiveTab] = useState<string>('details');
  
  // Fetch change details
  const { data: changeDetails, isLoading, error } = useGetChangeDetailsQuery(changeId!, {
    skip: !changeId || !open,
  });

  // Fetch correlated changes (lazy load)
  // Note: cluster_id is required by the API, skip query if not available
  const hasClusterId = changeDetails?.cluster_id !== undefined;
  const { data: correlatedData, isLoading: correlatedLoading } = useGetCorrelatedChangesQuery(
    { 
      change_id: changeId!, 
      cluster_id: changeDetails?.cluster_id ?? 0, // 0 is placeholder, query will be skipped
      time_window: 30 
    },
    { skip: !changeId || !open || activeTab !== 'correlated' || !changeDetails || !hasClusterId }
  );

  const typeConfig = changeDetails ? changeTypeConfig[changeDetails.change_type] : null;
  const riskConfig = changeDetails ? riskLevelConfig[changeDetails.risk] : null;

  // Parse before/after state if available
  const safeParse = (val: unknown) => {
    if (!val) return null;
    if (typeof val !== 'string') return val;
    try { return JSON.parse(val); } catch { return null; }
  };
  const beforeState = safeParse(changeDetails?.before_state);
  const afterState = safeParse(changeDetails?.after_state);

  return (
    <Drawer
      title={
        <Space>
          <SwapOutlined style={{ color: '#b89b5d' }} />
          <span>Change Details</span>
          {changeDetails && (
            <Tag color={riskConfig?.color}>
              {riskConfig?.icon} {riskConfig?.label}
            </Tag>
          )}
        </Space>
      }
      placement="right"
      width={700}
      open={open}
      onClose={onClose}
      extra={
        changeDetails?.rollback_available && (
          <Tooltip title="Rollback this change (if supported)">
            <Button icon={<RollbackOutlined />} disabled>
              Rollback
            </Button>
          </Tooltip>
        )
      }
    >
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 50 }}>
          <Spin size="large" />
          <Text style={{ display: 'block', marginTop: 16 }}>Loading change details...</Text>
        </div>
      ) : error ? (
        <Alert
          type="error"
          message="Failed to load change details"
          description="The change may have been deleted or you may not have permission to view it."
        />
      ) : !changeDetails ? (
        <Empty description="No change selected" />
      ) : (
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          items={[
            {
              key: 'details',
              label: <span><InfoCircleOutlined /> Details</span>,
              children: (
                <div>
                  {/* Risk Alert */}
                  {(changeDetails.risk === 'critical' || changeDetails.risk === 'high') && (
                    <Alert
                      type={changeDetails.risk === 'critical' ? 'error' : 'warning'}
                      message={`${riskConfig?.label} Risk Change`}
                      description={riskConfig?.description}
                      icon={riskConfig?.icon}
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  {/* Change Type Header */}
                  <Card bordered={false} style={{ marginBottom: 16, background: '#fafafa' }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space>
                        <Tag color={typeConfig?.color || '#8c8c8c'} icon={typeConfig?.icon} style={{ fontSize: 14, padding: '4px 12px' }}>
                          {typeConfig?.label || changeDetails.change_type}
                        </Tag>
                        <Text type="secondary">#{changeDetails.id}</Text>
                      </Space>
                      <Title level={4} style={{ margin: 0 }}>{changeDetails.target}</Title>
                      <Text type="secondary">{typeConfig?.description}</Text>
                    </Space>
                  </Card>

          {/* Basic Information */}
          <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label={<><ClockCircleOutlined /> Detected</>}>
              <Tooltip title={dayjs(changeDetails.timestamp).format('YYYY-MM-DD HH:mm:ss')}>
                {dayjs(changeDetails.timestamp).fromNow()}
              </Tooltip>
            </Descriptions.Item>
            <Descriptions.Item label={<><UserOutlined /> Changed By</>}>
              {changeDetails.changed_by}
            </Descriptions.Item>
            <Descriptions.Item label="Namespace">
              <Tag>{changeDetails.namespace}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Status">
              <Badge 
                status={changeDetails.status === 'new' ? 'processing' : 'default'} 
                text={changeDetails.status || 'new'} 
              />
            </Descriptions.Item>
          </Descriptions>

          {/* Details */}
          <Card title="Details" size="small" style={{ marginBottom: 16 }}>
            <Paragraph>{changeDetails.details || 'No additional details available.'}</Paragraph>
          </Card>

          {/* Impact */}
          <Card title="Impact Assessment" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic
                  title="Affected Services"
                  value={changeDetails.affected_services}
                  valueStyle={{ 
                    color: changeDetails.affected_services > 5 
                      ? '#c75450' 
                      : changeDetails.affected_services > 2 
                        ? '#b89b5d' 
                        : '#4d9f7c' 
                  }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="Risk Level"
                  value={riskConfig?.label}
                  valueStyle={{ color: riskConfig?.color }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="Blast Radius"
                  value={
                    changeDetails.affected_services > 10 ? 'Wide' :
                    changeDetails.affected_services > 5 ? 'Medium' :
                    changeDetails.affected_services > 0 ? 'Limited' : 'None'
                  }
                  valueStyle={{ 
                    color: changeDetails.affected_services > 10 ? '#c75450' : '#4d9f7c' 
                  }}
                />
              </Col>
            </Row>
          </Card>

          {/* Before/After Comparison */}
          {(beforeState || afterState) && (
            <Card title="State Comparison" size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <div style={{ background: token.colorErrorBg, padding: 12, borderRadius: 4 }}>
                    <Text strong style={{ color: token.colorError }}>Before</Text>
                    <pre style={{ fontSize: 11, margin: '8px 0 0', overflow: 'auto', maxHeight: 150 }}>
                      {beforeState ? JSON.stringify(beforeState, null, 2) : 'N/A'}
                    </pre>
                  </div>
                </Col>
                <Col span={12}>
                  <div style={{ background: '#f6ffed', padding: 12, borderRadius: 4 }}>
                    <Text strong style={{ color: '#4d9f7c' }}>After</Text>
                    <pre style={{ fontSize: 11, margin: '8px 0 0', overflow: 'auto', maxHeight: 150 }}>
                      {afterState ? JSON.stringify(afterState, null, 2) : 'N/A'}
                    </pre>
                  </div>
                </Col>
              </Row>
            </Card>
          )}

          {/* Audit Trail */}
          {changeDetails.audit_trail && changeDetails.audit_trail.length > 0 && (
            <>
              <Divider><HistoryOutlined /> Audit Trail</Divider>
              <Timeline
                items={changeDetails.audit_trail.map((entry: any, index: number) => ({
                  key: index,
                  color: entry.action === 'detected' ? 'blue' : 
                         entry.action === 'acknowledged' ? 'green' : 'gray',
                  children: (
                    <div>
                      <Text strong style={{ textTransform: 'capitalize' }}>{entry.action}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(entry.timestamp).format('YYYY-MM-DD HH:mm:ss')} • {entry.actor}
                      </Text>
                    </div>
                  ),
                }))}
              />
            </>
          )}

          {/* Related Changes */}
          {changeDetails.related_changes && changeDetails.related_changes.length > 0 && (
            <>
              <Divider><LinkOutlined /> Related Changes</Divider>
              <Space direction="vertical" style={{ width: '100%' }}>
                {changeDetails.related_changes.map((related: Change) => (
                  <Card 
                    key={related.id} 
                    size="small" 
                    hoverable
                    onClick={() => onViewRelated?.(related.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <Space>
                      <Tag color={changeTypeConfig[related.change_type]?.color || '#8c8c8c'}>
                        {changeTypeConfig[related.change_type]?.label || related.change_type}
                      </Tag>
                      <Text>{related.target}</Text>
                      <ArrowRightOutlined style={{ color: '#999' }} />
                    </Space>
                  </Card>
                ))}
              </Space>
            </>
          )}

                  {/* Metadata */}
                  {changeDetails.metadata && Object.keys(changeDetails.metadata).length > 0 && (
                    <>
                      <Divider>Additional Metadata</Divider>
                      <Descriptions column={1} size="small" bordered>
                        {Object.entries(changeDetails.metadata).map(([key, value]) => (
                          <Descriptions.Item key={key} label={key}>
                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    </>
                  )}
                </div>
              ),
            },
            {
              key: 'impact',
              label: <span><ApartmentOutlined /> Impact Summary</span>,
              children: (
                <ChangeImpactSummary
                  changeType={changeDetails.change_type}
                  target={changeDetails.target}
                  namespace={changeDetails.namespace}
                  affectedServices={changeDetails.affected_services}
                  riskLevel={changeDetails.risk as 'critical' | 'high' | 'medium' | 'low'}
                  analysisId={changeDetails.analysis_id}
                  clusterId={changeDetails.cluster_id}
                />
              ),
            },
            {
              key: 'correlated',
              label: (
                <span>
                  <LinkOutlined /> Correlated
                  {correlatedData?.total_correlated ? (
                    <Badge 
                      count={correlatedData.total_correlated} 
                      size="small" 
                      style={{ marginLeft: 4 }} 
                    />
                  ) : null}
                </span>
              ),
              children: correlatedLoading ? (
                <div style={{ textAlign: 'center', padding: 50 }}>
                  <Spin />
                  <Text style={{ display: 'block', marginTop: 16 }}>Finding correlated changes...</Text>
                </div>
              ) : !correlatedData?.correlated_changes?.length ? (
                <Empty description="No correlated changes found within the time window" />
              ) : (
                <div>
                  <Alert
                    type="info"
                    message={`Found ${correlatedData.total_correlated} correlated changes`}
                    description={`Within ${correlatedData.time_window_minutes} minutes of this change`}
                    style={{ marginBottom: 16 }}
                  />
                  
                  <Space style={{ marginBottom: 16 }}>
                    <Tag color="blue">Same Source: {correlatedData.correlation_types.same_source}</Tag>
                    <Tag color="green">Same Namespace: {correlatedData.correlation_types.same_namespace}</Tag>
                    <Tag color="orange">Time Proximity: {correlatedData.correlation_types.time_proximity}</Tag>
                  </Space>
                  
                  <Timeline
                    items={correlatedData.correlated_changes.map((change) => ({
                      key: change.id,
                      color: change.correlation_type === 'same_source' ? 'blue' : 
                             change.correlation_type === 'same_namespace' ? 'green' : 'orange',
                      children: (
                        <Card 
                          size="small" 
                          hoverable
                          onClick={() => onViewRelated?.(change.id)}
                          style={{ cursor: 'pointer' }}
                        >
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              <Tag color={changeTypeConfig[change.change_type]?.color}>
                                {changeTypeConfig[change.change_type]?.label}
                              </Tag>
                              <Tag>{change.correlation_type.replace('_', ' ')}</Tag>
                            </Space>
                            <Text strong>{change.target}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {change.namespace} • {change.changed_by} • {dayjs(change.timestamp).format('HH:mm:ss')}
                            </Text>
                          </Space>
                        </Card>
                      ),
                    }))}
                  />
                </div>
              ),
            },
          ]}
        />
      )}
    </Drawer>
  );
};

export default ChangeDetailDrawer;
