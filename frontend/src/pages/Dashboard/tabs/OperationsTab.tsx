import React, { useMemo } from 'react';
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
  Tooltip,
  Empty,
  Spin,
  Badge,
  theme
} from 'antd';
import { 
  ClusterOutlined,
  ExperimentOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  SwapOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  FieldTimeOutlined,
  LineChartOutlined,
  ArrowUpOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetClustersQuery } from '../../../store/api/clusterApi';
import { useGetAnalysesQuery } from '../../../store/api/analysisApi';
import { useGetEventStatsQuery } from '../../../store/api/eventsApi';
import { useGetCommunicationStatsQuery } from '../../../store/api/communicationApi';
import { useGetWorkloadStatsQuery } from '../../../store/api/workloadApi';
import { useGetChangesQuery } from '../../../store/api/changesApi';
import { Analysis } from '../../../types';
import { useTheme } from '../../../contexts/ThemeContext';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';
import DonutChart from '../components/DonutChart';
import MiniAreaChart from '../components/MiniAreaChart';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;
const { useToken } = theme;

interface OperationsTabProps {
  clusterId?: number;
  analysisId?: number;
}

const OperationsTab: React.FC<OperationsTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  
  // Theme-aware colors
  const cardBg = isDark ? '#1f1f1f' : '#fafbfc';
  const textPrimary = isDark ? 'rgba(255,255,255,0.85)' : '#2d3748';
  const textSecondary = isDark ? 'rgba(255,255,255,0.45)' : '#5a6978';
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#718096';
  
  // API Queries
  const { data: clustersData } = useGetClustersQuery();
  const clusters = clustersData?.clusters || [];
  const currentCluster = clusters.find((c: any) => c.id === clusterId);
  const supportedGadgetVersion = clustersData?.supported_gadget_version || '';

  const { data: analyses = [], isLoading: analysesLoading } = useGetAnalysesQuery(
    { cluster_id: clusterId },
    { skip: !clusterId }
  );

  const { data: eventStats, isLoading: eventsLoading } = useGetEventStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  const { data: commStats, isLoading: commLoading } = useGetCommunicationStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  const { data: workloadStats, isLoading: workloadsLoading } = useGetWorkloadStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId || !analysisId }
  );

  const { data: changesData, isLoading: changesLoading } = useGetChangesQuery(
    { 
      cluster_id: clusterId!, 
      analysis_id: analysisId,
      limit: 5 
    },
    { skip: !clusterId }
  );

  // Computed values
  const analysisStats = useMemo(() => {
    if (!Array.isArray(analyses)) return { total: 0, running: 0, completed: 0, draft: 0 };
    return {
      total: analyses.length,
      running: analyses.filter((a: Analysis) => a.status === 'running').length,
      completed: analyses.filter((a: Analysis) => a.status === 'completed' || a.status === 'stopped').length,
      draft: analyses.filter((a: Analysis) => a.status === 'draft').length,
    };
  }, [analyses]);

  const recentChanges = changesData?.changes || [];
  const changeStats = changesData?.stats;

  const isLoading = analysesLoading || eventsLoading || commLoading || workloadsLoading || changesLoading;

  // Event type colors
  const eventTypeColors: Record<string, string> = {
    network_flow: '#0891b2',
    dns_query: '#4caf50',
    process_event: '#7c8eb5',
    security_event: '#c97a6d',
    oom_event: '#f76e6e',
    bind_event: '#22a6a6',
    sni_event: '#69b1ff',
    file_event: '#a67c9e',
    mount_event: '#8fa855',
  };

  if (!clusterId) {
    return <Empty description="Select a cluster to view operations data" />;
  }

  // Donut chart data for event distribution
  const eventDonutData = useMemo(() => {
    if (!eventStats?.event_counts) return [];
    return Object.entries(eventStats.event_counts)
      .sort(([, a], [, b]) => (b as number) - (a as number))
      .slice(0, 6)
      .map(([type, count]) => ({
        label: type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        value: count as number,
        color: eventTypeColors[type] || '#8c8c8c',
      }));
  }, [eventStats]);

  return (
    <div>
      {/* Top Stats Row - Animated Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Total Clusters"
            value={clusters.length}
            icon={<ClusterOutlined />}
            color="#2eb8b8"
            subtitle={`${clusters.filter((c: any) => c.status === 'active').length} active`}
            loading={!clustersData}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Analyses"
            value={analysisStats.total}
            icon={<ExperimentOutlined />}
            color="#3cc9c4"
            subtitle={`${analysisStats.running} running`}
            loading={analysesLoading}
            pulseEffect={analysisStats.running > 0}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Connections"
            value={commStats?.total_communications || 0}
            icon={<ApiOutlined />}
            color="#64b5f6"
            subtitle={`${commStats?.unique_namespaces || 0} namespaces`}
            loading={commLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Total Events"
            value={eventStats?.total_events || 0}
            icon={<ThunderboltOutlined />}
            color="#e57373"
            formatter={(v) => v >= 1000000 ? `${(v/1000000).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(1)}K` : v.toString()}
            subtitle={`${Object.keys(eventStats?.event_counts || {}).length} event types`}
            loading={eventsLoading}
          />
        </Col>
      </Row>

      {/* Second Row - Cluster Info & Event Distribution */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Cluster Status */}
        <Col xs={24} lg={8}>
          <Card 
            title={
              <Space>
                <ClusterOutlined style={{ color: '#0891b2' }} />
                <span>Cluster Status</span>
              </Space>
            }
            bordered={false}
            style={{ height: '100%' }}
          >
            {currentCluster ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text strong>{currentCluster.name}</Text>
                  <Tag color={currentCluster.status === 'active' ? 'success' : 'default'}>
                    {currentCluster.status?.toUpperCase()}
                  </Tag>
                </div>
                
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic 
                      title="Nodes" 
                      value={currentCluster.total_nodes || 0}
                      prefix={<CloudServerOutlined style={{ color: '#0891b2' }} />}
                      valueStyle={{ fontSize: 20 }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic 
                      title="Pods" 
                      value={currentCluster.total_pods || 0}
                      prefix={<DatabaseOutlined style={{ color: '#4caf50' }} />}
                      valueStyle={{ fontSize: 20 }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic 
                      title="Namespaces" 
                      value={currentCluster.total_namespaces || 0}
                      prefix={<ClusterOutlined style={{ color: '#7c8eb5' }} />}
                      valueStyle={{ fontSize: 20 }}
                    />
                  </Col>
                </Row>

                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Gadget: {' '}
                    <Tag color={currentCluster.gadget_health_status === 'healthy' ? 'green' : 'orange'}>
                      {currentCluster.gadget_health_status || 'unknown'}
                    </Tag>
                    {currentCluster.gadget_version && (() => {
                      let needsUpgrade = false;
                      if (supportedGadgetVersion) {
                        const pa = currentCluster.gadget_version.replace('v','').split('.').map(Number);
                        const pb = supportedGadgetVersion.replace('v','').split('.').map(Number);
                        for (let i = 0; i < 3; i++) {
                          if ((pa[i]||0) < (pb[i]||0)) { needsUpgrade = true; break; }
                          if ((pa[i]||0) > (pb[i]||0)) { break; }
                        }
                      }
                      return needsUpgrade ? (
                        <Tooltip title={`Upgrade available: ${supportedGadgetVersion}. Go to Cluster Management to upgrade.`}>
                          <span
                            style={{
                              marginLeft: 8,
                              fontSize: 11,
                              color: '#fa8c16',
                              cursor: 'pointer',
                              border: '1px solid #ffd591',
                              borderRadius: 10,
                              padding: '1px 8px',
                              background: '#fff7e6',
                              lineHeight: '18px',
                            }}
                          >
                            {currentCluster.gadget_version} <ArrowUpOutlined style={{ fontSize: 9 }} />
                          </span>
                        </Tooltip>
                      ) : (
                        <Text type="secondary" style={{ marginLeft: 8 }}>
                          {currentCluster.gadget_version}
                        </Text>
                      );
                    })()}
                  </Text>
                </div>
              </Space>
            ) : (
              <Empty description="No cluster selected" />
            )}
          </Card>
        </Col>

        {/* Event Distribution - Donut Chart */}
        <Col xs={24} lg={8}>
          <Card 
            title={
              <Space>
                <ThunderboltOutlined style={{ color: '#d4a844' }} />
                <span>Event Distribution</span>
              </Space>
            }
            bordered={false}
            style={{ height: '100%' }}
            extra={
              <Tag color="orange" style={{ fontSize: 10 }}>
                {(eventStats?.total_events || 0).toLocaleString()} total
              </Tag>
            }
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : eventDonutData.length > 0 ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                <DonutChart
                  data={eventDonutData}
                  size={180}
                  thickness={24}
                  centerValue={Object.keys(eventStats?.event_counts || {}).length}
                  centerLabel="Event Types"
                  animated={true}
                />
              </div>
            ) : (
              <Empty description="No events recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Workload Summary */}
        <Col xs={24} lg={8}>
          <Card 
            title={
              <Space>
                <DatabaseOutlined style={{ color: '#7c8eb5' }} />
                <span>Workload Summary</span>
              </Space>
            }
            bordered={false}
            style={{ height: '100%' }}
            extra={
              <Tag color="purple" style={{ fontSize: 10 }}>
                {workloadStats?.total_workloads || 0} total
              </Tag>
            }
          >
            {workloadsLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : workloadStats?.by_type ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Row gutter={[8, 8]}>
                  {Object.entries(workloadStats.by_type).map(([type, count], index) => {
                    const colors = ['#0891b2', '#4caf50', '#7c8eb5', '#d4a844', '#22a6a6', '#c97a6d'];
                    const color = colors[index % colors.length];
                    return (
                      <Col span={12} key={type}>
                        <div style={{ 
                          textAlign: 'center', 
                          background: `linear-gradient(135deg, ${color}15 0%, ${token.colorBgLayout} 100%)`,
                          borderRadius: 8,
                          padding: '12px 8px',
                          border: `1px solid ${color}30`,
                        }}>
                          <Text strong style={{ fontSize: 24, color }}>{count}</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase' }}>
                            {type}
                          </Text>
                        </div>
                      </Col>
                    );
                  })}
                </Row>
                <div style={{ textAlign: 'center', paddingTop: 8 }}>
                  <Progress
                    type="circle"
                    percent={workloadStats.active_workloads ? Math.round((workloadStats.active_workloads / workloadStats.total_workloads) * 100) : 0}
                    size={60}
                    strokeColor="#4caf50"
                    format={() => (
                      <span style={{ fontSize: 12, fontWeight: 600 }}>
                        {workloadStats.active_workloads || 0}
                        <br />
                        <span style={{ fontSize: 9, color: token.colorTextSecondary }}>Active</span>
                      </span>
                    )}
                  />
                </div>
              </Space>
            ) : (
              <Empty description="No workloads discovered" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Third Row - Recent Activity */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Running Analyses - Enhanced */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <ExperimentOutlined style={{ color: '#4caf50' }} />
                <span>Active Analyses</span>
                {analysisStats.running > 0 && (
                  <Badge count={analysisStats.running} style={{ backgroundColor: '#4caf50' }} />
                )}
              </Space>
            }
            bordered={false}
            extra={
              <Space size={4}>
                <Tag color="green" icon={<PlayCircleOutlined />} style={{ fontSize: 10 }}>
                  {analysisStats.running} Running
                </Tag>
                <Tag color="blue" icon={<CheckCircleOutlined />} style={{ fontSize: 10 }}>
                  {analysisStats.completed} Completed
                </Tag>
              </Space>
            }
          >
            {analysesLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : (
              <List
                dataSource={Array.isArray(analyses) ? analyses.filter((a: Analysis) => a.status === 'running').slice(0, 5) : []}
                locale={{ emptyText: <Empty description="No running analyses" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(analysis: Analysis) => {
                  const duration = analysis.started_at ? dayjs().diff(dayjs(analysis.started_at), 'minute') : 0;
                  return (
                    <List.Item
                      style={{
                        background: `linear-gradient(90deg, ${token.colorPrimary}08 0%, transparent 100%)`,
                        margin: '4px 0',
                        padding: '12px 16px',
                        borderRadius: 8,
                        border: `1px solid ${token.colorBorderSecondary}`,
                      }}
                    >
                      <List.Item.Meta
                        avatar={
                          <div style={{
                            width: 40,
                            height: 40,
                            borderRadius: 8,
                            background: '#3cc9c4',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            position: 'relative',
                          }}>
                            <ExperimentOutlined style={{ color: token.colorTextLightSolid, fontSize: 18 }} />
                            <div style={{
                              position: 'absolute',
                              top: -2,
                              right: -2,
                              width: 10,
                              height: 10,
                              borderRadius: '50%',
                              background: '#4caf50',
                              animation: 'pulse 1.5s infinite',
                            }} />
                          </div>
                        }
                        title={
                          <Space>
                            <Text strong>{analysis.name}</Text>
                            <Tag color="cyan" style={{ fontSize: 10 }}>{analysis.scope_type}</Tag>
                          </Space>
                        }
                        description={
                          <Space size="middle">
                            <Space size={4}>
                              <FieldTimeOutlined style={{ color: token.colorTextSecondary }} />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {duration < 60 ? `${duration}m` : `${Math.floor(duration / 60)}h ${duration % 60}m`}
                              </Text>
                            </Space>
                            <Space size={4}>
                              <ClockCircleOutlined style={{ color: token.colorTextSecondary }} />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                Started {dayjs(analysis.started_at).format('MM-DD HH:mm')}
                              </Text>
                            </Space>
                          </Space>
                        }
                      />
                      <Tag 
                        color="processing" 
                        icon={<PlayCircleOutlined />}
                        style={{ 
                          borderRadius: 12,
                          padding: '2px 12px',
                        }}
                      >
                        RUNNING
                      </Tag>
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>
        </Col>

        {/* Recent Changes - Enhanced Timeline Style */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <SwapOutlined style={{ color: '#d4a844' }} />
                <span>Recent Changes</span>
              </Space>
            }
            bordered={false}
            extra={
              changeStats?.total_changes ? (
                <Space size={4}>
                  {changeStats?.by_risk?.critical > 0 && (
                    <Tag color="red" style={{ fontSize: 10 }}>{changeStats.by_risk.critical} Critical</Tag>
                  )}
                  <Tag color="orange" style={{ fontSize: 10 }}>{changeStats.total_changes} Total</Tag>
                </Space>
              ) : null
            }
          >
            {changesLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : (
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
                
                {recentChanges.length === 0 ? (
                  <Empty description="No recent changes" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  recentChanges.slice(0, 5).map((change: any, index: number) => {
                    const riskColors: Record<string, string> = {
                      critical: '#cf1322',
                      high: '#e05252',
                      medium: '#d4a844',
                      low: '#4caf50',
                    };
                    const riskColor = riskColors[change.risk] || '#8c8c8c';
                    
                    return (
                      <div 
                        key={change.id || index}
                        style={{
                          position: 'relative',
                          paddingLeft: 20,
                          paddingBottom: 16,
                          marginBottom: index < 4 ? 0 : 0,
                        }}
                      >
                        {/* Timeline dot */}
                        <div style={{
                          position: 'absolute',
                          left: -14,
                          top: 4,
                          width: 12,
                          height: 12,
                          borderRadius: '50%',
                          background: riskColor,
                          border: `2px solid ${token.colorBgContainer}`,
                          boxShadow: `0 0 0 2px ${riskColor}30`,
                        }} />
                        
                        <div style={{
                          background: token.colorBgLayout,
                          borderRadius: 8,
                          padding: '10px 12px',
                          borderLeft: `3px solid ${riskColor}`,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <Space size={4}>
                              <Tag color={riskColor} style={{ fontSize: 10, margin: 0, textTransform: 'uppercase' }}>
                                {change.risk}
                              </Tag>
                              <Text strong style={{ fontSize: 12 }}>{change.target}</Text>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 10 }}>
                              {dayjs(change.timestamp).format('MM-DD HH:mm')}
                            </Text>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {change.namespace}
                          </Text>
                          <Tooltip title={change.details}>
                            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }} ellipsis>
                              {change.details}
                            </Text>
                          </Tooltip>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* Top Pods */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card 
            title={
              <Space>
                <CloudServerOutlined style={{ color: '#22a6a6' }} />
                <span>Top Active Pods</span>
              </Space>
            }
            bordered={false}
          >
            {eventsLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : eventStats?.top_pods && eventStats.top_pods.length > 0 ? (
              <Row gutter={[16, 16]}>
                {eventStats.top_pods.slice(0, 8).map((pod, index) => (
                  <Col xs={24} sm={12} md={6} key={`${pod.namespace}-${pod.pod}`}>
                    <Card size="small" style={{ background: token.colorBgLayout }}>
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Text strong style={{ fontSize: 13 }} ellipsis>
                            {index + 1}. {pod.pod}
                          </Text>
                        </div>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {pod.namespace}
                        </Text>
                        <div style={{ marginTop: 8 }}>
                          <Text style={{ fontSize: 16, fontWeight: 600, color: token.colorPrimary }}>
                            {pod.count.toLocaleString()}
                          </Text>
                          <Text type="secondary" style={{ marginLeft: 4, fontSize: 11 }}>
                            events
                          </Text>
                        </div>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty description="No pod activity data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default OperationsTab;

