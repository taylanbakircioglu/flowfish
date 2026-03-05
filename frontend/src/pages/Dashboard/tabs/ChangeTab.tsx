import React, { useMemo, useState } from 'react';
import { 
  Row, 
  Col, 
  Card, 
  Statistic, 
  Typography, 
  Tag, 
  Space, 
  List,
  Progress,
  Empty,
  Spin,
  Timeline,
  Alert,
  Tooltip,
  theme,
  Segmented,
  Badge
} from 'antd';
import { 
  SwapOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
  EditOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  ApiOutlined,
  CloudServerOutlined,
  RiseOutlined,
  FallOutlined,
  HistoryOutlined,
  FieldTimeOutlined,
  FireOutlined,
  DisconnectOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetChangesQuery, useGetChangeStatsSummaryQuery, Change, ChangeType, RiskLevel } from '../../../store/api/changesApi';
import { useTheme } from '../../../contexts/ThemeContext';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';
import DonutChart from '../components/DonutChart';

dayjs.extend(relativeTime);

const { Text } = Typography;
const { useToken } = theme;

interface ChangeTabProps {
  clusterId?: number;
  analysisId?: number;
}

// Change types configuration
const changeTypeConfig: Record<ChangeType, { label: string; color: string; icon: React.ReactNode }> = {
  // Legacy types
  workload_added: { label: 'Workload Added', color: '#4caf50', icon: <PlusCircleOutlined /> },
  workload_removed: { label: 'Workload Removed', color: '#e05252', icon: <MinusCircleOutlined /> },
  namespace_changed: { label: 'Namespace Changed', color: '#a67c9e', icon: <SwapOutlined /> },
  // Infrastructure changes - Workloads
  replica_changed: { label: 'Replica Changed', color: '#c9a55a', icon: <SwapOutlined /> },
  config_changed: { label: 'Config Changed', color: '#22a6a6', icon: <EditOutlined /> },
  image_changed: { label: 'Image Changed', color: '#9254de', icon: <EditOutlined /> },
  label_changed: { label: 'Label Changed', color: '#597ef7', icon: <EditOutlined /> },
  resource_changed: { label: 'Resource Changed', color: '#d48806', icon: <EditOutlined /> },
  env_changed: { label: 'Env Changed', color: '#13c2c2', icon: <EditOutlined /> },
  spec_changed: { label: 'Spec Changed', color: '#722ed1', icon: <EditOutlined /> },
  // Infrastructure changes - Services
  service_port_changed: { label: 'Service Port Changed', color: '#eb2f96', icon: <ApiOutlined /> },
  service_selector_changed: { label: 'Selector Changed', color: '#f5222d', icon: <ApiOutlined /> },
  service_type_changed: { label: 'Service Type Changed', color: '#fa8c16', icon: <ApiOutlined /> },
  service_added: { label: 'Service Added', color: '#52c41a', icon: <PlusCircleOutlined /> },
  service_removed: { label: 'Service Removed', color: '#ff4d4f', icon: <MinusCircleOutlined /> },
  // Infrastructure changes - Network/Ingress/Route
  network_policy_added: { label: 'NetPolicy Added', color: '#2f54eb', icon: <PlusCircleOutlined /> },
  network_policy_removed: { label: 'NetPolicy Removed', color: '#ff7a45', icon: <MinusCircleOutlined /> },
  network_policy_changed: { label: 'NetPolicy Changed', color: '#1d39c4', icon: <EditOutlined /> },
  ingress_added: { label: 'Ingress Added', color: '#36cfc9', icon: <PlusCircleOutlined /> },
  ingress_removed: { label: 'Ingress Removed', color: '#f759ab', icon: <MinusCircleOutlined /> },
  ingress_changed: { label: 'Ingress Changed', color: '#08979c', icon: <EditOutlined /> },
  route_added: { label: 'Route Added', color: '#73d13d', icon: <PlusCircleOutlined /> },
  route_removed: { label: 'Route Removed', color: '#cf1322', icon: <MinusCircleOutlined /> },
  route_changed: { label: 'Route Changed', color: '#389e0d', icon: <EditOutlined /> },
  // Connection changes
  connection_added: { label: 'Connection Added', color: '#0891b2', icon: <PlusCircleOutlined /> },
  port_changed: { label: 'Port Changed', color: '#7c8eb5', icon: <EditOutlined /> },
  // Anomaly types
  connection_removed: { label: 'Connection Anomaly', color: '#c75450', icon: <DisconnectOutlined /> },
  traffic_anomaly: { label: 'Traffic Anomaly', color: '#d4756a', icon: <ExclamationCircleOutlined /> },
  dns_anomaly: { label: 'DNS Anomaly', color: '#0891b2', icon: <ExclamationCircleOutlined /> },
  process_anomaly: { label: 'Process Anomaly', color: '#7c8eb5', icon: <ExclamationCircleOutlined /> },
  error_anomaly: { label: 'Error Anomaly', color: '#cf1322', icon: <ExclamationCircleOutlined /> },
};

// Risk levels configuration
const riskLevelConfig: Record<RiskLevel, { color: string; label: string }> = {
  critical: { color: '#cf1322', label: 'Critical' },
  high: { color: '#e05252', label: 'High' },
  medium: { color: '#d4a844', label: 'Medium' },
  low: { color: '#4caf50', label: 'Low' },
};

const ChangeTab: React.FC<ChangeTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  const [viewMode, setViewMode] = useState<string>('timeline');
  const cardBg = isDark ? '#262626' : '#fafbfc';
  
  // API Queries
  const { data: changesData, isLoading: changesLoading } = useGetChangesQuery(
    { 
      cluster_id: clusterId!, 
      analysis_id: analysisId,
      limit: 50 
    },
    { skip: !clusterId }
  );

  const { data: statsSummary, isLoading: statsLoading } = useGetChangeStatsSummaryQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, days: 7 },
    { skip: !clusterId }
  );

  const changes = changesData?.changes || [];
  const stats = changesData?.stats;
  const comparison = changesData?.comparison;

  // Compute stats
  const computedStats = useMemo(() => {
    const byType = stats?.by_type || {};
    const byRisk = stats?.by_risk || {};
    
    const addTypes = ['workload_added', 'connection_added', 'service_added', 'network_policy_added', 'ingress_added', 'route_added'];
    const removeTypes = ['workload_removed', 'service_removed', 'network_policy_removed', 'ingress_removed', 'route_removed'];
    
    return {
      total: stats?.total_changes || 0,
      additions: addTypes.reduce((sum, t) => sum + (byType[t] || 0), 0),
      removals: removeTypes.reduce((sum, t) => sum + (byType[t] || 0), 0),
      modifications: (stats?.total_changes || 0) - addTypes.reduce((sum, t) => sum + (byType[t] || 0), 0) - removeTypes.reduce((sum, t) => sum + (byType[t] || 0), 0),
      critical: byRisk.critical || 0,
      high: byRisk.high || 0,
      medium: byRisk.medium || 0,
      low: byRisk.low || 0,
    };
  }, [stats]);

  const isLoading = changesLoading || statsLoading;

  // Change type donut data
  const changeTypeDonutData = useMemo(() => {
    if (!stats?.by_type) return [];
    return Object.entries(stats.by_type)
      .map(([type, count]) => ({
        label: changeTypeConfig[type as ChangeType]?.label || type,
        value: count as number,
        color: changeTypeConfig[type as ChangeType]?.color || '#8c8c8c',
      }));
  }, [stats]);

  // Risk donut data
  const riskDonutData = useMemo(() => {
    if (!stats?.by_risk) return [];
    return Object.entries(stats.by_risk)
      .map(([risk, count]) => ({
        label: riskLevelConfig[risk as RiskLevel]?.label || risk,
        value: count as number,
        color: riskLevelConfig[risk as RiskLevel]?.color || '#8c8c8c',
      }));
  }, [stats]);

  // Timeline items
  const timelineItems = useMemo(() => {
    return changes.slice(0, 15).map((change: Change) => {
      const typeConfig = changeTypeConfig[change.change_type];
      const riskConfig = riskLevelConfig[change.risk];
      
      return {
        key: change.id,
        color: riskConfig?.color || '#8c8c8c',
        dot: typeConfig?.icon,
        children: (
          <div style={{ paddingBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Space>
                <Tag color={typeConfig?.color} style={{ fontSize: 10 }}>{typeConfig?.label}</Tag>
                <Tag color={riskConfig?.color} style={{ fontSize: 10 }}>{riskConfig?.label}</Tag>
              </Space>
              <Text type="secondary" style={{ fontSize: 10 }}>
                {dayjs(change.timestamp).format('MM-DD HH:mm')}
              </Text>
            </div>
            <div style={{ marginTop: 4 }}>
              <Text strong style={{ fontSize: 12 }}>{change.target}</Text>
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>({change.namespace})</Text>
            </div>
            <Tooltip title={change.details}>
              <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                {change.details}
              </Text>
            </Tooltip>
          </div>
        ),
      };
    });
  }, [changes]);

  if (!clusterId) {
    return <Empty description="Select a cluster to view change data" />;
  }

  return (
    <div>
      {/* View Mode Selector */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          {computedStats.critical > 0 && (
            <Tag color="red" icon={<FireOutlined />}>
              {computedStats.critical} Critical Changes
            </Tag>
          )}
        </Space>
        <Segmented
          value={viewMode}
          onChange={(value) => setViewMode(value as string)}
          options={[
            { label: 'Timeline', value: 'timeline', icon: <HistoryOutlined /> },
            { label: 'Summary', value: 'summary', icon: <FieldTimeOutlined /> },
          ]}
          size="small"
        />
      </div>

      {/* Top Stats Row - Animated */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="Total Changes"
            value={computedStats.total}
            icon={<SwapOutlined />}
            color="#d4a844"
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="Additions"
            value={computedStats.additions}
            icon={<PlusCircleOutlined />}
            color="#4caf50"
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="Removals"
            value={computedStats.removals}
            icon={<MinusCircleOutlined />}
            color="#e05252"
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="Modifications"
            value={computedStats.modifications}
            icon={<EditOutlined />}
            color="#0891b2"
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="Critical"
            value={computedStats.critical}
            icon={<ExclamationCircleOutlined />}
            color={computedStats.critical > 0 ? '#e57373' : '#2eb8b8'}
            loading={isLoading}
            pulseEffect={computedStats.critical > 0}
          />
        </Col>

        <Col xs={24} sm={12} lg={4}>
          <AnimatedStatCard
            title="High Risk"
            value={computedStats.high}
            icon={<WarningOutlined />}
            color={computedStats.high > 0 ? '#e05252' : '#8c8c8c'}
            loading={isLoading}
          />
        </Col>
      </Row>

      {/* Alert for critical changes */}
      {computedStats.critical > 0 && (
        <Alert
          message="Critical Changes Detected"
          description={`${computedStats.critical} critical change(s) require immediate attention.`}
          type="error"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}

      {/* Comparison Cards & Distribution */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Before/After Comparison */}
        {comparison && (
          <>
            <Col xs={24} lg={6}>
              <Card 
                title={
                  <Space>
                    <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                    <span style={{ fontSize: 13 }}>Before</span>
                  </Space>
                }
                bordered={false}
                size="small"
              >
                <Row gutter={[8, 8]}>
                  <Col span={12}>
                    <Statistic 
                      title={<span style={{ fontSize: 11 }}>Workloads</span>}
                      value={comparison.before?.workloads || 0} 
                      prefix={<CloudServerOutlined style={{ fontSize: 14 }} />}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic 
                      title={<span style={{ fontSize: 11 }}>Connections</span>}
                      value={comparison.before?.connections || 0} 
                      prefix={<ApiOutlined style={{ fontSize: 14 }} />}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                </Row>
              </Card>
            </Col>

            <Col xs={24} lg={6}>
              <Card 
                title={
                  <Space>
                    <ClockCircleOutlined style={{ color: '#0891b2' }} />
                    <span style={{ fontSize: 13 }}>After</span>
                  </Space>
                }
                bordered={false}
                size="small"
              >
                <Row gutter={[8, 8]}>
                  <Col span={12}>
                    <Statistic 
                      title={<span style={{ fontSize: 11 }}>Workloads</span>}
                      value={comparison.after?.workloads || 0} 
                      prefix={<CloudServerOutlined style={{ fontSize: 14 }} />}
                      valueStyle={{ fontSize: 18 }}
                      suffix={
                        comparison.after?.workloads !== comparison.before?.workloads && (
                          <span style={{ 
                            fontSize: 12, 
                            color: (comparison.after?.workloads || 0) > (comparison.before?.workloads || 0) ? '#4caf50' : '#e05252' 
                          }}>
                            {(comparison.after?.workloads || 0) > (comparison.before?.workloads || 0) ? (
                              <><RiseOutlined /> +{(comparison.after?.workloads || 0) - (comparison.before?.workloads || 0)}</>
                            ) : (
                              <><FallOutlined /> {(comparison.after?.workloads || 0) - (comparison.before?.workloads || 0)}</>
                            )}
                          </span>
                        )
                      }
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic 
                      title={<span style={{ fontSize: 11 }}>Connections</span>}
                      value={comparison.after?.connections || 0} 
                      prefix={<ApiOutlined style={{ fontSize: 14 }} />}
                      valueStyle={{ fontSize: 18 }}
                      suffix={
                        comparison.after?.connections !== comparison.before?.connections && (
                          <span style={{ 
                            fontSize: 12, 
                            color: (comparison.after?.connections || 0) > (comparison.before?.connections || 0) ? '#4caf50' : '#e05252' 
                          }}>
                            {(comparison.after?.connections || 0) > (comparison.before?.connections || 0) ? (
                              <><RiseOutlined /> +{(comparison.after?.connections || 0) - (comparison.before?.connections || 0)}</>
                            ) : (
                              <><FallOutlined /> {(comparison.after?.connections || 0) - (comparison.before?.connections || 0)}</>
                            )}
                          </span>
                        )
                      }
                    />
                  </Col>
                </Row>
              </Card>
            </Col>
          </>
        )}

        {/* Change Type Distribution */}
        <Col xs={24} lg={comparison ? 12 : 24}>
          <Card 
            title={
              <Space>
                <SwapOutlined style={{ color: '#d4a844' }} />
                <span>Change Distribution</span>
              </Space>
            }
            bordered={false}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : stats?.by_type && Object.keys(stats.by_type).length > 0 ? (
              <Row gutter={[16, 8]}>
                {Object.entries(stats.by_type)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .map(([type, count]) => {
                    const config = changeTypeConfig[type as ChangeType];
                    const total = computedStats.total || 1;
                    const percent = ((count as number) / total * 100);
                    return (
                      <Col xs={24} sm={12} key={type}>
                        <div style={{ marginBottom: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <Space>
                              {config?.icon}
                              <Text style={{ fontSize: 12 }}>{config?.label || type}</Text>
                            </Space>
                            <Text style={{ fontSize: 12 }}>{count as number}</Text>
                          </div>
                          <Progress 
                            percent={percent} 
                            showInfo={false}
                            strokeColor={config?.color || '#8c8c8c'}
                            size="small"
                          />
                        </div>
                      </Col>
                    );
                  })}
              </Row>
            ) : (
              <Empty description="No changes detected" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Risk Distribution & Timeline - Conditional Views */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {viewMode === 'summary' ? (
          <>
            {/* Change Type Donut */}
            <Col xs={24} lg={12}>
              <Card 
                title={
                  <Space>
                    <SwapOutlined style={{ color: '#d4a844' }} />
                    <span>Change Types</span>
                  </Space>
                }
                bordered={false}
              >
                {isLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : changeTypeDonutData.length > 0 ? (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                    <DonutChart
                      data={changeTypeDonutData}
                      size={200}
                      thickness={28}
                      centerValue={computedStats.total}
                      centerLabel="Total Changes"
                      animated={true}
                    />
                  </div>
                ) : (
                  <Empty description="No changes" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>

            {/* Risk Donut */}
            <Col xs={24} lg={12}>
              <Card 
                title={
                  <Space>
                    <WarningOutlined style={{ color: '#e05252' }} />
                    <span>Risk Breakdown</span>
                  </Space>
                }
                bordered={false}
              >
                {isLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : riskDonutData.length > 0 ? (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                    <DonutChart
                      data={riskDonutData}
                      size={200}
                      thickness={28}
                      centerValue={computedStats.critical + computedStats.high}
                      centerLabel="High Risk"
                      animated={true}
                    />
                  </div>
                ) : (
                  <Empty description="No risk data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </>
        ) : (
          <>
            {/* Risk Distribution - Enhanced */}
            <Col xs={24} lg={8}>
              <Card 
                title={
                  <Space>
                    <WarningOutlined style={{ color: '#e05252' }} />
                    <span>Risk Distribution</span>
                  </Space>
                }
                bordered={false}
                style={{ height: '100%' }}
              >
                {isLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : (
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    {['critical', 'high', 'medium', 'low'].map(risk => {
                      const count = stats?.by_risk?.[risk] || 0;
                      const total = computedStats.total || 1;
                      const percent = (count / total) * 100;
                      const config = riskLevelConfig[risk as RiskLevel];
                      return (
                        <div 
                          key={risk}
                          style={{
                            padding: '8px 12px',
                            background: count > 0 ? `${config?.color}10` : 'transparent',
                            borderRadius: 8,
                            borderLeft: `3px solid ${config?.color}`,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <Tag color={config?.color} style={{ margin: 0, fontSize: 10 }}>{config?.label}</Tag>
                            <Text strong style={{ fontSize: 16, color: count > 0 ? config?.color : undefined }}>
                              {count}
                            </Text>
                          </div>
                          <Progress 
                            percent={percent} 
                            showInfo={false}
                            strokeColor={config?.color}
                            size="small"
                          />
                        </div>
                      );
                    })}
                  </Space>
                )}
              </Card>
            </Col>

            {/* Recent Changes Timeline - Enhanced */}
            <Col xs={24} lg={16}>
              <Card 
                title={
                  <Space>
                    <ClockCircleOutlined style={{ color: '#0891b2' }} />
                    <span>Recent Changes Timeline</span>
                  </Space>
                }
                bordered={false}
                bodyStyle={{ maxHeight: 400, overflow: 'auto' }}
                extra={
                  <Badge count={changes.length} style={{ backgroundColor: '#0891b2' }} />
                }
              >
                {isLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : changes.length > 0 ? (
                  <div style={{ position: 'relative', paddingLeft: 20 }}>
                    {/* Timeline line */}
                    <div style={{
                      position: 'absolute',
                      left: 8,
                      top: 0,
                      bottom: 0,
                      width: 2,
                      background: `linear-gradient(180deg, ${token.colorPrimary} 0%, ${token.colorBorderSecondary} 100%)`,
                      borderRadius: 1,
                    }} />
                    
                    {changes.slice(0, 15).map((change: Change, index: number) => {
                      const typeConfig = changeTypeConfig[change.change_type];
                      const riskConfig = riskLevelConfig[change.risk];
                      
                      return (
                        <div 
                          key={change.id || index}
                          style={{
                            position: 'relative',
                            paddingLeft: 24,
                            paddingBottom: 16,
                          }}
                        >
                          {/* Timeline dot */}
                          <div style={{
                            position: 'absolute',
                            left: -14,
                            top: 4,
                            width: 14,
                            height: 14,
                            borderRadius: '50%',
                            background: riskConfig?.color || '#8c8c8c',
                            border: `2px solid ${token.colorBgContainer}`,
                            boxShadow: `0 0 0 2px ${riskConfig?.color}30`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}>
                            <span style={{ color: token.colorTextLightSolid, fontSize: 8 }}>
                              {typeConfig?.icon}
                            </span>
                          </div>
                          
                          <div style={{
                            background: token.colorBgLayout,
                            borderRadius: 8,
                            padding: '10px 12px',
                            borderLeft: `3px solid ${riskConfig?.color}`,
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <Space size={4}>
                                <Tag color={typeConfig?.color} style={{ fontSize: 9, margin: 0 }}>
                                  {typeConfig?.label}
                                </Tag>
                                <Tag color={riskConfig?.color} style={{ fontSize: 9, margin: 0 }}>
                                  {riskConfig?.label}
                                </Tag>
                              </Space>
                              <Text type="secondary" style={{ fontSize: 10 }}>
                                {dayjs(change.timestamp).format('MM-DD HH:mm')}
                              </Text>
                            </div>
                            <Text strong style={{ fontSize: 12 }}>{change.target}</Text>
                            <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
                              ({change.namespace})
                            </Text>
                            <Tooltip title={change.details}>
                              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }} ellipsis>
                                {change.details}
                              </Text>
                            </Tooltip>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <Empty description="No changes recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </>
        )}
      </Row>

      {/* Namespace Changes */}
      {stats?.by_namespace && Object.keys(stats.by_namespace).length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card 
              title={
                <Space>
                  <CloudServerOutlined style={{ color: '#7c8eb5' }} />
                  <span>Changes by Namespace</span>
                </Space>
              }
              bordered={false}
            >
              <Row gutter={[16, 16]}>
                {Object.entries(stats.by_namespace)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .slice(0, 8)
                  .map(([namespace, count], index) => (
                    <Col xs={12} sm={8} md={6} lg={3} key={namespace}>
                      <Card size="small" style={{ textAlign: 'center', background: token.colorBgLayout }}>
                        <Text strong style={{ fontSize: 18, color: '#7c8eb5' }}>
                          {count as number}
                        </Text>
                        <br />
                        <Tooltip title={namespace}>
                          <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                            {namespace}
                          </Text>
                        </Tooltip>
                      </Card>
                    </Col>
                  ))}
              </Row>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
};

export default ChangeTab;

