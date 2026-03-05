/**
 * ChangeAnalytics - Analytics Dashboard for Change Detection
 * 
 * Features:
 * - Velocity Chart: Changes over time (line/area chart)
 * - Type Distribution: Breakdown by change type (pie chart)
 * - Risk Distribution: Breakdown by risk level
 * - Top Workloads: Most frequently changed workloads
 * - Namespace Distribution: Changes by namespace
 */

import React, { useMemo } from 'react';
import {
  Card,
  Row,
  Col,
  Typography,
  Table,
  Tag,
  Progress,
  Space,
  Empty,
  Statistic,
  Tooltip,
} from 'antd';
import {
  LineChartOutlined,
  PieChartOutlined,
  BarChartOutlined,
  TrophyOutlined,
  RiseOutlined,
  FallOutlined,
  CloudServerOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Change, ChangeStats, SnapshotComparison } from '../store/api/changesApi';

const { Title, Text } = Typography;

// Change type config - organized by category
const changeTypeConfig: Record<string, { label: string; color: string }> = {
  // Legacy types
  workload_added: { label: 'Workload Added', color: '#4d9f7c' },
  workload_removed: { label: 'Workload Removed', color: '#c75450' },
  namespace_changed: { label: 'Namespace Changed', color: '#a67c9e' },
  // Infrastructure changes - Workloads (K8s API)
  replica_changed: { label: 'Replica Changed', color: '#c9a55a' },
  config_changed: { label: 'Config Changed', color: '#22a6a6' },
  image_changed: { label: 'Image Changed', color: '#9254de' },
  label_changed: { label: 'Label Changed', color: '#597ef7' },
  resource_changed: { label: 'Resource Changed', color: '#d48806' },
  env_changed: { label: 'Env Changed', color: '#13c2c2' },
  spec_changed: { label: 'Spec Changed', color: '#722ed1' },
  // Infrastructure changes - Services (K8s API)
  service_port_changed: { label: 'Service Port Changed', color: '#eb2f96' },
  service_selector_changed: { label: 'Selector Changed', color: '#f5222d' },
  service_type_changed: { label: 'Service Type Changed', color: '#fa8c16' },
  service_added: { label: 'Service Added', color: '#52c41a' },
  service_removed: { label: 'Service Removed', color: '#ff4d4f' },
  // Infrastructure changes - Network/Ingress/Route (K8s API)
  network_policy_added: { label: 'NetPolicy Added', color: '#2f54eb' },
  network_policy_removed: { label: 'NetPolicy Removed', color: '#ff7a45' },
  network_policy_changed: { label: 'NetPolicy Changed', color: '#1d39c4' },
  ingress_added: { label: 'Ingress Added', color: '#36cfc9' },
  ingress_removed: { label: 'Ingress Removed', color: '#f759ab' },
  ingress_changed: { label: 'Ingress Changed', color: '#08979c' },
  route_added: { label: 'Route Added', color: '#73d13d' },
  route_removed: { label: 'Route Removed', color: '#cf1322' },
  route_changed: { label: 'Route Changed', color: '#389e0d' },
  // Connection changes (eBPF)
  connection_added: { label: 'Connection Added', color: '#0891b2' },
  port_changed: { label: 'Port Changed', color: '#7c8eb5' },
  // Anomaly detection (eBPF)
  connection_removed: { label: 'Connection Anomaly', color: '#c75450' },
  traffic_anomaly: { label: 'Traffic Anomaly', color: '#d4756a' },
  dns_anomaly: { label: 'DNS Anomaly', color: '#0891b2' },
  process_anomaly: { label: 'Process Anomaly', color: '#7c8eb5' },
  error_anomaly: { label: 'Error Anomaly', color: '#cf1322' },
};

// Risk level config
const riskLevelConfig: Record<string, { label: string; color: string }> = {
  critical: { label: 'Critical', color: '#cf1322' },
  high: { label: 'High', color: '#c75450' },
  medium: { label: 'Medium', color: '#b89b5d' },
  low: { label: 'Low', color: '#4d9f7c' },
};

interface ChangeAnalyticsProps {
  changes: Change[];
  stats?: ChangeStats;
  comparison?: SnapshotComparison;
  dateRange?: [dayjs.Dayjs, dayjs.Dayjs] | null;
  loading?: boolean;
}

const ChangeAnalytics: React.FC<ChangeAnalyticsProps> = ({
  changes,
  stats,
  comparison,
  dateRange,
  loading = false,
}) => {
  // Calculate daily velocity
  const velocityData = useMemo(() => {
    const dailyCounts: Record<string, number> = {};
    
    changes.forEach(change => {
      const day = dayjs(change.timestamp).format('YYYY-MM-DD');
      dailyCounts[day] = (dailyCounts[day] || 0) + 1;
    });
    
    // Sort by date
    const sortedDays = Object.keys(dailyCounts).sort();
    
    return sortedDays.map(day => ({
      date: day,
      count: dailyCounts[day],
      label: dayjs(day).format('MM/DD'),
    }));
  }, [changes]);

  // Calculate top workloads
  const topWorkloads = useMemo(() => {
    const workloadCounts: Record<string, { count: number; namespace: string; types: Set<string> }> = {};
    
    changes.forEach(change => {
      const key = change.target;
      if (!workloadCounts[key]) {
        workloadCounts[key] = { count: 0, namespace: change.namespace, types: new Set() };
      }
      workloadCounts[key].count += 1;
      workloadCounts[key].types.add(change.change_type);
    });
    
    return Object.entries(workloadCounts)
      .map(([name, data]) => ({
        name,
        namespace: data.namespace,
        count: data.count,
        types: Array.from(data.types),
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [changes]);

  // Calculate namespace distribution - prefer server-side stats when available
  const namespaceData = useMemo(() => {
    const nsCounts: Record<string, number> = stats?.by_namespace && Object.keys(stats.by_namespace).length > 0
      ? { ...stats.by_namespace }
      : {};
    
    if (Object.keys(nsCounts).length === 0) {
      changes.forEach(change => {
        nsCounts[change.namespace] = (nsCounts[change.namespace] || 0) + 1;
      });
    }
    
    const total = Object.values(nsCounts).reduce((s, c) => s + c, 0) || 1;
    return Object.entries(nsCounts)
      .map(([namespace, count]) => ({
        namespace,
        count,
        percent: Math.round((count / total) * 100),
      }))
      .sort((a, b) => b.count - a.count);
  }, [changes, stats]);

  // Calculate trend (compare first half vs second half)
  const trend = useMemo(() => {
    if (changes.length < 2) return { direction: 'stable', percent: 0 };
    
    const sorted = [...changes].sort((a, b) => 
      dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix()
    );
    const mid = Math.floor(sorted.length / 2);
    const firstHalf = sorted.slice(0, mid).length;
    const secondHalf = sorted.slice(mid).length;
    
    if (firstHalf === 0) return { direction: 'up', percent: 100 };
    
    const change = ((secondHalf - firstHalf) / firstHalf) * 100;
    return {
      direction: change > 0 ? 'up' : change < 0 ? 'down' : 'stable',
      percent: Math.abs(Math.round(change)),
    };
  }, [changes]);

  // Risk score calculation
  const riskScore = useMemo(() => {
    if (!stats?.by_risk) return 0;
    
    const weights = { critical: 40, high: 25, medium: 10, low: 2 };
    let score = 0;
    let total = 0;
    
    Object.entries(stats.by_risk).forEach(([risk, count]) => {
      score += (weights[risk as keyof typeof weights] || 0) * count;
      total += count;
    });
    
    return total > 0 ? Math.min(100, Math.round(score / total)) : 0;
  }, [stats]);

  const hasStatsData = stats && (
    (stats.by_type && Object.keys(stats.by_type).length > 0) ||
    (stats.by_risk && Object.keys(stats.by_risk).length > 0)
  );
  
  if (!changes.length && !hasStatsData && !loading) {
    return (
      <Card bordered={false}>
        <Empty description="No change data available for analytics" />
      </Card>
    );
  }

  return (
    <div>
      {/* Summary Row */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Change Velocity"
              value={velocityData.length > 0 
                ? (changes.length / velocityData.length).toFixed(1) 
                : 0
              }
              suffix="per day"
              prefix={<LineChartOutlined style={{ color: '#0891b2' }} />}
            />
            <div style={{ marginTop: 8 }}>
              {trend.direction === 'up' ? (
                <Text type="danger"><RiseOutlined /> {trend.percent}% increase</Text>
              ) : trend.direction === 'down' ? (
                <Text type="success"><FallOutlined /> {trend.percent}% decrease</Text>
              ) : (
                <Text type="secondary">Stable</Text>
              )}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Risk Score"
              value={riskScore}
              suffix="/ 100"
              valueStyle={{ 
                color: riskScore > 60 ? '#cf1322' : 
                       riskScore > 30 ? '#b89b5d' : '#4d9f7c' 
              }}
              prefix={<WarningOutlined />}
            />
            <Progress 
              percent={riskScore} 
              size="small" 
              strokeColor={
                riskScore > 60 ? '#cf1322' : 
                riskScore > 30 ? '#b89b5d' : '#4d9f7c'
              }
              showInfo={false}
              style={{ marginTop: 8 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Active Workloads"
              value={topWorkloads.length}
              prefix={<CloudServerOutlined style={{ color: '#7c8eb5' }} />}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              With recent changes
            </Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Namespaces Affected"
              value={namespaceData.length}
              prefix={<BarChartOutlined style={{ color: '#22a6a6' }} />}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              With changes
            </Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {/* Velocity Chart (Simple ASCII-style) */}
        <Col span={12}>
          <Card 
            title={<><LineChartOutlined /> Change Velocity</>}
            bordered={false}
            bodyStyle={{ minHeight: 200 }}
          >
            {velocityData.length > 0 ? (
              <div style={{ display: 'flex', alignItems: 'flex-end', height: 160, gap: 4 }}>
                {velocityData.slice(-14).map((day, index) => {
                  const maxCount = Math.max(...velocityData.map(d => d.count));
                  const height = maxCount > 0 ? (day.count / maxCount) * 140 : 0;
                  
                  return (
                    <Tooltip key={index} title={`${day.date}: ${day.count} changes`}>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <div 
                          style={{ 
                            width: '100%', 
                            height: Math.max(height, 4),
                            background: 'linear-gradient(180deg, #0891b2 0%, #69c0ff 100%)',
                            borderRadius: '4px 4px 0 0',
                            minHeight: 4,
                          }} 
                        />
                        <Text type="secondary" style={{ fontSize: 10, marginTop: 4 }}>
                          {day.label}
                        </Text>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            ) : (
              <Empty description="No velocity data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Type Distribution */}
        <Col span={12}>
          <Card 
            title={<><PieChartOutlined /> Change Type Distribution</>}
            bordered={false}
          >
            {stats?.by_type && Object.keys(stats.by_type).length > 0 ? (
              <div>
                {(() => {
                  const typeTotal = Object.values(stats.by_type).reduce((s, c) => s + c, 0) || 1;
                  return Object.entries(stats.by_type)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => {
                      const config = changeTypeConfig[type];
                      const percent = Math.round((count / typeTotal) * 100);
                      
                      return (
                        <div key={type} style={{ marginBottom: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <Tag color={config?.color}>{config?.label || type}</Tag>
                            <Text>{count} ({percent}%)</Text>
                          </div>
                          <Progress 
                            percent={percent} 
                            strokeColor={config?.color} 
                            showInfo={false}
                            size="small"
                          />
                        </div>
                      );
                    });
                })()}
              </div>
            ) : (
              <Empty description="No type data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        {/* Risk Distribution */}
        <Col span={8}>
          <Card 
            title={<><WarningOutlined /> Risk Distribution</>}
            bordered={false}
          >
            {stats?.by_risk && Object.keys(stats.by_risk).length > 0 ? (
              <div>
                {(() => {
                  const riskTotal = Object.values(stats.by_risk).reduce((s, c) => s + c, 0) || 1;
                  return ['critical', 'high', 'medium', 'low'].map(risk => {
                    const count = stats.by_risk[risk] || 0;
                    const config = riskLevelConfig[risk];
                    const percent = Math.round((count / riskTotal) * 100);
                    
                    return (
                      <div key={risk} style={{ marginBottom: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Tag color={config?.color}>{config?.label}</Tag>
                          <Text>{count}</Text>
                        </div>
                        <Progress 
                          percent={percent} 
                          strokeColor={config?.color} 
                          showInfo={false}
                          size="small"
                        />
                      </div>
                    );
                  });
                })()}
              </div>
            ) : (
              <Empty description="No risk data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Top Workloads */}
        <Col span={8}>
          <Card 
            title={<><TrophyOutlined /> Top Changed Workloads</>}
            bordered={false}
            bodyStyle={{ maxHeight: 280, overflow: 'auto' }}
          >
            {topWorkloads.length > 0 ? (
              <Table
                dataSource={topWorkloads}
                columns={[
                  {
                    title: 'Workload',
                    dataIndex: 'name',
                    key: 'name',
                    render: (name: string, record: any) => (
                      <div>
                        <Text strong ellipsis style={{ maxWidth: 120, display: 'block' }}>{name}</Text>
                        <Text type="secondary" style={{ fontSize: 10 }}>{record.namespace}</Text>
                      </div>
                    ),
                  },
                  {
                    title: 'Changes',
                    dataIndex: 'count',
                    key: 'count',
                    width: 70,
                    render: (count: number) => (
                      <Tag color={count > 5 ? 'red' : count > 2 ? 'orange' : 'green'}>
                        {count}
                      </Tag>
                    ),
                  },
                ]}
                pagination={false}
                size="small"
                showHeader={false}
                rowKey="name"
              />
            ) : (
              <Empty description="No workload data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Namespace Distribution */}
        <Col span={8}>
          <Card 
            title={<><BarChartOutlined /> By Namespace</>}
            bordered={false}
            bodyStyle={{ maxHeight: 280, overflow: 'auto' }}
          >
            {namespaceData.length > 0 ? (
              <div>
                {namespaceData.slice(0, 8).map(ns => (
                  <div key={ns.namespace} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text ellipsis style={{ maxWidth: 120 }}>{ns.namespace}</Text>
                      <Text type="secondary">{ns.count} ({ns.percent}%)</Text>
                    </div>
                    <Progress 
                      percent={ns.percent} 
                      strokeColor="#7c8eb5" 
                      showInfo={false}
                      size="small"
                    />
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="No namespace data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ChangeAnalytics;
